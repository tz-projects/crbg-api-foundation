# AWS Lambda quickstart — the cheat sheet

> ⚠️ **This branch (`pure-python-aws-lambda-lite`) ships the LITE handlers (no S3, no SSM).** This cheat sheet describes the **heavy** S3/SSM variant. For this branch's actual deployment, follow **[aws-lambda-lite.md](aws-lambda-lite.md)**. The heavy variant lives on the `pure-python-aws-lambda-heavy` branch.


The shortest path to running the scanner and reports on AWS Lambda. Each command is labelled by **where** it runs (VDI PowerShell / AWS Console / CloudShell). For the *why* behind each step, see [aws-lambda-runbook.md](aws-lambda-runbook.md) (detailed) and [aws-lambda-walkthrough.md](aws-lambda-walkthrough.md) (concepts + validation).

Substitute three values throughout: **`$REGION`**, **`$BUCKET`**, and **`your-org-slug`**. Everything else is literal.

---

## Prerequisites — ask your cloud team (one-time)

You can't create these yourself in a corporate account. Request:

- [ ] An **S3 bucket** for artifacts (referred to as `$BUCKET`)
- [ ] An **SSM SecureString** `/swagger-studio/api-key` holding your SwaggerHub key
- [ ] Two **IAM roles**: `swagger-studio-scanner-role`, `swagger-studio-reports-role`
- [ ] Permission for you to **create/invoke Lambda functions** and **publish a layer**

Exact policies: [aws-lambda-deployment.md §1.3](aws-lambda-deployment.md#13-create-an-iam-execution-role-for-each-lambda). Don't proceed past Part 3 until these exist.

---

## Part 1 — Get the code onto the VDI

**VDI (PowerShell)** — if the VDI can reach GitHub:

```powershell
git clone -b pure-python git@github.com:tz-projects/crbg-api-foundation.git
cd crbg-api-foundation
```

If GitHub is unreachable, copy the repo over however you move files, then `cd` into it.

---

## Part 2 — Package the Python

**VDI (PowerShell):**

```powershell
.\tools\package-lambda.ps1
```

Creates in `dist\`:
- `reports-lambda.zip` — deploy as-is (Part 3)
- `scanner-source.zip` — build in CloudShell (Part 4)

> Blocked? `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` once, then re-run.

---

## Part 3 — Deploy the reports Lambda

**AWS Console:**

1. **Lambda → Create function → Author from scratch**
2. Name: `swagger-studio-reports`
3. Runtime **Python 3.13**, Architecture **x86_64**
4. **Change default execution role → Use an existing role →** `swagger-studio-reports-role`
5. **Create function**
6. **Code** tab → **Upload from → .zip file** → `dist\reports-lambda.zip` → **Save**
7. **Configuration → General configuration → Edit:** Timeout `1 min`, Memory `512 MB` → **Save**
8. **Runtime settings → Edit:** Handler = `lambda_handler.handler` → **Save**

---

## Part 4 — Build the scanner

**AWS Console → CloudShell icon (`>_`)**, then:

```bash
# Upload scanner-source.zip first: CloudShell "Actions -> Upload file"
unzip scanner-source.zip -d scanner-source
cd scanner-source
bash build-scanner-layer.sh
```

Produces in `lambda-build/`: `scanner-deps-layer.zip` + `scanner-code.zip`.

---

## Part 5 — Deploy the scanner Lambda

**CloudShell** — set your values:

```bash
REGION=us-east-1                              # your region
BUCKET=your-org-swagger-governance           # your bucket
ROLE_ARN=$(aws iam get-role --role-name swagger-studio-scanner-role --query 'Role.Arn' --output text)
cd ~/scanner-source/lambda-build
```

Publish the dependency layer:

```bash
LAYER_ARN=$(aws lambda publish-layer-version \
    --layer-name swagger-studio-scanner-deps \
    --zip-file fileb://scanner-deps-layer.zip \
    --compatible-runtimes python3.13 \
    --region $REGION \
    --query 'LayerVersionArn' --output text)
echo "$LAYER_ARN"
```

Create the function (replace `your-org-slug`):

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

Confirm ready:

```bash
aws lambda get-function --function-name swagger-studio-scanner --query 'Configuration.State' --output text
# wait until: Active
```

---

## Part 6 — Run and get the report

**CloudShell.**

**1. Scan (small test first):**

```bash
DATE=$(date +%Y-%m-%d)
aws lambda invoke \
    --function-name swagger-studio-scanner \
    --cli-binary-format raw-in-base64-out \
    --payload "{\"s3_bucket\":\"$BUCKET\",\"s3_prefix\":\"scans/${DATE}-test/\",\"limit\":10}" \
    /tmp/out.json
cat /tmp/out.json | python3 -m json.tool
```

Expect `"statusCode": 200` + a summary. For a full scan, drop `,\"limit\":10`.

**2. Generate the reports:**

```bash
aws lambda invoke \
    --function-name swagger-studio-reports \
    --cli-binary-format raw-in-base64-out \
    --payload "{\"scan_json_s3_uri\":\"s3://$BUCKET/scans/${DATE}-test/scan.json\",\"output_s3_prefix\":\"s3://$BUCKET/reports/${DATE}-test/\",\"org_display_name\":\"Your Org\",\"studio_base_url\":\"https://app.swaggerhub.com/apis\",\"placeholder_ask\":true}" \
    /tmp/out.json
cat /tmp/out.json | python3 -m json.tool
```

**3. Download the HTML:**

```bash
aws s3 sync s3://$BUCKET/reports/${DATE}-test/ ./reports-out/
```

Then CloudShell **Actions → Download file** → `reports-out/executive-report.html` → open in a browser. To share without AWS access:

```bash
aws s3 presign s3://$BUCKET/reports/${DATE}-test/executive-report.html --expires-in 3600
```

---

## Where each part runs

| Part | Where | What |
|---|---|---|
| 1–2 | VDI PowerShell | Get code, package → two zips |
| 3 | AWS Console | Upload `reports-lambda.zip` |
| 4 | CloudShell | Build scanner → layer + code |
| 5 | CloudShell | Publish layer, create function |
| 6 | CloudShell | Run scan + reports, download HTML |

---

## See also

- [aws-lambda-runbook.md](aws-lambda-runbook.md) — the same flow with explanations and the no-Git/no-Docker transport details
- [aws-lambda-walkthrough.md](aws-lambda-walkthrough.md) — concepts + a "validate it worked" check after every resource
- [aws-lambda-deployment.md](aws-lambda-deployment.md) — full command reference incl. IAM policies and the container-image alternative
