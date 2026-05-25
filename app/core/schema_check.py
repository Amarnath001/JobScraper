"""Verify PostgreSQL schema exists before running app pipelines."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

SCHEMA_NOT_INITIALIZED_MESSAGE = (
    "Database schema not initialized. Run `alembic upgrade head` or the Init DB GitHub Actions workflow."
)


async def assert_database_schema_ready(
    session_factory: async_sessionmaker,
    *,
    table: str = "companies",
) -> None:
    """Raise RuntimeError if the expected table is missing (migrations not applied)."""
    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables "
                "  WHERE table_schema = 'public' AND table_name = :table_name"
                ")"
            ),
            {"table_name": table},
        )
        if not result.scalar():
            raise RuntimeError(SCHEMA_NOT_INITIALIZED_MESSAGE)
