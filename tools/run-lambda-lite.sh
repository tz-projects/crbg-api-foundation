#!/usr/bin/env bash
# Run the LITE Lambda chain from CloudShell: scan -> reports -> HTML files.
#
# Invokes the scanner Lambda, pipes its inline scan.json into the reports
# Lambda, and writes the returned HTML + CSV to local files. No S3.
#
# Configure via environment variables (or accept the defaults):
#
#   ORG_DISPLAY_NAME   (optional) human-readable org name (default "Your Org")
#   STUDIO_BASE_URL    (optional) default https://app.swaggerhub.com/apis
#   SCAN_LIMIT         (optional) number of APIs to scan; empty = full scan
#   OUT_DIR            (optional) where to write outputs (default ./lite-output)
#   AWS_REGION         (optional) defaults to the CLI's configured region
#   SCANNER_FN         (optional) default swagger-studio-scanner
#   REPORTS_FN         (optional) default swagger-studio-reports
#
# Usage:
#   bash run-lambda-lite.sh                 # full scan
#   SCAN_LIMIT=25 bash run-lambda-lite.sh   # first 25 APIs
#
# Requires jq (preinstalled in CloudShell). See docs/aws-lambda-lite.md.

set -euo pipefail

command -v jq >/dev/null || { echo "ERROR: jq is required (preinstalled in CloudShell)"; exit 1; }

ORG_DISPLAY_NAME="${ORG_DISPLAY_NAME:-Your Org}"
STUDIO_BASE_URL="${STUDIO_BASE_URL:-https://app.swaggerhub.com/apis}"
OUT_DIR="${OUT_DIR:-./lite-output}"
SCANNER_FN="${SCANNER_FN:-swagger-studio-scanner}"
REPORTS_FN="${REPORTS_FN:-swagger-studio-reports}"
REGION_ARG=()
[ -n "${AWS_REGION:-}" ] && REGION_ARG=(--region "$AWS_REGION")

mkdir -p "$OUT_DIR"

# Build the scanner payload (with or without a limit).
if [ -n "${SCAN_LIMIT:-}" ]; then
    SCAN_PAYLOAD="{\"limit\": ${SCAN_LIMIT}}"
    echo "==> Scanning first ${SCAN_LIMIT} APIs ..."
else
    SCAN_PAYLOAD="{}"
    echo "==> Scanning full org ..."
fi

aws lambda invoke \
    --function-name "$SCANNER_FN" \
    --cli-binary-format raw-in-base64-out \
    --payload "$SCAN_PAYLOAD" \
    "${REGION_ARG[@]}" \
    "$OUT_DIR/scan-response.json" >/dev/null

# Surface scanner errors (Lambda may return a 200 invoke with a function error).
if jq -e '.errorMessage' "$OUT_DIR/scan-response.json" >/dev/null 2>&1; then
    echo "Scanner function error:"; jq '.errorMessage, .errorType' "$OUT_DIR/scan-response.json"; exit 1
fi
if [ "$(jq -r '.scan // "null"' "$OUT_DIR/scan-response.json")" = "null" ]; then
    echo "No scan returned. Response:"; jq '.' "$OUT_DIR/scan-response.json"; exit 1
fi

echo "    summary: $(jq -c '.summary' "$OUT_DIR/scan-response.json")"

# Build the reports payload from the scanner output.
jq --arg org "$ORG_DISPLAY_NAME" --arg studio "$STUDIO_BASE_URL" \
   '{scan: .scan, org_display_name: $org, studio_base_url: $studio, placeholder_ask: true}' \
   "$OUT_DIR/scan-response.json" > "$OUT_DIR/reports-payload.json"

echo "==> Generating reports ..."
aws lambda invoke \
    --function-name "$REPORTS_FN" \
    --cli-binary-format raw-in-base64-out \
    --payload "file://$OUT_DIR/reports-payload.json" \
    "${REGION_ARG[@]}" \
    "$OUT_DIR/reports-response.json" >/dev/null

if jq -e '.errorMessage' "$OUT_DIR/reports-response.json" >/dev/null 2>&1; then
    echo "Reports function error:"; jq '.errorMessage, .errorType' "$OUT_DIR/reports-response.json"; exit 1
fi

jq -r '.executive_html' "$OUT_DIR/reports-response.json" > "$OUT_DIR/executive-report.html"
jq -r '.platform_html'  "$OUT_DIR/reports-response.json" > "$OUT_DIR/platform-report.html"
jq -r '.findings_csv'   "$OUT_DIR/reports-response.json" > "$OUT_DIR/findings.csv"

# Tidy intermediate payloads.
rm -f "$OUT_DIR/reports-payload.json"

echo ""
echo "Done. Wrote to $OUT_DIR/:"
echo "  executive-report.html"
echo "  platform-report.html"
echo "  findings.csv"
echo "  scan-response.json  (raw scanner output; .scan is the scan.json)"
echo ""
echo "Download via CloudShell: Actions -> Download file"
