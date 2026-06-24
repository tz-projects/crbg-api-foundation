# Lambda hand-off sheet — create the functions from three zip files

This is for whoever owns AWS. You've been given three zip files. This sheet tells you exactly what to create from each. No code knowledge needed — it's all clicks in the AWS Console.

## The three files

| File | What it is |
|---|---|
| `scanner-deps-layer.zip` | A **Lambda Layer** — the scanner's Python dependencies |
| `scanner-code.zip` | The **scanner** function's code |
| `reports-code.zip` | The **reports** function's code |

## What you'll create

1. One Lambda **Layer** (from the deps zip)
2. The **scanner** Lambda function (code zip + the layer + an API key)
3. The **reports** Lambda function (code zip only)

Both functions need a basic execution role (logging only — `AWSLambdaBasicExecutionRole`). No S3, no SSM, no custom policy.

---

## Step 1 — Create the Layer

1. AWS Console → **Lambda → Layers → Create layer**
2. Name: `swagger-studio-scanner-deps`
3. **Upload** `scanner-deps-layer.zip`
4. Compatible runtimes: **Python 3.13**
5. **Create**
6. **Copy the Layer Version ARN** it shows — you'll need it in Step 2.

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
| **Code → Layers → Add a layer → Custom layers** | layer | `swagger-studio-scanner-deps` (the ARN from Step 1) |
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
| **Configuration → General configuration → Edit** | Timeout | `1 min` |
| | Memory | `512 MB` |

No layer, no environment variables for this one.

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

Expect a `200` with `executive_html`, `platform_html`, and `findings_csv` fields.

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
