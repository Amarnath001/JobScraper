"""Heuristics for generic careers-page job link discovery (no Playwright)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urlunparse

ACCEPT_TEXT_RE = re.compile(
    r"job|jobs|career|careers|opening|requisition|position|software|engineer",
    re.I,
)
REJECT_TEXT_RE = re.compile(
    r"login|sign[\s-]?in|sign[\s-]?up|apply[\s/]?login|benefits|culture|blog|"
    r"privacy|terms|cookie|interview[\s-]?tips|life[\s-]?at|diversity[\s-]?and",
    re.I,
)
REJECT_URL_RE = re.compile(
    r"login|signin|sign-in|signup|sign-up|/apply(?:/|$|\?)|benefits|culture|"
    r"/blog|privacy|terms|cookie|interview-tips|auth/|oauth|sso",
    re.I,
)
APPLY_BUTTON_RE = re.compile(r"^\s*apply\s*$|^apply\s+now\s*$", re.I)

FOLLOW_PATH_HINTS = (
    "/jobs",
    "/job/",
    "/careers",
    "/openings",
    "/opportunities",
    "/search",
    "/positions",
    "/requisition",
)

JOB_PATH_HINT_RE = re.compile(
    r"job|jobs|career|careers|opening|requisition|position|posting|vacanc",
    re.I,
)

LOAD_MORE_SELECTORS = (
    'button[data-automation-id="loadMoreJobs"]',
    'button:has-text("Load more")',
    'button:has-text("Show more")',
    'a:has-text("Load more")',
    '[data-testid*="load-more" i]',
)

COOKIE_DISMISS_SELECTORS = (
    "#onetrust-accept-btn-handler",
    'button:has-text("Accept all")',
    'button:has-text("Accept All")',
    'button:has-text("Accept")',
    'button:has-text("I agree")',
    'button:has-text("Agree")',
    '[aria-label*="accept" i]',
    '[id*="accept-cookies" i]',
)


@dataclass(frozen=True)
class ExtractedJobLink:
    title: str
    url: str
    location: str | None = None


def normalize_page_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", ""))


def same_site(base_url: str, candidate: str) -> bool:
    base = urlparse(base_url)
    cand = urlparse(candidate)
    if base.netloc.lower() != cand.netloc.lower():
        return False
    return cand.scheme in ("http", "https")


def is_rejected_url(url: str, link_text: str = "") -> bool:
    blob = f"{url} {link_text}".lower()
    if REJECT_URL_RE.search(url) or REJECT_TEXT_RE.search(blob):
        return True
    if APPLY_BUTTON_RE.match(link_text.strip()):
        return True
    if re.search(r"\bapply\b", link_text, re.I) and len(link_text.strip()) < 24:
        return True
    return False


def is_job_link(url: str, link_text: str = "") -> bool:
    if not url or url.startswith(("mailto:", "tel:", "javascript:", "#")):
        return False
    if is_rejected_url(url, link_text):
        return False
    path_query = f"{urlparse(url).path} {urlparse(url).query} {link_text}"
    if not ACCEPT_TEXT_RE.search(path_query) and not JOB_PATH_HINT_RE.search(path_query):
        return False
    return True


def score_job_link(url: str, link_text: str = "") -> int:
    if not is_job_link(url, link_text):
        return -1
    score = 10
    lower = f"{url} {link_text}".lower()
    if "/job/" in lower or "/jobs/" in lower:
        score += 20
    if "engineer" in lower or "software" in lower:
        score += 8
    if "requisition" in lower or "posting" in lower:
        score += 6
    if len(link_text.strip()) > 8:
        score += 4
    return score


def extract_title_from_link_text(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned or APPLY_BUTTON_RE.match(cleaned):
        return "Open position"
    if len(cleaned) > 160:
        return cleaned[:157] + "..."
    return cleaned


def merge_job_links(
    existing: dict[str, ExtractedJobLink],
    candidates: list[ExtractedJobLink],
    *,
    max_links: int,
) -> None:
    for item in candidates:
        if len(existing) >= max_links:
            return
        if item.url in existing:
            prev = existing[item.url]
            if len(item.title) > len(prev.title):
                existing[item.url] = item
            continue
        existing[item.url] = item


def candidate_follow_urls(base_url: str, page_url: str, hrefs: list[str]) -> list[str]:
    """Return same-site URLs worth visiting for more listings."""
    seen: set[str] = set()
    scored: list[tuple[int, str]] = []
    base_host = urlparse(base_url).netloc.lower()

    for href in hrefs:
        absolute = urljoin(page_url, href)
        if not same_site(base_url, absolute):
            continue
        normalized = normalize_page_url(absolute)
        if normalized in seen:
            continue
        seen.add(normalized)

        path_lower = urlparse(absolute).path.lower()
        score = 0
        if any(hint in path_lower for hint in FOLLOW_PATH_HINTS):
            score += 15
        if JOB_PATH_HINT_RE.search(path_lower):
            score += 10
        if path_lower in ("/careers", "/jobs", "/job", "/openings"):
            score += 20
        if score > 0 and not is_rejected_url(absolute):
            scored.append((score, absolute))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [url for _, url in scored[:20]]


def links_from_anchor_dicts(
    anchors: list[dict],
    page_url: str,
    *,
    max_links: int,
) -> list[ExtractedJobLink]:
    found: dict[str, ExtractedJobLink] = {}
    for anchor in anchors:
        href = str(anchor.get("href") or "").strip()
        text = str(anchor.get("text") or "").strip()
        if not href:
            continue
        absolute = urljoin(page_url, href)
        if not is_job_link(absolute, text):
            continue
        if score_job_link(absolute, text) < 0:
            continue
        title = extract_title_from_link_text(text)
        merge_job_links(
            found,
            [ExtractedJobLink(title=title, url=absolute, location=anchor.get("location"))],
            max_links=max_links,
        )
    return list(found.values())
