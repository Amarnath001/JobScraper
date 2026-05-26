"""Parse and upsert companies from data/company_targets.csv."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company
from app.utils.source_urls import careers_url_for

REQUIRED_COLUMNS = (
    "name",
    "category",
    "source_list",
    "careers_url",
    "source_type",
    "source_config_json",
    "priority",
    "enabled",
)

SCRAPER_SOURCE_TYPES = frozenset(
    {
        "greenhouse",
        "lever",
        "ashby",
        "workday",
        "icims",
        "gem",
        "smartrecruiters",
        "generic_playwright",
    }
)
UNCONFIGURED_SOURCE_TYPE = "unconfigured"
NEEDS_ATS_ERROR = "Needs ATS/source config"


@dataclass(frozen=True)
class CompanyTargetRow:
    name: str
    category: str
    source_list: str
    careers_url: str
    source_type: str
    source_config: dict[str, Any]
    priority: str
    enabled: bool
    line_number: int


@dataclass
class CompanyTargetImportSummary:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    unconfigured: int = 0
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_source_config(raw: str, line_number: int) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"line {line_number}: invalid source_config_json: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"line {line_number}: source_config_json must be a JSON object")
    return parsed


def parse_company_targets_csv(path: Path) -> list[CompanyTargetRow]:
    if not path.is_file():
        raise FileNotFoundError(path)

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")

        missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
        if missing:
            raise ValueError(f"CSV missing required columns: {', '.join(missing)}")

        rows: list[CompanyTargetRow] = []
        for line_number, raw in enumerate(reader, start=2):
            name = (raw.get("name") or "").strip()
            if not name:
                raise ValueError(f"line {line_number}: name is required")

            careers_url = (raw.get("careers_url") or "").strip()
            if not careers_url:
                raise ValueError(f"line {line_number}: careers_url is required for {name!r}")

            source_type = (raw.get("source_type") or "").strip().lower()
            source_config = _parse_source_config(raw.get("source_config_json") or "", line_number)

            rows.append(
                CompanyTargetRow(
                    name=name,
                    category=(raw.get("category") or "").strip(),
                    source_list=(raw.get("source_list") or "").strip(),
                    careers_url=careers_url,
                    source_type=source_type,
                    source_config=source_config,
                    priority=(raw.get("priority") or "").strip(),
                    enabled=_parse_bool(raw.get("enabled") or ""),
                    line_number=line_number,
                )
            )

    return rows


def normalize_target_row(row: CompanyTargetRow) -> dict[str, Any]:
    """Map a CSV row to Company fields (may force unconfigured + disabled)."""
    source_type = row.source_type
    enabled = row.enabled
    source_config = dict(row.source_config)
    last_error: str | None = None

    if not source_type or source_type not in SCRAPER_SOURCE_TYPES:
        source_type = UNCONFIGURED_SOURCE_TYPE
        source_config = {}
        enabled = False
        last_error = NEEDS_ATS_ERROR

    careers_url = row.careers_url
    if source_type != UNCONFIGURED_SOURCE_TYPE and not careers_url:
        careers_url = careers_url_for(source_type, source_config)

    return {
        "name": row.name,
        "careers_url": careers_url,
        "source_type": source_type,
        "source_config": source_config,
        "enabled": enabled,
        "last_error": last_error,
    }


async def upsert_company_targets(
    session: AsyncSession,
    rows: list[CompanyTargetRow],
) -> CompanyTargetImportSummary:
    summary = CompanyTargetImportSummary()

    for row in rows:
        try:
            payload = normalize_target_row(row)
        except ValueError as exc:
            summary.skipped += 1
            summary.errors.append(str(exc))
            continue

        if payload["source_type"] == UNCONFIGURED_SOURCE_TYPE:
            summary.unconfigured += 1

        existing = await session.scalar(
            select(Company).where(
                Company.name == payload["name"],
                Company.source_type == payload["source_type"],
            )
        )

        if existing is None:
            session.add(
                Company(
                    name=payload["name"],
                    careers_url=payload["careers_url"],
                    source_type=payload["source_type"],
                    source_config=payload["source_config"],
                    enabled=payload["enabled"],
                    last_error=payload["last_error"],
                )
            )
            summary.inserted += 1
        else:
            existing.careers_url = payload["careers_url"]
            existing.source_config = payload["source_config"]
            existing.enabled = payload["enabled"]
            existing.last_error = payload["last_error"]
            summary.updated += 1

    await session.flush()
    return summary
