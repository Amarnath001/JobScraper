"""Shared HTML/API parsing helpers for ATS scrapers (no network I/O)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

JOB_BOARD_HINTS = re.compile(
    r"job\s*posting|open\s*position|view\s*job|apply\s*now|search\s*jobs|"
    r"job\s*title|career\s*opportunit|data-automation-id|icims|smartrecruiters|"
    r"myworkdayjobs|jobs\.gem\.com",
    re.I,
)

HREF_RE = re.compile(r"""href\s*=\s*["']([^"'#][^"']*)["']""", re.I)


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(value, str):
        try:
            s = value.replace("Z", "+00:00") if value.endswith("Z") else value
            return datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


def looks_like_job_board(html: str, source_type: str | None = None) -> bool:
    text = html or ""
    lower = text.lower()
    if source_type == "gem" and "jobs.gem.com" in lower:
        return True
    if source_type == "icims" and "icims" in lower and "/jobs/" in lower:
        return True
    if source_type == "workday" and ("myworkdayjobs" in lower or "workday" in lower):
        return True
    if source_type == "smartrecruiters" and (
        "smartrecruiters" in lower or "posting" in lower
    ):
        return True
    if len(text) < 200:
        return False
    return bool(JOB_BOARD_HINTS.search(text))


def extract_hrefs(html: str, base_url: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for href in HREF_RE.findall(html or ""):
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href.strip())
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out


def parse_workday_careers_url(careers_url: str) -> tuple[str, str, str] | None:
    """
    Derive Workday CXS API parts from a myworkdayjobs.com URL.

    Returns (origin, tenant, site_name) e.g.
    https://boeing.wd1.myworkdayjobs.com, boeing, EXTERNAL_CAREERS
    """
    parsed = urlparse(careers_url.strip())
    if "myworkdayjobs.com" not in parsed.netloc.lower():
        return None
    tenant = parsed.netloc.split(".")[0].lower()
    if not tenant:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    site: str | None = None
    locale_re = re.compile(r"^[a-z]{2}-[A-Z]{2}$")
    skip = frozenset({"login", "jobs", "job", "apply", "search"})
    for i, part in enumerate(parts):
        if locale_re.match(part) and i + 1 < len(parts):
            candidate = parts[i + 1]
            if candidate.lower() not in skip:
                site = candidate
            break
    if site is None:
        for part in reversed(parts):
            if part.lower() not in skip and not locale_re.match(part):
                site = part
                break
    if not site:
        return None
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return origin, tenant, site


def workday_cxs_api_url(origin: str, tenant: str, site: str) -> str:
    return f"{origin}/wday/cxs/{tenant}/{site}/jobs"


def parse_workday_cxs_response(data: Any, *, origin: str) -> list[dict]:
    """Flatten Workday CXS /jobs JSON into raw job dicts."""
    if not isinstance(data, dict):
        return []
    postings = data.get("jobPostings") or data.get("jobs") or []
    if not isinstance(postings, list):
        return []
    out: list[dict] = []
    for item in postings:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row["_workday_source"] = "cxs_api"
        path = row.get("externalPath") or row.get("externalUrl")
        if path and not str(path).startswith("http"):
            row["url"] = urljoin(origin + "/", str(path).lstrip("/"))
        out.append(row)
    return out


def parse_smartrecruiters_api_payload(data: Any) -> list[dict]:
    if not isinstance(data, dict):
        return []
    content = data.get("content")
    if not isinstance(content, list):
        return []
    out: list[dict] = []
    for item in content:
        if isinstance(item, dict):
            row = dict(item)
            row["_sr_source"] = "api"
            out.append(row)
    return out


def smartrecruiters_company_from_url(careers_url: str) -> str | None:
    parsed = urlparse(careers_url)
    if "smartrecruiters.com" not in parsed.netloc.lower():
        return None
    parts = [p for p in parsed.path.split("/") if p]
    return parts[0] if parts else None


def gem_company_from_url(careers_url: str) -> str | None:
    parsed = urlparse(careers_url)
    if "jobs.gem.com" not in parsed.netloc.lower():
        return None
    parts = [p for p in parsed.path.split("/") if p]
    return parts[0] if parts else None


def normalize_gem_careers_url(careers_url: str) -> str:
    company = gem_company_from_url(careers_url)
    if company:
        return f"https://jobs.gem.com/{company}"
    return careers_url.rstrip("/")


GEM_JOB_LINK_RE = re.compile(
    r"https?://jobs\.gem\.com/([a-zA-Z0-9_-]+)/(?:[a-zA-Z0-9_-]+|am9icG9zd[A-Za-z0-9_-]+)",
    re.I,
)


def parse_gem_listing_html(html: str, base_url: str) -> list[dict]:
    """Extract unique Gem job board links from HTML."""
    company = gem_company_from_url(base_url)
    seen: set[str] = set()
    jobs: list[dict] = []

    for match in GEM_JOB_LINK_RE.finditer(html or ""):
        url = match.group(0).split('"')[0].split("'")[0]
        if url in seen:
            continue
        seen.add(url)
        slug_company = match.group(1)
        if company and slug_company.lower() != company.lower():
            continue
        jobs.append(
            {
                "_gem_source": "html",
                "url": url,
                "title": _title_from_gem_url(url),
                "company": slug_company,
            }
        )

    if jobs:
        return jobs

    prefix = normalize_gem_careers_url(base_url)
    for href in extract_hrefs(html, base_url):
        if "jobs.gem.com" not in href.lower():
            continue
        if href.rstrip("/") == prefix.rstrip("/"):
            continue
        if href in seen:
            continue
        if company and f"jobs.gem.com/{company}/" not in href.lower():
            continue
        seen.add(href)
        jobs.append(
            {
                "_gem_source": "html",
                "url": href,
                "title": _title_from_gem_url(href),
                "company": company or gem_company_from_url(href),
            }
        )
    return jobs


def _title_from_gem_url(url: str) -> str:
    path = urlparse(url).path.strip("/").split("/")
    if len(path) >= 2:
        tail = path[-1]
        if tail.isdigit() or tail.startswith("am9icG9zd"):
            return f"Role at {path[0]}"
    return "Open role"


ICIMS_JOB_PATH_RE = re.compile(r"/jobs/(?:intro|search|\d+)", re.I)
ICIMS_JOB_LINK_RE = re.compile(
    r'href\s*=\s*["\']([^"\']*/jobs/\d+/[^"\']*)["\']',
    re.I,
)


def parse_icims_listing_html(html: str, base_url: str) -> list[dict]:
    seen: set[str] = set()
    jobs: list[dict] = []

    for match in ICIMS_JOB_LINK_RE.finditer(html or ""):
        href = match.group(1).strip()
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        title = _icims_title_near(html, href) or "Open position"
        jobs.append(
            {
                "_icims_source": "html",
                "url": absolute,
                "title": title,
            }
        )

    if jobs:
        return jobs

    for href in extract_hrefs(html, base_url):
        if "icims.com" not in href.lower():
            continue
        if not ICIMS_JOB_PATH_RE.search(urlparse(href).path):
            continue
        if "/login" in href.lower():
            continue
        if href in seen:
            continue
        seen.add(href)
        jobs.append(
            {
                "_icims_source": "html",
                "url": href,
                "title": "Open position",
            }
        )
    return jobs


def _icims_title_near(html: str, href_fragment: str) -> str | None:
    idx = html.find(href_fragment)
    if idx < 0:
        return None
    window = html[max(0, idx - 200) : idx + 200]
    title_match = re.search(r">([^<]{4,120})</", window)
    if title_match:
        return title_match.group(1).strip()
    return None


def parse_smartrecruiters_listing_html(html: str, base_url: str) -> list[dict]:
    seen: set[str] = set()
    jobs: list[dict] = []
    company = smartrecruiters_company_from_url(base_url)

    for href in extract_hrefs(html, base_url):
        if "smartrecruiters.com" not in href.lower():
            continue
        if "/posting/" not in href.lower() and "/job/" not in href.lower():
            continue
        if href in seen:
            continue
        seen.add(href)
        jobs.append(
            {
                "_sr_source": "html",
                "url": href,
                "title": "Open position",
                "company": company,
            }
        )
    return jobs


def parse_workday_playwright_jobs(
    items: list[dict[str, str | None]],
    *,
    page_url: str,
) -> list[dict]:
    out: list[dict] = []
    for item in items:
        url = item.get("url")
        if not url:
            continue
        out.append(
            {
                "_workday_source": "playwright",
                "title": (item.get("title") or "Untitled").strip(),
                "url": urljoin(page_url, url) if not str(url).startswith("http") else url,
                "location": item.get("location"),
                "postedOn": item.get("posted_on"),
            }
        )
    return out


def safe_json_loads(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
