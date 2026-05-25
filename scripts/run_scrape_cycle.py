"""
Run scrape + ingest for all enabled companies.

By default also sends an entry-level digest email after the scrape when
SEND_DIGEST_AFTER_SCRAPE=true (GitHub Actions sets this).

  python scripts/run_scrape_cycle.py

Use DIGEST_LOOKBACK_HOURS (e.g. 4) so each run emails jobs first_seen in that window.
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
from app.services.scrape_runner_service import run_scrape_only, run_scrape_pipeline
from ci_summary import log_digest_summary, log_scrape_summary

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


async def main() -> None:
    setup_logging()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    send_digest = _env_bool("SEND_DIGEST_AFTER_SCRAPE", default=False)
    if send_digest:
        log_email_config_warnings()

    get_engine()
    logger.info(
        "Database engine initialized (send_digest_after_scrape=%s digest_lookback_hours=%s)",
        send_digest,
        os.environ.get("DIGEST_LOOKBACK_HOURS", ""),
    )

    factory = get_session_factory()
    if send_digest:
        summary = await run_scrape_pipeline(factory, send_digest=True)
    else:
        summary = await run_scrape_only(factory)

    log_scrape_summary(summary)
    if send_digest:
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
        logger.exception("Scrape cycle failed with unhandled exception")
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except SystemExit as exc:
        raise SystemExit(exc.code if exc.code is not None else 1) from None
