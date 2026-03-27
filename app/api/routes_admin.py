import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.db.session import get_db_session
from app.schemas.company import CompanyCreate, CompanyRead
from app.schemas.scrape import ScrapeTriggerResponse
from app.services.company_service import create_company, list_companies
from app.services.scrape_runner_service import run_scrape_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/companies", response_model=list[CompanyRead])
async def admin_list_companies(session: AsyncSession = Depends(get_db_session)) -> list[CompanyRead]:
    companies = await list_companies(session)
    return [CompanyRead.model_validate(c) for c in companies]


@router.post("/companies", response_model=CompanyRead)
async def admin_create_company(
    body: CompanyCreate,
    session: AsyncSession = Depends(get_db_session),
) -> CompanyRead:
    company = await create_company(session, body)
    return CompanyRead.model_validate(company)


@router.post("/run-scrape", response_model=ScrapeTriggerResponse)
async def admin_run_scrape() -> ScrapeTriggerResponse:
    try:
        summary = await run_scrape_pipeline(get_session_factory())
        return ScrapeTriggerResponse(
            success=len(summary.failures) == 0,
            message="Scrape pipeline finished",
            companies_scanned=summary.companies_scanned,
            jobs_seen=summary.jobs_seen,
            new_jobs_created=summary.new_jobs_created,
            inactive_jobs_marked=summary.inactive_jobs_marked,
            emails_sent=summary.emails_sent,
            failures=summary.failures,
        )
    except Exception as e:
        logger.exception("Manual scrape failed")
        return ScrapeTriggerResponse(
            success=False,
            message=str(e),
            failures=[str(e)],
        )
