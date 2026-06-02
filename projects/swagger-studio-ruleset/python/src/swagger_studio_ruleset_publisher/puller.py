"""Download a ruleset's current contents from SwaggerHub Studio to disk.

  GET /standardization/spectral-rulesets/{owner}/{ruleset_name}/zip
    Accept: application/zip
    -> 200 + raw zip bytes (single-entry `spectral.yaml`)
    -> 404 if the ruleset doesn't exist

Inverse of the upload — fetch what's currently published. Used for
drift detection (diff against the in-repo source) and bootstrapping
(seed a new repo from Studio's existing rules).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

import structlog

from swagger_studio_ruleset_publisher._http import create_client
from swagger_studio_ruleset_publisher.config import Settings

log = structlog.get_logger(__name__)


class RulesetNotInStudioError(RuntimeError):
    """The requested ruleset slot doesn't exist in Studio (HTTP 404)."""


@dataclass(frozen=True)
class PullResult:
    owner: str
    ruleset_name: str
    dest_dir: Path
    files_written: tuple[Path, ...]
    bytes_received: int


async def pull(settings: Settings, ruleset_name: str, dest_dir: Path) -> PullResult:
    """Fetch the ruleset's zip and unpack it into `dest_dir`.

    `dest_dir` is created if missing. Existing files in `dest_dir` with the
    same names will be overwritten — typical use is "pull into an empty dir
    then diff against the source repo."
    """
    owner = settings.swaggerhub_org
    path = f"/standardization/spectral-rulesets/{owner}/{ruleset_name}/zip"
    resolved_dest = dest_dir.expanduser().resolve()
    resolved_dest.mkdir(parents=True, exist_ok=True)

    async with create_client(settings, accept="application/zip") as client:
        log.info("pull_get", path=path, dest=str(resolved_dest))
        resp = await client.get(path)
        if resp.status_code == 404:
            raise RulesetNotInStudioError(
                f"Ruleset '{owner}/{ruleset_name}' not found in Studio (HTTP 404)."
            )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Pull returned HTTP {resp.status_code}: {resp.text.strip()}"
            )
        zip_bytes = resp.content

    written: list[Path] = []
    with ZipFile(io.BytesIO(zip_bytes)) as zf:
        for member in zf.namelist():
            # Guard against zip-slip — refuse absolute paths or `..` segments.
            target = (resolved_dest / member).resolve()
            if not str(target).startswith(str(resolved_dest)):
                raise RuntimeError(f"Refusing zip entry outside dest: {member!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(member))
            written.append(target)

    return PullResult(
        owner=owner,
        ruleset_name=ruleset_name,
        dest_dir=resolved_dest,
        files_written=tuple(written),
        bytes_received=len(zip_bytes),
    )
