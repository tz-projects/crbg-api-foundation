#!/usr/bin/env bash
# Turn scanner-source.zip into the scanner's two Lambda artifacts.
#
# Run this in AWS CloudShell (or any Linux/Mac with pip + zip). It does NOT
# need Docker. It uses pip's --platform flags to fetch Linux wheels for the
# Lambda runtime, so the compiled dependency (pydantic-core) is the correct
# build regardless of what machine you run this on.
#
# Produces:
#   scanner-deps-layer.zip   the dependencies, in Lambda Layer layout
#                            (everything under python/). Publish as a layer.
#   scanner-code.zip         just the scanner package source. The function code.
#
# Usage:
#   bash build-scanner-layer.sh [source] [output-dir] [py-version]
#
# `source` may be:
#   - omitted / "."      build from the current folder (run it after you
#                        unzip scanner-source.zip and cd into it)
#   - a directory        build from that folder
#   - a scanner-source.zip  unzip it first, then build
#
# Examples (all equivalent end result):
#   unzip scanner-source.zip && cd scanner-source && bash build-scanner-layer.sh
#   bash build-scanner-layer.sh scanner-source.zip
#   bash build-scanner-layer.sh ./some/dir ./out 3.13
#
# See docs/aws-lambda-runbook.md for the full deploy sequence.

set -euo pipefail

SRC="${1:-.}"
OUT_DIR="${2:-$(pwd)/lambda-build}"
PYVER="${3:-3.13}"

WORK=""
cleanup() { [ -n "$WORK" ] && rm -rf "$WORK"; }
trap cleanup EXIT

if [ -f "$SRC" ] && [[ "$SRC" == *.zip ]]; then
    WORK="$(mktemp -d)"
    SRC_ABS="$(cd "$(dirname "$SRC")" && pwd)/$(basename "$SRC")"
    echo "Unpacking $SRC_ABS ..."
    unzip -q "$SRC_ABS" -d "$WORK"
    SRCROOT="$WORK"
elif [ -d "$SRC" ]; then
    SRCROOT="$(cd "$SRC" && pwd)"
else
    echo "ERROR: '$SRC' is neither a .zip file nor a directory"; exit 1
fi

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"

# Sanity-check the source contained what we expect.
[ -f "$SRCROOT/requirements.txt" ] || { echo "ERROR: requirements.txt not found in $SRCROOT"; exit 1; }
[ -d "$SRCROOT/src/swagger_studio_scanner" ] || { echo "ERROR: src/swagger_studio_scanner not found in $SRCROOT"; exit 1; }
WORK="${WORK:-$(mktemp -d)}"

# ---- Dependency layer ---------------------------------------------------
# --platform + --only-binary forces Linux wheels for the target Python,
# so the layer is correct even when built on Mac/Windows/older CloudShell.
echo "Installing dependencies for python${PYVER} (manylinux wheels) ..."
mkdir -p "$WORK/layer/python"
pip install \
    -r "$SRCROOT/requirements.txt" \
    --target "$WORK/layer/python" \
    --python-version "$PYVER" \
    --only-binary=:all: \
    --platform manylinux2014_x86_64 \
    --quiet

# Drop caches so the layer is lean.
find "$WORK/layer" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$WORK/layer" -type f -name '*.pyc' -delete 2>/dev/null || true

rm -f "$OUT_DIR/scanner-deps-layer.zip"
( cd "$WORK/layer" && zip -r -q "$OUT_DIR/scanner-deps-layer.zip" python )

# ---- Code zip -----------------------------------------------------------
rm -f "$OUT_DIR/scanner-code.zip"
( cd "$SRCROOT/src" && zip -r -q "$OUT_DIR/scanner-code.zip" swagger_studio_scanner -x '*/__pycache__/*' )

echo ""
echo "Built:"
echo "  $OUT_DIR/scanner-deps-layer.zip   ->  aws lambda publish-layer-version"
echo "  $OUT_DIR/scanner-code.zip         ->  function code (handler: swagger_studio_scanner.lambda_handler.handler)"
echo ""
du -h "$OUT_DIR/scanner-deps-layer.zip" "$OUT_DIR/scanner-code.zip"
echo ""
echo "Layer top-level (should be 'python/'):"
unzip -l "$OUT_DIR/scanner-deps-layer.zip" | awk 'NR>3 && $4 {print $4}' | cut -d/ -f1 | sort -u | sed 's/^/  /'
