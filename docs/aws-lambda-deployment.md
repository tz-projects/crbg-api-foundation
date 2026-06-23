# Running the scanner and reports on AWS Lambda

End-to-end guide for deploying the **scanner** and the **reports** Python programs to AWS Lambda, invoked **manually** (no schedule, no API Gateway). Output lands in S3.

This is the right setup when your work-laptop / VDI can't reach `api.swaggerhub.com` over HTTPS (corporate TLS inspection blocks Python — see [troubleshooting.md §1](troubleshooting.md#1-ssl-certificate_verify_failed--self-signed-certificate-in-certificate-chain)) but the team's AWS account can. Lambda runs in AWS-managed networking and reaches public SaaS cleanly with the default certifi trust bundle — no corporate-CA dance.

> **New to AWS Lambda?** Read [aws-lambda-walkthrough.md](aws-lambda-walkthrough.md) first — it's the concept-first, hand-holding companion to this doc, with a "how to validate it worked" check after every resource. This doc is the terse command reference; that one explains *why* each step exists.

> **On a locked-down VDI (no Git, no Docker)?** Use [aws-lambda-runbook.md](aws-lambda-runbook.md) — it deploys the scanner as a **Lambda Layer + code zip** (no container image) and moves code as zip files (no `git clone`). This doc's container-image path below is the alternative for when Docker *is* available.

## Architecture

```
   You (Console "Test" button OR `aws lambda invoke`)
                       │
                       ├─────────────────────┐
                       ▼                     ▼
   ┌─────────────────────────┐   ┌─────────────────────────┐
   │ swagger-studio-scanner  │   │ swagger-studio-reports  │
   │  (container image)      │   │  (zip — stdlib only)    │
   │  reads SSM creds        │   │  reads scan.json from S3│
   │  writes scan.json to S3 │   │  writes HTML/CSV to S3  │
   └────────────┬────────────┘   └────────────┬────────────┘
                ▼                              ▼
   ┌────────────────────────────────────────────────────────┐
   │ S3 bucket — single source of truth                     │
   │   scans/2026-06-22/scan.json                           │
   │   reports/2026-06-22/executive-report.html             │
   │   reports/2026-06-22/platform-report/index.html        │
   │   reports/2026-06-22/platform-report/findings.csv      │
   └────────────────────────────────────────────────────────┘
```

Two Lambdas, **decoupled via S3**. You can re-run the reports against any historical `scan.json` without re-scanning.

## What you'll do

1. [Prereqs — S3 bucket + SSM parameter + IAM role](#1-prereqs)
2. [Deploy the scanner Lambda (container image)](#2-deploy-the-scanner-lambda-container-image)
3. [Deploy the reports Lambda (zip)](#3-deploy-the-reports-lambda-zip)
4. [Invoke them manually](#4-invoke-them-manually)
5. [Download the output from S3](#5-download-the-output-from-s3)
6. [Troubleshooting + caveats](#6-troubleshooting--caveats)

All commands assume **AWS CloudShell** (the browser shell from the AWS Console). It has the AWS CLI, Docker, Python, and git preinstalled. If you're using your own machine instead, install the [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) + Docker first.

Pick one **AWS region** and use it consistently throughout. The examples use `us-east-1`; substitute your region.

---

## 1. Prereqs

### 1.1 Create an S3 bucket for scan + report artifacts

```bash
BUCKET=your-org-swagger-governance       # must be globally unique
REGION=us-east-1
aws s3api create-bucket \
    --bucket $BUCKET \
    --region $REGION \
    --create-bucket-configuration LocationConstraint=$REGION
aws s3api put-bucket-versioning \
    --bucket $BUCKET \
    --versioning-configuration Status=Enabled
```

(For `us-east-1` specifically, drop the `--create-bucket-configuration` flag — AWS rejects it for that region only.)

### 1.2 Store the SwaggerHub API key in SSM Parameter Store

```bash
aws ssm put-parameter \
    --name "/swagger-studio/api-key" \
    --type SecureString \
    --value "YOUR_SWAGGERHUB_API_KEY_HERE" \
    --description "Org-owner read key for the SwaggerHub scanner"
```

Use `--overwrite` instead of repeating `put-parameter` to update an existing value. Never paste this key into a Lambda environment variable — env vars are visible in the Console to anyone with read access.

### 1.3 Create an IAM execution role for each Lambda

Both Lambdas need: basic CloudWatch logging + S3 read/write on your bucket. The scanner additionally needs SSM read on the API key parameter.

```bash
# Trust policy — lets Lambda assume the role
cat > /tmp/lambda-trust.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

# Scanner role
aws iam create-role \
    --role-name swagger-studio-scanner-role \
    --assume-role-policy-document file:///tmp/lambda-trust.json

aws iam attach-role-policy \
    --role-name swagger-studio-scanner-role \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Inline policy — bucket write + SSM read
cat > /tmp/scanner-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::$BUCKET/scans/*"
    },
    {
      "Effect": "Allow",
      "Action": ["ssm:GetParameter"],
      "Resource": "arn:aws:ssm:$REGION:*:parameter/swagger-studio/api-key"
    }
  ]
}
EOF
aws iam put-role-policy \
    --role-name swagger-studio-scanner-role \
    --policy-name scanner-inline \
    --policy-document file:///tmp/scanner-policy.json

# Reports role
aws iam create-role \
    --role-name swagger-studio-reports-role \
    --assume-role-policy-document file:///tmp/lambda-trust.json

aws iam attach-role-policy \
    --role-name swagger-studio-reports-role \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

cat > /tmp/reports-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::$BUCKET/scans/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::$BUCKET/reports/*"
    }
  ]
}
EOF
aws iam put-role-policy \
    --role-name swagger-studio-reports-role \
    --policy-name reports-inline \
    --policy-document file:///tmp/reports-policy.json
```

---

## 2. Deploy the scanner Lambda (container image)

The scanner has ~25 transitive deps (httpx, pydantic, etc.) — close enough to Lambda's 50 MB zip limit that a **container image** is the cleaner path. Container images cap at 10 GB and use familiar `pip install`.

### 2.1 Build the image in CloudShell

CloudShell has Docker preinstalled. From the repo root:

```bash
git clone <your-repo-url>
cd <repo-name>/projects/swagger-studio-scanner/python

# Build (Dockerfile.lambda is in this directory)
docker build -f Dockerfile.lambda -t swagger-studio-scanner-lambda:latest .
```

The build takes 1-2 minutes — most of it is `pip install` from the pinned `requirements.txt`.

### 2.2 Push to ECR

ECR is AWS's container registry. Create a repo, log Docker into it, tag and push:

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
REPO=swagger-studio-scanner-lambda

# Create ECR repo (one-time)
aws ecr create-repository --repository-name $REPO --region $REGION || true

# Auth Docker to ECR
aws ecr get-login-password --region $REGION | \
    docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# Tag + push
IMAGE_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"
docker tag swagger-studio-scanner-lambda:latest $IMAGE_URI
docker push $IMAGE_URI
echo "Pushed: $IMAGE_URI"
```

### 2.3 Create the Lambda function

```bash
ROLE_ARN=$(aws iam get-role --role-name swagger-studio-scanner-role --query 'Role.Arn' --output text)

aws lambda create-function \
    --function-name swagger-studio-scanner \
    --package-type Image \
    --code ImageUri=$IMAGE_URI \
    --role $ROLE_ARN \
    --timeout 900 \
    --memory-size 1024 \
    --environment "Variables={
        SWAGGERHUB_ORG=your-org-slug,
        SSM_API_KEY_PARAMETER=/swagger-studio/api-key,
        SCANNER_CONCURRENCY=8,
        SCANNER_LOG_LEVEL=INFO
    }" \
    --region $REGION
```

| Setting | Why this value |
|---|---|
| `--timeout 900` | 15 minutes — Lambda's max. For a 600-API scan, you may need to use `--limit` (see §4) or split via Step Functions. |
| `--memory-size 1024` | 1 GB is plenty for httpx + pydantic. CPU scales with memory in Lambda; more memory = faster. Bump to 2048 if scans feel slow. |
| `SWAGGERHUB_ORG` | Replace with your org slug from `app.swaggerhub.com/organization/<slug>`. |
| `SSM_API_KEY_PARAMETER` | Must match the name you used in §1.2. |

### 2.4 Updating the function later

When the code changes, rebuild + push the image, then tell Lambda to use the new version:

```bash
docker build -f Dockerfile.lambda -t swagger-studio-scanner-lambda:latest .
docker tag swagger-studio-scanner-lambda:latest $IMAGE_URI
docker push $IMAGE_URI
aws lambda update-function-code \
    --function-name swagger-studio-scanner \
    --image-uri $IMAGE_URI
```

---

## 3. Deploy the reports Lambda (zip)

Reports are stdlib-only — tiny zip, no Docker needed.

### 3.1 Build the zip

```bash
cd <repo-root>
bash projects/reports/build-lambda-zip.sh /tmp/reports-lambda.zip
# Output: ~28 KB zip with 4 files
```

### 3.2 Create the Lambda function

```bash
REPORTS_ROLE_ARN=$(aws iam get-role --role-name swagger-studio-reports-role --query 'Role.Arn' --output text)

aws lambda create-function \
    --function-name swagger-studio-reports \
    --runtime python3.13 \
    --handler lambda_handler.handler \
    --zip-file fileb:///tmp/reports-lambda.zip \
    --role $REPORTS_ROLE_ARN \
    --timeout 60 \
    --memory-size 512 \
    --region $REGION
```

| Setting | Why this value |
|---|---|
| `--runtime python3.13` | Matches the scripts' `requires-python` floor. |
| `--handler lambda_handler.handler` | `module_name.function_name` — `lambda_handler.py` exports `handler()`. |
| `--timeout 60` | Reports run in seconds, but 60s gives slack for S3 downloads of large `scan.json`. |
| `--memory-size 512` | Far more than needed; 256 MB also fine. |

### 3.3 Updating the function later

```bash
bash projects/reports/build-lambda-zip.sh /tmp/reports-lambda.zip
aws lambda update-function-code \
    --function-name swagger-studio-reports \
    --zip-file fileb:///tmp/reports-lambda.zip
```

---

## 4. Invoke them manually

### 4.1 From the AWS Console (easiest)

1. Open AWS Console → **Lambda** → click your function
2. Click the **Test** tab
3. Configure a test event with the JSON payload (examples below)
4. Click **Test**
5. The response panel shows the function's return value + execution logs

### 4.2 From CloudShell / AWS CLI

#### Run the scanner — small test first (10 APIs)

```bash
BUCKET=your-org-swagger-governance
DATE=$(date +%Y-%m-%d)

aws lambda invoke \
    --function-name swagger-studio-scanner \
    --cli-binary-format raw-in-base64-out \
    --payload "{
        \"s3_bucket\": \"$BUCKET\",
        \"s3_prefix\": \"scans/${DATE}-test/\",
        \"limit\": 10
    }" \
    /tmp/scanner-response.json

cat /tmp/scanner-response.json | python -m json.tool
```

Successful output:
```json
{
  "statusCode": 200,
  "body": {
    "scan_json_s3_uri": "s3://your-org-swagger-governance/scans/2026-06-22-test/scan.json",
    "summary": {
      "total_apis": 10,
      "passed": 3,
      "warned": 0,
      "failed": 7,
      "errored": 0,
      ...
    },
    "limit_applied": 10
  }
}
```

#### Run the scanner — full scan (omit `limit`)

```bash
aws lambda invoke \
    --function-name swagger-studio-scanner \
    --cli-binary-format raw-in-base64-out \
    --payload "{
        \"s3_bucket\": \"$BUCKET\",
        \"s3_prefix\": \"scans/${DATE}/\"
    }" \
    /tmp/scanner-response.json
```

If the full scan hits the 15-minute timeout, fall back to `"limit": 100` and run in chunks against the same prefix (each invocation overwrites `scan.json` — but that's fine for testing scale; production-grade chunking needs Step Functions).

#### Run the reports — basic (Tier 1 only)

```bash
aws lambda invoke \
    --function-name swagger-studio-reports \
    --cli-binary-format raw-in-base64-out \
    --payload "{
        \"scan_json_s3_uri\": \"s3://$BUCKET/scans/$DATE/scan.json\",
        \"output_s3_prefix\": \"s3://$BUCKET/reports/$DATE/\",
        \"org_display_name\": \"Your Org\",
        \"studio_base_url\": \"https://app.swaggerhub.com/apis\",
        \"placeholder_ask\": true
    }" \
    /tmp/reports-response.json

cat /tmp/reports-response.json | python -m json.tool
```

#### Run the reports — with Tier 2/3 enrichment

Upload your input files to S3 first:

```bash
aws s3 cp ownership.yaml s3://$BUCKET/inputs/ownership.yaml
aws s3 cp rule_display_names.yaml s3://$BUCKET/inputs/rule_display_names.yaml
aws s3 cp cop_guidance.yaml s3://$BUCKET/inputs/cop_guidance.yaml
aws s3 cp asks.md s3://$BUCKET/inputs/asks.md
```

Then:

```bash
aws lambda invoke \
    --function-name swagger-studio-reports \
    --cli-binary-format raw-in-base64-out \
    --payload "{
        \"scan_json_s3_uri\": \"s3://$BUCKET/scans/$DATE/scan.json\",
        \"output_s3_prefix\": \"s3://$BUCKET/reports/$DATE/\",
        \"org_display_name\": \"Your Org\",
        \"studio_base_url\": \"https://app.swaggerhub.com/apis\",
        \"ownership_map_s3_uri\": \"s3://$BUCKET/inputs/ownership.yaml\",
        \"rule_display_names_s3_uri\": \"s3://$BUCKET/inputs/rule_display_names.yaml\",
        \"cop_guidance_s3_uri\": \"s3://$BUCKET/inputs/cop_guidance.yaml\",
        \"asks_file_s3_uri\": \"s3://$BUCKET/inputs/asks.md\",
        \"per_team_threshold\": 5
    }" \
    /tmp/reports-response.json
```

> **PyYAML caveat:** if your `ownership.yaml` is **nested** (with `team:` / `domain:` / `contact_email:` blocks per entry), the Lambda needs PyYAML. Either flatten the YAML to `key: value`, or uncomment the PyYAML block in `projects/reports/build-lambda-zip.sh` and rebuild + redeploy.

---

## 5. Download the output from S3

The HTML reports are self-contained (embedded CSS + JS, no external assets), so you can download them and open in any browser.

```bash
# Whole reports folder for a given date
aws s3 sync s3://$BUCKET/reports/$DATE/ ./reports-$DATE/

# Or just one file
aws s3 cp s3://$BUCKET/reports/$DATE/executive-report.html ./executive-report.html
```

Open `executive-report.html` and `platform-report/index.html` directly in a browser. The CSV is the same `findings.csv` you'd get from a local run.

If others on the team need access without using the CLI, generate a **pre-signed URL** (works for ~1 hour, no AWS login needed):

```bash
aws s3 presign s3://$BUCKET/reports/$DATE/executive-report.html --expires-in 3600
```

Paste the resulting URL into Slack / email.

---

## 6. Troubleshooting + caveats

### 6.1 Lambda timing out at 15 minutes on a full scan

The scanner's `--limit/-n` flag exists for exactly this. Invoke with `"limit": 100` for the first hundred APIs, see how long it takes, scale concurrency:

```bash
# In the Lambda environment variables, bump:
SCANNER_CONCURRENCY=16     # default 8
```

(Update with `aws lambda update-function-configuration --function-name swagger-studio-scanner --environment ...`.)

If 600 APIs at concurrency 16 still won't fit, the architectural answer is **Step Functions** orchestrating multiple Lambda invocations with different `limit`/offset windows — separate work-item from this guide.

### 6.2 Reading CloudWatch logs

Every Lambda invocation writes to CloudWatch. Quick tail from CLI:

```bash
aws logs tail /aws/lambda/swagger-studio-scanner --since 10m --follow
```

Or in the Console: Lambda → your function → **Monitor** → **View CloudWatch logs**.

### 6.3 Common errors

| Error | Likely cause | Fix |
|---|---|---|
| `KeyError: 's3_bucket'` | Required field missing from invoke payload | Add `s3_bucket` to the event JSON |
| `botocore.exceptions.ClientError ... AccessDenied ... ssm:GetParameter` | Lambda role lacks SSM read permission | Re-run §1.3 to attach the inline policy |
| `... AccessDenied ... s3:PutObject` | Lambda role lacks S3 write to your bucket | Re-check the `Resource` ARN in `scanner-policy.json` matches `$BUCKET` |
| `Settings ... validation error ... swaggerhub_api_key Field required` | SSM_API_KEY_PARAMETER unset, or wrong name | Double-check the env var matches the SSM parameter name |
| `Settings ... swaggerhub_org Field required` | `SWAGGERHUB_ORG` env var not set on the Lambda | Set it via `update-function-configuration` |
| Image push fails with `denied: ... not authorized` | ECR auth expired (12-hour window) | Re-run `aws ecr get-login-password \| docker login ...` |
| `network_error` or TLS errors in scanner logs | Lambda VPC config routing through corporate egress | Make sure the Lambda is NOT attached to a VPC (default), or that the VPC has internet via NAT |

### 6.4 Cost

Both Lambdas are well under the AWS free tier for casual use:

- Scanner: 1 GB memory × ~5 min/run × 1 run/week = trivial (~$0.05/month)
- Reports: 512 MB × ~10 s/run × 1 run/week = trivial (a few cents/year)
- S3 storage: scan.json is ~1 MB per scan; HTML reports ~50 KB each. Negligible.
- ECR storage: ~100 MB for the scanner image. Negligible.

The big-bill risks (NAT Gateway, idle EC2, RDS) don't apply to this setup.

### 6.5 Local testing of the handler

You can invoke the handler directly with `python -c` against a real `.env` to debug logic without redeploying:

```bash
cd projects/swagger-studio-scanner/python
source .venv/bin/activate
SSM_API_KEY_PARAMETER=fake SWAGGERHUB_ORG=your-org python -c "
from swagger_studio_scanner.lambda_handler import handler
import os
os.environ['SWAGGERHUB_API_KEY'] = 'real-key'   # short-circuits SSM
print(handler({'s3_bucket': 'fake', 's3_prefix': 'test/', 'limit': 2}, None))
"
```

(You'll also need AWS credentials in your environment for the S3 upload to a real bucket, or stub `_s3.upload_file` in code temporarily.)

---

## See also

- [installation.md](installation.md) — toolchain setup for running locally
- [run-commands.md](run-commands.md) — full CLI reference (same commands, different runtime)
- [reports.md](reports.md) — Tier 1/2/3 input file design used by the reports Lambda
- [troubleshooting.md](troubleshooting.md) — corporate-laptop SSL diagnostics (why you might want Lambda in the first place)
