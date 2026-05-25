"""
Run scrape + ingest for all enabled companies (no email digest).

Used by GitHub Actions and cron hosts:

  python scripts/run_scrape_cycle.py
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
from app.core.logging import setup_logging
from app.services.scrape_runner_service import run_scrape_only
from ci_summary import log_scrape_summary

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is required")

    get_engine()
    logger.info("Database engine initialized")

    summary = await run_scrape_only(get_session_factory())
    log_scrape_summary(summary)


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
