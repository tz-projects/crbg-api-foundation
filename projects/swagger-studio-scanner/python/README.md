# swagger-studio-scanner (Python)

Python 3.12+ implementation. Runs with stock Python — no `uv` required.

## Layout

```
python/
├── pyproject.toml             # PEP 621 + ruff/mypy/pytest config
├── .envrc                     # direnv: auto-activates .venv on cd
├── src/swagger_studio_scanner/
│   ├── __init__.py
│   ├── __main__.py            # `python -m swagger_studio_scanner`
│   ├── cli.py                 # Typer commands (version / probe / scan)
│   ├── config.py              # Settings (pydantic-settings)
│   ├── logging_setup.py       # structlog wiring
│   ├── models.py              # Domain models
│   ├── client.py              # Async SwaggerHub REST client + payload parsers
│   ├── probe.py               # Step-zero capability probe
│   ├── scanner.py             # Org-wide scan orchestrator
│   ├── pareto.py              # Rule-failure Pareto + scan summary
│   └── reports/               # JSON / CSV / HTML writers + Jinja template
└── tests/
    ├── test_smoke.py
    ├── test_pareto.py
    ├── test_scanner.py
    └── test_reports.py
```

## First-time setup (plain Python, no uv)

```bash
# macOS / Linux
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e . --no-deps          # registers the `scanner` CLI

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
pip install -e . --no-deps
```

`requirements.txt` pins every dependency to an exact version, so the work laptop gets the same set the Mac dev environment was verified on. Re-run `pip install -r requirements.txt` whenever the file changes.

## Common commands

Once the venv is activated:

```bash
scanner version                      # Confirm CLI is wired
scanner probe                        # Capability probe (needs .env one level up)
scanner scan                         # Full org scan -> output/scan.json + findings.csv + scan.html
scanner scan -o /tmp/myreport        # Write reports elsewhere
```

For tests, lint, and types you'll also need the dev extras:

```bash
pip install -e ".[dev]" --no-deps    # adds pytest, ruff, mypy, etc.
pytest
ruff check .
ruff format .
mypy src
```

## Updating the pinned requirements

If you change `pyproject.toml` dependencies, regenerate `requirements.txt` from a fresh install:

```bash
python -m venv .venv-refresh
.venv-refresh/bin/pip install --upgrade pip
.venv-refresh/bin/pip install -e .
.venv-refresh/bin/pip freeze --exclude-editable | sort > requirements.txt
rm -rf .venv-refresh
```

## Conventions

- `src/` layout (PEP 621). Imports go through the package name, not relative paths.
- Strict mypy + ruff. `S` (bandit), `ANN` (annotations), `B` (bugbear) all on.
- Async I/O via `httpx` + `asyncio.Semaphore`. No threads.
- Config via `pydantic-settings`; nothing reads `os.environ` directly outside `config.py`.
- Logging via `structlog`; nothing uses `print` for runtime output (CLI uses `rich` for human surface).
