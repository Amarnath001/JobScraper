from pydantic import BaseModel


class ScrapeTriggerResponse(BaseModel):
    success: bool
    message: str
    companies_scanned: int = 0
    jobs_seen: int = 0
    new_jobs_created: int = 0
    inactive_jobs_marked: int = 0
    emails_sent: int = 0
    failures: list[str] = []
