/**
 * Bundle a ruleset directory for upload.
 *
 * The on-disk layout is modular: `spectral.yaml` extends individual
 * `rules/*.yaml` category files for clean editing and review. Before upload
 * we flatten everything into a single self-contained `spectral.yaml` so
 * Studio doesn't have to resolve relative `./rules/*.yaml` references.
 *
 * Built-in extends like `spectral:oas` are left in place — those refer to
 * Spectral's own bundled rulesets and resolve at runtime regardless.
 */

import archiver from "archiver";
import { createWriteStream, existsSync, mkdtempSync, statSync, unlinkSync, writeFileSync } from "node:fs";
import { access, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import * as YAML from "yaml";

export interface RulesetBundle {
  readonly directory: string;
  readonly zipPath: string;
}

export async function validate(directory: string): Promise<string> {
  const resolved = resolve(directory);
  if (!existsSync(resolved) || !statSync(resolved).isDirectory()) {
    throw new Error(`Ruleset directory not found: ${resolved}`);
  }
  const entry = join(resolved, "spectral.yaml");
  if (!existsSync(entry)) {
    throw new Error(
      `Ruleset entry point not found: ${entry}\n` +
        "Every ruleset must declare a top-level spectral.yaml.",
    );
  }
  return resolved;
}

/**
 * Resolve all relative `extends: ./...yaml` references inline and return the
 * merged YAML content. Built-in extends (e.g. `spectral:oas`) are kept.
 * Own `rules:` in the entry file always wins conflicts.
 */
export async function flatten(directory: string): Promise<string> {
  const resolved = await validate(directory);
  const main = (YAML.parse(await readFile(join(resolved, "spectral.yaml"), "utf-8")) ?? {}) as Record<
    string,
    unknown
  >;

  const mergedRules: Record<string, unknown> = {};
  const runtimeExtends: unknown[] = [];

  const rawExtends = normalizeArray(main["extends"]);
  for (const entry of rawExtends) {
    if (isRelativeFileRef(entry)) {
      const subPath = resolve(resolved, entry);
      const sub = (YAML.parse(await readFile(subPath, "utf-8")) ?? {}) as Record<string, unknown>;
      const subRules = sub["rules"];
      if (isRecord(subRules)) {
        Object.assign(mergedRules, subRules);
      }
    } else {
      runtimeExtends.push(entry);
    }
  }

  const ownRules = main["rules"];
  if (isRecord(ownRules)) {
    Object.assign(mergedRules, ownRules);
  }

  const output: Record<string, unknown> = {};
  if (runtimeExtends.length > 0) {
    output["extends"] = runtimeExtends;
  }
  if (Object.keys(mergedRules).length > 0) {
    output["rules"] = mergedRules;
  }
  return YAML.stringify(output);
}

/**
 * Materialize the flattened ruleset to a temp directory containing a single
 * `spectral.yaml`. Caller is responsible for cleanup.
 */
export async function writeFlattenedDir(directory: string): Promise<string> {
  const merged = await flatten(directory);
  const tmp = mkdtempSync(join(tmpdir(), "ruleset-flat-"));
  writeFileSync(join(tmp, "spectral.yaml"), merged, "utf-8");
  return tmp;
}

/**
 * Validate, flatten, and write a single-file ZIP at `zipDest`. The ZIP
 * contains exactly one file (`spectral.yaml`) with rules inlined.
 */
export async function pkg(directory: string, zipDest: string): Promise<RulesetBundle> {
  const resolved = await validate(directory);
  const merged = await flatten(resolved);

  if (existsSync(zipDest)) {
    unlinkSync(zipDest);
  } else {
    await access(dirname(zipDest)).catch(async () => {
      const { mkdir } = await import("node:fs/promises");
      await mkdir(dirname(zipDest), { recursive: true });
    });
  }

  await new Promise<void>((res, rej) => {
    const output = createWriteStream(zipDest);
    const archive = archiver("zip", { zlib: { level: 9 } });
    output.on("close", () => {
      res();
    });
    archive.on("error", (err) => {
      rej(err);
    });
    archive.pipe(output);
    archive.append(merged, { name: "spectral.yaml" });
    void archive.finalize();
  });

  return { directory: resolved, zipPath: resolve(zipDest) };
}

export function cleanup(bundle: RulesetBundle): void {
  try {
    if (existsSync(bundle.zipPath)) {
      unlinkSync(bundle.zipPath);
    }
  } catch {
    // best-effort cleanup
  }
}

export function tempZipPath(directory: string): string {
  const resolved = resolve(directory);
  const parent = dirname(resolved);
  const name = resolved.split("/").pop() ?? "ruleset";
  return join(parent, `.${name}.bundle.zip`);
}

export async function hasSwaggerhubCli(): Promise<boolean> {
  const { execFile } = await import("node:child_process");
  return new Promise<boolean>((res) => {
    execFile("swaggerhub", ["--version"], (err) => {
      res(err === null);
    });
  });
}

// --- helpers -----------------------------------------------------------

function normalizeArray(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (value == null) return [];
  return [value];
}

function isRelativeFileRef(entry: unknown): entry is string {
  if (typeof entry !== "string") return false;
  return entry.startsWith("./") || entry.startsWith("../") || entry.endsWith(".yaml") || entry.endsWith(".yml");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
