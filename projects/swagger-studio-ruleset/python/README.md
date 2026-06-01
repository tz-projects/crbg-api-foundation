# swagger-studio-ruleset-publisher (Python)

Python 3.12, uv-managed. Publishes the [`ruleset/`](../ruleset/) directory to SwaggerHub Studio as the org's active standardization ruleset.

## Common commands

```bash
uv sync --all-extras

# CLI backend (default) — shells out to `swaggerhub spectral:upload`
uv run ruleset-publisher publish

# REST backend — direct HTTPS PUT
uv run ruleset-publisher publish --backend rest

# Point at a different ruleset directory
uv run ruleset-publisher publish --ruleset /path/to/other/ruleset

# Sanity
uv run ruleset-publisher version
uv run pytest
uv run ruff check .
uv run mypy src
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
