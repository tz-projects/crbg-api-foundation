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

The only requirement is Python 3.12+ (`python --version`). Both scripts run directly:

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
