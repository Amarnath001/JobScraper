"""
Insert example companies (Greenhouse, Lever, Ashby) if missing.
Run: python -m scripts.seed_example_companies
(from project root with DATABASE_URL set)
"""

import asyncio
import os
import sys

# Allow running as script or module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.core.database import get_session_factory
from app.db.models import Company


EXAMPLES: list[dict] = [
    {
        "name": "Example — Greenhouse (Netflix)",
        "careers_url": "https://explore.jobs.netflix.net/careers",
        "source_type": "greenhouse",
        "source_config": {"board_token": "netflix"},
        "enabled": False,
    },
    {
        "name": "Example — Lever (Figma)",
        "careers_url": "https://jobs.lever.co/figma",
        "source_type": "lever",
        "source_config": {"company": "figma"},
        "enabled": False,
    },
    {
        "name": "Example — Ashby (Linear)",
        "careers_url": "https://jobs.ashbyhq.com/linear",
        "source_type": "ashby",
        "source_config": {"organization": "linear"},
        "enabled": False,
    },
]


async def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    factory = get_session_factory()
    async with factory() as session:
        for row in EXAMPLES:
            existing = await session.scalar(select(Company).where(Company.name == row["name"]))
            if existing:
                continue
            session.add(
                Company(
                    name=row["name"],
                    careers_url=row["careers_url"],
                    source_type=row["source_type"],
                    source_config=row["source_config"],
                    enabled=row["enabled"],
                )
            )
        await session.commit()
    print("Seed complete (skipped rows that already exist).")


if __name__ == "__main__":
    asyncio.run(main())
