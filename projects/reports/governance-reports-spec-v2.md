# Governance Reports — Build Specification (v2)

Two reports generated from the scanner output (`org-scan-report.json`):
1. **Executive report** — for the platform owner to show his CIO
2. **Platform team report** — for socializing with app dev teams to drive remediation

**Revision note:** v1 of this spec assumed team and domain data would be available. They are
NOT available from Swagger Studio — they require an external ownership map that may or may not
exist when the report runs. This v2 spec is structured so that EVERY section grounded in
Studio-only data renders fully on its own, and sections needing the ownership map are clearly
delineated and degrade gracefully when the map is absent or sparse.

The goal: a report that is fully useful from Studio data alone, and BECOMES MORE useful as
external data sources mature. Not a report that needs everything to be useful.

---

## Data sources, declared upfront

### Tier 1 — From Swagger Studio (always available)

The scanner already pulls these. Reports MUST render fully from these alone.

- Org name, scan timestamp
- Per API: name, version, default-version flag, published/unpublished state
- Per API: created_at, modified_at (after the scanner patch — extracted from `properties`)
- Per API: status (PASS / WARN / FAIL / SCAN_ERROR), critical count, warning count
- Per finding: rule ID (after the scanner patch — parsed from `description`), severity,
  line number, human-readable message
- Active ruleset name and version (after the scanner patch — one extra call per scan)
- Pareto of rules by failure count, derived from the above
- API → Studio URL (buildable by convention from org + api + version)

### Tier 2 — External, ownership map (`ownership.yaml`)

OPTIONAL input. When present, enriches Studio data with org-internal context.

- Per API: owning team
- Per API: engineering domain
- Per API: team contact email
- Per API: source repo URL
- Orphan classification (API in Studio without an ownership map entry)

When the map is absent: skip Tier 2 sections, surface a visible "ownership data not configured"
notice in their place. When the map is partial (some APIs mapped, some not): include only the
mapped APIs in Tier 2 sections, list the unmapped ones in the orphan section.

### Tier 3 — Curated, platform-team-maintained (small files in the same repo as the generator)

OPTIONAL inputs. Each is a small lookup file the platform team maintains.

- `rule_display_names.yaml` — maps rule ID → humanized display name. When absent, the report
  uses the rule ID directly with the description appended.
- `cop_guidance.yaml` — maps rule ID → CoP wiki URL. When absent, omit the guidance link
  column; do NOT emit broken links.
- `asks.md` — content for the executive report's "What's needed" section. When absent, emit
  the visible placeholder and refuse to mark the report as final.

### What is NEVER recoverable from Studio

Documented here so future readers don't try:

- Team ownership in any form. SwaggerHub's Teams feature is role-based permissions, not
  ownership. Multiple teams can have permissions on one API; "owner" isn't a defined concept
  at the API level.
- Engineering domain (financial-services, commerce, platform, etc.) — purely org-internal.
- Contact information for any role — comes from your directory.
- Source repository — Studio doesn't know about Git.
- Anything about the organizational unit the API belongs to beyond what's in custom properties.

---

## REPORT 1: Executive Report (CIO-facing, via platform owner)

### Purpose, format, tone

Unchanged from v1. Self-contained HTML, single page, plain language, no hedge, designed for
60-second CIO scan with enough detail to support a specific ask.

### Required sections (revised)

**1. Title and metadata block (Tier 1 only)**

- Title: "API Governance Conformance — Baseline Report"
- Subtitle: org display name
- Scan date
- One-line methodology footer (ruleset name + version + coverage note)

**2. Headline sentence (Tier 1 only)**

Auto-generated. Template:
> "Of {api_count} APIs in Swagger Studio, {fail_percentage}% currently fail governance and
> cannot be published. Failures concentrate in {top_n_rules} rule violations that account for
> {top_n_percentage}% of all findings."

Adapts if data shows scattered rather than concentrated failures (unchanged from v1).

**3. Headline numbers block (Tier 1 + optional Tier 2)**

Four numbers always, fifth conditional:

ALWAYS:
- Total APIs scanned
- % passing governance
- % with critical errors (blocks publish)
- Distinct rule violations driving failures

CONDITIONAL on ownership map presence:
- Distinct teams represented (only shown if map is present and covers ≥50% of scanned APIs)

If the map is absent or sparse, that fifth tile is replaced by:
- "APIs by age" — split into "recently modified" (modified in last 90 days) and "stable"
  (not modified in 90+ days). This is a Tier 1 substitute that surfaces something equally
  meaningful to a CIO: how active the portfolio is. Computed from `modified_at`.

The substitution is important. Don't leave a blank tile and don't show "data not available"
as a headline number — that draws the eye to the gap. Replace with a Tier 1 alternative.

**4. The Pareto — top rule violations (Tier 1 only)**

Unchanged from v1. Top 5-10 rules by failure count, CSS-bar chart, humanized names if Tier 3
display-name lookup is present (otherwise rule ID + first 60 chars of description).

Beneath the chart, the adaptive interpretation sentence.

This is the strongest single piece of evidence in the report. It is fully Studio-driven and
needs no external data to be meaningful.

**5. Distribution section — REVISED to be Tier 1 first, Tier 2 enriched**

Section header changes based on data availability:

IF ownership map covers ≥50% of scanned APIs:
- Header: "Where the work sits"
- Render as v1 spec: aggregate by domain (or team if domain missing), table with API counts
  and conformance percentages, interpretive sentence below.

IF ownership map is absent or covers <50% of scanned APIs:
- Header: "How the failures distribute"
- Render a Tier 1 alternative breakdown using data Studio DOES provide:
  - Split the failing APIs by AGE: <90 days, 90 days-1 year, 1-3 years, 3+ years old
    (using created_at). This tells the CIO whether the failures are in new APIs (active
    development quality issue) or legacy ones (accumulated debt).
  - Split by RECENT ACTIVITY: modified in last 90 days vs. dormant. This tells the CIO
    whether failing APIs are still being touched (remediable through CI gate) or
    abandoned (need a different approach).
  - Two simple tables, side by side.
- Add a one-line note at the bottom of the section: "Detailed team and domain attribution
  will be available once the organizational ownership map is in place; this report uses API
  age and activity as proxies."

This substitution preserves the CIO's ability to understand "where to direct attention" even
without team data, by framing it temporally instead of organizationally.

**6. Severity context (Tier 1 only)**

Unchanged from v1.

**7. The ask (Tier 3: asks.md)**

Unchanged from v1. Placeholder mode if asks.md is absent.

**8. Methodology footer (Tier 1 + transparency about Tier 2 state)**

ADDITION to v1: explicit one-line statement about the ownership map status, e.g.:
- "Team and domain attribution: based on ownership map covering 387 of 612 scanned APIs."
- Or: "Team and domain attribution: ownership map not yet configured; report uses API age and
  activity as organizational proxies."

This makes the gap visible and honest without making it the headline. A CIO who reads this
will know to ask about the missing data — which is the conversation the platform owner
wants to have anyway.

### What this report MUST NOT include

Unchanged from v1.

### Generator interface (revised)

```
python generate_executive_report.py \
    --input org-scan-report.json \
    --output executive-report.html \
    --org-display-name "Acme Corporation" \
    [--ownership-map ownership.yaml]             # optional; Tier 2 sections degrade if absent
    [--rule-display-names rule_display_names.yaml]  # optional; Tier 3 lookup
    [--asks-file asks.md]                        # optional; Tier 3
    [--placeholder-ask]                          # explicit placeholder mode
```

The generator MUST print a summary to stdout at the end:
- Sections rendered with Tier 1 data only
- Sections rendered with Tier 2 enrichment
- Tier 2 fields missing or sparse
- Whether the report is in "placeholder ask" mode

So the platform owner can see at a glance what the report does and doesn't include before
sending it.

---

## REPORT 2: Platform Team Report (for socializing with app dev teams)

### Purpose, format, tone

Unchanged from v1. Reference material, dense, technical, designed for working with.

### Required sections (revised)

**1. Header (Tier 1 only)**

Unchanged.

**2. How to use this report (Tier 1 only)**

Brief instructions. ADDITION: a line acknowledging which Tier 2/Tier 3 data is and isn't
present, so readers don't waste time looking for sections that aren't there.

**3. Rule reference section (Tier 1 + Tier 3)**

For each rule that appears in the data:
- Rule ID (Tier 1)
- Humanized name (Tier 3 if present; else rule ID)
- Severity (Tier 1)
- Count of APIs failing this rule (Tier 1)
- Count of total findings (Tier 1)
- Rule description (Tier 1 — comes from Studio's standardization response)
- Example violating snippet from one of the actual findings (Tier 1)
- Link to CoP guidance (Tier 3 if present; otherwise the row reads "guidance pending —
  contact platform team")

A Tier 3 lookup with no entry for a given rule still emits "guidance pending" — this is a
feature, not a bug. The empty links surface which rules the CoP still owes guidance for,
making the guidance-authoring backlog visible.

Corrected example snippets (the "fix pattern") — these are CoP-authored content. If the CoP
hasn't written them, the section shows the violating snippet only, with a note that the
remediation pattern is in the CoP wiki when guidance is published.

**4. Findings table (Tier 1 + Tier 2 columns conditional)**

Columns when ownership map IS present:
```
team | api_name | api_version | rule_id | rule_name | severity | line | message |
studio_url | cop_url
```

Columns when ownership map IS ABSENT:
```
api_name | api_version | rule_id | rule_name | severity | line | message |
studio_url | cop_url | api_created_at | api_modified_at
```

The age/activity columns substitute for the missing team data — they at least let a reader
sort by "newest failing APIs" or "most recently touched failing APIs" as a proxy for "what's
actively being worked on right now."

Filters above the table:
- Severity (always)
- Rule (always)
- Status (always)
- Free-text search on API name (always)
- Team (only if ownership map present)
- API age range (only if ownership map absent — substitutes for team filter)

Same pagination, sort, and download-CSV behavior as v1.

**5. Per-team summary (Tier 2 — degrades fully if map absent)**

When ownership map is present: render as v1 spec.

When ownership map is absent: replace this entire section with a "Per-rule summary" that
gives the inverse cut of the data:
- For each rule in the Pareto, list the APIs failing it
- This is what a CoP working on remediation guidance per rule actually wants anyway
- Headed "APIs grouped by rule violation"

This is not a degradation — it's a different but equally useful view. The platform team can
work the remediation backlog by rule when team data isn't available.

**6. Per-API summary (Tier 1 + Tier 2 conditional)**

For each API, render the v1 spec contents. The Team field reads "unassigned" if the
ownership map doesn't cover that API. Everything else is Tier 1.

**7. Orphan APIs section (Tier 2)**

When ownership map is present: APIs in Studio with no ownership entry, listed here.

When ownership map is absent: this section becomes "Unmapped APIs (all)" and the explanatory
text is changed to "ownership data not yet configured; once configured, this section will
show only the APIs missing from the map."

**8. Scan errors section (Tier 1 only)**

Unchanged.

**9. Methodology and definitions footer (Tier 1 + transparency)**

Same v1 content, plus the ownership-map status disclosure line.

### Generator interface (revised)

```
python generate_platform_report.py \
    --input org-scan-report.json \
    --output-dir reports/
    --org-display-name "Acme Corporation"
    --studio-base-url https://app.swaggerhub.com/apis
    [--ownership-map ownership.yaml]              # optional Tier 2
    [--rule-display-names rule_display_names.yaml] # optional Tier 3
    [--cop-guidance cop_guidance.yaml]            # optional Tier 3
    [--per-team-threshold 5]                       # only used if ownership map present
```

Same stdout summary as the executive report generator.

### What changes about per-team subset reports

Generated only when the ownership map is present. When absent, no per-team subsets are
generated — and the main report's CSV becomes the primary distribution artifact for the
platform team to send to individual teams once ownership is known.

---

## Shared implementation notes

Same as v1, plus:

- Generators MUST handle ownership.yaml partial coverage. Some APIs mapped, some not. Don't
  crash, don't silently drop the unmapped APIs from sections that are Tier 1 — they belong in
  Tier 1 sections regardless of whether ownership is known.
- Generators MUST print the Tier-status summary to stdout at completion.
- Generators MUST stamp the report (visibly, in the footer) with which Tiers contributed,
  so any reader knows what they're looking at.

---

*End of revised specification.*
