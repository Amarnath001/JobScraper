import logging

import httpx
from playwright.async_api import async_playwright

from app.core.config import get_settings
from app.scrapers.base import BaseScraper
from app.scrapers.parsing import parse_icims_listing_html, parse_timestamp
from app.schemas.job import NormalizedJob

logger = logging.getLogger(__name__)

USER_AGENT = "JobScraper/1.0 (iCIMS scraper)"


class ICIMSScraper(BaseScraper):
    """
    iCIMS careers scraper.

    source_config:
      careers_url (required) — e.g. https://careers-company.icims.com/jobs
    """

    def _careers_url(self) -> str:
        url = self.source_config.get("careers_url") or self.careers_url
        if not url:
            raise ValueError("iCIMS source_config requires careers_url")
        return str(url).rstrip("/")

    async def fetch_raw_jobs(self) -> list[dict]:
        careers = self._careers_url()
        settings = get_settings()
        timeout = httpx.Timeout(settings.scrape_timeout_seconds)

        html = await self._fetch_html(careers, timeout)
        jobs = parse_icims_listing_html(html, careers) if html else []

        if len(jobs) >= 3:
            logger.info("iCIMS HTML scrape found %s jobs for %s", len(jobs), self.company_name)
            return jobs

        logger.info(
            "iCIMS HTML found %s jobs for %s; trying Playwright fallback",
            len(jobs),
            self.company_name,
        )
        pw_jobs = await self._fetch_via_playwright(careers)
        if pw_jobs:
            return pw_jobs
        return jobs

    async def _fetch_html(self, url: str, timeout: httpx.Timeout) -> str:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            return resp.text

    async def _fetch_via_playwright(self, careers_url: str) -> list[dict]:
        settings = get_settings()
        timeout_ms = int(settings.scrape_timeout_seconds * 1000)
        wait_sel = self.source_config.get("wait_selector") or 'a[href*="/jobs/"]'

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.playwright_headless)
            try:
                page = await browser.new_page()
                await page.goto(careers_url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    await page.wait_for_selector(str(wait_sel), timeout=min(timeout_ms, 30_000))
                except Exception:
                    pass
                html = await page.content()
                return parse_icims_listing_html(html, careers_url)
            finally:
                await browser.close()

    def normalize_job(self, raw_job: dict) -> NormalizedJob:
        url = str(raw_job.get("url") or self._careers_url())
        title = str(raw_job.get("title") or "Untitled")
        ext = raw_job.get("job_id")
        if ext is None:
            parts = url.rstrip("/").split("/")
            for part in reversed(parts):
                if part.isdigit():
                    ext = part
                    break
        return NormalizedJob(
            company_name=self.company_name,
            source_type="icims",
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
