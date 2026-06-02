#!/usr/bin/env node
/**
 * Commander CLI for the publisher.
 *
 * Commands:
 *   - version     — print version
 *   - publish     — upload ruleset/ and activate it (create or update)
 *   - deactivate  — flip enabled=false for a slot, keep its content
 *   - delete      — remove the slot from Studio entirely
 *   - list        — show every ruleset in the org with its enabled state
 *   - pull        — download a slot's current content to disk
 */

import { Command, Option } from "commander";
import { createInterface } from "node:readline/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

import {
  activate,
  deactivate,
  RulesetNotFoundError,
} from "./activator.js";
import { loadSettings } from "./config.js";
import { deleteRuleset } from "./deleter.js";
import { listRulesets } from "./lister.js";
import { createLogger } from "./logger.js";
import { Backend, type Publisher } from "./publishers/base.js";
import { CliPublisher } from "./publishers/cliPublisher.js";
import { RestPublisher } from "./publishers/restPublisher.js";
import { pull, RulesetNotInStudioError } from "./puller.js";
import { VERSION } from "./index.js";

// Per context doc §3 — Studio scans against this fixed-name slot for the
// OAS hygiene guide. A second guide (OWASP) is published under its own slot;
// both can be active simultaneously because Studio's `spectralRulesets[]`
// config keeps a per-entry `enabled` flag.
const DEFAULT_RULESET_NAME = "openapi-3-0-active";

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
  .description("Publish the ruleset to {owner}/{name} and activate it")
  .option("-r, --ruleset <path>", "Directory containing spectral.yaml", DEFAULT_RULESET_DIR)
  .option(
    "-n, --name <name>",
    "Studio style-guide slot to publish into (e.g. openapi-3-0-active, owasp-top-10-active)",
    DEFAULT_RULESET_NAME,
  )
  .addOption(
    new Option("-b, --backend <backend>", "Upload mechanism")
      .choices([Backend.Cli, Backend.Rest])
      .default(Backend.Cli),
  )
  .option("--no-activate", "Upload as a draft; skip the activation step.")
  .action(
    async (opts: { ruleset: string; name: string; backend: Backend; activate: boolean }) => {
      const settings = loadSettings();
      const log = createLogger(settings.publisherLogLevel);

      const rulesetSlug = `${settings.swaggerhubOrg}/${opts.name}`;
      const publisher: Publisher =
        opts.backend === Backend.Cli ? new CliPublisher(settings) : new RestPublisher(settings);

      log.info({ slug: rulesetSlug, backend: opts.backend }, "publishing");

      let uploadedRulesetId: string | undefined;
      try {
        const upload = await publisher.publish(opts.ruleset, rulesetSlug);
        uploadedRulesetId = upload.rulesetId;
        log.info(
          { slug: upload.rulesetSlug, url: upload.studioUrl, id: upload.rulesetId },
          "uploaded",
        );
        process.stdout.write(`Uploaded ${upload.rulesetSlug}\n`);
        process.stdout.write(`  detail: ${upload.detail}\n`);
        if (upload.rulesetId !== undefined) {
          process.stdout.write(`  id:     ${upload.rulesetId}\n`);
        }
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
        const act = await activate(settings, opts.name, uploadedRulesetId);
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

program
  .command("deactivate")
  .description("Flip enabled=false for {owner}/{name}. Keeps content in Studio.")
  .requiredOption("-n, --name <name>", "Studio style-guide slot to deactivate")
  .action(async (opts: { name: string }) => {
    const settings = loadSettings();
    const log = createLogger(settings.publisherLogLevel);
    try {
      const result = await deactivate(settings, opts.name);
      log.info({ slug: `${result.owner}/${result.rulesetName}` }, "deactivated");
      const verb = result.enabled === false ? "Deactivated" : "No change";
      process.stdout.write(`${verb} ${result.owner}/${result.rulesetName}\n`);
      process.stdout.write(`  detail: ${result.detail}\n`);
      process.stdout.write(`  open:   ${result.studioUrl}\n`);
    } catch (err: unknown) {
      const code = err instanceof RulesetNotFoundError ? 3 : 1;
      const message = err instanceof Error ? err.message : String(err);
      log.error({ err: message }, "deactivate_failed");
      process.exitCode = code;
    }
  });

program
  .command("delete")
  .description("Remove {owner}/{name} from Studio entirely (config + ruleset)")
  .requiredOption("-n, --name <name>", "Studio style-guide slot to delete")
  .option("-y, --yes", "Skip confirmation prompt (required for non-TTY use)")
  .action(async (opts: { name: string; yes?: boolean }) => {
    const settings = loadSettings();
    const log = createLogger(settings.publisherLogLevel);
    const slug = `${settings.swaggerhubOrg}/${opts.name}`;

    if (opts.yes !== true) {
      const rl = createInterface({ input: process.stdin, output: process.stdout });
      const answer = await rl.question(`Delete ${slug}? This cannot be undone. [y/N] `);
      rl.close();
      if (!/^y(es)?$/i.test(answer.trim())) {
        process.stdout.write("Aborted.\n");
        return;
      }
    }

    try {
      const result = await deleteRuleset(settings, opts.name);
      log.info({ slug, deleted: result.deleted }, "deleted");
      if (result.deleted) {
        process.stdout.write(`Deleted ${result.owner}/${result.rulesetName}\n`);
      } else {
        process.stdout.write(`Already absent ${result.owner}/${result.rulesetName}\n`);
      }
      process.stdout.write(`  detail:         ${result.detail}\n`);
      process.stdout.write(`  config cleaned: ${String(result.configEntryRemoved)}\n`);
      if (result.rulesetId !== null) {
        process.stdout.write(`  id:             ${result.rulesetId}\n`);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      log.error({ err: message }, "delete_failed");
      process.exitCode = 1;
    }
  });

program
  .command("list")
  .description("Show every ruleset in the org with its enabled state")
  .action(async () => {
    const settings = loadSettings();
    const log = createLogger(settings.publisherLogLevel);
    try {
      const rulesets = await listRulesets(settings);
      log.info({ count: rulesets.length }, "listed");
      if (rulesets.length === 0) {
        process.stdout.write(`No rulesets found for ${settings.swaggerhubOrg}.\n`);
        return;
      }
      const nameWidth = Math.max(4, ...rulesets.map((r) => r.name.length));
      process.stdout.write(
        `${"NAME".padEnd(nameWidth)}  ENABLED  UUID\n`,
      );
      for (const r of rulesets) {
        process.stdout.write(
          `${r.name.padEnd(nameWidth)}  ${r.enabled ? "yes    " : "no     "}  ${r.rulesetId}\n`,
        );
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      log.error({ err: message }, "list_failed");
      process.exitCode = 1;
    }
  });

program
  .command("pull")
  .description("Download {owner}/{name}'s current zip from Studio into DEST")
  .requiredOption("-n, --name <name>", "Studio style-guide slot to pull")
  .requiredOption("-d, --dest <path>", "Destination directory (created if missing)")
  .action(async (opts: { name: string; dest: string }) => {
    const settings = loadSettings();
    const log = createLogger(settings.publisherLogLevel);
    try {
      const result = await pull(settings, opts.name, opts.dest);
      log.info(
        { slug: `${result.owner}/${result.rulesetName}`, dest: result.destDir },
        "pulled",
      );
      process.stdout.write(
        `Pulled ${result.owner}/${result.rulesetName} ` +
          `(${String(result.bytesReceived)} bytes)\n`,
      );
      for (const fp of result.filesWritten) {
        process.stdout.write(`  wrote: ${fp}\n`);
      }
    } catch (err: unknown) {
      const code = err instanceof RulesetNotInStudioError ? 3 : 1;
      const message = err instanceof Error ? err.message : String(err);
      log.error({ err: message }, "pull_failed");
      process.exitCode = code;
    }
  });

await program.parseAsync(process.argv);
