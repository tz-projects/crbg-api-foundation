/**
 * CLI backend — shells out to `swaggerhub spectral:upload`.
 *
 * Reliable default. Requires swaggerhub-cli on PATH (installed in the
 * devcontainer). For environments without it, use the REST backend.
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";

import * as packager from "../packager.js";
import type { Settings } from "../config.js";
import { Backend, type Publisher, type PublishResult } from "./base.js";

const execFileAsync = promisify(execFile);

export class CliPublisher implements Publisher {
  readonly backend = Backend.Cli;

  constructor(private readonly settings: Settings) {}

  async publish(rulesetDir: string, rulesetSlug: string): Promise<PublishResult> {
    const resolved = await packager.validate(rulesetDir);

    if (!(await packager.hasSwaggerhubCli())) {
      throw new Error(
        "swaggerhub-cli not on PATH. " +
          "Install via `npm i -g swaggerhub-cli` or use --backend rest.",
      );
    }

    // Flatten extends before handing off — Studio shouldn't have to resolve
    // relative `./rules/*.yaml` references. Same artifact REST backend ships.
    const flattenedDir = await packager.writeFlattenedDir(resolved);

    const env: NodeJS.ProcessEnv = {
      ...process.env,
      SWAGGERHUB_API_KEY: this.settings.swaggerhubApiKey,
    };

    let stdout = "";
    try {
      const result = await execFileAsync(
        "swaggerhub",
        ["spectral:upload", rulesetSlug, flattenedDir],
        { env },
      );
      stdout = result.stdout.trim();
    } catch (err: unknown) {
      const e = err as { stderr?: string; stdout?: string; code?: number };
      throw new Error(
        `swaggerhub spectral:upload failed (exit ${String(e.code ?? "?")}):\n` +
          ((e.stderr?.trim() || e.stdout?.trim()) ?? "no output"),
      );
    } finally {
      const { rm } = await import("node:fs/promises");
      await rm(flattenedDir, { recursive: true, force: true }).catch(() => {
        // best-effort cleanup
      });
    }

    const [owner, name] = splitSlug(rulesetSlug);
    return {
      rulesetSlug,
      backend: Backend.Cli,
      studioUrl: `https://app.swaggerhub.com/standardization/${owner}/${name}`,
      detail: stdout || "uploaded",
    };
  }
}

function splitSlug(slug: string): [string, string] {
  const idx = slug.indexOf("/");
  if (idx === -1) return [slug, slug];
  return [slug.slice(0, idx), slug.slice(idx + 1)];
}
