# swagger-studio-scanner (Python)

Python 3.12 implementation. Managed by [`uv`](https://docs.astral.sh/uv/).

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

## Common commands

```bash
uv sync --all-extras    # Install + create .venv (post-create runs this for you)
uv run scanner version  # Confirm CLI is wired
uv run scanner probe    # Capability probe (needs .env one level up)
uv run scanner scan     # Full org scan -> writes output/scan.json + findings.csv + scan.html
uv run scanner scan -o /tmp/myreport   # Write reports elsewhere

uv run pytest           # Tests
uv run ruff check .     # Lint
uv run ruff format .    # Format
uv run mypy src         # Strict type-check
```

## Conventions

- `src/` layout (PEP 621). Imports go through the package name, not relative paths.
- Strict mypy + ruff. `S` (bandit), `ANN` (annotations), `B` (bugbear) all on.
- Async I/O via `httpx` + `asyncio.Semaphore`. No threads.
- Config via `pydantic-settings`; nothing reads `os.environ` directly outside `config.py`.
- Logging via `structlog`; nothing uses `print` for runtime output (CLI uses `rich` for human surface).
