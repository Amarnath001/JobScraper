import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import get_settings
from app.scrapers.base import BaseScraper
from app.schemas.job import NormalizedJob

logger = logging.getLogger(__name__)


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        try:
            if value.endswith("Z"):
                value = value.replace("Z", "+00:00")
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


class GreenhouseScraper(BaseScraper):
    async def fetch_raw_jobs(self) -> list[dict]:
        token = self.source_config.get("board_token") or self.source_config.get("token")
        if not token:
            raise ValueError("Greenhouse source_config requires 'board_token' (or 'token')")
        url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
        settings = get_settings()
        timeout = httpx.Timeout(settings.scrape_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        jobs = data.get("jobs") or []
        if not isinstance(jobs, list):
            return []
        return [j for j in jobs if isinstance(j, dict)]

    def normalize_job(self, raw_job: dict) -> NormalizedJob:
        job_id = raw_job.get("id")
        ext_id = str(job_id) if job_id is not None else None
        title = str(raw_job.get("title") or "Untitled")
        loc_obj = raw_job.get("location") or {}
        location = None
        if isinstance(loc_obj, dict):
            location = loc_obj.get("name")
        elif isinstance(loc_obj, str):
            location = loc_obj
        url = str(raw_job.get("absolute_url") or raw_job.get("url") or self.careers_url)
        desc = raw_job.get("content")
        if desc is not None:
            desc = str(desc)[:50000]
        posted = _parse_ts(raw_job.get("updated_at") or raw_job.get("first_published"))

        return NormalizedJob(
            company_name=self.company_name,
            source_type="greenhouse",
            external_job_id=ext_id,
            title=title,
            team=None,
            location=location,
            employment_type=None,
            level=None,
            url=url,
            description_text=desc,
            posted_at=posted,
            raw_payload=raw_job,
        )
