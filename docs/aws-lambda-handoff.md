# Lambda hand-off sheet — create the functions from three zip files

This is for whoever owns AWS. You've been given three zip files. This sheet tells you exactly what to create from each. No code knowledge needed — it's all clicks in the AWS Console.

## The three files

| File | What it is |
|---|---|
| `shared-deps-layer.zip` | A **single Lambda Layer** — ALL dependencies for both functions |
| `scanner-code.zip` | The **scanner** function's code (tiny) |
| `reports-code.zip` | The **reports** function's code (tiny) |

## What you'll create

1. **One** Lambda **Layer** (from `shared-deps-layer.zip`)
2. The **scanner** Lambda function (code zip + the layer + an API key)
3. The **reports** Lambda function (code zip + **the same layer**)

Both functions attach the **same** shared layer. Both need a basic execution role (logging only — `AWSLambdaBasicExecutionRole`). No S3, no SSM, no custom policy.

---

## Step 1 — Create the shared Layer

1. AWS Console → **Lambda → Layers → Create layer**
2. Name: `swagger-studio-shared-deps`
3. **Upload** `shared-deps-layer.zip`
4. Compatible runtimes: **Python 3.13**
5. **Create**
6. **Copy the Layer Version ARN** it shows — you'll attach it to **both** functions (Steps 2 and 3).

---

## Step 2 — Create the scanner function

1. **Lambda → Create function → Author from scratch**
2. Function name: `swagger-studio-scanner`
3. Runtime: **Python 3.13**, Architecture: **x86_64**
4. **Change default execution role → Use an existing role →** a basic Lambda execution role (logging only)
5. **Create function**

Then configure it:

| Where in the Console | Setting | Value |
|---|---|---|
| **Code → Upload from → .zip file** | code | `scanner-code.zip` |
| **Runtime settings → Edit** | Handler | `swagger_studio_scanner.lambda_handler.handler` |
| **Code → Layers → Add a layer → Custom layers** | layer | `swagger-studio-shared-deps` (the ARN from Step 1) |
| **Configuration → Environment variables → Edit** | `SWAGGERHUB_API_KEY` | *(the API key — provided separately)* |
| | `SWAGGERHUB_ORG` | *(the org slug — provided separately)* |
| **Configuration → General configuration → Edit** | Timeout | `15 min` |
| | Memory | `1024 MB` |

> The API key and org slug are provided out-of-band (not in this doc). Set them as plain environment variables.

---

## Step 3 — Create the reports function

1. **Lambda → Create function → Author from scratch**
2. Function name: `swagger-studio-reports`
3. Runtime: **Python 3.13**, Architecture: **x86_64**
4. **Use an existing role →** the same basic execution role
5. **Create function**

Then:

| Where in the Console | Setting | Value |
|---|---|---|
| **Code → Upload from → .zip file** | code | `reports-code.zip` |
| **Runtime settings → Edit** | Handler | `lambda_handler.handler` |
| **Code → Layers → Add a layer → Custom layers** | layer | `swagger-studio-shared-deps` (**same ARN as Step 2**) |
| **Configuration → General configuration → Edit** | Timeout | `2 min` |
| | Memory | `1024 MB` |

No environment variables for this one. It attaches the **same** shared layer as the scanner (that layer carries reportlab for PDF output). The higher memory is for PDF rendering.

---

## Step 4 — Quick test (optional, confirms it works)

**Scanner** — Test tab → event JSON:

```json
{ "limit": 5 }
```

Expect a `200` response whose `scan` field holds the scan results. (No `limit` = full scan.)

**Reports** — needs the scanner's output as input. Easiest end-to-end test is to run the scanner first, copy its `scan` value, and send:

```json
{
  "scan": <paste the scanner response's "scan" value here>,
  "org_display_name": "Your Org",
  "studio_base_url": "https://app.swaggerhub.com/apis",
  "placeholder_ask": true
}
```

Expect a `200` with `executive_html`, `platform_html`, and `findings_csv` fields — plus `executive_pdf_base64` and `platform_pdf_base64` (the PDFs, base64-encoded). Decode those with `base64 -d` to get `.pdf` files. (Send `"pdf": false` in the event to skip PDF generation.)

---

## How the two functions relate

```
   invoke {limit: N}  ─►  scanner  ─►  returns the scan results inline
                                              │
                          (you pass that into the reports function)
                                              │
   invoke {scan: …}   ─►  reports  ─►  returns the HTML + CSV inline
```

The scanner reaches SwaggerHub; the reports function just formats the scanner's output into HTML. They don't talk to each other directly — whoever runs them passes the scanner's output into the reports call. There's no S3 or database involved.

## Notes / limits

- A synchronous Lambda response caps at ~6 MB. A small or limited scan (`{"limit": N}`) is fine. A full 600-API scan may exceed it — run with a `limit`, or ask the requester about the S3-backed (heavy) variant for full-estate scans.
- The API key is a plain environment variable on the scanner function (visible in the Console to anyone with read access). Fine for a trial key; for a sensitive key, ask the requester about the SSM-backed variant.

---

For the people producing the zips: build them with `tools/build-lambda-zips.ps1` (VDI) or `tools/build-lambda-zips.sh` (Mac/Linux/CloudShell). Full context: [aws-lambda-lite.md](aws-lambda-lite.md).
