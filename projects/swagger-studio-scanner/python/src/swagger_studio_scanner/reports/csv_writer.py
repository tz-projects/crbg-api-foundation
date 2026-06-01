"""CSV report writer — finding-level rows, pivot-friendly.

One row per finding. APIs that pass cleanly still get a row with empty
finding fields so "how many are clean" is answerable from the CSV alone.
"""

from __future__ import annotations

import csv
from pathlib import Path

from swagger_studio_scanner.models import ApiScanResult


_FIELDS = [
    "owner",
    "api",
    "version",
    "status",
    "rule",
    "severity",
    "description",
    "line",
    "path",
    "error",
    "scanned_at",
]


def write_csv(results: list[ApiScanResult], out_dir: Path) -> Path:
    """Write `findings.csv` and return its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "findings.csv"

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDS)
        writer.writeheader()
        for result in results:
            base = {
                "owner": result.api.owner,
                "api": result.api.name,
                "version": result.api.version,
                "status": result.status.value,
                "error": result.error or "",
                "scanned_at": result.scanned_at.isoformat(),
            }
            if not result.findings:
                writer.writerow({**base, "rule": "", "severity": "", "description": "",
                                 "line": "", "path": ""})
                continue
            for finding in result.findings:
                writer.writerow({
                    **base,
                    "rule": finding.rule,
                    "severity": finding.severity.value,
                    "description": finding.description,
                    "line": finding.line if finding.line is not None else "",
                    "path": finding.path or "",
                })
    return path
