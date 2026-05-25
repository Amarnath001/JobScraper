"""Human-readable summaries for GitHub Actions logs."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from app.services.scrape_runner_service import PipelineSummary

logger = logging.getLogger(__name__)


def log_scrape_summary(summary: PipelineSummary) -> None:
    payload: dict[str, Any] = {
        "companies_scanned": summary.companies_scanned,
        "jobs_seen": summary.jobs_seen,
        "new_jobs_created": summary.new_jobs_created,
        "inactive_jobs_marked": summary.inactive_jobs_marked,
        "scraper_failures": summary.scraper_failures,
        "scraper_failure_count": len(summary.scraper_failures),
    }
    logger.info("=== SCRAPE CYCLE SUMMARY ===")
    for key, value in payload.items():
        logger.info("%s=%s", key, value)
    print(json.dumps(payload, indent=2))
    if summary.scraper_failures:
        logger.warning(
            "Scrape completed with %s company failure(s); see logs above for details.",
            len(summary.scraper_failures),
        )
        for msg in summary.scraper_failures:
            print(f"SCRAPER_FAILURE: {msg}", file=sys.stderr)


def log_digest_summary(summary: PipelineSummary) -> None:
    email_ok = summary.emails_sent > 0 and not summary.email_failures
    payload: dict[str, Any] = {
        "digest_window": summary.digest_window,
        "digest_jobs_count": summary.digest_jobs_count,
        "emails_attempted": summary.emails_attempted,
        "emails_sent": summary.emails_sent,
        "email_sent_successfully": email_ok,
        "email_failures": summary.email_failures,
    }
    logger.info("=== DIGEST EMAIL SUMMARY ===")
    for key, value in payload.items():
        logger.info("%s=%s", key, value)
    print(json.dumps(payload, indent=2))
    if summary.email_failures:
        for msg in summary.email_failures:
            print(f"EMAIL_FAILURE: {msg}", file=sys.stderr)
    elif summary.emails_attempted and summary.emails_sent:
        logger.info("Daily digest email sent successfully.")
    elif not summary.emails_attempted:
        logger.info(
            "No email sent (digest_jobs_count=%s; set SEND_EMPTY_DIGEST=true to send when empty).",
            summary.digest_jobs_count,
        )
