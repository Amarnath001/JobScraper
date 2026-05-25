import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.db.session import get_db_session
from app.schemas.company import CompanyCreate, CompanyRead, CompanyValidationResponse, CompanyValidationRow
from app.schemas.scrape import ScrapeTriggerResponse, TestEmailResponse
from app.services.company_service import create_company, list_companies
from app.services.company_validation_service import validate_all_companies
from app.services.email_service import EmailService
from app.services.scrape_runner_service import PipelineSummary, _pipeline_message, run_scrape_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/companies", response_model=list[CompanyRead])
async def admin_list_companies(
    session: AsyncSession = Depends(get_db_session),
    enabled: bool | None = Query(default=None, description="Filter by enabled flag"),
) -> list[CompanyRead]:
    companies = await list_companies(session, enabled=enabled)
    return [CompanyRead.model_validate(c) for c in companies]


@router.post("/companies", response_model=CompanyRead)
async def admin_create_company(
    body: CompanyCreate,
    session: AsyncSession = Depends(get_db_session),
) -> CompanyRead:
    company = await create_company(session, body)
    return CompanyRead.model_validate(company)


@router.post("/companies/validate", response_model=CompanyValidationResponse)
async def admin_validate_companies(
    session: AsyncSession = Depends(get_db_session),
) -> CompanyValidationResponse:
    summary = await validate_all_companies(session, disable_on_404=True)
    rows = [
        CompanyValidationRow(
            company=r.company_name,
            source_type=r.source_type,
            status_code=r.status_code,
            valid=r.valid,
            error=r.error,
        )
        for r in summary.results
    ]
    return CompanyValidationResponse(
        valid_count=summary.valid_count,
        disabled_count=summary.disabled_count,
        failed_count=summary.failed_count,
        skipped_count=summary.skipped_count,
        results=rows,
    )


def _summary_to_response(summary: PipelineSummary) -> ScrapeTriggerResponse:
    return ScrapeTriggerResponse(
        success=True,
        message=_pipeline_message(summary),
        companies_scanned=summary.companies_scanned,
        jobs_seen=summary.jobs_seen,
        new_jobs_created=summary.new_jobs_created,
        inactive_jobs_marked=summary.inactive_jobs_marked,
        emails_attempted=summary.emails_attempted,
        emails_sent=summary.emails_sent,
        scraper_failures=summary.scraper_failures,
        email_failures=summary.email_failures,
    )


@router.post("/run-scrape", response_model=ScrapeTriggerResponse)
async def admin_run_scrape() -> ScrapeTriggerResponse:
    try:
        summary = await run_scrape_pipeline(get_session_factory())
        return _summary_to_response(summary)
    except Exception as e:
        logger.exception("Manual scrape failed")
        return ScrapeTriggerResponse(
            success=False,
            message=f"Scrape pipeline failed: {e}",
            scraper_failures=[],
            email_failures=[str(e)],
        )


@router.post("/send-test-email", response_model=TestEmailResponse)
async def admin_send_test_email() -> TestEmailResponse:
    email_svc = EmailService()
    result = email_svc.send_test_email()
    if result.ok:
        return TestEmailResponse(
            success=True,
            message="Test email accepted by provider",
            provider_id=result.provider_id,
        )
    return TestEmailResponse(
        success=False,
        message="Test email was not accepted by provider",
        error=result.error,
    )
