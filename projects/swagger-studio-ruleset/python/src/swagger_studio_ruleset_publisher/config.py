"""Runtime configuration.

Reuses the scanner's shared `.env` so both sub-projects pull credentials
from one place. Resolution rule: walk up from this file to the repo root,
then look for `projects/swagger-studio-scanner/.env`.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _shared_env_path() -> Path:
    """Locate the shared scanner `.env` regardless of where the publisher runs."""
    # This file: projects/swagger-studio-ruleset/python/src/<pkg>/config.py
    # Repo root: 6 parents up
    here = Path(__file__).resolve()
    repo_root = here.parents[5]
    return repo_root / "projects" / "swagger-studio-scanner" / ".env"


class Settings(BaseSettings):
    """Strongly-typed settings sourced from env + the shared scanner .env file."""

    model_config = SettingsConfigDict(
        env_file=_shared_env_path(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    swaggerhub_api_key: SecretStr = Field(
        ..., description="Org-owner API key from app.swaggerhub.com/settings/apiKey"
    )
    swaggerhub_org: str = Field(..., description="Organization slug to publish to")
    swaggerhub_base_url: str = Field(default="https://api.swaggerhub.com")

    publisher_request_timeout_s: float = Field(default=30.0, gt=0)
    publisher_log_level: str = Field(default="INFO")


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
