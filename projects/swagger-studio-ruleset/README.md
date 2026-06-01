# swagger-studio-ruleset

Source-of-truth Spectral ruleset for the org's SwaggerHub Studio governance, plus a publisher that pushes it to Studio.

The split mirrors the context document §5 architecture: rules authored in Git, pushed to Studio via CI. Studio is a publishing surface, not the editing surface.

## Layout

```
swagger-studio-ruleset/
├── ruleset/                # The Spectral ruleset — uploaded to Studio
│   ├── spectral.yaml       # Entry point: extends every category + standalone
│   └── rules/
│       ├── info.yaml                       # Category: info block (contact, license, ...)
│       ├── operations.yaml                 # Category: per-operation hygiene
│       ├── responses.yaml                  # Category: response standards
│       └── security-no-api-key-in-url.yaml # Standalone: high-stakes security
├── python/                 # Publisher tool (Python)
└── typescript/             # Publisher tool (TypeScript)
```

## Modularization — "hybrid"

Most rules live in **category files** grouped by what they govern (`info`, `operations`, `responses`, `schemas`, `security`). High-stakes or controversial rules that warrant per-rule visibility live as **standalone single-rule files** named `<area>-<rule-name>.yaml`.

| When to add a rule to a category file | When to make it standalone |
|---|---|
| Routine hygiene rule fitting an existing theme | Security-critical (PII, auth, secret handling) |
| Severity matches the category convention | Likely to be debated / exception-requested often |
| Owners are the platform team | Has a different owner (security team, compliance) |

The two patterns coexist freely — `spectral.yaml` just `extends` everything in `rules/`.

## Publisher

Two implementations, both behind the same CLI surface (`ruleset-publisher publish`):

- **Python** (`python/`) — uv, typer
- **TypeScript** (`typescript/`) — pnpm, commander

Each publisher supports two backends:

| Backend | How | When to use |
|---|---|---|
| `cli` (default) | Shells out to `swaggerhub spectral:upload` | Reliable, mirrors documented mechanism. Requires swaggerhub-cli installed. |
| `rest` | Direct HTTPS POST to the SwaggerHub Standardization API | Self-contained, scriptable in environments without swaggerhub-cli. Endpoint shape verified against current docs in the source. |

Both backends upload to the fixed-name slot `${OWNER}/openapi-3-0-active`, the slot Studio scans against per context doc §3.

## Quick start

```bash
# Python
cd projects/swagger-studio-ruleset/python
uv run ruleset-publisher publish               # backend defaults to `cli`
uv run ruleset-publisher publish --backend rest

# TypeScript
cd projects/swagger-studio-ruleset/typescript
pnpm dev publish
pnpm dev publish --backend rest
```

Both read `projects/swagger-studio-scanner/.env` for credentials — same `.env` the scanner uses.

## Out of scope (deferred)

The context document §7 calls out three more capabilities for the ruleset repo: ruleset-change blast-radius analysis, grace-period machinery, and Studio→ruleset bootstrap. Those land in later iterations once the publish + scan loop is proven end-to-end.
