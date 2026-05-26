from typing import Any

from app.scrapers.parsing import normalize_gem_careers_url, smartrecruiters_company_from_url


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
    if source_type == "smartrecruiters":
        if url := source_config.get("careers_url"):
            return str(url).rstrip("/")
        company = source_config.get("company")
        if not company:
            raise ValueError("SmartRecruiters source_config requires company or careers_url")
        return f"https://jobs.smartrecruiters.com/{company}"
    if source_type == "gem":
        url = source_config.get("careers_url")
        if not url:
            raise ValueError("Gem source_config requires careers_url")
        return normalize_gem_careers_url(str(url))
    if source_type in ("workday", "icims", "generic_playwright"):
        url = source_config.get("careers_url") or source_config.get("page_url")
        if not url:
            raise ValueError(f"{source_type} source_config requires careers_url")
        return str(url).rstrip("/")
    return source_config.get("careers_url") or source_config.get("page_url") or ""


def validation_url_for(source_type: str, source_config: dict[str, Any]) -> str | None:
    """Public probe URL for validation (API or careers page)."""
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
    if source_type == "smartrecruiters":
        company = source_config.get("company") or smartrecruiters_company_from_url(
            str(source_config.get("careers_url") or "")
        )
        if not company:
            return None
        return f"https://api.smartrecruiters.com/v1/companies/{company}/postings"
    if source_type in ("workday", "icims", "gem", "generic_playwright"):
        try:
            return careers_url_for(source_type, source_config)
        except ValueError:
            return None
    return None


def validation_expects_json(source_type: str) -> bool:
    return source_type in ("greenhouse", "lever", "ashby", "smartrecruiters")
