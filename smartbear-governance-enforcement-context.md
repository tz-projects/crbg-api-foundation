# SmartBear API Governance Enforcement & Publishing — Context Document

A working context document for the initiative to enforce governance on 600+ APIs in Swagger Studio and drive them to a published, conformant state. Captures design decisions, constraints, artifacts built, and open items so work can continue in a new session (or in Claude Code) without re-litigating settled ground.

This is a sibling to the User Lifecycle POC context document. Different problem space (governance enforcement & CI/CD), same organization and same Swagger Studio instance.

---

## 1. Scope and purpose

The organization has 600+ APIs on Swagger Studio. Governance is enabled org-wide but no APIs are published, and almost all currently fail the OAS 3.0 rules SmartBear provides (the built-in standardization ruleset). The goal is to drive all APIs to a conformant, published state, and to put automated enforcement in place so conformance is maintained going forward.

**In scope:**

- A non-conformance scanner that scans the entire Studio org and produces a publishable report
- A ruleset repo + pipeline that pushes Spectral rulesets from GitHub to Studio
- A per-API repo + pipeline that validates a spec against governance rules and publishes to Studio on pass
- The enforcement model (strict vs. exception-aware) and its phased rollout
- Ruleset-change blast-radius mitigation (impact analysis + grace periods)
- An API → team ownership map generator

**Out of scope (parked):**

- The dashboard's organizational placement and full implementation (SharePoint/Power BI sink is stubbed)
- Center of Practice remediation guidance content (the CoP owns this; referenced but not built here)
- Bulk remediation tooling for the existing 600 beyond the scanner report
- Monorepo support in the ownership map (one api_name per repo assumed for now)

---

## 2. Standing decisions and constraints

These are settled. Don't re-open unless something material changes.

- **GitHub is the source of truth for specs.** Specs live in GitHub alongside backend code; app dev teams own them. Studio is a publishing + governance surface on top of GitHub, not a parallel authoring environment.
- **Direction is GitHub → Studio only.** Organization security policy does NOT allow SmartBear-to-GitHub sync. All sync flows from GitHub into Studio via CI. This is a hard constraint.
- **GitHub is also the source of truth for rulesets.** Rules are authored in a central ruleset repo and pushed to Studio. Nobody edits rules directly in Studio.
- **Remediation is the app dev teams' responsibility, not the platform team's.** The platform team builds enforcement/reporting/tooling; teams fix their own specs. The platform team cannot sustainably hold a backlog of fixes across 600 repos owned by others.
- **Single platform team** owns the governance machinery (carried over from the lifecycle POC context — same team).
- **SaaS, not on-premise.** The org uses Swagger Studio SaaS. Base URL is `https://api.swaggerhub.com`. (On-prem would need `SWAGGERHUB_URL`; not applicable here.)
- **Enforcement stance: exception-aware, reached gradually — NOT unconditional hard-block from day one.** The platform owner initially wanted to stop the pipeline / block deploy on any governance failure. The agreed counter-position: an unconditional halt is technically strong but politically/operationally fragile (first blocked hotfix gets the gate ripped out). Exception-aware enforcement (gate by default, defined+logged+visible exception path) gives the same teeth and is sustainable. Strict enforcement applies to NEW APIs; exception-aware applies to the EXISTING 600.
- **No hard deadline** for publishing all 600, but it is the ultimate goal. Drive adoption via visibility, new-API enforcement, and waves — not a big-bang mandate.
- **Decouple gates.** Spec-publish gating on governance is uncontroversial and always on. Backend-deploy gating on governance is the variable (the decision switch). Don't couple them until late in the rollout, and even then only with the exception path live.

---

## 3. Source-of-truth & drift model

- Specs: GitHub → (CI) → Studio. Fixes happen in GitHub; Studio reflects GitHub.
- Rulesets: central ruleset repo → (CI: `spectral:upload`) → Studio. Studio scans against a fixed-name ruleset (`openapi-3-0-active`); versioned snapshots (`openapi-3-0-<version>`) kept for audit/pinning.
- Drift between the GitHub ruleset and Studio's enforced ruleset is avoided because the publish pipeline is the only writer, and the per-API pipeline can validate using Studio's own engine (`api:validate:local`) as a drift check.

---

## 4. Confirmed SmartBear CLI / API facts

Verified against SmartBear docs and the swaggerhub-cli README (https://github.com/SmartBear/swaggerhub-cli). These were confirmed, not assumed:

- **CLI requires Node.js 20.17+**, installed via `npm i -g swaggerhub-cli`.
- **Auth:** `SWAGGERHUB_API_KEY` env var (takes precedence) or `swaggerhub configure`. Key from app.swaggerhub.com/settings/apiKey.
- **`swaggerhub spectral:upload OWNER/RULESET_NAME <directory>`** — create/update an org's Spectral ruleset. Directory contains `spectral.yaml` (+ optional `functions/`, additional YAMLs). THIS is how rulesets get pushed to Studio.
- **`swaggerhub spectral:download OWNER/RULESET_NAME <directory>`** — pull a named ruleset back.
- **`swaggerhub api:validate:download-rules OWNER [-s] [-d]`** — download the org's ACTIVE standardization ruleset, including built-in system rules with `-s`. This means Studio's built-in rules ARE exportable via CLI (they are NOT exportable via the UI). Use this to bootstrap the central repo instead of re-authoring rules by hand.
- **`swaggerhub api:validate:local -o ORG -f FILE [-c] [-j]`** — validate a LOCAL spec file against the org's Studio config, no round-trip, Studio's own engine. `-c` = fail-on-critical (exit 1). `-j` = JSON output. This is the preferred per-API CI validation method (zero drift, no ruleset duplication on the runner).
- **`swaggerhub api:validate OWNER/API/[VERSION] [-c] [-j]`** — validate a version already in Studio. `-c` exits 1 on critical standardization errors.
- **`swaggerhub api:create` / `api:update`** — push spec (with `--published publish|unpublish`, `--setdefault`, `--visibility`).
- **`swaggerhub api:get OWNER/API/[VERSION]`** — fetch a spec / check existence (404 = doesn't exist).
- **`swaggerhub api:publish` / `api:unpublish` / `api:setdefault`** — lifecycle state.
- **REST Standardization endpoint:** `GET https://api.swaggerhub.com/apis/{OWNER}/{API}/{VERSION}/standardization` returns governance findings (severity CRITICAL/WARNING, line, description). One call per API version. Used by the scanner.
- **Studio import accepts Spectral rulesets** as YAML, JS, JSON, or pre-bundled `.zip` (custom functions in a separate folder).

**Open verification item:** confirm the trial/org TIER includes Governance/Standardization. The `/standardization` endpoint returns empty (not an error) if the tier lacks it — a confusing failure mode. Always run a capability probe first.

---

## 5. Repo structure decision (Phase 1)

**Two separate repos, two (or three) pipelines.** Confirmed approach:

- **Ruleset repo** — one pipeline: push ruleset from GitHub → Studio (`spectral:upload`). Kept separate so the trial mirrors the ideal end-state architecture.
- **Per-API repo** — contains the spec + pipelines:
  1. Existence/state check (does API exist in Studio? published or not? → create vs. update branch)
  2. Get rules + validate. TWO variants to build:
     - **Variant 1 (Studio is authority):** `api:validate:local -o ORG -f spec.yaml` — validate against Studio's live config, no ruleset file on runner. Zero drift; requires Studio reachable.
     - **Variant 2 (GitHub is authority):** check out the ruleset repo, run Spectral locally against the spec. Pinned, offline-capable; only as current as last push to Studio. Aligns with GitHub-as-source-of-truth stance; Variant 1 becomes the periodic drift check.
  3. Gate on validation exit code (`-c` / fail-on-critical).
  4. Publish to Studio on pass (`api:create`/`api:update`, then `api:publish`).

For the TRIAL specifically (single user, trial org): the two-repo split is still the right call because it mirrors production. (Earlier "use one repo for the trial" advice was superseded — the user correctly wanted the production-shaped split.)

**Demonstration requires TWO sample specs:** one "good" (passes rules) and one "bad" (fails ≥1 rule). A pipeline that passes everything can't be distinguished from one that isn't checking. Good spec → passes gate → publishes. Bad spec → fails gate → publish never runs.

---

## 6. Enforcement rollout phases

- **Phase 0 — Foundation:** non-prod env, credentials, central ruleset repo, bootstrap ruleset from Studio, publish v1.0.0 + wire active pointer, first ownership map. No enforcement.
- **Phase 1 — Reporting/visibility:** org-wide scanner + baseline report + Pareto, dashboard sink, per-app pipeline in reporting-only mode (deploy gate disabled). No blocking.
- **Phase 2 — New-API enforcement:** strict gate for new APIs / new major versions only. Tiny blast radius.
- **Phase 3 — Exception-aware for active existing APIs:** existing APIs getting a new version must pass or file an exception. Roll in waves. Watch exception volume per rule (high volume = rule needs tuning). Impact-analysis + grace-period machinery must be working before any rule tightening.
- **Phase 4 — Coupled gate:** failed publish blocks deploy unless exception filed. The platform owner's original goal, reached gradually.
- **Phase 5 — Backlog remediation (parallel, ongoing):** drive stable/dormant tier down using scanner output + ownership map; resolve Studio orphans (remediate/reassign/deprecate).

Tier the 600: active (remediate via CI forcing function), stable (need campaign), dormant (no commits 12mo+; question whether they belong in Studio).

---

## 7. Artifacts already built

Living in two output bundles (the user has these files). Built and compile-checked; SharePoint sinks and notifications are stubs.

**Per-API pipeline bundle:**
- `governance_check.py` — core pipeline logic (existence check, Spectral validate, push to validation slot, promote, exception handling, report, exit codes 0/1/2/3). Invoked by both CI configs.
- `Jenkinsfile` + `api-governance.yml` (GitHub Actions) — thin wrappers around governance_check.py.
- `scan_all_apis.py` and `scan_all_apis.ts` — org-wide scanner (REST-based, async, paginated, Pareto + team breakdown).
- `examples/`: `openapi-3.0.yaml` (Spectral ruleset mirroring Studio built-ins), `governance.config.yaml` (per-repo config incl. governance_mode + decision switch), `.spectral.yaml` (per-repo pointer).

**Ruleset repo bundle:**
- `analyze_ruleset_impact.py` — dual-ruleset blast-radius analysis (old vs new against all APIs); regressions/improvements/rule+team breakdown; threshold gate.
- `publish_ruleset.py` — semver bump, `spectral:upload` to `-active` + `-<version>`, grace-period record creation, team notification. (Corrected to use real `spectral:upload`.)
- `bootstrap_ruleset_from_studio.py` — one-time: `api:validate:download-rules` to seed the central repo from Studio's existing config.
- `grace_period.py` — runtime: downgrade error→warn for rules in active grace window.
- `generate_ownership_map.py` — scan all GitHub repos' governance.config.yaml → consolidated ownership.yaml; detect conflicts/orphans.
- CI workflows: `ruleset-impact-and-publish.yml`, `refresh-ownership-map.yml`, + Jenkinsfile.
- `grace-periods/v1.5.0.yaml` and `ownership.yaml` — example/format files.

---

## 8. The scanner (current focus)

**Decision: REST, not CLI.** Rationale: the scanner has two operations — enumerate all APIs (CLI is poor at this; needs REST anyway) and get findings per API (CLI's `api:validate` is fine but 600 subprocess spawns is slow and forces a hybrid). REST does the whole job in one fast, poolable, structured-error path. (CLI IS the right choice for the per-API pipeline gate, where it's one API per run.)

**Runs on the user's laptop, not "in SmartBear."** There is no SmartBear compute environment — SaaS exposes a public REST API; the scanner is just an HTTPS client. Test on personal laptop against trial org; run on work laptop against real org. Same code, org is a parameter.

**Work-laptop run considerations (organizational, not code):**
- Network egress to api.swaggerhub.com (watch for corporate proxy / SSL inspection that breaks scripts even when browser works → may need proxy env vars or corporate CA bundle).
- Org-owner read API key (member-scoped key returns partial list).
- Possibly sanction to run a full-estate enumeration against corporate Studio (it's read-only, but politically visible).
- Conservative rate-limit throttle (≥600 calls; SaaS has limits). Scanner already batches with concurrency cap.

**Report output (confirmed decisions):**
- Formats: JSON (machine feed) + CSV (import-anywhere, finding-level granularity) + self-contained HTML (human/leadership report, summary + detail).
- HTML headline = the rule Pareto (which rules account for most failures — the single most decision-relevant output; tells you bulk-fix vs. long-tail).
- Include passing APIs too, with a status column (pass/warn/fail/error) — "how many are already clean" is useful.
- Capability/connectivity probe as step zero (confirm auth, org reachable, /standardization returns data) — fail fast on work laptop.

**Prerequisites (REST scanner):**
- Python option: Python 3.11+, venv, packages `aiohttp` + `pyyaml`. Stdlib covers json/csv/html. Fallback: urllib (zero external deps) if work laptop blocks package installs.
- Node/TS option: Node 20.17+, packages `axios` + `p-limit` + `yaml` (+ `typescript`/`@types/node` if TS). Built-in fetch can replace axios for zero HTTP deps.
- Shared: API key, owner/org name, tier confirmation.

---

## 9. Open items / immediate next steps

- **Confirm tier includes Governance** + **owner name** on the trial (blocks everything; make it the capability probe).
- **Choose scanner language** (one, not both) — Python recommended for lighter footprint on locked-down machines. Decide whether to keep the zero-dependency fallback (urllib / built-in fetch) in mind.
- **Build the scanner** (REST, chosen language) with JSON+CSV+HTML output and the step-zero probe. — Recommended to do in Claude Code (runs locally, tight test loop against live Studio).
- **Refactor `governance_check.py`** to use `api:validate:local` instead of fetching/running Spectral separately (eliminates drift). Open from earlier.
- **Build Phase 1 pipelines** (ruleset repo push; per-API validate+publish, both Variant 1 & 2; good+bad specs). Claude Code territory.
- **Grace-period cleanup process** (move expired records to `grace-periods/expired/`) — not yet built.
- **SharePoint/dashboard sink** — stubbed; needs site/list ID resolution + batched Graph POSTs. Decide dashboard placement.
- **Ownership map** — monorepo (multiple APIs per repo) schema extension if needed.

---

## 10. Where to continue which work

- **Claude Code (local machine):** scanner build, the Phase 1 pipelines, capability probe, anything needing to run against live Studio and iterate on real responses. Hand it THIS document.
- **This chat interface (with project context docs):** strategy/advisory work — dashboard placement, adoption & pushback plan, phase timing, anything the scanner output reopens (e.g. if failures are long-tail not Pareto, rethink rollout), and regenerating/updating these context documents.
- Context documents are the handoff mechanism in both directions. Update them at phase boundaries.

---

*End of context document. Upload to the Project and/or hand to Claude Code to carry forward.*
