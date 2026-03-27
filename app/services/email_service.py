import logging

import resend

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self) -> None:
        settings = get_settings()
        self._from = settings.email_from
        self._api_key = settings.resend_api_key

    def send_daily_digest(self, *, to_email: str, subject: str, html: str, text: str) -> bool:
        if not self._api_key:
            logger.warning("RESEND_API_KEY not set; skipping email send")
            return False
        resend.api_key = self._api_key
        try:
            params: dict = {
                "from": self._from,
                "to": [to_email],
                "subject": subject,
                "html": html,
                "text": text,
            }
            resend.Emails.send(params)
            return True
        except Exception as e:
            logger.exception("Failed to send digest email: %s", e)
            raise

    def send_no_jobs_email(self, *, to_email: str) -> bool:
        settings = get_settings()
        subject = "Job Scraper — no new entry-level jobs today"
        html = "<p>No new entry-level software engineering jobs were discovered today.</p>"
        text = "No new entry-level software engineering jobs were discovered today."
        return self.send_daily_digest(to_email=to_email, subject=subject, html=html, text=text)
