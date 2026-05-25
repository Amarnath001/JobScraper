import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def validate_email_config() -> list[str]:
    """Return human-readable issues; empty list means config looks usable."""
    settings = get_settings()
    issues: list[str] = []

    if not (settings.resend_api_key or "").strip():
        issues.append("RESEND_API_KEY is missing or empty")
    if not (settings.email_from or "").strip():
        issues.append("EMAIL_FROM is missing or empty")
    if not (settings.email_to or "").strip():
        issues.append("EMAIL_TO is missing or empty")

    return issues


def log_email_config_warnings() -> None:
    """Log startup warnings for email; does not raise."""
    issues = validate_email_config()
    if not issues:
        settings = get_settings()
        logger.info(
            "Email config present: to=%s from=%s api_key_set=%s",
            settings.email_to,
            settings.email_from,
            bool((settings.resend_api_key or "").strip()),
        )
        return

    for issue in issues:
        logger.warning("Email config: %s — digest sends will fail until fixed", issue)
