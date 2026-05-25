from pydantic import BaseModel, Field


class ScrapeTriggerResponse(BaseModel):
    success: bool
    message: str
    companies_scanned: int = 0
    jobs_seen: int = 0
    new_jobs_created: int = 0
    inactive_jobs_marked: int = 0
    emails_attempted: int = 0
    emails_sent: int = 0
    scraper_failures: list[str] = Field(default_factory=list)
    email_failures: list[str] = Field(default_factory=list)


class TestEmailResponse(BaseModel):
    success: bool
    message: str
    provider_id: str | None = None
    error: str | None = None
