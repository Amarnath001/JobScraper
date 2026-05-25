"""
Upsert companies from data/companies.json (match on name + source_type).

  python scripts/import_companies_from_json.py
  docker compose exec app python scripts/import_companies_from_json.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import get_session_factory
from app.services.company_import_service import load_companies_from_json, upsert_companies_from_rows

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "companies.json"


async def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    path = Path(os.environ.get("COMPANIES_JSON", DEFAULT_PATH))
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")

    rows = load_companies_from_json(path)
    factory = get_session_factory()
    async with factory() as session:
        inserted, updated = await upsert_companies_from_rows(session, rows)
        await session.commit()

    print(f"Import complete from {path}: inserted={inserted} updated={updated} total_rows={len(rows)}")


if __name__ == "__main__":
    asyncio.run(main())
