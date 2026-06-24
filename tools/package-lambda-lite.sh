#!/usr/bin/env bash
# Package the LITE Lambda variant as ONE self-contained bundle.
#
# Unlike the heavy packaging (two separate zips), the lite flow ships a single
# bundle you upload to CloudShell once. Inside CloudShell you run the bundled
# deploy + run scripts — no S3, no SSM.
#
# Produces (default: <repo>/dist/):
#   lambda-lite.zip   contains:
#                       requirements.txt
#                       src/swagger_studio_scanner/      (scanner code)
#                       reports/*.py                     (reports code)
#                       build-scanner-layer.sh           (builds the deps layer)
#                       deploy-lambda-lite.sh            (creates both functions)
#                       run-lambda-lite.sh               (scan -> reports -> HTML)
#
# Usage (from anywhere):
#   bash tools/package-lambda-lite.sh [output-dir]
#
# See docs/aws-lambda-lite.md for the full flow.

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
BUNDLE="$STAGE/lambda-lite"
mkdir -p "$BUNDLE/reports"

# Scanner source
cp "$SCANNER_PY/requirements.txt" "$BUNDLE/"
cp -r "$SCANNER_PY/src" "$BUNDLE/src"

# Reports source (the 4 stdlib files)
cp "$REPORTS/lambda_handler.py" \
   "$REPORTS/generate_executive_report.py" \
   "$REPORTS/generate_platform_report.py" \
   "$REPORTS/_lib.py" \
   "$BUNDLE/reports/"

# Bundled scripts
cp "$SCRIPT_DIR/build-scanner-layer.sh" \
   "$SCRIPT_DIR/deploy-lambda-lite.sh" \
   "$SCRIPT_DIR/run-lambda-lite.sh" \
   "$BUNDLE/"

# Strip caches
find "$BUNDLE" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$BUNDLE" -type f -name '*.pyc' -delete 2>/dev/null || true

rm -f "$OUT_DIR/lambda-lite.zip"
( cd "$STAGE" && zip -r -q "$OUT_DIR/lambda-lite.zip" lambda-lite )

echo "Built: $OUT_DIR/lambda-lite.zip"
echo ""
echo "Next: upload it to CloudShell, then:"
echo "  unzip lambda-lite.zip && cd lambda-lite"
echo "  bash deploy-lambda-lite.sh    # creates both Lambda functions"
echo "  bash run-lambda-lite.sh       # runs scan -> reports -> HTML"
echo ""
echo "Contents:"
unzip -l "$OUT_DIR/lambda-lite.zip" | awk 'NR>3 && $4 {print "  " $4}' | grep -vE '/$' | head -40
