import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.services.scrape_runner_service import run_scrape_pipeline

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _scheduled_pipeline() -> None:
    await run_scrape_pipeline(get_session_factory())


def start_scheduler() -> None:
    global _scheduler
    settings = get_settings()
    if not settings.enable_scheduler:
        logger.info("Scheduler disabled (ENABLE_SCHEDULER=false)")
        return
    _scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.timezone))
    _scheduler.add_job(
        _scheduled_pipeline,
        "cron",
        hour=6,
        minute=0,
        id="daily_scrape_digest",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info("Scheduler started: daily job at 06:00 %s", settings.timezone)


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
