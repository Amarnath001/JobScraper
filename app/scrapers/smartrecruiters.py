import logging

import httpx

from app.core.config import get_settings
from app.scrapers.base import BaseScraper
from app.scrapers.parsing import (
    parse_smartrecruiters_api_payload,
    parse_smartrecruiters_listing_html,
    parse_timestamp,
    smartrecruiters_company_from_url,
)
from app.schemas.job import NormalizedJob

logger = logging.getLogger(__name__)

USER_AGENT = "JobScraper/1.0 (SmartRecruiters scraper)"


class SmartRecruitersScraper(BaseScraper):
    """
    SmartRecruiters scraper (public API first, HTML fallback).

    source_config:
      company (required) — company slug
      careers_url (optional) — public board URL for HTML fallback
    """

    def _company_slug(self) -> str:
        slug = self.source_config.get("company")
        if not slug:
            slug = smartrecruiters_company_from_url(
                str(self.source_config.get("careers_url") or self.careers_url or "")
            )
        if not slug:
            raise ValueError(
                "SmartRecruiters source_config requires 'company' or a careers_url with slug"
            )
        return str(slug)

    def _careers_url(self) -> str:
        url = self.source_config.get("careers_url") or self.careers_url
        if url:
            return str(url).rstrip("/")
        return f"https://jobs.smartrecruiters.com/{self._company_slug()}"

    async def fetch_raw_jobs(self) -> list[dict]:
        settings = get_settings()
        timeout = httpx.Timeout(settings.scrape_timeout_seconds)
        company = self._company_slug()

        api_jobs = await self._fetch_via_api(company, timeout)
        if api_jobs:
            return api_jobs

        logger.info(
            "SmartRecruiters API empty/failed for %s; trying HTML at %s",
            self.company_name,
            self._careers_url(),
        )
        return await self._fetch_via_html(self._careers_url(), timeout)

    async def _fetch_via_api(self, company: str, timeout: httpx.Timeout) -> list[dict]:
        url = f"https://api.smartrecruiters.com/v1/companies/{company}/postings"
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                )
                if resp.status_code >= 400:
                    logger.debug("SmartRecruiters API %s returned %s", url, resp.status_code)
                    return []
                data = resp.json()
            jobs = parse_smartrecruiters_api_payload(data)
            if jobs:
                logger.info(
                    "SmartRecruiters API returned %s jobs for %s",
                    len(jobs),
                    self.company_name,
                )
            return jobs
        except Exception as exc:
            logger.debug("SmartRecruiters API failed for %s: %s", self.company_name, exc)
            return []

    async def _fetch_via_html(self, careers_url: str, timeout: httpx.Timeout) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(careers_url, headers={"User-Agent": USER_AGENT})
                resp.raise_for_status()
                jobs = parse_smartrecruiters_listing_html(resp.text, careers_url)
            if not jobs:
                logger.warning(
                    "SmartRecruiters HTML found no jobs for %s at %s",
                    self.company_name,
                    careers_url,
                )
            return jobs
        except Exception as exc:
            logger.warning("SmartRecruiters HTML scrape failed for %s: %s", self.company_name, exc)
            return []

    def normalize_job(self, raw_job: dict) -> NormalizedJob:
        if raw_job.get("_sr_source") == "api":
            job_id = raw_job.get("id") or raw_job.get("uuid")
            ext_id = str(job_id) if job_id is not None else None
            title = str(raw_job.get("name") or raw_job.get("title") or "Untitled")
            location = None
            loc = raw_job.get("location")
            if isinstance(loc, dict):
                parts = [loc.get("city"), loc.get("region"), loc.get("country")]
                location = ", ".join(p for p in parts if p) or loc.get("fullLocation")
            elif isinstance(loc, str):
                location = loc

            url = self._careers_url()
            ref = raw_job.get("ref") or raw_job.get("refNumber")
            if ref:
                url = f"https://jobs.smartrecruiters.com/{self._company_slug()}/{ref}"
            elif job_id:
                url = f"https://jobs.smartrecruiters.com/{self._company_slug()}/posting/{job_id}"

            posted = parse_timestamp(
                raw_job.get("releasedDate") or raw_job.get("createdOn") or raw_job.get("postedDate")
            )
            return NormalizedJob(
                company_name=self.company_name,
                source_type="smartrecruiters",
                external_job_id=ext_id,
                title=title,
                team=None,
                location=location,
                employment_type=raw_job.get("typeOfEmployment", {}).get("label")
                if isinstance(raw_job.get("typeOfEmployment"), dict)
                else None,
                level=None,
                url=url,
                description_text=None,
                posted_at=posted,
                raw_payload=raw_job,
            )

        return NormalizedJob(
            company_name=self.company_name,
            source_type="smartrecruiters",
            external_job_id=None,
            title=str(raw_job.get("title") or "Untitled"),
            team=None,
            location=raw_job.get("location"),
            employment_type=None,
            level=None,
            url=str(raw_job.get("url") or self._careers_url()),
            description_text=None,
            posted_at=parse_timestamp(raw_job.get("posted_at")),
            raw_payload=raw_job,
        )
