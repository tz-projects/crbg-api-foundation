# Implementation Context — Session Handoff

A snapshot of the api-foundation workspace state and the load-bearing knowledge gained while building it, so a fresh session (or someone else on the team) can pick up cold.

Paired with [`smartbear-governance-enforcement-context.md`](../smartbear-governance-enforcement-context.md) — that's the *design* context (phases, decisions, why); this is the *implementation* context (what exists, what's known, what's next).

Last updated: 2026-05-29.

---

## 1. TL;DR — what works end-to-end today

Against a real SparkLayer trial org (Enterprise tier, governance enabled):

1. **Ruleset publish** (Python or TypeScript, CLI or REST backend) — uploads a flattened single-file Spectral ruleset to Studio AND activates it via the `/standardization/{owner}/config` flip.
2. **Sample push** — `bash projects/swagger-studio-scanner/samples/push_samples.sh` seeds one clean and one deliberately broken API.
3. **Scan** (Python end-to-end; TypeScript has only probe+version) — enumerates all APIs, fetches `/standardization` findings per version, writes JSON + CSV + HTML reports with a rule Pareto.
4. **Lifecycle** (ruleset publisher only) — `publish`, `deactivate`, `delete`, `list`, `pull` commands cover the full slot lifecycle.

Last verified scan against the trial org: **2 APIs, 1 pass, 1 fail, 17 findings (8 critical / 9 warning)** on the bad-petstore sample.

---

## 2. Workspace layout

```
crbg-api-foundation/
├── .devcontainer/                          # Dockerfile-based (not features) — Python 3.12, Node 20, uv, pnpm@10, swaggerhub-cli, gh, direnv, oh-my-zsh + p10k, dotfiles
├── .vscode/                                # Shared editor settings + recommended extensions
├── docs/
│   ├── installation.md                     # Work-laptop native install (no Docker)
│   ├── runbook.md                          # Day-to-day commands + demo loop + troubleshooting
│   └── implementation-context.md           # ← this file
├── projects/
│   ├── swagger-studio-scanner/
│   │   ├── python/                         # uv-managed, full scan + reports
│   │   ├── typescript/                     # pnpm-managed, probe + version only (parity gap)
│   │   └── samples/                        # good-petstore.yaml, bad-petstore.yaml, push_samples.sh
│   └── swagger-studio-ruleset/
│       ├── ruleset/                        # spectral.yaml + rules/{info,operations,responses}.yaml + standalone files
│       ├── python/                         # uv-managed, full lifecycle CLI
│       └── typescript/                     # pnpm-managed, full lifecycle CLI
├── pnpm-workspace.yaml                     # Picks up projects/*/typescript
└── smartbear-governance-enforcement-context.md   # Design context
```

---

## 3. SwaggerHub REST API findings — load-bearing

Discovered the hard way (network capture + reading swaggerhub-cli source). Capture them so they don't have to be re-discovered:

### 3.1 List APIs in an org

`GET https://api.swaggerhub.com/apis/{owner}?page={n}&limit=100`

Response shape — **canonical slug lives in the `Swagger` property URL**, NOT in the top-level `name` field (which is the OpenAPI `info.title`):

```json
{
  "apis": [
    {
      "name": "Scanner Good Petstore",                              ← info.title — DO NOT USE as slug
      "properties": [
        { "type": "Swagger",
          "url": "https://api.swaggerhub.com/apis/sparklayerinc/scanner-good-petstore/1.0.0" },  ← parse THIS
        { "type": "X-Version", "value": "1.0.0" },                  ← real version
        { "type": "X-Versions", "value": "-1.0.0" }                 ← a marker, NOT a version list
      ]
    }
  ]
}
```

The scanner's parser at [client.py:_extract_api_ref](../projects/swagger-studio-scanner/python/src/swagger_studio_scanner/client.py) parses the Swagger URL for `(owner, name, version)`.

### 3.2 Get findings for one API version

`GET https://api.swaggerhub.com/apis/{owner}/{name}/{version}/standardization`

**Response key is `validation`** — not `findings`, not `standardization`:

```json
{ "validation": [ {"severity": "Critical", "message": "...", "rule": "..."}, ... ] }
```

### 3.3 Upload Spectral ruleset

`PUT https://api.swaggerhub.com/standardization/spectral-rulesets/{owner}/{name}/zip`

- Content-Type: `application/zip`
- Body: raw zip bytes (no multipart)
- Returns: the new ruleset's UUID in the response body

Endpoint discovered in [swaggerhub-cli `src/requests/spectral.js#saveSpectralRuleset`](https://github.com/SmartBear/swaggerhub-cli/blob/master/src/requests/spectral.js).

### 3.4 List Spectral rulesets in an org

`GET https://api.swaggerhub.com/standardization/spectral-rulesets/{owner}`

Returns an **array** of `{ id: UUID, name: string, rulesetId: null, title: null }`. The `id` field is the UUID; `rulesetId` is always null in this view (field-naming asymmetry — see 3.5).

### 3.5 Org governance config (the activation flip)

`GET / POST https://api.swaggerhub.com/standardization/{owner}/config`

GET returns:

```json
{
  "enabled": true,
  "canPublishWithErrors": true,
  "spectralRulesets": [
    { "rulesetId": "8fc6a0a0-...uuid...", "enabled": true }      ← here it's `rulesetId`, NOT `id`
  ],
  "systemRules": [ ... ],
  "customRules": [],
  "styleguides": []
}
```

Activation is **read-modify-write** against this endpoint:
1. GET config
2. Find `spectralRulesets[].rulesetId == target_uuid` → set `enabled: true` (or append if missing)
3. POST the entire modified body back

### 3.6 Field-naming asymmetry summary

| Endpoint | Field name for the UUID |
|---|---|
| `GET /standardization/spectral-rulesets/{owner}` (listing) | `id` |
| `GET /standardization/{owner}/config` (`spectralRulesets[]`) | `rulesetId` |
| `PUT /standardization/spectral-rulesets/{owner}/{name}/zip` (upload response) | `id` |

The publisher reads from `id` in the listing/upload-response and writes to `rulesetId` in the config. Don't conflate.

---

## 4. Architectural decisions made this session

### 4.1 Devcontainer: Dockerfile, not features

Switched mid-session from features+postCreate to a single Dockerfile. Reasoning: dotfiles + custom installs (uv via curl, p10k from git, swaggerhub-cli global npm) accumulated past what features express cleanly. The Dockerfile is one readable artifact instead of a JSON+shell-script combo.

`post-create.sh` is now minimal — only handles workspace-mounted setup (`uv sync`, `pnpm install`, `direnv allow`) that can't happen at image build time.

### 4.2 Modularization: hybrid (categories + standalones)

Ruleset rules grouped by category (`info.yaml`, `operations.yaml`, `responses.yaml`) with high-stakes ones in their own file (`security-no-api-key-in-url.yaml`). One-per-file was rejected as overkill at this ruleset size.

### 4.3 Bundling: flatten on upload, keep modular on disk

Ruleset publisher resolves all relative `extends: ./rules/*.yaml` references inline and uploads a **single-file ZIP** containing only the merged `spectral.yaml`. Built-in extends (`spectral:oas`) are kept and resolved by Spectral at scan time. Same pattern as a JS bundler: modular source, bundled artifact.

### 4.4 Two backends behind one publisher protocol

Each publisher (Python and TypeScript) supports both `--backend cli` (shells out to `swaggerhub spectral:upload`) and `--backend rest` (direct PUT). The Publisher protocol/interface keeps the CLI orchestration backend-agnostic. CLI is the default; REST is fully working as of this session.

### 4.5 Activator is its own module

Activation is always REST regardless of upload backend, and it's a distinct concern. Activator lives in `activator.py`/`activator.ts` rather than coupling to either publisher backend. Caller passes the UUID returned from upload to skip the lookup round-trip (and ride out the indexing lag).

### 4.6 Full lifecycle in the publisher CLI

Beyond `publish`, the ruleset publisher now has `deactivate`, `delete`, `list`, `pull`. All share the same shared HTTP helpers in `_http.py`/`_http.ts`. Multiple slots can coexist (e.g. `openapi-3-0-active`, `owasp-top-10-active`) — `--name` selects the slot.

### 4.7 No Claude/Anthropic branding in commits

Per repo convention — drop `Co-Authored-By: Claude` and "Generated with Claude Code" footers.

---

## 5. Per sub-project state

### swagger-studio-scanner

| Component | Python | TypeScript |
|---|---|---|
| `version` command | ✓ | ✓ |
| `probe` command (capability check) | ✓ | ✓ |
| `scan` command (full org enumeration + reports) | ✓ | **gap — not built** |
| Defensive parsers (Swagger URL → ApiRef; `validation` key) | ✓ | partial |
| Report writers (JSON / CSV / HTML with Pareto) | ✓ | not built |

**TypeScript scanner parity is the biggest gap.** Python is the recommended runtime (lighter install per context doc §8); TS exists for future feature parity but isn't on the demo critical path today.

### swagger-studio-ruleset

| Command | Python | TypeScript |
|---|---|---|
| `version` | ✓ | ✓ |
| `publish` (upload + activate, CLI or REST backend) | ✓ | ✓ |
| `deactivate` (flip enabled=false, keep content) | ✓ | ✓ |
| `delete` (remove slot entirely) | ✓ | ✓ |
| `list` (every ruleset + enabled state) | ✓ | ✓ |
| `pull` (download slot content to disk) | ✓ | ✓ |

Full feature parity. The `_http` module abstracts client construction so every command shares auth/timeout/headers.

---

## 6. Known issues / open items

- **TypeScript scanner parity** — bring `list_apis` / `get_findings` / `scan_org` / report writers to parity with Python. ~30 min of focused work; mirrors the existing Python implementations.
- **HTTP integration tests** — neither publisher has integration tests for the activator's GET→POST flow against a real or mocked SwaggerHub. Currently relying on the live verified demo. `pytest-recording` / `nock` were deferred earlier; consider adding.
- **Phase 1 per-API pipeline** — context doc §5 calls for a per-API CI pipeline that validates spec → blocks publish. Not started.
- **Impact analysis** (context §7) — dual-ruleset blast-radius script. Not started.
- **Grace-period machinery** (context §7) — runtime downgrade of error→warn for rules in active grace window. Not started.
- **Ownership map generator** (context §7) — consolidates per-repo `governance.config.yaml` into an org-wide map. Not started.
- **Work laptop verification** — the full demo loop has been verified on personal Mac (devcontainer); still needs verification on a corporate-network work laptop following `docs/installation.md`.

---

## 7. Running the demo from a fresh session

```bash
# 1. Open the repo in VS Code → "Reopen in Container" (or native install per docs/installation.md)

# 2. Make sure .env exists
cp projects/swagger-studio-scanner/.env.example projects/swagger-studio-scanner/.env
# Edit: SWAGGERHUB_API_KEY (org-owner read), SWAGGERHUB_ORG (slug)

# 3. Full demo — see docs/runbook.md §3 for the canonical sequence
cd projects/swagger-studio-ruleset/python
uv run ruleset-publisher publish              # upload + activate

cd /workspaces/crbg-api-foundation
bash projects/swagger-studio-scanner/samples/push_samples.sh
sleep 25

cd projects/swagger-studio-scanner/python
rm -rf output
uv run scanner scan                            # → output/scan.{json,csv,html}
```

---

## 8. References

- [runbook.md](runbook.md) — day-to-day command reference, troubleshooting matrix
- [installation.md](installation.md) — work-laptop native install (no Docker)
- [smartbear-governance-enforcement-context.md](../smartbear-governance-enforcement-context.md) — design context, decisions, phases
- [swaggerhub-cli source](https://github.com/SmartBear/swaggerhub-cli) — primary reference for "what does swaggerhub-cli actually call" questions
- Per-sub-project READMEs under `projects/*/`

---

*End of implementation context. Carry forward by handing this + the design context to the next session.*
