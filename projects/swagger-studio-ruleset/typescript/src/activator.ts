/**
 * Mark an uploaded Spectral ruleset as the org's active style guide.
 *
 * Three-step flow (works around the field-naming asymmetry SwaggerHub uses):
 *
 *   1. GET  /standardization/spectral-rulesets/{owner}
 *        -> array of {id, name, ...}. Look up the UUID by `name`.
 *        (Retried with backoff — there's an indexing lag right after upload.)
 *
 *   2. GET  /standardization/{owner}/config
 *        -> shallow form: spectralRulesets[] entries carry only
 *        `rulesetId` (the UUID from step 1) and `enabled`.
 *
 *   3. POST /standardization/{owner}/config  (entire modified body)
 *        Find the entry whose `rulesetId` === lookup UUID, set
 *        `enabled = true`. If no entry exists yet, add one.
 */

import type { Settings } from "./config.js";

export interface ActivationResult {
  readonly owner: string;
  readonly rulesetName: string;
  readonly rulesetId: string;
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

export async function activate(settings: Settings, rulesetName: string): Promise<ActivationResult> {
  const owner = settings.swaggerhubOrg;
  const baseUrl = settings.swaggerhubBaseUrl.replace(/\/$/, "");
  const headers: Record<string, string> = {
    Authorization: settings.swaggerhubApiKey,
    Accept: "application/json",
    "Content-Type": "application/json",
    "User-Agent": "api-foundation-ruleset-publisher/0.1",
  };

  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort();
  }, settings.publisherRequestTimeoutMs);

  try {
    const rulesetId = await lookupRulesetId(baseUrl, owner, rulesetName, headers, controller.signal);
    if (rulesetId === null) {
      throw new RulesetNotFoundError(
        `Ruleset '${rulesetName}' not found in /standardization/spectral-rulesets/${owner} ` +
          `after ${String(LOOKUP_DELAYS_MS.length)} attempts. Confirm the upload succeeded.`,
      );
    }

    const configUrl = `${baseUrl}/standardization/${owner}/config`;

    const getResp = await fetch(configUrl, { method: "GET", headers, signal: controller.signal });
    if (!getResp.ok) {
      const body = await getResp.text();
      throw new Error(`GET config returned HTTP ${String(getResp.status)}: ${body.trim()}`);
    }
    const config = (await getResp.json()) as Record<string, unknown>;

    setEnabledById(config, rulesetId);

    const postResp = await fetch(configUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(config),
      signal: controller.signal,
    });
    if (!postResp.ok) {
      const body = await postResp.text();
      throw new Error(`POST config returned HTTP ${String(postResp.status)}: ${body.trim()}`);
    }

    return {
      owner,
      rulesetName,
      rulesetId,
      studioUrl: `https://app.swaggerhub.com/organizations/${owner}/governance`,
      detail: `HTTP ${String(postResp.status)}`,
    };
  } finally {
    clearTimeout(timer);
  }
}

async function lookupRulesetId(
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

/** Exported for unit testing. */
export function setEnabledById(config: Record<string, unknown>, rulesetId: string): void {
  let rulesets = config["spectralRulesets"];
  if (!Array.isArray(rulesets)) {
    rulesets = [];
    config["spectralRulesets"] = rulesets;
  }
  const arr = rulesets as unknown[];
  for (const entry of arr) {
    if (isRecord(entry) && entry["rulesetId"] === rulesetId) {
      entry["enabled"] = true;
      return;
    }
  }
  arr.push({ rulesetId, enabled: true });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
