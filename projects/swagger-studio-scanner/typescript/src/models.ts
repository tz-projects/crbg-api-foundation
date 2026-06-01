/**
 * Zod schemas + inferred types for SwaggerHub payloads and internal results.
 *
 * Three concerns are kept separate so a change in one layer doesn't ripple
 * through the others:
 *
 *  - **Identity**     — `ApiRef`. What API is this (stable).
 *  - **Metadata**     — `ApiMeta`, `RulesetMeta`. Descriptive context, optional.
 *  - **Scan outcome** — `Finding`, `ApiScanResult`, `ScanReport`.
 *
 * Wire-shaped payloads come in via `parsers.ts`; this module is the typed
 * domain the rest of the pipeline consumes. Keeping the two layers separated
 * means a Studio response-shape change only touches the adapter.
 */

import { z } from "zod";

export const Severity = {
  Critical: "CRITICAL",
  Warning: "WARNING",
  Info: "INFO",
} as const;
export type Severity = (typeof Severity)[keyof typeof Severity];

export const ScanStatus = {
  Pass: "pass",
  Warn: "warn",
  Fail: "fail",
  Error: "error",
} as const;
export type ScanStatus = (typeof ScanStatus)[keyof typeof ScanStatus];

// --- Identity --------------------------------------------------------------

export const ApiRefSchema = z.object({
  owner: z.string(),
  name: z.string(),
  version: z.string(),
});
export type ApiRef = z.infer<typeof ApiRefSchema>;

export function apiRefSlug(ref: ApiRef): string {
  return `${ref.owner}/${ref.name}/${ref.version}`;
}

// --- Metadata --------------------------------------------------------------

/**
 * Descriptive metadata for one API version — every field optional.
 *
 * Recovered from the `properties` array of a SwaggerHub listing item
 * (`X-Created`, `X-Modified`, `X-Default`, `X-Published`). Reports degrade
 * gracefully when fields are absent, so the schema never invents values:
 * missing inputs map to `null`.
 */
export const ApiMetaSchema = z.object({
  createdAt: z.string().datetime().nullable().default(null),
  modifiedAt: z.string().datetime().nullable().default(null),
  isDefaultVersion: z.boolean().nullable().default(null),
  isPublished: z.boolean().nullable().default(null),
});
export type ApiMeta = z.infer<typeof ApiMetaSchema>;

export const RulesetMetaSchema = z.object({
  name: z.string().nullable().default(null),
  version: z.string().nullable().default(null),
});
export type RulesetMeta = z.infer<typeof RulesetMetaSchema>;

// --- Scan outcome ----------------------------------------------------------

/**
 * One governance finding from the `/standardization` endpoint.
 *
 * `rule` is the canonical rule id; `description` is the raw text as
 * returned by Studio; `message` is the human-readable portion after the
 * rule id has been split off (when extractable). All three are kept so
 * downstream consumers can pick the granularity they need.
 */
export const FindingSchema = z.object({
  rule: z.string(),
  severity: z.enum([Severity.Critical, Severity.Warning, Severity.Info]),
  description: z.string(),
  message: z.string().nullable().default(null),
  line: z.number().int().nullable().default(null),
  path: z.string().nullable().default(null),
});
export type Finding = z.infer<typeof FindingSchema>;

export const ApiScanResultSchema = z.object({
  api: ApiRefSchema,
  status: z.enum([ScanStatus.Pass, ScanStatus.Warn, ScanStatus.Fail, ScanStatus.Error]),
  findings: z.array(FindingSchema).default([]),
  error: z.string().nullable().default(null),
  scannedAt: z.string().datetime(),
  meta: ApiMetaSchema.default({
    createdAt: null,
    modifiedAt: null,
    isDefaultVersion: null,
    isPublished: null,
  }),
});
export type ApiScanResult = z.infer<typeof ApiScanResultSchema>;

export function criticalCount(result: ApiScanResult): number {
  return result.findings.filter((f) => f.severity === Severity.Critical).length;
}

export function warningCount(result: ApiScanResult): number {
  return result.findings.filter((f) => f.severity === Severity.Warning).length;
}

/** Bundle of identity + metadata as returned by the listing adapter. */
export const ListedApiSchema = z.object({
  ref: ApiRefSchema,
  meta: ApiMetaSchema,
});
export type ListedApi = z.infer<typeof ListedApiSchema>;

/** Scan-level aggregate: when it ran, against which ruleset, with what results. */
export const ScanReportSchema = z.object({
  scannedAt: z.string().datetime(),
  ruleset: RulesetMetaSchema.nullable().default(null),
  results: z.array(ApiScanResultSchema).default([]),
});
export type ScanReport = z.infer<typeof ScanReportSchema>;
