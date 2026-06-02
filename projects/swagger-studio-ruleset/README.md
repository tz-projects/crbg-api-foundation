# swagger-studio-ruleset

Source-of-truth Spectral ruleset for the org's SwaggerHub Studio governance, plus a publisher that pushes it to Studio.

The split mirrors the context document §5 architecture: rules authored in Git, pushed to Studio via CI. Studio is a publishing surface, not the editing surface.

## Layout

```
swagger-studio-ruleset/
├── ruleset/                # OAS 3.0 hygiene guide — slot: openapi-3-0-active
│   ├── spectral.yaml       # Entry point: extends every category + standalone
│   └── rules/
│       ├── info.yaml                       # Category: info block (contact, license, ...)
│       ├── operations.yaml                 # Category: per-operation hygiene
│       ├── responses.yaml                  # Category: response standards
│       └── security-no-api-key-in-url.yaml # Standalone: high-stakes security
├── ruleset-owasp/          # OWASP Top 10 guide — slot: owasp-top-10-active
│   ├── spectral.yaml
│   └── rules/
│       └── owasp-api2-operation-security-defined.yaml  # API2:2023 Broken Authentication
├── python/                 # Publisher tool (Python)
└── typescript/             # Publisher tool (TypeScript)
```

## Multiple active style guides

Studio's `/standardization/{owner}/config` stores `spectralRulesets[]` as an array
where each entry has its own `enabled` flag. Activating one ruleset leaves any
others untouched, so multiple guides can be active simultaneously — Studio's
engine merges findings from every enabled entry. This repo publishes two guides:

| Slot | Source | Scope |
|---|---|---|
| `openapi-3-0-active` | `ruleset/` | General OAS 3.0 hygiene (info, operations, responses, key-in-URL) |
| `owasp-top-10-active` | `ruleset-owasp/` | OWASP API Security Top 10 (currently API2:2023 only) |

## Modularization — "hybrid"

Most rules live in **category files** grouped by what they govern (`info`, `operations`, `responses`, `schemas`, `security`). High-stakes or controversial rules that warrant per-rule visibility live as **standalone single-rule files** named `<area>-<rule-name>.yaml`.

| When to add a rule to a category file | When to make it standalone |
|---|---|
| Routine hygiene rule fitting an existing theme | Security-critical (PII, auth, secret handling) |
| Severity matches the category convention | Likely to be debated / exception-requested often |
| Owners are the platform team | Has a different owner (security team, compliance) |

The two patterns coexist freely — `spectral.yaml` just `extends` everything in `rules/`.

## Publisher

Two implementations, both behind the same CLI surface:

- **Python** (`python/`) — uv, typer
- **TypeScript** (`typescript/`) — pnpm, commander

### Commands

| Command | What it does | Endpoints |
|---|---|---|
| `publish` | Upload + activate a guide. Creates a slot if missing, updates if present. | `PUT .../zip` then activator flow |
| `deactivate` | Set `enabled=false` for a slot in the org config. Content stays in Studio. | `GET`/`POST .../config` |
| `delete` | Remove the slot entirely: clean its config entry then DELETE the ruleset. Idempotent (404 → "already absent"). | `DELETE .../{name}` |
| `list` | Show every ruleset in the org with its enabled state, merged from `/spectral-rulesets/{owner}` + `/config`. | Two GETs |
| `pull` | Download a slot's current zip into a directory. Used for drift detection / bootstrapping. | `GET .../zip` |

`publish` and `deactivate` accept `--name` to target the slot; `--ruleset` (publish only) points at the source dir.

### Backends (publish only)

| Backend | How | When to use |
|---|---|---|
| `cli` (default) | Shells out to `swaggerhub spectral:upload` | Reliable, mirrors documented mechanism. Requires swaggerhub-cli installed. |
| `rest` | Direct HTTPS POST to the SwaggerHub Standardization API | Self-contained, scriptable in environments without swaggerhub-cli. Endpoint shape verified against current docs in the source. |

Both backends upload to `${OWNER}/${--name}`. `--name` defaults to `openapi-3-0-active` (the OAS hygiene slot per context doc §3); pass `--name owasp-top-10-active` with `--ruleset ../ruleset-owasp` to publish the second guide.

## Quick start

```bash
# Python — full lifecycle
cd projects/swagger-studio-ruleset/python
uv run ruleset-publisher publish                                              # OAS (default)
uv run ruleset-publisher publish --ruleset ../ruleset-owasp --name owasp-top-10-active
uv run ruleset-publisher list                                                 # show enabled state
uv run ruleset-publisher pull --name owasp-top-10-active --dest /tmp/check   # download for diff
uv run ruleset-publisher deactivate --name owasp-top-10-active               # turn off, keep content
uv run ruleset-publisher delete --name owasp-top-10-active --yes             # remove entirely

# TypeScript — same surface, same flags
cd projects/swagger-studio-ruleset/typescript
pnpm dev publish
pnpm dev publish --ruleset ../ruleset-owasp --name owasp-top-10-active
pnpm dev list
pnpm dev pull --name owasp-top-10-active --dest /tmp/check
pnpm dev deactivate --name owasp-top-10-active
pnpm dev delete --name owasp-top-10-active --yes
```

After both publishes, the two guides are both `enabled=true` in the org's
standardization config. The next spec scan will report findings from both —
e.g. `bad-petstore.yaml` fails OAS hygiene rules AND the OWASP API2 rule.

Both read `projects/swagger-studio-scanner/.env` for credentials — same `.env` the scanner uses.

## Out of scope (deferred)

The context document §7 calls out three more capabilities for the ruleset repo: ruleset-change blast-radius analysis, grace-period machinery, and Studio→ruleset bootstrap. Those land in later iterations once the publish + scan loop is proven end-to-end.
