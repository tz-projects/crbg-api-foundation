#!/usr/bin/env bash
# Push the sample APIs to Swagger Studio under the org from .env.
# Idempotent: uses api:create if the API doesn't exist, api:update otherwise.

set -euo pipefail

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m!!\033[0m %s\n' "$*" >&2; }

# --- Resolve env -------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SAMPLES_DIR="${SCRIPT_DIR}"
ENV_FILE="${SCRIPT_DIR}/../.env"

if [ -f "${ENV_FILE}" ]; then
  set -a; source "${ENV_FILE}"; set +a
fi

: "${SWAGGERHUB_API_KEY:?SWAGGERHUB_API_KEY must be set (export or .env)}"
: "${SWAGGERHUB_ORG:?SWAGGERHUB_ORG must be set (export or .env)}"

if ! command -v swaggerhub >/dev/null 2>&1; then
  err "swaggerhub-cli not found on PATH. (Should be installed in the devcontainer.)"
  exit 1
fi

# --- Push one spec ----------------------------------------------------
# Usage: push_one <api-name> <version> <file>
push_one() {
  local name="$1" version="$2" file="$3"
  local slug="${SWAGGERHUB_ORG}/${name}/${version}"

  if [ ! -f "${file}" ]; then
    err "missing spec file: ${file}"; return 1
  fi

  log "Pushing ${slug}  <-  ${file##*/}"

  if swaggerhub api:get "${slug}" >/dev/null 2>&1; then
    swaggerhub api:update "${slug}" --file "${file}" --visibility=private --published=unpublish
    echo "  -> updated"
  else
    swaggerhub api:create "${slug}" --file "${file}" --visibility=private --published=unpublish --setdefault
    echo "  -> created"
  fi

  echo "  -> https://app.swaggerhub.com/apis/${SWAGGERHUB_ORG}/${name}/${version}"
}

# --- Push both samples -----------------------------------------------
push_one "scanner-good-petstore" "1.0.0" "${SAMPLES_DIR}/good-petstore.yaml"
push_one "scanner-bad-petstore"  "1.0.0" "${SAMPLES_DIR}/bad-petstore.yaml"

log "Done."
echo "Wait ~10-30s for SwaggerHub to evaluate standardization, then run:"
echo "  cd projects/swagger-studio-scanner/python && uv run scanner scan"
