"""Delete a Spectral ruleset from SwaggerHub Studio.

Two-step flow so the org config doesn't end up with a dangling rulesetId
pointing at a slot that no longer exists:

  1. (best-effort) Look up the UUID by name, GET /standardization/{owner}/config,
     remove the entry from spectralRulesets[], POST the config back.
     Skipped silently if the ruleset isn't in the config or the lookup fails.

  2. DELETE /standardization/spectral-rulesets/{owner}/{ruleset_name}
     -> 204 No Content on success.
     -> 404 Ruleset not found  (treated as success — idempotent).

Probed against the live API:
    PUT  create -> 200 {"id":"<uuid>"}
    DELETE      -> 204
    GET verify  -> 404
    DELETE x2   -> 404 {"message":"Ruleset not found"}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from swagger_studio_ruleset_publisher._http import create_client
from swagger_studio_ruleset_publisher.activator import (
    lookup_ruleset_id,
    remove_entry_by_id,
)
from swagger_studio_ruleset_publisher.config import Settings

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DeleteResult:
    owner: str
    ruleset_name: str
    ruleset_id: str | None
    config_entry_removed: bool
    deleted: bool  # False if the ruleset was already gone (404)
    detail: str


async def delete(settings: Settings, ruleset_name: str) -> DeleteResult:
    """Delete the ruleset from Studio, after removing its config entry."""
    owner = settings.swaggerhub_org
    delete_path = f"/standardization/spectral-rulesets/{owner}/{ruleset_name}"
    config_path = f"/standardization/{owner}/config"

    async with create_client(settings) as client:
        # Step 1: best-effort config cleanup. If the lookup fails (ruleset
        # already gone), skip — the DELETE below will return 404 cleanly.
        ruleset_id = await lookup_ruleset_id(client, owner, ruleset_name)
        config_entry_removed = False
        if ruleset_id is not None:
            log.info("delete_config_get", path=config_path, ruleset_id=ruleset_id)
            get_resp = await client.get(config_path)
            get_resp.raise_for_status()
            config: dict[str, Any] = get_resp.json()
            if remove_entry_by_id(config, ruleset_id):
                log.info("delete_config_post", path=config_path, ruleset_id=ruleset_id)
                post_resp = await client.post(
                    config_path, json=config, headers={"Content-Type": "application/json"}
                )
                if post_resp.status_code >= 400:
                    raise RuntimeError(
                        f"Removing config entry returned HTTP {post_resp.status_code}: "
                        f"{post_resp.text.strip()}"
                    )
                config_entry_removed = True
        else:
            log.info("delete_no_config_entry", ruleset_name=ruleset_name)

        # Step 2: delete the ruleset itself. 404 = already gone, treat as success.
        log.info("delete_ruleset", path=delete_path)
        del_resp = await client.delete(delete_path)
        if del_resp.status_code == 404:
            return DeleteResult(
                owner=owner,
                ruleset_name=ruleset_name,
                ruleset_id=ruleset_id,
                config_entry_removed=config_entry_removed,
                deleted=False,
                detail="ruleset was already absent (HTTP 404)",
            )
        if del_resp.status_code >= 400:
            raise RuntimeError(
                f"DELETE returned HTTP {del_resp.status_code}: {del_resp.text.strip()}"
            )

    return DeleteResult(
        owner=owner,
        ruleset_name=ruleset_name,
        ruleset_id=ruleset_id,
        config_entry_removed=config_entry_removed,
        deleted=True,
        detail=f"HTTP {del_resp.status_code}",
    )
