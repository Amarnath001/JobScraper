"""Human-readable summaries for GitHub Actions logs."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from app.services.scrape_runner_service import PipelineSummary

logger = logging.getLogger(__name__)


def log_scrape_summary(summary: PipelineSummary) -> None:
    ing = summary.ingest
    payload: dict[str, Any] = {
        "companies_scanned": summary.companies_scanned,
        "jobs_seen_total": ing.jobs_seen_total,
        "jobs_inserted_total": ing.jobs_inserted_total,
        "new_jobs_created_all": ing.jobs_inserted_total,
        "new_swe_jobs_created": ing.jobs_inserted_software_related,
        "new_entry_level_swe_jobs_created": ing.jobs_inserted_digest_eligible,
        "jobs_inserted_software_related": ing.jobs_inserted_software_related,
        "jobs_inserted_entry_level": ing.jobs_inserted_entry_level,
        "jobs_inserted_digest_eligible": ing.jobs_inserted_digest_eligible,
        "jobs_skipped_international": ing.jobs_skipped_international,
        "jobs_skipped_non_software": ing.jobs_skipped_non_software,
        "jobs_skipped_non_entry_level": ing.jobs_skipped_non_entry_level,
        "digest_candidates_count": summary.digest_candidates_count,
        "inactive_jobs_marked": ing.inactive_jobs_marked,
        "jobs_seen": ing.jobs_seen,
        "new_jobs_created": ing.new_jobs_created,
        "scraper_failures": summary.scraper_failures,
        "scraper_failure_count": len(summary.scraper_failures),
    }
    logger.info("=== SCRAPE CYCLE SUMMARY ===")
    logger.info("companies_scanned=%s", summary.companies_scanned)
    logger.info("jobs_seen_total=%s", ing.jobs_seen_total)
    logger.info("jobs_inserted_total=%s", ing.jobs_inserted_total)
    logger.info("new_swe_jobs_created=%s", ing.jobs_inserted_software_related)
    logger.info("new_entry_level_swe_jobs_created=%s", ing.jobs_inserted_digest_eligible)
    logger.info("jobs_skipped_international=%s", ing.jobs_skipped_international)
    logger.info("jobs_skipped_non_software=%s", ing.jobs_skipped_non_software)
    logger.info("jobs_skipped_non_entry_level=%s", ing.jobs_skipped_non_entry_level)
    logger.info("digest_candidates_count=%s", summary.digest_candidates_count)
    logger.info("inactive_jobs_marked=%s", ing.inactive_jobs_marked)
    for key, value in payload.items():
        if key.startswith("jobs_") or key.startswith("new_"):
            continue
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
        "digest_candidates_count": summary.digest_candidates_count,
        "digest_swe_jobs_count": summary.digest_swe_jobs_count,
        "digest_entry_level_swe_jobs_count": summary.digest_entry_level_swe_jobs_count,
        "digest_jobs_count": summary.digest_candidates_count,
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
            "No email sent (digest_candidates_count=%s; set SEND_EMPTY_DIGEST=true to send when empty).",
            summary.digest_candidates_count,
        )
