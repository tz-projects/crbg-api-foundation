# Reports — Generating the executive and platform team HTML

Two reports are generated from a scan: one for the CIO (the **executive report**) and one for the platform team to socialize with app dev teams (the **platform team report**). Both consume the scanner's `scan.json` — no re-scan is required.

The report generators live in `projects/reports/`. They are **standard-library Python** by design: any Python ≥3.10 can run them, no `uv`/venv required, the only optional dependency is PyYAML for nested ownership maps.

For the data-source design (Tier 1 / Tier 2 / Tier 3) the reports implement, see [`projects/reports/governance-reports-spec-v2.md`](../projects/reports/governance-reports-spec-v2.md).

---

## 1. Quick run (Tier 1 only — Studio data alone)

After a successful scan (`uv run scanner scan`):

```bash
cd /workspaces/crbg-api-foundation/projects/reports
SCAN=/workspaces/crbg-api-foundation/projects/swagger-studio-scanner/python/output/scan.json

# Executive (CIO-facing, single page)
python3 generate_executive_report.py \
  --input "$SCAN" \
  --output output/executive-report.html \
  --org-display-name "Acme Corporation" \
  --placeholder-ask

# Platform team (dense reference + filterable findings table + CSV)
python3 generate_platform_report.py \
  --input "$SCAN" \
  --output-dir output/platform-report \
  --org-display-name "Acme Corporation" \
  --studio-base-url https://app.swaggerhub.com/apis
```

This produces (everything self-contained, no external assets):

```
projects/reports/output/
├── executive-report.html
└── platform-report/
    ├── index.html
    ├── findings.csv
    └── per-team/             # only when --ownership-map is provided
```

Each command prints a tier-status summary to stdout — useful for confirming what rendered and what fell back to a Tier 1 substitute. Read that first to know what the report contains before sending it.

---

## 2. Optional inputs that enrich the reports

The report generators accept four optional inputs. Each adds a layer of context without changing the contract: a missing input is acknowledged in the report and the relevant section degrades gracefully (a Tier 1 substitute renders instead — never a blank section).

| Flag (both generators unless noted) | Input | What it lights up |
|---|---|---|
| `--ownership-map ownership.yaml` | Tier 2: API → team / domain / contact / repo | Headline "teams represented" tile, "Where the work sits" table, per-team summary, per-team subset reports, team column + filter in the findings table, orphan vs. mapped distinction |
| `--rule-display-names rule_display_names.yaml` | Tier 3: rule id → humanized name | Humanized Pareto labels in the executive report, friendlier rule reference cards in the platform report |
| `--cop-guidance cop_guidance.yaml` | Tier 3: rule id → CoP wiki URL | Real CoP links on rule cards and the findings table (replaces "guidance pending") |
| `--asks-file asks.md` *(executive only)* | Tier 3: the "What's needed" paragraph | Replaces the visible placeholder in the executive report |

### File formats

**`ownership.yaml`** — keys are matched in order: `owner/name/version` → `owner/name` → `name`. PyYAML required for nested maps (`pip install pyyaml`).

```yaml
sparklayerinc/scanner-bad-petstore/1.0.0:
  team: payments
  domain: commerce
  contact_email: payments-leads@acme.example.com
  repo_url: https://git.acme.example.com/payments/scanner-bad-petstore

sparklayerinc/ledger:                          # applies to every ledger version
  team: finance
  domain: commerce
  contact_email: finance-leads@acme.example.com
```

**`rule_display_names.yaml`** — flat. No PyYAML required (the bundled fallback parser handles flat key: value).

```yaml
info-contact: Contact info missing from API description
info-license: License missing from API description
operation-operationId: Operations missing operationId
operation-summary: Operations missing summary
operation-tags: Operations missing tags
response-success-content: 2xx responses missing content
response-description: Response descriptions missing or too short
```

**`cop_guidance.yaml`** — flat. No PyYAML required.

```yaml
info-contact: https://confluence.acme.example.com/cop/rules/info-contact
info-license: https://confluence.acme.example.com/cop/rules/info-license
operation-operationId: https://confluence.acme.example.com/cop/rules/operation-operationId
```

**`asks.md`** — plain prose, embedded verbatim as the "What's needed" paragraph in the executive report. Don't write the heading; the report adds it.

```markdown
The platform team will drive remediation through phased CI/CD enforcement: strict
governance gating on new APIs from Q3, exception-aware enforcement on existing
APIs as they are modified, and a Center of Practice publishing remediation
guidance against the top failing rules. Successful execution requires executive
endorsement of the gating milestone and one dedicated remediation engineer per
top-3 failing domain.
```

These four files are **gitignored by default** because they typically carry org-internal information (team emails, internal wiki URLs, the CIO ask wording). Track them in a private location or, if they're safe to commit, force-add with `git add -f`.

---

## 3. Full run with all inputs

```bash
cd /workspaces/crbg-api-foundation/projects/reports
SCAN=/workspaces/crbg-api-foundation/projects/swagger-studio-scanner/python/output/scan.json

python3 generate_executive_report.py \
  --input "$SCAN" \
  --output output/executive-report.html \
  --org-display-name "Acme Corporation" \
  --ownership-map ownership.yaml \
  --rule-display-names rule_display_names.yaml \
  --asks-file asks.md

python3 generate_platform_report.py \
  --input "$SCAN" \
  --output-dir output/platform-report \
  --org-display-name "Acme Corporation" \
  --studio-base-url https://app.swaggerhub.com/apis \
  --ownership-map ownership.yaml \
  --rule-display-names rule_display_names.yaml \
  --cop-guidance cop_guidance.yaml \
  --per-team-threshold 5
```

`--per-team-threshold 5` (platform report only) controls when a per-team subset HTML is generated — one is written for every team whose failing-API count exceeds the threshold. Useful for emailing individual team leads without exposing the full org landscape.

---

## 4. What the reports automatically pick up from the patched scanner

After the scanner patch (rule-id, ruleset, age, published/default flags), the reports auto-light up the following without any flag changes:

- **Executive** — fifth headline tile becomes "Unpublished among failing" when ≥50% of scanned APIs carry a known `is_published`; ruleset name appears in the footer; the "How the failures distribute" section switches to API-age / activity tables when `created_at` / `modified_at` are populated.
- **Platform team** — per-API cards show `published` / `draft` and `default` pills plus `created` / `modified` dates; the findings table gains a Published column + filter (and a Default column when ownership data isn't present).

If those don't appear, your `scan.json` was written by an older scanner. Re-scan with `uv run scanner scan` to refresh.

---

## 5. Subsetting the scan (development / targeted runs)

For dev-loop iteration against a large org (600+ APIs), the scanner supports `--limit/-n`:

```bash
uv run scanner scan -n 25                # scan only 25 API versions
uv run scanner scan -n 25 -o /tmp/dev    # ...to a custom output dir
```

The reports work identically off the trimmed `scan.json` — point `--input` at the alternate path. See [`runbook.md`](runbook.md#scanner-cli) for full scanner CLI reference.

---

## 6. Reading the tier-status stdout summary

Both generators print a summary at the end. Example from the executive report:

```
Wrote output/executive-report.html
Executive report — render summary
  Tier 1 sections: title, headline, tiles 1-4, Pareto, severity, methodology
  Tier 1 substitute: 'unpublished among failing' tile (published-state known on 100% of APIs)
  Tier 3 rule display names: not provided
  Tier 3 asks file: placeholder mode
```

Lines starting with **`Tier 2`** mean an external ownership map enriched the report.
Lines starting with **`Tier 1 substitute`** mean the spec's fallback chain rendered something different from the default — and the line tells you what.
Lines starting with **`Tier 3`** name a curated lookup; "not provided" is fine, "placeholder mode" on the asks file means the report is intentionally incomplete until a CIO ask is written.

If the platform owner is about to send the report, this is the line to read first.

---

## See also

- [`runbook.md`](runbook.md) — scanner CLI commands and the end-to-end demo loop
- [`installation.md`](installation.md) — toolchain setup
- [`../projects/reports/governance-reports-spec-v2.md`](../projects/reports/governance-reports-spec-v2.md) — the spec the generators implement
