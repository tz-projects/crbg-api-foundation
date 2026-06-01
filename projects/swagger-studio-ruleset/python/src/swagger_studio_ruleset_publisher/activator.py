"""Mark an uploaded Spectral ruleset as the org's active style guide.

`spectral:upload` saves a draft style guide; the SwaggerHub UI's "Publish"
button is what flips `spectralRulesets[].enabled` to `true` in the org's
standardization config. Without that flip, `/standardization` returns no
findings — the engine has no active ruleset to evaluate against.

Three-step flow (works around the field-naming asymmetry SwaggerHub uses):

  1. GET  /standardization/spectral-rulesets/{owner}
       -> array of {id, name, ...}.  Look up the UUID by `name`.
       (Retried with backoff — there's an indexing lag right after upload.)

  2. GET  /standardization/{owner}/config
       -> shallow form: spectralRulesets[] entries carry only
       `rulesetId` (the UUID from step 1) and `enabled`.

  3. POST /standardization/{owner}/config  (entire modified body)
       Find the entry whose `rulesetId` == lookup UUID, set
       `enabled = true`. If no entry exists yet (fresh org, never
       activated), add one.

Endpoints discovered by capturing the UI's network calls.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

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
    studio_url: str
    detail: str


async def activate(settings: Settings, ruleset_name: str) -> ActivationResult:
    """Look up the ruleset's UUID, flip enabled=true in the org config, persist."""
    owner = settings.swaggerhub_org

    async with _client(settings) as client:
        ruleset_id = await _lookup_ruleset_id(client, owner, ruleset_name)
        if ruleset_id is None:
            raise RulesetNotFoundError(
                f"Ruleset {ruleset_name!r} not found in /standardization/spectral-rulesets/{owner} "
                f"after {len(_LOOKUP_DELAYS_S)} attempts. Confirm the upload succeeded."
            )

        config_path = f"/standardization/{owner}/config"
        log.info("activate_get", path=config_path, ruleset_id=ruleset_id)
        get_resp = await client.get(config_path)
        get_resp.raise_for_status()
        config: dict[str, Any] = get_resp.json()

        _set_enabled_by_id(config, ruleset_id)

        log.info("activate_post", path=config_path, ruleset_id=ruleset_id)
        post_resp = await client.post(config_path, json=config)
        if post_resp.status_code >= 400:
            raise RuntimeError(
                f"Activation POST returned HTTP {post_resp.status_code}: "
                f"{post_resp.text.strip()}"
            )

    return ActivationResult(
        owner=owner,
        ruleset_name=ruleset_name,
        ruleset_id=ruleset_id,
        studio_url=f"https://app.swaggerhub.com/organizations/{owner}/governance",
        detail=f"HTTP {post_resp.status_code}",
    )


async def _lookup_ruleset_id(
    client: httpx.AsyncClient,
    owner: str,
    ruleset_name: str,
) -> str | None:
    """Find the ruleset's UUID by name. Retries to ride out upload-indexing lag."""
    path = f"/standardization/spectral-rulesets/{owner}"
    last_status: int | None = None
    for delay in _LOOKUP_DELAYS_S:
        if delay > 0:
            log.info("activate_lookup_retry", delay_s=delay, path=path)
            await asyncio.sleep(delay)
        else:
            log.info("activate_lookup", path=path)
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
    log.warning("activate_lookup_exhausted", last_status=last_status)
    return None


def _set_enabled_by_id(config: dict[str, Any], ruleset_id: str) -> None:
    """Set enabled=True for the entry matching `ruleset_id`. Adds one if missing.

    Mutates `config` in place. Always succeeds — the lookup happened earlier.
    """
    rulesets = config.get("spectralRulesets")
    if not isinstance(rulesets, list):
        rulesets = []
        config["spectralRulesets"] = rulesets

    for entry in rulesets:
        if isinstance(entry, dict) and entry.get("rulesetId") == ruleset_id:
            entry["enabled"] = True
            return

    rulesets.append({"rulesetId": ruleset_id, "enabled": True})


def _client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.swaggerhub_base_url,
        timeout=settings.publisher_request_timeout_s,
        headers={
            "Authorization": settings.swaggerhub_api_key.get_secret_value(),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "api-foundation-ruleset-publisher/0.1",
        },
    )
