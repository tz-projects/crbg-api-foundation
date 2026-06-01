"""Async HTTP client for the SwaggerHub REST API.

A thin, typed wrapper over httpx. Single responsibility: own auth, base URL,
timeouts, and concurrency, and expose a typed surface for the endpoints the
scanner needs. All payload interpretation lives in :mod:`parsers` — that
separation keeps the wire-shape grammar in one place and lets us unit-test
adapters without a network.

Three high-level operations:

- :py:meth:`SwaggerHubClient.list_api_versions` — yields :class:`ListedApi`
  (identity + descriptive metadata) for every API version under an org.
- :py:meth:`SwaggerHubClient.get_findings` — fetches and parses standardization
  findings for one API version, using the injected :class:`FindingParser`.
- :py:meth:`SwaggerHubClient.get_active_ruleset` — returns the active org
  ruleset metadata if Studio exposes it; returns ``None`` (not raises) when
  the endpoint is unavailable or returns nothing recognizable.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import httpx
import structlog

from .config import Settings
from .models import ApiMeta, ApiRef, Finding, RulesetMeta
from .parsers import (
    DEFAULT_FINDING_PARSER,
    FindingParser,
    extract_api_items,
    extract_api_meta,
    extract_api_ref,
    parse_ruleset_payload,
)

log = structlog.get_logger(__name__)

_PAGE_SIZE = 100


@dataclass(frozen=True)
class ListedApi:
    """One row of the ``/apis/{owner}`` listing after parsing.

    Bundles identity (:class:`ApiRef`) with descriptive metadata
    (:class:`ApiMeta`) so the scanner can carry both forward without
    re-parsing.
    """

    ref: ApiRef
    meta: ApiMeta


class SwaggerHubClient:
    """Async client for SwaggerHub's public REST API."""

    def __init__(
        self,
        settings: Settings,
        finding_parser: FindingParser = DEFAULT_FINDING_PARSER,
    ) -> None:
        self._settings = settings
        self._finding_parser = finding_parser
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

    # --- High-level operations ----------------------------------------------

    async def list_api_versions(self, owner: str) -> AsyncIterator[ListedApi]:
        """Yield identity + metadata for every API version under ``owner``."""
        page = 0
        while True:
            data = await self.get_json(f"/apis/{owner}", page=page, limit=_PAGE_SIZE)
            items = extract_api_items(data)
            if not items:
                return
            for item in items:
                ref = extract_api_ref(item)
                if ref is None:
                    continue
                yield ListedApi(ref=ref, meta=extract_api_meta(item))
            if len(items) < _PAGE_SIZE:
                return
            page += 1

    async def get_findings(self, api: ApiRef) -> list[Finding]:
        """Fetch and parse standardization findings for one API version.

        Response shape (confirmed against ``swaggerhub-cli``'s
        ``api/validate``):

            ``{"validation": [{rule, severity, description, line, ...}, ...]}``

        Empty result can mean *clean* OR *tier doesn't include Governance*
        (the silent failure mode flagged in the context doc) — the caller
        decides what to do with empty results, based on the probe outcome.
        """
        path = f"/apis/{api.owner}/{api.name}/{api.version}/standardization"
        data = await self.get_json(path)
        raw = (
            data.get("validation")
            or data.get("standardization")
            or data.get("findings")
            or []
        )
        if not isinstance(raw, list):
            return []
        return [self._finding_parser.parse(e) for e in raw if isinstance(e, dict)]

    async def get_active_ruleset(self, owner: str) -> RulesetMeta | None:
        """Return the active org standardization ruleset, or ``None`` on miss.

        The endpoint shape is not officially documented; this is best-effort
        and intentionally swallows HTTP errors (including 404). A scan must
        not fail because ruleset metadata is unavailable — the report
        layer surfaces "not recorded by scanner" in that case.
        """
        try:
            data = await self.get_json(f"/orgs/{owner}/standardization")
        except httpx.HTTPError as e:
            log.info("ruleset_unavailable", owner=owner, error=str(e))
            return None
        return parse_ruleset_payload(data)
