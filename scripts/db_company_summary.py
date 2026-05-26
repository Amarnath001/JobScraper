"""
Print company counts from the database (local or Render via DATABASE_URL).

  python scripts/db_company_summary.py
  python scripts/db_company_summary.py --brief
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

from sqlalchemy import select

from app.core.database import get_session_factory
from app.core.logging import setup_logging
from app.db.models import Company
from app.services.company_targets_service import UNCONFIGURED_SOURCE_TYPE

UNCONFIGURED_LABELS = frozenset({UNCONFIGURED_SOURCE_TYPE, "", "none", "null"})


def _is_unconfigured_source_type(source_type: str | None) -> bool:
    if source_type is None:
        return True
    normalized = source_type.strip().lower()
    return normalized in UNCONFIGURED_LABELS or not normalized


async def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Summarize companies in the database")
    parser.add_argument(
        "--brief",
        action="store_true",
        help="Print only total and enabled counts (for scrape workflow logs)",
    )
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    factory = get_session_factory()
    async with factory() as session:
        res = await session.execute(select(Company).order_by(Company.name))
        companies = list(res.scalars().all())

    total = len(companies)
    enabled = sum(1 for c in companies if c.enabled)
    disabled = total - enabled

    if args.brief:
        print(f"companies_total={total}")
        print(f"companies_enabled={enabled}")
        return

    by_source_type: Counter[str] = Counter()
    by_validation_status: Counter[str] = Counter()
    unconfigured_count = 0

    for company in companies:
        st = (company.source_type or "").strip() or UNCONFIGURED_SOURCE_TYPE
        by_source_type[st] += 1
        if _is_unconfigured_source_type(company.source_type):
            unconfigured_count += 1
        status = (company.last_validation_status or "never").strip() or "never"
        by_validation_status[status] += 1

    print("=== DATABASE COMPANY SUMMARY ===")
    print(f"total_companies={total}")
    print(f"enabled_companies={enabled}")
    print(f"disabled_companies={disabled}")
    print(f"unconfigured_or_empty_source_type={unconfigured_count}")
    print()
    print("--- by source_type ---")
    for source_type, count in sorted(by_source_type.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {source_type}: {count}")
    print()
    print("--- by last_validation_status ---")
    for status, count in sorted(by_validation_status.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {status}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
