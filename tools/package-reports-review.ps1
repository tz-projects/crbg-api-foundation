<#
.SYNOPSIS
    Build a shareable "review" package of the reports-generation programs (VDI/Windows).

.DESCRIPTION
    For handing to a colleague to READ, UNDERSTAND, and RUN on their own machine
    against their own scan.json. NOT for Lambda upload. PowerShell equivalent of
    tools/package-reports-review.sh.

    Produces (default <repo>\dist\):  reports-generator-review.zip  containing the
    reports source, the PDF tooling, the design spec, and a self-contained README.

.PARAMETER OutDir
    Where to write the zip. Defaults to <repo>\dist\.

.EXAMPLE
    ./tools/package-reports-review.ps1
#>
#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$OutDir
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Reports  = Join-Path $RepoRoot 'projects\reports'

if (-not $OutDir) { $OutDir = Join-Path $RepoRoot 'dist' }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path

$Stage = Join-Path $env:TEMP ("reports-review-" + [System.Guid]::NewGuid().ToString('N'))
$Pkg   = Join-Path $Stage 'reports-generator-review'
New-Item -ItemType Directory -Force -Path $Pkg | Out-Null

try {
    # Source + spec + PDF deps
    @('_lib.py','generate_executive_report.py','generate_platform_report.py',
      'generate_pdf_reports.py','requirements-pdf.txt','governance-reports-spec-v2.md') |
        ForEach-Object { Copy-Item (Join-Path $Reports $_) $Pkg }
    Copy-Item (Join-Path $PSScriptRoot 'html-to-pdf.py') $Pkg

    # Self-contained README for the colleague (single-quoted here-string = literal)
    $readme = @'
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
'@
    Set-Content -Path (Join-Path $Pkg 'README.md') -Value $readme -Encoding utf8

    $zip = Join-Path $OutDir 'reports-generator-review.zip'
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path $Pkg -DestinationPath $zip

    Write-Host "Built: $zip" -ForegroundColor Green
    Write-Host ""
    Write-Host "Give this zip to your colleague. They unzip it, drop their scan.json in, and follow README.md."
}
finally {
    Remove-Item $Stage -Recurse -Force -ErrorAction SilentlyContinue
}
