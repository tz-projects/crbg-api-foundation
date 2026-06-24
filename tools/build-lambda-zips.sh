#!/usr/bin/env bash
# Build the THREE Lambda zips for hand-off (no deploy, no AWS calls).
#
# Produces (default <repo>/dist/):
#   1. scanner-deps-layer.zip   the dependencies, as a Lambda Layer (python/ layout)
#   2. scanner-code.zip         the scanner code (handler: swagger_studio_scanner.lambda_handler.handler)
#   3. reports-code.zip         the reports code (handler: lambda_handler.handler)
#
# Upload the three zips wherever you like (SharePoint, S3, etc.) and have
# whoever owns AWS create the functions from them. See docs/aws-lambda-handoff.md
# for the exact function settings (runtime / handler / layer / env vars).
#
# The layer is built with manylinux wheels for the Lambda runtime, so it is
# Lambda-correct even when this runs on Mac/Windows/CloudShell.
#
# Usage:
#   bash tools/build-lambda-zips.sh [output-dir] [py-version]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCANNER_PY="$REPO_ROOT/projects/swagger-studio-scanner/python"
REPORTS="$REPO_ROOT/projects/reports"
OUT_DIR="${1:-$REPO_ROOT/dist}"
PYVER="${2:-3.13}"

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# ---- 1. Dependency layer (the only Linux-specific build) ----------------
echo "==> [1/3] scanner-deps-layer.zip  (installing manylinux wheels for python${PYVER}) ..."
mkdir -p "$STAGE/layer/python"
pip install \
    -r "$SCANNER_PY/requirements.txt" \
    --target "$STAGE/layer/python" \
    --python-version "$PYVER" \
    --only-binary=:all: \
    --platform manylinux2014_x86_64 \
    --quiet
find "$STAGE/layer" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -f "$OUT_DIR/scanner-deps-layer.zip"
( cd "$STAGE/layer" && zip -r -q "$OUT_DIR/scanner-deps-layer.zip" python )

# ---- 2. Scanner code (pure Python) --------------------------------------
echo "==> [2/3] scanner-code.zip ..."
rm -f "$OUT_DIR/scanner-code.zip"
( cd "$SCANNER_PY/src" && zip -r -q "$OUT_DIR/scanner-code.zip" swagger_studio_scanner -x '*/__pycache__/*' )

# ---- 3. Reports code (pure Python, files at zip root) -------------------
echo "==> [3/3] reports-code.zip ..."
rm -f "$OUT_DIR/reports-code.zip"
( cd "$REPORTS" && zip -j -q "$OUT_DIR/reports-code.zip" \
    lambda_handler.py generate_executive_report.py generate_platform_report.py _lib.py )

echo ""
echo "Built in $OUT_DIR :"
for z in scanner-deps-layer.zip scanner-code.zip reports-code.zip; do
    printf "  %-26s %s\n" "$z" "$(du -h "$OUT_DIR/$z" | cut -f1)"
done
echo ""
echo "Hand these to whoever creates the Lambda functions. Settings: docs/aws-lambda-handoff.md"
