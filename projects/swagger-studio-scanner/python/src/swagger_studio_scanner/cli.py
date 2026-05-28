"""Typer-based CLI surface.

Two commands today:
  * `version` — print package version (sanity check the devcontainer wiring).
  * `probe`   — run the capability probe against the configured org.

`scan` will be added once the report writers land.
"""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from swagger_studio_scanner import __version__
from swagger_studio_scanner.config import load_settings
from swagger_studio_scanner.logging_setup import configure_logging
from swagger_studio_scanner.probe import run_probe

app = typer.Typer(
    name="scanner",
    help="Org-wide non-conformance scanner for SmartBear Swagger Studio.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def version() -> None:
    """Print the scanner version."""
    console.print(f"swagger-studio-scanner v{__version__}")


@app.command()
def probe() -> None:
    """Verify auth, org reachability, and governance availability."""
    settings = load_settings()
    configure_logging(settings.scanner_log_level)
    result = asyncio.run(run_probe(settings))
    style = "green" if result.ok else "red"
    console.print(f"[{style}]{result.status.value}[/]: {result.detail}")
    raise typer.Exit(code=0 if result.ok else 1)


if __name__ == "__main__":  # pragma: no cover
    app()
