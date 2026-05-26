"""
Recompute entry-level and software-engineering filters for all jobs in the database.

  python scripts/recompute_job_filters.py
  docker compose exec app python scripts/recompute_job_filters.py
"""

from __future__ import annotations

import asyncio
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

from sqlalchemy import select

from app.core.database import get_session_factory
from app.core.logging import setup_logging
from app.db.models import Job
from app.services.filter_service import classify_job


async def main() -> None:
    setup_logging()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    factory = get_session_factory()
    updated = 0
    software_related = 0
    entry_level = 0
    digest_eligible = 0

    async with factory() as session:
        res = await session.execute(select(Job).order_by(Job.id))
        jobs = list(res.scalars().all())
        total = len(jobs)

        for job in jobs:
            result = classify_job(job.title, job.description_text, job.level)
            job.entry_level_score = result.entry_level_score
            job.is_entry_level = result.is_entry_level_related
            job.is_software_engineering_related = result.is_software_engineering_related
            updated += 1
            if result.is_software_engineering_related:
                software_related += 1
            if result.is_entry_level_related:
                entry_level += 1
            if result.is_digest_eligible:
                digest_eligible += 1

        await session.commit()

    print("=== RECOMPUTE JOB FILTERS ===")
    print(f"total={total}")
    print(f"updated={updated}")
    print(f"software_related={software_related}")
    print(f"entry_level={entry_level}")
    print(f"digest_eligible={digest_eligible}")


if __name__ == "__main__":
    asyncio.run(main())
