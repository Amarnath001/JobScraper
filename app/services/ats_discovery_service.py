"""ATS detection by inspecting careers landing pages and linked job-search pages."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from app.services.company_targets_service import SCRAPER_SOURCE_TYPES

logger = logging.getLogger(__name__)

USER_AGENT = "JobScraper/1.0 (ATS discovery)"
MAX_FOLLOW_LINKS = 5
LINK_HINT_RE = re.compile(
    r"jobs|careers|search|openings|opportunities|greenhouse|lever|ashby|"
    r"workday|smartrecruiters|icims|myworkdayjobs|taleo|eightfold|oraclecloud|jobs\.gem",
    re.I,
)
HREF_RE = re.compile(r"""href\s*=\s*["']([^"'#][^"']*)["']""", re.I)
IFRAME_SRC_RE = re.compile(r"""<iframe[^>]+src\s*=\s*["']([^"']+)["']""", re.I)

SUPPORTED_PROVIDERS = frozenset(SCRAPER_SOURCE_TYPES)


@dataclass(frozen=True)
class ATSDiscoveryCandidate:
    """One ATS signature match found in page HTML or URL."""

    provider: str
    confidence: int
    source_type: str | None
    source_config: dict[str, Any]
    evidence: str


@dataclass
class AtsDiscoveryResult:
    """Discovery outcome for one company careers site."""

    source_type: str = ""
    source_config: dict[str, Any] = field(default_factory=dict)
    provider_detected: str | None = None
    suggested_source_type: str | None = None
    supported: bool = False
    confidence: str = "none"
    reason: str = ""
    evidence: str = ""
    pages_inspected: tuple[str, ...] = ()
    final_careers_url: str | None = None
    fetch_failed: bool = False

    @property
    def source_config_json(self) -> dict[str, Any]:
        return self.source_config

    @property
    def remains_unconfigured(self) -> bool:
        return not self.supported


def json_dumps(config: dict[str, Any]) -> str:
    return json.dumps(config, separators=(",", ":"))


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def _same_registrable_domain(a: str, b: str) -> bool:
    def root(host: str) -> str:
        parts = (host or "").lower().split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host

    return root(urlparse(a).netloc) == root(urlparse(b).netloc)


def extract_candidate_links(html: str, base_url: str, *, limit: int = 30) -> list[str]:
    """Return scored job-related links from HTML (highest priority first)."""
    seen: set[str] = set()
    scored: list[tuple[int, str]] = []
    base_host = urlparse(base_url).netloc.lower()

    raw_hrefs = [m.group(1).strip() for m in HREF_RE.finditer(html or "")]
    raw_hrefs.extend(m.group(1).strip() for m in IFRAME_SRC_RE.finditer(html or ""))

    for href in raw_hrefs:
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        normalized = _normalize_url(absolute)
        if normalized in seen:
            continue
        seen.add(normalized)

        score = 0
        blob = f"{normalized} {href}".lower()
        if LINK_HINT_RE.search(blob):
            score += 10
        if any(
            host in parsed.netloc.lower()
            for host in (
                "greenhouse.io",
                "lever.co",
                "ashbyhq.com",
                "myworkdayjobs.com",
                "smartrecruiters.com",
                "icims.com",
                "taleo.net",
                "eightfold.ai",
                "oraclecloud.com",
                "jobs.gem.com",
            )
        ):
            score += 25
        if _same_registrable_domain(base_url, normalized):
            score += 5
        if parsed.netloc.lower() == base_host:
            score += 3
        if score > 0:
            scored.append((score, normalized))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [url for _, url in scored[:limit]]


def _first_group(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.I)
    return match.group(1) if match else None


def collect_ats_candidates(text: str, page_url: str) -> list[ATSDiscoveryCandidate]:
    """Scan page HTML + URL for ATS signatures."""
    blob = f"{text}\n{page_url}"
    found: list[ATSDiscoveryCandidate] = []

    if token := _first_group(r"boards-api\.greenhouse\.io/v1/boards/([a-z0-9_-]+)/", blob):
        found.append(
            ATSDiscoveryCandidate(
                "greenhouse",
                100,
                "greenhouse",
                {"board_token": token},
                f"Greenhouse API board token: {token}",
            )
        )
    if token := _first_group(r"(?:boards|job-boards)\.greenhouse\.io/([a-z0-9_-]+)", blob):
        found.append(
            ATSDiscoveryCandidate(
                "greenhouse",
                95,
                "greenhouse",
                {"board_token": token},
                f"Greenhouse board URL token: {token}",
            )
        )
    if slug := _first_group(r"jobs\.lever\.co/([a-z0-9_-]+)", blob):
        found.append(
            ATSDiscoveryCandidate(
                "lever",
                100,
                "lever",
                {"company": slug},
                f"Lever jobs URL slug: {slug}",
            )
        )
    if slug := _first_group(r"api\.lever\.co/v0/postings/([a-z0-9_-]+)", blob):
        found.append(
            ATSDiscoveryCandidate(
                "lever",
                98,
                "lever",
                {"company": slug},
                f"Lever API slug: {slug}",
            )
        )
    if org := _first_group(r"jobs\.ashbyhq\.com/([a-z0-9_-]+)", blob):
        found.append(
            ATSDiscoveryCandidate(
                "ashby",
                100,
                "ashby",
                {"organization": org},
                f"Ashby jobs org: {org}",
            )
        )
    if org := _first_group(r"api\.ashbyhq\.com/posting-api/job-board/([a-z0-9_-]+)", blob):
        found.append(
            ATSDiscoveryCandidate(
                "ashby",
                98,
                "ashby",
                {"organization": org},
                f"Ashby posting API org: {org}",
            )
        )
    if m := _first_group(r"(https?://[a-z0-9.-]*\.myworkdayjobs\.com/[^\"'\s<>]+)", blob):
        found.append(
            ATSDiscoveryCandidate(
                "workday",
                90,
                None,
                {"careers_url": m.rstrip("/"), "page_url": m.rstrip("/")},
                f"Workday host: {m}",
            )
        )
    if m := _first_group(r"(https?://jobs\.smartrecruiters\.com/[a-z0-9_-]+)", blob):
        found.append(
            ATSDiscoveryCandidate(
                "smartrecruiters",
                88,
                None,
                {"careers_url": m.rstrip("/")},
                f"SmartRecruiters board: {m}",
            )
        )
    if m := _first_group(r"(https?://[a-z0-9.-]*\.icims\.com[^\"'\s<>]*)", blob):
        found.append(
            ATSDiscoveryCandidate(
                "icims",
                85,
                None,
                {"careers_url": m.rstrip("/")},
                f"iCIMS URL: {m}",
            )
        )
    if m := _first_group(r"(https?://jobs\.gem\.com/[^\"'\s<>]+)", blob):
        found.append(
            ATSDiscoveryCandidate(
                "gem",
                84,
                None,
                {"careers_url": m.rstrip("/")},
                f"Gem jobs URL: {m}",
            )
        )
    if "taleo.net" in blob.lower():
        if m := _first_group(r"(https?://[^\"'\s<>]*taleo\.net[^\"'\s<>]*)", blob):
            found.append(
                ATSDiscoveryCandidate(
                    "taleo",
                    82,
                    None,
                    {"careers_url": m.rstrip("/")},
                    f"Taleo URL: {m}",
                )
            )
        else:
            found.append(
                ATSDiscoveryCandidate(
                    "taleo",
                    70,
                    None,
                    {},
                    "Taleo reference in page (no board URL extracted)",
                )
            )
    if m := _first_group(r"(https?://[^\"'\s<>]*eightfold\.ai[^\"'\s<>]*)", blob):
        found.append(
            ATSDiscoveryCandidate(
                "eightfold",
                84,
                None,
                {"careers_url": m.rstrip("/")},
                f"Eightfold URL: {m}",
            )
        )
    if m := _first_group(
        r"(https?://[a-z0-9.-]*\.oraclecloud\.com/hcmUI/CandidateExperience[^\"'\s<>]*)",
        blob,
    ):
        found.append(
            ATSDiscoveryCandidate(
                "oracle",
                86,
                None,
                {"careers_url": m.rstrip("/")},
                f"Oracle Cloud HCM: {m}",
            )
        )

    parsed = urlparse(page_url)
    if parsed.netloc.endswith("greenhouse.io") and parsed.path.strip("/"):
        token = parsed.path.strip("/").split("/")[0]
        if token and token not in ("embed", "jobs"):
            found.append(
                ATSDiscoveryCandidate(
                    "greenhouse",
                    92,
                    "greenhouse",
                    {"board_token": token},
                    f"Greenhouse host path token: {token}",
                )
            )

    return found


# Backward-compatible alias
_collect_candidates = collect_ats_candidates


def _pick_best(candidates: list[ATSDiscoveryCandidate]) -> ATSDiscoveryCandidate | None:
    if not candidates:
        return None
    supported = [c for c in candidates if c.source_type in SUPPORTED_PROVIDERS]
    pool = supported if supported else candidates
    return max(pool, key=lambda c: c.confidence)


def _unknown_result(pages: tuple[str, ...], landing_url: str) -> AtsDiscoveryResult:
    reason = "No supported ATS pattern detected"
    return AtsDiscoveryResult(
        source_type="",
        source_config={},
        provider_detected=None,
        suggested_source_type=None,
        supported=False,
        confidence="none",
        reason=reason,
        evidence=reason,
        pages_inspected=pages,
        final_careers_url=landing_url,
    )


def _result_from_candidates(
    candidates: list[ATSDiscoveryCandidate],
    pages_inspected: list[str],
    landing_url: str,
) -> AtsDiscoveryResult:
    pages = tuple(pages_inspected)
    best = _pick_best(candidates)
    if best is None:
        return _unknown_result(pages, landing_url)

    if best.source_type in SUPPORTED_PROVIDERS:
        return AtsDiscoveryResult(
            source_type=best.source_type,
            source_config=dict(best.source_config),
            provider_detected=best.provider,
            suggested_source_type=best.source_type,
            supported=True,
            confidence="high",
            reason=best.evidence,
            evidence=best.evidence,
            pages_inspected=pages,
            final_careers_url=landing_url,
        )

    reason = (
        f"{best.evidence}. Provider '{best.provider}' is detected but not auto-enabled "
        f"(supported scrapers: {', '.join(sorted(SUPPORTED_PROVIDERS))})."
    )
    return AtsDiscoveryResult(
        source_type=best.provider,
        source_config=dict(best.source_config),
        provider_detected=best.provider,
        suggested_source_type=best.provider,
        supported=False,
        confidence="medium",
        reason=reason,
        evidence=reason,
        pages_inspected=pages,
        final_careers_url=best.source_config.get("careers_url") or landing_url,
    )


def discover_ats_from_html(html: str, page_url: str) -> AtsDiscoveryResult:
    """Inspect a single page (legacy helper)."""
    return _result_from_candidates(
        collect_ats_candidates(html, page_url),
        [page_url],
        page_url,
    )


def discover_careers_site(
    client: httpx.Client,
    careers_url: str,
    *,
    max_follow: int = MAX_FOLLOW_LINKS,
) -> AtsDiscoveryResult:
    """Fetch landing page, follow top job-related links, detect ATS."""
    pages_inspected: list[str] = []
    combined_html: list[str] = []
    final_url = careers_url

    try:
        response = client.get(careers_url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        final_url = str(response.url)
        pages_inspected.append(final_url)
        combined_html.append(response.text)
    except Exception as exc:
        msg = f"Failed to fetch careers landing page: {exc}"
        return AtsDiscoveryResult(
            source_type="",
            source_config={},
            evidence=msg,
            reason=msg,
            fetch_failed=True,
            final_careers_url=careers_url,
        )

    follow_urls = extract_candidate_links(response.text, final_url, limit=max_follow * 3)[:max_follow]
    for link in follow_urls:
        if link in pages_inspected:
            continue
        try:
            sub = client.get(link, headers={"User-Agent": USER_AGENT})
            sub.raise_for_status()
            sub_url = str(sub.url)
            pages_inspected.append(sub_url)
            combined_html.append(sub.text)
        except Exception as exc:
            logger.debug("Skip follow link %s: %s", link, exc)

    all_candidates: list[ATSDiscoveryCandidate] = []
    for page_url, html in zip(pages_inspected, combined_html, strict=False):
        all_candidates.extend(collect_ats_candidates(html, page_url))

    return _result_from_candidates(all_candidates, pages_inspected, final_url)


def classify_discovery_bucket(result: AtsDiscoveryResult) -> str:
    """Map discovery result to summary bucket name."""
    if result.fetch_failed:
        return "errors"
    if result.supported and result.source_type in SUPPORTED_PROVIDERS:
        return "configured_supported"
    if result.provider_detected:
        return "detected_unsupported"
    return "still_unknown"


def format_company_discovery_line(result: AtsDiscoveryResult) -> str:
    bucket = classify_discovery_bucket(result)
    if bucket == "configured_supported":
        return f"configured supported source: {result.source_type}"
    if bucket == "detected_unsupported":
        return f"detected unsupported provider: {result.provider_detected}"
    if bucket == "errors":
        return f"error: {result.reason or result.evidence}"
    return f"still unknown: {result.reason or result.evidence}"


def format_discovery_result(company_name: str, careers_url: str, result: AtsDiscoveryResult) -> str:
    lines = [
        f"Company: {company_name}",
        f"Careers URL: {careers_url}",
        f"Pages inspected ({len(result.pages_inspected)}):",
    ]
    for page in result.pages_inspected[:8]:
        lines.append(f"  - {page}")
    if len(result.pages_inspected) > 8:
        lines.append(f"  ... and {len(result.pages_inspected) - 8} more")
    lines.append(f"confidence: {result.confidence}")
    lines.append(f"reason: {result.reason}")

    if result.supported and result.source_type in SUPPORTED_PROVIDERS:
        lines.append(f"source_type: {result.source_type}")
        lines.append(f"source_config_json: {json_dumps(result.source_config)}")
        lines.append("supported: yes (will enable after validation)")
    elif result.provider_detected:
        lines.append(f"provider_detected: {result.provider_detected}")
        lines.append(f"suggested_source_type: {result.suggested_source_type}")
        lines.append(f"source_type: {result.source_type}")
        lines.append("supported: no (scraper not implemented)")
    else:
        lines.append("provider_detected: none")
        lines.append("source_type: (leave empty / unconfigured)")
        lines.append("source_config_json: {}")
    return "\n".join(lines)
