# swagger-studio-scanner

Org-wide non-conformance scanner for SmartBear Swagger Studio. Enumerates every API in an organization, pulls standardization findings, and produces a publishable report (JSON, CSV, HTML) with a rule Pareto as the headline.

Two implementations live side-by-side:

- [`python/`](./python/) — Python 3.13, uv, ruff, mypy, pytest, httpx (async)
- [`typescript/`](./typescript/) — Node 20, pnpm, eslint, prettier, vitest, native fetch + p-limit

Both target the same REST endpoints on `https://api.swaggerhub.com` and produce identically-shaped output. See [`smartbear-governance-enforcement-context.md`](../../smartbear-governance-enforcement-context.md) §8 for the design.

## Required configuration

Copy `.env.example` to `.env` and fill in:

| Variable | Purpose |
|---|---|
| `SWAGGERHUB_API_KEY` | Org-owner read key from `app.swaggerhub.com/settings/apiKey` |
| `SWAGGERHUB_ORG` | Organization (owner) slug to scan |
| `SWAGGERHUB_BASE_URL` | Defaults to `https://api.swaggerhub.com` (SaaS); override only for on-prem |

The `.env` file is read by both implementations. It is gitignored.

## Step-zero capability probe

Both CLIs expose a `probe` command that verifies:

1. Auth works (token is valid + has org-read scope)
2. The org is reachable
3. The `/standardization` endpoint returns data (i.e. the tier includes Governance — empty response is the silent-failure mode flagged in the context doc)

Run the probe before any full scan, especially on a fresh laptop where corporate proxy / SSL inspection may be in play.
