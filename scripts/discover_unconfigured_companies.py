"""
Bulk ATS discovery for companies stored as unconfigured in the database.

  python scripts/discover_unconfigured_companies.py --dry-run --limit 25
  python scripts/discover_unconfigured_companies.py --limit 25
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

import httpx
from sqlalchemy import select

from app.core.database import get_session_factory
from app.core.logging import setup_logging
from app.db.models import Company
from app.services.ats_discovery_service import (
    AtsDiscoveryResult,
    classify_discovery_bucket,
    discover_careers_site,
    format_company_discovery_line,
)
from app.services.company_targets_service import SCRAPER_SOURCE_TYPES, UNCONFIGURED_SOURCE_TYPE
from app.services.company_validation_service import probe_company_source
from app.utils.source_urls import careers_url_for

logger = logging.getLogger(__name__)

SUMMARY_KEYS = (
    "processed",
    "configured_supported",
    "detected_unsupported",
    "still_unknown",
    "errors",
    "enabled_after_validation",
)


def _empty_summary() -> dict[str, int]:
    return {key: 0 for key in SUMMARY_KEYS}


async def _load_unconfigured(limit: int | None) -> list[Company]:
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(Company)
            .where(Company.source_type == UNCONFIGURED_SOURCE_TYPE)
            .order_by(Company.name)
        )
        if limit:
            stmt = stmt.limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all())


async def _persist_result(
    company_id: int,
    result: AtsDiscoveryResult,
    bucket: str,
) -> bool:
    """Save discovery to DB; return True if company was enabled."""
    factory = get_session_factory()
    async with factory() as session:
        db_company = await session.get(Company, company_id)
        if db_company is None:
            return False

        if bucket == "configured_supported" and result.source_type in SCRAPER_SOURCE_TYPES:
            db_company.source_type = result.source_type
            db_company.source_config = dict(result.source_config)
            careers = result.final_careers_url or db_company.careers_url
            db_company.careers_url = (
                careers_url_for(result.source_type, db_company.source_config) or careers
            )
            probe = await probe_company_source(db_company)
            if probe.valid:
                db_company.enabled = True
                db_company.last_error = None
                db_company.consecutive_failures = 0
                db_company.last_validation_status = "200"
                await session.commit()
                return True
            db_company.enabled = False
            db_company.last_error = probe.error or f"Validation failed (HTTP {probe.status_code})"
            await session.commit()
            return False

        db_company.enabled = False
        db_company.source_type = UNCONFIGURED_SOURCE_TYPE
        db_company.source_config = {}
        db_company.last_error = result.reason or result.evidence
        await session.commit()
        return False


async def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Discover ATS for unconfigured companies in DB")
    parser.add_argument("--limit", type=int, default=None, help="Max companies to process")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without saving")
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=float(os.environ.get("DISCOVERY_DELAY_SECONDS", "1.5")),
        help="Delay between companies (rate limit)",
    )
    parser.add_argument(
        "--max-follow",
        type=int,
        default=int(os.environ.get("DISCOVERY_MAX_FOLLOW", "5")),
        help="Job-related links to follow per company",
    )
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    companies = await _load_unconfigured(args.limit)
    if not companies:
        print("No unconfigured companies found in database.")
        return

    timeout = httpx.Timeout(float(os.environ.get("SCRAPE_TIMEOUT_SECONDS", "60")))
    summary = _empty_summary()

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for company in companies:
            summary["processed"] += 1
            prefix = "[dry-run] " if args.dry_run else ""
            print(f"\n{prefix}Discovering: {company.name} ({company.careers_url})")

            try:
                result = discover_careers_site(
                    client,
                    company.careers_url,
                    max_follow=args.max_follow,
                )
                bucket = classify_discovery_bucket(result)
                if bucket in summary:
                    summary[bucket] += 1
                else:
                    summary["errors"] += 1
                    bucket = "errors"

                print(f"  -> {format_company_discovery_line(result)}")

                for page in result.pages_inspected[:6]:
                    print(f"     inspected: {page}")
                if len(result.pages_inspected) > 6:
                    print(f"     ... and {len(result.pages_inspected) - 6} more pages")

                if not args.dry_run and bucket != "errors":
                    enabled = await _persist_result(company.id, result, bucket)
                    if enabled:
                        summary["enabled_after_validation"] += 1
                        print("  -> saved and enabled after validation")

            except Exception as exc:
                summary["errors"] += 1
                logger.exception("Discovery failed for %s", company.name)
                print(f"  -> error: {exc}")
                if not args.dry_run:
                    factory = get_session_factory()
                    async with factory() as session:
                        db_company = await session.get(Company, company.id)
                        if db_company:
                            db_company.last_error = f"Discovery error: {exc}"
                            await session.commit()

            if args.delay_seconds > 0:
                time.sleep(args.delay_seconds)

    print("\n=== DISCOVERY SUMMARY ===")
    for key in SUMMARY_KEYS:
        print(f"{key}={summary[key]}")
    if args.dry_run:
        print("(dry-run: no database changes written)")


if __name__ == "__main__":
    asyncio.run(main())
