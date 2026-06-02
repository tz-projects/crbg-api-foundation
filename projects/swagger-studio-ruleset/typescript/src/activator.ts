/**
 * Mark an uploaded Spectral ruleset as the org's active style guide —
 * or revoke that mark.
 *
 * Flow (works around SwaggerHub's field-naming asymmetry — upload addresses
 * rulesets by name, the org config addresses them by UUID):
 *
 *   1. (skippable) GET /standardization/spectral-rulesets/{owner}
 *        -> array of {id, name, ...}. Look up the UUID by `name`.
 *        Retried with backoff to ride out the post-upload indexing lag.
 *        SKIPPED when the caller already has the UUID.
 *
 *   2. GET  /standardization/{owner}/config
 *        -> spectralRulesets[] entries carry {rulesetId, enabled}.
 *
 *   3. POST /standardization/{owner}/config  (entire modified body)
 *        For activate: flip enabled=true, append if missing.
 *        For deactivate: flip enabled=false; if no entry, no-op.
 */

import type { Settings } from "./config.js";
import { buildHeaders, studioBaseUrl, withTimeout } from "./_http.js";

export interface ActivationResult {
  readonly owner: string;
  readonly rulesetName: string;
  readonly rulesetId: string;
  readonly enabled: boolean;
  readonly studioUrl: string;
  readonly detail: string;
}

export class RulesetNotFoundError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RulesetNotFoundError";
  }
}

const LOOKUP_DELAYS_MS = [0, 2_000, 5_000] as const;

export async function activate(
  settings: Settings,
  rulesetName: string,
  knownRulesetId?: string,
): Promise<ActivationResult> {
  return setState(settings, rulesetName, true, knownRulesetId);
}

export async function deactivate(
  settings: Settings,
  rulesetName: string,
  knownRulesetId?: string,
): Promise<ActivationResult> {
  return setState(settings, rulesetName, false, knownRulesetId);
}

async function setState(
  settings: Settings,
  rulesetName: string,
  enabled: boolean,
  knownRulesetId?: string,
): Promise<ActivationResult> {
  const owner = settings.swaggerhubOrg;
  const baseUrl = studioBaseUrl(settings);
  const headers = buildHeaders(settings, { "Content-Type": "application/json" });

  return withTimeout(settings, async (signal) => {
    let rulesetId: string | null;
    if (knownRulesetId !== undefined && knownRulesetId.length > 0) {
      rulesetId = knownRulesetId;
    } else {
      rulesetId = await lookupRulesetId(baseUrl, owner, rulesetName, headers, signal);
      if (rulesetId === null) {
        throw new RulesetNotFoundError(
          `Ruleset '${rulesetName}' not found in /standardization/spectral-rulesets/${owner} ` +
            `after ${String(LOOKUP_DELAYS_MS.length)} attempts.`,
        );
      }
    }

    const configUrl = `${baseUrl}/standardization/${owner}/config`;

    const getResp = await fetch(configUrl, { method: "GET", headers, signal });
    if (!getResp.ok) {
      const body = await getResp.text();
      throw new Error(`GET config returned HTTP ${String(getResp.status)}: ${body.trim()}`);
    }
    const config = (await getResp.json()) as Record<string, unknown>;

    const changed = setEnabledById(config, rulesetId, enabled);
    if (!changed) {
      // Deactivating something not in the config — no-op.
      return {
        owner,
        rulesetName,
        rulesetId,
        enabled: false,
        studioUrl: `https://app.swaggerhub.com/organizations/${owner}/governance`,
        detail: "no-op (entry not present in config)",
      };
    }

    const postResp = await fetch(configUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(config),
      signal,
    });
    if (!postResp.ok) {
      const body = await postResp.text();
      throw new Error(`POST config returned HTTP ${String(postResp.status)}: ${body.trim()}`);
    }

    return {
      owner,
      rulesetName,
      rulesetId,
      enabled,
      studioUrl: `https://app.swaggerhub.com/organizations/${owner}/governance`,
      detail: `HTTP ${String(postResp.status)}`,
    };
  });
}

/**
 * Look up the ruleset's UUID by name. Retries to ride out upload-indexing lag.
 * Exported so deleter and other modules can reuse.
 */
export async function lookupRulesetId(
  baseUrl: string,
  owner: string,
  rulesetName: string,
  headers: Record<string, string>,
  signal: AbortSignal,
): Promise<string | null> {
  const url = `${baseUrl}/standardization/spectral-rulesets/${owner}`;
  for (const delay of LOOKUP_DELAYS_MS) {
    if (delay > 0) {
      await new Promise<void>((res) => setTimeout(res, delay));
    }
    const resp = await fetch(url, { method: "GET", headers, signal });
    if (!resp.ok) continue;
    const data: unknown = await resp.json();
    if (!Array.isArray(data)) continue;
    for (const entry of data) {
      if (isRecord(entry) && entry["name"] === rulesetName) {
        const id = entry["id"];
        if (typeof id === "string" && id.length > 0) {
          return id;
        }
      }
    }
  }
  return null;
}

/**
 * Set the entry's `enabled` flag. Returns true if the config was modified.
 *
 * Backward-compatible: defaults to `enabled=true` so existing call sites
 * (and tests) keep working. For deactivate semantics (`enabled=false`),
 * a missing entry yields `false` — there's nothing to disable, and creating
 * a disabled entry would be pointless noise in the config.
 */
export function setEnabledById(
  config: Record<string, unknown>,
  rulesetId: string,
  enabled = true,
): boolean {
  let rulesets = config["spectralRulesets"];
  if (!Array.isArray(rulesets)) {
    if (!enabled) return false;
    rulesets = [];
    config["spectralRulesets"] = rulesets;
  }
  const arr = rulesets as unknown[];
  for (const entry of arr) {
    if (isRecord(entry) && entry["rulesetId"] === rulesetId) {
      entry["enabled"] = enabled;
      return true;
    }
  }
  if (!enabled) return false;
  arr.push({ rulesetId, enabled: true });
  return true;
}

/**
 * Drop the spectralRulesets[] entry for `rulesetId`. Returns true if removed.
 * Used by the deleter after a successful DELETE so we don't leave a
 * dangling rulesetId in the config.
 */
export function removeEntryById(config: Record<string, unknown>, rulesetId: string): boolean {
  const rulesets = config["spectralRulesets"];
  if (!Array.isArray(rulesets)) return false;
  const arr = rulesets as unknown[];
  const next = arr.filter(
    (e) => !(isRecord(e) && e["rulesetId"] === rulesetId),
  );
  if (next.length === arr.length) return false;
  config["spectralRulesets"] = next;
  return true;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
