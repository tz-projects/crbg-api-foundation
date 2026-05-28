#!/usr/bin/env node
/**
 * Commander-based CLI surface.
 *
 * Two commands today:
 *   - `version` — print package version (sanity check the devcontainer wiring).
 *   - `probe`   — run the capability probe against the configured org.
 *
 * `scan` will be added once the report writers land.
 */

import { Command } from "commander";

import { loadSettings } from "./config.js";
import { createLogger } from "./logger.js";
import { runProbe } from "./probe.js";
import { VERSION } from "./index.js";

const program = new Command()
  .name("scanner")
  .description("Org-wide non-conformance scanner for SmartBear Swagger Studio.")
  .version(VERSION);

program
  .command("version")
  .description("Print the scanner version")
  .action(() => {
    process.stdout.write(`swagger-studio-scanner v${VERSION}\n`);
  });

program
  .command("probe")
  .description("Verify auth, org reachability, and governance availability")
  .action(async () => {
    const settings = loadSettings();
    const log = createLogger(settings.scannerLogLevel);
    const result = await runProbe(settings);
    log[result.ok ? "info" : "error"]({ status: result.status }, result.detail);
    process.exit(result.ok ? 0 : 1);
  });

await program.parseAsync(process.argv);
