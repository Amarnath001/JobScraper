import logging
from datetime import datetime
from typing import Any

import httpx

from app.core.config import get_settings
from app.scrapers.base import BaseScraper
from app.schemas.job import NormalizedJob

logger = logging.getLogger(__name__)


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            if value.endswith("Z"):
                value = value.replace("Z", "+00:00")
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


class AshbyScraper(BaseScraper):
    """
    Uses Ashby public Posting API when available.
    Config keys:
    - organization (slug) — required unless `posting_api_url` is set
    - posting_api_url — optional full URL override
    """

    def _resolve_url(self) -> str:
        if custom := self.source_config.get("posting_api_url"):
            return str(custom)
        org = self.source_config.get("organization") or self.source_config.get("org")
        if not org:
            raise ValueError("Ashby source_config requires 'organization' or 'posting_api_url'")
        return f"https://api.ashbyhq.com/posting-api/job-board/{org}"

    async def fetch_raw_jobs(self) -> list[dict]:
        url = self._resolve_url()
        settings = get_settings()
        timeout = httpx.Timeout(settings.scrape_timeout_seconds)
        headers = {"Accept": "application/json"}
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        jobs = data.get("jobs") if isinstance(data, dict) else None
        if jobs is None and isinstance(data, list):
            jobs = data
        if not isinstance(jobs, list):
            return []
        return [j for j in jobs if isinstance(j, dict)]

    def normalize_job(self, raw_job: dict) -> NormalizedJob:
        ext_id = raw_job.get("id")
        ext_id = str(ext_id) if ext_id is not None else None
        title = str(raw_job.get("title") or "Untitled")
        loc = raw_job.get("location") or raw_job.get("locationName")
        if isinstance(loc, dict):
            location = loc.get("name") or loc.get("primaryLocation")
            if isinstance(location, dict):
                location = location.get("name")
        else:
            location = str(loc) if loc is not None else None
        url = str(raw_job.get("jobUrl") or raw_job.get("url") or self.careers_url)
        desc = raw_job.get("descriptionPlain") or raw_job.get("descriptionHtml") or raw_job.get("description")
        if desc is not None:
            desc = str(desc)[:50000]
        team = raw_job.get("team")
        team = str(team) if team is not None else None
        employment = raw_job.get("employmentType")
        employment = str(employment) if employment is not None else None
        posted = _parse_ts(raw_job.get("publishedDate") or raw_job.get("updatedAt"))

        return NormalizedJob(
            company_name=self.company_name,
            source_type="ashby",
            external_job_id=ext_id,
            title=title,
            team=team,
            location=location,
            employment_type=employment,
            level=None,
            url=url,
            description_text=desc,
            posted_at=posted,
            raw_payload=raw_job,
        )
