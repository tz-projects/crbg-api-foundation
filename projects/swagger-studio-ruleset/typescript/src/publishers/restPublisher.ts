/**
 * REST backend — direct HTTPS to the SwaggerHub Standardization API.
 *
 * Endpoint mirrored from swaggerhub-cli's `saveSpectralRuleset` helper
 * (`src/requests/spectral.js`):
 *
 *     PUT  /standardization/spectral-rulesets/{owner}/{rulesetName}/zip
 *     Content-Type: application/zip
 *     body: raw zip bytes (no multipart)
 */

import { readFile } from "node:fs/promises";

import * as packager from "../packager.js";
import type { Settings } from "../config.js";
import { Backend, type Publisher, type PublishResult } from "./base.js";

export class RestPublisher implements Publisher {
  readonly backend = Backend.Rest;

  constructor(private readonly settings: Settings) {}

  async publish(rulesetDir: string, rulesetSlug: string): Promise<PublishResult> {
    const resolved = await packager.validate(rulesetDir);
    const zipPath = packager.tempZipPath(resolved);
    const bundle = await packager.pkg(resolved, zipPath);

    try {
      const [owner, name] = splitSlug(rulesetSlug);
      const url =
        `${this.settings.swaggerhubBaseUrl.replace(/\/$/, "")}` +
        `/standardization/spectral-rulesets/${owner}/${name}/zip`;
      const zipBuffer = await readFile(bundle.zipPath);

      const controller = new AbortController();
      const timer = setTimeout(() => {
        controller.abort();
      }, this.settings.publisherRequestTimeoutMs);

      let response: Response;
      try {
        response = await fetch(url, {
          method: "PUT",
          headers: {
            Authorization: this.settings.swaggerhubApiKey,
            "Content-Type": "application/zip",
            Accept: "application/json",
            "User-Agent": "api-foundation-ruleset-publisher/0.1",
          },
          body: zipBuffer,
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timer);
      }

      if (!response.ok) {
        const body = await response.text();
        throw new Error(`SwaggerHub returned HTTP ${String(response.status)}: ${body.trim()}`);
      }

      return {
        rulesetSlug,
        backend: Backend.Rest,
        studioUrl: `https://app.swaggerhub.com/standardization/${owner}/${name}`,
        detail: `HTTP ${String(response.status)}`,
      };
    } finally {
      packager.cleanup(bundle);
    }
  }
}

function splitSlug(slug: string): [string, string] {
  const idx = slug.indexOf("/");
  if (idx === -1) return [slug, slug];
  return [slug.slice(0, idx), slug.slice(idx + 1)];
}
