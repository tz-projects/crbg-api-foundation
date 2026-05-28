"""Pydantic models for SwaggerHub REST payloads and internal scan results.

Wire-shaped models (`*Payload`) match the API; domain models (`ApiRef`,
`Finding`, `ApiScanResult`) are what the rest of the pipeline consumes.
Keeping the two layers separated means a change in the API shape only
touches the adapter, not every consumer.
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


# --- Domain models ------------------------------------------------------


class ApiRef(BaseModel):
    """Identifier for one API version in Studio."""

    model_config = ConfigDict(frozen=True)

    owner: str
    name: str
    version: str

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}/{self.version}"


class Finding(BaseModel):
    """One governance finding from the /standardization endpoint."""

    rule: str
    severity: Severity
    description: str
    line: int | None = None
    path: str | None = None


class ApiScanResult(BaseModel):
    """Aggregated scan result for one API version."""

    api: ApiRef
    status: ScanStatus
    findings: list[Finding] = Field(default_factory=list)
    error: str | None = None
    scanned_at: datetime

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity is Severity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity is Severity.WARNING)
