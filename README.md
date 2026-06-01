# api-foundation

Workspace for the API Foundation initiative. Holds the tooling that drives API governance enforcement, publishing, and the API marketplace surface.

## Layout

```
.
├── .devcontainer/              # Reproducible dev environment (Python + Node + SwaggerHub CLI)
├── .vscode/                    # Shared editor settings & recommended extensions
├── projects/                   # One folder per sub-project
│   ├── swagger-studio-scanner/ # Org-wide non-conformance scanner (Phase 1)
│   │   ├── python/             # Python implementation (uv + ruff + mypy + pytest)
│   │   └── typescript/         # TypeScript implementation (pnpm + eslint + prettier + vitest)
│   ├── swagger-studio-ruleset/ # Source-of-truth Spectral ruleset + publisher
│   │   ├── ruleset/            # Spectral rules (uploaded to Studio)
│   │   ├── python/             # Publisher: CLI + REST backends
│   │   └── typescript/         # Publisher: CLI + REST backends
│   └── reports/                # Executive + platform team report generators (Phase 1)
│                               # Stdlib-only Python; consume scan.json, emit self-contained HTML + CSV
└── pnpm-workspace.yaml         # Monorepo workspace pointer for all TS sub-projects
```

Each sub-project under `projects/` is self-contained: its own dependency manifest, lockfile, tests, and CLI. The Python and TypeScript folders inside a sub-project are independent implementations of the same surface — built side-by-side so the work can be compared end-to-end.

## Development environment

There are two supported paths:

1. **Devcontainer (recommended where Docker is available — typically personal laptop)** — see below.
2. **Native install (work laptop, no Docker)** — see [`docs/installation.md`](docs/installation.md) for step-by-step Python and TypeScript install paths, plus corporate-network gotchas (proxy, SSL inspection, CA bundle, registry mirrors).

### Devcontainer

Open the repo in VS Code and accept "Reopen in Container". The devcontainer installs:

- Python 3.12 + [`uv`](https://docs.astral.sh/uv/) (package & project manager)
- Node 20 LTS + `pnpm` (via corepack)
- `swaggerhub-cli` (global)
- `direnv` (auto-activates Python venvs on `cd`)
- `gh`, `git`, `jq`, `make`

After the container builds, the post-create hook runs `uv sync` and `pnpm install` for each sub-project so the workspace is ready to use immediately.

## Quick checks

```bash
# Python sub-project
cd projects/swagger-studio-scanner/python
uv run scanner --help        # CLI entry point
uv run pytest                # Unit tests
uv run ruff check .          # Lint
uv run mypy src              # Types

# TypeScript sub-project
cd projects/swagger-studio-scanner/typescript
pnpm dev -- --help           # CLI entry point
pnpm test                    # Unit tests
pnpm lint                    # ESLint
pnpm typecheck               # tsc --noEmit

# Ruleset publisher (Python)
cd projects/swagger-studio-ruleset/python
uv run ruleset-publisher publish                    # CLI backend (default)
uv run ruleset-publisher publish --backend rest     # REST backend

# Ruleset publisher (TypeScript)
cd projects/swagger-studio-ruleset/typescript
pnpm dev publish
pnpm dev publish --backend rest
```

## Day-to-day commands

- [`docs/runbook.md`](docs/runbook.md) — consolidated command reference: per-sub-project commands, the full end-to-end demo loop (publish ruleset → push samples → scan → reports), reset between runs, troubleshooting matrix.
- [`docs/reports.md`](docs/reports.md) — executive + platform team report generators, including the optional ownership map / rule display name / CoP guidance / asks file inputs.
- [`docs/installation.md`](docs/installation.md) — native (work-laptop, no-Docker) install paths for the Python and TypeScript toolchains, plus corporate-network gotchas.

## Adding a new sub-project

Create `projects/<name>/{python,typescript}/` following the same layout as `swagger-studio-scanner`. The TS half is auto-picked up by `pnpm-workspace.yaml`; the Python half is independent (each has its own `pyproject.toml` and venv).

## Context

For background on the wider initiative — phases, decisions, constraints — see [smartbear-governance-enforcement-context.md](smartbear-governance-enforcement-context.md).
