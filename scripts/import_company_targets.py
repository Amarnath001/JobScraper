"""
Import companies from data/company_targets.csv.

  python scripts/import_company_targets.py
  python scripts/import_company_targets.py --path data/company_targets.csv
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

from app.core.database import get_session_factory
from app.services.company_targets_service import (
    CompanyTargetImportSummary,
    parse_company_targets_csv,
    upsert_company_targets,
)

DEFAULT_PATH = Path(_root) / "data" / "company_targets.csv"


def _print_summary(summary: CompanyTargetImportSummary, path: Path) -> None:
    print(f"Import complete from {path}")
    print(
        f"inserted={summary.inserted} updated={summary.updated} "
        f"skipped={summary.skipped} unconfigured={summary.unconfigured}"
    )
    if summary.errors:
        print("errors:")
        for err in summary.errors:
            print(f"  - {err}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import company targets from CSV")
    parser.add_argument(
        "--path",
        type=Path,
        default=Path(os.environ.get("COMPANY_TARGETS_CSV", DEFAULT_PATH)),
        help="Path to company_targets.csv",
    )
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    rows = parse_company_targets_csv(args.path)
    factory = get_session_factory()
    async with factory() as session:
        summary = await upsert_company_targets(session, rows)
        await session.commit()

    _print_summary(summary, args.path)


if __name__ == "__main__":
    asyncio.run(main())
