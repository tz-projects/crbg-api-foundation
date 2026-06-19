# Run commands — every variant of every program

A single reference of **how to run each program with each parameter**, written for the plain-Python flow on the `pure-python` branch (no `uv`, no Docker). Once you've set the environment up per [installation.md](installation.md), this doc tells you what to actually type.

Three programs ship in this repo:

| Program | Path | What it does | Backends |
|---|---|---|---|
| **scanner** | `projects/swagger-studio-scanner/python/` | Org-wide non-conformance scan against SwaggerHub | REST only |
| **publisher** | `projects/swagger-studio-ruleset/python/` | Publish + manage standardization rulesets in Studio | `cli` (Node) or `rest` |
| **reports** | `projects/reports/` | Render `scan.json` into executive + platform-team HTML | n/a — local file only |

Quick links to the per-command sections:

- [Scanner — `version` / `probe` / `scan`](#1-scanner)
- [Publisher — `version` / `publish` / `deactivate` / `delete` / `list` / `pull`](#2-publisher)
- [Reports — `executive` / `platform`](#3-reports)
- [End-to-end demo loop](#4-end-to-end-demo-loop)

For the toolchain install (Python 3.12+, venv, pip), see [installation.md](installation.md). For the design context, see [implementation-context.md](implementation-context.md).

---

## 0. One-time setup recap

Each program lives in its own folder with its own virtual environment. The `.env` is **shared** across scanner and publisher and lives at `projects/swagger-studio-scanner/.env`.

> **Shell note:** Every command in this doc is shown in two variants where they differ — **bash** (macOS / Linux / WSL / Git Bash on Windows) and **Windows PowerShell**. The Python invocations themselves (`scanner probe`, `python generate_report.py ...`) are identical across both — only activation, env-var syntax, path separators, and loop syntax change. Pick whichever block matches your terminal.

**bash (macOS / Linux):**

```bash
# Credentials (once per machine)
cp projects/swagger-studio-scanner/.env.example projects/swagger-studio-scanner/.env
# Edit .env -> set SWAGGERHUB_API_KEY (org-owner read) and SWAGGERHUB_ORG (slug)

# Scanner venv
cd projects/swagger-studio-scanner/python
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e . --no-deps
deactivate
cd -

# Publisher venv (separate from the scanner's)
cd projects/swagger-studio-ruleset/python
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e . --no-deps
deactivate
cd -

# Reports — no venv needed (stdlib only). Optionally:
pip install --user pyyaml                # only for nested YAML ownership maps
```

**Windows PowerShell:**

```powershell
# Credentials (once per machine)
Copy-Item projects\swagger-studio-scanner\.env.example projects\swagger-studio-scanner\.env
# Edit .env -> set SWAGGERHUB_API_KEY (org-owner read) and SWAGGERHUB_ORG (slug)

# Scanner venv
Push-Location projects\swagger-studio-scanner\python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e . --no-deps
deactivate
Pop-Location

# Publisher venv (separate from the scanner's)
Push-Location projects\swagger-studio-ruleset\python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e . --no-deps
deactivate
Pop-Location

# Reports — no venv needed (stdlib only). Optionally:
pip install --user pyyaml                # only for nested YAML ownership maps
```

> **PowerShell execution-policy note:** if `.\.venv\Scripts\Activate.ps1` fails with *"cannot be loaded because running scripts is disabled on this system,"* run this once per user:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```
> Doesn't need admin; allows local scripts (like `Activate.ps1`) to run while still blocking unsigned remote scripts.

The shared `.env` accepts these keys (defaults in parentheses are fine to omit):

| Variable | Used by | Purpose |
|---|---|---|
| `SWAGGERHUB_API_KEY` | both | Org-owner read key for scanner; write key for publisher |
| `SWAGGERHUB_ORG` | both | Org slug (the part after `app.swaggerhub.com/organization/`) |
| `SWAGGERHUB_BASE_URL` (`https://api.swaggerhub.com`) | both | Only set for on-prem Studio |
| `SCANNER_CONCURRENCY` (`8`) | scanner | Parallel requests during scan; lower to 4 if you hit 429s |
| `SCANNER_REQUEST_TIMEOUT_S` (`30`) | scanner | Per-request timeout in seconds |
| `SCANNER_LOG_LEVEL` (`INFO`) | scanner | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `PUBLISHER_REQUEST_TIMEOUT_S` (`30`) | publisher | Per-request timeout |
| `PUBLISHER_LOG_LEVEL` (`INFO`) | publisher | Log verbosity |

**All commands below assume the relevant venv is activated.** Activation is `source .venv/bin/activate` on bash, `.\.venv\Scripts\Activate.ps1` on PowerShell. If you'd rather not activate, swap `scanner ...` for `.venv/bin/scanner ...` (bash) or `.venv\Scripts\scanner.exe ...` (PowerShell), and likewise for `ruleset-publisher`.

### Verify the install (read-only — safe to run anytime)

Once both venvs are set up and `.env` has your credentials, run these three quick checks. They prove the venv-installed CLIs can reach SwaggerHub end-to-end. All three are **read-only** — no writes, no scans of all 600 APIs, no risk to your org.

**bash:**

```bash
# 1. Scanner can talk to your org (auth + reachability)
cd projects/swagger-studio-scanner/python
source .venv/bin/activate
scanner probe
# Expect: ok: Auth + org reachable; verify standardization next.
deactivate
cd -

# 2. Publisher can talk to your org (lists rulesets — no changes)
cd projects/swagger-studio-ruleset/python
source .venv/bin/activate
ruleset-publisher list
# Expect: a table of rulesets in your org with their enabled state
deactivate
cd -

# 3. Reports can read a scan.json (only meaningful if you've already run scanner scan)
cd projects/reports
python generate_executive_report.py --help
python generate_platform_report.py --help
# Expect: usage info printed for both — confirms stdlib-only run works
cd -
```

**Windows PowerShell:**

```powershell
# 1. Scanner can talk to your org (auth + reachability)
Push-Location projects\swagger-studio-scanner\python
.\.venv\Scripts\Activate.ps1
scanner probe
# Expect: ok: Auth + org reachable; verify standardization next.
deactivate
Pop-Location

# 2. Publisher can talk to your org (lists rulesets — no changes)
Push-Location projects\swagger-studio-ruleset\python
.\.venv\Scripts\Activate.ps1
ruleset-publisher list
# Expect: a table of rulesets in your org with their enabled state
deactivate
Pop-Location

# 3. Reports can read a scan.json (only meaningful if you've already run scanner scan)
Push-Location projects\reports
python generate_executive_report.py --help
python generate_platform_report.py --help
# Expect: usage info printed for both — confirms stdlib-only run works
Pop-Location
```

If all three succeed, the work-laptop install is fully verified. If `scanner probe` returns `auth_failed` / `org_unreachable` / `network_error`, see [installation.md §5 corporate-laptop gotchas](installation.md#5-corporate-laptop-gotchas).

> **Corporate-laptop SSL gotcha:** On a work laptop behind corporate TLS inspection, `scanner probe` will return `network_error: ... SSL: CERTIFICATE_VERIFY_FAILED` on the first run. The fix is to point Python at your corporate CA bundle via `SSL_CERT_FILE` + `REQUESTS_CA_BUNDLE` user env vars — see [installation.md §5.2](installation.md#52-ssl-inspection--corporate-ca) for the full export-and-set procedure.

---

## 1. Scanner

**bash:**
```bash
cd projects/swagger-studio-scanner/python
source .venv/bin/activate
```

**Windows PowerShell:**
```powershell
cd projects\swagger-studio-scanner\python
.\.venv\Scripts\Activate.ps1
```

The scanner has **three commands**. It only has a REST backend — there is no `--backend` flag.

### 1.1 `scanner version`

Sanity check that the CLI is wired correctly.

```bash
scanner version
# -> swagger-studio-scanner v0.1.0
```

No flags.

### 1.2 `scanner probe`

Step-zero capability probe. Verifies auth, org reachability, and (eventually) that the Governance tier is active. Run this first — it fails in <1s if something is misconfigured, saving a 600-API scan against a broken environment.

```bash
scanner probe
```

Exit codes: `0` on success, `1` on any probe failure. The status code in the output tells you which leg broke:

| Status | Meaning | First thing to check |
|---|---|---|
| `ok` | All checks passed | — |
| `auth_failed` | 401/403 from Studio | API key is wrong, expired, or not org-owner scope |
| `org_unreachable` | 404 listing org APIs | `SWAGGERHUB_ORG` slug is wrong |
| `network_error` | TLS, DNS, or timeout | See [installation.md §5](installation.md#5-corporate-laptop-gotchas) |

No flags.

### 1.3 `scanner scan`

Full org scan. Writes three reports to `output/`: `scan.json` (the contract for the reports project), `findings.csv`, and `scan.html` (the scanner's built-in HTML).

```bash
scanner scan
```

| Flag | Default | Purpose |
|---|---|---|
| `--output, -o PATH` | `output` | Directory for the three reports. Created if missing. |
| `--limit, -n N` | (none) | Stop after `N` API versions. Order follows Studio's listing endpoint (not stable across calls). Useful for dev iteration against a 600+ API org. |

Examples:

```bash
# Full scan (typical use)
scanner scan

# Write reports somewhere else (e.g. to share)
scanner scan -o /tmp/scan-2026-06-18

# Dev loop — just enough APIs to see the rule Pareto stabilize
scanner scan -n 25

# Combined: subset scan with custom output directory
scanner scan -n 25 -o /tmp/dev-scan

# Performance ramp-up — measure how the scan scales as N grows (bash)
for N in 10 25 50 100 200; do
    time scanner scan -n $N -o /tmp/scan-$N
done
```

**Windows PowerShell equivalent of the ramp-up loop:**

```powershell
foreach ($N in 10, 25, 50, 100, 200) {
    Write-Host "=== Scanning first $N APIs ==="
    Measure-Command { scanner scan -n $N -o "$env:TEMP\scan-$N" } |
        Select-Object TotalSeconds
}
```

Exit codes: `0` on success, `2` when the org has no APIs (probably a slug typo), `1` on transport/parse error.

### 1.4 Scanner tuning knobs (env vars)

The scanner exposes three knobs as environment variables. **You don't need to touch them for normal use** — defaults are fine. Reach for them only when you see specific symptoms during a large scan.

| Variable | Default | Allowed range | What it controls |
|---|---|---|---|
| `SCANNER_CONCURRENCY` | `8` | 1–64 | How many APIs the scanner queries SwaggerHub about **in parallel**. Higher = faster scan but more aggressive on Studio. Implemented as an `asyncio.Semaphore` in [client.py:70](../projects/swagger-studio-scanner/python/src/swagger_studio_scanner/client.py#L70). |
| `SCANNER_REQUEST_TIMEOUT_S` | `30` | any value > 0 | Seconds the scanner waits for a single HTTP response from Studio before giving up on that one API. Big specs may need more. Passed straight to `httpx` in [client.py:73](../projects/swagger-studio-scanner/python/src/swagger_studio_scanner/client.py#L73). |
| `SCANNER_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | How chatty the scanner is. `DEBUG` shows every request and its timing; `WARNING` hides routine progress. Applied in [cli.py:45,74](../projects/swagger-studio-scanner/python/src/swagger_studio_scanner/cli.py#L45). |

**When to change each:**

| You see this | Try this |
|---|---|
| `errored: N` rows in `scan.json` with HTTP `429` (rate-limited) | Lower concurrency: `SCANNER_CONCURRENCY=4` |
| Errors saying `timeout` or `network` on a few specific APIs | Raise timeout: `SCANNER_REQUEST_TIMEOUT_S=60` |
| Scan feels stuck or behaves oddly and you want a per-API trace | Crank logging: `SCANNER_LOG_LEVEL=DEBUG` |
| Routine scans flooding the terminal | Quiet it: `SCANNER_LOG_LEVEL=WARNING` |

**Two ways to set them:**

1. **Inline, for a single run.** Only affects that one invocation. Syntax differs between shells:

   **bash** — prefix the env var directly on the command:
   ```bash
   SCANNER_CONCURRENCY=4 scanner scan -n 200
   SCANNER_REQUEST_TIMEOUT_S=60 scanner scan -n 200
   SCANNER_LOG_LEVEL=DEBUG scanner scan -n 50

   # Combine multiple in one command
   SCANNER_CONCURRENCY=4 SCANNER_REQUEST_TIMEOUT_S=60 scanner scan
   ```

   **Windows PowerShell** — set `$env:` vars on a line before the command (PowerShell doesn't support bash-style inline prefixes). They stay set for the rest of the terminal session unless you clear them:
   ```powershell
   $env:SCANNER_CONCURRENCY = 4
   scanner scan -n 200

   $env:SCANNER_REQUEST_TIMEOUT_S = 60
   scanner scan -n 200

   $env:SCANNER_LOG_LEVEL = "DEBUG"
   scanner scan -n 50

   # Combine multiple
   $env:SCANNER_CONCURRENCY = 4
   $env:SCANNER_REQUEST_TIMEOUT_S = 60
   scanner scan

   # Clear a one-off when done
   Remove-Item Env:\SCANNER_CONCURRENCY
   ```

2. **Persistently, for every run** — edit `projects/swagger-studio-scanner/.env` (same file that holds your API key). Uncomment / set the line and it applies to every future `scanner` invocation until you change it again. Same `.env` format on every OS:

   ```
   # In projects/swagger-studio-scanner/.env
   SWAGGERHUB_API_KEY=...
   SWAGGERHUB_ORG=...
   SCANNER_CONCURRENCY=4
   SCANNER_REQUEST_TIMEOUT_S=60
   SCANNER_LOG_LEVEL=INFO
   ```

   The inline form **wins over** the `.env` value when both are set, so a one-off override is always possible without editing the file.

> **Note about non-scanner env vars (like `SSL_CERT_FILE`):** the `.env` file is only honored for variables declared in the scanner's `Settings` class. Generic Python env vars (`SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `HTTPS_PROXY`) must be set at the **shell or OS level** — they won't take effect from `.env`. See [installation.md §5](installation.md#5-corporate-laptop-gotchas).

---

## 2. Publisher

**bash:**
```bash
cd projects/swagger-studio-ruleset/python
source .venv/bin/activate
```

**Windows PowerShell:**
```powershell
cd projects\swagger-studio-ruleset\python
.\.venv\Scripts\Activate.ps1
```

The publisher has **six commands**. The `publish` command supports two **backends** — pick one with `--backend`:

| Backend | How it talks to SwaggerHub | When to use |
|---|---|---|
| `cli` (default) | Shells out to `swaggerhub spectral:upload` (Node CLI) | The documented / officially supported path. Requires Node 20+ and `swaggerhub-cli` installed and authenticated. |
| `rest` | Direct `PUT /standardization/spectral-rulesets/{owner}/{name}/zip` over HTTPS | Pure Python. Use on the work laptop if the Node CLI isn't installed. Verified working against the live trial. |

### 2.1 `ruleset-publisher version`

```bash
ruleset-publisher version
# -> swagger-studio-ruleset-publisher v0.1.0
```

### 2.2 `ruleset-publisher publish`

Upload `../ruleset/spectral.yaml` (default) into a Studio style-guide slot and activate it.

```bash
ruleset-publisher publish                                # CLI backend, default slot
ruleset-publisher publish --backend rest                 # REST backend, default slot
```

| Flag | Default | Purpose |
|---|---|---|
| `--ruleset, -r PATH` | `../ruleset` | Directory containing `spectral.yaml` to package and upload |
| `--name, -n SLOT` | `openapi-3-0-active` | Studio slot to publish into (e.g. `owasp-top-10-active`). One repo can publish multiple guides to multiple slots. |
| `--backend, -b {cli,rest}` | `cli` | Which upload mechanism to use |
| `--activate / --no-activate` | `--activate` | After upload, flip the slot's `enabled=true` so Studio scans against it. Set `--no-activate` to stage a ruleset without making it live. |

Examples — every variant:

```bash
# Default: publish ../ruleset to openapi-3-0-active via CLI backend, activate
ruleset-publisher publish

# Same, but talk to Studio over REST (no Node CLI required)
ruleset-publisher publish --backend rest

# Publish a different ruleset directory
ruleset-publisher publish --ruleset /path/to/my-other-ruleset

# Publish into a different slot (e.g. OWASP guide alongside the OAS hygiene guide)
ruleset-publisher publish --name owasp-top-10-active --ruleset /path/to/owasp-ruleset

# Stage without activating — content uploaded, slot stays disabled
ruleset-publisher publish --no-activate

# Combined: REST backend, custom ruleset, custom slot, staged-only
ruleset-publisher publish \
    --backend rest \
    --ruleset /path/to/owasp-ruleset \
    --name owasp-top-10-active \
    --no-activate
```

Exit codes: `0` on success, `1` on transport/upload error, `2` if the ruleset directory is missing, `3` if activation can't find the uploaded slot.

### 2.3 `ruleset-publisher deactivate`

Flip a slot's `enabled` flag to `false` in the org config. **Keeps the ruleset content** — only stops Studio from scanning against it.

```bash
ruleset-publisher deactivate --name openapi-3-0-active
```

| Flag | Required | Purpose |
|---|---|---|
| `--name, -n SLOT` | yes | Slot to disable |

### 2.4 `ruleset-publisher delete`

Remove a slot from Studio entirely — config entry **and** ruleset content. Destructive.

```bash
ruleset-publisher delete --name old-experimental-guide --yes
```

| Flag | Required | Purpose |
|---|---|---|
| `--name, -n SLOT` | yes | Slot to delete |
| `--yes, -y` | no | Skip the confirmation prompt. **Required when running non-interactively** (CI, scripts). |

Without `--yes` you'll be prompted; aborting returns exit code 0.

### 2.5 `ruleset-publisher list`

Show every ruleset in the org with its `enabled` state and Studio UUID. Read-only, no flags.

```bash
ruleset-publisher list
```

### 2.6 `ruleset-publisher pull`

Download a slot's current zip from Studio and unpack it locally. Useful for diffing what's live against your local working copy before re-publishing.

```bash
ruleset-publisher pull --name openapi-3-0-active --dest /tmp/live-ruleset
```

| Flag | Required | Purpose |
|---|---|---|
| `--name, -n SLOT` | yes | Slot to download |
| `--dest, -d DIR` | yes | Local directory to unpack into. Created if missing; existing files may be overwritten. |

Exit code `3` if the slot doesn't exist in Studio.

---

## 3. Reports

Run from `projects/reports/`. **No venv, no install** — pure stdlib Python. Both scripts take the scanner's `scan.json` as input.

**bash:**
```bash
cd projects/reports
SCAN=../swagger-studio-scanner/python/output/scan.json
```

**Windows PowerShell:**
```powershell
cd projects\reports
$SCAN = "..\swagger-studio-scanner\python\output\scan.json"
```

In the examples below, the bash blocks use `"$SCAN"` and the PowerShell equivalent is `$SCAN` (no quotes needed unless the path contains spaces, in which case use `"$SCAN"`). Forward-slash paths inside Python args work on Windows too — Python normalizes them — so you can usually copy the bash examples verbatim into PowerShell as long as you've set `$SCAN` first.

> **Line continuations:** the multi-line `python generate_*.py \` blocks use **bash backslash** continuations. In **PowerShell**, the equivalent is a **backtick** at end of line: `` ` ``. Or — easier — just remove the continuations and write the whole command on one line. Both work.

### 3.1 `generate_executive_report.py`

Single-page CIO-facing HTML (self-contained, no external assets).

```bash
python generate_executive_report.py --input "$SCAN" --output output/executive-report.html --org-display-name "Acme Corporation"
```

| Flag | Required | Purpose |
|---|---|---|
| `--input PATH` | yes | Scanner's `scan.json` |
| `--output PATH` | yes | Output HTML file (overwritten if it exists) |
| `--org-display-name STR` | yes | Human-readable org name shown in titles |
| `--ownership-map PATH` | no (Tier 2) | YAML/JSON mapping `owner/name[/version]` → team / domain / contact / repo. Lights up the "teams represented" tile and per-team distribution. PyYAML required for nested maps. |
| `--rule-display-names PATH` | no (Tier 3) | Flat YAML/JSON mapping rule id → humanized name. Replaces raw rule ids in the Pareto with friendly labels. |
| `--asks-file PATH` | no (Tier 3) | Markdown file whose contents replace the "What's needed" paragraph |
| `--placeholder-ask` | no | Use a built-in placeholder paragraph instead of `--asks-file`. Mutually exclusive with `--asks-file`. |

Example variants:

```bash
# Tier 1 only — Studio data, placeholder ask
python generate_executive_report.py \
    --input "$SCAN" \
    --output output/executive-report.html \
    --org-display-name "Acme Corporation" \
    --placeholder-ask

# Tier 1 + Tier 3 (rule labels + real ask)
python generate_executive_report.py \
    --input "$SCAN" \
    --output output/executive-report.html \
    --org-display-name "Acme Corporation" \
    --rule-display-names rule_display_names.yaml \
    --asks-file asks.md

# Full enrichment (Tier 1 + 2 + 3)
python generate_executive_report.py \
    --input "$SCAN" \
    --output output/executive-report.html \
    --org-display-name "Acme Corporation" \
    --ownership-map ownership.yaml \
    --rule-display-names rule_display_names.yaml \
    --asks-file asks.md
```

### 3.2 `generate_platform_report.py`

Dense reference HTML for app dev teams + `findings.csv` side-car. Embedded JSON drives client-side filter/sort.

```bash
python generate_platform_report.py \
    --input "$SCAN" \
    --output-dir output/platform-report \
    --org-display-name "Acme Corporation" \
    --studio-base-url https://app.swaggerhub.com/apis
```

| Flag | Required | Purpose |
|---|---|---|
| `--input PATH` | yes | Scanner's `scan.json` |
| `--output-dir PATH` | yes | Directory for `index.html`, `findings.csv`, and `per-team/` subset reports |
| `--org-display-name STR` | yes | Human-readable org name |
| `--studio-base-url URL` | yes | Base URL for per-API "open in Studio" links (typically `https://app.swaggerhub.com/apis`) |
| `--ownership-map PATH` | no (Tier 2) | Same format as the executive report. Adds team column + filter, per-team summary, per-team subset HTML files. |
| `--rule-display-names PATH` | no (Tier 3) | Flat YAML/JSON rule id → label |
| `--cop-guidance PATH` | no (Tier 3) | Flat YAML/JSON rule id → CoP wiki URL. Replaces "guidance pending" placeholders on rule cards. |
| `--per-team-threshold N` | no (`5`) | When `--ownership-map` is provided, emit a subset HTML for every team whose failing-API count exceeds `N`. |

Example variants:

```bash
# Tier 1 only
python generate_platform_report.py \
    --input "$SCAN" \
    --output-dir output/platform-report \
    --org-display-name "Acme Corporation" \
    --studio-base-url https://app.swaggerhub.com/apis

# With ownership map + per-team subsets at the default threshold (5)
python generate_platform_report.py \
    --input "$SCAN" \
    --output-dir output/platform-report \
    --org-display-name "Acme Corporation" \
    --studio-base-url https://app.swaggerhub.com/apis \
    --ownership-map ownership.yaml

# Full enrichment + per-team subsets at a higher threshold (only big teams)
python generate_platform_report.py \
    --input "$SCAN" \
    --output-dir output/platform-report \
    --org-display-name "Acme Corporation" \
    --studio-base-url https://app.swaggerhub.com/apis \
    --ownership-map ownership.yaml \
    --rule-display-names rule_display_names.yaml \
    --cop-guidance cop_guidance.yaml \
    --per-team-threshold 10
```

### 3.3 Input file formats (Tier 2 and Tier 3)

These are the same formats both report generators expect. Per [reports.md](reports.md), all four files are gitignored by default because they typically carry org-internal information.

**`ownership.yaml`** — nested. PyYAML required (`pip install pyyaml`). Keys are matched in order: `owner/name/version` → `owner/name` → `name`.

```yaml
sparklayerinc/scanner-bad-petstore/1.0.0:
  team: payments
  domain: commerce
  contact_email: payments-leads@acme.example.com
  repo_url: https://git.acme.example.com/payments/scanner-bad-petstore
```

**`rule_display_names.yaml`** — flat. No PyYAML required.

```yaml
operation-operationId: Operations missing operationId
response-success-content: 2xx responses missing content
```

**`cop_guidance.yaml`** — flat. No PyYAML required.

```yaml
operation-operationId: https://confluence.acme.example.com/cop/rules/operation-operationId
```

**`asks.md`** — plain prose embedded verbatim. Don't include the heading; the report adds it.

---

## 4. End-to-end demo loop

Drives publish → seed → scan → report in one go, from the repo root, on the work laptop (no `uv`, no Docker). All three venvs must already be set up per §0.

**bash:**

```bash
ROOT=$(pwd)
SCANNER=projects/swagger-studio-scanner/python
PUBLISHER=projects/swagger-studio-ruleset/python
REPORTS=projects/reports

# (Step 0) Confirm credentials work
(cd $SCANNER && source .venv/bin/activate && scanner probe)

# (Step 1) Publish the ruleset over REST (no Node CLI required)
(cd $PUBLISHER && source .venv/bin/activate && ruleset-publisher publish --backend rest)

# (Step 2) Push the sample APIs (one good, one bad)
bash projects/swagger-studio-scanner/samples/push_samples.sh

# (Step 3) Let SwaggerHub evaluate standardization on the new specs
sleep 25

# (Step 4) Scan
(cd $SCANNER && source .venv/bin/activate && scanner scan)

# (Step 5) Generate the executive + platform reports
(cd $REPORTS && \
    python generate_executive_report.py \
        --input $ROOT/$SCANNER/output/scan.json \
        --output output/executive-report.html \
        --org-display-name "Acme Corporation" \
        --placeholder-ask && \
    python generate_platform_report.py \
        --input $ROOT/$SCANNER/output/scan.json \
        --output-dir output/platform-report \
        --org-display-name "Acme Corporation" \
        --studio-base-url https://app.swaggerhub.com/apis)

# (Step 6) Open the HTML reports in your browser
echo "Open:"
echo "  $ROOT/$SCANNER/output/scan.html             (scanner's built-in)"
echo "  $ROOT/$REPORTS/output/executive-report.html (CIO-facing)"
echo "  $ROOT/$REPORTS/output/platform-report/index.html (platform team)"
```

**Windows PowerShell:**

PowerShell doesn't have bash-style subshells `(cmd1 && cmd2)`. Instead, use `Push-Location` / `Pop-Location` to enter/leave each project folder while keeping a single shell session. Each venv must be deactivated before activating the next one.

```powershell
$ROOT      = (Get-Location).Path
$SCANNER   = "projects\swagger-studio-scanner\python"
$PUBLISHER = "projects\swagger-studio-ruleset\python"
$REPORTS   = "projects\reports"

# (Step 0) Confirm credentials work
Push-Location $SCANNER
.\.venv\Scripts\Activate.ps1
scanner probe
deactivate
Pop-Location

# (Step 1) Publish the ruleset over REST (no Node CLI required)
Push-Location $PUBLISHER
.\.venv\Scripts\Activate.ps1
ruleset-publisher publish --backend rest
deactivate
Pop-Location

# (Step 2) Push the sample APIs (one good, one bad)
# The push_samples.sh script needs bash — run it via Git Bash, WSL, or skip if seeding manually.
bash projects\swagger-studio-scanner\samples\push_samples.sh

# (Step 3) Let SwaggerHub evaluate standardization on the new specs
Start-Sleep -Seconds 25

# (Step 4) Scan
Push-Location $SCANNER
.\.venv\Scripts\Activate.ps1
scanner scan
deactivate
Pop-Location

# (Step 5) Generate the executive + platform reports
Push-Location $REPORTS
python generate_executive_report.py `
    --input "$ROOT\$SCANNER\output\scan.json" `
    --output output\executive-report.html `
    --org-display-name "Acme Corporation" `
    --placeholder-ask
python generate_platform_report.py `
    --input "$ROOT\$SCANNER\output\scan.json" `
    --output-dir output\platform-report `
    --org-display-name "Acme Corporation" `
    --studio-base-url https://app.swaggerhub.com/apis
Pop-Location

# (Step 6) Open the HTML reports in your browser
Write-Host "Open:"
Write-Host "  $ROOT\$SCANNER\output\scan.html             (scanner's built-in)"
Write-Host "  $ROOT\$REPORTS\output\executive-report.html (CIO-facing)"
Write-Host "  $ROOT\$REPORTS\output\platform-report\index.html (platform team)"

# Optional: have Windows open each report in the default browser
Start-Process "$ROOT\$REPORTS\output\executive-report.html"
Start-Process "$ROOT\$REPORTS\output\platform-report\index.html"
```

> **Step 2 caveat on Windows:** `push_samples.sh` is a bash script. If your work laptop doesn't have Git Bash or WSL, either skip Step 2 (and instead seed the org through SwaggerHub UI), or rewrite the script's contents inline — it's just a few `swaggerhub api:create` calls.

Expected on success:

| Step | What to see |
|---|---|
| Probe | `ok: Auth + org reachable; verify standardization next.` |
| Publish | `Uploaded <org>/openapi-3-0-active` + `Activated <org>/openapi-3-0-active` |
| Push samples | Two `-> created` (or `-> updated`) lines |
| Scan summary | `APIs scanned: 2`, `Pass: 1`, `Fail: 1`, `Total findings: 10+` |
| Reports | Three HTML files written, each ≥ 5 KB |

### Resetting between runs

**bash:**

```bash
# Delete the sample specs from Studio (requires swaggerhub-cli, or use REST/curl)
swaggerhub api:delete "$SWAGGERHUB_ORG/scanner-good-petstore" || true
swaggerhub api:delete "$SWAGGERHUB_ORG/scanner-bad-petstore"  || true

# Or, pure-Python: deactivate / delete via the publisher (rulesets only — APIs need REST/curl)
# (cd $PUBLISHER && source .venv/bin/activate && ruleset-publisher list)

# Remove local scan artifacts
rm -rf $SCANNER/output $REPORTS/output
```

**Windows PowerShell:**

```powershell
# Delete the sample specs from Studio — needs swaggerhub-cli, or use Invoke-RestMethod
# (Set $env:SWAGGERHUB_ORG / $env:SWAGGERHUB_API_KEY first, or rely on what's in .env if you're inside a venv)
swaggerhub api:delete "$env:SWAGGERHUB_ORG/scanner-good-petstore"
swaggerhub api:delete "$env:SWAGGERHUB_ORG/scanner-bad-petstore"
# (Errors on 404 are fine — means it's already gone.)

# Remove local scan artifacts
Remove-Item -Recurse -Force $SCANNER\output, $REPORTS\output -ErrorAction SilentlyContinue
```

The ruleset stays in place between scans by design — to replace it, re-run `ruleset-publisher publish`.

---

## 5. Troubleshooting quick table

| Symptom | First thing to check | Fix |
|---|---|---|
| `python -m venv .venv` fails | Python version too old | Need 3.12+. `python --version` |
| `pip install` SSL errors | Corporate TLS inspection | Set `PIP_CERT=/path/to/corp-ca.pem`, see [installation.md §5.2](installation.md#52-ssl-inspection--corporate-ca) |
| `pip install` timeout | Corporate proxy or blocked PyPI | Set `HTTPS_PROXY`, or use internal mirror via `pip config set global.index-url ...` |
| Scanner `auth_failed` | API key wrong / not org-owner scope | Re-issue key at `app.swaggerhub.com/settings/apiKey` |
| Scanner `org_unreachable` | Wrong slug | Check URL: `app.swaggerhub.com/organization/<slug>` |
| Scanner `network_error` | Proxy / TLS / DNS | See [installation.md §5](installation.md#5-corporate-laptop-gotchas) |
| Publisher CLI backend fails with `swaggerhub: command not found` | Node CLI isn't installed | Use `--backend rest` instead |
| Publisher REST backend returns 401 | API key lacks write scope | Re-issue an org-owner write key |
| Scan reports `0` findings on `bad-petstore` | Ruleset isn't active in Studio | Re-run `ruleset-publisher publish` |
| Reports complain about ownership YAML | PyYAML missing for nested format | `pip install --user pyyaml`, or flatten the file |
| PowerShell: `Activate.ps1 cannot be loaded because running scripts is disabled` | Default execution policy blocks local scripts | One-time: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` |
| PowerShell: `scanner: The term 'scanner' is not recognized` | venv isn't activated, or activation didn't add `Scripts\` to PATH | Re-run `.\.venv\Scripts\Activate.ps1`. Confirm with `$env:VIRTUAL_ENV` (should print the venv path). |
| PowerShell: `$env:SSL_CERT_FILE` prints blank in a new terminal | User env var didn't persist | Re-run the `[System.Environment]::SetEnvironmentVariable(..., 'User')` call, then **fully close** the terminal (not just deactivate) and reopen |

---

## See also

- [installation.md](installation.md) — toolchain setup (Python 3.12+, venv, pip)
- [troubleshooting.md](troubleshooting.md) — runnable diagnostics for SSL errors, venv issues, and other common problems
- [runbook.md](runbook.md) — `uv`-based commands for the devcontainer / personal laptop
- [reports.md](reports.md) — deeper dive on the Tier 1 / Tier 2 / Tier 3 report design
- [implementation-context.md](implementation-context.md) — architectural decisions and known gaps
- [../projects/reports/governance-reports-spec-v2.md](../projects/reports/governance-reports-spec-v2.md) — the spec the report generators implement
