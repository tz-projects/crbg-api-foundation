/**
 * Shared HTTP helpers — every Studio-touching module uses the same headers,
 * base URL, and timeout machinery. Centralizing keeps drift out of the
 * activator/deleter/lister/puller surfaces.
 */

import type { Settings } from "./config.js";

export function studioBaseUrl(settings: Settings): string {
  return settings.swaggerhubBaseUrl.replace(/\/$/, "");
}

export function buildHeaders(
  settings: Settings,
  overrides: Record<string, string> = {},
): Record<string, string> {
  return {
    Authorization: settings.swaggerhubApiKey,
    Accept: "application/json",
    "User-Agent": "api-foundation-ruleset-publisher/0.1",
    ...overrides,
  };
}

/**
 * Run `fn` against a fetch that aborts after the configured timeout.
 * Always clears the timer so it doesn't keep the event loop alive.
 */
export async function withTimeout<T>(
  settings: Settings,
  fn: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => {
    controller.abort();
  }, settings.publisherRequestTimeoutMs);
  try {
    return await fn(controller.signal);
  } finally {
    clearTimeout(timer);
  }
}
