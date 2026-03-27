import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from playwright.async_api import async_playwright

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


def _flatten_jobs_payload(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("jobPostings", "jobs", "data", "results"):
        v = data.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    return []


class WorkdayScraper(BaseScraper):
    """
    Workday sources vary. Configure either:
    - `json_url` (+ optional `json_method`, `json_headers`, `json_body`) for direct API
    - or Playwright with `page_url` (defaults to careers_url) and selectors:
        `list_selector`, `item_link_selector`, optional `title_selector`, `location_selector`
    """

    async def fetch_raw_jobs(self) -> list[dict]:
        settings = get_settings()
        timeout = httpx.Timeout(settings.scrape_timeout_seconds)

        if self.source_config.get("json_url"):
            return await self._fetch_via_http(timeout)

        return await self._fetch_via_playwright()

    async def _fetch_via_http(self, timeout: httpx.Timeout) -> list[dict]:
        url = str(self.source_config["json_url"])
        method = str(self.source_config.get("json_method", "GET")).upper()
        headers: dict[str, str] = {"Accept": "application/json"}
        extra = self.source_config.get("json_headers")
        if isinstance(extra, dict):
            headers.update({str(k): str(v) for k, v in extra.items()})
        body = self.source_config.get("json_body")
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if method == "POST":
                if isinstance(body, dict):
                    resp = await client.post(url, headers=headers, json=body)
                elif isinstance(body, str):
                    resp = await client.post(url, headers=headers, content=body.encode("utf-8"))
                else:
                    resp = await client.post(url, headers=headers)
            else:
                resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        raw_list = _flatten_jobs_payload(data)
        out: list[dict] = []
        for item in raw_list:
            item = dict(item)
            item["_workday_source"] = "json"
            out.append(item)
        return out

    async def _fetch_via_playwright(self) -> list[dict]:
        page_url = str(self.source_config.get("page_url") or self.careers_url)
        list_sel = self.source_config.get("list_selector")
        link_sel = self.source_config.get("item_link_selector") or self.source_config.get("link_selector")
        if not list_sel or not link_sel:
            raise ValueError(
                "Workday Playwright mode requires source_config list_selector and item_link_selector (or link_selector)"
            )
        settings = get_settings()
        timeout_ms = int(settings.scrape_timeout_seconds * 1000)
        wait_sel = self.source_config.get("wait_selector")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.playwright_headless)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
                if wait_sel:
                    await page.wait_for_selector(str(wait_sel), timeout=timeout_ms)
                items = await page.query_selector_all(str(list_sel))
                raw_jobs: list[dict] = []
                for el in items:
                    link = await el.query_selector(str(link_sel))
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
                        abs_url = urljoin(page_url, href)
                        raw_jobs.append(
                            {
                                "_workday_source": "playwright",
                                "title": (title_txt or "Untitled").strip(),
                                "url": abs_url,
                                "location": loc_txt.strip() if loc_txt else None,
                            }
                        )
                return raw_jobs
            finally:
                await browser.close()

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
                url=str(raw_job.get("url") or self.careers_url),
                description_text=None,
                posted_at=None,
                raw_payload=raw_job,
            )

        title = (
            raw_job.get("title")
            or raw_job.get("name")
            or raw_job.get("jobPostingTitle")
            or "Untitled"
        )
        title = str(title)
        ext = raw_job.get("bulletFields") or raw_job.get("jobPostingId") or raw_job.get("id")
        ext_id = str(ext) if ext is not None else None

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

        path = raw_job.get("externalPath") or raw_job.get("jobPostingUrl") or raw_job.get("url")
        url = self.careers_url
        if path:
            if str(path).startswith("http"):
                url = str(path)
            else:
                base = f"{urlparse(self.careers_url).scheme}://{urlparse(self.careers_url).netloc}"
                url = urljoin(base + "/", str(path).lstrip("/"))

        posted = _parse_ts(raw_job.get("postedOn") or raw_job.get("startDate"))

        desc = raw_job.get("jobDescription")
        if desc is None:
            desc = raw_job.get("description")
        if desc is not None:
            if isinstance(desc, dict):
                desc = json.dumps(desc)[:50000]
            else:
                desc = str(desc)[:50000]

        return NormalizedJob(
            company_name=self.company_name,
            source_type="workday",
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
