"""Smoke tests: prove the package imports and the CLI is wired."""

from __future__ import annotations

from typer.testing import CliRunner

from swagger_studio_scanner import __version__
from swagger_studio_scanner.cli import app
from swagger_studio_scanner.models import ApiRef, Finding, Severity


def test_version_is_populated() -> None:
    assert __version__
    assert isinstance(__version__, str)


def test_cli_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "swagger-studio-scanner" in result.stdout


def test_api_ref_slug_format() -> None:
    ref = ApiRef(owner="acme", name="orders", version="1.0.0")
    assert ref.slug == "acme/orders/1.0.0"


def test_finding_is_immutable_in_severity_enum() -> None:
    finding = Finding(rule="oas3-schema", severity=Severity.CRITICAL, description="x")
    assert finding.severity is Severity.CRITICAL
