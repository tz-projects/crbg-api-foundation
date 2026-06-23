#!/usr/bin/env bash
# Package the Python Lambda artifacts out of this mixed-language repo.
#
# The repo holds scanner + ruleset-publisher + reports in BOTH Python and
# TypeScript. For AWS Lambda we only ship two small Python payloads. This
# script stages JUST those (an allow-list) and ignores everything else —
# no node_modules, no TypeScript, no ruleset-publisher, no tests, no caches.
#
# Produces two zips (default: <repo>/dist/):
#
#   scanner-source.zip   TRANSPORT — requirements.txt + the scanner package
#                        source. Upload this to CloudShell, where you build the
#                        deps layer + code zip (deps need Linux wheels).
#
#   reports-lambda.zip   DEPLOYMENT — the 4 stdlib-only report files, already
#                        in Lambda's required layout (files at the zip root).
#                        Upload this straight to the Lambda Console — no build.
#
# Usage (from anywhere):
#   bash tools/package-lambda.sh [output-dir]
#
# See docs/aws-lambda-walkthrough.md for what to do with each zip.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCANNER_PY="$REPO_ROOT/projects/swagger-studio-scanner/python"
REPORTS="$REPO_ROOT/projects/reports"
OUT_DIR="${1:-$REPO_ROOT/dist}"

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# ---- Scanner: source transport zip --------------------------------------
SCAN_STAGE="$STAGE/scanner"
mkdir -p "$SCAN_STAGE"
cp "$SCANNER_PY/requirements.txt" "$SCAN_STAGE/"
cp -r "$SCANNER_PY/src" "$SCAN_STAGE/src"
# Bundle the CloudShell build script so the transport zip is self-contained:
# unzip it in CloudShell, then `bash build-scanner-layer.sh` builds the layer.
cp "$SCRIPT_DIR/build-scanner-layer.sh" "$SCAN_STAGE/"
# Strip Python caches so they don't bloat the transport zip.
find "$SCAN_STAGE" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$SCAN_STAGE" -type f -name '*.pyc' -delete 2>/dev/null || true

rm -f "$OUT_DIR/scanner-source.zip"
( cd "$SCAN_STAGE" && zip -r -q "$OUT_DIR/scanner-source.zip" . )

# ---- Reports: deployment-ready zip (files at root via -j) ---------------
rm -f "$OUT_DIR/reports-lambda.zip"
( cd "$REPORTS" && zip -j -q "$OUT_DIR/reports-lambda.zip" \
    lambda_handler.py \
    generate_executive_report.py \
    generate_platform_report.py \
    _lib.py )

echo ""
echo "Built:"
echo "  $OUT_DIR/scanner-source.zip   ->  upload to CloudShell, then build layer + code"
echo "  $OUT_DIR/reports-lambda.zip   ->  upload straight to the Lambda Console"
echo ""
echo "Contents check:"
echo "  scanner-source.zip:"
unzip -l "$OUT_DIR/scanner-source.zip" | sed 's/^/    /'
echo "  reports-lambda.zip:"
unzip -l "$OUT_DIR/reports-lambda.zip" | sed 's/^/    /'
