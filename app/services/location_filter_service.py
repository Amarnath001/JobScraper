"""
Centralized US / remote-US location filtering for job ingest.
"""

from __future__ import annotations

import re
from enum import Enum

# --- Pattern groups (checked in classify order via helpers) ---

_INTERNATIONAL_REMOTE = re.compile(
    r"\bremote\s*[-–—]?\s*("
    r"emea|europe|eu\b|uk|united kingdom|canada|india|apac|asia|latam|"
    r"australia|japan|singapore|germany|france|ireland|netherlands|"
    r"middle east|africa|china|korea|mexico|brazil"
    r")\b",
    re.I,
)

_REMOTE_US_PHRASES = re.compile(
    r"\b("
    r"remote\s*us|us\s*remote|remote\s*usa|remote\s*,?\s*usa|"
    r"remote\s*[-–—,]\s*united states|united states\s*remote|"
    r"remote\s*in\s*(the\s+)?us|remote\s*in\s*(the\s+)?usa|"
    r"anywhere\s+in\s+(the\s+)?us|anywhere\s+in\s+(the\s+)?usa|"
    r"work\s+from\s+home\s*[-–—,]?\s*us|wfh\s*[-–—,]?\s*us|"
    r"us-?based\s+remote|remote\s*[-–—]\s*us\b"
    r")\b",
    re.I,
)

_PLAIN_REMOTE = re.compile(
    r"^(remote|work from home|wfh|distributed)(\s|$|[,;/|])",
    re.I,
)

_HYBRID_US = re.compile(
    r"\bhybrid\b",
    re.I,
)

_US_COUNTRY = re.compile(
    r"\b(united states|u\.?s\.?a\.?|u\.?s\.?\b|usa)\b",
    re.I,
)

_STATE_COMMA = re.compile(
    r",\s*([a-z]{2})\b",
    re.I,
)

_STATE_TOKEN = re.compile(
    r"\b([a-z]{2})\b",
    re.I,
)

_US_STATES = frozenset(
    {
        "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in",
        "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv",
        "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn",
        "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
    }
)

_US_STATE_NAMES = re.compile(
    r"\b("
    r"alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|"
    r"florida|georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|"
    r"maine|maryland|massachusetts|michigan|minnesota|mississippi|missouri|montana|"
    r"nebraska|nevada|new hampshire|new jersey|new mexico|new york|north carolina|"
    r"north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina|"
    r"south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|"
    r"wisconsin|wyoming|district of columbia"
    r")\b",
    re.I,
)

_INTERNATIONAL_MARKERS = re.compile(
    r"\b("
    # Countries / regions
    r"united kingdom|u\.?k\.?|england|scotland|wales|ireland|germany|france|spain|"
    r"italy|netherlands|holland|belgium|sweden|norway|denmark|finland|switzerland|"
    r"austria|poland|czech republic|portugal|greece|romania|hungary|ukraine|"
    r"canada|mexico|brazil|argentina|chile|colombia|"
    r"india|china|japan|korea|south korea|singapore|hong kong|taiwan|"
    r"australia|new zealand|israel|uae|dubai|saudi arabia|"
    r"emea|apac|latam|europe|european union|\beu\b|middle east|africa|"
    # Cities (non-US hubs)
    r"london|berlin|munich|frankfurt|hamburg|paris|lyon|dublin|cork|"
    r"amsterdam|rotterdam|stockholm|oslo|copenhagen|helsinki|zurich|geneva|"
    r"vienna|warsaw|prague|lisbon|madrid|barcelona|milan|rome|"
    r"toronto|vancouver|montreal|ottawa|calgary|edmonton|winnipeg|"
    r"mumbai|bangalore|bengaluru|hyderabad|delhi|new delhi|pune|chennai|"
    r"singapore|tokyo|osaka|seoul|sydney|melbourne|brisbane|auckland|"
    r"tel aviv|dubai|hong kong"
    r")\b",
    re.I,
)

_US_CITIES = re.compile(
    r"\b("
    r"san francisco|sf\b|oakland|san jose|palo alto|mountain view|sunnyvale|"
    r"menlo park|redwood city|los angeles|la\b|santa monica|pasadena|"
    r"san diego|sacramento|irvine|"
    r"new york|nyc|manhattan|brooklyn|queens|jersey city|hoboken|"
    r"new york city|"
    r"seattle|bellevue|redmond|kirkland|"
    r"austin|dallas|houston|san antonio|plano|"
    r"boston|cambridge\b|"
    r"chicago|denver|boulder|phoenix|scottsdale|tempe|"
    r"portland\b|atlanta|miami|orlando|tampa|"
    r"philadelphia|pittsburgh|detroit|ann arbor|minneapolis|"
    r"raleigh|durham|charlotte|nashville|salt lake city|"
    r"washington\b|dc\b|arlington|alexandria|bethesda|"
    r"las vegas|reno|honolulu|"
    r"remote/san francisco|remote/nyc"
    r")\b",
    re.I,
)

_SEGMENT_SPLIT = re.compile(r"\s*[|;/]\s*|\s+or\s+|\s+and\s+", re.I)


class LocationCategory(str, Enum):
    US = "US"
    REMOTE_US = "REMOTE_US"
    INTERNATIONAL = "INTERNATIONAL"
    UNKNOWN = "UNKNOWN"


def normalize_location(location: str | None) -> str:
    if not location:
        return ""
    return " ".join(str(location).lower().strip().split())


def _split_segments(normalized: str) -> list[str]:
    if not normalized:
        return [""]
    parts = _SEGMENT_SPLIT.split(normalized)
    return [p.strip() for p in parts if p.strip()] or [normalized]


def _has_us_state_abbr(text: str) -> bool:
    for match in _STATE_COMMA.finditer(text):
        if match.group(1).lower() in _US_STATES:
            return True
    tokens = text.replace(",", " ").split()
    for i, token in enumerate(tokens):
        t = re.sub(r"[^a-z]", "", token.lower())
        if t in _US_STATES and (i == 0 or tokens[i - 1] not in {"in", "of"}):
            return True
    return False


def _classify_segment(segment: str) -> LocationCategory:
    if not segment:
        return LocationCategory.UNKNOWN

    if _INTERNATIONAL_REMOTE.search(segment) or _INTERNATIONAL_MARKERS.search(segment):
        return LocationCategory.INTERNATIONAL

    if _REMOTE_US_PHRASES.search(segment):
        return LocationCategory.REMOTE_US

    if _PLAIN_REMOTE.search(segment) and not _INTERNATIONAL_MARKERS.search(segment):
        return LocationCategory.REMOTE_US

    if _US_COUNTRY.search(segment) or _US_STATE_NAMES.search(segment) or _has_us_state_abbr(segment):
        return LocationCategory.US

    if _US_CITIES.search(segment):
        return LocationCategory.US

    if _HYBRID_US.search(segment) and (
        _US_CITIES.search(segment)
        or _has_us_state_abbr(segment)
        or _US_STATE_NAMES.search(segment)
        or _US_COUNTRY.search(segment)
    ):
        return LocationCategory.US

    if re.search(r"\bremote\b", segment, re.I) and not _INTERNATIONAL_MARKERS.search(segment):
        return LocationCategory.REMOTE_US

    if re.search(r"\b(hybrid|onsite|on-site|in-office)\b", segment, re.I):
        if (
            _US_CITIES.search(segment)
            or _has_us_state_abbr(segment)
            or _US_STATE_NAMES.search(segment)
            or _US_COUNTRY.search(segment)
        ):
            return LocationCategory.US
        if _INTERNATIONAL_MARKERS.search(segment):
            return LocationCategory.INTERNATIONAL

    return LocationCategory.UNKNOWN


def classify_location(location: str | None) -> LocationCategory:
    normalized = normalize_location(location)
    if not normalized:
        return LocationCategory.UNKNOWN

    categories = [_classify_segment(seg) for seg in _split_segments(normalized)]

    if LocationCategory.INTERNATIONAL in categories:
        return LocationCategory.INTERNATIONAL

    accepted = {LocationCategory.US, LocationCategory.REMOTE_US}
    if not any(c in accepted for c in categories):
        return LocationCategory.UNKNOWN

    if any(c == LocationCategory.UNKNOWN for c in categories):
        return LocationCategory.UNKNOWN

    if LocationCategory.US in categories:
        return LocationCategory.US
    return LocationCategory.REMOTE_US


def is_us_or_remote(location: str | None) -> bool:
    return classify_location(location) in {LocationCategory.US, LocationCategory.REMOTE_US}
