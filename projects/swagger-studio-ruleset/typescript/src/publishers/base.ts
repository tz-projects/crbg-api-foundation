/**
 * Publisher interface — every backend honors this surface.
 */

export const Backend = {
  Cli: "cli",
  Rest: "rest",
} as const;
export type Backend = (typeof Backend)[keyof typeof Backend];

export interface PublishResult {
  readonly rulesetSlug: string;
  readonly backend: Backend;
  readonly studioUrl: string;
  readonly detail: string;
  /**
   * Studio-assigned UUID for the slot. The REST backend reads it from the
   * upload response body (`{"id": "..."}`); the CLI backend leaves it
   * undefined because `swaggerhub spectral:upload` only emits a
   * human-formatted status line. When present, callers can pass it to
   * `activate(...)` to skip the name->UUID lookup.
   */
  readonly rulesetId?: string;
}

export interface Publisher {
  readonly backend: Backend;
  publish(rulesetDir: string, rulesetSlug: string): Promise<PublishResult>;
}
