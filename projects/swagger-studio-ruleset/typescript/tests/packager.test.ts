import { describe, expect, it } from "vitest";
import { mkdtempSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import * as YAML from "yaml";

import * as packager from "@/packager.js";

function seedRuleset(): string {
  const root = mkdtempSync(join(tmpdir(), "rs-"));
  const rs = join(root, "ruleset");
  mkdirSync(join(rs, "rules"), { recursive: true });
  writeFileSync(
    join(rs, "spectral.yaml"),
    "extends:\n  - ./rules/info.yaml\n  - ./rules/operations.yaml\n",
  );
  writeFileSync(
    join(rs, "rules", "info.yaml"),
    "rules:\n  info-contact:\n    severity: error\n    given: $.info\n    then:\n      field: contact\n      function: truthy\n",
  );
  writeFileSync(
    join(rs, "rules", "operations.yaml"),
    "rules:\n  operation-operationId:\n    severity: error\n    given: $.paths[*]\n    then:\n      field: operationId\n      function: truthy\n",
  );
  return rs;
}

describe("packager", () => {
  it("validate returns resolved path", async () => {
    const rs = seedRuleset();
    const out = await packager.validate(rs);
    expect(out).toMatch(/ruleset$/);
  });

  it("validate throws when entry point missing", async () => {
    const empty = mkdtempSync(join(tmpdir(), "rs-empty-"));
    await expect(packager.validate(empty)).rejects.toThrow(/spectral.yaml/);
  });

  it("flatten inlines rules from relative extends and drops them", async () => {
    const rs = seedRuleset();
    const merged = YAML.parse(await packager.flatten(rs)) as Record<string, unknown>;
    const rules = merged["rules"] as Record<string, unknown>;
    expect(rules).toHaveProperty("info-contact");
    expect(rules).toHaveProperty("operation-operationId");
    expect(merged).not.toHaveProperty("extends");
  });

  it("flatten keeps built-in extends like spectral:oas", async () => {
    const root = mkdtempSync(join(tmpdir(), "rs-"));
    const rs = join(root, "ruleset");
    mkdirSync(join(rs, "rules"), { recursive: true });
    writeFileSync(
      join(rs, "spectral.yaml"),
      "extends:\n  - spectral:oas\n  - ./rules/info.yaml\n",
    );
    writeFileSync(join(rs, "rules", "info.yaml"), "rules: {info-contact: {severity: error}}\n");

    const merged = YAML.parse(await packager.flatten(rs)) as Record<string, unknown>;
    expect(merged["extends"]).toEqual(["spectral:oas"]);
    expect((merged["rules"] as Record<string, unknown>)["info-contact"]).toBeDefined();
  });

  it("flatten — own rules win conflicts with inlined", async () => {
    const root = mkdtempSync(join(tmpdir(), "rs-"));
    const rs = join(root, "ruleset");
    mkdirSync(join(rs, "rules"), { recursive: true });
    writeFileSync(join(rs, "rules", "info.yaml"), "rules: {info-contact: {severity: warn}}\n");
    writeFileSync(
      join(rs, "spectral.yaml"),
      "extends: [./rules/info.yaml]\nrules:\n  info-contact: {severity: error}\n",
    );

    const merged = YAML.parse(await packager.flatten(rs)) as Record<string, unknown>;
    const rules = merged["rules"] as Record<string, unknown>;
    const contact = rules["info-contact"] as Record<string, unknown>;
    expect(contact["severity"]).toBe("error");
  });

  it("pkg writes a zip artifact at the requested path", async () => {
    const rs = seedRuleset();
    const zipDest = join(rs, "..", "bundle.zip");
    const bundle = await packager.pkg(rs, zipDest);
    expect(existsSync(bundle.zipPath)).toBe(true);
    packager.cleanup(bundle);
  });

  it("cleanup is idempotent", async () => {
    const rs = seedRuleset();
    const bundle = await packager.pkg(rs, join(rs, "..", "bundle.zip"));
    packager.cleanup(bundle);
    expect(() => {
      packager.cleanup(bundle);
    }).not.toThrow();
  });
});
