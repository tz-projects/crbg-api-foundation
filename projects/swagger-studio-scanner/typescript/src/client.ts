/**
 * SwaggerHub REST client.
 *
 * Thin typed wrapper over Node's native `fetch`. Single responsibility:
 * own auth, base URL, timeouts, and concurrency, and expose a typed
 * surface for the endpoints the scanner needs. All payload interpretation
 * lives in `parsers.ts` — that separation keeps the wire-shape grammar in
 * one place and lets us unit-test adapters without a network.
 *
 * Three high-level operations:
 *
 *  - `listApiVersions`   — async-iterates `{ ref, meta }` for every API
 *                           version under an org.
 *  - `getFindings`       — fetches + parses standardization findings for
 *                           one API version, using the injected
 *                           `FindingParser`.
 *  - `getActiveRuleset`  — returns the active org ruleset, or `null` when
 *                           the endpoint is unavailable / unrecognized.
 */

import pLimit, { type LimitFunction } from "p-limit";

import type { Settings } from "./config.js";
import type {
  ApiRef,
  Finding,
  ListedApi,
  RulesetMeta,
} from "./models.js";
import {
  DEFAULT_FINDING_PARSER,
  extractApiItems,
  extractApiMeta,
  extractApiRef,
  parseRulesetPayload,
  type FindingParser,
} from "./parsers.js";

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
  private static readonly PAGE_SIZE = 100;

  private readonly limit: LimitFunction;
  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;
  private readonly timeoutMs: number;
  private readonly findingParser: FindingParser;

  constructor(settings: Settings, findingParser: FindingParser = DEFAULT_FINDING_PARSER) {
    this.limit = pLimit(settings.scannerConcurrency);
    this.baseUrl = settings.swaggerhubBaseUrl.replace(/\/$/, "");
    this.timeoutMs = settings.scannerRequestTimeoutMs;
    this.findingParser = findingParser;
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

  // --- High-level operations ----------------------------------------------

  /** Yield identity + metadata for every API version under `owner`. */
  async *listApiVersions(owner: string): AsyncIterableIterator<ListedApi> {
    let page = 0;
    while (true) {
      const data = await this.getJson<unknown>(`/apis/${owner}`, {
        page,
        limit: SwaggerHubClient.PAGE_SIZE,
      });
      const items = extractApiItems(data);
      if (items.length === 0) return;
      for (const item of items) {
        const ref = extractApiRef(item);
        if (ref) yield { ref, meta: extractApiMeta(item) };
      }
      if (items.length < SwaggerHubClient.PAGE_SIZE) return;
      page += 1;
    }
  }

  /**
   * Fetch and parse standardization findings for one API version.
   *
   * Empty result can mean *clean* OR *tier doesn't include Governance* —
   * callers decide what to do with empty results, based on the probe outcome.
   */
  async getFindings(api: ApiRef): Promise<Finding[]> {
    const path = `/apis/${api.owner}/${api.name}/${api.version}/standardization`;
    const data = await this.getJson<Record<string, unknown>>(path);
    const raw =
      (data["validation"] as unknown) ??
      (data["standardization"] as unknown) ??
      (data["findings"] as unknown) ??
      [];
    if (!Array.isArray(raw)) return [];
    return raw.map((e) => this.findingParser.parse(e));
  }

  /**
   * Return the active org standardization ruleset, or `null` on miss.
   *
   * The endpoint shape is not officially documented; this is best-effort and
   * intentionally swallows HTTP errors (including 404). A scan must not
   * fail because ruleset metadata is unavailable.
   */
  async getActiveRuleset(owner: string): Promise<RulesetMeta | null> {
    try {
      const data = await this.getJson<unknown>(`/orgs/${owner}/standardization`);
      return parseRulesetPayload(data);
    } catch (err: unknown) {
      if (err instanceof SwaggerHubHttpError) return null;
      throw err;
    }
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
