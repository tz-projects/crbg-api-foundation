# Reports hand-off sheet — run the governance reports on your VDI

This is for whoever generates the reports on a VDI. You run the **scanner** in AWS Lambda, download its `scan.json`, and turn it into the HTML reports (and PDFs) locally. **No GitHub access needed** — everything runs from the `reports-code.zip` you were given.

## What you need

- **Python 3** (3.9 or newer; 3.13 matches the Lambda runtime).
- **`reports-code.zip`** (provided).
- **`scan.json`** — the scanner Lambda's output (Step 1 below).
- *(Optional, only for the automated PDF)* **`html-to-pdf.py`** — a single script, provided separately (it is **not** inside `reports-code.zip`). Microsoft Edge, already on the VDI, does the actual rendering.

> **No `pip install` needed for the reports.** The HTML report generators use only the Python standard library. (Ignore `generate_pdf_reports.py` inside the zip — it is a separate PDF path that *would* need extra packages and does not match the HTML. Use the PDF steps in Step 4 instead.)

---

## Step 1 — Get `scan.json` from the scanner Lambda

Using the AWS CLI on the VDI (Windows PowerShell):

```powershell
'{"limit":25}' | Set-Content payload.json          # or {} for a full scan
aws lambda invoke --function-name swagger-studio-scanner `
  --cli-binary-format raw-in-base64-out --payload file://payload.json scan-response.json

# Pull just the scan results into scan.json (no extra tools needed)
(Get-Content scan-response.json -Raw | ConvertFrom-Json).scan |
  ConvertTo-Json -Depth 100 | Set-Content scan.json
```

Alternatively, in the Lambda **Console → Test** tab: invoke with `{ "limit": 25 }`, then copy the value of the `scan` field from the response into a file named `scan.json`.

> A synchronous Lambda response caps at ~6 MB, so use `{"limit": N}` for large orgs. A limited scan is well within the limit.

---

## Step 2 — Unzip the reports code

Unzip `reports-code.zip` into a folder, e.g. `C:\reports`. You'll see:

```
generate_executive_report.py
generate_platform_report.py
_lib.py
generate_pdf_reports.py   (not used — ignore)
lambda_handler.py         (not used — ignore)
```

Running the generators from this folder is the intended way — `_lib.py` sits next to them, which is what they expect.

---

## Step 3 — Generate the HTML reports (PowerShell)

```powershell
cd C:\reports

python generate_executive_report.py `
  --input C:\path\to\scan.json `
  --output executive-report.html `
  --org-display-name "Your Org"

python generate_platform_report.py `
  --input C:\path\to\scan.json `
  --output-dir platform-report `
  --org-display-name "Your Org" `
  --studio-base-url https://app.swaggerhub.com/apis
```

Outputs:

- `executive-report.html` — the CIO-facing one-pager.
- `platform-report\index.html` — the detailed team report (plus `platform-report\findings.csv`).

Open either `.html` in a browser to view.

---

## Step 4 — PDF (two options, both match the HTML exactly)

### Option A — Edge "Save as PDF" (nothing to install)

Open each HTML file in **Microsoft Edge → Ctrl+P → Destination: Save as PDF → Save**. The PDF is rendered from the real report, so it matches exactly.

### Option B — `html-to-pdf.py` (automated, needs the script)

If you were given `html-to-pdf.py`, put it in the same `C:\reports` folder and run:

```powershell
cd C:\reports
python html-to-pdf.py executive-report.html platform-report\index.html
```

It auto-detects Edge and writes a PDF next to each HTML (`executive-report.pdf`, `platform-report.pdf`). Useful flags:

- `--out-dir pdf\` — collect the PDFs in one folder instead of next to each input.
- `--browser "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"` — only if auto-detection can't find Edge.

This script is standard-library only (no `pip install`); it just drives the Edge that's already on the VDI.

---

## Recap

1. Scanner runs in Lambda → download `scan.json`.
2. Unzip `reports-code.zip`, run the two generators → HTML.
3. Edge "Save as PDF" **or** `html-to-pdf.py` → PDFs.

No GitHub, no `pip install`, no AWS beyond invoking the scanner.
