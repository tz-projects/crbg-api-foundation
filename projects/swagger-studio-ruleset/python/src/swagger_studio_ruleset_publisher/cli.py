"""Typer CLI for the publisher.

Commands:
  version  — print version
  publish  — push ruleset/ to Studio under {owner}/openapi-3-0-active
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import typer
from rich.console import Console

from swagger_studio_ruleset_publisher import __version__
from swagger_studio_ruleset_publisher.activator import (
    RulesetNotFoundError,
    activate as activate_ruleset,
)
from swagger_studio_ruleset_publisher.config import load_settings
from swagger_studio_ruleset_publisher.logging_setup import configure_logging
from swagger_studio_ruleset_publisher.publishers import (
    Backend,
    CliPublisher,
    Publisher,
    RestPublisher,
)

# Per context doc §3 — Studio scans against this fixed-name slot.
ACTIVE_RULESET_NAME = "openapi-3-0-active"

app = typer.Typer(
    name="ruleset-publisher",
    help="Publishes the API Foundation Spectral ruleset to SwaggerHub Studio.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def version() -> None:
    """Print the publisher version."""
    console.print(f"swagger-studio-ruleset-publisher v{__version__}")


@app.command()
def publish(
    ruleset_dir: Path = typer.Option(
        Path("../ruleset"),
        "--ruleset",
        "-r",
        help="Directory containing spectral.yaml.",
    ),
    backend: Backend = typer.Option(
        Backend.CLI,
        "--backend",
        "-b",
        help="Upload mechanism: shell out to swaggerhub-cli, or direct REST.",
        case_sensitive=False,
    ),
    activate: bool = typer.Option(
        True,
        "--activate/--no-activate",
        help="After upload, mark the ruleset as the org's active style guide.",
    ),
) -> None:
    """Publish the ruleset to {owner}/openapi-3-0-active and activate it."""
    settings = load_settings()
    configure_logging(settings.publisher_log_level)

    ruleset_slug = f"{settings.swaggerhub_org}/{ACTIVE_RULESET_NAME}"
    publisher: Publisher = (
        CliPublisher(settings) if backend is Backend.CLI else RestPublisher(settings)
    )

    console.print(
        f"[bold]Publishing[/] [cyan]{ruleset_slug}[/] via [magenta]{backend.value}[/] backend..."
    )

    async def _run() -> None:
        try:
            upload = await publisher.publish(ruleset_dir, ruleset_slug)
        except FileNotFoundError as e:
            console.print(f"[red]Ruleset not found:[/] {e}")
            raise typer.Exit(code=2) from e
        except RuntimeError as e:
            console.print(f"[red]Publish failed:[/] {e}")
            raise typer.Exit(code=1) from e

        console.print(f"[green]Uploaded[/] {upload.ruleset_slug}")
        console.print(f"  detail: {upload.detail}")
        console.print(f"  open:   [cyan]{upload.studio_url}[/]")

        if not activate:
            console.print("[yellow]Skipping activation[/] (--no-activate).")
            return

        console.print(f"[bold]Activating[/] [cyan]{ACTIVE_RULESET_NAME}[/]...")
        try:
            act = await activate_ruleset(settings, ACTIVE_RULESET_NAME)
        except RulesetNotFoundError as e:
            console.print(f"[red]Activation failed:[/] {e}")
            raise typer.Exit(code=3) from e
        except (RuntimeError, httpx.HTTPError) as e:
            console.print(f"[red]Activation failed:[/] {e}")
            raise typer.Exit(code=1) from e

        console.print(f"[green]Activated[/] {act.owner}/{act.ruleset_name}")
        console.print(f"  detail: {act.detail}")
        console.print(f"  open:   [cyan]{act.studio_url}[/]")

    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    app()
