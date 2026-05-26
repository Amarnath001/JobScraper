import re
from dataclasses import dataclass

# Entry-level scoring — tune without changing call sites
ENTRY_POSITIVE_WEIGHT = 2.0
ENTRY_NEGATIVE_WEIGHT = 3.0
ENTRY_LEVEL_THRESHOLD = 0.0

ENTRY_LEVEL_POSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("new grad", re.compile(r"\bnew\s+grad\b", re.I)),
    ("new graduate", re.compile(r"\bnew\s+graduate\b", re.I)),
    ("university grad", re.compile(r"\buniversity\s+grad(uate)?\b", re.I)),
    ("entry level", re.compile(r"\bentry[\s-]level\b", re.I)),
    ("early career", re.compile(r"\bearly\s+career\b", re.I)),
    ("associate software engineer", re.compile(r"\bassociate\s+software\s+engineer\b", re.I)),
    ("junior software engineer", re.compile(r"\bjunior\s+software\s+engineer\b", re.I)),
    ("software engineer i", re.compile(r"\bsoftware\s+engineer\s+i\b", re.I)),
    ("engineer i", re.compile(r"\bengineer\s+i\b", re.I)),
    ("swe i", re.compile(r"\bswe\s+i\b", re.I)),
    ("0-2 years", re.compile(r"\b0[\s-]2\s+years?\b", re.I)),
    ("bachelor's degree required", re.compile(r"bachelor'?s?\s+degree\s+required", re.I)),
    ("bachelor's degree preferred", re.compile(r"bachelor'?s?\s+degree\s+preferred", re.I)),
    ("campus", re.compile(r"\bcampus\b", re.I)),
    ("l3 new grad", re.compile(r"\bl\d+\s+new\s+grad\b", re.I)),
    ("intern", re.compile(r"\bintern\b", re.I)),
]

ENTRY_LEVEL_NEGATIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("senior", re.compile(r"\bsenior\b", re.I)),
    ("staff", re.compile(r"\bstaff\b", re.I)),
    ("principal", re.compile(r"\bprincipal\b", re.I)),
    ("manager", re.compile(r"\bmanager\b", re.I)),
    ("lead", re.compile(r"\blead\b", re.I)),
    ("director", re.compile(r"\bdirector\b", re.I)),
    ("architect", re.compile(r"\barchitect\b", re.I)),
    ("5+ years", re.compile(r"\b5\s*\+\s*years?\b", re.I)),
    ("7+ years", re.compile(r"\b7\s*\+\s*years?\b", re.I)),
    ("10+ years", re.compile(r"\b10\s*\+\s*years?\b", re.I)),
]

# Strong SWE role indicators (title-focused; description as fallback)
SOFTWARE_POSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("software engineer", re.compile(r"\bsoftware\s+engineer\b", re.I)),
    ("software developer", re.compile(r"\bsoftware\s+developer\b", re.I)),
    ("backend engineer", re.compile(r"\bbackend\s+engineer\b", re.I)),
    ("frontend engineer", re.compile(r"\bfrontend\s+engineer\b", re.I)),
    ("full stack engineer", re.compile(r"\bfull[\s-]stack\s+engineer\b", re.I)),
    ("full-stack engineer", re.compile(r"\bfull[\s-]stack\s+engineer\b", re.I)),
    ("infrastructure engineer", re.compile(r"\binfrastructure\s+engineer\b", re.I)),
    ("platform engineer", re.compile(r"\bplatform\s+engineer\b", re.I)),
    ("systems engineer", re.compile(r"\bsystems?\s+engineer\b", re.I)),
    ("site reliability engineer", re.compile(r"\bsite\s+reliability\s+engineer\b", re.I)),
    ("sre", re.compile(r"\bsre\b", re.I)),
    ("devops engineer", re.compile(r"\bdevops\s+engineer\b", re.I)),
    ("cloud engineer", re.compile(r"\bcloud\s+engineer\b", re.I)),
    ("machine learning engineer", re.compile(r"\bmachine\s+learning\s+engineer\b", re.I)),
    ("ml engineer", re.compile(r"\bml\s+engineer\b", re.I)),
    ("data engineer", re.compile(r"\bdata\s+engineer\b", re.I)),
    ("ai engineer", re.compile(r"\bai\s+engineer\b", re.I)),
    ("security engineer", re.compile(r"\bsecurity\s+engineer\b", re.I)),
    ("mobile engineer", re.compile(r"\bmobile\s+engineer\b", re.I)),
    ("android engineer", re.compile(r"\bandroid\s+engineer\b", re.I)),
    ("ios engineer", re.compile(r"\bios\s+engineer\b", re.I)),
    ("firmware engineer", re.compile(r"\bfirmware\s+engineer\b", re.I)),
    ("embedded engineer", re.compile(r"\bembedded\s+engineer\b", re.I)),
    ("frontend software engineer", re.compile(r"\bfrontend\s+software\s+engineer\b", re.I)),
    ("associate software engineer", re.compile(r"\bassociate\s+software\s+engineer\b", re.I)),
    ("junior software engineer", re.compile(r"\bjunior\s+software\s+engineer\b", re.I)),
]

# Overrides non-SWE negatives when present in title (strict phrases only)
EXPLICIT_SWE_TITLE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("software engineer", re.compile(r"\bsoftware\s+engineer\b", re.I)),
    ("software developer", re.compile(r"\bsoftware\s+developer\b", re.I)),
    ("frontend software engineer", re.compile(r"\bfrontend\s+software\s+engineer\b", re.I)),
]

NON_SOFTWARE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("sales", re.compile(r"\bsales\b", re.I)),
    ("sales development", re.compile(r"\bsales\s+development\b", re.I)),
    ("account executive", re.compile(r"\baccount\s+executive\b", re.I)),
    ("account manager", re.compile(r"\baccount\s+manager\b", re.I)),
    ("customer success", re.compile(r"\bcustomer\s+success\b", re.I)),
    ("business development", re.compile(r"\bbusiness\s+development\b", re.I)),
    ("business analyst", re.compile(r"\bbusiness\s+analyst\b", re.I)),
    ("marketing", re.compile(r"\bmarketing\b", re.I)),
    ("product manager", re.compile(r"\bproduct\s+manager\b", re.I)),
    ("project manager", re.compile(r"\bproject\s+manager\b", re.I)),
    ("program manager", re.compile(r"\bprogram\s+manager\b", re.I)),
    ("recruiter", re.compile(r"\brecruiter\b", re.I)),
    ("talent", re.compile(r"\btalent\b", re.I)),
    ("finance", re.compile(r"\bfinance\b", re.I)),
    ("legal", re.compile(r"\blegal\b", re.I)),
    ("operations", re.compile(r"\boperations\b", re.I)),
    ("hr", re.compile(r"\bhr\b", re.I)),
    ("human resources", re.compile(r"\bhuman\s+resources\b", re.I)),
    ("people", re.compile(r"\bpeople\b", re.I)),
    ("design", re.compile(r"\bdesign\b", re.I)),
    ("content", re.compile(r"\bcontent\b", re.I)),
    ("support", re.compile(r"\bsupport\b", re.I)),
    ("solutions consultant", re.compile(r"\bsolutions\s+consultant\b", re.I)),
    ("sales engineer", re.compile(r"\bsales\s+engineer\b", re.I)),
    ("customer engineer", re.compile(r"\bcustomer\s+engineer\b", re.I)),
]


@dataclass(frozen=True)
class EntryLevelScoreResult:
    score: float
    is_entry_level: bool
    matched_positive: list[str]
    matched_negative: list[str]


@dataclass(frozen=True)
class JobFilterResult:
    is_software_engineering_related: bool
    is_entry_level_related: bool
    software_indicators_matched: list[str]
    non_software_indicators_matched: list[str]
    entry_level_indicators_matched: list[str]
    entry_level_negative_matched: list[str]
    entry_level_score: float
    rejection_reason: str | None = None

    @property
    def is_entry_level(self) -> bool:
        return self.is_entry_level_related

    @property
    def is_digest_eligible(self) -> bool:
        return self.is_software_engineering_related and self.is_entry_level_related


def _combine_text(title: str, description: str | None, level: str | None) -> str:
    parts = [title]
    if level:
        parts.append(level)
    if description:
        parts.append(description)
    return "\n".join(parts)


def _match_patterns(
    patterns: list[tuple[str, re.Pattern[str]]],
    text: str,
) -> list[str]:
    return [label for label, pattern in patterns if pattern.search(text)]


def classify_software_engineering(title: str, description_text: str | None, level: str | None) -> tuple[bool, list[str], list[str], str | None]:
    """Return (is_swe, software_matched, non_software_matched, rejection_reason)."""
    title_text = title or ""
    full_text = _combine_text(title, description_text, level)

    non_software_title = _match_patterns(NON_SOFTWARE_PATTERNS, title_text)
    explicit_swe_title = _match_patterns(EXPLICIT_SWE_TITLE_PATTERNS, title_text)

    if non_software_title and not explicit_swe_title:
        return False, [], non_software_title, "non_software_role_in_title"

    software_title = _match_patterns(SOFTWARE_POSITIVE_PATTERNS, title_text)
    if software_title:
        return True, software_title, non_software_title, None

    software_full = _match_patterns(SOFTWARE_POSITIVE_PATTERNS, full_text)
    if software_full:
        return True, software_full, non_software_title, None

    return False, [], non_software_title, "no_software_engineering_indicators"


def score_entry_level(title: str, description_text: str | None, level: str | None) -> EntryLevelScoreResult:
    text = _combine_text(title, description_text, level)
    matched_positive = _match_patterns(ENTRY_LEVEL_POSITIVE_PATTERNS, text)
    matched_negative = _match_patterns(ENTRY_LEVEL_NEGATIVE_PATTERNS, text)

    score = len(matched_positive) * ENTRY_POSITIVE_WEIGHT - len(matched_negative) * ENTRY_NEGATIVE_WEIGHT
    is_el = score > ENTRY_LEVEL_THRESHOLD

    return EntryLevelScoreResult(
        score=score,
        is_entry_level=is_el,
        matched_positive=matched_positive,
        matched_negative=matched_negative,
    )


def classify_job(title: str, description_text: str | None, level: str | None) -> JobFilterResult:
    """Classify SWE relevance and entry-level independently."""
    entry = score_entry_level(title, description_text, level)
    is_swe, software_matched, non_software_matched, swe_reason = classify_software_engineering(
        title, description_text, level
    )

    rejection_reason: str | None = None
    if not is_swe:
        rejection_reason = swe_reason
    elif not entry.is_entry_level:
        rejection_reason = "not_entry_level"

    return JobFilterResult(
        is_software_engineering_related=is_swe,
        is_entry_level_related=entry.is_entry_level,
        software_indicators_matched=software_matched,
        non_software_indicators_matched=non_software_matched,
        entry_level_indicators_matched=entry.matched_positive,
        entry_level_negative_matched=entry.matched_negative,
        entry_level_score=entry.score,
        rejection_reason=rejection_reason,
    )
