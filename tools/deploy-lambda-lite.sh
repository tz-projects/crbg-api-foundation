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

echo "==> Building shared deps layer (scanner + reports, python${PY_VERSION}) ..."
LAYER_PY="$BUILD/layer/python"
rm -rf "$BUILD/layer"; mkdir -p "$LAYER_PY"
pip install -r requirements.txt -r reports/requirements-pdf.txt --target "$LAYER_PY" \
    --python-version "$PY_VERSION" --only-binary=:all: --platform manylinux2014_x86_64 --quiet
find "$BUILD/layer" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -f "$BUILD/shared-deps-layer.zip"
( cd "$BUILD/layer" && zip -r -q "$BUILD/shared-deps-layer.zip" python )

echo "==> Building scanner code zip ..."
rm -f "$BUILD/scanner-code.zip"
( cd src && zip -r -q "$BUILD/scanner-code.zip" swagger_studio_scanner -x '*/__pycache__/*' )

echo "==> Building reports code zip ..."
rm -f "$BUILD/reports-code.zip"
( cd reports && zip -j -q "$BUILD/reports-code.zip" \
    lambda_handler.py generate_executive_report.py generate_platform_report.py \
    generate_pdf_reports.py _lib.py )
echo "    layer: $(du -h "$BUILD/shared-deps-layer.zip" | cut -f1)   scanner: $(du -h "$BUILD/scanner-code.zip" | cut -f1)   reports: $(du -h "$BUILD/reports-code.zip" | cut -f1)"

echo "==> Publishing shared dependency layer ..."
LAYER_ARN=$(aws lambda publish-layer-version \
    --layer-name "swagger-studio-shared-deps" \
    --zip-file "fileb://$BUILD/shared-deps-layer.zip" \
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

echo "==> Deploying reports function ($REPORTS_FN) — same shared layer ..."
if fn_exists "$REPORTS_FN"; then
    aws lambda update-function-code --function-name "$REPORTS_FN" \
        --zip-file "fileb://$BUILD/reports-code.zip" "${REGION_ARG[@]}" >/dev/null
    aws lambda wait function-updated --function-name "$REPORTS_FN" "${REGION_ARG[@]}"
    aws lambda update-function-configuration --function-name "$REPORTS_FN" \
        --layers "$LAYER_ARN" --timeout 120 --memory-size 1024 "${REGION_ARG[@]}" >/dev/null
    echo "    updated"
else
    aws lambda create-function --function-name "$REPORTS_FN" \
        --runtime "python${PY_VERSION}" \
        --handler lambda_handler.handler \
        --zip-file "fileb://$BUILD/reports-code.zip" \
        --layers "$LAYER_ARN" \
        --role "$LAMBDA_ROLE_ARN" \
        --timeout 120 --memory-size 1024 \
        "${REGION_ARG[@]}" >/dev/null
    echo "    created"
fi

echo ""
echo "Done. Both functions deployed. Run a scan + reports with:"
echo "  bash run-lambda-lite.sh"
