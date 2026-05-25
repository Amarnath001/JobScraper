from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company
from app.utils.source_urls import careers_url_for


def load_companies_from_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("companies.json must be a JSON array")
    return data


def _careers_url_for_row(row: dict[str, Any]) -> str:
    if url := row.get("careers_url"):
        return str(url)
    return careers_url_for(str(row["source_type"]), dict(row["source_config"]))


async def upsert_companies_from_rows(
    session: AsyncSession,
    rows: list[dict[str, Any]],
) -> tuple[int, int]:
    """Returns (inserted, updated)."""
    inserted = 0
    updated = 0

    for row in rows:
        name = str(row["name"])
        source_type = str(row["source_type"])
        source_config = dict(row["source_config"])
        enabled = bool(row.get("enabled", True))
        careers_url = _careers_url_for_row(row)

        existing = await session.scalar(
            select(Company).where(Company.name == name, Company.source_type == source_type)
        )
        if existing is None:
            session.add(
                Company(
                    name=name,
                    careers_url=careers_url,
                    source_type=source_type,
                    source_config=source_config,
                    enabled=enabled,
                )
            )
            inserted += 1
        else:
            existing.careers_url = careers_url
            existing.source_config = source_config
            if "enabled" in row:
                existing.enabled = enabled
            updated += 1

    await session.flush()
    return inserted, updated
