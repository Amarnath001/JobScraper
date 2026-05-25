from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes_admin import router as admin_router
from app.api.routes_health import router as health_router
from app.api.routes_jobs import router as jobs_router
from app.core.email_validation import log_email_config_warnings
from app.core.logging import setup_logging
from app.core.scheduler import shutdown_scheduler, start_scheduler

setup_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log_email_config_warnings()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="job-scraper", lifespan=lifespan)
app.include_router(health_router)
app.include_router(jobs_router)
app.include_router(admin_router)
