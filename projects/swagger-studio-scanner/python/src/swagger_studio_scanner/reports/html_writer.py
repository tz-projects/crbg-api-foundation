"""HTML report writer — self-contained leadership report.

Self-contained = single .html file, inline CSS, no external assets. Open it
on any laptop, share it on SharePoint, attach it to a ticket — it just works.

Headline = the rule Pareto. That's the single most decision-relevant output
per the §8 design note: tells you bulk-fix vs. long-tail at a glance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from swagger_studio_scanner.models import ApiScanResult
from swagger_studio_scanner.pareto import ScanSummary, rule_pareto, top_failing_apis


_TEMPLATE_DIR = Path(__file__).parent / "templates"


def write_html(results: list[ApiScanResult], out_dir: Path) -> Path:
    """Write `scan.html` and return its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "scan.html"

    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("scan.html.j2")

    html = template.render(
        generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        summary=ScanSummary.from_results(results),
        pareto=rule_pareto(results, top_n=20),
        top_failing=top_failing_apis(results, top_n=20),
        results=sorted(results, key=lambda r: (r.status.value, r.api.slug)),
    )
    path.write_text(html, encoding="utf-8")
    return path
