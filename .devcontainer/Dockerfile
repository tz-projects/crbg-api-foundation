# syntax=docker/dockerfile:1.7
#
# api-foundation devcontainer image.
# Bakes in Python 3.12, Node 20, uv, pnpm, swaggerhub-cli, gh, direnv,
# oh-my-zsh, Powerlevel10k, and the user's shell dotfiles.
#
# Build context is .devcontainer/ (see devcontainer.json).

FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

ARG NODE_MAJOR=20
# pnpm 11+ requires Node 22.13; pin to 10.x (last major supporting Node 20 LTS).
ARG PNPM_VERSION=10

ENV DEBIAN_FRONTEND=noninteractive

# --- System packages (Ubuntu 24.04 ships Python 3.12 natively) ----------
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         python3 \
         python3-venv \
         python3-dev \
         python3-pip \
         direnv \
         jq \
         make \
         zsh \
         ca-certificates \
         gnupg \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && rm -rf /var/lib/apt/lists/*

# --- Node.js + pnpm (via corepack) --------------------------------------
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && corepack enable \
    && corepack prepare "pnpm@${PNPM_VERSION}" --activate

# --- GitHub CLI (gh) ----------------------------------------------------
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
         | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
         > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# --- SwaggerHub CLI (global npm) ----------------------------------------
RUN npm install -g swaggerhub-cli

# --- Powerlevel10k (system-wide install) --------------------------------
RUN git clone --depth=1 https://github.com/romkatv/powerlevel10k.git \
        /usr/local/share/powerlevel10k

# --- Per-user setup: oh-my-zsh, uv, dotfiles, default shell -------------
USER vscode
WORKDIR /home/vscode

# oh-my-zsh — base image already installs it, but install conditionally so
# this Dockerfile also works against bases that don't ship it.
RUN [ -d "$HOME/.oh-my-zsh" ] \
    || sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended

# uv — installs to ~/.local/bin
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Dotfiles (COPY late = small cache-bust surface when these change)
COPY --chown=vscode:vscode .zshrc  /home/vscode/.zshrc
COPY --chown=vscode:vscode .p10k.zsh /home/vscode/.p10k.zsh

# direnv hooks (idempotent — only appended if not already present)
RUN grep -qxF 'eval "$(direnv hook zsh)"' /home/vscode/.zshrc \
      || echo 'eval "$(direnv hook zsh)"' >> /home/vscode/.zshrc \
    && grep -qxF 'eval "$(direnv hook bash)"' /home/vscode/.bashrc \
      || echo 'eval "$(direnv hook bash)"' >> /home/vscode/.bashrc

# Default shell -> zsh (so SSH / non-VS-Code shells also land in zsh)
USER root
RUN chsh -s /usr/bin/zsh vscode

USER vscode
WORKDIR /workspaces

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    PNPM_HOME=/home/vscode/.local/share/pnpm \
    PATH=/home/vscode/.local/bin:/home/vscode/.local/share/pnpm:${PATH}
