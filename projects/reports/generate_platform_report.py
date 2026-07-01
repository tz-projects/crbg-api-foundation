"""Platform team governance report generator — v2 spec.

Dense reference HTML for app dev teams + CSV side-car. The HTML is fully
self-contained: vanilla JS for filter/sort, data embedded as a JSON constant
in a <script> tag, no external assets.

Sections degrade per the v2 tier model:
- Tier 1 (Studio) sections always render.
- Tier 2 (ownership map) sections render only when the map is present.
- The "per-team summary" section is replaced by a "per-rule" view when the
  ownership map is absent — different cut, equally useful for CoP work.

Usage:
    python generate_platform_report.py \\
        --input output/scan.json \\
        --output-dir output/platform-report \\
        --org-display-name "Acme Corporation" \\
        --studio-base-url https://app.swaggerhub.com/apis \\
        [--ownership-map ownership.yaml] \\
        [--rule-display-names rule_display_names.yaml] \\
        [--cop-guidance cop_guidance.yaml] \\
        [--per-team-threshold 5]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import _lib as L

# ---- CSV --------------------------------------------------------------------

_CSV_FIELDS = [
    "team",
    "team_contact_email",
    "domain",
    "api_owner",
    "api_name",
    "api_version",
    "api_studio_url",
    "rule_id",
    "rule_humanized_name",
    "severity",
    "line",
    "message",
    "cop_guidance_url",
    "scan_timestamp",
]


def _write_csv(scan: L.NormalizedScan, studio_base: str, cop_guidance: dict[str, str],
               out_path: Path) -> Path:
    """One row per finding. APIs with no findings still appear (blank rule cols)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        w.writeheader()
        for api in scan.apis:
            base = {
                "team": api.team or "",
                "team_contact_email": api.contact_email or "",
                "domain": api.domain or "",
                "api_owner": api.owner,
                "api_name": api.name,
                "api_version": api.version,
                "api_studio_url": api.studio_url(studio_base),
                "scan_timestamp": api.scanned_at.isoformat() if api.scanned_at else "",
            }
            if not api.findings:
                w.writerow({**base, "rule_id": "", "rule_humanized_name": "",
                            "severity": "", "line": "", "message": "",
                            "cop_guidance_url": ""})
                continue
            for fnd in api.findings:
                w.writerow({
                    **base,
                    "rule_id": fnd.rule_id,
                    "rule_humanized_name": fnd.rule_display,
                    "severity": L.sev_label(fnd.severity),
                    "line": fnd.line if fnd.line is not None else "",
                    "message": fnd.message,
                    "cop_guidance_url": cop_guidance.get(fnd.rule_id, ""),
                })
    return out_path


# ---- HTML section renderers -------------------------------------------------


def _header(scan: L.NormalizedScan, org_display: str) -> str:
    return f"""
      <header>
        <h1>API Governance Findings — Platform Team Report</h1>
        <p class="meta">{L.esc(org_display)} &middot; scan {L.esc(L.fmt_date(scan.scanned_at))}</p>
        <p class="meta">
          {scan.api_count} APIs scanned &middot;
          <span class="pill pass">PASS {scan.pass_count}</span>
          <span class="pill warn">WARN {scan.warn_count}</span>
          <span class="pill fail">FAIL {scan.fail_count}</span>
          <span class="pill err">SCAN_ERROR {scan.error_count}</span>
          &middot; {len(scan.all_findings)} findings
        </p>
      </header>
    """


def _howto(scan: L.NormalizedScan) -> str:
    ownership_note = ""
    if scan.has_ownership:
        ownership_note = (
            f'<li class="muted">Ownership map covers {scan.ownership_coverage_pct:.0f}% of scanned APIs; '
            "unmapped APIs appear in the Orphan section.</li>"
        )
    cop_note = (
        "CoP guidance links present."
        if scan.has_cop_guidance
        else 'CoP guidance lookup not provided — affected rows read "guidance pending."'
    )
    return f"""
      <section>
        <h2>How to use this report</h2>
        <ul>
          <li>Use the filters above the findings table to narrow by team, rule, severity, or status.</li>
          <li>Each rule card links to its CoP remediation guidance (when published).</li>
          <li>Findings are sorted by API, then by severity descending.</li>
          <li>Questions: contact the platform team.</li>
          {ownership_note}
          <li class="muted">{L.esc(cop_note)}</li>
        </ul>
      </section>
    """


# --- Rule reference cards ----------------------------------------------------


def _rule_cards(scan: L.NormalizedScan, cop_guidance: dict[str, str]) -> str:
    by_rule: dict[str, list[tuple[L.ApiView, L.FindingView]]] = defaultdict(list)
    for a in scan.apis:
        for f in a.findings:
            by_rule[f.rule_id].append((a, f))
    if not by_rule:
        return ""

    cards = []
    for rule_id in sorted(by_rule, key=lambda r: (-len(by_rule[r]), r)):
        entries = by_rule[rule_id]
        sample_api, sample_finding = entries[0]
        apis_failing = len({a.slug for a, _ in entries})
        sev_set = {f.severity for _, f in entries}
        sev = next(iter(sev_set)) if len(sev_set) == 1 else "mixed"
        cop_url = cop_guidance.get(rule_id)
        guidance_html = (
            f'<a href="{L.esc(cop_url)}" target="_blank" rel="noopener">CoP remediation guidance</a>'
            if cop_url
            else '<span class="muted">guidance pending &mdash; contact platform team</span>'
        )
        snippet_html = ""
        if sample_finding.line is not None:
            snippet_html = (
                f'<p class="muted">Example: {L.esc(sample_api.slug)} '
                f"line {sample_finding.line}: {L.esc(L.truncate(sample_finding.message, 160))}</p>"
            )
        cards.append(f"""
          <article class="rule-card" id="rule-{L.esc(rule_id)}">
            <header>
              <code>{L.esc(rule_id)}</code>
              <span class="rule-display">{L.esc(sample_finding.rule_display)}</span>
              <span class="pill sev-{L.esc(sev.lower())}">{L.esc(L.sev_label(sev))}</span>
            </header>
            <p>APIs failing: <strong>{apis_failing}</strong>
               &middot; Total findings: <strong>{len(entries)}</strong></p>
            <p class="rule-desc">{L.esc(sample_finding.message)}</p>
            {snippet_html}
            <p>{guidance_html}</p>
          </article>
        """)
    return f"""
      <section>
        <h2>Rule reference</h2>
        <div class="rule-grid">{''.join(cards)}</div>
      </section>
    """


# --- Findings table (filterable) ---------------------------------------------


def _findings_table(scan: L.NormalizedScan, studio_base: str, cop_guidance: dict[str, str]) -> str:
    rows: list[dict[str, object]] = []
    for api in scan.apis:
        for f in api.findings:
            rows.append({
                "team": api.team or "",
                "api_owner": api.owner,
                "api_name": api.name,
                "api_version": api.version,
                "api_slug": api.slug,
                "rule_id": f.rule_id,
                "rule_display": f.rule_display,
                "severity": f.severity,
                "status": api.status.upper(),
                "line": f.line if f.line is not None else "",
                "message": f.message,
                "studio_url": api.studio_url(studio_base),
                "cop_url": cop_guidance.get(f.rule_id, ""),
                "created_at": api.created_at.isoformat() if api.created_at else "",
                "modified_at": api.modified_at.isoformat() if api.modified_at else "",
                # Tri-state: True / False / None — JS treats None as "unknown."
                "is_published": api.is_published,
                "is_default_version": api.is_default_version,
            })

    rules = sorted({r["rule_id"] for r in rows})
    severities = ["CRITICAL", "WARNING", "INFO"]
    statuses = ["PASS", "WARN", "FAIL", "ERROR"]

    team_filter = ""
    if scan.has_ownership:
        teams = sorted({r["team"] for r in rows if r["team"]})
        team_filter = (
            '<label>Team <select id="f-team"><option value="">all</option>'
            + "".join(f'<option>{L.esc(t)}</option>' for t in teams)
            + "</select></label>"
        )

    pub_filter = ""
    if scan.has_published_data:
        pub_filter = (
            '<label>Published <select id="f-published">'
            '<option value="">all</option>'
            '<option value="yes">yes</option>'
            '<option value="no">no (draft)</option>'
            '<option value="unknown">unknown</option>'
            "</select></label>"
        )

    rule_options = "".join(f'<option value="{L.esc(r)}">{L.esc(r)}</option>' for r in rules)
    sev_options = "".join(f'<option value="{s}">{L.sev_label(s)}</option>' for s in severities)
    status_options = "".join(f"<option>{s}</option>" for s in statuses)

    # Column header set differs by tier; "Published" is a Tier 1 column
    # included whenever any API has a known publish state.
    columns: list[str] = []
    if scan.has_ownership:
        columns.append("Team")
    if scan.has_published_data:
        columns.append("Published")
    if not scan.has_ownership and scan.has_default_version_data:
        columns.append("Default")
    columns += ["API", "Version", "Rule", "Severity", "Line", "Message", "Links"]
    if not scan.has_ownership:
        columns += ["Created", "Modified"]
    thead = "".join(f"<th>{c}</th>" for c in columns)

    # Embed the data + render options for the client-side filter logic.
    data_json = json.dumps(rows, ensure_ascii=False)
    options_json = json.dumps(
        {
            "showTeam": scan.has_ownership,
            "showPublished": scan.has_published_data,
            "showDefault": (not scan.has_ownership) and scan.has_default_version_data,
            "showAgeCols": not scan.has_ownership,
        }
    )

    return f"""
      <section>
        <h2>Findings ({len(rows)})</h2>
        <div class="filters">
          {team_filter}
          {pub_filter}
          <label>Severity <select id="f-severity"><option value="">all</option>{sev_options}</select></label>
          <label>Status <select id="f-status"><option value="">all</option>{status_options}</select></label>
          <label>Rule <select id="f-rule"><option value="">all</option>{rule_options}</select></label>
          <label>Search <input id="f-search" type="search" placeholder="API name…" /></label>
          <button id="dl-csv" type="button">Download filtered CSV</button>
        </div>
        <p id="row-status" class="muted"></p>
        <div class="table-wrap">
          <table id="findings-table">
            <thead><tr>{thead}</tr></thead>
            <tbody></tbody>
          </table>
        </div>
        <div class="pager">
          <button id="prev" type="button">Prev</button>
          <span id="page-info"></span>
          <button id="next" type="button">Next</button>
        </div>
        <script id="findings-data" type="application/json">{data_json}</script>
        <script id="findings-options" type="application/json">{options_json}</script>
        <script>{_FINDINGS_JS}</script>
      </section>
    """


_FINDINGS_JS = r"""
(() => {
  const opts = JSON.parse(document.getElementById('findings-options').textContent);
  const showTeam = !!opts.showTeam;
  const showPublished = !!opts.showPublished;
  const showDefault = !!opts.showDefault;
  const showAgeCols = !!opts.showAgeCols;
  const data = JSON.parse(document.getElementById('findings-data').textContent);
  const PAGE_SIZE = 100;
  let page = 0;

  const $ = id => document.getElementById(id);
  const tbody = document.querySelector('#findings-table tbody');

  const escapeHtml = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

  // Display label only; the underlying value stays for filtering + pill class.
  const sevLabel = s => (String(s).toUpperCase() === 'CRITICAL' ? 'ERROR' : s);

  const fmtLinks = r => {
    const parts = [];
    if (r.studio_url) parts.push(`<a href="${escapeHtml(r.studio_url)}" target="_blank" rel="noopener">Studio</a>`);
    if (r.cop_url) parts.push(`<a href="${escapeHtml(r.cop_url)}" target="_blank" rel="noopener">CoP</a>`);
    parts.push(`<a href="#rule-${encodeURIComponent(r.rule_id)}">rule</a>`);
    return parts.join(' &middot; ');
  };

  const fmtTriState = (v, yesLabel, noLabel) => {
    if (v === true) return `<span class="pill pub-yes">${yesLabel}</span>`;
    if (v === false) return `<span class="pill pub-no">${noLabel}</span>`;
    return '<span class="muted">—</span>';
  };

  const fmtRow = r => {
    const cells = [];
    if (showTeam) cells.push(escapeHtml(r.team || 'unassigned'));
    if (showPublished) cells.push(fmtTriState(r.is_published, 'yes', 'draft'));
    if (showDefault) cells.push(fmtTriState(r.is_default_version, 'default', 'older'));
    cells.push(escapeHtml(r.api_name));
    cells.push(escapeHtml(r.api_version));
    cells.push(`<code>${escapeHtml(r.rule_id)}</code><div class="cell-sub">${escapeHtml(r.rule_display)}</div>`);
    cells.push(`<span class="pill sev-${escapeHtml(r.severity.toLowerCase())}">${escapeHtml(sevLabel(r.severity))}</span>`);
    cells.push(escapeHtml(r.line));
    cells.push(escapeHtml(r.message));
    cells.push(fmtLinks(r));
    if (showAgeCols) {
      cells.push(escapeHtml((r.created_at || '').slice(0, 10) || '—'));
      cells.push(escapeHtml((r.modified_at || '').slice(0, 10) || '—'));
    }
    return '<tr>' + cells.map(c => `<td>${c}</td>`).join('') + '</tr>';
  };

  const matchPublished = (r, choice) => {
    if (!choice) return true;
    if (choice === 'yes') return r.is_published === true;
    if (choice === 'no') return r.is_published === false;
    if (choice === 'unknown') return r.is_published == null;
    return true;
  };

  const filtered = () => {
    const team = showTeam ? $('f-team').value : '';
    const sev = $('f-severity').value;
    const status = $('f-status').value;
    const rule = $('f-rule').value;
    const search = $('f-search').value.toLowerCase();
    const pubChoice = showPublished ? $('f-published').value : '';
    return data.filter(r =>
      (!team || r.team === team) &&
      (!sev || r.severity === sev) &&
      (!status || r.status === status) &&
      (!rule || r.rule_id === rule) &&
      (!search || r.api_name.toLowerCase().includes(search)) &&
      matchPublished(r, pubChoice)
    );
  };

  const render = () => {
    const rows = filtered();
    const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    if (page >= totalPages) page = totalPages - 1;
    if (page < 0) page = 0;
    const slice = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
    tbody.innerHTML = slice.map(fmtRow).join('');
    $('row-status').textContent =
      `Showing ${slice.length} of ${rows.length} findings (total ${data.length}).`;
    $('page-info').textContent = `Page ${page + 1} of ${totalPages}`;
    $('prev').disabled = page === 0;
    $('next').disabled = page >= totalPages - 1;
  };

  const downloadCsv = () => {
    const rows = filtered();
    const cols = showTeam
      ? ['team','api_name','api_version','rule_id','rule_display','severity','line','message','studio_url','cop_url']
      : ['api_name','api_version','rule_id','rule_display','severity','line','message','studio_url','cop_url','created_at','modified_at'];
    const esc = v => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`;
    const cell = (r, c) => (c === 'severity' ? sevLabel(r[c]) : r[c]);
    const body = [cols.join(',')].concat(rows.map(r => cols.map(c => esc(cell(r, c))).join(','))).join('\n');
    const blob = new Blob([body], {type: 'text/csv;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'findings-filtered.csv'; a.click();
    URL.revokeObjectURL(url);
  };

  ['f-severity','f-status','f-rule','f-search'].forEach(id => {
    const el = $(id);
    if (el) el.addEventListener('input', () => { page = 0; render(); });
  });
  if (showTeam) $('f-team').addEventListener('input', () => { page = 0; render(); });
  if (showPublished) $('f-published').addEventListener('input', () => { page = 0; render(); });
  $('prev').addEventListener('click', () => { page--; render(); });
  $('next').addEventListener('click', () => { page++; render(); });
  $('dl-csv').addEventListener('click', downloadCsv);

  render();
})();
"""


# --- Team or Rule grouping ---------------------------------------------------


def _per_team_or_per_rule(scan: L.NormalizedScan, per_team_dir_name: str) -> str:
    if scan.has_ownership:
        return _per_team_summary(scan, per_team_dir_name)
    return _per_rule_summary(scan)


def _per_team_summary(scan: L.NormalizedScan, per_team_dir_name: str) -> str:
    teams = L.team_summaries(scan)
    if not teams:
        return ""
    rows = []
    for t in teams:
        top_rules = ", ".join(f"{L.esc(name)} ({c})" for name, c in t.top_rules) or "—"
        team_slug = _slugify(t.team)
        rows.append(f"""
          <tr>
            <td>{L.esc(t.team)}</td>
            <td>{L.esc(t.domain or '—')}</td>
            <td>{L.esc(t.contact_email or '—')}</td>
            <td>{t.owned}</td>
            <td>{t.failing}</td>
            <td>{t.findings_critical} / {t.findings_warning}</td>
            <td>{top_rules}</td>
            <td><a href="{L.esc(per_team_dir_name)}/{L.esc(team_slug)}.html">subset</a></td>
          </tr>
        """)
    return f"""
      <section>
        <h2>Per-team summary</h2>
        <table>
          <thead>
            <tr><th>Team</th><th>Domain</th><th>Contact</th><th>APIs</th><th>Failing</th>
                <th>Errors / Warn</th><th>Top rules</th><th>Subset</th></tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </section>
    """


def _per_rule_summary(scan: L.NormalizedScan) -> str:
    pareto = L.rule_pareto(scan, top_n=100)
    if not pareto:
        return ""
    rows = []
    for p in pareto:
        apis = L.apis_failing_rule(scan, p.rule_id)
        api_list = ", ".join(L.esc(a.slug) for a in apis[:8])
        if len(apis) > 8:
            api_list += f", &hellip; (+{len(apis) - 8} more)"
        rows.append(f"""
          <tr>
            <td><a href="#rule-{L.esc(p.rule_id)}"><code>{L.esc(p.rule_id)}</code></a></td>
            <td>{L.esc(p.rule_display)}</td>
            <td><span class="pill sev-{L.esc(p.severity.lower())}">{L.esc(L.sev_label(p.severity))}</span></td>
            <td>{p.count}</td>
            <td>{len(apis)}</td>
            <td>{api_list}</td>
          </tr>
        """)
    return f"""
      <section>
        <h2>APIs grouped by rule violation</h2>
        <p class="muted">Per-team grouping requires the ownership map. This per-rule cut serves
        the same remediation workflow — each row is a CoP guidance unit and the list of APIs to fix.</p>
        <table>
          <thead><tr><th>Rule</th><th>Name</th><th>Severity</th><th>Findings</th><th>APIs failing</th><th>APIs</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </section>
    """


# --- Per-API summary ---------------------------------------------------------


def _per_api_summary(scan: L.NormalizedScan, studio_base: str) -> str:
    if not scan.apis:
        return ""
    blocks = []
    for api in sorted(scan.apis, key=lambda a: a.slug):
        team = L.esc(api.team) if api.team else '<span class="muted">unassigned</span>'
        pub_pill = ""
        if api.is_published is True:
            pub_pill = '<span class="pill pub-yes">published</span>'
        elif api.is_published is False:
            pub_pill = '<span class="pill pub-no">draft</span>'
        default_pill = (
            '<span class="pill default-yes">default</span>'
            if api.is_default_version is True
            else ""
        )
        dates_html = ""
        if api.created_at or api.modified_at:
            created = api.created_at.strftime("%Y-%m-%d") if api.created_at else "—"
            modified = api.modified_at.strftime("%Y-%m-%d") if api.modified_at else "—"
            dates_html = (
                f'<span class="muted">created {L.esc(created)} · modified {L.esc(modified)}</span>'
            )
        findings_html = ""
        if api.findings:
            items = "".join(
                f"<li><span class=\"pill sev-{L.esc(f.severity.lower())}\">{L.esc(L.sev_label(f.severity))}</span> "
                f"<code>{L.esc(f.rule_id)}</code> &mdash; {L.esc(f.message)}"
                + (f" <span class=\"muted\">(line {f.line})</span>" if f.line is not None else "")
                + "</li>"
                for f in api.findings
            )
            findings_html = f"<details><summary>{len(api.findings)} finding(s)</summary><ul class=\"findings-list\">{items}</ul></details>"
        elif api.status == "error":
            findings_html = f'<p class="muted">scan error: {L.esc(api.error or "unknown")}</p>'
        else:
            findings_html = '<p class="muted">no findings</p>'

        blocks.append(f"""
          <article class="api-card">
            <header>
              <strong>{L.esc(api.name)}</strong> v{L.esc(api.version)}
              <span class="pill status-{L.esc(api.status)}">{L.esc(api.status.upper())}</span>
              {pub_pill}
              {default_pill}
              <span class="muted">errors {api.critical_count} / warnings {api.warning_count}</span>
              <span class="muted">team: {team}</span>
              {dates_html}
              <a href="{L.esc(api.studio_url(studio_base))}" target="_blank" rel="noopener">open in Studio</a>
            </header>
            <p class="muted">scanned {L.esc(L.fmt_datetime(api.scanned_at))}</p>
            {findings_html}
          </article>
        """)
    return f"""
      <section>
        <h2>Per-API summary</h2>
        <details><summary>Expand all APIs ({len(blocks)})</summary>
          <div class="api-grid">{''.join(blocks)}</div>
        </details>
      </section>
    """


# --- Orphan / unmapped APIs --------------------------------------------------


def _orphan_section(scan: L.NormalizedScan) -> str:
    if scan.has_ownership:
        orphans = [a for a in scan.apis if not a.team]
        if not orphans:
            return """
              <section>
                <h2>Orphan APIs</h2>
                <p class="muted">Every scanned API has an ownership map entry.</p>
              </section>
            """
        header = "Orphan APIs"
        intro = (
            "APIs in Studio with no ownership map entry. Track these down and add them to "
            "the ownership map so future reports can attribute them."
        )
    else:
        orphans = list(scan.apis)
        header = "Unmapped APIs (all)"
        intro = (
            "The ownership map is not yet configured; until it is, every scanned API is "
            "listed here. Once configured, this section will show only APIs missing from the map."
        )

    rows = "".join(
        f"<tr><td>{L.esc(a.owner)}</td><td>{L.esc(a.name)}</td><td>{L.esc(a.version)}</td>"
        f"<td>{L.esc(a.status.upper())}</td><td>{len(a.findings)}</td></tr>"
        for a in sorted(orphans, key=lambda a: a.slug)
    )
    return f"""
      <section>
        <h2>{L.esc(header)}</h2>
        <p class="muted">{L.esc(intro)}</p>
        <table>
          <thead><tr><th>Owner</th><th>API</th><th>Version</th><th>Status</th><th>Findings</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
    """


def _scan_errors_section(scan: L.NormalizedScan) -> str:
    errs = [a for a in scan.apis if a.status == "error"]
    if not errs:
        return """
          <section>
            <h2>Scan errors</h2>
            <p class="muted">No APIs failed to scan in this run.</p>
          </section>
        """
    rows = "".join(
        f"<tr><td>{L.esc(a.slug)}</td><td>{L.esc(a.error or 'unknown')}</td></tr>"
        for a in errs
    )
    return f"""
      <section>
        <h2>Scan errors</h2>
        <p class="muted">These APIs could not be evaluated and are excluded from conformance counts.</p>
        <table>
          <thead><tr><th>API</th><th>Reason</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
    """


def _methodology(scan: L.NormalizedScan) -> str:
    own_line = ""
    if scan.has_ownership:
        own_line = (
            f'<p>Ownership map: covers {scan.ownership_coverage_pct:.0f}% of scanned APIs.</p>'
        )
    return f"""
      <footer>
        <h2>Methodology and definitions</h2>
        <p>Scan timestamp: {L.esc(L.fmt_datetime(scan.scanned_at))}.</p>
        <p><strong>Status:</strong>
          PASS = no findings; WARN = warnings only (publishable); FAIL = at least one ERROR
          finding (blocks publish); SCAN_ERROR = scanner could not evaluate the API.
        </p>
        <p><strong>Severity:</strong>
          ERROR = governance violation that blocks publish; WARNING = quality gap that does
          not block publish but indicates non-conformance.
        </p>
        {own_line}
        <p class="muted">To request a rule exception or report a false positive, contact the platform team.</p>
      </footer>
    """


# --- Per-team subset reports -------------------------------------------------


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-") or "team"


def _write_per_team_reports(scan: L.NormalizedScan, out_dir: Path, studio_base: str,
                            cop_guidance: dict[str, str], threshold: int) -> list[Path]:
    """One mini-report per team with > threshold failing APIs. Only when ownership map present."""
    written: list[Path] = []
    if not scan.has_ownership:
        return written
    by_team: dict[str, list[L.ApiView]] = defaultdict(list)
    for a in scan.apis:
        if a.team:
            by_team[a.team].append(a)
    for team, apis in by_team.items():
        failing = [a for a in apis if a.status in ("fail", "warn")]
        if len(failing) <= threshold:
            continue
        subset = L.NormalizedScan(
            org=scan.org,
            scanned_at=scan.scanned_at,
            ruleset_name=scan.ruleset_name,
            apis=apis,
            has_age_data=scan.has_age_data,
            has_ownership=True,
            ownership_coverage_pct=100.0,
            has_rule_display_lookup=scan.has_rule_display_lookup,
            has_cop_guidance=scan.has_cop_guidance,
        )
        html = _render_page(
            subset,
            org_display=f"{scan.org} — team {team}",
            studio_base=studio_base,
            cop_guidance=cop_guidance,
            per_team_dir_name="",  # subset has no nested per-team links
            include_team_section=False,
        )
        path = out_dir / f"{_slugify(team)}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        written.append(path)
    return written


# --- Page assembly -----------------------------------------------------------


_CSS = """
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body {
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1a1a1a; background: #fff; margin: 0; padding: 24px 32px; max-width: 1200px; margin-left: auto; margin-right: auto;
  }
  h1 { margin: 0 0 4px; }
  h2 { margin: 28px 0 12px; padding-bottom: 6px; border-bottom: 1px solid #e0e0e0; font-size: 18px; }
  code { background: #f1f3f8; padding: 1px 6px; border-radius: 3px; font-size: 13px; }
  .meta { color: #555; font-size: 13px; margin: 0 0 6px; }
  .muted { color: #777; }
  .pill { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
  .pill.pass { background: #e3f5e1; color: #225e1c; }
  .pill.warn { background: #fff3cd; color: #7a5b00; }
  .pill.fail { background: #fde2e1; color: #7a1d18; }
  .pill.err  { background: #e5e7eb; color: #374151; }
  .pill.sev-critical { background: #fde2e1; color: #7a1d18; }
  .pill.sev-warning  { background: #fff3cd; color: #7a5b00; }
  .pill.sev-info     { background: #e0ecff; color: #1a3d7a; }
  .pill.sev-mixed    { background: #ede0ff; color: #4b2076; }
  .pill.status-pass { background: #e3f5e1; color: #225e1c; }
  .pill.status-warn { background: #fff3cd; color: #7a5b00; }
  .pill.status-fail { background: #fde2e1; color: #7a1d18; }
  .pill.status-error { background: #e5e7eb; color: #374151; }
  .pill.pub-yes { background: #e0ecff; color: #1a3d7a; }
  .pill.pub-no  { background: #f1ecff; color: #4b2076; }
  .pill.default-yes { background: #f3f0e0; color: #5a4a14; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #eee; vertical-align: top; }
  th { background: #f7f7f5; font-weight: 600; }
  .filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 10px 0; }
  .filters label { font-size: 13px; }
  .filters select, .filters input { font-size: 13px; padding: 4px 6px; margin-left: 4px; }
  .filters button, .pager button { font-size: 13px; padding: 4px 10px; cursor: pointer; }
  .pager { display: flex; gap: 12px; align-items: center; margin-top: 10px; }
  .table-wrap { overflow-x: auto; }
  .rule-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 12px; }
  .rule-card { border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px 14px; background: #fafafa; }
  .rule-card header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
  .rule-card .rule-display { font-weight: 600; }
  .rule-card p { margin: 6px 0; font-size: 13px; }
  .rule-card .rule-desc { color: #333; }
  .cell-sub { color: #777; font-size: 12px; }
  .api-grid { display: grid; gap: 10px; }
  .api-card { border: 1px solid #e6e6e6; border-radius: 4px; padding: 8px 12px; }
  .api-card header { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
  .findings-list { font-size: 13px; padding-left: 18px; }
  footer { margin-top: 40px; padding-top: 16px; border-top: 1px solid #ddd; font-size: 13px; color: #444; }
"""


def _render_page(scan: L.NormalizedScan, org_display: str, studio_base: str,
                 cop_guidance: dict[str, str], per_team_dir_name: str,
                 include_team_section: bool) -> str:
    middle_section = _per_team_or_per_rule(scan, per_team_dir_name) if include_team_section else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>API Governance Findings — Platform Team Report — {L.esc(org_display)}</title>
  <style>{_CSS}</style>
</head>
<body>
{_header(scan, org_display)}
{_howto(scan)}
{_rule_cards(scan, cop_guidance)}
{_findings_table(scan, studio_base, cop_guidance)}
{middle_section}
{_per_api_summary(scan, studio_base)}
{_orphan_section(scan)}
{_scan_errors_section(scan)}
{_methodology(scan)}
</body>
</html>
"""


# ---- CLI --------------------------------------------------------------------


def _summary_stdout(scan: L.NormalizedScan, out_paths: list[Path], per_team_paths: list[Path]) -> None:
    print("Platform team report — render summary")
    for p in out_paths:
        print(f"  wrote {p}")
    if scan.has_ownership:
        print(f"  Tier 2 (ownership): per-team summary rendered, {scan.ownership_coverage_pct:.0f}% coverage")
        print(f"  per-team subset reports: {len(per_team_paths)}")
    else:
        print("  Tier 1 substitute: per-rule summary in place of per-team; no subset reports")
    print(f"  Tier 3 rule display names: {'present' if scan.has_rule_display_lookup else 'not provided'}")
    print(f"  Tier 3 CoP guidance: {'present' if scan.has_cop_guidance else 'not provided'}")
    if not scan.ruleset_name:
        print("  Note: ruleset name/version not in scan input (scanner patch pending).")
    if not scan.has_age_data:
        print("  Note: created_at / modified_at not in scan input (scanner patch pending).")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate the platform team governance report.")
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--org-display-name", required=True)
    p.add_argument("--studio-base-url", required=True)
    p.add_argument("--ownership-map", type=Path, default=None)
    p.add_argument("--rule-display-names", type=Path, default=None)
    p.add_argument("--cop-guidance", type=Path, default=None)
    p.add_argument("--per-team-threshold", type=int, default=5)
    args = p.parse_args(argv)

    scan_raw = L.load_scan(args.input)
    ownership = L.load_optional_mapping(args.ownership_map)
    rule_display = L.load_optional_mapping(args.rule_display_names)
    cop = L.load_optional_mapping(args.cop_guidance)
    scan = L.normalize(
        scan=scan_raw,
        ownership_map=ownership or None,
        rule_display_lookup=rule_display or None,
        cop_guidance=cop or None,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    index_path = args.output_dir / "index.html"
    csv_path = args.output_dir / "findings.csv"
    per_team_dir = args.output_dir / "per-team"

    html = _render_page(
        scan,
        org_display=args.org_display_name,
        studio_base=args.studio_base_url,
        cop_guidance=cop or {},
        per_team_dir_name="per-team",
        include_team_section=True,
    )
    index_path.write_text(html, encoding="utf-8")
    _write_csv(scan, args.studio_base_url, cop or {}, csv_path)
    per_team_paths = _write_per_team_reports(
        scan, per_team_dir, args.studio_base_url, cop or {}, args.per_team_threshold
    )

    _summary_stdout(scan, [index_path, csv_path] + per_team_paths, per_team_paths)
    return 0


if __name__ == "__main__":
    sys.exit(main())
