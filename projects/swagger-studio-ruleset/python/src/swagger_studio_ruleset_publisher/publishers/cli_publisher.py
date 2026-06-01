"""CLI backend — shells out to `swaggerhub spectral:upload`.

Reliable default. Requires `swaggerhub-cli` on PATH (installed in the
devcontainer). For environments where it's not available, use the REST
backend instead.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from swagger_studio_ruleset_publisher import packager
from swagger_studio_ruleset_publisher.config import Settings
from swagger_studio_ruleset_publisher.publishers.base import (
    Backend,
    PublishResult,
)

log = structlog.get_logger(__name__)


class CliPublisher:
    backend = Backend.CLI

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def publish(self, ruleset_dir: Path, ruleset_slug: str) -> PublishResult:
        resolved = packager.validate(ruleset_dir)

        if not packager.has_swaggerhub_cli():
            raise RuntimeError(
                "swaggerhub-cli not on PATH. "
                "Install via `npm i -g swaggerhub-cli` or use --backend rest."
            )

        # Flatten extends before handing off — Studio shouldn't have to resolve
        # relative `./rules/*.yaml` references. Same artifact REST backend ships.
        flattened_dir = packager.write_flattened_dir(resolved)
        log.info(
            "cli_publishing",
            slug=ruleset_slug,
            source_dir=str(resolved),
            flattened_dir=str(flattened_dir),
        )

        try:
            env = {
                "SWAGGERHUB_API_KEY": self._settings.swaggerhub_api_key.get_secret_value(),
                "PATH": _system_path(),
            }
            proc = await asyncio.create_subprocess_exec(
                "swaggerhub",
                "spectral:upload",
                ruleset_slug,
                str(flattened_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        finally:
            import shutil
            shutil.rmtree(flattened_dir, ignore_errors=True)

        if proc.returncode != 0:
            raise RuntimeError(
                f"swaggerhub spectral:upload failed (exit {proc.returncode}):\n"
                f"{stderr.decode(errors='replace').strip() or stdout.decode(errors='replace').strip()}"
            )

        owner = ruleset_slug.split("/", 1)[0]
        ruleset_name = ruleset_slug.split("/", 1)[1] if "/" in ruleset_slug else ruleset_slug
        return PublishResult(
            ruleset_slug=ruleset_slug,
            backend=Backend.CLI,
            studio_url=f"https://app.swaggerhub.com/standardization/{owner}/{ruleset_name}",
            detail=stdout.decode(errors="replace").strip() or "uploaded",
        )


def _system_path() -> str:
    """Pass through the parent PATH so the subprocess can find `swaggerhub`."""
    import os
    return os.environ.get("PATH", "")
