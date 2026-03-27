from app.schemas.job import NormalizedJob
from app.utils.hashing import compute_job_fingerprint


def fingerprint_for_normalized(company_name: str, job: NormalizedJob) -> str:
    return compute_job_fingerprint(
        company_name=company_name,
        title=job.title,
        location=job.location,
        url=job.url,
        external_job_id=job.external_job_id,
    )
