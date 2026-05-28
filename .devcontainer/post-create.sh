#!/usr/bin/env bash
# Post-create provisioning for the api-foundation devcontainer.
# Runs ONCE on container creation. Idempotent so a rebuild is safe.

set -euo pipefail

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

log "Updating apt and installing baseline tools"
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  direnv \
  jq \
  curl \
  ca-certificates \
  make
sudo rm -rf /var/lib/apt/lists/*

log "Installing uv (Python package & project manager)"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

log "Installing pnpm via corepack"
sudo corepack enable
corepack prepare pnpm@latest --activate

log "Installing SwaggerHub CLI globally"
if ! command -v swaggerhub >/dev/null 2>&1; then
  npm install -g swaggerhub-cli
fi

log "Installing user dotfiles (zsh + Powerlevel10k)"
DEVCONTAINER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for dotfile in .zshrc .p10k.zsh; do
  if [ -f "${DEVCONTAINER_DIR}/${dotfile}" ]; then
    cp "${DEVCONTAINER_DIR}/${dotfile}" "${HOME}/${dotfile}"
    echo "  -> installed ${HOME}/${dotfile}"
  fi
done

log "Wiring direnv hook into zsh and bash"
grep -qxF 'eval "$(direnv hook zsh)"' ~/.zshrc 2>/dev/null \
  || echo 'eval "$(direnv hook zsh)"' >> ~/.zshrc
grep -qxF 'eval "$(direnv hook bash)"' ~/.bashrc 2>/dev/null \
  || echo 'eval "$(direnv hook bash)"' >> ~/.bashrc

log "Bootstrapping scanner sub-projects"
SCANNER_DIR="projects/swagger-studio-scanner"

if [ -f "${SCANNER_DIR}/python/pyproject.toml" ]; then
  log "  -> Python: uv sync"
  (cd "${SCANNER_DIR}/python" && uv sync --all-extras)
  # Pre-authorize the .envrc so direnv auto-activates the venv without prompting.
  (cd "${SCANNER_DIR}/python" && direnv allow . || true)
fi

if [ -f "${SCANNER_DIR}/typescript/package.json" ]; then
  log "  -> TypeScript: pnpm install"
  (cd "${SCANNER_DIR}/typescript" && pnpm install --frozen-lockfile=false)
fi

log "Done. Versions:"
python3 --version || true
uv --version || true
node --version || true
pnpm --version || true
swaggerhub --version || true
direnv --version || true
