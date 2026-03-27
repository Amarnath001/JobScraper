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
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    if isinstance(value, str):
        try:
            if value.endswith("Z"):
                value = value.replace("Z", "+00:00")
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


class LeverScraper(BaseScraper):
    async def fetch_raw_jobs(self) -> list[dict]:
        company = self.source_config.get("company") or self.source_config.get("site")
        if not company:
            raise ValueError("Lever source_config requires 'company' (Lever site name)")
        url = f"https://api.lever.co/v0/postings/{company}"
        settings = get_settings()
        timeout = httpx.Timeout(settings.scrape_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        if not isinstance(data, list):
            return []
        return [j for j in data if isinstance(j, dict)]

    def normalize_job(self, raw_job: dict) -> NormalizedJob:
        ext_id = raw_job.get("id")
        ext_id = str(ext_id) if ext_id is not None else None
        title = str(raw_job.get("text") or raw_job.get("title") or "Untitled")
        locs = raw_job.get("categories", {}).get("location") if isinstance(raw_job.get("categories"), dict) else None
        location = None
        if isinstance(locs, str):
            location = locs
        elif isinstance(locs, list) and locs:
            location = ", ".join(str(x) for x in locs[:5])
        url = str(raw_job.get("hostedUrl") or raw_job.get("applyUrl") or self.careers_url)
        desc = raw_job.get("descriptionPlain") or raw_job.get("description")
        if desc is not None:
            desc = str(desc)[:50000]
        team = None
        cats = raw_job.get("categories")
        if isinstance(cats, dict):
            team = cats.get("team")
            if team is not None:
                team = str(team)
        posted = _parse_ts(raw_job.get("createdAt") or raw_job.get("updatedAt"))

        return NormalizedJob(
            company_name=self.company_name,
            source_type="lever",
            external_job_id=ext_id,
            title=title,
            team=team,
            location=location,
            employment_type=None,
            level=None,
            url=url,
            description_text=desc,
            posted_at=posted,
            raw_payload=raw_job,
        )
