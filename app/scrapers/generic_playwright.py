import logging
from urllib.parse import urljoin

from playwright.async_api import async_playwright

from app.core.config import get_settings
from app.scrapers.base import BaseScraper
from app.schemas.job import NormalizedJob

logger = logging.getLogger(__name__)


class GenericPlaywrightScraper(BaseScraper):
    """
    Generic careers page scraping via configurable selectors.

    source_config keys:
    - page_url (optional, defaults to careers_url)
    - wait_selector (optional)
    - list_selector — required: selector for each job row/card
    - link_selector — required: relative selector within item for <a href>
    - title_selector (optional)
    - location_selector (optional)
    - load_more_selector (optional): click until gone or max_rounds
    - max_load_more_rounds (optional, default 5)
    """

    async def fetch_raw_jobs(self) -> list[dict]:
        page_url = str(self.source_config.get("page_url") or self.careers_url)
        list_sel = self.source_config.get("list_selector")
        link_sel = self.source_config.get("link_selector")
        if not list_sel or not link_sel:
            raise ValueError("generic_playwright requires list_selector and link_selector in source_config")

        settings = get_settings()
        timeout_ms = int(settings.scrape_timeout_seconds * 1000)
        wait_sel = self.source_config.get("wait_selector")
        load_more = self.source_config.get("load_more_selector")
        max_rounds = int(self.source_config.get("max_load_more_rounds", 5))

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=settings.playwright_headless)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
                if wait_sel:
                    try:
                        await page.wait_for_selector(str(wait_sel), timeout=timeout_ms)
                    except Exception as e:
                        logger.warning("wait_selector failed for %s: %s", page_url, e)

                if load_more:
                    for _ in range(max_rounds):
                        btn = await page.query_selector(str(load_more))
                        if not btn:
                            break
                        try:
                            await btn.click()
                            await page.wait_for_timeout(800)
                        except Exception as e:
                            logger.warning("load_more click failed: %s", e)
                            break

                items = await page.query_selector_all(str(list_sel))
                raw_jobs: list[dict] = []
                for el in items:
                    link = await el.query_selector(str(link_sel))
                    href = await link.get_attribute("href") if link else None
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
                    if href:
                        abs_url = urljoin(page_url, href)
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
