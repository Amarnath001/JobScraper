from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company
from app.schemas.company import CompanyCreate


async def list_companies(session: AsyncSession) -> list[Company]:
    res = await session.execute(select(Company).order_by(Company.name))
    return list(res.scalars().all())


async def create_company(session: AsyncSession, data: CompanyCreate) -> Company:
    company = Company(
        name=data.name,
        careers_url=data.careers_url,
        source_type=data.source_type,
        source_config=data.source_config,
        enabled=data.enabled,
    )
    session.add(company)
    await session.flush()
    await session.refresh(company)
    return company


async def count_enabled_companies(session: AsyncSession) -> int:
    return int(
        await session.scalar(select(func.count()).select_from(Company).where(Company.enabled.is_(True))) or 0
    )
