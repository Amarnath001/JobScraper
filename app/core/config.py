from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(..., alias="DATABASE_URL")
    resend_api_key: str = Field(default="", alias="RESEND_API_KEY")
    email_from: str = Field(default="jobs@example.com", alias="EMAIL_FROM")
    email_to: str = Field(default="", alias="EMAIL_TO")
    send_empty_digest: bool = Field(default=False, alias="SEND_EMPTY_DIGEST")
    timezone: str = Field(default="America/Los_Angeles", alias="TIMEZONE")
    playwright_headless: bool = Field(default=True, alias="PLAYWRIGHT_HEADLESS")
    scrape_timeout_seconds: float = Field(default=60.0, alias="SCRAPE_TIMEOUT_SECONDS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    enable_scheduler: bool = Field(default=True, alias="ENABLE_SCHEDULER")
    digest_lookback_hours: int | None = Field(default=None, alias="DIGEST_LOOKBACK_HOURS")
    us_only_mode: bool = Field(default=True, alias="US_ONLY_MODE")
    generic_playwright_enabled: bool = Field(default=True, alias="GENERIC_PLAYWRIGHT_ENABLED")
    generic_playwright_max_companies_per_run: int = Field(
        default=25,
        alias="GENERIC_PLAYWRIGHT_MAX_COMPANIES_PER_RUN",
    )
    generic_playwright_max_pages_per_company: int = Field(
        default=5,
        alias="GENERIC_PLAYWRIGHT_MAX_PAGES_PER_COMPANY",
    )
    generic_playwright_timeout_seconds: float = Field(
        default=45.0,
        alias="GENERIC_PLAYWRIGHT_TIMEOUT_SECONDS",
    )

    @field_validator("digest_lookback_hours", mode="before")
    @classmethod
    def _empty_digest_lookback(cls, value: Any) -> Any:
        if value == "" or value is None:
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
