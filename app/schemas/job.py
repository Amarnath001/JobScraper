from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NormalizedJob(BaseModel):
    """Consistent shape produced by all scrapers before DB persistence."""

    model_config = ConfigDict(extra="forbid")

    company_name: str
    source_type: str
    external_job_id: str | None = None
    title: str
    team: str | None = None
    location: str | None = None
    employment_type: str | None = None
    level: str | None = None
    url: str
    description_text: str | None = None
    posted_at: datetime | None = None
    raw_payload: dict = Field(default_factory=dict)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    source_type: str
    external_job_id: str | None
    title: str
    team: str | None
    location: str | None
    employment_type: str | None
    level: str | None
    url: str
    description_text: str | None
    posted_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool
    entry_level_score: float
    is_entry_level: bool
    is_software_engineering_related: bool
    fingerprint_hash: str
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[JobRead]
    total: int
    limit: int
    offset: int
