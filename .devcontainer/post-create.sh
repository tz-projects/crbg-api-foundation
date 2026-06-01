#!/usr/bin/env bash
# Post-create provisioning for the api-foundation devcontainer.
# Runs ONCE after container creation. All system + user tooling is baked
# into the Dockerfile; this script only handles workspace-mounted setup
# (deps inside the project, direnv allow, etc.) that can't happen at
# image-build time because the workspace isn't mounted yet.

set -euo pipefail

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

log "Bootstrapping all sub-projects under projects/"

# Bootstrap every Python sub-project (any projects/<name>/python with pyproject.toml).
for pyproject in projects/*/python/pyproject.toml; do
  [ -f "${pyproject}" ] || continue
  proj_dir="$(dirname "${pyproject}")"
  log "  -> Python: uv sync in ${proj_dir}"
  (cd "${proj_dir}" && uv sync --all-extras)
  (cd "${proj_dir}" && direnv allow . || true)
done

# Bootstrap every TypeScript sub-project (any projects/<name>/typescript with package.json).
for pkg in projects/*/typescript/package.json; do
  [ -f "${pkg}" ] || continue
  proj_dir="$(dirname "${pkg}")"
  log "  -> TypeScript: pnpm install in ${proj_dir}"
  (cd "${proj_dir}" && pnpm install --frozen-lockfile=false)
done

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
