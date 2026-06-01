"""Pareto math + scan summary unit tests — no network, no I/O."""

from __future__ import annotations

from datetime import UTC, datetime

from swagger_studio_scanner.models import (
    ApiRef,
    ApiScanResult,
    Finding,
    ScanStatus,
    Severity,
)
from swagger_studio_scanner.pareto import ScanSummary, rule_pareto, top_failing_apis


def _result(
    name: str,
    findings: list[Finding],
    status: ScanStatus = ScanStatus.FAIL,
) -> ApiScanResult:
    return ApiScanResult(
        api=ApiRef(owner="acme", name=name, version="1.0.0"),
        status=status,
        findings=findings,
        scanned_at=datetime.now(UTC),
    )


def _f(rule: str, severity: Severity = Severity.CRITICAL) -> Finding:
    return Finding(rule=rule, severity=severity, description="x")


def test_pareto_ranks_by_count_and_computes_shares() -> None:
    results = [
        _result("a", [_f("oas3-schema"), _f("oas3-schema"), _f("operation-tag")]),
        _result("b", [_f("oas3-schema"), _f("operation-tag")]),
    ]
    entries = rule_pareto(results)

    assert [e.rule for e in entries] == ["oas3-schema", "operation-tag"]
    assert entries[0].count == 3
    assert entries[0].share_pct == 60.0
    assert entries[1].share_pct == 40.0
    assert entries[1].cumulative_pct == 100.0


def test_pareto_separates_severity_for_same_rule() -> None:
    results = [
        _result(
            "a",
            [
                _f("oas3-schema", Severity.CRITICAL),
                _f("oas3-schema", Severity.WARNING),
                _f("oas3-schema", Severity.WARNING),
            ],
        ),
    ]
    entries = rule_pareto(results)
    pairs = {(e.rule, e.severity) for e in entries}
    assert (("oas3-schema", Severity.CRITICAL)) in pairs
    assert (("oas3-schema", Severity.WARNING)) in pairs


def test_pareto_empty_when_no_findings() -> None:
    results = [_result("a", [], ScanStatus.PASS)]
    assert rule_pareto(results) == []


def test_scan_summary_counts_each_bucket() -> None:
    results = [
        _result("a", [_f("r1")], ScanStatus.FAIL),
        _result("b", [_f("r1", Severity.WARNING)], ScanStatus.WARN),
        _result("c", [], ScanStatus.PASS),
        _result("d", [], ScanStatus.ERROR),
    ]
    s = ScanSummary.from_results(results)
    assert s.total_apis == 4
    assert s.passed == 1
    assert s.warned == 1
    assert s.failed == 1
    assert s.errored == 1
    assert s.critical_findings == 1
    assert s.warning_findings == 1


def test_top_failing_apis_excludes_pass_and_sorts_descending() -> None:
    results = [
        _result("clean", [], ScanStatus.PASS),
        _result("small", [_f("r1")], ScanStatus.FAIL),
        _result("big", [_f("r1"), _f("r2"), _f("r3")], ScanStatus.FAIL),
    ]
    ordered = top_failing_apis(results)
    names = [r.api.name for r, _ in ordered]
    assert names == ["big", "small"]
    assert "clean" not in names
