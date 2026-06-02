/**
 * Delete a Spectral ruleset from SwaggerHub Studio.
 *
 * Two-step flow so the org config doesn't end up with a dangling
 * rulesetId pointing at a slot that no longer exists:
 *
 *   1. (best-effort) Look up the UUID by name, GET the org config,
 *      remove the entry from spectralRulesets[], POST it back.
 *      Skipped silently if the ruleset isn't in the config.
 *
 *   2. DELETE /standardization/spectral-rulesets/{owner}/{rulesetName}
 *      -> 204 No Content on success.
 *      -> 404 Not Found (idempotent — treat as success).
 */

import type { Settings } from "./config.js";
import { lookupRulesetId, removeEntryById } from "./activator.js";
import { buildHeaders, studioBaseUrl, withTimeout } from "./_http.js";

export interface DeleteResult {
  readonly owner: string;
  readonly rulesetName: string;
  readonly rulesetId: string | null;
  readonly configEntryRemoved: boolean;
  readonly deleted: boolean; // false if the slot was already absent (404)
  readonly detail: string;
}

export async function deleteRuleset(
  settings: Settings,
  rulesetName: string,
): Promise<DeleteResult> {
  const owner = settings.swaggerhubOrg;
  const baseUrl = studioBaseUrl(settings);
  const headers = buildHeaders(settings, { "Content-Type": "application/json" });
  const deleteUrl = `${baseUrl}/standardization/spectral-rulesets/${owner}/${rulesetName}`;
  const configUrl = `${baseUrl}/standardization/${owner}/config`;

  return withTimeout(settings, async (signal) => {
    // Step 1: best-effort config cleanup.
    const rulesetId = await lookupRulesetId(baseUrl, owner, rulesetName, headers, signal);
    let configEntryRemoved = false;
    if (rulesetId !== null) {
      const getResp = await fetch(configUrl, { method: "GET", headers, signal });
      if (!getResp.ok) {
        const body = await getResp.text();
        throw new Error(
          `GET config returned HTTP ${String(getResp.status)}: ${body.trim()}`,
        );
      }
      const config = (await getResp.json()) as Record<string, unknown>;
      if (removeEntryById(config, rulesetId)) {
        const postResp = await fetch(configUrl, {
          method: "POST",
          headers,
          body: JSON.stringify(config),
          signal,
        });
        if (!postResp.ok) {
          const body = await postResp.text();
          throw new Error(
            `Removing config entry returned HTTP ${String(postResp.status)}: ${body.trim()}`,
          );
        }
        configEntryRemoved = true;
      }
    }

    // Step 2: delete the ruleset itself.
    const delResp = await fetch(deleteUrl, { method: "DELETE", headers, signal });
    if (delResp.status === 404) {
      return {
        owner,
        rulesetName,
        rulesetId,
        configEntryRemoved,
        deleted: false,
        detail: "ruleset was already absent (HTTP 404)",
      };
    }
    if (!delResp.ok) {
      const body = await delResp.text();
      throw new Error(
        `DELETE returned HTTP ${String(delResp.status)}: ${body.trim()}`,
      );
    }

    return {
      owner,
      rulesetName,
      rulesetId,
      configEntryRemoved,
      deleted: true,
      detail: `HTTP ${String(delResp.status)}`,
    };
  });
}
