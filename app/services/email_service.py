import logging
from dataclasses import dataclass
from typing import Any

import resend

from app.core.config import get_settings
from app.core.email_validation import validate_email_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailSendResult:
    ok: bool
    provider_id: str | None = None
    error: str | None = None


def _extract_provider_id(response: Any) -> str | None:
    if response is None:
        return None
    if isinstance(response, dict):
        err = response.get("error")
        if err:
            return None
        pid = response.get("id")
        return str(pid) if pid else None
    pid = getattr(response, "id", None)
    if pid:
        return str(pid)
    data = getattr(response, "data", None)
    if data is not None:
        return _extract_provider_id(data)
    return None


def _extract_error_message(response: Any) -> str | None:
    if response is None:
        return "Resend returned no response"
    if isinstance(response, dict):
        err = response.get("error")
        if err:
            if isinstance(err, dict):
                return err.get("message") or str(err)
            return str(err)
        if not response.get("id"):
            return f"Unexpected Resend response: {response!r}"
        return None
    err = getattr(response, "error", None)
    if err:
        return str(err)
    if _extract_provider_id(response):
        return None
    return f"Unexpected Resend response type: {type(response).__name__}"


class EmailService:
    def __init__(self) -> None:
        settings = get_settings()
        self._from = (settings.email_from or "").strip()
        self._api_key = (settings.resend_api_key or "").strip()
        self._default_to = (settings.email_to or "").strip()
        self.last_error: str | None = None

    def _config_ready(self) -> tuple[bool, str]:
        issues = validate_email_config()
        if issues:
            return False, "; ".join(issues)
        return True, ""

    def _send(
        self,
        *,
        to_email: str,
        subject: str,
        html: str,
        text: str,
        job_count: int | None = None,
    ) -> EmailSendResult:
        self.last_error = None
        ready, reason = self._config_ready()
        if not ready:
            self.last_error = reason
            logger.error(
                "Email send aborted (config): to=%r from=%r subject=%r jobs=%s reason=%s",
                to_email,
                self._from,
                subject,
                job_count,
                reason,
            )
            return EmailSendResult(ok=False, error=reason)

        logger.info(
            "Sending email: to=%s from=%s subject=%r jobs_in_digest=%s",
            to_email,
            self._from,
            subject,
            job_count,
        )

        resend.api_key = self._api_key
        params: dict[str, Any] = {
            "from": self._from,
            "to": [to_email],
            "subject": subject,
            "html": html,
            "text": text,
        }

        try:
            response = resend.Emails.send(params)
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception(
                "Email provider raised: to=%s from=%s subject=%r jobs=%s",
                to_email,
                self._from,
                subject,
                job_count,
            )
            return EmailSendResult(ok=False, error=self.last_error)

        provider_id = _extract_provider_id(response)
        err_msg = _extract_error_message(response)

        if provider_id:
            logger.info(
                "Email accepted by provider: to=%s from=%s subject=%r jobs=%s provider_id=%s",
                to_email,
                self._from,
                subject,
                job_count,
                provider_id,
            )
            return EmailSendResult(ok=True, provider_id=provider_id)

        self.last_error = err_msg or "Resend did not return a message id"
        logger.error(
            "Email rejected or incomplete response: to=%s from=%s subject=%r jobs=%s "
            "provider_response=%r error=%s",
            to_email,
            self._from,
            subject,
            job_count,
            response,
            self.last_error,
        )
        return EmailSendResult(ok=False, error=self.last_error)

    def send_daily_digest(
        self,
        *,
        to_email: str,
        subject: str,
        html: str,
        text: str,
        job_count: int = 0,
    ) -> bool:
        result = self._send(
            to_email=to_email,
            subject=subject,
            html=html,
            text=text,
            job_count=job_count,
        )
        return result.ok

    def send_no_jobs_email(self, *, to_email: str) -> bool:
        subject = "Job Scraper — no new entry-level jobs today"
        html = "<p>No new entry-level software engineering jobs were discovered today.</p>"
        text = "No new entry-level software engineering jobs were discovered today."
        return self.send_daily_digest(
            to_email=to_email,
            subject=subject,
            html=html,
            text=text,
            job_count=0,
        )

    def send_test_email(self) -> EmailSendResult:
        to_email = self._default_to
        if not to_email:
            msg = "EMAIL_TO is missing or empty"
            logger.error("Test email aborted: %s", msg)
            return EmailSendResult(ok=False, error=msg)

        subject = "Job Scraper — test email"
        html = "<p>If you received this, Resend accepted the message from Job Scraper.</p>"
        text = "If you received this, Resend accepted the message from Job Scraper."
        return self._send(
            to_email=to_email,
            subject=subject,
            html=html,
            text=text,
            job_count=None,
        )
