#!/usr/bin/env bash
# Build a deployment zip for the reports Lambda.
#
# Usage (from anywhere):
#   bash projects/reports/build-lambda-zip.sh [output-path]
#
# Default output: projects/reports/reports-lambda.zip
#
# Contents of the zip:
#   - lambda_handler.py
#   - generate_executive_report.py
#   - generate_platform_report.py
#   - _lib.py
#
# All stdlib-only. boto3 is preinstalled in the Lambda Python runtime, so it
# is NOT bundled. If you need PyYAML for nested ownership maps, install it
# into a sibling folder and add it to the zip — see comments below.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$SCRIPT_DIR/reports-lambda.zip}"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"

cd "$SCRIPT_DIR"

# Wipe previous build
rm -f "$OUT"

# Bundle only the runtime files — skip docs, sample outputs, etc.
zip -j "$OUT" \
    lambda_handler.py \
    generate_executive_report.py \
    generate_platform_report.py \
    _lib.py

# --- Optional: bundle PyYAML for nested ownership maps ---
# Uncomment the block below if your ownership map is nested (team:/domain:/...).
# Flat key:value YAML works without PyYAML thanks to the bundled fallback parser.
#
# TMP=$(mktemp -d)
# pip install --target "$TMP" pyyaml --quiet
# (cd "$TMP" && zip -r "$OUT" yaml _yaml*)
# rm -rf "$TMP"

echo "Built: $OUT"
echo "Size : $(du -h "$OUT" | cut -f1)"
echo "Files: $(unzip -l "$OUT" | tail -1 | awk '{print $2}')"
