import { describe, expect, it } from "vitest";

import { setEnabledById } from "@/activator.js";

describe("setEnabledById", () => {
  it("flips matching entry by rulesetId", () => {
    const config: Record<string, unknown> = {
      spectralRulesets: [
        { rulesetId: "abc-123", enabled: false },
        { rulesetId: "xyz-999", enabled: false },
      ],
    };
    setEnabledById(config, "abc-123");
    const arr = config["spectralRulesets"] as { rulesetId: string; enabled: boolean }[];
    expect(arr[0]!.enabled).toBe(true);
    expect(arr[1]!.enabled).toBe(false);
  });

  it("adds entry when id missing from existing array", () => {
    const config: Record<string, unknown> = { spectralRulesets: [] };
    setEnabledById(config, "new-id");
    expect(config["spectralRulesets"]).toEqual([{ rulesetId: "new-id", enabled: true }]);
  });

  it("creates array when key missing entirely", () => {
    const config: Record<string, unknown> = {};
    setEnabledById(config, "id-1");
    expect(config["spectralRulesets"]).toEqual([{ rulesetId: "id-1", enabled: true }]);
  });

  it("creates array when key present but not a list", () => {
    const config: Record<string, unknown> = { spectralRulesets: null };
    setEnabledById(config, "id-1");
    expect(config["spectralRulesets"]).toEqual([{ rulesetId: "id-1", enabled: true }]);
  });

  it("is idempotent on already-enabled", () => {
    const config: Record<string, unknown> = {
      spectralRulesets: [{ rulesetId: "id-1", enabled: true }],
    };
    setEnabledById(config, "id-1");
    const arr = config["spectralRulesets"] as { rulesetId: string; enabled: boolean }[];
    expect(arr.length).toBe(1);
    expect(arr[0]!.enabled).toBe(true);
  });

  it("skips non-object entries", () => {
    const config: Record<string, unknown> = {
      spectralRulesets: ["not-a-record", { rulesetId: "abc-123", enabled: false }],
    };
    setEnabledById(config, "abc-123");
    const arr = config["spectralRulesets"] as unknown[];
    expect((arr[1] as { enabled: boolean }).enabled).toBe(true);
  });
});
