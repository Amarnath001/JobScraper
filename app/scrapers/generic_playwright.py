import asyncio
import logging
from typing import Any
from urllib.parse import urljoin

from playwright.async_api import Page, async_playwright

from app.core.config import get_settings
from app.scrapers.base import BaseScraper
from app.scrapers.generic_playwright_heuristics import (
    COOKIE_DISMISS_SELECTORS,
    LOAD_MORE_SELECTORS,
    ExtractedJobLink,
    candidate_follow_urls,
    links_from_anchor_dicts,
    merge_job_links,
    normalize_page_url,
    same_site,
)
from app.schemas.job import NormalizedJob

logger = logging.getLogger(__name__)

EXTRACT_ANCHORS_JS = """
() => {
  const out = [];
  const seen = new Set();
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.href;
    if (!href || seen.has(href)) continue;
    seen.add(href);
    let loc = null;
    const row = a.closest('li, tr, article, [class*="job"], [class*="posting"]');
    if (row) {
      const locEl = row.querySelector('[class*="location"], [data-automation-id*="location"]');
      if (locEl) loc = (locEl.innerText || '').trim().slice(0, 120);
    }
    out.push({
      href,
      text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 300),
      location: loc,
    });
  }
  return out;
}
"""


class GenericPlaywrightScraper(BaseScraper):
    """
    Best-effort careers page scraper using Playwright heuristics.

    source_config (all optional):
      careers_url / page_url — landing page (defaults to company careers_url)
      list_selector + link_selector — legacy explicit selectors (skips heuristics)
      max_pages, max_links — override settings defaults
    """

    def _landing_url(self) -> str:
        url = self.source_config.get("careers_url") or self.source_config.get("page_url") or self.careers_url
        if not url:
            raise ValueError("generic_playwright requires careers_url")
        return str(url).strip()

    def _uses_legacy_selectors(self) -> bool:
        return bool(
            self.source_config.get("list_selector") and self.source_config.get("link_selector")
        )

    async def fetch_raw_jobs(self) -> list[dict]:
        if self._uses_legacy_selectors():
            return await self._fetch_via_legacy_selectors()
        return await self._fetch_via_heuristics()

    async def _fetch_via_heuristics(self) -> list[dict]:
        settings = get_settings()
        landing = self._landing_url()
        max_pages = int(
            self.source_config.get("max_pages")
            or settings.generic_playwright_max_pages_per_company
        )
        max_links = int(self.source_config.get("max_links") or 200)
        timeout_s = float(
            self.source_config.get("timeout_seconds")
            or settings.generic_playwright_timeout_seconds
        )
        timeout_ms = int(timeout_s * 1000)

        collected: dict[str, ExtractedJobLink] = {}
        visited_pages: set[str] = set()
        to_visit = [normalize_page_url(landing)]

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.playwright_headless)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                deadline = asyncio.get_event_loop().time() + timeout_s

                while to_visit and len(visited_pages) < max_pages:
                    if asyncio.get_event_loop().time() > deadline:
                        logger.warning(
                            "generic_playwright timeout for %s after %ss",
                            self.company_name,
                            timeout_s,
                        )
                        break
                    page_url = to_visit.pop(0)
                    if page_url in visited_pages:
                        continue
                    visited_pages.add(page_url)

                    try:
                        await self._load_page(page, page_url, timeout_ms)
                    except Exception as exc:
                        logger.debug("Skip page %s for %s: %s", page_url, self.company_name, exc)
                        continue

                    anchors = await page.evaluate(EXTRACT_ANCHORS_JS)
                    page_jobs = links_from_anchor_dicts(
                        anchors if isinstance(anchors, list) else [],
                        page_url,
                        max_links=max_links,
                    )
                    merge_job_links(collected, page_jobs, max_links=max_links)

                    if len(visited_pages) < max_pages and len(collected) < max_links:
                        hrefs = [
                            str(a.get("href"))
                            for a in (anchors if isinstance(anchors, list) else [])
                            if a.get("href")
                        ]
                        for follow in candidate_follow_urls(landing, page_url, hrefs):
                            if follow not in visited_pages and follow not in to_visit:
                                to_visit.append(follow)

                return [
                    {
                        "title": job.title,
                        "url": job.url,
                        "location": job.location,
                        "_source_page": landing,
                    }
                    for job in collected.values()
                ]
            finally:
                await browser.close()

    async def _load_page(self, page: Page, page_url: str, timeout_ms: int) -> None:
        await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 15_000))
        except Exception:
            pass
        await self._dismiss_cookies(page)
        await self._scroll_page(page)
        await self._click_load_more(page)

    async def _dismiss_cookies(self, page: Page) -> None:
        for selector in COOKIE_DISMISS_SELECTORS:
            try:
                btn = await page.query_selector(selector)
                if btn and await btn.is_visible():
                    await btn.click(timeout=2000)
                    await page.wait_for_timeout(400)
                    return
            except Exception:
                continue

    async def _scroll_page(self, page: Page) -> None:
        for _ in range(3):
            try:
                await page.evaluate("window.scrollBy(0, Math.min(window.innerHeight * 2, 1200))")
                await page.wait_for_timeout(500)
            except Exception:
                break

    async def _click_load_more(self, page: Page) -> None:
        settings = get_settings()
        max_rounds = int(self.source_config.get("max_load_more_rounds", 3))
        for _ in range(max_rounds):
            clicked = False
            for selector in LOAD_MORE_SELECTORS:
                try:
                    btn = await page.query_selector(selector)
                    if not btn or not await btn.is_visible():
                        continue
                    label = (await btn.inner_text()).lower()
                    if "apply" in label and "more" not in label:
                        continue
                    await btn.click(timeout=2000)
                    await page.wait_for_timeout(800)
                    clicked = True
                    break
                except Exception:
                    continue
            if not clicked:
                break

    async def _fetch_via_legacy_selectors(self) -> list[dict]:
        page_url = self._landing_url()
        list_sel = str(self.source_config["list_selector"])
        link_sel = str(self.source_config["link_selector"])
        settings = get_settings()
        timeout_ms = int(settings.generic_playwright_timeout_seconds * 1000)
        wait_sel = self.source_config.get("wait_selector")
        load_more = self.source_config.get("load_more_selector")
        max_rounds = int(self.source_config.get("max_load_more_rounds", 5))

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.playwright_headless)
            try:
                page = await browser.new_page()
                await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
                if wait_sel:
                    try:
                        await page.wait_for_selector(str(wait_sel), timeout=timeout_ms)
                    except Exception as exc:
                        logger.warning("wait_selector failed for %s: %s", page_url, exc)
                if load_more:
                    for _ in range(max_rounds):
                        btn = await page.query_selector(str(load_more))
                        if not btn:
                            break
                        try:
                            await btn.click()
                            await page.wait_for_timeout(800)
                        except Exception as exc:
                            logger.warning("load_more click failed: %s", exc)
                            break

                items = await page.query_selector_all(list_sel)
                raw_jobs: list[dict] = []
                for el in items:
                    link = await el.query_selector(link_sel)
                    href = await link.get_attribute("href") if link else None
                    if not href:
                        continue
                    abs_url = urljoin(page_url, href)
                    if not same_site(page_url, abs_url):
                        continue
                    title_txt = None
                    if ts := self.source_config.get("title_selector"):
                        t_el = await el.query_selector(str(ts))
                        if t_el:
                            title_txt = (await t_el.inner_text()).strip()
                    if not title_txt and link:
                        title_txt = (await link.inner_text()).strip()
                    loc_txt = None
                    if ls := self.source_config.get("location_selector"):
                        l_el = await el.query_selector(str(ls))
                        if l_el:
                            loc_txt = (await l_el.inner_text()).strip()
                    raw_jobs.append(
                        {
                            "title": title_txt or "Untitled",
                            "url": abs_url,
                            "location": loc_txt,
                        }
                    )
                return raw_jobs
            finally:
                await browser.close()

    def normalize_job(self, raw_job: dict) -> NormalizedJob:
        return NormalizedJob(
            company_name=self.company_name,
            source_type="generic_playwright",
            external_job_id=raw_job.get("external_job_id"),
            title=str(raw_job.get("title") or "Untitled"),
            team=None,
            location=raw_job.get("location"),
            employment_type=None,
            level=None,
            url=str(raw_job.get("url") or self._landing_url()),
            description_text=raw_job.get("description_text"),
            posted_at=raw_job.get("posted_at"),
            raw_payload=dict(raw_job),
        )
