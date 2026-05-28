/**
 * Runtime configuration loaded from the sibling `.env` and process env.
 *
 * Centralizing config here keeps the rest of the code pure: handlers and
 * the HTTP client take a typed `Settings` object rather than reaching into
 * `process.env` themselves.
 */

import { config as loadDotenv } from "dotenv";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { z } from "zod";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// The .env lives one directory above (shared between python/ and typescript/).
const sharedEnvPath = resolve(__dirname, "..", "..", ".env");
loadDotenv({ path: sharedEnvPath, override: false });

const SettingsSchema = z.object({
  swaggerhubApiKey: z.string().min(1, "SWAGGERHUB_API_KEY is required"),
  swaggerhubOrg: z.string().min(1, "SWAGGERHUB_ORG is required"),
  swaggerhubBaseUrl: z.string().url().default("https://api.swaggerhub.com"),
  scannerConcurrency: z.coerce.number().int().min(1).max(64).default(8),
  scannerRequestTimeoutMs: z.coerce.number().positive().default(30_000),
  scannerLogLevel: z
    .enum(["fatal", "error", "warn", "info", "debug", "trace"])
    .default("info"),
});

export type Settings = z.infer<typeof SettingsSchema>;

export function loadSettings(): Settings {
  return SettingsSchema.parse({
    swaggerhubApiKey: process.env["SWAGGERHUB_API_KEY"],
    swaggerhubOrg: process.env["SWAGGERHUB_ORG"],
    swaggerhubBaseUrl: process.env["SWAGGERHUB_BASE_URL"],
    scannerConcurrency: process.env["SCANNER_CONCURRENCY"],
    scannerRequestTimeoutMs: process.env["SCANNER_REQUEST_TIMEOUT_S"]
      ? Number(process.env["SCANNER_REQUEST_TIMEOUT_S"]) * 1000
      : undefined,
    scannerLogLevel: process.env["SCANNER_LOG_LEVEL"]?.toLowerCase(),
  });
}
