#!/usr/bin/env bash
# Deploy the LITE Lambda variant from inside CloudShell.
#
# Run from the unzipped lambda-lite bundle directory. Builds the scanner
# layer + code and the reports zip, publishes the layer, and creates (or
# updates) both Lambda functions. No S3, no SSM — the API key goes into a
# plain env var on the scanner function.
#
# Configure via environment variables (or edit the defaults below):
#
#   SWAGGERHUB_API_KEY   (required) org-owner read key
#   SWAGGERHUB_ORG       (required) org slug
#   LAMBDA_ROLE_ARN      (required) execution role ARN (logging-only is enough)
#   AWS_REGION           (optional) defaults to the CLI's configured region
#   PY_VERSION           (optional) defaults to 3.13
#   SCANNER_FN           (optional) defaults to swagger-studio-scanner
#   REPORTS_FN           (optional) defaults to swagger-studio-reports
#
# Usage:
#   export SWAGGERHUB_API_KEY=...   SWAGGERHUB_ORG=...   LAMBDA_ROLE_ARN=arn:aws:iam::...:role/...
#   bash deploy-lambda-lite.sh
#
# See docs/aws-lambda-lite.md.

set -euo pipefail

: "${SWAGGERHUB_API_KEY:?Set SWAGGERHUB_API_KEY}"
: "${SWAGGERHUB_ORG:?Set SWAGGERHUB_ORG}"
: "${LAMBDA_ROLE_ARN:?Set LAMBDA_ROLE_ARN (a Lambda execution role; logging-only is fine)}"

PY_VERSION="${PY_VERSION:-3.13}"
SCANNER_FN="${SCANNER_FN:-swagger-studio-scanner}"
REPORTS_FN="${REPORTS_FN:-swagger-studio-reports}"
REGION_ARG=()
[ -n "${AWS_REGION:-}" ] && REGION_ARG=(--region "$AWS_REGION")

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

[ -f requirements.txt ] || { echo "ERROR: run this from the unzipped lambda-lite bundle (requirements.txt not found)"; exit 1; }
[ -d reports ] || { echo "ERROR: reports/ not found in bundle"; exit 1; }

BUILD="$HERE/build"
mkdir -p "$BUILD"

echo "==> Building scanner layer + code (python${PY_VERSION}) ..."
bash build-scanner-layer.sh . "$BUILD" "$PY_VERSION" >/dev/null
echo "    layer: $(du -h "$BUILD/scanner-deps-layer.zip" | cut -f1)   code: $(du -h "$BUILD/scanner-code.zip" | cut -f1)"

echo "==> Building reports zip (+ reportlab/pillow for PDF) ..."
rm -f "$BUILD/reports-lambda.zip"
RSTAGE="$BUILD/reports-stage"
rm -rf "$RSTAGE"; mkdir -p "$RSTAGE"
cp reports/lambda_handler.py reports/generate_executive_report.py \
   reports/generate_platform_report.py reports/generate_pdf_reports.py \
   reports/_lib.py "$RSTAGE/"
pip install -r reports/requirements-pdf.txt --target "$RSTAGE" \
    --python-version "$PY_VERSION" --only-binary=:all: --platform manylinux2014_x86_64 --quiet
find "$RSTAGE" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
( cd "$RSTAGE" && zip -r -q "$BUILD/reports-lambda.zip" . )

echo "==> Publishing dependency layer ..."
LAYER_ARN=$(aws lambda publish-layer-version \
    --layer-name "${SCANNER_FN}-deps" \
    --zip-file "fileb://$BUILD/scanner-deps-layer.zip" \
    --compatible-runtimes "python${PY_VERSION}" \
    "${REGION_ARG[@]}" \
    --query 'LayerVersionArn' --output text)
echo "    $LAYER_ARN"

# create-or-update helper for a function
fn_exists() { aws lambda get-function --function-name "$1" "${REGION_ARG[@]}" >/dev/null 2>&1; }

echo "==> Deploying scanner function ($SCANNER_FN) ..."
SCANNER_ENV="Variables={SWAGGERHUB_API_KEY=$SWAGGERHUB_API_KEY,SWAGGERHUB_ORG=$SWAGGERHUB_ORG,SCANNER_LOG_LEVEL=INFO}"
if fn_exists "$SCANNER_FN"; then
    aws lambda update-function-code --function-name "$SCANNER_FN" \
        --zip-file "fileb://$BUILD/scanner-code.zip" "${REGION_ARG[@]}" >/dev/null
    aws lambda wait function-updated --function-name "$SCANNER_FN" "${REGION_ARG[@]}"
    aws lambda update-function-configuration --function-name "$SCANNER_FN" \
        --layers "$LAYER_ARN" --environment "$SCANNER_ENV" \
        --timeout 900 --memory-size 1024 "${REGION_ARG[@]}" >/dev/null
    echo "    updated"
else
    aws lambda create-function --function-name "$SCANNER_FN" \
        --runtime "python${PY_VERSION}" \
        --handler swagger_studio_scanner.lambda_handler.handler \
        --zip-file "fileb://$BUILD/scanner-code.zip" \
        --layers "$LAYER_ARN" \
        --role "$LAMBDA_ROLE_ARN" \
        --timeout 900 --memory-size 1024 \
        --environment "$SCANNER_ENV" \
        "${REGION_ARG[@]}" >/dev/null
    echo "    created"
fi

echo "==> Deploying reports function ($REPORTS_FN) ..."
if fn_exists "$REPORTS_FN"; then
    aws lambda update-function-code --function-name "$REPORTS_FN" \
        --zip-file "fileb://$BUILD/reports-lambda.zip" "${REGION_ARG[@]}" >/dev/null
    echo "    updated"
else
    aws lambda create-function --function-name "$REPORTS_FN" \
        --runtime "python${PY_VERSION}" \
        --handler lambda_handler.handler \
        --zip-file "fileb://$BUILD/reports-lambda.zip" \
        --role "$LAMBDA_ROLE_ARN" \
        --timeout 120 --memory-size 1024 \
        "${REGION_ARG[@]}" >/dev/null
    echo "    created"
fi

echo ""
echo "Done. Both functions deployed. Run a scan + reports with:"
echo "  bash run-lambda-lite.sh"
