"""Pydantic models for SwaggerHub REST payloads and internal scan results.

Three concerns are kept separate so a change in one layer doesn't ripple
through the others:

- **Identity**     — `ApiRef`. What API is this (stable, hashable).
- **Metadata**     — `ApiMeta`, `RulesetMeta`. Descriptive context, all optional.
- **Scan outcome** — `Finding`, `ApiScanResult`, `ScanReport`. What we learned.

Wire-shaped payloads come in via `parsers.py`; this module is the typed
domain the rest of the pipeline consumes. Keeping the two layers separated
means a Studio response-shape change only touches the adapter.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    """SwaggerHub standardization severities."""

    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class ScanStatus(StrEnum):
    """Per-API outcome bucket used in the report."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    ERROR = "error"


# --- Identity ---------------------------------------------------------------


class ApiRef(BaseModel):
    """Stable identity for one API version (owner/name/version)."""

    model_config = ConfigDict(frozen=True)

    owner: str
    name: str
    version: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}/{self.version}"


# --- Metadata ---------------------------------------------------------------


class ApiMeta(BaseModel):
    """Descriptive metadata for one API version — every field optional.

    Recovered from the `properties` array of a SwaggerHub listing item
    (`X-Created`, `X-Modified`, `X-Default`, `X-Published`). Reports degrade
    gracefully when fields are absent, so the model never invents values:
    missing inputs map to `None`.
    """

    created_at: datetime | None = None
    modified_at: datetime | None = None
    is_default_version: bool | None = None
    is_published: bool | None = None


class RulesetMeta(BaseModel):
    """Identity of the active org standardization ruleset, when known."""

    name: str | None = None
    version: str | None = None


# --- Scan outcome -----------------------------------------------------------


class Finding(BaseModel):
    """One governance finding from the `/standardization` endpoint.

    `rule` is the canonical rule id; `description` is the raw text as
    returned by Studio; `message` is the human-readable portion after the
    rule id has been split off (when extractable). All three are kept so
    downstream consumers can pick the granularity they need.
    """

    rule: str
    severity: Severity
    description: str
    message: str | None = None
    line: int | None = None
    path: str | None = None


class ApiScanResult(BaseModel):
    """Aggregated scan result for one API version."""

    api: ApiRef
    status: ScanStatus
    findings: list[Finding] = Field(default_factory=list)
    error: str | None = None
    scanned_at: datetime
    meta: ApiMeta = Field(default_factory=ApiMeta)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity is Severity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity is Severity.WARNING)


class ScanReport(BaseModel):
    """Scan-level aggregate: when it ran, against which ruleset, with what results."""

    scanned_at: datetime
    ruleset: RulesetMeta | None = None
    results: list[ApiScanResult] = Field(default_factory=list)
    # rule id -> human-readable title, fetched from Studio's rule definitions
    # at scan time (where SwaggerHub is reachable) so the reports can show
    # friendly names offline. Empty when unavailable; reports fall back to a
    # humanized rule id. Additive/optional — older readers ignore it.
    rule_display_names: dict[str, str] = Field(default_factory=dict)
