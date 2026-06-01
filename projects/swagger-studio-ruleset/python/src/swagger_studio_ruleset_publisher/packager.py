"""Bundle a ruleset directory for upload.

The on-disk layout is modular: `spectral.yaml` extends individual
`rules/*.yaml` category files for clean editing and review. Before upload
we flatten everything into a single self-contained `spectral.yaml` so
Studio doesn't have to resolve relative `./rules/*.yaml` references (it
may not, and the modular form is for humans, not the engine).

Built-in extends like `spectral:oas` are left in place — those refer to
Spectral's own bundled rulesets and resolve at runtime regardless.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import yaml


@dataclass(frozen=True)
class RulesetBundle:
    """Result of packaging: a validated directory + a zip artifact path."""

    directory: Path
    zip_path: Path


def validate(directory: Path) -> Path:
    """Resolve and sanity-check the ruleset directory.

    Returns the absolute path. Raises with a helpful message if the directory
    or required entry point is missing — these checks fail fast before any
    network call so the user gets a useful error.
    """
    resolved = directory.expanduser().resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"Ruleset directory not found: {resolved}")
    entry = resolved / "spectral.yaml"
    if not entry.is_file():
        raise FileNotFoundError(
            f"Ruleset entry point not found: {entry}\n"
            "Every ruleset must declare a top-level spectral.yaml."
        )
    return resolved


def package(directory: Path, zip_dest: Path) -> RulesetBundle:
    """Validate, flatten extends, and produce a single-file ZIP at `zip_dest`.

    The ZIP contains exactly one file (`spectral.yaml`) with every relative
    extends inlined. No `rules/` subdirectory in the artifact — modular form
    is for humans, flattened form is for Studio.
    """
    resolved = validate(directory)
    merged_yaml = flatten(resolved)

    zip_dest.parent.mkdir(parents=True, exist_ok=True)
    if zip_dest.exists():
        zip_dest.unlink()

    with ZipFile(zip_dest, "w", ZIP_DEFLATED) as zf:
        zf.writestr("spectral.yaml", merged_yaml)

    return RulesetBundle(directory=resolved, zip_path=zip_dest)


def flatten(directory: Path) -> str:
    """Resolve all relative `extends: ./...yaml` references inline.

    Returns the merged YAML content as a string. Built-in extends (e.g.
    `spectral:oas`, `[spectral:oas, recommended]`) are kept as-is.

    Rule conflicts (same name from multiple files) take last-write-wins
    in extends order, with the entry file's own `rules:` block applied
    last so it always overrides.
    """
    main = yaml.safe_load((directory / "spectral.yaml").read_text(encoding="utf-8")) or {}
    merged_rules: dict[str, Any] = {}
    runtime_extends: list[Any] = []

    raw_extends = main.get("extends") or []
    if not isinstance(raw_extends, list):
        raw_extends = [raw_extends]

    for entry in raw_extends:
        if _is_relative_file_ref(entry):
            sub_path = (directory / entry).resolve()
            sub = yaml.safe_load(sub_path.read_text(encoding="utf-8")) or {}
            sub_rules = sub.get("rules") or {}
            if isinstance(sub_rules, dict):
                merged_rules.update(sub_rules)
        else:
            # built-in ruleset reference — leave for Spectral to resolve.
            runtime_extends.append(entry)

    # Inline rules from the main file last, so they win conflicts.
    own_rules = main.get("rules") or {}
    if isinstance(own_rules, dict):
        merged_rules.update(own_rules)

    output: dict[str, Any] = {}
    if runtime_extends:
        output["extends"] = runtime_extends
    if merged_rules:
        output["rules"] = merged_rules
    return yaml.safe_dump(output, sort_keys=False, default_flow_style=False)


def write_flattened_dir(directory: Path) -> Path:
    """Materialize the flattened ruleset to a temp directory.

    Returns the path to the temp directory (containing a single
    `spectral.yaml`). Caller is responsible for cleanup — use as a
    `shutil.rmtree` target or pass to the CLI backend.
    """
    merged_yaml = flatten(directory)
    tmp = Path(tempfile.mkdtemp(prefix="ruleset-flat-"))
    (tmp / "spectral.yaml").write_text(merged_yaml, encoding="utf-8")
    return tmp


def _is_relative_file_ref(entry: Any) -> bool:
    """True iff this extends entry points at a local YAML file."""
    if not isinstance(entry, str):
        return False
    return entry.startswith("./") or entry.startswith("../") or entry.endswith((".yaml", ".yml"))


def cleanup(bundle: RulesetBundle) -> None:
    """Best-effort cleanup of the generated zip. Safe to call multiple times."""
    try:
        bundle.zip_path.unlink(missing_ok=True)
    except OSError:
        pass


def temp_zip_path(directory: Path) -> Path:
    """Choose a deterministic but isolated location for the temp zip."""
    return directory.parent / f".{directory.name}.bundle.zip"


def has_swaggerhub_cli() -> bool:
    """Cheap availability check for the CLI backend."""
    return shutil.which("swaggerhub") is not None
