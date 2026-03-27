from pydantic import BaseModel


class DigestPreview(BaseModel):
    subject: str
    html: str
    text: str
    job_count: int
