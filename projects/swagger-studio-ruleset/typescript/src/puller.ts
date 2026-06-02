/**
 * Download a ruleset's current contents from SwaggerHub Studio to disk.
 *
 *   GET /standardization/spectral-rulesets/{owner}/{rulesetName}/zip
 *     Accept: application/zip
 *     -> 200 + raw zip bytes (single-entry `spectral.yaml`)
 *     -> 404 if the ruleset doesn't exist
 *
 * Inverse of upload. Used for drift detection (diff against repo) and
 * bootstrapping (seed a new repo from Studio's existing rules).
 */

import AdmZip from "adm-zip";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve, sep } from "node:path";

import type { Settings } from "./config.js";
import { buildHeaders, studioBaseUrl, withTimeout } from "./_http.js";

export class RulesetNotInStudioError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RulesetNotInStudioError";
  }
}

export interface PullResult {
  readonly owner: string;
  readonly rulesetName: string;
  readonly destDir: string;
  readonly filesWritten: readonly string[];
  readonly bytesReceived: number;
}

export async function pull(
  settings: Settings,
  rulesetName: string,
  destDir: string,
): Promise<PullResult> {
  const owner = settings.swaggerhubOrg;
  const baseUrl = studioBaseUrl(settings);
  const headers = buildHeaders(settings, { Accept: "application/zip" });
  const url = `${baseUrl}/standardization/spectral-rulesets/${owner}/${rulesetName}/zip`;
  const resolvedDest = resolve(destDir);
  await mkdir(resolvedDest, { recursive: true });

  return withTimeout(settings, async (signal) => {
    const resp = await fetch(url, { method: "GET", headers, signal });
    if (resp.status === 404) {
      throw new RulesetNotInStudioError(
        `Ruleset '${owner}/${rulesetName}' not found in Studio (HTTP 404).`,
      );
    }
    if (!resp.ok) {
      const body = await resp.text();
      throw new Error(`Pull returned HTTP ${String(resp.status)}: ${body.trim()}`);
    }

    const zipBuf = Buffer.from(await resp.arrayBuffer());
    const zip = new AdmZip(zipBuf);
    const written: string[] = [];
    for (const entry of zip.getEntries()) {
      if (entry.isDirectory) continue;
      // Zip-slip guard.
      const target = resolve(resolvedDest, entry.entryName);
      if (!target.startsWith(resolvedDest + sep) && target !== resolvedDest) {
        throw new Error(`Refusing zip entry outside dest: ${entry.entryName}`);
      }
      await mkdir(dirname(target), { recursive: true });
      await writeFile(target, entry.getData());
      written.push(target);
    }

    return {
      owner,
      rulesetName,
      destDir: resolvedDest,
      filesWritten: written,
      bytesReceived: zipBuf.length,
    };
  });
}
