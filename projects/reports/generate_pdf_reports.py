"""PDF governance reports — executive + platform — via reportlab.

Reads the same scanner ``scan.json`` the HTML generators use (through the
shared ``_lib`` normalization layer) and renders two PDFs:

  - executive-report.pdf   CIO-facing single-page summary
  - platform-report.pdf    dense reference for app dev teams

Unlike the HTML generators (standard-library only), this one needs reportlab:

    pip install reportlab

reportlab is pure-Python-installable and runs anywhere Python runs — locally,
on a VDI, and on AWS Lambda (bundle it in the reports package). The PDFs are
generated directly from the scan data, not converted from HTML, so they need
no browser and render identically in every environment.

Usage:

    python generate_pdf_reports.py \\
        --input output/scan.json \\
        --output-dir output \\
        --org-display-name "Acme Corporation" \\
        --studio-base-url https://app.swaggerhub.com/apis \\
        [--ownership-map ownership.yaml] \\
        [--rule-display-names rule_display_names.yaml] \\
        [--asks-file asks.md] [--placeholder-ask]

Exit codes: 0 ok; 2 reportlab not installed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import _lib as L

# Importing this module never fails hard, so callers (e.g. the Lambda handler)
# can import it and check REPORTLAB_AVAILABLE before generating PDFs.
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph as P,
    )
    from reportlab.platypus import (
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def _require_reportlab() -> None:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError(
            "reportlab is required for PDF reports. Install it with:\n"
            "    pip install reportlab"
        )


# --- Shared styling (only defined when reportlab is present) -------------------

if REPORTLAB_AVAILABLE:
    _CRITICAL = colors.HexColor("#b00020")
    _WARNING = colors.HexColor("#8a6d00")
    _OK = colors.HexColor("#1b6e2e")
    _INK = colors.HexColor("#1a1a1a")
    _MUTED = colors.HexColor("#5a5a5a")
    _RULE = colors.HexColor("#d0d0d0")
    _HEADER_BG = colors.HexColor("#f0f2f5")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    s = {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontSize=20, textColor=_INK, spaceAfter=4
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"], fontSize=12, textColor=_MUTED, spaceAfter=2
        ),
        "meta": ParagraphStyle(
            "meta", parent=base["Normal"], fontSize=9, textColor=_MUTED, spaceAfter=2
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=13, textColor=_INK,
            spaceBefore=14, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontSize=10, textColor=_INK,
            leading=14, spaceAfter=6,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["Normal"], fontSize=8.5, textColor=_INK, leading=11
        ),
        "cellhead": ParagraphStyle(
            "cellhead", parent=base["Normal"], fontSize=8.5, textColor=_INK,
            leading=11, fontName="Helvetica-Bold",
        ),
    }
    return s


def _sev_color(sev: str):
    return {"CRITICAL": _CRITICAL, "WARNING": _WARNING}.get(sev.upper(), _MUTED)


def _table(data: list[list], col_widths: list[float], header: bool = True) -> Table:
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, _RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), _HEADER_BG),
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, _RULE),
        ]
    t.setStyle(TableStyle(style))
    return t


def _doc(path: Path, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        title=title,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
    )


# --- Executive report ---------------------------------------------------------


def build_executive_pdf(
    scan: L.NormalizedScan,
    org_display: str,
    out_path: Path,
    asks_text: str | None,
    placeholder: bool,
) -> Path:
    _require_reportlab()
    st = _styles()
    story: list = []

    ruleset = L.esc(scan.ruleset_name) if scan.ruleset_name else "ruleset version not recorded"
    story.append(P("API Governance Conformance — Baseline Report", st["title"]))
    story.append(P(L.esc(org_display), st["subtitle"]))
    story.append(P(f"Scan date: {L.esc(L.fmt_date(scan.scanned_at))}", st["meta"]))
    excl = scan.error_count
    story.append(P(
        f"Scanned {scan.api_count} APIs in Swagger Studio against {ruleset}. "
        f"{excl} API{'s' if excl != 1 else ''} could not be scanned and are excluded "
        f"from conformance counts.",
        st["meta"],
    ))

    # Headline tiles
    story.append(P("Conformance at a glance", st["h2"]))
    tiles = [
        [P("Pass", st["cellhead"]), P("Warn only", st["cellhead"]),
         P("Fail", st["cellhead"]), P("Excluded", st["cellhead"])],
        [
            P(f"{scan.pass_count}  ({L.fmt_pct(scan.pass_pct)})", st["cell"]),
            P(f"{scan.warn_count}  ({L.fmt_pct(scan.warn_only_pct)})", st["cell"]),
            P(f"{scan.fail_count}  ({L.fmt_pct(scan.fail_pct)})", st["cell"]),
            P(f"{scan.error_count}", st["cell"]),
        ],
    ]
    usable = 7.1 * inch
    story.append(_table(tiles, [usable / 4] * 4))
    story.append(Spacer(1, 6))
    story.append(P(
        f"Of {scan.scannable_count} scannable APIs, {L.fmt_pct(scan.pass_pct)} fully "
        f"conform; {L.fmt_pct(scan.fail_pct)} have at least one critical finding.",
        st["body"],
    ))

    # Pareto
    pareto = L.rule_pareto(scan, top_n=10)
    if pareto:
        story.append(P("Where the failures concentrate (top rules)", st["h2"]))
        rows = [[P("Rule", st["cellhead"]), P("Severity", st["cellhead"]),
                 P("Count", st["cellhead"]), P("Share", st["cellhead"]),
                 P("Cumulative", st["cellhead"])]]
        for e in pareto:
            rows.append([
                P(L.esc(e.rule_display), st["cell"]),
                P(L.esc(e.severity), ParagraphStyle("s", parent=st["cell"], textColor=_sev_color(e.severity))),
                P(str(e.count), st["cell"]),
                P(L.fmt_pct(e.share_pct), st["cell"]),
                P(L.fmt_pct(e.cumulative_pct), st["cell"]),
            ])
        story.append(_table(rows, [usable * 0.40, usable * 0.15, usable * 0.13, usable * 0.16, usable * 0.16]))

    # Severity context
    crit = sum(a.critical_count for a in scan.apis)
    warn = sum(a.warning_count for a in scan.apis)
    story.append(P("Finding severity", st["h2"]))
    story.append(P(
        f"{crit} critical and {warn} warning findings across all scanned APIs. "
        f"Critical findings are what move an API into the Fail bucket.",
        st["body"],
    ))

    # Ask
    if placeholder and not asks_text:
        asks_text = (
            "The platform team will drive remediation through phased CI/CD enforcement. "
            "Successful execution requires executive endorsement of the gating milestone "
            "and dedicated remediation capacity for the top failing domains."
        )
    if asks_text:
        story.append(P("What's needed", st["h2"]))
        story.append(P(L.esc(asks_text), st["body"]))

    _doc(out_path, "API Governance — Executive Report").build(story)
    return out_path


# --- Platform report ----------------------------------------------------------


def build_platform_pdf(
    scan: L.NormalizedScan,
    org_display: str,
    out_path: Path,
    studio_base: str,
) -> Path:
    _require_reportlab()
    st = _styles()
    story: list = []
    usable = 7.1 * inch

    story.append(P("API Governance — Platform Team Report", st["title"]))
    story.append(P(L.esc(org_display), st["subtitle"]))
    story.append(P(f"Scan date: {L.esc(L.fmt_date(scan.scanned_at))}", st["meta"]))
    story.append(P(
        f"{scan.api_count} APIs scanned — "
        f"{scan.pass_count} pass, {scan.warn_count} warn, {scan.fail_count} fail, "
        f"{scan.error_count} excluded.",
        st["meta"],
    ))

    # Per-rule summary
    pareto = L.rule_pareto(scan, top_n=10_000)
    if pareto:
        story.append(P("Findings by rule", st["h2"]))
        rows = [[P("Rule", st["cellhead"]), P("Severity", st["cellhead"]),
                 P("Count", st["cellhead"]), P("Share", st["cellhead"])]]
        for e in pareto:
            rows.append([
                P(L.esc(e.rule_display), st["cell"]),
                P(L.esc(e.severity), ParagraphStyle("s", parent=st["cell"], textColor=_sev_color(e.severity))),
                P(str(e.count), st["cell"]),
                P(L.fmt_pct(e.share_pct), st["cell"]),
            ])
        story.append(_table(rows, [usable * 0.52, usable * 0.18, usable * 0.15, usable * 0.15]))

    # Per-API breakdown
    story.append(P("Per-API findings", st["h2"]))
    rows = [[P("API", st["cellhead"]), P("Status", st["cellhead"]),
             P("Crit", st["cellhead"]), P("Warn", st["cellhead"])]]
    for a in sorted(scan.apis, key=lambda x: (x.status != "fail", x.slug)):
        status_color = {"pass": _OK, "fail": _CRITICAL, "warn": _WARNING}.get(a.status, _MUTED)
        rows.append([
            P(L.esc(a.slug), st["cell"]),
            P(L.esc(a.status.upper()), ParagraphStyle("st", parent=st["cell"], textColor=status_color)),
            P(str(a.critical_count), st["cell"]),
            P(str(a.warning_count), st["cell"]),
        ])
    story.append(_table(rows, [usable * 0.64, usable * 0.16, usable * 0.10, usable * 0.10]))

    # Detailed findings (capped to keep the PDF reasonable)
    all_findings = [(a, f) for a in scan.apis for f in a.findings]
    if all_findings:
        cap = 200
        story.append(P("Findings detail", st["h2"]))
        if len(all_findings) > cap:
            story.append(P(
                f"Showing the first {cap} of {len(all_findings)} findings. "
                f"For the complete list use the CSV side-car from the HTML report.",
                st["meta"],
            ))
        rows = [[P("API", st["cellhead"]), P("Rule", st["cellhead"]),
                 P("Sev", st["cellhead"]), P("Line", st["cellhead"])]]
        for a, f in all_findings[:cap]:
            rows.append([
                P(L.esc(a.slug), st["cell"]),
                P(L.esc(f.rule_display), st["cell"]),
                P(L.esc(f.severity), ParagraphStyle("s", parent=st["cell"], textColor=_sev_color(f.severity))),
                P(str(f.line) if f.line is not None else "—", st["cell"]),
            ])
        story.append(_table(rows, [usable * 0.34, usable * 0.42, usable * 0.14, usable * 0.10]))

    _doc(out_path, "API Governance — Platform Report").build(story)
    return out_path


# --- Convenience for programmatic callers (e.g. the Lambda handler) -----------


def build_all(
    scan: L.NormalizedScan,
    org_display: str,
    out_dir: Path,
    studio_base: str = "https://app.swaggerhub.com/apis",
    asks_text: str | None = None,
    placeholder: bool = True,
) -> tuple[Path, Path]:
    """Render both PDFs into out_dir; return (executive_path, platform_path)."""
    _require_reportlab()
    out_dir.mkdir(parents=True, exist_ok=True)
    exec_path = build_executive_pdf(
        scan, org_display, out_dir / "executive-report.pdf", asks_text, placeholder
    )
    plat_path = build_platform_pdf(
        scan, org_display, out_dir / "platform-report.pdf", studio_base
    )
    return exec_path, plat_path


# --- CLI ----------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    if not REPORTLAB_AVAILABLE:
        print(
            "reportlab is required for PDF reports. Install it with:\n"
            "    pip install reportlab\n"
            "(or: pip install -r requirements-pdf.txt)",
            file=sys.stderr,
        )
        return 2
    parser = argparse.ArgumentParser(description="Generate executive + platform PDF reports.")
    parser.add_argument("--input", required=True, help="scanner scan.json")
    parser.add_argument("--output-dir", required=True, help="directory for the PDFs")
    parser.add_argument("--org-display-name", required=True)
    parser.add_argument("--studio-base-url", default="https://app.swaggerhub.com/apis")
    parser.add_argument("--ownership-map")
    parser.add_argument("--rule-display-names")
    parser.add_argument("--asks-file")
    parser.add_argument("--placeholder-ask", action="store_true")
    args = parser.parse_args(argv)

    scan_dict = L.load_scan(Path(args.input))
    ownership = L.load_optional_mapping(Path(args.ownership_map)) if args.ownership_map else {}
    rule_names = L.load_optional_mapping(Path(args.rule_display_names)) if args.rule_display_names else {}
    scan = L.normalize(scan_dict, ownership, rule_names, None)

    asks_text = None
    if args.asks_file:
        asks_text = Path(args.asks_file).read_text(encoding="utf-8").strip()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    exec_path = build_executive_pdf(
        scan, args.org_display_name, out_dir / "executive-report.pdf",
        asks_text, args.placeholder_ask,
    )
    plat_path = build_platform_pdf(
        scan, args.org_display_name, out_dir / "platform-report.pdf", args.studio_base_url,
    )

    print(f"Wrote {exec_path}")
    print(f"Wrote {plat_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
