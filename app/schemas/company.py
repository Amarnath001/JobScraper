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
    created_at: datetime
    updated_at: datetime
