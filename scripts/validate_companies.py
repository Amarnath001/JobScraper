"""
Validate companies against public ATS endpoints and update enabled flags.

  python scripts/validate_companies.py
  python scripts/validate_companies.py --all --enable-valid
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import get_session_factory
from app.services.company_validation_service import format_validation_table, validate_all_companies


async def main() -> None:
    parser = argparse.ArgumentParser(description="Validate company ATS sources")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate disabled companies too (default: enabled only)",
    )
    parser.add_argument(
        "--enable-valid",
        action="store_true",
        help="Re-enable companies that pass validation",
    )
    parser.add_argument(
        "--no-disable-on-404",
        action="store_true",
        help="Do not disable companies on HTTP 404",
    )
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    factory = get_session_factory()
    async with factory() as session:
        summary = await validate_all_companies(
            session,
            only_enabled=not args.all,
            disable_on_404=not args.no_disable_on_404,
            re_enable_valid=args.enable_valid,
        )
        await session.commit()

    print(format_validation_table(summary.results))
    print()
    print("=== VALIDATION SUMMARY ===")
    print(f"valid={summary.valid_count}")
    print(f"disabled_on_404={summary.disabled_count}")
    print(f"failed={summary.failed_count}")
    print(f"skipped={summary.skipped_count}")
    if not args.all:
        print("(Only enabled companies were validated; use --all to include disabled)")


if __name__ == "__main__":
    asyncio.run(main())
