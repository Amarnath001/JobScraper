import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job
from app.schemas.job import NormalizedJob
from app.core.config import get_settings
from app.services.dedupe_service import fingerprint_for_normalized
from app.services.filter_service import score_entry_level
from app.services.location_filter_service import is_us_or_remote

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IngestResult:
    jobs_seen: int
    new_jobs_created: int
    inactive_jobs_marked: int
    jobs_skipped_location: int = 0


async def ingest_jobs_for_company(
    session: AsyncSession,
    *,
    company_id: int,
    company_name: str,
    normalized_jobs: list[NormalizedJob],
) -> IngestResult:
    now = utc_now()
    seen_hashes: set[str] = set()
    new_jobs_created = 0
    jobs_skipped_location = 0
    us_only = get_settings().us_only_mode

    for nj in normalized_jobs:
        if us_only and not is_us_or_remote(nj.location):
            jobs_skipped_location += 1
            logger.info(
                "Skipping international job: Company=%s Location=%s",
                company_name,
                nj.location or "",
            )
            continue
        fp = fingerprint_for_normalized(company_name, nj)
        seen_hashes.add(fp)
        score_res = score_entry_level(nj.title, nj.description_text, nj.level)

        existing = await session.scalar(select(Job).where(Job.fingerprint_hash == fp))

        if existing is None:
            job = Job(
                company_id=company_id,
                source_type=nj.source_type,
                external_job_id=nj.external_job_id,
                title=nj.title,
                team=nj.team,
                location=nj.location,
                employment_type=nj.employment_type,
                level=nj.level,
                url=nj.url,
                description_text=nj.description_text,
                posted_at=nj.posted_at,
                first_seen_at=now,
                last_seen_at=now,
                is_active=True,
                entry_level_score=score_res.score,
                is_entry_level=score_res.is_entry_level,
                fingerprint_hash=fp,
                raw_payload=nj.raw_payload,
            )
            session.add(job)
            new_jobs_created += 1
        else:
            existing.last_seen_at = now
            existing.is_active = True
            existing.title = nj.title
            existing.team = nj.team
            existing.location = nj.location
            existing.employment_type = nj.employment_type
            existing.level = nj.level
            existing.url = nj.url
            existing.description_text = nj.description_text
            existing.posted_at = nj.posted_at
            existing.external_job_id = nj.external_job_id
            existing.source_type = nj.source_type
            existing.raw_payload = nj.raw_payload
            existing.entry_level_score = score_res.score
            existing.is_entry_level = score_res.is_entry_level

    inactive_jobs_marked = 0
    if seen_hashes:
        res = await session.execute(
            select(Job.id).where(
                Job.company_id == company_id,
                Job.is_active.is_(True),
                Job.fingerprint_hash.not_in(seen_hashes),
            )
        )
        stale_ids = [row[0] for row in res.all()]
        if stale_ids:
            await session.execute(
                update(Job)
                .where(Job.id.in_(stale_ids))
                .values(is_active=False, last_seen_at=now)
            )
            inactive_jobs_marked = len(stale_ids)
    else:
        res = await session.execute(select(Job.id).where(Job.company_id == company_id, Job.is_active.is_(True)))
        all_active = [row[0] for row in res.all()]
        if all_active:
            await session.execute(
                update(Job).where(Job.id.in_(all_active)).values(is_active=False, last_seen_at=now)
            )
            inactive_jobs_marked = len(all_active)

    await session.flush()

    if jobs_skipped_location:
        logger.info(
            "Location filter: company=%s skipped=%s kept=%s",
            company_name,
            jobs_skipped_location,
            len(seen_hashes),
        )

    return IngestResult(
        jobs_seen=len(normalized_jobs),
        new_jobs_created=new_jobs_created,
        inactive_jobs_marked=inactive_jobs_marked,
        jobs_skipped_location=jobs_skipped_location,
    )
