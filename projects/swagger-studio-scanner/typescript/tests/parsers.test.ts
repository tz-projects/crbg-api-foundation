import { describe, expect, it } from "vitest";

import {
  DEFAULT_FINDING_PARSER,
  DescriptionPrefixFindingParser,
  extractApiItems,
  extractApiMeta,
  extractApiRef,
  parseFinding,
  parseRulesetPayload,
  parseSwaggerUrl,
} from "@/parsers.js";
import { Severity, type Finding } from "@/models.js";

// --- parseSwaggerUrl / extractApiRef ---------------------------------------

describe("parseSwaggerUrl", () => {
  it("accepts absolute SwaggerHub URLs", () => {
    expect(
      parseSwaggerUrl("https://api.swaggerhub.com/apis/sparklayerinc/scanner-bad-petstore/1.0.0"),
    ).toEqual({ owner: "sparklayerinc", name: "scanner-bad-petstore", version: "1.0.0" });
  });

  it("accepts relative apis/... URLs", () => {
    expect(parseSwaggerUrl("apis/acme/orders/2.1.0")).toEqual({
      owner: "acme",
      name: "orders",
      version: "2.1.0",
    });
  });

  it("rejects unrecognized shapes", () => {
    expect(parseSwaggerUrl("https://example.com/whatever")).toBeNull();
    expect(parseSwaggerUrl("apis/owner")).toBeNull();
    expect(parseSwaggerUrl("")).toBeNull();
  });
});

describe("extractApiRef", () => {
  it("uses the Swagger property URL, not info.title", () => {
    const item = {
      name: "Scanner Good Petstore", // info.title — distractor
      properties: [
        {
          type: "Swagger",
          url: "https://api.swaggerhub.com/apis/sparklayerinc/scanner-good-petstore/1.0.0",
        },
        { type: "X-Version", value: "1.0.0" },
        { type: "X-Versions", value: "-1.0.0" },
      ],
    };
    expect(extractApiRef(item)).toEqual({
      owner: "sparklayerinc",
      name: "scanner-good-petstore",
      version: "1.0.0",
    });
  });

  it("returns null when no Swagger property is present", () => {
    expect(
      extractApiRef({ name: "x", properties: [{ type: "X-Version", value: "1.0.0" }] }),
    ).toBeNull();
  });
});

// --- extractApiItems --------------------------------------------------------

describe("extractApiItems", () => {
  it("finds apis key", () => {
    expect(extractApiItems({ apis: [{ name: "x" }, { name: "y" }] })).toHaveLength(2);
  });

  it("handles missing apis key", () => {
    expect(extractApiItems({ totalCount: 0 })).toEqual([]);
  });
});

// --- extractApiMeta ---------------------------------------------------------

describe("extractApiMeta", () => {
  it("reads ISO timestamps and boolean flags", () => {
    const meta = extractApiMeta({
      properties: [
        { type: "X-Created", value: "2025-08-13T10:21:00Z" },
        { type: "X-Modified", value: "2026-01-04T11:00:00+00:00" },
        { type: "X-Default", value: "true" },
        { type: "X-Published", value: "false" },
      ],
    });
    expect(meta.createdAt).toBe("2025-08-13T10:21:00.000Z");
    expect(meta.modifiedAt).toBe("2026-01-04T11:00:00.000Z");
    expect(meta.isDefaultVersion).toBe(true);
    expect(meta.isPublished).toBe(false);
  });

  it("returns all-null when properties are missing", () => {
    const meta = extractApiMeta({ properties: [{ type: "X-Version", value: "1.0" }] });
    expect(meta).toEqual({
      createdAt: null,
      modifiedAt: null,
      isDefaultVersion: null,
      isPublished: null,
    });
  });

  it("is robust to a garbage timestamp", () => {
    const meta = extractApiMeta({ properties: [{ type: "X-Created", value: "yesterday" }] });
    expect(meta.createdAt).toBeNull();
  });
});

// --- parseRulesetPayload ----------------------------------------------------

describe("parseRulesetPayload", () => {
  it("returns null for unrecognized payloads", () => {
    expect(parseRulesetPayload(null)).toBeNull();
    expect(parseRulesetPayload({})).toBeNull();
    expect(parseRulesetPayload({ unrelated: "data" })).toBeNull();
  });

  it("picks known keys", () => {
    expect(parseRulesetPayload({ name: "openapi-3-0-active", version: "1.4.0" })).toEqual({
      name: "openapi-3-0-active",
      version: "1.4.0",
    });
  });

  it("accepts partial payloads", () => {
    expect(parseRulesetPayload({ ruleset: "house-style" })).toEqual({
      name: "house-style",
      version: null,
    });
  });
});

// --- FindingParser strategy ------------------------------------------------

describe("DescriptionPrefixFindingParser", () => {
  it("splits rule id from a 'rule-id -> message' description", () => {
    const f = parseFinding({
      rule: "unknown",
      severity: "CRITICAL",
      description: "info-contact -> info.contact is required",
      line: 1,
    });
    expect(f.rule).toBe("info-contact");
    expect(f.message).toBe("info.contact is required");
    expect(f.severity).toBe(Severity.Critical);
    // raw description preserved for backward-compat consumers
    expect(f.description).toBe("info-contact -> info.contact is required");
    expect(f.line).toBe(1);
  });

  it("prefers an explicit rule field over parsing description", () => {
    const f = parseFinding({
      rule: "oas3-schema",
      severity: "WARNING",
      description: "human readable thing",
    });
    expect(f.rule).toBe("oas3-schema");
    expect(f.message).toBe("human readable thing");
  });

  it("falls back when description has no arrow", () => {
    const f = parseFinding({ rule: "", severity: "INFO", description: "no arrow here" });
    expect(f.rule).toBe("unknown");
    expect(f.message).toBe("no arrow here");
  });

  it("coerces unknown severity to INFO", () => {
    const f = parseFinding({ rule: "r", severity: "EXTREME", description: "x" });
    expect(f.severity).toBe(Severity.Info);
  });

  it("is swappable — custom parsers can be injected (OCP)", () => {
    class StaticParser {
      parse(): Finding {
        return {
          rule: "static",
          severity: Severity.Info,
          description: "x",
          message: null,
          line: null,
          path: null,
        };
      }
    }
    const f = parseFinding(
      { rule: "r", severity: "CRITICAL", description: "y" },
      new StaticParser(),
    );
    expect(f.rule).toBe("static");
    // Sanity: default parser path is unchanged.
    expect(DEFAULT_FINDING_PARSER).toBeInstanceOf(DescriptionPrefixFindingParser);
  });
});
