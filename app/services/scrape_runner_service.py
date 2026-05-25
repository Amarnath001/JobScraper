import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.email_validation import validate_email_config
from app.db.models import Company
from app.scrapers.ashby import AshbyScraper
from app.scrapers.base import BaseScraper
from app.scrapers.generic_playwright import GenericPlaywrightScraper
from app.scrapers.greenhouse import GreenhouseScraper
from app.scrapers.lever import LeverScraper
from app.scrapers.workday import WorkdayScraper
from app.services.digest_service import DigestService
from app.services.email_service import EmailService
from app.services.company_validation_service import is_http_404, record_scrape_failure, record_scrape_success
from app.services.ingest_service import ingest_jobs_for_company
from app.utils.dates import today_in_timezone

logger = logging.getLogger(__name__)


def build_scraper(company: Company) -> BaseScraper:
    mapping: dict[str, type[BaseScraper]] = {
        "greenhouse": GreenhouseScraper,
        "lever": LeverScraper,
        "ashby": AshbyScraper,
        "workday": WorkdayScraper,
        "generic_playwright": GenericPlaywrightScraper,
    }
    cls = mapping.get(company.source_type)
    if cls is None:
        raise ValueError(f"Unknown source_type: {company.source_type}")
    return cls(company.name, company.careers_url, company.source_config)


@dataclass
class PipelineSummary:
    companies_scanned: int = 0
    jobs_seen: int = 0
    new_jobs_created: int = 0
    inactive_jobs_marked: int = 0
    emails_attempted: int = 0
    emails_sent: int = 0
    scraper_failures: list[str] = field(default_factory=list)
    email_failures: list[str] = field(default_factory=list)
    digest_jobs_count: int = 0
    digest_window: str = ""


def _pipeline_message(summary: PipelineSummary) -> str:
    if summary.scraper_failures or summary.email_failures:
        return "Scrape pipeline completed with partial failures"
    return "Scrape pipeline completed"


async def run_scrape_only(session_factory: async_sessionmaker[AsyncSession]) -> PipelineSummary:
    """Scrape and ingest all enabled companies; no email."""
    return await run_scrape_pipeline(session_factory, send_digest=False)


async def run_daily_digest_only(session_factory: async_sessionmaker[AsyncSession]) -> PipelineSummary:
    """Send the daily entry-level digest email; no scraping."""
    summary = PipelineSummary()
    settings = get_settings()
    digest_date = today_in_timezone(settings.timezone)

    lookback_hours = settings.digest_lookback_hours
    async with session_factory() as session:
        digest_svc = DigestService(session)
        if lookback_hours:
            jobs = await digest_svc.get_entry_level_jobs_first_seen_within_hours(lookback_hours)
            summary.digest_window = f"last {lookback_hours} hours (UTC)"
        else:
            jobs = await digest_svc.get_todays_new_entry_level_jobs()
            summary.digest_window = f"today in {settings.timezone}"
        summary.digest_jobs_count = len(jobs)
        subject, html, text = DigestService.build_digest_bodies(jobs, digest_date)
        logger.info(
            "Digest query: window=%s entry_level_jobs=%s",
            summary.digest_window,
            summary.digest_jobs_count,
        )

    config_issues = validate_email_config()
    if config_issues:
        for issue in config_issues:
            summary.email_failures.append(issue)
        logger.warning(
            "Skipping digest send due to email config: %s",
            "; ".join(config_issues),
        )
        return summary

    to_email = settings.email_to.strip()
    email_svc = EmailService()
    should_send = bool(jobs) or settings.send_empty_digest

    if not should_send:
        logger.info(
            "No digest email attempted: jobs=%s SEND_EMPTY_DIGEST=%s",
            len(jobs),
            settings.send_empty_digest,
        )
        return summary

    summary.emails_attempted = 1
    if jobs:
        sent = email_svc.send_daily_digest(
            to_email=to_email,
            subject=subject,
            html=html,
            text=text,
            job_count=len(jobs),
        )
    else:
        sent = email_svc.send_no_jobs_email(to_email=to_email)

    if sent:
        summary.emails_sent = 1
    else:
        err = email_svc.last_error or "Email send returned False (see logs)"
        summary.email_failures.append(err)

    logger.info(
        "Digest send complete: jobs=%s emails_attempted=%s emails_sent=%s email_failures=%s",
        len(jobs),
        summary.emails_attempted,
        summary.emails_sent,
        len(summary.email_failures),
    )
    return summary


async def _scrape_enabled_companies(
    session_factory: async_sessionmaker[AsyncSession],
    summary: PipelineSummary,
) -> None:
    async with session_factory() as session:
        res = await session.execute(select(Company).where(Company.enabled.is_(True)).order_by(Company.id))
        companies = list(res.scalars().all())

    logger.info("Scrape cycle: enabled_companies=%s", len(companies))

    for company in companies:
        try:
            scraper = build_scraper(company)
            normalized = await scraper.scrape()
            async with session_factory() as session:
                ingest = await ingest_jobs_for_company(
                    session,
                    company_id=company.id,
                    company_name=company.name,
                    normalized_jobs=normalized,
                )
                db_company = await session.get(Company, company.id)
                if db_company:
                    await record_scrape_success(session, db_company)
                await session.commit()
            summary.companies_scanned += 1
            summary.jobs_seen += ingest.jobs_seen
            summary.new_jobs_created += ingest.new_jobs_created
            summary.inactive_jobs_marked += ingest.inactive_jobs_marked
            logger.info(
                "Scraped company=%s jobs_seen=%s new=%s inactive=%s",
                company.name,
                ingest.jobs_seen,
                ingest.new_jobs_created,
                ingest.inactive_jobs_marked,
            )
        except Exception as e:
            async with session_factory() as session:
                db_company = await session.get(Company, company.id)
                if db_company:
                    msg = await record_scrape_failure(session, db_company, e)
                    await session.commit()
                else:
                    msg = f"{company.name}: {e}"
                    if not is_http_404(e):
                        logger.exception("Scrape failed for %s", company.name)
            summary.scraper_failures.append(msg)


async def _send_digest_email(
    session_factory: async_sessionmaker[AsyncSession],
    summary: PipelineSummary,
) -> None:
    digest_summary = await run_daily_digest_only(session_factory)
    summary.digest_jobs_count = digest_summary.digest_jobs_count
    summary.digest_window = digest_summary.digest_window
    summary.emails_attempted = digest_summary.emails_attempted
    summary.emails_sent = digest_summary.emails_sent
    summary.email_failures.extend(digest_summary.email_failures)


async def run_scrape_pipeline(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    send_digest: bool = True,
) -> PipelineSummary:
    summary = PipelineSummary()
    await _scrape_enabled_companies(session_factory, summary)
    if send_digest:
        await _send_digest_email(session_factory, summary)

    logger.info(
        "Pipeline complete: scanned=%s jobs_seen=%s new_jobs=%s inactive=%s "
        "emails_attempted=%s emails_sent=%s scraper_failures=%s email_failures=%s",
        summary.companies_scanned,
        summary.jobs_seen,
        summary.new_jobs_created,
        summary.inactive_jobs_marked,
        summary.emails_attempted,
        summary.emails_sent,
        len(summary.scraper_failures),
        len(summary.email_failures),
    )
    return summary
