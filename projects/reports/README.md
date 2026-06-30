# reports (Python)

Generates the **executive** and **platform-team** governance reports from a scanner `scan.json` file. Pure Python, **standard library only by design** — no `uv`, no `pip install`, no virtual environment needed on the work laptop.

## Layout

```
reports/
├── _lib.py                        # Shared helpers (normalization, tier-aware view, HTML utilities)
├── generate_executive_report.py   # Single-page CIO-facing HTML
├── generate_platform_report.py    # Dense reference HTML + findings.csv for app dev teams
├── governance-reports-spec-v2.md  # Spec the generators implement
├── governance-data-gap-bridging-plan.md
├── output/                        # Default output destination
└── sample-output/                 # Checked-in examples
```

## Run them

The only requirement is Python 3.13+ (`python --version`). Both scripts run directly:

```bash
cd projects/reports

# Executive report (single self-contained HTML)
python generate_executive_report.py \
    --input ../swagger-studio-scanner/python/output/scan.json \
    --output output/executive-report.html \
    --org-display-name "Acme Corporation"

# Platform-team report (HTML + findings.csv)
python generate_platform_report.py \
    --input ../swagger-studio-scanner/python/output/scan.json \
    --output-dir output/platform-report \
    --org-display-name "Acme Corporation" \
    --studio-base-url https://app.swaggerhub.com/apis
```

On Windows replace the backslash continuations with backticks (PowerShell) or put everything on one line.

## PDF reports (optional)

There are **two** ways to get PDFs — pick based on whether you need PDFs in Lambda or want them to match the HTML exactly.

### Option A — export the HTML to PDF (matches the HTML exactly)

[`tools/html-to-pdf.py`](../../tools/html-to-pdf.py) drives a browser that's already on your machine (Edge on the Windows VDI, Chrome/Chromium on macOS/Linux) to print the generated HTML reports to PDF. **No pip install** — and because it renders the real HTML+CSS, the PDF looks exactly like the HTML report.

```bash
# After generating the HTML reports (above), convert them:
python ../../tools/html-to-pdf.py \
    output/executive-report.html \
    output/platform-report/index.html \
    --out-dir output
# -> output/executive-report.pdf, output/platform-report.pdf
```

This needs a browser, so it's a **local / VDI step — not Lambda**. That's usually fine: reports are typically finalized locally. Edge auto-detects on Windows; pass `--browser <path>` if needed.

### Option B — generate the PDF directly (runs anywhere, incl. Lambda)

`generate_pdf_reports.py` builds the PDF from the scan data using **reportlab** (a pure-Python install). It runs anywhere — including AWS Lambda — with no browser, but its layout is its own (it does **not** match the HTML).

```bash
pip install -r requirements-pdf.txt        # reportlab + pillow

python generate_pdf_reports.py \
    --input ../swagger-studio-scanner/python/output/scan.json \
    --output-dir output \
    --org-display-name "Acme Corporation" \
    --placeholder-ask
```

On Lambda, the reports function returns these PDFs base64-encoded when reportlab is available (it ships in the shared dependency layer) — see [docs/aws-lambda-lite.md](../../docs/aws-lambda-lite.md).

### Which to use

| | Option A (HTML → PDF) | Option B (reportlab) |
|---|---|---|
| Matches the HTML layout | **Yes** | No (own layout) |
| Needs a browser | Yes (local/VDI) | No |
| Runs on Lambda | No | **Yes** |
| Extra install | none | `pip install reportlab` |

Running reports locally on the VDI? **Option A** is the natural fit — Edge is already there and the PDF matches the HTML. The HTML generators themselves stay standard-library only either way.

## Optional: PyYAML for richer ownership maps

The Tier 2 ownership map and Tier 3 lookup files (`--ownership-map`, `--rule-display-names`, `--cop-guidance`) accept YAML or JSON. JSON works out of the box. **Flat** YAML (`key: value` per line) also works via a built-in fallback parser. **Nested** YAML (team / domain / contact-email blocks) needs PyYAML installed:

```bash
pip install pyyaml
```

That's the only optional dependency. Everything else uses Python's standard library.

## Inputs each script supports

Run with `--help` for the full surface:

```bash
python generate_executive_report.py --help
python generate_platform_report.py --help
```

Both scripts degrade gracefully when optional inputs are missing — they log which tier each section is rendering from so you can see exactly what's being substituted.
