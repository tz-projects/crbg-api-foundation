# AWS Lambda runbook — no Git, no Docker, copy-paste

The **sequential, do-this-then-this** guide for deploying the scanner and reports to AWS Lambda under real corporate constraints:

- **No Git repo to clone** — you move code as a zip file instead.
- **No Docker on the VDI** — the scanner is packaged as a Lambda **Layer + code zip**, not a container image.
- **Reports needs no build at all** — it's stdlib-only, deployed straight from the VDI.

If you want the *concepts* behind any step (what a Layer is, why least-privilege roles, etc.), read [aws-lambda-walkthrough.md](aws-lambda-walkthrough.md). This doc is just the runnable sequence. The ruleset publisher is out of scope.

## The whole flow on one page

```
  VDI (Windows PowerShell)                 AWS CloudShell (browser Linux)
  ────────────────────────                 ─────────────────────────────
  tools\package-lambda.ps1
        │
        ├─► reports-lambda.zip ───────────► Lambda Console: upload → done
        │                                   (no build — stdlib only)
        │
        └─► scanner-source.zip ──upload──►  unzip
                                            bash build-scanner-layer.sh
                                                  │
                                                  ├─► scanner-deps-layer.zip ─► publish as Layer
                                                  └─► scanner-code.zip ───────► function code
```

One artifact (`reports-lambda.zip`) deploys directly. The other (`scanner-source.zip`) is carried into CloudShell, where it builds itself into a Layer + code zip.

---

## Prerequisites (one-time — likely your cloud team)

Before any of the steps below, these must exist. They're explained with validation checks in [aws-lambda-walkthrough.md Part 3](aws-lambda-walkthrough.md#part-3--phase-a-the-shared-furniture); the exact policies are in [aws-lambda-deployment.md §1](aws-lambda-deployment.md#1-prereqs). In a corporate account, **IAM roles are almost always created by the cloud team** — send them [the request in walkthrough Part 9](aws-lambda-walkthrough.md#part-9--what-to-send-your-cloud-team).

- [ ] An **S3 bucket** for artifacts (this doc calls it `$BUCKET`)
- [ ] An **SSM SecureString** `/swagger-studio/api-key` holding your SwaggerHub key
- [ ] Two **IAM execution roles**: `swagger-studio-scanner-role`, `swagger-studio-reports-role`
- [ ] Permission for you to **create + invoke Lambda functions** and **publish a layer**

You can confirm all of these are in place with the [validation cheat sheet](aws-lambda-walkthrough.md#part-8--validation-cheat-sheet-one-glance-reference).

---

## Part 1 — Package on the VDI (PowerShell)

This produces both zips. Nothing here needs the internet, Docker, or Git.

```powershell
# From the repo root on the VDI
.\tools\package-lambda.ps1
```

Output (in `dist\`):

```
dist\reports-lambda.zip    ← deploy-ready (4 stdlib files)
dist\scanner-source.zip    ← transport (requirements.txt + src\ + the build script)
```

The script prints a contents check so you can see exactly what went in. It deliberately ignores everything else in the repo — no `node_modules`, no TypeScript, no ruleset publisher, no tests.

> **If PowerShell blocks the script** with "running scripts is disabled," run once:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

---

## Part 2 — Deploy the reports Lambda (no CloudShell needed)

Reports is stdlib-only, so `reports-lambda.zip` from Part 1 is already the final deployment package. Deploy it straight from the AWS Console:

1. AWS Console → **Lambda** → **Create function**
2. **Author from scratch**
3. Function name: `swagger-studio-reports`
4. Runtime: **Python 3.13**
5. Architecture: **x86_64**
6. **Change default execution role** → **Use an existing role** → pick `swagger-studio-reports-role`
7. **Create function**
8. On the function page → **Code** tab → **Upload from** → **.zip file** → choose `reports-lambda.zip` → **Save**
9. **Configuration** tab → **General configuration** → **Edit** → set **Timeout = 1 min**, **Memory = 512 MB** → **Save**
10. **Runtime settings** → **Edit** → **Handler** = `lambda_handler.handler` → **Save**

That's the reports Lambda, fully deployed. You'll invoke it in Part 5.

---

## Part 3 — Build the scanner in CloudShell

The scanner has compiled dependencies, so its libraries must be gathered on Linux. CloudShell is that Linux — in your browser, no install on the VDI.

### 3.1 Open CloudShell and upload the zip

1. In the AWS Console, click the **CloudShell icon** (top toolbar, `>_`).
2. Wait for the terminal to open.
3. **Actions → Upload file** → choose `scanner-source.zip` from your VDI.
   It lands in your CloudShell home directory (`~`).

> **No upload button / file too big?** Alternative via S3: in the S3 Console, drag `scanner-source.zip` into your bucket, then in CloudShell run
> `aws s3 cp s3://$BUCKET/scanner-source.zip .`

### 3.2 Unzip and build

```bash
unzip scanner-source.zip -d scanner-source
cd scanner-source
bash build-scanner-layer.sh
```

The build script (bundled inside the zip) installs the Linux dependencies and produces two files in `lambda-build/`:

```
lambda-build/scanner-deps-layer.zip   ← the dependencies, as a Lambda Layer
lambda-build/scanner-code.zip         ← just your scanner code
```

It prints the sizes and confirms the layer's top-level folder is `python/` (the Layer requirement).

> **Wrong Python version?** The script targets 3.13 regardless of CloudShell's own Python, so you don't need to match them. To build for a different runtime: `bash build-scanner-layer.sh . ./lambda-build 3.12`.

---

## Part 4 — Deploy the scanner Lambda

Still in CloudShell. Set these once:

```bash
REGION=us-east-1                         # your region
BUCKET=your-org-swagger-governance       # your bucket
ROLE_ARN=$(aws iam get-role --role-name swagger-studio-scanner-role --query 'Role.Arn' --output text)
cd ~/scanner-source/lambda-build
```

### 4.1 Publish the dependency layer

```bash
LAYER_ARN=$(aws lambda publish-layer-version \
    --layer-name swagger-studio-scanner-deps \
    --zip-file fileb://scanner-deps-layer.zip \
    --compatible-runtimes python3.13 \
    --region $REGION \
    --query 'LayerVersionArn' --output text)

echo "Layer published: $LAYER_ARN"
```

The `$LAYER_ARN` is captured automatically for the next step. (If the layer zip is over 50 MB, upload it to S3 first and use `--content S3Bucket=...,S3Key=...` instead of `--zip-file`. Ours is ~6 MB, so direct is fine.)

### 4.2 Create the function with the code zip + the layer

```bash
aws lambda create-function \
    --function-name swagger-studio-scanner \
    --runtime python3.13 \
    --handler swagger_studio_scanner.lambda_handler.handler \
    --zip-file fileb://scanner-code.zip \
    --layers $LAYER_ARN \
    --role $ROLE_ARN \
    --timeout 900 \
    --memory-size 1024 \
    --environment "Variables={SWAGGERHUB_ORG=your-org-slug,SSM_API_KEY_PARAMETER=/swagger-studio/api-key,SCANNER_CONCURRENCY=8,SCANNER_LOG_LEVEL=INFO}" \
    --region $REGION
```

Replace `your-org-slug` with your real org. The function pulls its libraries from the layer and its code from the code zip.

> **✅ Validate:** `aws lambda get-function --function-name swagger-studio-scanner --query 'Configuration.State' --output text` should print `Active` (wait ~30s and retry if it says `Pending`).

---

## Part 5 — Run both and get the output

### 5.1 Run the scanner (small test first)

```bash
DATE=$(date +%Y-%m-%d)
aws lambda invoke \
    --function-name swagger-studio-scanner \
    --cli-binary-format raw-in-base64-out \
    --payload "{\"s3_bucket\":\"$BUCKET\",\"s3_prefix\":\"scans/${DATE}-test/\",\"limit\":10}" \
    /tmp/scanner-out.json
cat /tmp/scanner-out.json | python3 -m json.tool
```

> **✅ Validate:** response shows `"statusCode": 200` and a summary with `total_apis: 10`. Confirm the file landed:
> `aws s3 ls s3://$BUCKET/scans/${DATE}-test/` → should list `scan.json`.
>
> If it errored, read the logs: `aws logs tail /aws/lambda/swagger-studio-scanner --since 10m`.

For a full scan, drop the `limit`:

```bash
aws lambda invoke --function-name swagger-studio-scanner \
    --cli-binary-format raw-in-base64-out \
    --payload "{\"s3_bucket\":\"$BUCKET\",\"s3_prefix\":\"scans/${DATE}/\"}" \
    /tmp/scanner-out.json
```

### 5.2 Run the reports

```bash
aws lambda invoke \
    --function-name swagger-studio-reports \
    --cli-binary-format raw-in-base64-out \
    --payload "{\"scan_json_s3_uri\":\"s3://$BUCKET/scans/${DATE}-test/scan.json\",\"output_s3_prefix\":\"s3://$BUCKET/reports/${DATE}-test/\",\"org_display_name\":\"Your Org\",\"studio_base_url\":\"https://app.swaggerhub.com/apis\",\"placeholder_ask\":true}" \
    /tmp/reports-out.json
cat /tmp/reports-out.json | python3 -m json.tool
```

(Full reports options — ownership map, rule names, CoP guidance — are in [aws-lambda-deployment.md §4](aws-lambda-deployment.md#4-invoke-them-manually).)

### 5.3 Download the HTML

```bash
aws s3 sync s3://$BUCKET/reports/${DATE}-test/ ./reports-out/
```

In CloudShell: **Actions → Download file** → grab `reports-out/executive-report.html` (and `platform-report/index.html`) to view in a browser. Or generate a shareable link (no AWS login needed, ~1 hour):

```bash
aws s3 presign s3://$BUCKET/reports/${DATE}-test/executive-report.html --expires-in 3600
```

---

## Updating later (when code changes)

You don't edit anything live — you rebuild and re-upload.

**Reports** (code changed):
```powershell
.\tools\package-lambda.ps1                       # on the VDI
# Console → swagger-studio-reports → Code → Upload from → .zip → reports-lambda.zip
```

**Scanner code only** (deps unchanged — fast):
```bash
# Rebuild source zip on VDI, re-upload to CloudShell, then:
cd ~/scanner-source && bash build-scanner-layer.sh
aws lambda update-function-code --function-name swagger-studio-scanner \
    --zip-file fileb://lambda-build/scanner-code.zip --region $REGION
```

**Scanner deps changed** (after editing `requirements.txt`): rebuild as above, then publish a new layer version (4.1) and point the function at the new `$LAYER_ARN`:
```bash
aws lambda update-function-configuration --function-name swagger-studio-scanner \
    --layers $LAYER_ARN --region $REGION
```

---

## Moving files in and out of CloudShell without Git — recap

| Direction | Method |
|---|---|
| VDI → CloudShell | CloudShell **Actions → Upload file**, or drag to S3 in the Console then `aws s3 cp s3://$BUCKET/file .` |
| CloudShell → you | CloudShell **Actions → Download file**, or `aws s3 cp file s3://$BUCKET/` then download from S3 Console |
| Share a report | `aws s3 presign <s3-uri> --expires-in 3600` → paste the URL into Slack/email |

CloudShell's home directory (`~`) persists between sessions (1 GB), so your uploaded zip and build output survive if you step away and come back.

---

## See also

- [aws-lambda-walkthrough.md](aws-lambda-walkthrough.md) — the *why* behind each step, with validation after every resource
- [aws-lambda-deployment.md](aws-lambda-deployment.md) — fuller command reference (incl. the container-image alternative)
- [run-commands.md](run-commands.md) — the same scanner/reports run locally
- [troubleshooting.md](troubleshooting.md) — why Lambda (corporate SSL blocking local runs)
