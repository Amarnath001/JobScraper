import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from playwright.async_api import async_playwright

from app.core.config import get_settings
from app.scrapers.base import BaseScraper
from app.scrapers.parsing import (
    parse_timestamp,
    parse_workday_careers_url,
    parse_workday_cxs_response,
    parse_workday_playwright_jobs,
    workday_cxs_api_url,
)
from app.schemas.job import NormalizedJob

logger = logging.getLogger(__name__)

WORKDAY_JOB_LINK_SELECTORS = [
    'a[data-automation-id="jobTitle"]',
    'li[data-automation-id="jobTitle"] a',
    '[data-automation-id="jobTitle"]',
    'a[href*="/job/"]',
]


class WorkdayScraper(BaseScraper):
    """
    Workday careers scraper.

    source_config:
      careers_url (required) — myworkdayjobs.com board URL
      page_url (optional) — override page for Playwright
      list_selector / item_link_selector (optional) — custom Playwright selectors
      json_url (optional) — direct JSON endpoint override
    """

    def _careers_url(self) -> str:
        url = (
            self.source_config.get("careers_url")
            or self.source_config.get("page_url")
            or self.careers_url
        )
        if not url:
            raise ValueError("Workday source_config requires careers_url")
        return str(url).rstrip("/")

    async def fetch_raw_jobs(self) -> list[dict]:
        settings = get_settings()
        timeout = httpx.Timeout(settings.scrape_timeout_seconds)
        careers = self._careers_url()

        if self.source_config.get("json_url"):
            return await self._fetch_json_override(timeout)

        cxs_jobs = await self._fetch_via_cxs_api(careers, timeout)
        if cxs_jobs:
            return cxs_jobs

        try:
            return await self._fetch_via_playwright(careers)
        except Exception as exc:
            logger.warning("Workday Playwright scrape failed for %s: %s", self.company_name, exc)
            if self._debug_enabled():
                await self._debug_capture(careers, exc)
            return []

    async def _fetch_json_override(self, timeout: httpx.Timeout) -> list[dict]:
        url = str(self.source_config["json_url"])
        method = str(self.source_config.get("json_method", "GET")).upper()
        headers: dict[str, str] = {"Accept": "application/json"}
        extra = self.source_config.get("json_headers")
        if isinstance(extra, dict):
            headers.update({str(k): str(v) for k, v in extra.items()})
        body = self.source_config.get("json_body")
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if method == "POST":
                resp = await client.post(
                    url,
                    headers=headers,
                    json=body if isinstance(body, dict) else None,
                )
            else:
                resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        parsed = urlparse(self._careers_url())
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return parse_workday_cxs_response(data, origin=origin)

    async def _fetch_via_cxs_api(self, careers_url: str, timeout: httpx.Timeout) -> list[dict]:
        parts = parse_workday_careers_url(careers_url)
        if not parts:
            return []
        origin, tenant, site = parts
        api_url = workday_cxs_api_url(origin, tenant, site)
        payload = {"appliedFacets": {}, "limit": 50, "offset": 0, "searchText": ""}
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.post(api_url, json=payload, headers=headers)
                if resp.status_code >= 400:
                    logger.debug("Workday CXS API %s returned %s", api_url, resp.status_code)
                    return []
                data = resp.json()
            jobs = parse_workday_cxs_response(data, origin=origin)
            if jobs:
                logger.info(
                    "Workday CXS API returned %s jobs for %s",
                    len(jobs),
                    self.company_name,
                )
            return jobs
        except Exception as exc:
            logger.debug("Workday CXS API failed for %s: %s", self.company_name, exc)
            return []

    async def _fetch_via_playwright(self, careers_url: str) -> list[dict]:
        page_url = str(self.source_config.get("page_url") or careers_url)
        list_sel = self.source_config.get("list_selector")
        link_sel = self.source_config.get("item_link_selector") or self.source_config.get(
            "link_selector"
        )

        settings = get_settings()
        timeout_ms = int(settings.scrape_timeout_seconds * 1000)
        wait_sel = self.source_config.get("wait_selector") or '[data-automation-id="jobTitle"]'

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.playwright_headless)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    await page.wait_for_selector(str(wait_sel), timeout=min(timeout_ms, 30_000))
                except Exception:
                    logger.debug("Workday wait_selector not found for %s", self.company_name)

                await self._try_load_more(page, timeout_ms)

                if list_sel and link_sel:
                    return await self._extract_configured_selectors(
                        page, page_url, str(list_sel), str(link_sel)
                    )

                return await self._extract_heuristic_jobs(page, page_url)
            finally:
                await browser.close()

    async def _try_load_more(self, page: Any, timeout_ms: int) -> None:
        load_more = self.source_config.get("load_more_selector") or (
            'button[data-automation-id="loadMoreJobs"]'
        )
        max_rounds = int(self.source_config.get("max_load_more_rounds", 3))
        for _ in range(max_rounds):
            try:
                btn = await page.query_selector(str(load_more))
                if not btn or not await btn.is_visible():
                    break
                await btn.click()
                await page.wait_for_timeout(1500)
            except Exception:
                break

    async def _extract_configured_selectors(
        self,
        page: Any,
        page_url: str,
        list_sel: str,
        link_sel: str,
    ) -> list[dict]:
        items = await page.query_selector_all(list_sel)
        rows: list[dict[str, str | None]] = []
        for el in items:
            link = await el.query_selector(link_sel)
            href = await link.get_attribute("href") if link else None
            title_el = None
            if ts := self.source_config.get("title_selector"):
                title_el = await el.query_selector(str(ts))
            loc_el = None
            if ls := self.source_config.get("location_selector"):
                loc_el = await el.query_selector(str(ls))
            title_txt = await title_el.inner_text() if title_el else None
            if not title_txt and link:
                title_txt = (await link.inner_text()).strip()
            loc_txt = (await loc_el.inner_text()) if loc_el else None
            if href:
                rows.append(
                    {
                        "url": href,
                        "title": title_txt,
                        "location": loc_txt.strip() if loc_txt else None,
                    }
                )
        return parse_workday_playwright_jobs(rows, page_url=page_url)

    async def _extract_heuristic_jobs(self, page: Any, page_url: str) -> list[dict]:
        rows: list[dict[str, str | None]] = []
        seen: set[str] = set()

        for selector in WORKDAY_JOB_LINK_SELECTORS:
            links = await page.query_selector_all(selector)
            for link in links:
                href = await link.get_attribute("href")
                if not href or "/job/" not in href:
                    continue
                abs_url = urljoin(page_url, href)
                if abs_url in seen:
                    continue
                seen.add(abs_url)
                try:
                    title = (await link.inner_text()).strip()
                except Exception:
                    title = "Untitled"
                rows.append({"url": abs_url, "title": title or "Untitled", "location": None})
            if rows:
                break

        if not rows:
            logger.warning(
                "Workday: no job links found via Playwright for %s (%s)",
                self.company_name,
                page_url,
            )
        return parse_workday_playwright_jobs(rows, page_url=page_url)

    def _debug_enabled(self) -> bool:
        return bool(
            self.source_config.get("debug")
            or os.environ.get("SCRAPE_DEBUG", "").lower() in ("1", "true", "yes")
        )

    async def _debug_capture(self, page_url: str, exc: Exception) -> None:
        debug_dir = Path(os.environ.get("SCRAPE_DEBUG_DIR", "/tmp/jobscraper-debug"))
        debug_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() else "_" for c in self.company_name)[:40]
        logger.error(
            "Workday debug for %s at %s (error=%s); set SCRAPE_DEBUG_DIR to capture screenshots",
            self.company_name,
            page_url,
            exc,
        )
        try:
            settings = get_settings()
            timeout_ms = int(settings.scrape_timeout_seconds * 1000)
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=settings.playwright_headless)
                page = await browser.new_page()
                await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
                shot = debug_dir / f"workday_{safe_name}.png"
                await page.screenshot(path=str(shot), full_page=True)
                await browser.close()
                logger.info("Workday debug screenshot saved: %s", shot)
        except Exception as cap_exc:
            logger.debug("Workday debug capture failed: %s", cap_exc)

    def normalize_job(self, raw_job: dict) -> NormalizedJob:
        if raw_job.get("_workday_source") == "playwright":
            return NormalizedJob(
                company_name=self.company_name,
                source_type="workday",
                external_job_id=None,
                title=str(raw_job.get("title") or "Untitled"),
                team=None,
                location=raw_job.get("location"),
                employment_type=None,
                level=None,
                url=str(raw_job.get("url") or self._careers_url()),
                description_text=None,
                posted_at=parse_timestamp(raw_job.get("postedOn")),
                raw_payload=raw_job,
            )

        title = (
            raw_job.get("title")
            or raw_job.get("name")
            or raw_job.get("jobPostingTitle")
            or "Untitled"
        )
        ext = raw_job.get("bulletFields") or raw_job.get("jobPostingId") or raw_job.get("id")
        ext_id = str(ext[0]) if isinstance(ext, list) and ext else (str(ext) if ext is not None else None)

        loc_parts: list[str] = []
        loc = raw_job.get("locationsText") or raw_job.get("location")
        if isinstance(loc, str):
            loc_parts.append(loc)
        elif isinstance(loc, list):
            for x in loc:
                if isinstance(x, str):
                    loc_parts.append(x)
                elif isinstance(x, dict):
                    nm = x.get("descriptor") or x.get("name")
                    if nm:
                        loc_parts.append(str(nm))
        location = ", ".join(loc_parts) if loc_parts else None

        url = str(raw_job.get("url") or self._careers_url())
        if not raw_job.get("url"):
            path = raw_job.get("externalPath") or raw_job.get("jobPostingUrl")
            if path:
                if str(path).startswith("http"):
                    url = str(path)
                else:
                    base = urlparse(self._careers_url())
                    url = urljoin(f"{base.scheme}://{base.netloc}/", str(path).lstrip("/"))

        posted = parse_timestamp(raw_job.get("postedOn") or raw_job.get("startDate"))
        desc = raw_job.get("jobDescription") or raw_job.get("description")
        if desc is not None:
            desc = str(desc)[:50000]

        return NormalizedJob(
            company_name=self.company_name,
            source_type="workday",
            external_job_id=ext_id,
            title=str(title),
            team=None,
            location=location,
            employment_type=None,
            level=None,
            url=url,
            description_text=desc if isinstance(desc, str) else None,
            posted_at=posted,
            raw_payload=raw_job,
        )
