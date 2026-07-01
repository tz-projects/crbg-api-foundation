"""JSON report writer — the machine-feedable format.

Takes a :class:`ScanReport` and emits ``scan.json``. The on-disk shape is
the contract that downstream consumers (the executive and platform
report generators, future dashboards) depend on — keep it stable.

Schema (top-level):

- ``generated_at``        : when the scan ran (ISO 8601 with TZ).
- ``ruleset``             : ``{name, version}`` or ``null`` when Studio did
                            not expose it.
- ``rule_display_names``  : ``{rule_id: friendly title}`` from Studio's rule
                            definitions, or ``null`` when unavailable. Optional
                            and additive — consumers fall back to a humanized
                            rule id when a rule is absent.
- ``summary``             : aggregated counts.
- ``rule_pareto``         : top rules by failure count, with share %.
- ``results[]``           : one entry per API version. Each carries its own
                            ``meta`` block (``created_at``, ``modified_at``,
                            ``is_default_version``, ``is_published``) so
                            consumers don't have to re-fetch the listing.
"""

from __future__ import annotations

import json
from pathlib import Path

from swagger_studio_scanner.models import ScanReport
from swagger_studio_scanner.pareto import ScanSummary, rule_pareto


def write_json(report: ScanReport, out_dir: Path) -> Path:
    """Write ``scan.json`` and return its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "scan.json"

    summary = ScanSummary.from_results(report.results)
    payload = {
        "generated_at": report.scanned_at.isoformat(),
        "ruleset": report.ruleset.model_dump(mode="json") if report.ruleset else None,
        "rule_display_names": report.rule_display_names or None,
        "summary": {
            "total_apis": summary.total_apis,
            "passed": summary.passed,
            "warned": summary.warned,
            "failed": summary.failed,
            "errored": summary.errored,
            "total_findings": summary.total_findings,
            "critical_findings": summary.critical_findings,
            "warning_findings": summary.warning_findings,
        },
        "rule_pareto": [
            {
                "rule": e.rule,
                "severity": e.severity.value,
                "count": e.count,
                "share_pct": e.share_pct,
                "cumulative_pct": e.cumulative_pct,
            }
            for e in rule_pareto(report.results)
        ],
        "results": [r.model_dump(mode="json") for r in report.results],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    return path
