"""
Validate all companies against public ATS endpoints and update enabled flags.

  python scripts/validate_companies.py
  docker compose exec app python scripts/validate_companies.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import get_session_factory
from app.services.company_validation_service import format_validation_table, validate_all_companies


async def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    factory = get_session_factory()
    async with factory() as session:
        summary = await validate_all_companies(session, disable_on_404=True)
        await session.commit()

    print(format_validation_table(summary.results))
    print()
    print(
        f"valid_count={summary.valid_count} "
        f"disabled_count={summary.disabled_count} "
        f"failed_count={summary.failed_count} "
        f"skipped_count={summary.skipped_count}"
    )


if __name__ == "__main__":
    asyncio.run(main())
