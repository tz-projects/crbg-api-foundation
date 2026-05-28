/**
 * SwaggerHub REST client.
 *
 * Thin typed wrapper over Node's native `fetch`. Owns auth, base URL,
 * timeouts, and concurrency control via p-limit. Anything that talks to
 * Studio goes through this class so retry/backoff/rate-limit policy lives
 * in exactly one place.
 */

import pLimit, { type LimitFunction } from "p-limit";

import type { Settings } from "./config.js";

export class SwaggerHubHttpError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: string,
    public readonly url: string,
  ) {
    super(`HTTP ${status} from ${url}`);
    this.name = "SwaggerHubHttpError";
  }
}

export class SwaggerHubClient {
  private readonly limit: LimitFunction;
  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;
  private readonly timeoutMs: number;

  constructor(settings: Settings) {
    this.limit = pLimit(settings.scannerConcurrency);
    this.baseUrl = settings.swaggerhubBaseUrl.replace(/\/$/, "");
    this.timeoutMs = settings.scannerRequestTimeoutMs;
    this.headers = {
      Authorization: settings.swaggerhubApiKey,
      Accept: "application/json",
      "User-Agent": "api-foundation-swagger-studio-scanner/0.1",
    };
  }

  async getJson<T>(path: string, params?: Record<string, string | number>): Promise<T> {
    return this.limit(async () => {
      const url = this.buildUrl(path, params);
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);
      try {
        const response = await fetch(url, { headers: this.headers, signal: controller.signal });
        if (!response.ok) {
          const body = await response.text();
          throw new SwaggerHubHttpError(response.status, body, url);
        }
        return (await response.json()) as T;
      } finally {
        clearTimeout(timer);
      }
    });
  }

  private buildUrl(path: string, params?: Record<string, string | number>): string {
    const url = new URL(`${this.baseUrl}${path.startsWith("/") ? path : `/${path}`}`);
    if (params) {
      for (const [key, value] of Object.entries(params)) {
        url.searchParams.set(key, String(value));
      }
    }
    return url.toString();
  }
}
