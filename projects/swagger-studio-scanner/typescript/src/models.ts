/**
 * Zod schemas + inferred types for SwaggerHub payloads and internal results.
 *
 * Wire-shaped schemas (`*PayloadSchema`) match the API; domain types
 * (`ApiRef`, `Finding`, `ApiScanResult`) are what consumers handle. Keeping
 * the two layers separated means an API shape change only touches the adapter.
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

export const ApiRefSchema = z.object({
  owner: z.string(),
  name: z.string(),
  version: z.string(),
});
export type ApiRef = z.infer<typeof ApiRefSchema>;

export function apiRefSlug(ref: ApiRef): string {
  return `${ref.owner}/${ref.name}/${ref.version}`;
}

export const FindingSchema = z.object({
  rule: z.string(),
  severity: z.enum([Severity.Critical, Severity.Warning, Severity.Info]),
  description: z.string(),
  line: z.number().int().nullable().optional(),
  path: z.string().nullable().optional(),
});
export type Finding = z.infer<typeof FindingSchema>;

export const ApiScanResultSchema = z.object({
  api: ApiRefSchema,
  status: z.enum([ScanStatus.Pass, ScanStatus.Warn, ScanStatus.Fail, ScanStatus.Error]),
  findings: z.array(FindingSchema).default([]),
  error: z.string().nullable().optional(),
  scannedAt: z.string().datetime(),
});
export type ApiScanResult = z.infer<typeof ApiScanResultSchema>;

export function criticalCount(result: ApiScanResult): number {
  return result.findings.filter((f) => f.severity === Severity.Critical).length;
}

export function warningCount(result: ApiScanResult): number {
  return result.findings.filter((f) => f.severity === Severity.Warning).length;
}
