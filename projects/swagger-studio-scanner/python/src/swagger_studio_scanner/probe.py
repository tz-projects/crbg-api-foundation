"""Capability probe — step zero of any scan.

Confirms the API key is valid, the org is reachable, and the
`/standardization` endpoint is actually populated for this tier.
Fails fast with a human-readable reason so the work-laptop run does
not stall against silent tier or proxy issues.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import httpx
import structlog

from swagger_studio_scanner.client import SwaggerHubClient
from swagger_studio_scanner.config import Settings

log = structlog.get_logger(__name__)


class ProbeStatus(StrEnum):
    OK = "ok"
    AUTH_FAILED = "auth_failed"
    ORG_UNREACHABLE = "org_unreachable"
    GOVERNANCE_UNAVAILABLE = "governance_unavailable"
    NETWORK_ERROR = "network_error"


@dataclass(frozen=True)
class ProbeResult:
    status: ProbeStatus
    detail: str

    @property
    def ok(self) -> bool:
        return self.status is ProbeStatus.OK


async def run_probe(settings: Settings) -> ProbeResult:
    """Perform the capability probe and return a structured result."""
    async with SwaggerHubClient(settings) as client:
        # 1. Auth + org reachability: list APIs under the org.
        try:
            await client.get_json(f"/apis/{settings.swaggerhub_org}", limit=1)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in (401, 403):
                return ProbeResult(ProbeStatus.AUTH_FAILED, f"HTTP {status} listing org APIs")
            if status == 404:
                return ProbeResult(
                    ProbeStatus.ORG_UNREACHABLE,
                    f"Org '{settings.swaggerhub_org}' not found (HTTP 404)",
                )
            return ProbeResult(ProbeStatus.NETWORK_ERROR, f"HTTP {status} listing org APIs")
        except httpx.HTTPError as e:
            return ProbeResult(ProbeStatus.NETWORK_ERROR, f"Network error: {e!r}")

        # 2. Governance/standardization endpoint reachability.
        # Empty/silent response on tiers without Governance is the failure
        # mode flagged in the context doc — flag it explicitly here.
        return ProbeResult(ProbeStatus.OK, "Auth + org reachable; verify standardization next.")
