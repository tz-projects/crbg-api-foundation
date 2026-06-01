"""Packager unit tests — no network, no subprocess."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

from swagger_studio_ruleset_publisher import packager


def _seed_ruleset(root: Path) -> Path:
    rs = root / "ruleset"
    (rs / "rules").mkdir(parents=True)
    (rs / "spectral.yaml").write_text(
        "extends:\n"
        "  - ./rules/info.yaml\n"
        "  - ./rules/operations.yaml\n"
    )
    (rs / "rules" / "info.yaml").write_text(
        "rules:\n"
        "  info-contact:\n"
        "    severity: error\n"
        "    given: $.info\n"
        "    then:\n"
        "      field: contact\n"
        "      function: truthy\n"
    )
    (rs / "rules" / "operations.yaml").write_text(
        "rules:\n"
        "  operation-operationId:\n"
        "    severity: error\n"
        "    given: $.paths[*]\n"
        "    then:\n"
        "      field: operationId\n"
        "      function: truthy\n"
    )
    return rs


def test_validate_returns_resolved_path(tmp_path: Path) -> None:
    rs = _seed_ruleset(tmp_path)
    result = packager.validate(rs)
    assert result == rs.resolve()


def test_validate_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        packager.validate(tmp_path / "does-not-exist")


def test_validate_missing_entry_point_raises(tmp_path: Path) -> None:
    empty = tmp_path / "ruleset"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="spectral.yaml"):
        packager.validate(empty)


def test_package_produces_single_file_zip_with_flattened_yaml(tmp_path: Path) -> None:
    rs = _seed_ruleset(tmp_path)
    zip_dest = tmp_path / "bundle.zip"
    bundle = packager.package(rs, zip_dest)

    assert bundle.zip_path == zip_dest
    assert zip_dest.is_file()

    with ZipFile(zip_dest) as zf:
        names = set(zf.namelist())
        assert names == {"spectral.yaml"}, f"expected flat single-file artifact, got {names}"
        merged = yaml.safe_load(zf.read("spectral.yaml"))

    # Rules from both extends files should be inlined.
    assert "info-contact" in merged["rules"]
    assert "operation-operationId" in merged["rules"]
    # Relative file extends should be gone from the flattened artifact.
    assert "extends" not in merged


def test_flatten_keeps_builtin_extends_but_drops_relative(tmp_path: Path) -> None:
    rs = tmp_path / "ruleset"
    (rs / "rules").mkdir(parents=True)
    (rs / "spectral.yaml").write_text(
        "extends:\n"
        "  - spectral:oas\n"
        "  - ./rules/info.yaml\n"
    )
    (rs / "rules" / "info.yaml").write_text("rules: {info-contact: {severity: error}}\n")

    merged = yaml.safe_load(packager.flatten(rs))
    assert merged["extends"] == ["spectral:oas"]
    assert "info-contact" in merged["rules"]


def test_flatten_own_rules_win_over_inlined(tmp_path: Path) -> None:
    rs = tmp_path / "ruleset"
    (rs / "rules").mkdir(parents=True)
    (rs / "rules" / "info.yaml").write_text(
        "rules: {info-contact: {severity: warn}}\n"
    )
    (rs / "spectral.yaml").write_text(
        "extends: [./rules/info.yaml]\n"
        "rules:\n"
        "  info-contact: {severity: error}\n"
    )

    merged = yaml.safe_load(packager.flatten(rs))
    assert merged["rules"]["info-contact"]["severity"] == "error"


def test_cleanup_is_idempotent(tmp_path: Path) -> None:
    rs = _seed_ruleset(tmp_path)
    bundle = packager.package(rs, tmp_path / "bundle.zip")
    packager.cleanup(bundle)
    packager.cleanup(bundle)  # second call must not raise
    assert not bundle.zip_path.exists()
