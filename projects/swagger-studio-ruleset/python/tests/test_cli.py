"""CLI surface tests — no network."""

from __future__ import annotations

from typer.testing import CliRunner

from swagger_studio_ruleset_publisher.cli import app


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "swagger-studio-ruleset-publisher" in result.stdout


def test_publish_help_lists_backend_option() -> None:
    result = CliRunner().invoke(app, ["publish", "--help"])
    assert result.exit_code == 0
    assert "--backend" in result.stdout
    assert "cli" in result.stdout.lower()
    assert "rest" in result.stdout.lower()
