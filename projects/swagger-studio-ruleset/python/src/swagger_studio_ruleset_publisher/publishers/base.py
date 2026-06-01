"""Publisher protocol — every backend honours this surface."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class Backend(StrEnum):
    CLI = "cli"
    REST = "rest"


@dataclass(frozen=True)
class PublishResult:
    """What a publisher returns on success — caller decides how to display it."""

    ruleset_slug: str
    backend: Backend
    studio_url: str
    detail: str


class Publisher(Protocol):
    """Contract for any publishing backend."""

    backend: Backend

    async def publish(self, ruleset_dir: Path, ruleset_slug: str) -> PublishResult:
        """Upload the ruleset directory to Studio under `ruleset_slug`.

        Args:
            ruleset_dir: Absolute path to a directory containing spectral.yaml.
            ruleset_slug: "{owner}/{rulesetName}" — typically owner/openapi-3-0-active.

        Raises:
            FileNotFoundError: If the directory or spectral.yaml is missing.
            RuntimeError: On any backend-specific failure (CLI non-zero exit,
                non-2xx HTTP). The wrapped exception carries the detail.
        """
        ...
