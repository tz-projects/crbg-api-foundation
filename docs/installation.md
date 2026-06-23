# Installation — Running the Swagger Studio scanner without Docker

Use this guide when you can't use the devcontainer — typically the **work laptop**, where Docker isn't available. On a machine with Docker (personal laptop), prefer the devcontainer described in the [root README](../README.md): one command, zero install drift.

This guide covers a native install of everything the scanner needs, for **both** the Python and TypeScript implementations. You only need the toolchain for the implementation you intend to run; if you're picking one, **Python** is the lighter install (and is what the context document recommends).

> **Scope note:** This is for the scanner sub-project (`projects/swagger-studio-scanner/`). The per-API governance pipeline will additionally need `swaggerhub-cli`; that's documented in a separate guide when that work starts.

---

## 1. What you need regardless of language

| Item | Why | How to get it |
|---|---|---|
| **Git** | Clone the repo | Usually pre-installed; otherwise [git-scm.com](https://git-scm.com/download/win) (Windows) or `xcode-select --install` (macOS) |
| **VS Code** (recommended) | Best editor experience; picks up `.vscode/` settings | [code.visualstudio.com](https://code.visualstudio.com) |
| **SwaggerHub API key** | Authenticates the scanner against your org | [app.swaggerhub.com/settings/apiKey](https://app.swaggerhub.com/settings/apiKey) — must be an **org-owner read key** (member-scoped keys return partial API lists) |
| **Org slug** | Tells the scanner which organization to enumerate | Visible in the URL on `app.swaggerhub.com/organization/<slug>` |
| **Network egress** to `api.swaggerhub.com` | Scanner is an HTTPS client | Confirm with `curl -I https://api.swaggerhub.com` — see [§5 Corporate laptop gotchas](#5-corporate-laptop-gotchas) if this fails |

### Shared environment file

After installing the toolchain (next sections), create the `.env` file the scanner reads:

```bash
cd projects/swagger-studio-scanner
cp .env.example .env
# Edit .env and fill in SWAGGERHUB_API_KEY and SWAGGERHUB_ORG
```

This single `.env` is read by **both** the Python and TypeScript implementations.

---

## 2. Python implementation

### 2.1 Required software

| Tool | Required version | Purpose |
|---|---|---|
| Python | **3.13+** | Runtime |
| pip + venv | shipped with Python | Package manager + virtualenv (both included in the stock Python install) |

> **No `uv` needed on the work laptop.** The `pure-python` branch ships pinned `requirements.txt` files so a clone-and-pip flow works without any extra toolchain. If you're on a personal machine and prefer `uv`, the `uv sync` flow still works against the same `pyproject.toml` — see §2.5 below.

### 2.2 Install Python 3.13

Pick one path based on what your work laptop allows.

**Windows (no admin rights — most restrictive):**
- [python.org installer](https://www.python.org/downloads/) → check "Install for my user only" (no admin needed). Verify with `python --version`.
- Or via the Microsoft Store: search "Python 3.13" → Install (user-scope, no admin).

**Windows (with admin or winget):**
```powershell
winget install --id Python.Python.3.13
```

**macOS:**
```bash
# Homebrew (recommended if you have it)
brew install python@3.13

# Or python.org installer if Homebrew is blocked
```

**Linux:**
```bash
# Most distros: use the system package manager
sudo apt install python3.13 python3.13-venv      # Debian/Ubuntu (may need the deadsnakes PPA)
sudo dnf install python3.13                       # Fedora/RHEL
```

**If your laptop blocks all of the above**, use [pyenv](https://github.com/pyenv/pyenv) (Linux/macOS) or [pyenv-win](https://github.com/pyenv-win/pyenv-win) (Windows) — it builds Python in your user directory with no system changes.

Verify:
```bash
python --version    # or python3 --version
# Expected: Python 3.13.x
```

### 2.3 Build and run the Python scanner (plain pip)

```bash
cd projects/swagger-studio-scanner/python

# Create the virtual environment (stock Python only).
python -m venv .venv

# Activate it.
source .venv/bin/activate         # macOS / Linux
.venv\Scripts\Activate.ps1        # Windows PowerShell

# Install the pinned dependencies, then the project itself.
pip install --upgrade pip
pip install -r requirements.txt
pip install -e . --no-deps        # registers the `scanner` console command

# Smoke test.
scanner version
scanner probe
```

The same flow applies to the ruleset publisher under `projects/swagger-studio-ruleset/python/`. Use `--backend rest` with the publisher if you don't have the Node-based `swaggerhub-cli` installed.

For tests, lint, and types add the dev extras:

```bash
pip install -e ".[dev]" --no-deps
pytest
ruff check .
mypy src
```

### 2.4 Report generators (no install needed)

The HTML report generators under `projects/reports/` are deliberately stdlib-only — they run directly with the system Python interpreter, no venv or `pip install` required. Once you have a `scan.json` from the scanner, generate both reports with:

```bash
cd projects/reports

python generate_executive_report.py \
    --input ../swagger-studio-scanner/python/output/scan.json \
    --output output/executive-report.html \
    --org-display-name "Your Org"

python generate_platform_report.py \
    --input ../swagger-studio-scanner/python/output/scan.json \
    --output-dir output/platform-report \
    --org-display-name "Your Org" \
    --studio-base-url https://app.swaggerhub.com/apis
```

PyYAML is optional and only needed for nested YAML ownership maps — see [`projects/reports/README.md`](../projects/reports/README.md).

### 2.5 Refreshing `requirements.txt`

The pinned file is generated by `pip freeze` after a fresh install of the project. If you (or anyone) bumps a dependency in `pyproject.toml`, regenerate it:

```bash
python -m venv .venv-refresh
.venv-refresh/bin/pip install --upgrade pip
.venv-refresh/bin/pip install -e .
.venv-refresh/bin/pip freeze --exclude-editable | sort > requirements.txt
rm -rf .venv-refresh
```

Then commit the updated `requirements.txt` so the work laptop picks up the new pins on its next pull.

### 2.6 Optional: `uv` for personal-machine convenience

`uv` is **not** required, but it's faster and is what the original `uv.lock` file was authored with. If you have it on a personal machine:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
# Windows PowerShell:
#   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

cd projects/swagger-studio-scanner/python
uv sync --all-extras
uv run scanner version
```

Don't introduce `uv` on the work laptop just for this project — the plain-pip flow above produces an equivalent environment.

---

## 3. TypeScript implementation

### 3.1 Required software

| Tool | Required version | Purpose |
|---|---|---|
| Node.js | **20.17+** (LTS) | Runtime |
| pnpm | latest | Package manager |

### 3.2 Install Node.js 20

**Windows:**
- [nodejs.org installer](https://nodejs.org/) → pick the LTS (20.x) installer. "Install for current user" path doesn't need admin.
- Or `winget install --id OpenJS.NodeJS.LTS` if you have winget.

**macOS:**
```bash
brew install node@20
# Or use the official installer from nodejs.org
```

**Linux:**
```bash
# Debian/Ubuntu via NodeSource (the apt default is usually too old)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install nodejs
```

**If your laptop blocks system Node**, use [fnm](https://github.com/Schniz/fnm) or [nvm](https://github.com/nvm-sh/nvm) (Linux/macOS) / [nvm-windows](https://github.com/coreybutler/nvm-windows). Both install Node entirely in your user directory.

Verify:
```bash
node --version    # Expected: v20.17.x or higher (must be ≥ 20.17.0)
```

### 3.3 Install pnpm

The cleanest path is **corepack**, which ships with Node 20 — no extra install needed:

```bash
corepack enable
corepack prepare pnpm@latest --activate
```

If corepack is disabled on your laptop, fall back to:
```bash
npm install -g pnpm
# Or the standalone script:
#   macOS/Linux:  curl -fsSL https://get.pnpm.io/install.sh | sh -
#   Windows:      iwr https://get.pnpm.io/install.ps1 -useb | iex
```

Verify:
```bash
pnpm --version
# Expected: 9.x or higher
```

### 3.4 Build and run the TypeScript scanner

```bash
cd projects/swagger-studio-scanner/typescript

# Install all dependencies.
pnpm install

# Run the CLI in dev mode (no build step — tsx runs the TS directly).
pnpm dev version
pnpm dev probe

# Tests, lint, types, build
pnpm test
pnpm lint
pnpm typecheck
pnpm build    # Emits dist/ — only needed for production deployment
```

---

## 4. Verify the install end-to-end

Run the **capability probe** — this is step zero from the [context document §8](../smartbear-governance-enforcement-context.md). It confirms auth, org reachability, and (eventually) that the Governance tier is active. Failing fast here saves you from running a 600-API scan against a misconfigured environment.

Pick whichever side you installed:

```bash
# Python
cd projects/swagger-studio-scanner/python && uv run scanner probe

# TypeScript
cd projects/swagger-studio-scanner/typescript && pnpm dev probe
```

Expected on success:
```
ok: Auth + org reachable; verify standardization next.
```

If it fails, the status code tells you which leg broke:

| Status | Meaning | First thing to check |
|---|---|---|
| `auth_failed` | 401/403 from Studio | API key is wrong, expired, or not org-owner scope |
| `org_unreachable` | 404 listing org APIs | `SWAGGERHUB_ORG` slug is wrong |
| `network_error` | TLS, DNS, or timeout | See [§5 Corporate laptop gotchas](#5-corporate-laptop-gotchas) |

---

## 5. Corporate laptop gotchas

The context document flagged these explicitly — they're the most common reasons the scanner runs cleanly on a personal laptop but fails on a work one.

### 5.1 Corporate proxy

If your network forces traffic through an HTTP proxy, both Python (httpx) and Node (fetch) respect standard env vars. Set them once in your shell profile or in `.env`:

```bash
export HTTPS_PROXY=http://proxy.corp.example:8080
export HTTP_PROXY=http://proxy.corp.example:8080
export NO_PROXY=localhost,127.0.0.1
```

Check with your security team for the correct host/port — it's the same proxy your browser is using.

### 5.2 SSL inspection / corporate CA

Many corporate networks intercept HTTPS with their own root CA. The browser trusts it (because the CA is in the OS trust store); command-line HTTP clients often **don't**, which produces confusing "certificate verify failed" errors even though `https://api.swaggerhub.com` opens fine in Chrome.

Two ways to fix:

**Python (httpx via certifi):**
```bash
# Point at the corporate CA bundle (.pem file from IT)
export SSL_CERT_FILE=/path/to/corporate-ca-bundle.pem
export REQUESTS_CA_BUNDLE=/path/to/corporate-ca-bundle.pem
```

**Node:**
```bash
export NODE_EXTRA_CA_CERTS=/path/to/corporate-ca-bundle.pem
```

If IT can't give you the bundle file, you can export it from the OS trust store yourself — ask and someone will know the procedure for your machine.

### 5.3 pip / npm registry blocking

Some corporate networks block public registries and require an internal mirror.

- **pip / uv:** `uv` honors `PIP_INDEX_URL`. Set `export UV_INDEX_URL=https://your-internal-mirror/simple/`.
- **pnpm:** `pnpm config set registry https://your-internal-mirror/`.

### 5.4 Read-permission sanction

The scanner is **read-only** — it never writes to Studio. But running a full-estate enumeration against the production org is politically visible. Before the first full scan against the real org, give the platform owner a heads-up. The probe is harmless and doesn't need sanction.

### 5.5 Conservative rate limiting

The scanner already batches requests with a concurrency cap (`SCANNER_CONCURRENCY`, default 8). If you hit 429s, lower it in `.env`:

```
SCANNER_CONCURRENCY=4
```

SaaS rate limits aren't aggressively documented; 8 has been fine in testing but a 600-API run on a slow link may want 4 to be safe.

---

## 6. VS Code (optional but recommended)

If you install VS Code, the workspace ships `.vscode/extensions.json` with the full recommended extension set (Python, Pylance, Ruff, ESLint, Prettier, Vitest Explorer, etc.). On first open, VS Code will offer to install them — click yes. Everything else (format-on-save, strict type checking, test discovery) is preconfigured in `.vscode/settings.json` and applies automatically.

---

## 7. Quick reference — minimal install checklist

For someone copying this into a setup ticket, the absolute minimum:

**Python path (work laptop, no uv):**
1. Python 3.13+ (`python --version`)
2. `cd projects/swagger-studio-scanner/python`
3. `python -m venv .venv && source .venv/bin/activate` (or `.venv\Scripts\Activate.ps1` on Windows)
4. `pip install -r requirements.txt && pip install -e . --no-deps`
5. `scanner probe`

**TypeScript path:**
1. Node 20.17+ LTS
2. `corepack enable && corepack prepare pnpm@latest --activate`
3. `cd projects/swagger-studio-scanner/typescript && pnpm install`
4. `pnpm dev probe`

Both expect `projects/swagger-studio-scanner/.env` to exist with `SWAGGERHUB_API_KEY` and `SWAGGERHUB_ORG` filled in.
