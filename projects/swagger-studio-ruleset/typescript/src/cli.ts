#!/usr/bin/env node
/**
 * Commander CLI for the publisher.
 *
 * Commands:
 *   - version  — print version
 *   - publish  — push ruleset/ to Studio under {owner}/openapi-3-0-active
 *               and (by default) mark it as the org's active style guide
 */

import { Command, Option } from "commander";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

import { activate, RulesetNotFoundError } from "./activator.js";
import { loadSettings } from "./config.js";
import { createLogger } from "./logger.js";
import { Backend, type Publisher } from "./publishers/base.js";
import { CliPublisher } from "./publishers/cliPublisher.js";
import { RestPublisher } from "./publishers/restPublisher.js";
import { VERSION } from "./index.js";

// Per context doc §3 — Studio scans against this fixed-name slot.
const ACTIVE_RULESET_NAME = "openapi-3-0-active";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const DEFAULT_RULESET_DIR = resolve(__dirname, "..", "..", "ruleset");

const program = new Command()
  .name("ruleset-publisher")
  .description("Publishes the API Foundation Spectral ruleset to SwaggerHub Studio.")
  .version(VERSION);

program
  .command("version")
  .description("Print the publisher version")
  .action(() => {
    process.stdout.write(`swagger-studio-ruleset-publisher v${VERSION}\n`);
  });

program
  .command("publish")
  .description("Publish the ruleset to {owner}/openapi-3-0-active and activate it")
  .option("-r, --ruleset <path>", "Directory containing spectral.yaml", DEFAULT_RULESET_DIR)
  .addOption(
    new Option("-b, --backend <backend>", "Upload mechanism")
      .choices([Backend.Cli, Backend.Rest])
      .default(Backend.Cli),
  )
  .option("--no-activate", "Upload as a draft; skip the activation step.")
  .action(
    async (opts: { ruleset: string; backend: Backend; activate: boolean }) => {
      const settings = loadSettings();
      const log = createLogger(settings.publisherLogLevel);

      const rulesetSlug = `${settings.swaggerhubOrg}/${ACTIVE_RULESET_NAME}`;
      const publisher: Publisher =
        opts.backend === Backend.Cli ? new CliPublisher(settings) : new RestPublisher(settings);

      log.info({ slug: rulesetSlug, backend: opts.backend }, "publishing");

      try {
        const upload = await publisher.publish(opts.ruleset, rulesetSlug);
        log.info({ slug: upload.rulesetSlug, url: upload.studioUrl }, "uploaded");
        process.stdout.write(`Uploaded ${upload.rulesetSlug}\n`);
        process.stdout.write(`  detail: ${upload.detail}\n`);
        process.stdout.write(`  open:   ${upload.studioUrl}\n`);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : String(err);
        log.error({ err: message }, "upload_failed");
        process.exitCode = 1;
        return;
      }

      if (!opts.activate) {
        process.stdout.write("Skipping activation (--no-activate).\n");
        return;
      }

      try {
        const act = await activate(settings, ACTIVE_RULESET_NAME);
        log.info({ owner: act.owner, ruleset: act.rulesetName, url: act.studioUrl }, "activated");
        process.stdout.write(`Activated ${act.owner}/${act.rulesetName}\n`);
        process.stdout.write(`  detail: ${act.detail}\n`);
        process.stdout.write(`  open:   ${act.studioUrl}\n`);
      } catch (err: unknown) {
        const code = err instanceof RulesetNotFoundError ? 3 : 1;
        const message = err instanceof Error ? err.message : String(err);
        log.error({ err: message }, "activate_failed");
        process.exitCode = code;
      }
    },
  );

await program.parseAsync(process.argv);
