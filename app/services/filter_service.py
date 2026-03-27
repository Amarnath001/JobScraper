import re
from dataclasses import dataclass

# Weights — tune without changing call sites
POSITIVE_WEIGHT = 2.0
NEGATIVE_WEIGHT = 3.0
ENTRY_LEVEL_THRESHOLD = 0.0

POSITIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("software engineer i", re.compile(r"\bsoftware\s+engineer\s+i\b", re.I)),
    ("swe i", re.compile(r"\bswe\s+i\b", re.I)),
    ("new grad", re.compile(r"\bnew\s+grad\b", re.I)),
    ("new graduate", re.compile(r"\bnew\s+graduate\b", re.I)),
    ("university grad", re.compile(r"\buniversity\s+grad(uate)?\b", re.I)),
    ("entry level", re.compile(r"\bentry[\s-]level\b", re.I)),
    ("early career", re.compile(r"\bearly\s+career\b", re.I)),
    ("associate software engineer", re.compile(r"\bassociate\s+software\s+engineer\b", re.I)),
    ("junior software engineer", re.compile(r"\bjunior\s+software\s+engineer\b", re.I)),
    ("0-2 years", re.compile(r"\b0[\s-]2\s+years?\b", re.I)),
    ("bachelor's degree required", re.compile(r"bachelor'?s?\s+degree\s+required", re.I)),
    ("bachelor's degree preferred", re.compile(r"bachelor'?s?\s+degree\s+preferred", re.I)),
    ("campus", re.compile(r"\bcampus\b", re.I)),
    ("l3 new grad", re.compile(r"\bl\d+\s+new\s+grad\b", re.I)),
]

NEGATIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
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


@dataclass(frozen=True)
class EntryLevelScoreResult:
    score: float
    is_entry_level: bool
    matched_positive: list[str]
    matched_negative: list[str]


def _combine_text(title: str, description: str | None, level: str | None) -> str:
    parts = [title]
    if level:
        parts.append(level)
    if description:
        parts.append(description)
    return "\n".join(parts)


def score_entry_level(title: str, description_text: str | None, level: str | None) -> EntryLevelScoreResult:
    text = _combine_text(title, description_text, level)
    matched_positive: list[str] = []
    matched_negative: list[str] = []

    for label, pattern in POSITIVE_PATTERNS:
        if pattern.search(text):
            matched_positive.append(label)

    for label, pattern in NEGATIVE_PATTERNS:
        if pattern.search(text):
            matched_negative.append(label)

    score = len(matched_positive) * POSITIVE_WEIGHT - len(matched_negative) * NEGATIVE_WEIGHT
    is_el = score > ENTRY_LEVEL_THRESHOLD

    return EntryLevelScoreResult(
        score=score,
        is_entry_level=is_el,
        matched_positive=matched_positive,
        matched_negative=matched_negative,
    )
