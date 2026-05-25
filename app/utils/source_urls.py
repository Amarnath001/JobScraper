from typing import Any


def careers_url_for(source_type: str, source_config: dict[str, Any]) -> str:
    if source_type == "greenhouse":
        token = source_config.get("board_token") or source_config.get("token")
        if not token:
            raise ValueError("Greenhouse source_config requires board_token")
        return f"https://boards.greenhouse.io/{token}"
    if source_type == "lever":
        site = source_config.get("company") or source_config.get("site")
        if not site:
            raise ValueError("Lever source_config requires company")
        return f"https://jobs.lever.co/{site}"
    if source_type == "ashby":
        org = source_config.get("organization") or source_config.get("org")
        if org:
            return f"https://jobs.ashbyhq.com/{org}"
        return source_config.get("posting_api_url") or "https://jobs.ashbyhq.com/"
    return source_config.get("careers_url") or source_config.get("page_url") or ""


def validation_url_for(source_type: str, source_config: dict[str, Any]) -> str | None:
    """Public ATS probe URL, or None if not HTTP-validatable."""
    if source_type == "greenhouse":
        token = source_config.get("board_token") or source_config.get("token")
        if not token:
            return None
        return f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    if source_type == "lever":
        site = source_config.get("company") or source_config.get("site")
        if not site:
            return None
        return f"https://api.lever.co/v0/postings/{site}"
    if source_type == "ashby":
        if custom := source_config.get("posting_api_url"):
            return str(custom)
        org = source_config.get("organization") or source_config.get("org")
        if not org:
            return None
        return f"https://api.ashbyhq.com/posting-api/job-board/{org}"
    return None
