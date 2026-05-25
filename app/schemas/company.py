from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    name: str
    careers_url: str
    source_type: str
    source_config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    careers_url: str
    source_type: str
    source_config: dict[str, Any]
    enabled: bool
    last_validated_at: datetime | None = None
    last_validation_status: str | None = None
    consecutive_failures: int = 0
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class CompanyValidationRow(BaseModel):
    company: str
    source_type: str
    status_code: int | None
    valid: bool
    error: str | None = None


class CompanyValidationResponse(BaseModel):
    valid_count: int
    disabled_count: int
    failed_count: int
    skipped_count: int = 0
    results: list[CompanyValidationRow] = Field(default_factory=list)
