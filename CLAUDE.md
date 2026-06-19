# CLAUDE.md — Working agreement for this workspace

Read first; auto-loaded by Claude Code on session start.

## Before doing anything

Read these two context documents in order — the first is *why*, the second is *what's built*:

1. **[smartbear-governance-enforcement-context.md](smartbear-governance-enforcement-context.md)** — design context: phases, standing decisions, constraints. The settled ground.
2. **[docs/implementation-context.md](docs/implementation-context.md)** — implementation snapshot: SwaggerHub REST findings (load-bearing knowledge that would take hours to re-derive), architectural choices made during construction, per-sub-project state, known gaps.

For day-to-day commands once you're oriented: [docs/runbook.md](docs/runbook.md).

For native install (work laptop, no Docker): [docs/installation.md](docs/installation.md).

## Conventions for this workspace

- **No Claude/Anthropic branding in commits.** Drop the `Co-Authored-By: Claude` trailer and the "Generated with Claude Code" footer. Commit messages read as the user's own authorship.
- **Python is the primary scanner runtime.** TypeScript is parity work; if there's a conflict between shipping Python vs. building TS to parity first, ship Python.
- **uv for Python, pnpm@10 for Node.** `pnpm@11` requires Node 22+; we're pinned to Node 20 LTS because that's the SwaggerHub CLI floor.
- **Shared `.env`.** Both sub-projects read `projects/swagger-studio-scanner/.env`. Don't introduce a second credentials file.
- **CLI backend is the trusted default for the ruleset publisher.** REST backend works and is verified, but CLI shells out to `swaggerhub spectral:upload` which is the documented mechanism.
- **Validate at boundaries, trust internally.** Pydantic models on Python REST adapters, zod on TS. Don't add defensive checks against well-typed internal code.
- **Don't commit captured HTTP transcripts.** `.har`, `http-requests.md`, anything with cookies/CSRF/tokens — gitignored. If you need to share them, sanitize first.
- **Verify against the live trial before marking work done.** Unit tests are necessary but not sufficient for anything that talks to SwaggerHub — endpoint shapes have surprised us repeatedly (Swagger URL parsing, `validation` response key, `id` vs `rulesetId`).

## Style

- Default to no code comments unless the *why* is non-obvious.
- Match existing file shape: structured logging via structlog/pino, no `print`/`console.log` for runtime output.
- Both languages run strict type-checking (`mypy --strict`, `tsc strict`). Don't loosen for convenience.
- Tests live next to the code: `tests/` in each sub-project, smoke + unit for pure logic; HTTP integration tests are still a gap.

## What's the next obvious work?

Per [docs/implementation-context.md §6](docs/implementation-context.md#6-known-issues--open-items):

1. TypeScript scanner parity — mirror the Python implementation (list_apis / get_findings / scan_org / report writers). ~30 min.
2. Work-laptop verification — full demo loop on a corporate-network machine.
3. HTTP integration tests for the activator GET→POST flow.

Anything else from §6 is later-phase work and should be confirmed with the user before starting.
