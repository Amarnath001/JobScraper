"""
Enable generic Playwright scraping for companies without a configured ATS API.

  python scripts/enable_generic_for_unconfigured.py --limit 25
  docker compose exec app python scripts/enable_generic_for_unconfigured.py --limit 25
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

from sqlalchemy import select

from app.core.database import get_session_factory
from app.core.logging import setup_logging
from app.db.models import Company
from app.services.company_targets_service import SCRAPER_SOURCE_TYPES, UNCONFIGURED_SOURCE_TYPE

API_SOURCE_TYPES = SCRAPER_SOURCE_TYPES - {"generic_playwright"}


def is_eligible_for_generic(company: Company) -> bool:
    if not (company.careers_url or "").strip():
        return False
    if company.source_type == "generic_playwright":
        return False
    if company.source_type == UNCONFIGURED_SOURCE_TYPE:
        return True
    if company.source_type and company.source_type not in API_SOURCE_TYPES:
        return True
    return False


async def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(
        description="Set unconfigured companies to generic_playwright scraper",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max companies to update")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without saving")
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    factory = get_session_factory()
    async with factory() as session:
        res = await session.execute(select(Company).order_by(Company.name))
        all_companies = list(res.scalars().all())

    eligible = [c for c in all_companies if is_eligible_for_generic(c)]
    if args.limit:
        eligible = eligible[: args.limit]

    if not eligible:
        print("No eligible unconfigured companies found.")
        return

    prefix = "[dry-run] " if args.dry_run else ""
    updated = 0

    async with factory() as session:
        for row in eligible:
            company = await session.get(Company, row.id)
            if company is None:
                continue
            careers = (company.careers_url or "").strip()
            print(
                f"{prefix}{company.name}: {company.source_type} -> generic_playwright "
                f"({careers})"
            )
            if not args.dry_run:
                company.source_type = "generic_playwright"
                company.source_config = {"careers_url": careers}
                company.enabled = True
                company.last_error = None
                updated += 1
        if not args.dry_run:
            await session.commit()

    print(f"\n=== SUMMARY ===")
    print(f"eligible={len(eligible)}")
    print(f"updated={updated if not args.dry_run else 0}")
    if args.dry_run:
        print("(dry-run: no database changes written)")


if __name__ == "__main__":
    asyncio.run(main())
