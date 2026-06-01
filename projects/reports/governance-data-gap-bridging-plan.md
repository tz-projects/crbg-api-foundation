# Bridging the Gaps — Data Not Available in Swagger Studio

The reports rely on three categories of data Studio cannot provide. This document covers each
category: what's missing, where it actually lives in the org, and the practical path to making
it available for reporting.

The categories are ordered by impact on the report. Ownership data is by far the biggest gap;
the other two are smaller and easier.

---

## Gap 1: Team ownership of APIs (largest gap)

### What's missing

For every API in Studio, the report needs to know:
- Which team owns it
- The engineering domain it belongs to (financial-services, commerce, platform, etc.)
- The team's contact email (or distribution list)
- The source repo where the spec lives

Studio has none of this. Studio's Teams feature is permissions over APIs, not ownership of
APIs — multiple teams can have permission on one API, and "owner" isn't a defined concept at
the API level. There is no path to derive ownership from Studio alone.

### Where the data actually lives

In your org, the authoritative source for "who owns this API" is one of three places, depending
on org maturity:

1. **The app dev team's GitHub repository.** If the team owns the spec, they own the API. The
   repo's CODEOWNERS file, README, or a config file is the ground truth. This is the source
   we've been designing for.

2. **An internal service catalog** (Backstage, ServiceNow CMDB, a custom internal tool, even
   a wiki page). If your org has one of these, it likely already has team→service mappings,
   and the API is downstream of the service.

3. **Nobody's written it down anywhere.** Tribal knowledge. People know which team owns which
   API by working there long enough. This is the worst case and unfortunately common for
   legacy portfolios.

For the 600-API context: realistically you have a mix of all three. Newer APIs are likely
mapped in a catalog or have clear repo ownership; older ones may be tribal knowledge or
genuinely orphaned (someone built it, the team reorganized, nobody clear inherited it).

### The bridging approach — three phases

**Phase A: Stand up the ownership map structure (immediate, 1-2 weeks)**

Create the central file: `ownership.yaml` in the api-governance-rules repo. The schema is
already defined in the earlier artifacts (see `generate_ownership_map.py`):

```yaml
generated_at: <timestamp>
source: <how this was populated>
apis:
  payments-service:
    api_name: payments-service
    team: payments-platform
    contact_email: payments-platform@acme.example.com
    domain: financial-services
    studio_org: acme-corp
    source_repo: acme-corp/payments-service
    source_repo_url: https://github.com/acme-corp/payments-service
    governance_mode: exception_aware
    last_seen: <timestamp>
```

The map is the contract. Once it exists with this schema, every downstream consumer — the
scanner, the reports, the dashboard — can rely on it. Populate it with whatever data you
have today, even if sparse. An empty `ownership.yaml` with just the schema header is better
than no file at all because it lets the generators run in their proper mode.

**Phase B: Populate it from the highest-fidelity sources you have (3-6 weeks)**

Three population strategies, in order of preference. Use whichever yields the best coverage
for your org; in practice you'll use a combination.

*Strategy 1 — Automated from per-repo configs (the long-term right answer).*

The artifact `generate_ownership_map.py` is built for this. It scans every repo in your
GitHub org, reads `governance.config.yaml` from each, and aggregates into ownership.yaml.

The catch: this only works for repos that already have `governance.config.yaml`. If Phase 0
of the rollout (creating these configs per repo) hasn't happened, this strategy yields a
near-empty map.

Path forward:
- Onboarding new APIs requires creating governance.config.yaml as a precondition. Make this
  a Phase 2 enforcement gate: new APIs don't get into Studio without a config in their repo.
- For existing repos, treat the config as a remediation task tied to the broader governance
  rollout. Each team's first interaction with governance is "create your governance.config.yaml."
- Run `generate_ownership_map.py` nightly; coverage grows naturally as teams onboard.

*Strategy 2 — Import from an existing service catalog.*

If your org has Backstage, ServiceNow, or a similar catalog with team→service mappings, write
a one-time importer that pulls the data and emits an ownership.yaml in the right schema.

This is faster than Strategy 1 if the catalog has good coverage. The work is essentially:
- One Python/TypeScript script that queries the catalog's API
- Maps catalog records to ownership.yaml entries
- Handles the catalog's own gaps (records without team info, deprecated services)
- Outputs ownership.yaml committed to the rules repo

The script doesn't need to run on a schedule; the catalog isn't churning by the minute. Run
weekly or on-demand.

*Strategy 3 — Hand-curated, top-down (the fastest start).*

For the first report run, especially the executive baseline, hand-build the ownership.yaml.
This is the platform owner sitting down with the org chart and the API list and filling in
what's known.

Yes, it's manual. Yes, it'll be wrong in places. It's still faster than waiting for Strategies
1 and 2, and it gets you a real report in days rather than months.

Practical approach:
- Export the scanned API list to a spreadsheet
- Add columns for team, domain, contact, repo
- Fill in what's known with high confidence
- Mark the rest as "unknown"
- Share with engineering domain leads, ask them to fill in their teams' APIs
- Convert the spreadsheet to ownership.yaml when reasonably complete

The "unknown" entries are themselves valuable — they become the orphan list in the report,
which surfaces the gap to leadership in the same artifact that's asking for action.

**Phase C: Maintain it (ongoing)**

Whichever strategies you use, the ownership.yaml must be kept current. The mechanisms:

- The `refresh-ownership-map.yml` workflow (already designed) runs nightly. Regenerates from
  per-repo configs and the catalog. Detects conflicts (two repos claim same API) and orphans
  (Studio has API, map doesn't).
- Conflicts open GitHub issues automatically (already designed).
- Orphans surface in the platform team report (now designed in v2).
- When a team reorganization happens, ownership.yaml must be updated — this is part of the
  reorg checklist for whoever owns reorgs.

### The recommendation for your specific situation

For the trial: skip Strategies 1 and 2, just hand-write a small ownership.yaml covering the
trial APIs. Even synthetic team names ("team-alpha," "team-beta") are fine — the goal is to
prove the report mechanics, not to convey real data.

For the work-laptop run on the real org: Strategy 3 (hand-curated) to get the first report
out. Strategy 1 in parallel as Phase 0 of the rollout brings per-repo configs into existence.
Strategy 2 if you have a usable internal catalog. The first report ships with whatever
ownership coverage you can get in a week; subsequent reports get better as coverage grows.

Don't gate the first report on perfect ownership data. The v2 spec is designed to render
fully without it, and the gaps are themselves part of the story you're telling the CIO
("we don't yet know who owns ~X% of our APIs, and that's part of why governance is hard").

---

## Gap 2: Humanized rule display names

### What's missing

Studio returns rule descriptions in the format `"operation-description -> Operation must have
a description"`. The scanner parses out the rule ID and description, but the rule ID itself
(`operation-description`) is what engineers grep for in their tooling, while the description
is what readers actually understand.

For a report, ideally each rule appears with BOTH a humanized display name ("Operations
missing descriptions") and the rule ID for technical reference.

The description Studio provides is usable as a fallback but is often phrased awkwardly for
report presentation. Compare:
- Studio's: "Operation must have a description"
- Humanized: "Operations missing descriptions" (matches the report's failure-listing context)

### Where the data actually lives

Nowhere yet. This is a small lookup table the platform team needs to maintain.

### The bridging approach

Create `rule_display_names.yaml` in the api-governance-rules repo:

```yaml
# Maps Spectral/Studio rule IDs to humanized display names used in reports.
# Authored by the platform team. Updated when new rules are added to the ruleset.

operation-description:
  display_name: "Operations missing descriptions"
  category: "Documentation"

operation-tag-defined:
  display_name: "Operations missing tags"
  category: "Documentation"

info-license:
  display_name: "API license not specified"
  category: "Metadata"

# ... one entry per rule in your active ruleset
```

The `category` field is optional and useful when you want to group rules in the Pareto
section by theme (Documentation, Security, Naming, etc.).

Maintenance: when a new rule is added to the ruleset (PR to the governance-rules repo), the
PR must include the corresponding `rule_display_names.yaml` entry. Add this as a checklist
item in the rules-repo PR template so it's not forgotten.

The report generator falls back to the raw rule ID + description if a rule isn't in the
lookup, so missing entries cause minor cosmetic issues, not breakage.

Effort: small. A few hours to build the initial file for whatever rules are active in your
Studio org today. Ongoing: one line per new rule.

---

## Gap 3: CoP remediation guidance URLs

### What's missing

For each rule a finding triggers on, the report should link to a CoP page explaining how to
fix it. Studio doesn't know about your CoP wiki.

### Where the data lives

In your CoP wiki (Confluence, Notion, internal docs site — wherever the CoP publishes).
Each rule should ideally have its own page or section.

This is the slowest of the three gaps because it depends on the CoP actually writing the
guidance. The technical bridging is trivial; the content creation is real work, and it's
out of scope for this conversation (you noted the CoP owns guidance content separately).

### The bridging approach

**For the URL mapping itself:**

Create `cop_guidance.yaml` in the api-governance-rules repo (or alongside the display names —
they could be in the same file):

```yaml
operation-description:
  guidance_url: "https://confluence.acme.example.com/cop/operation-description"

operation-tag-defined:
  guidance_url: "https://confluence.acme.example.com/cop/operation-tag-defined"

# ... entries only for rules where guidance has been published
```

Convention to consider: have the URL pattern be predictable (`<base>/<rule-id>`) and have the
CoP commit to using that pattern. Then you don't need a lookup file at all — the report
generator constructs URLs by convention. The downside is broken links if the CoP doesn't
have a page for a given rule yet.

The right answer is probably the convention with a lookup override: report generator builds
the URL from the convention by default, but `cop_guidance.yaml` can override or mark a rule
as "guidance pending" so the link doesn't appear broken.

**For the content (out of our scope, but worth flagging):**

The CoP will need to author one page per rule, ideally with:
- What the rule checks (in plain language)
- Why the rule exists (the design principle it enforces)
- Example violation
- Example fix
- Common variations / edge cases

The platform team report's "rule reference section" surfaces which rules need guidance most
urgently — sort by failure count and start at the top. The top 5 rules from the baseline
scan are where the CoP's first 5 pages should focus.

Estimate: a CoP can reasonably author 1-2 well-written rule guides per week. Plan accordingly.
The reports will function with empty CoP guidance — the "guidance pending" placeholder
surfaces the gap without being broken.

---

## Summary: what to do in what order

If you want a single concrete action sequence:

1. **Today/this week:** Hand-build a minimal `ownership.yaml` covering the APIs you care most
   about for the baseline report (your most-active 20-50 APIs, plus anything in domains the
   CIO will recognize). This is the highest-leverage bridging activity you can do.

2. **This week:** Author `rule_display_names.yaml` for whatever rules are active in your
   Studio org. Few hours of work. Massive improvement to both reports' readability.

3. **This week:** Decide on the CoP URL convention. Even if no guidance exists yet, fix the
   URL pattern so links generated today still work later when content is published.

4. **Next 1-2 weeks:** Run the scanner, run the reports, look at the output. Decide based on
   actual data whether the ownership coverage is good enough for the executive report or
   whether you need more before showing it to the CIO.

5. **Next 1-3 months:** As Phase 0 of the rollout brings per-repo `governance.config.yaml`
   files into existence, the automated ownership map generator takes over and the hand-curated
   ownership.yaml becomes obsolete. The same file, just regenerated from a better source.

The principle running through all of this: **don't gate the first report on the perfect
version of any of these data sources.** Use the v2 spec (which renders fully on Tier 1 data
alone), enrich with whatever Tier 2/Tier 3 you can assemble quickly, and let subsequent
reports improve as the data sources mature.

---

*End of bridging plan.*
