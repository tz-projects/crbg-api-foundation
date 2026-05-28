import { describe, expect, it } from "vitest";

import { VERSION, Severity, ScanStatus } from "@/index.js";
import { apiRefSlug, type ApiRef } from "@/models.js";

describe("smoke", () => {
  it("exports a version string", () => {
    expect(VERSION).toMatch(/^\d+\.\d+\.\d+/);
  });

  it("formats an ApiRef slug", () => {
    const ref: ApiRef = { owner: "acme", name: "orders", version: "1.0.0" };
    expect(apiRefSlug(ref)).toBe("acme/orders/1.0.0");
  });

  it("exposes severity + status enums", () => {
    expect(Severity.Critical).toBe("CRITICAL");
    expect(ScanStatus.Pass).toBe("pass");
  });
});
