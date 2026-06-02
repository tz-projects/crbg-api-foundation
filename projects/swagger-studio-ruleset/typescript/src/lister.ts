/**
 * List the org's Spectral rulesets with their enabled state.
 *
 * Two endpoints, merged by UUID:
 *
 *   GET /standardization/spectral-rulesets/{owner}
 *     -> [{id, name, ...}]
 *
 *   GET /standardization/{owner}/config
 *     -> {spectralRulesets: [{rulesetId, enabled}]}
 *
 * "Not in config" => enabled=false (it isn't being evaluated).
 */

import type { Settings } from "./config.js";
import { buildHeaders, studioBaseUrl, withTimeout } from "./_http.js";

export interface RulesetInfo {
  readonly name: string;
  readonly rulesetId: string;
  readonly enabled: boolean;
}

export async function listRulesets(settings: Settings): Promise<RulesetInfo[]> {
  const owner = settings.swaggerhubOrg;
  const baseUrl = studioBaseUrl(settings);
  const headers = buildHeaders(settings);

  return withTimeout(settings, async (signal) => {
    const rulesetsUrl = `${baseUrl}/standardization/spectral-rulesets/${owner}`;
    const configUrl = `${baseUrl}/standardization/${owner}/config`;

    const rulesetsResp = await fetch(rulesetsUrl, { method: "GET", headers, signal });
    if (!rulesetsResp.ok) {
      const body = await rulesetsResp.text();
      throw new Error(
        `GET rulesets returned HTTP ${String(rulesetsResp.status)}: ${body.trim()}`,
      );
    }
    const rulesetsRaw: unknown = await rulesetsResp.json();
    if (!Array.isArray(rulesetsRaw)) {
      throw new Error(
        `Expected list from ${rulesetsUrl}, got ${typeof rulesetsRaw}`,
      );
    }

    const configResp = await fetch(configUrl, { method: "GET", headers, signal });
    if (!configResp.ok) {
      const body = await configResp.text();
      throw new Error(
        `GET config returned HTTP ${String(configResp.status)}: ${body.trim()}`,
      );
    }
    const config = (await configResp.json()) as unknown;

    const enabledById = new Map<string, boolean>();
    if (isRecord(config)) {
      const cfgRulesets = config["spectralRulesets"];
      if (Array.isArray(cfgRulesets)) {
        for (const entry of cfgRulesets as unknown[]) {
          if (isRecord(entry)) {
            const rid = entry["rulesetId"];
            const en = entry["enabled"];
            if (typeof rid === "string" && typeof en === "boolean") {
              enabledById.set(rid, en);
            }
          }
        }
      }
    }

    const results: RulesetInfo[] = [];
    for (const entry of rulesetsRaw) {
      if (!isRecord(entry)) continue;
      const rid = entry["id"];
      const name = entry["name"];
      if (typeof rid !== "string" || typeof name !== "string") continue;
      results.push({
        name,
        rulesetId: rid,
        enabled: enabledById.get(rid) ?? false,
      });
    }
    results.sort((a, b) => a.name.localeCompare(b.name));
    return results;
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
