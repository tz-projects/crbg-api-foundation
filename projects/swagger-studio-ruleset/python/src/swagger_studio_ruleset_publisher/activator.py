"""Mark an uploaded Spectral ruleset as the org's active style guide
— or revoke that mark.

`spectral:upload` only saves a draft style guide; the SwaggerHub UI's
"Publish" button is what flips `spectralRulesets[].enabled` in the org's
standardization config. Without an enabled entry, `/standardization`
returns no findings — the engine has nothing to evaluate against.

Flow (works around the field-naming asymmetry SwaggerHub uses — upload
addresses rulesets by name, the org config addresses them by UUID):

  1. (skippable) GET /standardization/spectral-rulesets/{owner}
       -> array of {id, name, ...}. Look up the UUID by `name`.
       Retried with backoff to ride out the indexing lag right after upload.
       SKIPPED when the caller already has the UUID (the REST upload
       endpoint returns it in the response body — pass it via the
       `ruleset_id` arg to short-circuit this step).

  2. GET  /standardization/{owner}/config
       -> shallow form: spectralRulesets[] entries carry only
       `rulesetId` (the UUID from step 1) and `enabled`.

  3. POST /standardization/{owner}/config  (entire modified body)
       Find the entry whose `rulesetId` == lookup UUID, flip `enabled`.
       For `activate`: create the entry if missing. For `deactivate`:
       if there's no entry there's nothing to disable — return early.

Endpoints discovered by capturing the UI's network calls.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from swagger_studio_ruleset_publisher._http import create_client
from swagger_studio_ruleset_publisher.config import Settings

log = structlog.get_logger(__name__)

# Backoff schedule for the lookup step. Total wait <= 7s.
_LOOKUP_DELAYS_S: tuple[float, ...] = (0.0, 2.0, 5.0)


class RulesetNotFoundError(RuntimeError):
    """The named ruleset wasn't found in the org's rulesets list."""


@dataclass(frozen=True)
class ActivationResult:
    owner: str
    ruleset_name: str
    ruleset_id: str
    enabled: bool
    studio_url: str
    detail: str


async def activate(
    settings: Settings,
    ruleset_name: str,
    ruleset_id: str | None = None,
) -> ActivationResult:
    """Flip enabled=True for `ruleset_name` in the org config and persist.

    If `ruleset_id` is supplied (the REST upload returns it), the lookup
    round-trip is skipped — saves one request and removes the
    indexing-lag retry surface. Falls back to lookup-by-name otherwise.
    """
    return await _set_state(settings, ruleset_name, enabled=True, ruleset_id=ruleset_id)


async def deactivate(
    settings: Settings,
    ruleset_name: str,
    ruleset_id: str | None = None,
) -> ActivationResult:
    """Flip enabled=False for `ruleset_name` in the org config and persist.

    Idempotent: if no entry exists in the config, returns success with
    `detail` noting the no-op. The ruleset itself isn't deleted —
    its content stays in Studio under the original slot.
    """
    return await _set_state(settings, ruleset_name, enabled=False, ruleset_id=ruleset_id)


async def _set_state(
    settings: Settings,
    ruleset_name: str,
    *,
    enabled: bool,
    ruleset_id: str | None,
) -> ActivationResult:
    """Shared flow for activate/deactivate. `enabled` decides the direction."""
    owner = settings.swaggerhub_org
    op = "activate" if enabled else "deactivate"

    async with create_client(settings) as client:
        if ruleset_id is None:
            ruleset_id = await lookup_ruleset_id(client, owner, ruleset_name)
            if ruleset_id is None:
                raise RulesetNotFoundError(
                    f"Ruleset {ruleset_name!r} not found in /standardization/spectral-rulesets/{owner} "
                    f"after {len(_LOOKUP_DELAYS_S)} attempts."
                )
        else:
            log.info(f"{op}_lookup_skipped", ruleset_id=ruleset_id)

        config_path = f"/standardization/{owner}/config"
        log.info(f"{op}_get", path=config_path, ruleset_id=ruleset_id)
        get_resp = await client.get(config_path)
        get_resp.raise_for_status()
        config: dict[str, Any] = get_resp.json()

        changed = _set_enabled_by_id(config, ruleset_id, enabled=enabled)
        if not changed:
            # Deactivating something that was never in the config — no-op.
            return ActivationResult(
                owner=owner,
                ruleset_name=ruleset_name,
                ruleset_id=ruleset_id,
                enabled=False,
                studio_url=f"https://app.swaggerhub.com/organizations/{owner}/governance",
                detail="no-op (entry not present in config)",
            )

        log.info(f"{op}_post", path=config_path, ruleset_id=ruleset_id)
        post_resp = await client.post(
            config_path, json=config, headers={"Content-Type": "application/json"}
        )
        if post_resp.status_code >= 400:
            raise RuntimeError(
                f"{op.capitalize()} POST returned HTTP {post_resp.status_code}: "
                f"{post_resp.text.strip()}"
            )

    return ActivationResult(
        owner=owner,
        ruleset_name=ruleset_name,
        ruleset_id=ruleset_id,
        enabled=enabled,
        studio_url=f"https://app.swaggerhub.com/organizations/{owner}/governance",
        detail=f"HTTP {post_resp.status_code}",
    )


async def lookup_ruleset_id(
    client: httpx.AsyncClient,
    owner: str,
    ruleset_name: str,
) -> str | None:
    """Find the ruleset's UUID by name. Retries to ride out upload-indexing lag.

    Public so the deleter / other modules can reuse it.
    """
    path = f"/standardization/spectral-rulesets/{owner}"
    last_status: int | None = None
    for delay in _LOOKUP_DELAYS_S:
        if delay > 0:
            log.info("lookup_retry", delay_s=delay, path=path)
            await asyncio.sleep(delay)
        else:
            log.info("lookup", path=path)
        resp = await client.get(path)
        last_status = resp.status_code
        if resp.status_code >= 400:
            continue
        data = resp.json()
        if not isinstance(data, list):
            continue
        for entry in data:
            if not isinstance(entry, dict):
                continue
            if entry.get("name") == ruleset_name:
                rid = entry.get("id")
                if isinstance(rid, str) and rid:
                    return rid
    log.warning("lookup_exhausted", last_status=last_status)
    return None


def _set_enabled_by_id(
    config: dict[str, Any], ruleset_id: str, enabled: bool = True
) -> bool:
    """Set the entry's `enabled` flag. Returns True if a write is needed.

    For `enabled=True`: appends a new entry if one doesn't exist (activate
    semantics — caller wants this thing turned on regardless of prior state).

    For `enabled=False`: returns False when no entry exists (deactivate
    semantics — nothing to disable, and creating a disabled entry would
    be pointless noise).

    Mutates `config` in place when applicable.
    """
    rulesets = config.get("spectralRulesets")
    if not isinstance(rulesets, list):
        if not enabled:
            return False
        rulesets = []
        config["spectralRulesets"] = rulesets

    for entry in rulesets:
        if isinstance(entry, dict) and entry.get("rulesetId") == ruleset_id:
            entry["enabled"] = enabled
            return True

    if not enabled:
        return False

    rulesets.append({"rulesetId": ruleset_id, "enabled": True})
    return True


def remove_entry_by_id(config: dict[str, Any], ruleset_id: str) -> bool:
    """Drop the `spectralRulesets[]` entry for `ruleset_id`. Returns True if removed.

    Used by the deleter after a successful DELETE so we don't leave a
    dangling rulesetId in the config pointing at a slot that no longer
    exists.
    """
    rulesets = config.get("spectralRulesets")
    if not isinstance(rulesets, list):
        return False
    new_list = [
        e
        for e in rulesets
        if not (isinstance(e, dict) and e.get("rulesetId") == ruleset_id)
    ]
    if len(new_list) == len(rulesets):
        return False
    config["spectralRulesets"] = new_list
    return True
