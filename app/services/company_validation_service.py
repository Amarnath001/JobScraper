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
from app.utils.source_urls import validation_url_for

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
    error: str | None = None
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
    if exc:
        return str(exc)
    return "source returned 404"


async def probe_company_source(
    company: Company,
    *,
    retries: int = PROBE_RETRIES,
) -> ValidationProbeResult:
    url = validation_url_for(company.source_type, company.source_config)
    if not url:
        return ValidationProbeResult(
            company_name=company.name,
            source_type=company.source_type,
            status_code=None,
            valid=False,
            error="validation not supported for this source_type",
            url=None,
        )

    settings = get_settings()
    timeout = httpx.Timeout(settings.scrape_timeout_seconds)
    last_error: str | None = None

    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(url, headers={"Accept": "application/json"})
            status = response.status_code
            valid = status == 200
            err = None if valid else f"HTTP {status}"
            return ValidationProbeResult(
                company_name=company.name,
                source_type=company.source_type,
                status_code=status,
                valid=valid,
                error=err,
                url=url,
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            return ValidationProbeResult(
                company_name=company.name,
                source_type=company.source_type,
                status_code=status,
                valid=status == 200,
                error=str(exc),
                url=url,
            )
        except Exception as exc:
            last_error = str(exc)
            if attempt < retries:
                await asyncio.sleep(PROBE_RETRY_DELAY_SECONDS * attempt)
                continue
            return ValidationProbeResult(
                company_name=company.name,
                source_type=company.source_type,
                status_code=None,
                valid=False,
                error=last_error,
                url=url,
            )

    return ValidationProbeResult(
        company_name=company.name,
        source_type=company.source_type,
        status_code=None,
        valid=False,
        error=last_error or "unknown error",
        url=url,
    )


def apply_probe_to_company(
    company: Company,
    probe: ValidationProbeResult,
    *,
    disable_on_404: bool,
) -> None:
    company.last_validated_at = _now()
    company.last_validation_status = str(probe.status_code) if probe.status_code is not None else "error"

    if probe.valid:
        company.enabled = True
        company.consecutive_failures = 0
        company.last_error = None
        company.last_validation_status = "200"
        return

    company.last_error = probe.error

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
    if probe.error and probe.status_code is None and "not supported" in (probe.error or ""):
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
    only_enabled: bool = False,
    disable_on_404: bool = True,
) -> ValidationRunSummary:
    stmt = select(Company).order_by(Company.name)
    if only_enabled:
        stmt = stmt.where(Company.enabled.is_(True))
    res = await session.execute(stmt)
    companies = list(res.scalars().all())

    summary = ValidationRunSummary()
    for company in companies:
        probe = await probe_company_source(company)
        apply_probe_to_company(company, probe, disable_on_404=disable_on_404)
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
