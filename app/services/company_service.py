from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company
from app.schemas.company import CompanyCreate


async def list_companies(
    session: AsyncSession,
    *,
    enabled: bool | None = None,
) -> list[Company]:
    stmt = select(Company).order_by(Company.name)
    if enabled is not None:
        stmt = stmt.where(Company.enabled.is_(enabled))
    res = await session.execute(stmt)
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
