from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Company
from app.scrapers.parsing import looks_like_job_board
from app.services.company_targets_service import UNCONFIGURED_SOURCE_TYPE
from app.utils.source_urls import validation_expects_json, validation_url_for

logger = logging.getLogger(__name__)

CONSECUTIVE_404_THRESHOLD = 2
PROBE_RETRIES = 3
PROBE_RETRY_DELAY_SECONDS = 0.75


@dataclass(frozen=True)
class ValidationProbeResult:
    company_name: str
    source_type: str
    status_code: int | None
    valid: bool
    error: str = ""
    url: str | None = None


@dataclass
class ValidationRunSummary:
    valid_count: int = 0
    disabled_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    results: list[ValidationProbeResult] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_http_404(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 404
    msg = str(exc).lower()
    return "404" in msg and ("not found" in msg or "status" in msg or "client error" in msg)


def invalid_source_detail(company: Company, exc: BaseException | None = None) -> str:
    if company.source_type == "greenhouse":
        token = company.source_config.get("board_token", "?")
        return f"Greenhouse board_token {token} returned 404"
    if company.source_type == "lever":
        site = company.source_config.get("company", "?")
        return f"Lever company slug {site} returned 404"
    if company.source_type == "ashby":
        org = company.source_config.get("organization") or company.source_config.get("org") or "?"
        return f"Ashby organization {org} returned 404"
    if company.source_type == "smartrecruiters":
        slug = company.source_config.get("company", "?")
        return f"SmartRecruiters company {slug} returned 404"
    if company.source_type == "workday":
        return f"Workday careers_url returned 404"
    if company.source_type == "icims":
        return f"iCIMS careers_url returned 404"
    if company.source_type == "gem":
        return f"Gem careers_url returned 404"
    if company.source_type == "generic_playwright":
        return "Generic Playwright careers_url returned 404"
    if exc:
        return str(exc)
    return "source returned 404"


def _validate_json_probe(source_type: str, response: httpx.Response) -> tuple[bool, str]:
    """Return (valid, error_message) for JSON ATS probe responses."""
    if source_type == "smartrecruiters":
        try:
            payload = response.json()
        except Exception:
            return False, "invalid JSON from SmartRecruiters API"
        if not isinstance(payload, dict):
            return False, "invalid SmartRecruiters API response"
    return True, ""


def _probe_result(
    company: Company,
    *,
    valid: bool,
    status_code: int | None,
    error_message: str,
    url: str | None,
) -> ValidationProbeResult:
    return ValidationProbeResult(
        company_name=company.name,
        source_type=company.source_type,
        status_code=status_code,
        valid=valid,
        error=error_message,
        url=url,
    )


async def _probe_generic_playwright(company: Company) -> ValidationProbeResult:
    """Validate generic_playwright: HTTP 200 on careers_url, else brief Playwright open."""
    url = (company.careers_url or company.source_config.get("careers_url") or "").strip()
    if not url:
        return _probe_result(
            company,
            valid=False,
            status_code=None,
            error_message="missing careers_url",
            url=None,
        )

    settings = get_settings()
    timeout = httpx.Timeout(
        min(settings.scrape_timeout_seconds, settings.generic_playwright_timeout_seconds)
    )
    headers = {"User-Agent": "JobScraper/1.0", "Accept": "text/html,application/xhtml+xml"}

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
        if response.status_code == 200:
            return _probe_result(
                company,
                valid=True,
                status_code=200,
                error_message="",
                url=url,
            )
        if response.status_code in (403, 404):
            return _probe_result(
                company,
                valid=False,
                status_code=response.status_code,
                error_message=f"HTTP {response.status_code}",
                url=url,
            )
    except Exception as exc:
        logger.debug("HTTP probe failed for %s, trying Playwright: %s", company.name, exc)

    try:
        from playwright.async_api import async_playwright

        timeout_ms = int(settings.generic_playwright_timeout_seconds * 1000)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=settings.playwright_headless)
            try:
                page = await browser.new_page()
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                status = response.status if response else 200
                if status >= 400:
                    return _probe_result(
                        company,
                        valid=False,
                        status_code=status,
                        error_message=f"HTTP {status}",
                        url=url,
                    )
                return _probe_result(
                    company,
                    valid=True,
                    status_code=status,
                    error_message="",
                    url=url,
                )
            finally:
                await browser.close()
    except Exception as exc:
        return _probe_result(
            company,
            valid=False,
            status_code=None,
            error_message=str(exc),
            url=url,
        )


async def probe_company_source(
    company: Company,
    *,
    retries: int = PROBE_RETRIES,
) -> ValidationProbeResult:
    if company.source_type == "generic_playwright":
        return await _probe_generic_playwright(company)

    url = validation_url_for(company.source_type, company.source_config)
    if not url:
        return _probe_result(
            company,
            valid=False,
            status_code=None,
            error_message="validation not supported for this source_type",
            url=None,
        )

    settings = get_settings()
    timeout = httpx.Timeout(settings.scrape_timeout_seconds)
    last_error: str | None = None
    expects_json = validation_expects_json(company.source_type)
    headers = (
        {"Accept": "application/json", "User-Agent": "JobScraper/1.0"}
        if expects_json
        else {"Accept": "text/html,application/xhtml+xml", "User-Agent": "JobScraper/1.0"}
    )

    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
            status = response.status_code
            error_message = ""
            valid = False

            if status in (403, 404):
                valid = False
                error_message = f"HTTP {status}"
            elif status != 200:
                valid = False
                error_message = f"HTTP {status}"
            elif expects_json:
                valid, error_message = _validate_json_probe(company.source_type, response)
            else:
                valid = looks_like_job_board(response.text, company.source_type)
                if not valid:
                    error_message = "page does not look like a job board"

            return _probe_result(
                company,
                valid=valid,
                status_code=status,
                error_message=error_message,
                url=url,
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            error_message = f"HTTP {status}" if status else str(exc)
            return _probe_result(
                company,
                valid=status == 200,
                status_code=status,
                error_message="" if status == 200 else error_message,
                url=url,
            )
        except Exception as exc:
            last_error = str(exc)
            if attempt < retries:
                await asyncio.sleep(PROBE_RETRY_DELAY_SECONDS * attempt)
                continue
            return _probe_result(
                company,
                valid=False,
                status_code=None,
                error_message=last_error,
                url=url,
            )

    return _probe_result(
        company,
        valid=False,
        status_code=None,
        error_message=last_error or "unknown error",
        url=url,
    )


def apply_probe_to_company(
    company: Company,
    probe: ValidationProbeResult,
    *,
    disable_on_404: bool,
    re_enable_valid: bool = False,
) -> None:
    company.last_validated_at = _now()
    company.last_validation_status = str(probe.status_code) if probe.status_code is not None else "error"

    if probe.valid:
        if re_enable_valid:
            company.enabled = True
        company.consecutive_failures = 0
        company.last_error = None
        company.last_validation_status = "200"
        return

    company.last_error = probe.error or None

    if probe.status_code == 404 and disable_on_404:
        company.enabled = False
        company.consecutive_failures = max(company.consecutive_failures, CONSECUTIVE_404_THRESHOLD)
        detail = invalid_source_detail(company)
        logger.warning("Disabling %s: %s", company.name, detail)
        company.last_error = detail
        return

    if probe.status_code == 404:
        company.consecutive_failures += 1
        company.last_error = invalid_source_detail(company)
        return


def _tally_summary(
    summary: ValidationRunSummary,
    probe: ValidationProbeResult,
    *,
    disable_on_404: bool,
) -> None:
    summary.results.append(probe)
    if probe.status_code is None and "not supported" in probe.error:
        summary.skipped_count += 1
        return
    if probe.valid:
        summary.valid_count += 1
    elif probe.status_code == 404 and disable_on_404:
        summary.disabled_count += 1
    else:
        summary.failed_count += 1


async def validate_all_companies(
    session: AsyncSession,
    *,
    only_enabled: bool = True,
    disable_on_404: bool = True,
    re_enable_valid: bool = False,
) -> ValidationRunSummary:
    stmt = select(Company).order_by(Company.name)
    if only_enabled:
        stmt = stmt.where(Company.enabled.is_(True))
    res = await session.execute(stmt)
    companies = list(res.scalars().all())

    summary = ValidationRunSummary()
    for company in companies:
        if company.source_type == UNCONFIGURED_SOURCE_TYPE:
            summary.skipped_count += 1
            summary.results.append(
                ValidationProbeResult(
                    company_name=company.name,
                    source_type=company.source_type,
                    status_code=None,
                    valid=False,
                    error="unconfigured source (run discover/import first)",
                    url=None,
                )
            )
            continue

        probe = await probe_company_source(company)
        apply_probe_to_company(
            company,
            probe,
            disable_on_404=disable_on_404,
            re_enable_valid=re_enable_valid,
        )
        _tally_summary(summary, probe, disable_on_404=disable_on_404)

    await session.flush()
    return summary


def format_validation_table(results: list[ValidationProbeResult]) -> str:
    header = f"{'company':<22} {'source_type':<14} {'status_code':<12} {'valid':<6} error"
    lines = [header, "-" * len(header)]
    for r in results:
        code = str(r.status_code) if r.status_code is not None else "—"
        valid = "yes" if r.valid else "no"
        err = (r.error or "")[:60]
        lines.append(f"{r.company_name:<22} {r.source_type:<14} {code:<12} {valid:<6} {err}")
    return "\n".join(lines)


async def record_scrape_failure(
    session: AsyncSession,
    company: Company,
    exc: BaseException,
) -> str:
    """Update company failure state; return message for pipeline summary."""
    company.last_error = str(exc)

    if is_http_404(exc):
        company.consecutive_failures += 1
        detail = invalid_source_detail(company, exc)
        company.last_error = detail
        company.last_validation_status = "404"
        msg = f"{company.name}: invalid_source_config ({detail})"

        if company.consecutive_failures >= CONSECUTIVE_404_THRESHOLD:
            company.enabled = False
            logger.warning("Disabling %s: %s", company.name, detail)
        else:
            logger.warning(
                "invalid_source_config for %s (%s/%s): %s",
                company.name,
                company.consecutive_failures,
                CONSECUTIVE_404_THRESHOLD,
                detail,
            )
        await session.flush()
        return msg

    logger.exception("Scrape failed for %s", company.name)
    await session.flush()
    return f"{company.name}: {exc}"


async def record_scrape_success(session: AsyncSession, company: Company) -> None:
    company.consecutive_failures = 0
    company.last_error = None
    await session.flush()
