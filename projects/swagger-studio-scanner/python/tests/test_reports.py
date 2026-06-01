"""Report writer integration tests — write to tmp_path, verify shape."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from swagger_studio_scanner.models import (
    ApiMeta,
    ApiRef,
    ApiScanResult,
    Finding,
    RulesetMeta,
    ScanReport,
    ScanStatus,
    Severity,
)
from swagger_studio_scanner.reports import write_csv, write_html, write_json


def _sample_results() -> list[ApiScanResult]:
    return [
        ApiScanResult(
            api=ApiRef(owner="acme", name="orders", version="1.0.0"),
            status=ScanStatus.FAIL,
            findings=[
                Finding(
                    rule="oas3-schema",
                    severity=Severity.CRITICAL,
                    description="oas3-schema -> bad",
                    message="bad",
                ),
                Finding(
                    rule="op-tag",
                    severity=Severity.WARNING,
                    description="op-tag -> warn",
                    message="warn",
                ),
            ],
            scanned_at=datetime.now(UTC),
            meta=ApiMeta(
                created_at=datetime(2024, 5, 1, tzinfo=UTC),
                modified_at=datetime(2025, 11, 1, tzinfo=UTC),
                is_default_version=True,
                is_published=True,
            ),
        ),
        ApiScanResult(
            api=ApiRef(owner="acme", name="ledger", version="2.1.0"),
            status=ScanStatus.PASS,
            findings=[],
            scanned_at=datetime.now(UTC),
        ),
    ]


def _sample_report() -> ScanReport:
    return ScanReport(
        scanned_at=datetime.now(UTC),
        ruleset=RulesetMeta(name="openapi-3-0-active", version="1.4.0"),
        results=_sample_results(),
    )


def test_json_writer_round_trips_with_ruleset_and_meta(tmp_path: Path) -> None:
    path = write_json(_sample_report(), tmp_path)
    payload = json.loads(path.read_text())

    assert payload["summary"]["total_apis"] == 2
    assert payload["summary"]["failed"] == 1
    assert payload["summary"]["passed"] == 1
    assert any(e["rule"] == "oas3-schema" for e in payload["rule_pareto"])
    assert len(payload["results"]) == 2

    # New v2 fields:
    assert payload["ruleset"] == {"name": "openapi-3-0-active", "version": "1.4.0"}
    orders = next(r for r in payload["results"] if r["api"]["name"] == "orders")
    assert orders["meta"]["created_at"].startswith("2024-05-01")
    assert orders["meta"]["is_default_version"] is True


def test_json_writer_emits_null_ruleset_when_absent(tmp_path: Path) -> None:
    report = ScanReport(scanned_at=datetime.now(UTC), ruleset=None, results=_sample_results())
    payload = json.loads(write_json(report, tmp_path).read_text())
    assert payload["ruleset"] is None


def test_csv_writer_emits_row_per_finding_plus_pass_row(tmp_path: Path) -> None:
    path = write_csv(_sample_results(), tmp_path)
    with path.open() as f:
        rows = list(csv.DictReader(f))
    # 2 findings on the FAIL API + 1 empty row for the PASS API = 3
    assert len(rows) == 3
    fail_rows = [r for r in rows if r["api"] == "orders"]
    pass_rows = [r for r in rows if r["api"] == "ledger"]
    assert len(fail_rows) == 2
    assert len(pass_rows) == 1
    assert pass_rows[0]["rule"] == ""


def test_html_writer_renders_summary_and_pareto(tmp_path: Path) -> None:
    path = write_html(_sample_results(), tmp_path)
    html = path.read_text()
    assert "SwaggerHub Governance Scan" in html
    assert "Rule Pareto" in html
    assert "oas3-schema" in html
    assert "acme/orders/1.0.0" in html
