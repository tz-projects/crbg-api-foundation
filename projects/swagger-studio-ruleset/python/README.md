# swagger-studio-ruleset-publisher (Python)

Python 3.13+. Runs with stock Python — no `uv` required. Publishes the [`ruleset/`](../ruleset/) directory to SwaggerHub Studio as the org's active standardization ruleset.

## First-time setup (plain Python, no uv)

```bash
# macOS / Linux
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e . --no-deps           # registers the `ruleset-publisher` CLI

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
pip install -e . --no-deps
```

`requirements.txt` pins every dependency to an exact version, so the work laptop matches the Mac dev environment.

> **CLI backend note:** the default `--backend cli` shells out to `swaggerhub spectral:upload`, which requires the Node-based `swaggerhub-cli` to be installed and authenticated. If you only have Python set up, use `--backend rest` — it talks to SwaggerHub directly over HTTPS.

## Common commands

Once the venv is activated:

```bash
ruleset-publisher version

# CLI backend (default) — shells out to `swaggerhub spectral:upload`
ruleset-publisher publish

# REST backend — direct HTTPS PUT (no Node CLI needed)
ruleset-publisher publish --backend rest

# Point at a different ruleset directory
ruleset-publisher publish --ruleset /path/to/other/ruleset
```

For tests, lint, and types you'll also need the dev extras:

```bash
pip install -e ".[dev]" --no-deps
pytest
ruff check .
mypy src
```

## Updating the pinned requirements

If you change `pyproject.toml` dependencies, regenerate `requirements.txt`:

```bash
python -m venv .venv-refresh
.venv-refresh/bin/pip install --upgrade pip
.venv-refresh/bin/pip install -e .
.venv-refresh/bin/pip freeze --exclude-editable | sort > requirements.txt
rm -rf .venv-refresh
```

## Layout

```
python/
├── pyproject.toml
├── .envrc                                  # direnv: shares scanner's .env
├── src/swagger_studio_ruleset_publisher/
│   ├── cli.py                              # Typer commands
│   ├── config.py                           # Shared .env -> Settings
│   ├── logging_setup.py                    # structlog
│   ├── packager.py                         # validate + zip the ruleset dir
│   └── publishers/
│       ├── base.py                         # Publisher protocol + types
│       ├── cli_publisher.py                # Backend: swaggerhub spectral:upload
│       └── rest_publisher.py               # Backend: REST PUT
└── tests/
```

## Backend selection

The `Publisher` protocol in `publishers/base.py` defines a single async surface; the CLI picks `CliPublisher` or `RestPublisher` based on the `--backend` flag. To add a third backend later (e.g. a GitOps controller), implement the protocol and register it in `cli.py` — nothing else changes.

## REST endpoint

`rest_publisher.py` calls `PUT /standardization/spectral-rulesets/{owner}/{rulesetName}/zip` with `Content-Type: application/zip` and raw zip bytes — the same path swaggerhub-cli's `saveSpectralRuleset` helper uses. Verified against a real trial org.
