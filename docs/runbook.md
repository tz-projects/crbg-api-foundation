# Runbook — Commands for the api-foundation workspace

A quick-reference of the commands you run day-to-day plus the full end-to-end demo loop. Two audiences:

- **In the devcontainer** (personal Mac via Docker/Colima)
- **On the work laptop** (native install — see [installation.md](installation.md) for the toolchain setup; the commands below are identical once the toolchain is in place)

For "where do I get credentials," see [installation.md §1](installation.md#1-what-you-need-regardless-of-language).

---

## 0. One-time setup per machine

```bash
# In the project root: create the shared .env (read by every sub-project)
cd projects/swagger-studio-scanner
cp .env.example .env
# Edit .env: fill in SWAGGERHUB_API_KEY (org-owner read) and SWAGGERHUB_ORG (slug)
```

If you're in the devcontainer and direnv complains about a new `.envrc`:

```bash
# One per sub-project that has an .envrc — only blocks until approved.
direnv allow /workspaces/crbg-api-foundation/projects/swagger-studio-scanner/python
direnv allow /workspaces/crbg-api-foundation/projects/swagger-studio-ruleset/python
```

direnv is a convenience — `uv run` works without it.

---

## 1. Toolchain sanity check

Run in a fresh container/terminal to confirm everything's wired:

```bash
echo "shell=$SHELL"
uv --version
node --version           # must be >= 20.17
pnpm --version           # 10.x — pinned (pnpm 11+ requires Node 22)
swaggerhub --version
gh --version | head -1
direnv --version
```

Then load `.env` into the current shell for any ad-hoc `curl`s:

```bash
set -a; source projects/swagger-studio-scanner/.env; set +a
echo "ORG=$SWAGGERHUB_ORG  KEY_LEN=${#SWAGGERHUB_API_KEY}"
```

Direct REST sanity check (proves credentials + org work before any scanner code runs):

```bash
curl -i -H "Authorization: $SWAGGERHUB_API_KEY" \
  "https://api.swaggerhub.com/apis/$SWAGGERHUB_ORG?limit=1" | head -20
# HTTP/2 200 -> good. 401/403 -> key. 404 -> org slug. TLS/timeout -> proxy/CA.
```

---

## 2. Per sub-project commands

### swagger-studio-scanner — Python

```bash
cd projects/swagger-studio-scanner/python

uv sync --all-extras                    # install deps + create .venv
uv run pytest -v                        # tests (no network)
uv run ruff check .                     # lint
uv run mypy src                         # types

uv run scanner version                  # confirm CLI is wired
uv run scanner probe                    # capability probe
uv run scanner scan                     # full scan -> output/{scan.json,findings.csv,scan.html}
uv run scanner scan -o /tmp/myreport    # write reports elsewhere
uv run scanner scan -n 25               # scan only first 25 APIs (dev / targeted runs)
uv run scanner scan -n 25 -o /tmp/dev   # subset + custom output dir
```

The `--limit/-n` flag stops enumeration after N API versions and skips extra page fetches — useful on a 600+ API org when you're iterating on a fix. Order follows Studio's listing endpoint (not guaranteed stable across calls).

### swagger-studio-scanner — TypeScript

```bash
cd projects/swagger-studio-scanner/typescript

pnpm install
pnpm test                               # vitest
pnpm lint                               # eslint
pnpm typecheck                          # tsc --noEmit
pnpm build                              # emit dist/

pnpm dev version                        # confirm CLI is wired
pnpm dev probe                          # capability probe
# pnpm dev scan                         # NOT YET BUILT — Python is full-feature today
```

### swagger-studio-ruleset — Python publisher

```bash
cd projects/swagger-studio-ruleset/python

uv sync --all-extras
uv run pytest -v

uv run ruleset-publisher version
uv run ruleset-publisher publish                    # CLI backend (default)
uv run ruleset-publisher publish --backend rest     # REST backend
uv run ruleset-publisher publish --ruleset /path/to/other/ruleset
```

### swagger-studio-ruleset — TypeScript publisher

```bash
cd projects/swagger-studio-ruleset/typescript

pnpm install
pnpm test
pnpm lint
pnpm typecheck

pnpm dev version
pnpm dev publish                                    # CLI backend (default)
pnpm dev publish --backend rest                     # REST backend
pnpm dev publish --ruleset /path/to/other/ruleset
```

### Consolidated Ruleset publisher variants
```bash
# Python
cd /workspaces/crbg-api-foundation/projects/swagger-studio-ruleset/python
# CLI backend (default)
uv run ruleset-publisher publish
# REST backend
uv run ruleset-publisher publish --backend rest

# TypeScript
cd /workspaces/crbg-api-foundation/projects/swagger-studio-ruleset/typescript
# CLI backend (default)
pnpm dev publish
# REST backend
pnpm dev publish --backend rest
```

---

## 3. End-to-end demo loop

Drives a full publish → seed → scan → report cycle against the trial org. Run from the repo root.

```bash
# (Step 0) Confirm credentials work
cd projects/swagger-studio-scanner/python && uv run scanner probe && cd -

# (Step 1) Publish the ruleset to {OWNER}/openapi-3-0-active
#   Either language works. Pick one.
cd projects/swagger-studio-ruleset/python && uv run ruleset-publisher publish && cd -
# or
cd projects/swagger-studio-ruleset/typescript && pnpm dev publish && cd -

# (Step 2) Push the sample APIs (one good, one bad)
bash projects/swagger-studio-scanner/samples/push_samples.sh

# (Step 3) Let SwaggerHub evaluate standardization on the new specs
sleep 25

# (Step 4) Scan
cd projects/swagger-studio-scanner/python && uv run scanner scan && cd -

# (Step 5) Inspect the HTML scan report (scanner's built-in)
ls -la projects/swagger-studio-scanner/python/output/
# Drag-and-drop scan.html into a browser, or open via VS Code's Simple Browser.

# (Step 6) Generate the executive + platform reports
cd projects/reports
SCAN=/workspaces/crbg-api-foundation/projects/swagger-studio-scanner/python/output/scan.json
python3 generate_executive_report.py \
  --input "$SCAN" --output output/executive-report.html \
  --org-display-name "Acme Corporation" --placeholder-ask
python3 generate_platform_report.py \
  --input "$SCAN" --output-dir output/platform-report \
  --org-display-name "Acme Corporation" \
  --studio-base-url https://app.swaggerhub.com/apis
cd -
# See docs/reports.md for ownership map, CoP guidance, asks file flags.
```

### Expected outcome

| Step | What to see |
|---|---|
| Probe | `ok: Auth + org reachable; verify standardization next.` |
| Publish | `Published <org>/openapi-3-0-active`, with a Studio URL |
| Push samples | Two `-> created` (or `-> updated`) lines |
| Scan summary | `APIs scanned: 2`, `Pass: 1`, `Fail: 1`, `Total findings: ~10+` |
| HTML Rule Pareto | `operation-operationId`, `response-success-content`, `operation-description` at the top (each fires 3× per bad-petstore's three operations) |

---

## 4. Resetting between runs

To clean the trial org so the next demo run starts from scratch:

```bash
set -a; source projects/swagger-studio-scanner/.env; set +a

# Delete the sample specs (idempotent — ignores 404)
swaggerhub api:delete "$SWAGGERHUB_ORG/scanner-good-petstore" || true
swaggerhub api:delete "$SWAGGERHUB_ORG/scanner-bad-petstore"  || true

# Remove local scan artifacts
rm -rf projects/swagger-studio-scanner/python/output
```

The ruleset stays in place — typically you don't want to delete the active ruleset between scans. To replace it, just re-run `ruleset-publisher publish`.

---

## 5. Quick troubleshooting

| Symptom | First thing to check | Fix |
|---|---|---|
| `pnpm install` errors with `node:sqlite` | pnpm 11 pulled in; needs Node 22 | `corepack prepare pnpm@10 --activate` |
| `direnv: command not found` while `/usr/bin/direnv` exists | Stale zsh hash cache | `hash -r && direnv --version` |
| Scanner probe returns `auth_failed` | API key wrong / not org-owner scope | Re-issue key at app.swaggerhub.com/settings/apiKey |
| Scanner probe returns `org_unreachable` | Wrong slug | Check URL: `app.swaggerhub.com/organization/<slug>` |
| Scanner probe returns `network_error` | Corporate proxy / TLS inspection | See [installation.md §5](installation.md#5-corporate-laptop-gotchas) |
| Scan reports `0` findings on `bad-petstore` | Ruleset isn't active in Studio | Re-run `ruleset-publisher publish` |
| Scan reports `errored: N` | Per-API HTTP errors during fetch | Check `output/scan.json` — each error row carries the HTTP status |
| Container won't start at all | Docker daemon issue (Colima) | `colima status; colima delete -f; colima start` (personal Mac only) |

---

## 6. Common operational commands

```bash
# Reload .env into the current shell (after editing)
set -a; source projects/swagger-studio-scanner/.env; set +a

# Inspect the ruleset Studio is currently enforcing (download what's live)
swaggerhub api:validate:download-rules "$SWAGGERHUB_ORG" -s -d /tmp/active-rules

# Validate a single local spec against Studio's live ruleset (no upload)
swaggerhub api:validate:local -o "$SWAGGERHUB_ORG" \
  -f projects/swagger-studio-scanner/samples/bad-petstore.yaml -c -j

# List all APIs in the org (raw REST)
curl -s -H "Authorization: $SWAGGERHUB_API_KEY" \
  "https://api.swaggerhub.com/apis/$SWAGGERHUB_ORG?limit=100" | jq '.totalCount, (.apis // .items | length)'
```

---

## See also

- [installation.md](installation.md) — toolchain setup for native (work laptop) installs
- [reports.md](reports.md) — executive + platform team report generators (Tier 2/3 input formats, full-run example)
- [../smartbear-governance-enforcement-context.md](../smartbear-governance-enforcement-context.md) — design context, phases, decisions
- [../README.md](../README.md) — workspace layout overview
