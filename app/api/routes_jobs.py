from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import Company, Job
from app.db.session import get_db_session
from app.schemas.job import JobListResponse, JobRead
from app.core.config import get_settings
from app.utils.dates import end_of_day_local, start_of_day_local, today_in_timezone

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse)
async def list_jobs(
    session: AsyncSession = Depends(get_db_session),
    company: str | None = Query(
        default=None,
        description="Case-insensitive substring match on company name",
    ),
    company_id: int | None = Query(default=None),
    is_entry_level: bool | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    first_seen_date: date | None = Query(default=None, description="Filter by first_seen day in configured timezone"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> JobListResponse:
    stmt = select(Job).options(joinedload(Job.company))
    count_stmt = select(func.count()).select_from(Job)

    company_name = (company or "").strip() or None
    if company_name:
        pattern = f"%{company_name}%"
        stmt = stmt.join(Company).where(Company.name.ilike(pattern))
        count_stmt = count_stmt.join(Company).where(Company.name.ilike(pattern))
    if company_id is not None:
        stmt = stmt.where(Job.company_id == company_id)
        count_stmt = count_stmt.where(Job.company_id == company_id)
    if is_entry_level is not None:
        stmt = stmt.where(Job.is_entry_level.is_(is_entry_level))
        count_stmt = count_stmt.where(Job.is_entry_level.is_(is_entry_level))
    if is_active is not None:
        stmt = stmt.where(Job.is_active.is_(is_active))
        count_stmt = count_stmt.where(Job.is_active.is_(is_active))
    if first_seen_date is not None:
        settings = get_settings()
        tz = settings.timezone
        start = start_of_day_local(first_seen_date, tz)
        end = end_of_day_local(first_seen_date, tz)
        stmt = stmt.where(Job.first_seen_at >= start, Job.first_seen_at <= end)
        count_stmt = count_stmt.where(Job.first_seen_at >= start, Job.first_seen_at <= end)

    total = int((await session.execute(count_stmt)).scalar_one())
    stmt = stmt.order_by(Job.first_seen_at.desc()).limit(limit).offset(offset)
    res = await session.execute(stmt)
    items = list(res.unique().scalars().all())
    return JobListResponse(
        items=[JobRead.model_validate(j) for j in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/new-today", response_model=JobListResponse)
async def new_jobs_today(
    session: AsyncSession = Depends(get_db_session),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> JobListResponse:
    settings = get_settings()
    tz = settings.timezone
    today_d = today_in_timezone(tz)
    start = start_of_day_local(today_d, tz)
    end = end_of_day_local(today_d, tz)

    count_stmt = (
        select(func.count())
        .select_from(Job)
        .where(Job.first_seen_at >= start, Job.first_seen_at <= end)
    )
    total = int((await session.execute(count_stmt)).scalar_one())

    stmt = (
        select(Job)
        .options(joinedload(Job.company))
        .where(Job.first_seen_at >= start, Job.first_seen_at <= end)
        .order_by(Job.company_id, Job.title)
        .limit(limit)
        .offset(offset)
    )
    res = await session.execute(stmt)
    items = list(res.unique().scalars().all())
    return JobListResponse(
        items=[JobRead.model_validate(j) for j in items],
        total=total,
        limit=limit,
        offset=offset,
    )
