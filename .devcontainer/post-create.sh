#!/usr/bin/env bash
# Post-create provisioning for the api-foundation devcontainer.
# Runs ONCE after container creation. All system + user tooling is baked
# into the Dockerfile; this script only handles workspace-mounted setup
# (deps inside the project, direnv allow, etc.) that can't happen at
# image-build time because the workspace isn't mounted yet.

set -euo pipefail

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

log "Bootstrapping scanner sub-projects"
SCANNER_DIR="projects/swagger-studio-scanner"

if [ -f "${SCANNER_DIR}/python/pyproject.toml" ]; then
  log "  -> Python: uv sync"
  (cd "${SCANNER_DIR}/python" && uv sync --all-extras)
  (cd "${SCANNER_DIR}/python" && direnv allow . || true)
fi

if [ -f "${SCANNER_DIR}/typescript/package.json" ]; then
  log "  -> TypeScript: pnpm install"
  (cd "${SCANNER_DIR}/typescript" && pnpm install --frozen-lockfile=false)
fi

log "Versions"
{
  printf 'python3      : '; python3 --version
  printf 'uv           : '; uv --version
  printf 'node         : '; node --version
  printf 'pnpm         : '; pnpm --version
  printf 'swaggerhub   : '; swaggerhub --version
  printf 'gh           : '; gh --version | head -1
  printf 'direnv       : '; direnv --version
} 2>&1 || true

log "Done."
