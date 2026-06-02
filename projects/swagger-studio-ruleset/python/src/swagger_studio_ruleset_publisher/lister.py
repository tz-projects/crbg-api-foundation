"""List the org's Spectral rulesets with their enabled state.

Two endpoints, merged by UUID:

  GET /standardization/spectral-rulesets/{owner}
    -> [{id, name, ...}]  — every ruleset in the org

  GET /standardization/{owner}/config
    -> {spectralRulesets: [{rulesetId, enabled}]}  — which are enabled

A ruleset appears in the first endpoint as soon as it's uploaded. It only
appears in the second once activate has been called at least once. The
merge treats "not in config" as enabled=false (it isn't being evaluated).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from swagger_studio_ruleset_publisher._http import create_client
from swagger_studio_ruleset_publisher.config import Settings

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RulesetInfo:
    name: str
    ruleset_id: str
    enabled: bool


async def list_rulesets(settings: Settings) -> list[RulesetInfo]:
    """Return every ruleset in the org with its current enabled state."""
    owner = settings.swaggerhub_org

    async with create_client(settings) as client:
        rulesets_path = f"/standardization/spectral-rulesets/{owner}"
        config_path = f"/standardization/{owner}/config"

        log.info("list_get_rulesets", path=rulesets_path)
        rulesets_resp = await client.get(rulesets_path)
        rulesets_resp.raise_for_status()
        rulesets_raw = rulesets_resp.json()
        if not isinstance(rulesets_raw, list):
            raise RuntimeError(
                f"Expected list from {rulesets_path}, got {type(rulesets_raw).__name__}"
            )

        log.info("list_get_config", path=config_path)
        config_resp = await client.get(config_path)
        config_resp.raise_for_status()
        config = config_resp.json()

    enabled_by_id: dict[str, bool] = {}
    if isinstance(config, dict):
        cfg_rulesets = config.get("spectralRulesets")
        if isinstance(cfg_rulesets, list):
            for entry in cfg_rulesets:
                if isinstance(entry, dict):
                    rid = entry.get("rulesetId")
                    en = entry.get("enabled")
                    if isinstance(rid, str) and isinstance(en, bool):
                        enabled_by_id[rid] = en

    results: list[RulesetInfo] = []
    for entry in rulesets_raw:
        if not isinstance(entry, dict):
            continue
        rid = entry.get("id")
        name = entry.get("name")
        if not isinstance(rid, str) or not isinstance(name, str):
            continue
        results.append(
            RulesetInfo(
                name=name,
                ruleset_id=rid,
                enabled=enabled_by_id.get(rid, False),
            )
        )

    results.sort(key=lambda r: r.name)
    return results
