"""Scan orchestrator.

One responsibility: drive a full org scan and return a typed :class:`ScanReport`.
Composes the client (HTTP) and the parsers (interpretation) — neither of which
this module knows the internals of.

Per-API errors are caught and surfaced as :attr:`ScanStatus.ERROR` rows
instead of killing the run — one bad API should never lose us the report
for 599 others.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
import structlog

from .client import ListedApi, SwaggerHubClient
from .config import Settings
from .models import (
    ApiScanResult,
    Finding,
    ScanReport,
    ScanStatus,
    Severity,
)

log = structlog.get_logger(__name__)


async def scan_org(settings: Settings, *, limit: int | None = None) -> ScanReport:
    """Enumerate the configured org and return a :class:`ScanReport`.

    When ``limit`` is provided, enumeration stops after the first N API
    versions returned by Studio's listing endpoint — no additional pages
    are fetched. Useful for dev-loop iteration and targeted runs against
    a large org (e.g. ``--limit 25`` instead of 600+).

    Ordering matches the listing endpoint's natural order, which the
    Studio REST API does not guarantee is stable across runs; callers
    that need determinism should pair ``limit`` with a deterministic
    filter rather than relying on slicing alone.
    """
    started = datetime.now(UTC)
    async with SwaggerHubClient(settings) as client:
        ruleset, rule_display_names, listed = await asyncio.gather(
            client.get_active_ruleset(settings.swaggerhub_org),
            client.get_system_rule_display_names(),
            _enumerate(client, settings.swaggerhub_org, limit=limit),
        )
        log.info(
            "enumerated",
            count=len(listed),
            limit=limit,
            org=settings.swaggerhub_org,
            ruleset=(ruleset.name if ruleset else None),
            rule_names=len(rule_display_names),
        )
        results = await asyncio.gather(*[_scan_one(client, item) for item in listed])
    return ScanReport(
        scanned_at=started,
        ruleset=ruleset,
        results=list(results),
        rule_display_names=rule_display_names,
    )


async def _enumerate(
    client: SwaggerHubClient, owner: str, *, limit: int | None = None
) -> list[ListedApi]:
    """Drain the listing iterator, stopping after ``limit`` items if given."""
    out: list[ListedApi] = []
    async for item in client.list_api_versions(owner):
        out.append(item)
        if limit is not None and len(out) >= limit:
            break
    return out


async def _scan_one(client: SwaggerHubClient, listed: ListedApi) -> ApiScanResult:
    """Fetch findings for one API version, never raising."""
    now = datetime.now(UTC)
    ref = listed.ref
    try:
        findings = await client.get_findings(ref)
    except httpx.HTTPStatusError as e:
        log.warning("findings_http_error", api=ref.slug, status=e.response.status_code)
        return ApiScanResult(
            api=ref,
            status=ScanStatus.ERROR,
            error=f"HTTP {e.response.status_code}",
            scanned_at=now,
            meta=listed.meta,
        )
    except httpx.HTTPError as e:
        log.warning("findings_network_error", api=ref.slug, error=str(e))
        return ApiScanResult(
            api=ref,
            status=ScanStatus.ERROR,
            error=f"Network: {e!r}",
            scanned_at=now,
            meta=listed.meta,
        )

    return ApiScanResult(
        api=ref,
        status=_bucket_status(findings),
        findings=findings,
        scanned_at=now,
        meta=listed.meta,
    )


def _bucket_status(findings: list[Finding]) -> ScanStatus:
    """Map a finding list to a top-level status bucket."""
    if not findings:
        return ScanStatus.PASS
    if any(f.severity is Severity.CRITICAL for f in findings):
        return ScanStatus.FAIL
    return ScanStatus.WARN
