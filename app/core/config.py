from functools import lru_cache

from pydantic import Field
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
