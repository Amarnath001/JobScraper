import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job
from app.schemas.job import NormalizedJob
from app.core.config import get_settings
from app.services.dedupe_service import fingerprint_for_normalized
from app.services.filter_service import classify_job
from app.services.location_filter_service import is_us_or_remote

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IngestResult:
    jobs_seen_total: int = 0
    jobs_inserted_total: int = 0
    jobs_inserted_software_related: int = 0
    jobs_inserted_entry_level: int = 0
    jobs_inserted_digest_eligible: int = 0
    jobs_skipped_international: int = 0
    jobs_skipped_non_software: int = 0
    jobs_skipped_non_entry_level: int = 0
    inactive_jobs_marked: int = 0

    @property
    def jobs_seen(self) -> int:
        return self.jobs_seen_total

    @property
    def new_jobs_created(self) -> int:
        return self.jobs_inserted_total


def merge_ingest_results(target: IngestResult, source: IngestResult) -> None:
    target.jobs_seen_total += source.jobs_seen_total
    target.jobs_inserted_total += source.jobs_inserted_total
    target.jobs_inserted_software_related += source.jobs_inserted_software_related
    target.jobs_inserted_entry_level += source.jobs_inserted_entry_level
    target.jobs_inserted_digest_eligible += source.jobs_inserted_digest_eligible
    target.jobs_skipped_international += source.jobs_skipped_international
    target.jobs_skipped_non_software += source.jobs_skipped_non_software
    target.jobs_skipped_non_entry_level += source.jobs_skipped_non_entry_level
    target.inactive_jobs_marked += source.inactive_jobs_marked


async def ingest_jobs_for_company(
    session: AsyncSession,
    *,
    company_id: int,
    company_name: str,
    normalized_jobs: list[NormalizedJob],
) -> IngestResult:
    now = utc_now()
    seen_hashes: set[str] = set()
    result = IngestResult(jobs_seen_total=len(normalized_jobs))
    us_only = get_settings().us_only_mode

    for nj in normalized_jobs:
        if us_only and not is_us_or_remote(nj.location):
            result.jobs_skipped_international += 1
            logger.info(
                "Skipping international job: Company=%s Location=%s",
                company_name,
                nj.location or "",
            )
            continue
        fp = fingerprint_for_normalized(company_name, nj)
        seen_hashes.add(fp)
        filter_res = classify_job(nj.title, nj.description_text, nj.level)

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
                entry_level_score=filter_res.entry_level_score,
                is_entry_level=filter_res.is_entry_level_related,
                is_software_engineering_related=filter_res.is_software_engineering_related,
                fingerprint_hash=fp,
                raw_payload=nj.raw_payload,
            )
            session.add(job)
            result.jobs_inserted_total += 1
            if filter_res.is_software_engineering_related:
                result.jobs_inserted_software_related += 1
            if filter_res.is_entry_level_related:
                result.jobs_inserted_entry_level += 1
            if filter_res.is_digest_eligible:
                result.jobs_inserted_digest_eligible += 1
            else:
                if not filter_res.is_software_engineering_related:
                    result.jobs_skipped_non_software += 1
                elif not filter_res.is_entry_level_related:
                    result.jobs_skipped_non_entry_level += 1
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
            existing.entry_level_score = filter_res.entry_level_score
            existing.is_entry_level = filter_res.is_entry_level_related
            existing.is_software_engineering_related = filter_res.is_software_engineering_related

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
            result.inactive_jobs_marked = len(stale_ids)
    else:
        res = await session.execute(select(Job.id).where(Job.company_id == company_id, Job.is_active.is_(True)))
        all_active = [row[0] for row in res.all()]
        if all_active:
            await session.execute(
                update(Job).where(Job.id.in_(all_active)).values(is_active=False, last_seen_at=now)
            )
            result.inactive_jobs_marked = len(all_active)

    await session.flush()

    if result.jobs_skipped_international:
        logger.info(
            "Location filter: company=%s skipped=%s kept=%s",
            company_name,
            result.jobs_skipped_international,
            len(seen_hashes),
        )

    return result
