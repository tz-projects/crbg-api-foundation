"""Scanner pure-logic tests — status bucketing + enumeration limit (no network)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from swagger_studio_scanner.client import ListedApi
from swagger_studio_scanner.models import ApiMeta, ApiRef, Finding, ScanStatus, Severity
from swagger_studio_scanner.scanner import _bucket_status, _enumerate


def test_bucket_status_empty_is_pass() -> None:
    assert _bucket_status([]) is ScanStatus.PASS


def test_bucket_status_warning_only_is_warn() -> None:
    findings = [Finding(rule="r", severity=Severity.WARNING, description="x")]
    assert _bucket_status(findings) is ScanStatus.WARN


def test_bucket_status_any_critical_is_fail() -> None:
    findings = [
        Finding(rule="r1", severity=Severity.WARNING, description="x"),
        Finding(rule="r2", severity=Severity.CRITICAL, description="y"),
    ]
    assert _bucket_status(findings) is ScanStatus.FAIL


# --- _enumerate limit behavior -----------------------------------------------


@dataclass
class _FakeClient:
    """Stub of SwaggerHubClient that yields a fixed number of refs.

    Tracks how many were yielded so the test can verify enumeration
    stopped early under ``limit`` (no wasted HTTP).
    """

    total: int
    yielded: int = 0

    async def list_api_versions(self, owner: str) -> AsyncIterator[ListedApi]:
        for i in range(self.total):
            self.yielded += 1
            yield ListedApi(
                ref=ApiRef(owner=owner, name=f"api-{i:03d}", version="1.0.0"),
                meta=ApiMeta(),
            )


def test_enumerate_returns_everything_when_no_limit() -> None:
    fake = _FakeClient(total=25)
    out = asyncio.run(_enumerate(fake, "acme"))  # type: ignore[arg-type]
    assert len(out) == 25
    assert fake.yielded == 25


def test_enumerate_stops_early_at_limit() -> None:
    fake = _FakeClient(total=600)
    out = asyncio.run(_enumerate(fake, "acme", limit=10))  # type: ignore[arg-type]
    assert len(out) == 10
    # The iterator must not have been drained past the limit — that's the
    # whole point: avoid extra page fetches against a 600-API org.
    assert fake.yielded == 10


def test_enumerate_limit_above_total_is_a_noop() -> None:
    fake = _FakeClient(total=4)
    out = asyncio.run(_enumerate(fake, "acme", limit=100))  # type: ignore[arg-type]
    assert len(out) == 4
