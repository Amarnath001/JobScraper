import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.db.models import Company
from app.scrapers.ashby import AshbyScraper
from app.scrapers.base import BaseScraper
from app.scrapers.generic_playwright import GenericPlaywrightScraper
from app.scrapers.greenhouse import GreenhouseScraper
from app.scrapers.lever import LeverScraper
from app.scrapers.workday import WorkdayScraper
from app.services.digest_service import DigestService
from app.services.email_service import EmailService
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
    emails_sent: int = 0
    failures: list[str] = field(default_factory=list)


async def run_scrape_pipeline(session_factory: async_sessionmaker[AsyncSession]) -> PipelineSummary:
    summary = PipelineSummary()
    settings = get_settings()
    async with session_factory() as session:
        res = await session.execute(select(Company).where(Company.enabled.is_(True)).order_by(Company.id))
        companies = list(res.scalars().all())

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
            msg = f"{company.name}: {e}"
            logger.exception("Scrape failed for %s", company.name)
            summary.failures.append(msg)

    digest_date = today_in_timezone(settings.timezone)
    async with session_factory() as session:
        digest_svc = DigestService(session)
        jobs = await digest_svc.get_todays_new_entry_level_jobs()
        subject, html, text = DigestService.build_digest_bodies(jobs, digest_date)

    to_email = settings.email_to.strip()
    if not to_email:
        logger.warning("EMAIL_TO not set; skipping digest email")
        return summary

    email_svc = EmailService()
    try:
        if jobs:
            email_svc.send_daily_digest(to_email=to_email, subject=subject, html=html, text=text)
            summary.emails_sent = 1
        elif settings.send_empty_digest:
            email_svc.send_no_jobs_email(to_email=to_email)
            summary.emails_sent = 1
        else:
            logger.info("No new entry-level jobs today; skipping email (SEND_EMPTY_DIGEST=false)")
    except Exception as e:
        summary.failures.append(f"email: {e}")
        logger.exception("Digest email failed")

    logger.info(
        "Pipeline complete: scanned=%s jobs_seen=%s new_jobs=%s inactive=%s emails=%s failures=%s",
        summary.companies_scanned,
        summary.jobs_seen,
        summary.new_jobs_created,
        summary.inactive_jobs_marked,
        summary.emails_sent,
        len(summary.failures),
    )
    return summary
