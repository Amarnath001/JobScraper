import re
import unicodedata


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def normalize_for_fingerprint(value: str | None) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = text.lower().strip()
    text = normalize_whitespace(text)
    return text
