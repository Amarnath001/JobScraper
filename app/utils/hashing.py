import hashlib

from app.utils.text import normalize_for_fingerprint


def compute_job_fingerprint(
    *,
    company_name: str,
    title: str,
    location: str | None,
    url: str,
    external_job_id: str | None,
) -> str:
    """
    Stable SHA-256 over normalized company, title, location, url, external id.
    """
    parts = [
        normalize_for_fingerprint(company_name),
        normalize_for_fingerprint(title),
        normalize_for_fingerprint(location),
        normalize_for_fingerprint(url),
        normalize_for_fingerprint(external_job_id),
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
