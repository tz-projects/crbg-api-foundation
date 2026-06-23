# AWS Lambda walkthrough — a beginner's hand-holding guide

A slow, concept-first companion to [aws-lambda-deployment.md](aws-lambda-deployment.md). That doc is the terse command reference; **this doc explains what each step does, why, and — crucially — how to confirm it actually worked** before you move on.

Scope: the **scanner** and the **reports generator** only. The ruleset publisher is intentionally skipped.

You are not expected to run anything while reading this. It's a map. When you're ready to act, each step has the command and a validation check right next to it.

> **Just want the runnable steps for the no-Git / no-Docker path?** Go straight to [aws-lambda-runbook.md](aws-lambda-runbook.md) — it's the copy-paste sequence that matches a locked-down VDI (package on the VDI, build the scanner in CloudShell as a Layer, no container image). This walkthrough explains the concepts behind it.

> **Company-account reality:** in a corporate AWS account, you often **cannot create some of these resources yourself** — especially IAM roles. Each step below is marked with **who typically does it**. Your real first move may be sending the cloud team a request listing what you need. The validation checks let you confirm they built it correctly once they hand it back.

---

## Part 1 — The mental model (read this first)

### A Lambda is not a server

A Lambda function is **your code sitting in AWS, asleep, until something pokes it.** When poked ("invoked"), AWS:

1. Grabs your code
2. Runs one specific function in it (the "handler")
3. Returns whatever that function returns
4. Goes back to sleep

No machine to start or stop. For you, the "poke" is **clicking a Test button** in the Console or running one `aws lambda invoke` command. Manual, on demand.

### The "handler" — the one new piece of code

Normally you run the scanner as `scanner scan` in a terminal. Lambda has no terminal — it can't type that. It needs **one Python function it can call directly**:

```python
def handler(event, context):
    # do the work
    return result
```

- `event` = the input you send when you poke it (small JSON, e.g. "scan 10 APIs, save here")
- `return` = what comes back to you

This handler **does not replace your scanner**. It's a thin doorway Lambda knows how to knock on, which then calls your existing, unchanged scanner code behind it. (Already written: `lambda_handler.py` in each project.)

### Why two different packaging methods

To run in Lambda you ship **your code + all the libraries it depends on**. There are two ways to bundle that, and a plain zip has a size limit (~250 MB unzipped).

| Program | Dependencies | Method | Why |
|---|---|---|---|
| **Reports** | None (pure standard library) | **Zip** | Tiny — 28 KB. Simplest possible. |
| **Scanner** | ~25 libraries (httpx, pydantic, …) | **Container image** | Bigger, fiddlier to zip correctly. A container image sidesteps the size limit and the "did I bundle the libs right?" problem. |

A "container image" is just **a heavier box for code with lots of dependencies.** More on that in Part 4.

### The whole journey on one page

| Phase | What | Who usually does it |
|---|---|---|
| **A1** | S3 bucket (cloud folder for results) | You or cloud team |
| **A2** | SSM secret (safe home for the API key) | You or cloud team |
| **A3** | IAM roles (permission slips) | **Cloud team** (locked down) |
| **B1–B3** | Package + deploy the **scanner** (container image → ECR → Lambda) | You |
| **C1–C2** | Package + deploy the **reports** (zip → Lambda) | You |
| **D1–D3** | Run them, get HTML out of S3 | You |

Everything in Phase A is **one-time setup**. B/C/D are repeatable.

---

## Part 2 — How to read the validation checks

After each resource, you'll see a box like this:

> **✅ Validate it worked**
> - **Command:** the one-liner to check
> - **Success looks like:** what you should see
> - **Failure looks like:** common wrong outputs and what they mean

Run the validation **before moving to the next step.** If a resource isn't right, everything built on top of it fails with confusing errors later. Validating as you go turns a 2-hour debugging session into a 10-second check.

A note on the AWS CLI: every command starts with `aws`. If you ever get `command not found: aws`, you're not in CloudShell or on a machine with the CLI installed. Most validation commands are **read-only** (`describe`, `get`, `list`) — safe to run repeatedly, they change nothing.

---

## Part 3 — Phase A: the shared furniture

Set two variables once at the top of your terminal session; the commands below reuse them:

```bash
BUCKET=your-org-swagger-governance     # pick a unique name (ask cloud team re: naming rules)
REGION=us-east-1                        # pick one region, use it everywhere
```

> **✅ Validate your setup before you start**
> - **Command:** `aws sts get-caller-identity`
> - **Success looks like:** a JSON blob with `Account`, `UserId`, `Arn` — proves you're authenticated to AWS and shows *which* account you're in. **Check the `Account` number is the company account you expect.**
> - **Failure looks like:** `Unable to locate credentials` → you're not logged in / not in CloudShell. Sort this before anything else.

### A1 — The S3 bucket (the pantry)

**Concept:** S3 is AWS's file storage. A "bucket" is a uniquely-named top-level folder. The scanner drops `scan.json` here; the reports read it and write HTML back. It's the shared space both programs communicate through.

**Who:** You, possibly the cloud team (bucket creation is sometimes restricted; naming conventions common).

**Command:**
```bash
aws s3api create-bucket \
    --bucket $BUCKET \
    --region $REGION \
    --create-bucket-configuration LocationConstraint=$REGION
# (For us-east-1 ONLY, drop the --create-bucket-configuration line — AWS quirk.)
```

> **✅ Validate it worked**
> - **Command:** `aws s3api head-bucket --bucket $BUCKET && echo "EXISTS and reachable"`
> - **Success looks like:** prints `EXISTS and reachable` with no error. You can also run `aws s3 ls s3://$BUCKET/` — it returns nothing (empty bucket) but no error, which is correct.
> - **Failure looks like:**
>   - `Not Found` / `404` → bucket doesn't exist (creation failed or wrong name).
>   - `Forbidden` / `403` → bucket exists but belongs to someone else (S3 names are global) **or** you lack permission. Pick a more unique name, or ask the cloud team.
> - **Console check:** S3 service → you should see `your-org-swagger-governance` in the bucket list.

### A2 — The secret drawer for the API key (SSM Parameter Store)

**Concept:** The scanner needs the SwaggerHub API key. Never paste it into Lambda settings in plain text. Store it once here as an encrypted "SecureString"; the Lambda fetches it at runtime. One safe home.

**Who:** Usually you. (Some companies prefer Secrets Manager or require a path prefix — ask first.)

**Command:**
```bash
aws ssm put-parameter \
    --name "/swagger-studio/api-key" \
    --type SecureString \
    --value "YOUR_SWAGGERHUB_API_KEY_HERE" \
    --description "Org-owner read key for the SwaggerHub scanner"
```

> **✅ Validate it worked**
> - **Command (existence + type, WITHOUT revealing the secret):**
>   ```bash
>   aws ssm get-parameter --name "/swagger-studio/api-key" \
>       --query 'Parameter.{Name:Name,Type:Type}' --output table
>   ```
> - **Success looks like:** a small table showing `Name = /swagger-studio/api-key` and `Type = SecureString`. The value is **not** printed (good — that's the point).
> - **Optional — confirm the value decrypts** (this *does* print the key, so only do it somewhere private):
>   ```bash
>   aws ssm get-parameter --name "/swagger-studio/api-key" --with-decryption \
>       --query 'Parameter.Value' --output text
>   ```
>   Should print your actual API key. If it does, the scanner Lambda will be able to read it too.
> - **Failure looks like:**
>   - `ParameterNotFound` → it wasn't created, or the name differs (check exact spelling/casing).
>   - `Type = String` instead of `SecureString` → it's stored **unencrypted**. Delete and recreate with `--type SecureString`.
> - **Console check:** Systems Manager → Parameter Store → you see `/swagger-studio/api-key` with type `SecureString`.

### A3 — The permission slips (IAM roles)

**Concept:** A Lambda can do **nothing** by default. An IAM role is a bundle of permissions you attach so the function may read *that one* secret and write to *that one* bucket — and nothing else. (Full scoping explained in [Part 6](#part-6--how-tight-can-the-permissions-be-least-privilege).)

**Who:** ⚠️ **Almost always the cloud team.** IAM is the most locked-down service in any company account. Expect `iam create-role` to be **denied** for you — that's by design. You'll likely hand them the JSON policies and ask them to create the roles. The validation below is exactly what you run when they hand the roles back, to confirm they're correct.

**Command (what the cloud team runs):**
```bash
# 1. Create the scanner role with a trust policy (lets Lambda use it)
cat > /tmp/lambda-trust.json <<'EOF'
{ "Version": "2012-10-17",
  "Statement": [{ "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole" }] }
EOF
aws iam create-role --role-name swagger-studio-scanner-role \
    --assume-role-policy-document file:///tmp/lambda-trust.json

# 2. Basic logging permission
aws iam attach-role-policy --role-name swagger-studio-scanner-role \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# 3. Scoped S3-write + SSM-read
cat > /tmp/scanner-policy.json <<EOF
{ "Version": "2012-10-17",
  "Statement": [
    {"Effect":"Allow","Action":["s3:PutObject"],
     "Resource":"arn:aws:s3:::$BUCKET/scans/*"},
    {"Effect":"Allow","Action":["ssm:GetParameter"],
     "Resource":"arn:aws:ssm:$REGION:*:parameter/swagger-studio/api-key"}
  ] }
EOF
aws iam put-role-policy --role-name swagger-studio-scanner-role \
    --policy-name scanner-inline --policy-document file:///tmp/scanner-policy.json
```

(The reports role is the same shape but with bucket read+write and **no** SSM access — see [aws-lambda-deployment.md §1.3](aws-lambda-deployment.md#13-create-an-iam-execution-role-for-each-lambda).)

> **✅ Validate it worked** (run these once the role exists — they're read-only)
> - **Role exists + get its ARN** (you'll need this ARN to create the Lambda):
>   ```bash
>   aws iam get-role --role-name swagger-studio-scanner-role \
>       --query 'Role.Arn' --output text
>   ```
>   Success: prints `arn:aws:iam::123456789012:role/swagger-studio-scanner-role`. **Copy this — it's needed in Phase B.**
> - **List the attached managed policies** (should include basic execution):
>   ```bash
>   aws iam list-attached-role-policies --role-name swagger-studio-scanner-role \
>       --query 'AttachedPolicies[].PolicyName' --output text
>   ```
>   Success: shows `AWSLambdaBasicExecutionRole`.
> - **Inspect the inline scoped policy** (confirm it points at YOUR bucket + secret, not `*`):
>   ```bash
>   aws iam get-role-policy --role-name swagger-studio-scanner-role \
>       --policy-name scanner-inline
>   ```
>   Success: the JSON shows `Resource` lines naming `your-bucket/scans/*` and your exact parameter ARN. **This is your least-privilege audit** — if you see `"Resource": "*"`, the policy is too broad; ask for it to be tightened.
> - **Failure looks like:**
>   - `NoSuchEntity` → role wasn't created, or wrong name.
>   - `AccessDenied` running `get-role` → you lack even read access to IAM; ask the cloud team to run these checks and screenshot the output for you.

### Phase A finish line

When all three validate green, you have an empty bucket, a safely-stored key, and two correctly-scoped roles — **but nothing runs yet.** You haven't touched the scanner or reports code at all. Next we package the actual programs.

---

## Part 4 — Phase B: package & deploy the scanner

The scanner has ~25 dependencies, so we use a **container image**.

### What is a container image (in one paragraph)

A container image is a **self-contained box** holding a mini Linux system, Python, your code, and all its libraries — everything needed to run, frozen together. You "build" it once from a recipe file (`Dockerfile.lambda`), upload it to AWS, and Lambda runs it. The advantage over a zip: no size limit and no guessing whether you bundled the right library versions — `pip install` runs *inside* the box at build time.

### B1 — Build the image

**Who:** You. Needs Docker — **CloudShell has it preinstalled**, which is the easiest place to do this.

**Command:**
```bash
git clone <your-repo-url>
cd <repo-name>/projects/swagger-studio-scanner/python
docker build -f Dockerfile.lambda -t swagger-studio-scanner-lambda:latest .
```

> **✅ Validate it worked**
> - **Command:** `docker images swagger-studio-scanner-lambda`
> - **Success looks like:** a row listing the image with a `latest` tag and a size (~200–400 MB). The build's last lines should read `Successfully built ...` / `Successfully tagged ...`.
> - **Failure looks like:** build stops with a red error. Most common: a `pip install` failure (network or a dependency issue) — re-read the last 20 lines; the failing package is named there.

### B2 — Upload the image to ECR

**Concept:** ECR (Elastic Container Registry) is AWS's storage for container images — like a private shelf Lambda can pull from.

**Who:** You (may need a permission the cloud team grants for ECR push).

**Command:**
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REPO=swagger-studio-scanner-lambda
aws ecr create-repository --repository-name $REPO --region $REGION || true

aws ecr get-login-password --region $REGION | \
    docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

IMAGE_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"
docker tag swagger-studio-scanner-lambda:latest $IMAGE_URI
docker push $IMAGE_URI
echo "Pushed: $IMAGE_URI"
```

> **✅ Validate it worked**
> - **Command:**
>   ```bash
>   aws ecr describe-images --repository-name swagger-studio-scanner-lambda \
>       --query 'imageDetails[].imageTags' --output text
>   ```
> - **Success looks like:** prints `latest` — confirms the image is now sitting in ECR. The `docker push` output should also have ended with size/digest lines, not an error.
> - **Failure looks like:**
>   - `RepositoryNotFoundException` → the `create-repository` step didn't run.
>   - `denied: ... not authorized` on push → ECR login expired (it lasts 12 hours) — re-run the `get-login-password | docker login` line.
> - **Console check:** ECR service → Repositories → `swagger-studio-scanner-lambda` → you see one image tagged `latest`.

### B3 — Create the Lambda function

**Who:** You (needs `lambda:CreateFunction` + permission to pass the role; cloud team may need to grant `iam:PassRole`).

**Command:**
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

> **✅ Validate it worked**
> - **Function exists + is ready:**
>   ```bash
>   aws lambda get-function --function-name swagger-studio-scanner \
>       --query 'Configuration.{State:State,LastUpdate:LastUpdateStatus}' --output table
>   ```
>   Success: `State = Active` and `LastUpdate = Successful`. (Right after creation it may briefly show `Pending` — wait ~30s and re-run until `Active`.)
> - **Confirm the env vars + role are set correctly:**
>   ```bash
>   aws lambda get-function-configuration --function-name swagger-studio-scanner \
>       --query '{Role:Role,Env:Environment.Variables,Timeout:Timeout,Memory:MemorySize}' --output json
>   ```
>   Success: shows your role ARN, `SWAGGERHUB_ORG` set to your real slug, `SSM_API_KEY_PARAMETER` matching the name from A2, timeout 900, memory 1024. **If `SWAGGERHUB_ORG` still says `your-org-slug`, you forgot to substitute it — fix with `update-function-configuration`.**
> - **Failure looks like:**
>   - `InvalidParameterValueException ... cannot be assumed by Lambda` → the role's trust policy is wrong (doesn't allow `lambda.amazonaws.com`). Back to A3.
>   - `AccessDeniedException ... iam:PassRole` → you lack permission to attach that role; ask the cloud team to grant `iam:PassRole` for this specific role.

---

## Part 5 — Phase C: package & deploy the reports

Reports are stdlib-only — a tiny zip, no Docker.

### C1 — Build the zip

**Who:** You.

**Command:**
```bash
cd <repo-root>
bash projects/reports/build-lambda-zip.sh /tmp/reports-lambda.zip
```

> **✅ Validate it worked**
> - **Command:** `unzip -l /tmp/reports-lambda.zip`
> - **Success looks like:** lists 4 files — `lambda_handler.py`, `generate_executive_report.py`, `generate_platform_report.py`, `_lib.py` — and the script prints `Built: ...` with a size around 28 KB.
> - **Failure looks like:** `No such file or directory` → you're not at the repo root, or the path is wrong.

### C2 — Create the Lambda function

**Who:** You (same `iam:PassRole` note as B3).

**Command:**
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

> **✅ Validate it worked**
> - **Command:**
>   ```bash
>   aws lambda get-function --function-name swagger-studio-reports \
>       --query 'Configuration.{State:State,Runtime:Runtime,Handler:Handler}' --output table
>   ```
> - **Success looks like:** `State = Active`, `Runtime = python3.13`, `Handler = lambda_handler.handler`.
> - **Failure looks like:** `Runtime.ImportModuleError` only shows up at *invoke* time, not creation — so getting `Active` here just means it's deployed, not that it runs. The real test is Phase D.

---

## Part 6 — How tight can the permissions be (least privilege)

You asked the right question: can each function be boxed into exactly what it needs? **Yes — to the exact resource, in both directions.**

### Per-function identity

Each Lambda has its **own** role. The scanner literally cannot use the reports' role. First layer of separation.

### Scoped to exact resources

| Role | Read the API key? | Write the bucket? | Read the bucket? |
|---|---|---|---|
| **scanner-role** | ✅ only `/swagger-studio/api-key` | ✅ only `bucket/scans/*` | ❌ |
| **reports-role** | ❌ **never** (no SSM permission at all) | ✅ only `bucket/reports/*` | ✅ only `bucket/scans/*` |

The reports Lambda has **zero** access to the API key — not "denied," simply never granted, so the secret is invisible to it. And each is scoped to a **sub-folder** (`scans/` vs `reports/`), not the whole bucket.

### Two directions of locking (defense in depth)

- **Identity side** (role policy): "this role may read that secret." — covered above.
- **Resource side** (bucket policy / KMS key policy): "only these roles may touch me." The bucket itself, and the encryption key on the secret, can name exactly which roles are allowed and deny all others. Company cloud teams often require this second layer.

### Tightest: only *this function* may use the role

By default any Lambda in the account could assume a given role. To pin a role to one specific function, add a trust-policy condition:

```json
"Condition": { "ArnLike": {
  "aws:SourceArn": "arn:aws:lambda:us-east-1:123456789012:function:swagger-studio-scanner"
}}
```

Advanced/optional, but available if security asks.

### What to validate

Run the `get-role-policy` check from A3 and **read the `Resource` lines**. If they name your exact bucket prefix and parameter ARN (no bare `*`), you have least privilege. This is your manual security audit.

---

## Part 7 — Phase D: run them and get output

Now the payoff. (Full invoke examples with all options are in [aws-lambda-deployment.md §4](aws-lambda-deployment.md#4-invoke-them-manually).)

### D1 — Run the scanner (small test first)

```bash
DATE=$(date +%Y-%m-%d)
aws lambda invoke \
    --function-name swagger-studio-scanner \
    --cli-binary-format raw-in-base64-out \
    --payload "{\"s3_bucket\":\"$BUCKET\",\"s3_prefix\":\"scans/${DATE}-test/\",\"limit\":10}" \
    /tmp/scanner-response.json

cat /tmp/scanner-response.json | python -m json.tool
```

> **✅ Validate it worked**
> - **The response file** should show `"statusCode": 200` and a `summary` with `total_apis: 10`.
> - **Confirm the output actually landed in S3:**
>   ```bash
>   aws s3 ls s3://$BUCKET/scans/${DATE}-test/
>   ```
>   Success: lists `scan.json` with a size and timestamp.
> - **If something failed, read the logs:**
>   ```bash
>   aws logs tail /aws/lambda/swagger-studio-scanner --since 10m
>   ```
> - **Failure signatures:**
>   - `AccessDenied ... ssm:GetParameter` → scanner role missing SSM read (A3).
>   - `AccessDenied ... s3:PutObject` → scanner role missing S3 write, or wrong bucket ARN.
>   - `swaggerhub_api_key Field required` → the SSM parameter name in the env var doesn't match A2.
>   - `network_error` → the Lambda can reach SwaggerHub? (Default Lambda networking can; a VPC-attached one may not.)

### D2 — Run the reports

```bash
aws lambda invoke \
    --function-name swagger-studio-reports \
    --cli-binary-format raw-in-base64-out \
    --payload "{\"scan_json_s3_uri\":\"s3://$BUCKET/scans/${DATE}-test/scan.json\",\"output_s3_prefix\":\"s3://$BUCKET/reports/${DATE}-test/\",\"org_display_name\":\"Your Org\",\"studio_base_url\":\"https://app.swaggerhub.com/apis\",\"placeholder_ask\":true}" \
    /tmp/reports-response.json

cat /tmp/reports-response.json | python -m json.tool
```

> **✅ Validate it worked**
> - **Response** shows `statusCode: 200` and lists the S3 URIs it wrote.
> - **Confirm the HTML landed:**
>   ```bash
>   aws s3 ls s3://$BUCKET/reports/${DATE}-test/ --recursive
>   ```
>   Success: lists `executive-report.html` and `platform-report/index.html` + `findings.csv`.

### D3 — Download and view

```bash
aws s3 sync s3://$BUCKET/reports/${DATE}-test/ ./reports-out/
# Open ./reports-out/executive-report.html in a browser.
```

Or share without giving AWS access — a pre-signed link (valid ~1 hour):
```bash
aws s3 presign s3://$BUCKET/reports/${DATE}-test/executive-report.html --expires-in 3600
```

> **✅ Validate it worked**
> - The downloaded `executive-report.html` opens in a browser and shows the governance report. That's the full pipeline confirmed end to end.

---

## Part 8 — Validation cheat sheet (one-glance reference)

Run top to bottom; each should succeed before the next is meaningful.

```bash
# Auth — who/where am I?
aws sts get-caller-identity

# A1 bucket
aws s3api head-bucket --bucket $BUCKET && echo OK

# A2 secret (existence + type, no reveal)
aws ssm get-parameter --name "/swagger-studio/api-key" --query 'Parameter.Type' --output text   # -> SecureString

# A3 roles
aws iam get-role --role-name swagger-studio-scanner-role --query 'Role.Arn' --output text
aws iam get-role-policy --role-name swagger-studio-scanner-role --policy-name scanner-inline   # audit Resource lines

# B image in ECR
aws ecr describe-images --repository-name swagger-studio-scanner-lambda --query 'imageDetails[].imageTags' --output text

# B/C functions
aws lambda get-function --function-name swagger-studio-scanner --query 'Configuration.State' --output text   # -> Active
aws lambda get-function --function-name swagger-studio-reports --query 'Configuration.State' --output text    # -> Active

# D output present after a run
aws s3 ls s3://$BUCKET/scans/  --recursive
aws s3 ls s3://$BUCKET/reports/ --recursive
```

---

## Part 9 — What to send your cloud team

Since IAM (and maybe S3/ECR) needs them, here's a ready-to-paste request:

> Hi — I need to deploy two manually-invoked Lambda functions for SwaggerHub governance reporting. Requesting:
>
> 1. **S3 bucket** (or permission to create one) for scan results + HTML reports. Happy to follow naming conventions.
> 2. **SSM SecureString parameter** `/swagger-studio/api-key` (or your preferred path) — I'll supply the value.
> 3. **Two Lambda execution roles**, least-privilege:
>    - `swagger-studio-scanner-role`: read **only** that one SSM parameter; `s3:PutObject` **only** on `bucket/scans/*`; basic Lambda logging.
>    - `swagger-studio-reports-role`: `s3:GetObject` on `bucket/scans/*`; `s3:GetObject`/`s3:PutObject` on `bucket/reports/*`; basic logging; **no** secret access.
> 4. Permission for me to **push to ECR** and **create/invoke** these two Lambda functions (incl. `iam:PassRole` for the two roles above).
>
> Exact JSON policies are in our repo at `docs/aws-lambda-deployment.md §1.3`. Both functions are manual-invoke only — no public endpoints, no schedules.

---

## See also

- [aws-lambda-deployment.md](aws-lambda-deployment.md) — the terse command reference this doc explains
- [run-commands.md](run-commands.md) — the same scanner/reports run locally
- [reports.md](reports.md) — the report tiers and input files
- [troubleshooting.md](troubleshooting.md) — why you may want Lambda (corporate SSL blocking local runs)
