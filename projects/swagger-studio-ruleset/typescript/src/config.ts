/**
 * Runtime configuration.
 *
 * Reuses the scanner's shared `.env` so both sub-projects pull credentials
 * from one place.
 */

import { config as loadDotenv } from "dotenv";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { z } from "zod";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// .../projects/swagger-studio-ruleset/typescript/src/config.ts -> repo root is 4 levels up
const sharedEnvPath = resolve(
  __dirname,
  "..",
  "..",
  "..",
  "swagger-studio-scanner",
  ".env",
);
loadDotenv({ path: sharedEnvPath, override: false });

const SettingsSchema = z.object({
  swaggerhubApiKey: z.string().min(1, "SWAGGERHUB_API_KEY is required"),
  swaggerhubOrg: z.string().min(1, "SWAGGERHUB_ORG is required"),
  swaggerhubBaseUrl: z.string().url().default("https://api.swaggerhub.com"),
  publisherRequestTimeoutMs: z.coerce.number().positive().default(30_000),
  publisherLogLevel: z
    .enum(["fatal", "error", "warn", "info", "debug", "trace"])
    .default("info"),
});

export type Settings = z.infer<typeof SettingsSchema>;

export function loadSettings(): Settings {
  return SettingsSchema.parse({
    swaggerhubApiKey: process.env["SWAGGERHUB_API_KEY"],
    swaggerhubOrg: process.env["SWAGGERHUB_ORG"],
    swaggerhubBaseUrl: process.env["SWAGGERHUB_BASE_URL"],
    publisherRequestTimeoutMs: process.env["PUBLISHER_REQUEST_TIMEOUT_S"]
      ? Number(process.env["PUBLISHER_REQUEST_TIMEOUT_S"]) * 1000
      : undefined,
    publisherLogLevel: process.env["PUBLISHER_LOG_LEVEL"]?.toLowerCase(),
  });
}
