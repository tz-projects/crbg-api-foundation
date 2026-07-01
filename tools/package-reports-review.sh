#!/usr/bin/env bash
# Build a shareable "review" package of the reports-generation programs.
#
# For handing to a colleague to READ, UNDERSTAND, and RUN on their own machine
# (e.g. a Windows VDI) against their own scan.json. NOT for Lambda upload.
#
# Produces (default <repo>/dist/):  reports-generator-review.zip  containing:
#   README.md                       self-contained run + orientation guide
#   _lib.py                         shared normalization / data layer
#   generate_executive_report.py    CIO-facing HTML report
#   generate_platform_report.py     platform-team HTML report + findings.csv
#   generate_pdf_reports.py         PDF reports (reportlab)
#   html-to-pdf.py                  export the HTML reports to PDF via a browser
#   requirements-pdf.txt            pinned PDF deps (reportlab, pillow)
#   governance-reports-spec-v2.md   the design spec the generators implement
#
# Usage:  bash tools/package-reports-review.sh [output-dir]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORTS="$REPO_ROOT/projects/reports"
OUT_DIR="${1:-$REPO_ROOT/dist}"

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
PKG="$STAGE/reports-generator-review"
mkdir -p "$PKG"

# Source + spec + PDF tooling
cp "$REPORTS/_lib.py" \
   "$REPORTS/generate_executive_report.py" \
   "$REPORTS/generate_platform_report.py" \
   "$REPORTS/generate_pdf_reports.py" \
   "$REPORTS/requirements-pdf.txt" \
   "$REPORTS/governance-reports-spec-v2.md" \
   "$PKG/"
cp "$SCRIPT_DIR/html-to-pdf.py" "$PKG/"

# Self-contained README for the colleague
cat > "$PKG/README.md" <<'EOF'
# API Governance Report Generators — review copy

These Python programs turn a **scanner result file (`scan.json`)** into
readable governance reports. This copy is for reviewing the code and running
it against your own `scan.json`. It is fully self-contained and **offline** —
no network calls, no SwaggerHub, no AWS.

## What's here

| File | What it does |
|---|---|
| `generate_executive_report.py` | One-page, CIO-facing **HTML** summary |
| `generate_platform_report.py` | Dense platform-team **HTML** + `findings.csv` |
| `generate_pdf_reports.py` | The same reports as **PDF** (via reportlab) |
| `html-to-pdf.py` | Alternative PDF: prints the HTML to PDF via your browser |
| `_lib.py` | Shared layer: loads `scan.json`, normalizes it, aggregates findings |
| `governance-reports-spec-v2.md` | The **design spec** — read this to understand the intent |
| `requirements-pdf.txt` | Pinned deps for the PDF option (reportlab, pillow) |

## Prerequisites

- **Python 3.10+** (3.13 recommended). Check with `python --version`.
- The HTML generators need **nothing else** — standard library only.
- The PDF options are optional (see below).

## Run it

Put your `scan.json` in this folder, then:

**Windows PowerShell**
```powershell
# Executive HTML
python generate_executive_report.py `
    --input scan.json `
    --output output\executive-report.html `
    --org-display-name "Your Org" `
    --placeholder-ask

# Platform HTML + findings.csv
python generate_platform_report.py `
    --input scan.json `
    --output-dir output\platform-report `
    --org-display-name "Your Org" `
    --studio-base-url https://app.swaggerhub.com/apis
```

**macOS / Linux / Git Bash**
```bash
python generate_executive_report.py \
    --input scan.json \
    --output output/executive-report.html \
    --org-display-name "Your Org" \
    --placeholder-ask

python generate_platform_report.py \
    --input scan.json \
    --output-dir output/platform-report \
    --org-display-name "Your Org" \
    --studio-base-url https://app.swaggerhub.com/apis
```

Open `output/executive-report.html` and `output/platform-report/index.html`
in a browser. Every `--help` lists the full set of options (ownership map,
rule display names, CoP guidance, etc.).

> `--studio-base-url` is only used to build clickable "open in Studio" links in
> the HTML. Nothing is contacted — it's just text in the output.

## PDF (optional — two ways)

**A) Match the HTML exactly** — prints the HTML with a browser already on your
machine (Edge on Windows). No install:
```
python html-to-pdf.py output/executive-report.html output/platform-report/index.html --out-dir output
```

**B) Generate PDF directly** — needs reportlab; its layout is its own (does not
match the HTML), but it needs no browser:
```
pip install -r requirements-pdf.txt
python generate_pdf_reports.py --input scan.json --output-dir output --org-display-name "Your Org" --placeholder-ask
```

## Understanding the design

Read `governance-reports-spec-v2.md`. The short version: reports render from
three tiers — **Tier 1** is the Studio scan data (always present), **Tier 2** is
an optional ownership map (team/domain/contact), **Tier 3** is optional curated
lookups (rule display names, guidance links). Anything missing degrades to a
Tier 1 fallback rather than breaking. `_lib.py` is where `scan.json` is parsed
into the tier-aware view both generators consume.
EOF

# Zip it
rm -f "$OUT_DIR/reports-generator-review.zip"
( cd "$STAGE" && zip -r -q "$OUT_DIR/reports-generator-review.zip" reports-generator-review )

echo "Built: $OUT_DIR/reports-generator-review.zip"
echo ""
unzip -l "$OUT_DIR/reports-generator-review.zip" | awk 'NR>3 && $4 {print "  " $4}' | grep -v '/$'
