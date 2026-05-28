"""Async HTTP client for the SwaggerHub REST API.

A thin, typed wrapper over httpx. Owns auth, base URL, timeouts, and
concurrency control. Anything that needs to talk to Studio goes through
this class so retry/backoff/rate-limit policy lives in exactly one place.
"""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any, Self

import httpx
import structlog

from swagger_studio_scanner.config import Settings

log = structlog.get_logger(__name__)


class SwaggerHubClient:
    """Async client for SwaggerHub's public REST API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._semaphore = asyncio.Semaphore(settings.scanner_concurrency)
        self._client = httpx.AsyncClient(
            base_url=settings.swaggerhub_base_url,
            timeout=settings.scanner_request_timeout_s,
            headers={
                "Authorization": settings.swaggerhub_api_key.get_secret_value(),
                "Accept": "application/json",
                "User-Agent": "api-foundation-swagger-studio-scanner/0.1",
            },
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_json(self, path: str, **params: Any) -> dict[str, Any]:
        """GET a JSON resource, throttled by the concurrency semaphore."""
        async with self._semaphore:
            response = await self._client.get(path, params=params or None)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
