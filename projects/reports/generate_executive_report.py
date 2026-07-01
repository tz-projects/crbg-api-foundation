"""Executive (CIO-facing) governance report generator — v2 spec.

One self-contained HTML file, single page, plain language. Renders fully
from Tier 1 (Studio) data and substitutes Tier 1 alternatives whenever
Tier 2 (ownership map) or Tier 3 (curated lookups) inputs are missing —
so the report is always meaningful, not a half-empty form.

Usage:
    python generate_executive_report.py \\
        --input output/scan.json \\
        --output output/executive-report.html \\
        --org-display-name "Acme Corporation" \\
        [--ownership-map ownership.yaml] \\
        [--rule-display-names rule_display_names.yaml]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _lib as L

# ---- Section renderers -------------------------------------------------------


def _title_block(scan: L.NormalizedScan, org_display: str) -> str:
    return f"""
      <header class="title-block">
        <h1>API Governance Conformance — Baseline Report</h1>
        <p class="subtitle">{L.esc(org_display)}</p>
        <p class="meta">Scan date: {L.esc(L.fmt_date(scan.scanned_at))}</p>
      </header>
    """


def _headline_numbers(scan: L.NormalizedScan) -> str:
    pareto = L.rule_pareto(scan, top_n=10_000)
    distinct_rules = len(pareto)

    # Always tiles 1-4.
    tiles = [
        ("APIs scanned", str(scan.api_count), "in Swagger Studio"),
        ("Pass rate", L.fmt_pct(scan.pass_pct), "of scannable APIs"),
        ("Failure rate", L.fmt_pct(scan.fail_pct), "blocked from publish"),
        ("Distinct rule violations", str(distinct_rules), "driving findings"),
    ]

    # Tile 5: fallback chain — ownership > published-state > age > total findings.
    # Never blank, never "data not available" as a headline (per v2 §3 substitution rule).
    if scan.has_ownership and scan.ownership_coverage_pct >= 50.0:
        tiles.append(("Teams represented", str(len(scan.teams)), "in ownership map"))
    elif scan.published_coverage_pct >= 50.0:
        unpub, total = L.unpublished_failing_stats(scan)
        if total > 0:
            pct = round(100.0 * unpub / total)
            tiles.append(
                (
                    "Unpublished among failing",
                    f"{pct:.0f}%",
                    f"{unpub} of {total} failing APIs are still drafts",
                )
            )
        else:
            tiles.append(
                ("Unpublished among failing", "—", "no failing APIs with a known publish state")
            )
    elif scan.has_age_data:
        r_total, _, d_total, _ = L.recent_vs_dormant(scan, window_days=90)
        tiles.append(
            (
                "Recently modified",
                str(r_total),
                f"of {r_total + d_total} APIs in last 90 days",
            )
        )
    else:
        tiles.append(("Total findings", str(len(scan.all_findings)), "across the portfolio"))

    tile_html = "".join(
        f"""
          <div class="tile">
            <div class="tile-value">{L.esc(value)}</div>
            <div class="tile-label">{L.esc(label)}</div>
            <div class="tile-sub">{L.esc(sub)}</div>
          </div>
        """
        for label, value, sub in tiles
    )
    return f'<section class="tiles">{tile_html}</section>'


def _pareto_section(scan: L.NormalizedScan) -> str:
    pareto = L.rule_pareto(scan, top_n=10)
    if not pareto:
        return ""
    max_count = max(p.count for p in pareto)
    rows = []
    for p in pareto:
        bar_pct = round(100.0 * p.count / max_count, 1)
        rows.append(
            f"""
              <li class="pareto-row">
                <div class="pareto-label" title="{L.esc(p.rule_id)}">{L.esc(p.rule_display)}</div>
                <div class="pareto-bar-track">
                  <div class="pareto-bar" style="width: {bar_pct}%"></div>
                </div>
                <div class="pareto-count">{p.count} <span class="muted">({p.share_pct:.0f}%)</span></div>
              </li>
            """
        )
    top_n = L.rules_to_reach(scan, threshold_pct=70.0)
    top_share = pareto[min(top_n, len(pareto)) - 1].cumulative_pct if top_n else 0.0
    distinct = len(L.rule_pareto(scan, top_n=10_000))

    if top_n and top_n <= max(1, distinct // 2):
        interp = (
            f"The top {top_n} rules account for {top_share:.0f}% of all findings, "
            "indicating remediation at scale is tractable through focused guidance on a small set of common patterns."
        )
    else:
        interp = (
            f"Findings are distributed across {distinct} distinct rules with no dominant pattern, "
            "indicating remediation will require per-API attention rather than bulk fixes."
        )

    return f"""
      <section class="section pareto">
        <h2>Most frequently violated rules</h2>
        <ol class="pareto-list">{''.join(rows)}</ol>
        <p class="interp">{L.esc(interp)}</p>
      </section>
    """


def _distribution_section(scan: L.NormalizedScan) -> str:
    """Tier 2 (domain) when ownership covers >=50%, else Tier 1 age/activity."""
    if scan.has_ownership and scan.ownership_coverage_pct >= 50.0:
        return _distribution_by_domain(scan)
    return _distribution_by_age_activity(scan)


def _distribution_by_domain(scan: L.NormalizedScan) -> str:
    domains = L.domain_summaries(scan)
    if not domains:
        # Map present but no domain field — fall back to teams (top 10).
        teams = L.team_summaries(scan)[:10]
        rows = "".join(
            f"<tr><td>{L.esc(t.team)}</td><td>{t.owned}</td><td>{t.failing}</td>"
            f"<td>{L.fmt_pct(100.0 * (t.owned - t.failing) / t.owned if t.owned else 0)}</td></tr>"
            for t in teams
        )
        head = "Team"
    else:
        rows = "".join(
            f"<tr><td>{L.esc(d)}</td><td>{owned}</td><td>{failing}</td>"
            f"<td>{L.fmt_pct(100.0 * (owned - failing) / owned if owned else 0)}</td></tr>"
            for d, owned, failing in domains[:10]
        )
        head = "Domain"

    return f"""
      <section class="section dist">
        <h2>Where the work sits</h2>
        <table>
          <thead><tr><th>{head}</th><th>APIs owned</th><th>APIs failing</th><th>Conformance</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
    """


def _distribution_by_age_activity(scan: L.NormalizedScan) -> str:
    if not scan.has_age_data:
        return f"""
          <section class="section dist">
            <h2>Recent API activity (last 90 days)</h2>
            <p class="muted">
              API age and modification metadata were not recorded by the scanner for this run,
              and the organizational ownership map is not yet configured. Once either is in
              place, this section will show how failures distribute across teams, domains, or
              API age and activity.
            </p>
          </section>
        """

    def _rows(field: str) -> str:
        return "".join(
            f"<tr><td>{L.esc(b.label)}</td><td>{b.api_count}</td><td>{b.failing_count}</td></tr>"
            for b in L.recency_buckets(scan, field)
        )

    return f"""
      <section class="section dist">
        <h2>Recent API activity (last 90 days)</h2>
        <div class="dist-grid">
          <div>
            <h3>By creation date</h3>
            <table>
              <thead><tr><th>Created</th><th>APIs</th><th>Failing</th></tr></thead>
              <tbody>{_rows("created")}</tbody>
            </table>
          </div>
          <div>
            <h3>By modification date</h3>
            <table>
              <thead><tr><th>Modified</th><th>APIs</th><th>Failing</th></tr></thead>
              <tbody>{_rows("modified")}</tbody>
            </table>
          </div>
        </div>
      </section>
    """


def _severity_context(scan: L.NormalizedScan) -> str:
    return f"""
      <section class="section severity">
        <h2>Severity context</h2>
        <ul>
          <li>{L.fmt_pct(scan.fail_pct)} of scannable APIs have errors (blocks publish).</li>
          <li>{L.fmt_pct(scan.warn_only_pct)} have WARNING-only findings (does not block publish, indicates quality gap).</li>
        </ul>
      </section>
    """


def _methodology_footer(scan: L.NormalizedScan) -> str:
    return f"""
      <footer class="methodology">
        <p>Scan date and time: {L.esc(L.fmt_datetime(scan.scanned_at))}</p>
        <p>APIs evaluated: {scan.scannable_count} of {scan.api_count} in Studio
           ({scan.error_count} could not be scanned).</p>
      </footer>
    """


# ---- Page assembly ----------------------------------------------------------

_CSS = """
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body {
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1a1a1a; background: #fff; margin: 0;
    padding: 32px 40px; max-width: 920px; margin-left: auto; margin-right: auto;
  }
  h1 { font-size: 28px; margin: 0 0 4px; }
  h2 { font-size: 18px; margin: 0 0 12px; padding-bottom: 6px; border-bottom: 1px solid #e0e0e0; }
  h3 { font-size: 14px; margin: 0 0 8px; color: #444; }
  p  { margin: 8px 0; }
  .subtitle { font-size: 18px; color: #555; margin: 0 0 4px; }
  .meta { font-size: 13px; color: #666; margin: 0; }
  .methodology-top { margin-top: 12px; }
  .title-block { margin-bottom: 28px; }
  .headline p {
    font-size: 19px; line-height: 1.4; font-weight: 500;
    background: #f7f7f5; padding: 18px 22px; border-left: 4px solid #0b5fff; border-radius: 4px;
  }
  .tiles { display: flex; gap: 12px; margin: 28px 0; flex-wrap: wrap; }
  .tile {
    flex: 1 1 160px; min-width: 150px; padding: 14px 16px;
    border: 1px solid #e2e2e2; border-radius: 6px; background: #fafafa;
  }
  .tile-value { font-size: 28px; font-weight: 600; color: #0b5fff; }
  .tile-label { font-size: 13px; font-weight: 600; margin-top: 2px; }
  .tile-sub   { font-size: 12px; color: #777; margin-top: 2px; }
  .section { margin: 32px 0; }
  .pareto-list { list-style: none; padding: 0; margin: 0; }
  .pareto-row { display: grid; grid-template-columns: 300px 1fr 110px; gap: 12px; align-items: center; padding: 6px 0; }
  .pareto-label { font-size: 14px; line-height: 1.3; overflow-wrap: break-word; }
  .pareto-bar-track { background: #eef0f4; height: 18px; border-radius: 3px; overflow: hidden; }
  .pareto-bar { background: #0b5fff; height: 100%; }
  .pareto-count { font-variant-numeric: tabular-nums; font-size: 13px; text-align: right; }
  .muted { color: #777; }
  .interp { margin-top: 14px; font-size: 14px; color: #444; }
  table { border-collapse: collapse; width: 100%; font-size: 14px; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #eee; }
  th { font-weight: 600; background: #f7f7f5; }
  .dist-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
  .severity ul { padding-left: 18px; }
  .ask p {
    background: #fff8e6; padding: 16px 18px; border-left: 4px solid #c79100; border-radius: 4px;
    font-size: 15px;
  }
  .ask.placeholder p { background: #fff0f0; border-left-color: #b00020; color: #b00020; font-style: italic; }
  .methodology { margin-top: 40px; padding-top: 16px; border-top: 1px solid #ddd; font-size: 12px; color: #555; }
  .methodology .baseline { margin-top: 8px; color: #333; font-weight: 500; }
  @media print {
    body { padding: 18px; max-width: none; }
    .section { page-break-inside: avoid; }
    .tile { background: #fff; }
  }
"""


def _render(scan: L.NormalizedScan, org_display: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>API Governance Conformance — Baseline Report — {L.esc(org_display)}</title>
  <style>{_CSS}</style>
</head>
<body>
{_title_block(scan, org_display)}
{_headline_numbers(scan)}
{_pareto_section(scan)}
{_distribution_section(scan)}
{_severity_context(scan)}
{_methodology_footer(scan)}
</body>
</html>
"""


# ---- CLI --------------------------------------------------------------------


def _summary_stdout(scan: L.NormalizedScan) -> None:
    print("Executive report — render summary")
    print(f"  Tier 1 sections: title, headline, tiles 1-4, Pareto, severity, methodology")
    if scan.has_ownership and scan.ownership_coverage_pct >= 50.0:
        print(
            f"  Tier 2 (ownership): teams tile + 'Where the work sits' "
            f"(coverage {scan.ownership_coverage_pct:.0f}%)"
        )
    elif scan.published_coverage_pct >= 50.0:
        print(
            f"  Tier 1 substitute: 'unpublished among failing' tile "
            f"(published-state known on {scan.published_coverage_pct:.0f}% of APIs)"
        )
    elif scan.has_age_data:
        print("  Tier 1 substitute: 'recently modified' tile + age/activity distribution")
    else:
        print("  Tier 1 substitute: total-findings tile + distribution shows 'data not available'")
    print(f"  Tier 3 rule display names: {'present' if scan.has_rule_display_lookup else 'not provided'}")
    if not scan.ruleset_name:
        print("  Note: ruleset name/version not in scan input (scanner patch pending).")
    if not scan.has_age_data:
        print("  Note: created_at / modified_at not in scan input (scanner patch pending).")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate the executive governance report.")
    p.add_argument("--input", required=True, type=Path, help="Path to scan JSON.")
    p.add_argument("--output", required=True, type=Path, help="Path to output HTML.")
    p.add_argument("--org-display-name", required=True)
    p.add_argument("--ownership-map", type=Path, default=None)
    p.add_argument("--rule-display-names", type=Path, default=None)
    args = p.parse_args(argv)

    scan_raw = L.load_scan(args.input)
    ownership_map = L.load_optional_mapping(args.ownership_map)
    rule_display = L.load_optional_mapping(args.rule_display_names)
    scan = L.normalize(
        scan=scan_raw,
        ownership_map=ownership_map or None,
        rule_display_lookup=rule_display or None,
        cop_guidance=None,
    )

    html = _render(scan, args.org_display_name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")

    print(f"Wrote {args.output}")
    _summary_stdout(scan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
