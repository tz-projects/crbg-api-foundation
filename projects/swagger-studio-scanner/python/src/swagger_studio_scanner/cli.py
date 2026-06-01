"""Typer-based CLI surface.

Commands:
  * `version` — print package version (sanity check the devcontainer wiring).
  * `probe`   — run the capability probe against the configured org.
  * `scan`    — full org scan, writes JSON + CSV + HTML reports to `output/`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from swagger_studio_scanner import __version__
from swagger_studio_scanner.config import load_settings
from swagger_studio_scanner.logging_setup import configure_logging
from swagger_studio_scanner.pareto import ScanSummary
from swagger_studio_scanner.probe import run_probe
from swagger_studio_scanner.reports import write_csv, write_html, write_json
from swagger_studio_scanner.scanner import scan_org

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


@app.command()
def scan(
    output: Path = typer.Option(
        Path("output"),
        "--output",
        "-o",
        help="Directory for scan.json / findings.csv / scan.html.",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        "-n",
        min=1,
        help=(
            "Scan at most N API versions; useful for dev runs against a large org. "
            "Enumeration stops early — no extra pages are fetched once N is reached. "
            "Order follows Studio's listing endpoint (not guaranteed stable)."
        ),
    ),
) -> None:
    """Scan the configured org and write JSON + CSV + HTML reports."""
    settings = load_settings()
    configure_logging(settings.scanner_log_level)

    if limit is not None:
        console.print(
            f"[bold]Scanning[/] org [cyan]{settings.swaggerhub_org}[/] "
            f"[dim](limit: first {limit} APIs)[/] ..."
        )
    else:
        console.print(f"[bold]Scanning[/] org [cyan]{settings.swaggerhub_org}[/] ...")
    report = asyncio.run(scan_org(settings, limit=limit))

    if not report.results:
        console.print("[yellow]No APIs found.[/] Check the org slug and the probe output.")
        raise typer.Exit(code=2)

    json_path = write_json(report, output)
    csv_path = write_csv(report.results, output)
    html_path = write_html(report.results, output)

    summary = ScanSummary.from_results(report.results)
    table = Table(title="Scan summary", show_header=False, box=None, pad_edge=False)
    if report.ruleset and (report.ruleset.name or report.ruleset.version):
        ruleset_label = " ".join(
            v for v in (report.ruleset.name, report.ruleset.version) if v
        )
        table.add_row("Ruleset", ruleset_label)
    table.add_row("APIs scanned", str(summary.total_apis))
    table.add_row("[green]Pass[/]", str(summary.passed))
    table.add_row("[yellow]Warn[/]", str(summary.warned))
    table.add_row("[red]Fail[/]", str(summary.failed))
    table.add_row("[grey50]Error[/]", str(summary.errored))
    table.add_row("Total findings", str(summary.total_findings))
    table.add_row("  Critical", str(summary.critical_findings))
    table.add_row("  Warning", str(summary.warning_findings))
    console.print(table)

    console.print(f"\n[bold]Reports written to[/] [cyan]{output.resolve()}[/]:")
    console.print(f"  • {json_path.name}")
    console.print(f"  • {csv_path.name}")
    console.print(f"  • {html_path.name}  [dim](open in a browser)[/]")


if __name__ == "__main__":  # pragma: no cover
    app()
