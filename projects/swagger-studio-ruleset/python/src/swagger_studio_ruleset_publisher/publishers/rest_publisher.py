"""REST backend — direct HTTPS to the SwaggerHub Standardization API.

Endpoint mirrored from swaggerhub-cli's `saveSpectralRuleset` helper
(`src/requests/spectral.js`):

    PUT  /standardization/spectral-rulesets/{owner}/{rulesetName}/zip
    Content-Type: application/zip
    body: raw zip bytes (no multipart)
"""

from __future__ import annotations

from pathlib import Path

import httpx
import structlog

from swagger_studio_ruleset_publisher import packager
from swagger_studio_ruleset_publisher.config import Settings
from swagger_studio_ruleset_publisher.publishers.base import (
    Backend,
    PublishResult,
)

log = structlog.get_logger(__name__)


class RestPublisher:
    backend = Backend.REST

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def publish(self, ruleset_dir: Path, ruleset_slug: str) -> PublishResult:
        resolved = packager.validate(ruleset_dir)
        zip_path = packager.temp_zip_path(resolved)
        bundle = packager.package(resolved, zip_path)

        owner, name = _split_slug(ruleset_slug)
        path = f"/standardization/spectral-rulesets/{owner}/{name}/zip"

        log.info("rest_publishing", slug=ruleset_slug, zip=str(zip_path), path=path)

        try:
            zip_bytes = bundle.zip_path.read_bytes()
            async with self._client() as client:
                response = await client.put(
                    path,
                    content=zip_bytes,
                    headers={"Content-Type": "application/zip"},
                )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"SwaggerHub returned HTTP {response.status_code}: "
                    f"{response.text.strip()}"
                )
        finally:
            packager.cleanup(bundle)

        return PublishResult(
            ruleset_slug=ruleset_slug,
            backend=Backend.REST,
            studio_url=f"https://app.swaggerhub.com/standardization/{owner}/{name}",
            detail=f"HTTP {response.status_code}",
        )

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._settings.swaggerhub_base_url,
            timeout=self._settings.publisher_request_timeout_s,
            headers={
                "Authorization": self._settings.swaggerhub_api_key.get_secret_value(),
                "Accept": "application/json",
                "User-Agent": "api-foundation-ruleset-publisher/0.1",
            },
        )


def _split_slug(slug: str) -> tuple[str, str]:
    if "/" not in slug:
        return slug, slug
    owner, name = slug.split("/", 1)
    return owner, name
