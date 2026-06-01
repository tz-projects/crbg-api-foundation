"""Pareto analysis of scan results.

The §8 headline of the HTML report is "which rules account for most failures."
That's a Pareto: rank rules by failure count and report the top N + cumulative
share of the total. This module owns the math so the report writers stay
presentation-only.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from swagger_studio_scanner.models import ApiScanResult, ScanStatus, Severity


@dataclass(frozen=True)
class ParetoEntry:
    """One row in the rule-failure Pareto."""

    rule: str
    severity: Severity
    count: int
    share_pct: float
    cumulative_pct: float


@dataclass(frozen=True)
class ScanSummary:
    """Top-level counts shown in the HTML report header."""

    total_apis: int
    passed: int
    warned: int
    failed: int
    errored: int
    total_findings: int
    critical_findings: int
    warning_findings: int

    @classmethod
    def from_results(cls, results: list[ApiScanResult]) -> "ScanSummary":
        status_counts = Counter(r.status for r in results)
        all_findings = [f for r in results for f in r.findings]
        return cls(
            total_apis=len(results),
            passed=status_counts.get(ScanStatus.PASS, 0),
            warned=status_counts.get(ScanStatus.WARN, 0),
            failed=status_counts.get(ScanStatus.FAIL, 0),
            errored=status_counts.get(ScanStatus.ERROR, 0),
            total_findings=len(all_findings),
            critical_findings=sum(1 for f in all_findings if f.severity is Severity.CRITICAL),
            warning_findings=sum(1 for f in all_findings if f.severity is Severity.WARNING),
        )


def rule_pareto(results: list[ApiScanResult], top_n: int = 20) -> list[ParetoEntry]:
    """Top-N rules by failure count, with share and cumulative %.

    Each (rule, severity) pair is counted separately so a CRITICAL and a WARNING
    occurrence of the same rule don't get conflated — they're materially
    different signals for remediation prioritization.
    """
    counts: Counter[tuple[str, Severity]] = Counter()
    for result in results:
        for finding in result.findings:
            counts[(finding.rule, finding.severity)] += 1

    total = sum(counts.values())
    if total == 0:
        return []

    ranked = counts.most_common(top_n)
    entries: list[ParetoEntry] = []
    running = 0
    for (rule, severity), count in ranked:
        running += count
        entries.append(
            ParetoEntry(
                rule=rule,
                severity=severity,
                count=count,
                share_pct=round(100 * count / total, 1),
                cumulative_pct=round(100 * running / total, 1),
            )
        )
    return entries


def top_failing_apis(
    results: list[ApiScanResult], top_n: int = 20
) -> list[tuple[ApiScanResult, int]]:
    """APIs sorted by total finding count, descending. Tiebreak: critical first."""
    scored = [
        (r, len(r.findings), r.critical_count)
        for r in results
        if r.status in (ScanStatus.FAIL, ScanStatus.WARN)
    ]
    scored.sort(key=lambda t: (-t[1], -t[2], t[0].api.slug))
    return [(r, total) for r, total, _ in scored[:top_n]]
