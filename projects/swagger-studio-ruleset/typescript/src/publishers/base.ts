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
}

export interface Publisher {
  readonly backend: Backend;
  publish(rulesetDir: string, rulesetSlug: string): Promise<PublishResult>;
}
