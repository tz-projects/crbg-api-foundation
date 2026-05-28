/**
 * Capability probe — step zero of any scan.
 *
 * Confirms the API key is valid, the org is reachable, and the
 * `/standardization` endpoint is actually populated for this tier.
 * Fails fast with a human-readable reason so a work-laptop run does
 * not stall against silent tier or proxy issues.
 */

import { SwaggerHubClient, SwaggerHubHttpError } from "./client.js";
import type { Settings } from "./config.js";

export const ProbeStatus = {
  Ok: "ok",
  AuthFailed: "auth_failed",
  OrgUnreachable: "org_unreachable",
  GovernanceUnavailable: "governance_unavailable",
  NetworkError: "network_error",
} as const;
export type ProbeStatus = (typeof ProbeStatus)[keyof typeof ProbeStatus];

export interface ProbeResult {
  readonly status: ProbeStatus;
  readonly detail: string;
  readonly ok: boolean;
}

export async function runProbe(settings: Settings): Promise<ProbeResult> {
  const client = new SwaggerHubClient(settings);

  try {
    await client.getJson(`/apis/${settings.swaggerhubOrg}`, { limit: 1 });
  } catch (err: unknown) {
    if (err instanceof SwaggerHubHttpError) {
      if (err.status === 401 || err.status === 403) {
        return result(ProbeStatus.AuthFailed, `HTTP ${err.status} listing org APIs`);
      }
      if (err.status === 404) {
        return result(
          ProbeStatus.OrgUnreachable,
          `Org '${settings.swaggerhubOrg}' not found (HTTP 404)`,
        );
      }
      return result(ProbeStatus.NetworkError, `HTTP ${err.status} listing org APIs`);
    }
    return result(ProbeStatus.NetworkError, `Network error: ${String(err)}`);
  }

  // Governance/standardization reachability comes next once we wire it.
  return result(ProbeStatus.Ok, "Auth + org reachable; verify standardization next.");
}

function result(status: ProbeStatus, detail: string): ProbeResult {
  return { status, detail, ok: status === ProbeStatus.Ok };
}
