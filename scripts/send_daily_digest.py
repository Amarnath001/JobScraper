"""
Send the daily entry-level email digest (no scraping).

Used by GitHub Actions (6:00 AM America/Los_Angeles in UTC cron):

  python scripts/send_daily_digest.py

Set DIGEST_LOOKBACK_HOURS=24 (default in CI) to include entry-level jobs
first_seen in the last 24 hours. Omit it to use calendar-day boundaries in TIMEZONE.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_scripts = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _root)
sys.path.insert(0, _scripts)

from app.core.database import get_engine, get_session_factory
from app.core.email_validation import log_email_config_warnings
from app.core.logging import setup_logging
from app.services.scrape_runner_service import run_daily_digest_only
from ci_summary import log_digest_summary

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    log_email_config_warnings()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")
    if not os.environ.get("RESEND_API_KEY"):
        raise SystemExit("RESEND_API_KEY is required for digest email")
    if not os.environ.get("EMAIL_TO"):
        raise SystemExit("EMAIL_TO is required for digest email")

    get_engine()
    logger.info("Database engine initialized")

    if os.environ.get("GITHUB_ACTIONS") == "true":
        os.environ.setdefault("DIGEST_LOOKBACK_HOURS", "24")

    lookback = os.environ.get("DIGEST_LOOKBACK_HOURS", "").strip()
    if lookback:
        logger.info("Digest job window: last %s hours (first_seen_at, UTC)", lookback)
    else:
        logger.info(
            "Digest job window: calendar day in TIMEZONE=%s",
            os.environ.get("TIMEZONE", "America/Los_Angeles"),
        )

    summary = await run_daily_digest_only(get_session_factory())
    log_digest_summary(summary)

    if summary.email_failures:
        raise SystemExit(1)

    if summary.emails_attempted and not summary.emails_sent:
        raise SystemExit(1)


def run() -> int:
    try:
        asyncio.run(main())
        return 0
    except SystemExit:
        raise
    except Exception:
        logger.exception("Daily digest failed with unhandled exception")
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except SystemExit as exc:
        raise SystemExit(exc.code if exc.code is not None else 1) from None
