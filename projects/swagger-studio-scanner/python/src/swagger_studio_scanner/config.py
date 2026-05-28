"""Runtime configuration loaded from environment + .env file.

Centralizing config here keeps the rest of the code pure: handlers and the
HTTP client take a typed `Settings` object rather than reaching into os.environ.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed settings sourced from env + the sibling `.env` file."""

    model_config = SettingsConfigDict(
        # The .env lives one directory above (shared between python/ and typescript/).
        env_file=(Path(__file__).resolve().parents[3] / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    swaggerhub_api_key: SecretStr = Field(
        ..., description="Org-owner read key from app.swaggerhub.com/settings/apiKey"
    )
    swaggerhub_org: str = Field(..., description="Organization (owner) slug to scan")
    swaggerhub_base_url: str = Field(
        default="https://api.swaggerhub.com",
        description="SaaS base URL. Override only for on-prem.",
    )

    scanner_concurrency: int = Field(default=8, ge=1, le=64)
    scanner_request_timeout_s: float = Field(default=30.0, gt=0)
    scanner_log_level: str = Field(default="INFO")


def load_settings() -> Settings:
    """Return a fresh Settings instance. Cheap; do not cache across tests."""
    return Settings()  # type: ignore[call-arg]
