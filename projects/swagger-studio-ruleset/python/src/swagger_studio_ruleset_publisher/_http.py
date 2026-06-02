"""Shared HTTPS client factory.

All Studio-touching modules (activator, deleter, lister, puller) use the
same auth, base URL, timeout, and user agent. Centralizing the factory
keeps drift from creeping in across modules.
"""

from __future__ import annotations

import httpx

from swagger_studio_ruleset_publisher.config import Settings


def create_client(settings: Settings, accept: str = "application/json") -> httpx.AsyncClient:
    """Build an httpx.AsyncClient configured for the SwaggerHub Standardization API.

    `accept` is overridable so binary fetchers (puller) can request `application/zip`.
    """
    return httpx.AsyncClient(
        base_url=settings.swaggerhub_base_url,
        timeout=settings.publisher_request_timeout_s,
        headers={
            "Authorization": settings.swaggerhub_api_key.get_secret_value(),
            "Accept": accept,
            "User-Agent": "api-foundation-ruleset-publisher/0.1",
        },
    )
