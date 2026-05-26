import logging

import httpx

from app.core.config import get_settings
from app.scrapers.base import BaseScraper
from app.scrapers.parsing import (
    gem_company_from_url,
    normalize_gem_careers_url,
    parse_gem_listing_html,
    parse_timestamp,
)
from app.schemas.job import NormalizedJob

logger = logging.getLogger(__name__)

USER_AGENT = "JobScraper/1.0 (Gem scraper)"


class GemScraper(BaseScraper):
    """
    Gem job board scraper (jobs.gem.com).

    source_config:
      careers_url (required) — e.g. https://jobs.gem.com/company
    """

    def _careers_url(self) -> str:
        url = self.source_config.get("careers_url") or self.careers_url
        if not url:
            raise ValueError("Gem source_config requires careers_url")
        return normalize_gem_careers_url(str(url))

    async def fetch_raw_jobs(self) -> list[dict]:
        careers = self._careers_url()
        settings = get_settings()
        timeout = httpx.Timeout(settings.scrape_timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(careers, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            html = resp.text

        jobs = parse_gem_listing_html(html, careers)

        if not jobs:
            logger.warning("Gem: no job listings found for %s at %s", self.company_name, careers)
        else:
            logger.info("Gem HTML scrape found %s jobs for %s", len(jobs), self.company_name)
        return jobs

    def normalize_job(self, raw_job: dict) -> NormalizedJob:
        url = str(raw_job.get("url") or self._careers_url())
        title = str(raw_job.get("title") or "Open role")
        ext = raw_job.get("external_id")
        if ext is None:
            tail = url.rstrip("/").split("/")[-1]
            if tail and not tail.isalpha():
                ext = tail
        return NormalizedJob(
            company_name=self.company_name,
            source_type="gem",
            external_job_id=str(ext) if ext is not None else None,
            title=title,
            team=None,
            location=raw_job.get("location"),
            employment_type=None,
            level=None,
            url=url,
            description_text=None,
            posted_at=parse_timestamp(raw_job.get("posted_at")),
            raw_payload=raw_job,
        )
