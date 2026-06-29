# AWS Lambda — lite variant (no S3, no SSM)

The **simplest** way to run the scanner and reports on Lambda. No S3 bucket, no SSM Parameter Store, no custom IAM policy.

- **API key** lives in a plain Lambda **environment variable**.
- **Data flows through the invoke payload/response**, not S3: the scanner returns `scan.json` inline; you hand that to the reports Lambda, which returns the HTML inline.

This is the variant on the `pure-python-aws-lambda-lite` branch. For the production-grade version (encrypted key in SSM, artifacts in S3, full-estate scans), see the `pure-python-aws-lambda-heavy` branch and [aws-lambda-runbook.md](aws-lambda-runbook.md).

> **When lite is the right choice:** trials, demos, partial/`--limit` scans, getting unblocked fast on a locked-down VDI. **When to graduate to heavy:** sensitive API keys (env vars are visible in the console) or full 600-API scans (a synchronous response caps at ~6 MB — small/limited scans are fine, full estate may exceed it).

> **Just want to hand three zips to your AWS team?** Skip the deploy/run scripts. Run [`tools/build-lambda-zips.ps1`](../tools/build-lambda-zips.ps1) (VDI) to produce `shared-deps-layer.zip`, `scanner-code.zip`, `reports-code.zip` (one shared layer for both functions), upload them to SharePoint, and give your team [aws-lambda-handoff.md](aws-lambda-handoff.md) — a click-by-click sheet for creating the functions. That's the lowest-overhead path.

## Architecture

```
   you ──invoke {limit:25}──► [ scanner Lambda ]  env var: SWAGGERHUB_API_KEY
                                     │              reaches SwaggerHub
                                     ▼
                          response.scan  (the scan.json, inline)
                                     │
                  jq builds the next payload from it
                                     │
   you ──invoke {scan:…}─────► [ reports Lambda ]  no key, no network
                                     │
                                     ▼
                   response.executive_html / platform_html / findings_csv
                                     │
                          jq writes them to .html / .csv
```

Two Lambdas, no S3 in between — they're chained by you copying the scanner's output into the reports' input (one `jq` command).

---

## Prerequisites (minimal)

- [ ] Permission to **create + invoke** two Lambda functions
- [ ] A basic **Lambda execution role** with just `AWSLambdaBasicExecutionRole` (logging only — no S3, no SSM). Often self-serviceable; if not, this is a small ask to the cloud team. You'll need its ARN.
- [ ] `jq` (preinstalled in CloudShell)

That's it. No bucket, no secret store, no custom policy.

---

## The scripted flow (three commands)

The lite variant ships three helper scripts so you don't type the AWS commands by hand:

| Script | Runs on | Does |
|---|---|---|
| `tools/package-lambda-lite.ps1` (or `.sh`) | VDI | Bundles everything into one `lambda-lite.zip` |
| `deploy-lambda-lite.sh` | CloudShell | Builds artifacts, publishes the layer, creates both functions |
| `run-lambda-lite.sh` | CloudShell | Scan → reports → writes HTML + CSV files |

The deploy and run scripts are bundled *inside* `lambda-lite.zip`, so you upload one file and run them from the unzipped folder.

### Part 1 — Package (VDI PowerShell)

```powershell
git clone -b pure-python-aws-lambda-lite git@github.com:tz-projects/crbg-api-foundation.git
cd crbg-api-foundation
.\tools\package-lambda-lite.ps1
```

Produces `dist\lambda-lite.zip` — a single self-contained bundle (scanner source + reports code + the deploy/run scripts).

### Part 2 — Deploy (CloudShell)

Upload `lambda-lite.zip` via CloudShell **Actions → Upload file**, then:

```bash
unzip lambda-lite.zip && cd lambda-lite

export SWAGGERHUB_API_KEY=paste-your-key
export SWAGGERHUB_ORG=your-org-slug
export LAMBDA_ROLE_ARN=arn:aws:iam::123456789012:role/your-basic-lambda-role
# export AWS_REGION=us-east-1     # only if your CLI default isn't the right region

bash deploy-lambda-lite.sh
```

The script builds **one shared dependency layer** (scanner + reports deps) plus the two small code zips, publishes the layer, and creates both functions — attaching the same layer to each (re-running it later updates them in place). The API key goes into the scanner's env vars — no SSM.

### Part 3 — Run (CloudShell)

```bash
SCAN_LIMIT=25 ORG_DISPLAY_NAME="Your Org" bash run-lambda-lite.sh
# omit SCAN_LIMIT for a full scan
```

This invokes the scanner, pipes its inline `scan.json` into the reports Lambda, and writes `lite-output/executive-report.html`, `platform-report.html`, `findings.csv`, and — since the reports package bundles reportlab — `executive-report.pdf` and `platform-report.pdf`. Download them with CloudShell **Actions → Download file**.

> **PDFs:** the reports function returns the PDFs base64-encoded (`executive_pdf_base64` / `platform_pdf_base64`); `run-lambda-lite.sh` decodes them automatically. They're rendered directly from the scan data by reportlab — no browser, works in Lambda. Send `"pdf": false` in the reports payload to skip them.

---

## Alternative: run the reports locally on the VDI

The reports Lambda is *optional* — reports need no network, so you can skip the reports Lambda entirely and run them on the VDI from the scanner's output:

```bash
# CloudShell: scan only, save the scan.json
aws lambda invoke --function-name swagger-studio-scanner \
    --cli-binary-format raw-in-base64-out --payload '{"limit":25}' scan-out.json
jq .scan scan-out.json > scan.json   # download scan.json to the VDI
```

```powershell
# VDI: generate reports from scan.json (plain Python, no AWS, no network)
cd projects\reports
python generate_executive_report.py --input ..\..\scan.json --output executive-report.html --org-display-name "Your Org" --placeholder-ask
python generate_platform_report.py --input ..\..\scan.json --output-dir platform-report --org-display-name "Your Org" --studio-base-url https://app.swaggerhub.com/apis
```

That's the absolute simplest path: one Lambda (scanner), reports on the VDI.

---

## Manual equivalent (no scripts)

If you'd rather run the AWS commands yourself, the scripts are thin wrappers — see [`tools/deploy-lambda-lite.sh`](../tools/deploy-lambda-lite.sh) and [`tools/run-lambda-lite.sh`](../tools/run-lambda-lite.sh) for the exact `aws lambda` calls (publish-layer-version, create-function with the env-var key, the scan → `jq` → reports → `jq` extract chain).

---

## Full scans and the 6 MB limit

A synchronous Lambda response caps at ~6 MB, which bounds both the scanner's returned `scan.json` and the reports' returned HTML.

- Small / `--limit` scans: kilobytes — no issue.
- Full 600-API scan: may exceed 6 MB. Options:
  1. Scan in slices with `"limit"` and run reports per slice, or
  2. Switch to the **heavy** variant (S3-backed) for full-estate runs — same code, the S3 handler just streams to a bucket instead of returning inline.

---

## What differs from the heavy variant

| | Lite (this branch) | Heavy |
|---|---|---|
| API key | plain env var | SSM SecureString |
| Scan output | inline in response | written to S3 |
| Reports input | inline in payload | read from S3 |
| S3 bucket | none | required |
| SSM | none | required |
| IAM | logging only | logging + S3 + SSM |
| Full-estate scans | bounded by 6 MB | unbounded |

## See also

- [aws-lambda-runbook.md](aws-lambda-runbook.md) — the heavy (S3/SSM) flow, with the no-Git/no-Docker transport details
- [aws-lambda-walkthrough.md](aws-lambda-walkthrough.md) — concepts + validation (mostly applies to both; ignore the S3/SSM-specific parts for lite)
- [run-commands.md](run-commands.md) — running scanner/reports locally
