/**
 * Adapters that translate raw SwaggerHub payloads into typed domain models.
 *
 * Why a separate module: the SRP boundary between *talking to the API*
 * (`client.ts`) and *interpreting the API's payloads* is real. Wire shapes
 * evolve independently of HTTP concerns and unit-testing the adapters
 * requires no network. SwaggerHub also encodes several distinct facts —
 * API identity, age, default-version flag, published flag — inside one
 * generic `properties` array; one module owns that deserialization grammar.
 *
 * Public surface:
 *
 *  - Listing : `extractApiItems`, `extractApiRef`, `extractApiMeta`, `parseSwaggerUrl`.
 *  - Ruleset : `parseRulesetPayload`.
 *  - Finding : `FindingParser` interface, `DescriptionPrefixFindingParser`
 *              (default), `DEFAULT_FINDING_PARSER`, `parseFinding`.
 *
 * All functions are total: malformed input yields a sensible default
 * (`null` / empty array / parser fallback) rather than throwing. Callers
 * decide what to do with absences; the parsers never invent values.
 */

import {
  type ApiMeta,
  type ApiRef,
  type Finding,
  type RulesetMeta,
  Severity,
} from "./models.js";

// --- Listing payload -------------------------------------------------------

export function extractApiItems(payload: unknown): Record<string, unknown>[] {
  if (!isRecord(payload)) return [];
  for (const key of ["apis", "items"] as const) {
    const items = payload[key];
    if (Array.isArray(items)) return items.filter(isRecord);
  }
  return [];
}

/**
 * Recover `(owner, name, version)` from a listing item's Swagger URL.
 *
 * The canonical resource URL lives in the property whose `type` is
 * `Swagger`. The top-level `name` on a listing item is OpenAPI
 * `info.title` and must NOT be used as the slug.
 */
export function extractApiRef(item: unknown): ApiRef | null {
  if (!isRecord(item)) return null;
  const url = findProperty(item, "Swagger", "url");
  return typeof url === "string" ? parseSwaggerUrl(url) : null;
}

/**
 * Recover descriptive metadata from a listing item's `properties` array.
 *
 * Missing properties yield `null`; the report layer decides how to surface
 * absent data.
 */
export function extractApiMeta(item: unknown): ApiMeta {
  if (!isRecord(item)) return blankMeta();
  return {
    createdAt: toIsoString(findProperty(item, "X-Created", "value")),
    modifiedAt: toIsoString(findProperty(item, "X-Modified", "value")),
    isDefaultVersion: toBool(findProperty(item, "X-Default", "value")),
    isPublished: toBool(findProperty(item, "X-Published", "value")),
  };
}

/**
 * Extract `(owner, name, version)` from a SwaggerHub canonical URL.
 *
 * Accepts absolute (`https://api.swaggerhub.com/apis/...`) and relative
 * (`apis/...`) forms. Returns `null` for any URL that doesn't have the
 * `/apis/{owner}/{name}/{version}` shape — including the empty string.
 */
export function parseSwaggerUrl(url: string): ApiRef | null {
  if (!url) return null;
  let tail: string;
  if (url.includes("/apis/")) {
    tail = url.split("/apis/")[1] ?? "";
  } else if (url.startsWith("apis/")) {
    tail = url.slice("apis/".length);
  } else {
    return null;
  }
  const parts = tail.replace(/^\/+|\/+$/g, "").split("/");
  if (parts.length < 3 || parts.slice(0, 3).some((p) => !p)) return null;
  const [owner, name, version] = parts as [string, string, string];
  return { owner, name, version };
}

// --- Ruleset payload -------------------------------------------------------

/**
 * Pick the active ruleset name/version out of a `/standardization` payload.
 *
 * Endpoint shape isn't officially documented; we accept a small set of
 * known keys. Returns `null` when nothing recognizable is present —
 * callers treat "no active ruleset" identically to "we couldn't tell."
 */
export function parseRulesetPayload(payload: unknown): RulesetMeta | null {
  if (!isRecord(payload)) return null;
  const name = firstString(payload, "name", "ruleset", "rulesetName", "active");
  const version = firstString(payload, "version", "rulesetVersion");
  if (name === null && version === null) return null;
  return { name, version };
}

// --- Finding parsing -------------------------------------------------------

const DESCRIPTION_PREFIX_RE = /^([A-Za-z0-9][A-Za-z0-9_-]*)\s*->\s*(.+)$/;

/**
 * Strategy for normalizing a raw finding entry.
 *
 * OCP boundary: swap in a different parser when Studio changes its finding
 * shape, without touching `client.ts` or callers. The client accepts a
 * `FindingParser` in its constructor; the default is the description-prefix
 * parser.
 */
export interface FindingParser {
  parse(entry: unknown): Finding;
}

/**
 * Default parser: recover the rule id from `description = '<rule-id> -> <message>'`.
 *
 * SwaggerHub's `/standardization` response uses `description` as the only
 * carrier of the rule id in current deployments; the per-finding `rule`
 * field comes back as the literal string "unknown". We split when needed
 * and keep the original `description` intact so any consumer still
 * depending on the raw text continues to work.
 */
export class DescriptionPrefixFindingParser implements FindingParser {
  parse(entry: unknown): Finding {
    const e = isRecord(entry) ? entry : {};
    const description = String(e["description"] ?? e["message"] ?? "");
    const rawRule = String(e["rule"] ?? e["ruleId"] ?? "").trim();
    const { ruleId, message } = this.split(rawRule, description);
    return {
      rule: ruleId,
      severity: toSeverity(e["severity"]),
      description,
      message,
      line: typeof e["line"] === "number" ? e["line"] : null,
      path: typeof e["path"] === "string" ? e["path"] : null,
    };
  }

  private split(
    rawRule: string,
    description: string,
  ): { ruleId: string; message: string | null } {
    if (rawRule && rawRule.toLowerCase() !== "unknown") {
      return { ruleId: rawRule, message: description || null };
    }
    const m = description.trim().match(DESCRIPTION_PREFIX_RE);
    if (m) {
      return { ruleId: m[1] ?? "unknown", message: (m[2] ?? "").trim() || null };
    }
    return { ruleId: rawRule || "unknown", message: description || null };
  }
}

export const DEFAULT_FINDING_PARSER: FindingParser = new DescriptionPrefixFindingParser();

export function parseFinding(
  entry: unknown,
  parser: FindingParser = DEFAULT_FINDING_PARSER,
): Finding {
  return parser.parse(entry);
}

// --- Helpers ---------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function findProperty(
  item: Record<string, unknown>,
  type: string,
  key: string,
): unknown {
  const props = item["properties"];
  if (!Array.isArray(props)) return null;
  for (const p of props) {
    if (isRecord(p) && p["type"] === type) return p[key] ?? null;
  }
  return null;
}

function firstString(payload: Record<string, unknown>, ...keys: string[]): string | null {
  for (const k of keys) {
    const v = payload[k];
    if (typeof v === "string" && v) return v;
  }
  return null;
}

function toIsoString(value: unknown): string | null {
  if (typeof value !== "string" || !value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

function toBool(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    const v = value.trim().toLowerCase();
    if (v === "true" || v === "1" || v === "yes") return true;
    if (v === "false" || v === "0" || v === "no") return false;
  }
  return null;
}

function toSeverity(value: unknown): Severity {
  const s = String(value ?? "INFO").toUpperCase();
  if (s === Severity.Critical || s === Severity.Warning || s === Severity.Info) {
    return s as Severity;
  }
  return Severity.Info;
}

function blankMeta(): ApiMeta {
  return {
    createdAt: null,
    modifiedAt: null,
    isDefaultVersion: null,
    isPublished: null,
  };
}
