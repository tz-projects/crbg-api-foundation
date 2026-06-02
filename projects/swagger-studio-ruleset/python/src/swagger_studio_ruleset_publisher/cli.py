"""Typer CLI for the publisher.

Commands:
  version     — print version
  publish     — upload ruleset/ and activate it (create or update)
  deactivate  — flip enabled=false for a slot, keep its content
  delete      — remove the slot from Studio entirely
  list        — show every ruleset in the org with its enabled state
  pull        — download a slot's current content to disk
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.table import Table

from swagger_studio_ruleset_publisher import __version__
from swagger_studio_ruleset_publisher.activator import (
    RulesetNotFoundError,
    activate as activate_ruleset,
    deactivate as deactivate_ruleset,
)
from swagger_studio_ruleset_publisher.config import load_settings
from swagger_studio_ruleset_publisher.deleter import delete as delete_ruleset
from swagger_studio_ruleset_publisher.lister import list_rulesets
from swagger_studio_ruleset_publisher.logging_setup import configure_logging
from swagger_studio_ruleset_publisher.publishers import (
    Backend,
    CliPublisher,
    Publisher,
    RestPublisher,
)
from swagger_studio_ruleset_publisher.puller import (
    RulesetNotInStudioError,
    pull as pull_ruleset,
)

# Per context doc §3 — Studio scans against this fixed-name slot for the
# OAS hygiene guide. A second guide (OWASP) is published under its own slot;
# both can be active simultaneously because Studio's `spectralRulesets[]`
# config keeps a per-entry `enabled` flag.
DEFAULT_RULESET_NAME = "openapi-3-0-active"

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
    name: str = typer.Option(
        DEFAULT_RULESET_NAME,
        "--name",
        "-n",
        help="Studio style-guide slot to publish into (e.g. openapi-3-0-active, owasp-top-10-active).",
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
    """Publish the ruleset to {owner}/{name} and activate it."""
    settings = load_settings()
    configure_logging(settings.publisher_log_level)

    ruleset_slug = f"{settings.swaggerhub_org}/{name}"
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
        if upload.ruleset_id:
            console.print(f"  id:     [dim]{upload.ruleset_id}[/]")
        console.print(f"  open:   [cyan]{upload.studio_url}[/]")

        if not activate:
            console.print("[yellow]Skipping activation[/] (--no-activate).")
            return

        console.print(f"[bold]Activating[/] [cyan]{name}[/]...")
        try:
            act = await activate_ruleset(settings, name, upload.ruleset_id)
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


@app.command()
def deactivate(
    name: str = typer.Option(
        ..., "--name", "-n", help="Studio style-guide slot to deactivate."
    ),
) -> None:
    """Set enabled=false for {owner}/{name} in the org config. Keeps content."""
    settings = load_settings()
    configure_logging(settings.publisher_log_level)

    console.print(f"[bold]Deactivating[/] [cyan]{settings.swaggerhub_org}/{name}[/]...")

    async def _run() -> None:
        try:
            result = await deactivate_ruleset(settings, name)
        except RulesetNotFoundError as e:
            console.print(f"[red]Deactivation failed:[/] {e}")
            raise typer.Exit(code=3) from e
        except (RuntimeError, httpx.HTTPError) as e:
            console.print(f"[red]Deactivation failed:[/] {e}")
            raise typer.Exit(code=1) from e

        verb = "Deactivated" if result.enabled is False else "No change"
        console.print(f"[green]{verb}[/] {result.owner}/{result.ruleset_name}")
        console.print(f"  detail: {result.detail}")
        console.print(f"  open:   [cyan]{result.studio_url}[/]")

    asyncio.run(_run())


@app.command(name="delete")
def delete_cmd(
    name: str = typer.Option(
        ..., "--name", "-n", help="Studio style-guide slot to delete."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt (required for non-TTY use)."
    ),
) -> None:
    """Remove {owner}/{name} from Studio entirely (config entry + ruleset)."""
    settings = load_settings()
    configure_logging(settings.publisher_log_level)

    slug = f"{settings.swaggerhub_org}/{name}"
    if not yes:
        confirm = typer.confirm(f"Delete {slug}? This cannot be undone.")
        if not confirm:
            console.print("[yellow]Aborted.[/]")
            raise typer.Exit(code=0)

    console.print(f"[bold]Deleting[/] [cyan]{slug}[/]...")

    async def _run() -> None:
        try:
            result = await delete_ruleset(settings, name)
        except (RuntimeError, httpx.HTTPError) as e:
            console.print(f"[red]Delete failed:[/] {e}")
            raise typer.Exit(code=1) from e

        if result.deleted:
            console.print(f"[green]Deleted[/] {result.owner}/{result.ruleset_name}")
        else:
            console.print(f"[yellow]Already absent[/] {result.owner}/{result.ruleset_name}")
        console.print(f"  detail:         {result.detail}")
        console.print(f"  config cleaned: {result.config_entry_removed}")
        if result.ruleset_id:
            console.print(f"  id:             [dim]{result.ruleset_id}[/]")

    asyncio.run(_run())


@app.command(name="list")
def list_cmd() -> None:
    """Show every ruleset in the org with its enabled state."""
    settings = load_settings()
    configure_logging(settings.publisher_log_level)

    async def _run() -> None:
        try:
            rulesets = await list_rulesets(settings)
        except (RuntimeError, httpx.HTTPError) as e:
            console.print(f"[red]List failed:[/] {e}")
            raise typer.Exit(code=1) from e

        if not rulesets:
            console.print(f"[yellow]No rulesets found for[/] {settings.swaggerhub_org}.")
            return

        table = Table(title=f"Rulesets in {settings.swaggerhub_org}")
        table.add_column("Name", style="cyan")
        table.add_column("Enabled", style="green")
        table.add_column("UUID", style="dim")
        for r in rulesets:
            table.add_row(
                r.name,
                "[green]yes[/]" if r.enabled else "[red]no[/]",
                r.ruleset_id,
            )
        console.print(table)

    asyncio.run(_run())


@app.command()
def pull(
    name: str = typer.Option(
        ..., "--name", "-n", help="Studio style-guide slot to pull."
    ),
    dest: Path = typer.Option(
        ...,
        "--dest",
        "-d",
        help="Destination directory (created if missing). Existing files may be overwritten.",
    ),
) -> None:
    """Download {owner}/{name}'s current zip from Studio and unpack into DEST."""
    settings = load_settings()
    configure_logging(settings.publisher_log_level)

    console.print(
        f"[bold]Pulling[/] [cyan]{settings.swaggerhub_org}/{name}[/] -> {dest}"
    )

    async def _run() -> None:
        try:
            result = await pull_ruleset(settings, name, dest)
        except RulesetNotInStudioError as e:
            console.print(f"[red]{e}[/]")
            raise typer.Exit(code=3) from e
        except (RuntimeError, httpx.HTTPError) as e:
            console.print(f"[red]Pull failed:[/] {e}")
            raise typer.Exit(code=1) from e

        console.print(
            f"[green]Pulled[/] {result.owner}/{result.ruleset_name} "
            f"({result.bytes_received} bytes)"
        )
        for fp in result.files_written:
            console.print(f"  wrote: [dim]{fp}[/]")

    asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    app()
