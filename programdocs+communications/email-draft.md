Subject: API Governance — Pre-Enforcement Readiness Artifacts (for review)

Hi team,

Before we start rolling out enforcement, there's a set of information that needs to be in place so we can socialize the governance initiative properly and make adoption easier for the app-dev teams. Below is the full set I'd like us to prioritize — the documentation that needs to exist on the hub, and the communications sequence we run to roll it out.

Each entry has a one-line note on what it contains and a short punchline on what it's meant to achieve. Please review and push back before we commit to building.

========================================
DOCUMENTATION
========================================

--- Program Overview ---
Who we are and what we do — the team behind the program, its purpose, the end state, and how it fits the broader API initiative.
Goal: a newcomer knows who's driving this and why it exists, from one page.

--- Key Concepts & Glossary ---
Plain-language definitions of the shared vocabulary — spec, OAS, conformant, published, ruleset, gate, waiver, and so on.
Goal: everyone uses the same words; removes a whole class of confusion before it starts.

--- The Corebridge API Standards ---
The authoritative standard the estate is measured against.

- API Standards Overview — The umbrella view of all the standards and how they fit together. Goal: orient teams before they dive into specifics.
- How Governance Works — The end-to-end flow (GitHub to CI to API Hub, rules evaluate the spec, it reaches a published state, the pipeline checks that state, then the gateway deploys) and where the gate sits. Goal: governance reads as a logical checkpoint, not bureaucracy.
- Naming Conventions — The required naming rules for APIs, paths and operations, with examples. Goal: consistency that makes APIs predictable to consume.
- Versioning Strategy — How versions are expressed and evolved, and the breaking-change policy. Goal: predictable, safe evolution of APIs.
- API Documentation Standards — What a spec must document (descriptions, examples, error responses). Goal: specs that are usable by consumers, not merely valid.
- Spectral Rules Catalogue — Every rule in human terms: ID, what it checks, why it matters, severity, a violating example, and the fix. Goal: teams can interpret and remediate against the rules.
- Definition of Done (The Good API) — What "published" and "conformant" mean operationally, and the bar for new vs existing APIs. Goal: teams know exactly when they're finished.
- Rule Configuration in API Hub — How the ruleset is configured and maintained in the Hub, including severities and report-only vs enforced. Goal: transparency on how rules are applied and by whom.
- Exception / Waiver Process — What qualifies, how to request, who approves, duration, and what the owner must acknowledge. Goal: a sanctioned escape hatch so the gate can stay on under pressure.
  Timing note: recommend we AUTHOR this now but surface it in the comms at the Enforcement Warning stage — publishing it early invites teams to treat waivers as an opt-out instead of remediating.
- Top-Violations Playbook — The ~10-15 most common violations across the estate, each with a copy-paste fix. Populated after report-only gives us the real data. Goal: collapse 600 APIs' worth of problems into a handful of repeatable fixes.
- Support Model — The support channel, office-hours schedule, platform team contacts, and escalation path. Goal: every question has a clear home.

--- Corebridge API Hub ---
Where specs live, are published, and are discovered.

- API Catalog Introduction — What the catalogue is and what it holds. Goal: teams understand where their APIs live and surface.
- How to Access, View & Use — Getting access, navigating, and finding APIs. Goal: teams can actually use the Hub day to day.
- API Metadata & Tagging Standards — The required metadata and tags, and why they matter. Goal: discoverability and governance reporting both depend on consistent metadata.

--- Corebridge API Pipeline ---
How specs flow to the gateway and where the checks live.

- Pipeline Introduction — What the pipeline does at a high level. Goal: shared understanding of the delivery path.
- Pipeline Design — The stages and architecture, including the decoupling of the spec-publish gate from the backend deploy. Goal: clarity on how the checks are wired together.
- Onboarding, Configuration & Usage — How a team brings an API onto the pipeline and configures it. Goal: teams can self-onboard with minimal hand-holding.
- API Deployment Process — The deploy flow end to end. Goal: predictable, repeatable deployments.
- Spec Validation on API Hub — How and when the pipeline validates the spec against the ruleset and publish state. Goal: teams know exactly what the pipeline checks.
- Non-Conformance Reporting — How failures are surfaced and reported back to teams (the Hub has no native push, so this matters). Goal: teams find out they're non-conformant without having to hunt for it.
- Metadata & Governance Enforcement in Pipeline — The gate itself: the pipeline stops the deploy if the API isn't published and conformant. Goal: the enforcement mechanism every other artifact exists to prepare for.
  Timing note: document this now so it's ready and reviewed, but it's the last switch we flip — not the last doc we write.

========================================
COMMUNICATIONS (rollout sequence)
========================================

The phases run in order; we don't advance until the previous one has landed. Every message names new APIs vs existing APIs separately and links back to the hub.

| Phase                 | Audience                              | Channel                          | What it communicates                                                       | Goal                                                      |
| --------------------- | ------------------------------------- | -------------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------- |
| Pre-brief             | Exec sponsor, then eng managers/leads | Direct briefing (meeting + note) | What's coming, why, the timeline, and the ask of them                      | Air cover before developers hear about it                 |
| Announcement          | All app-dev teams (managers cc'd)     | Email (sponsor-endorsed)         | The program, the standard, the why, the full timeline; nothing blocks yet  | Establish understanding before any action                 |
| Visibility            | Each team individually                | Email (per-team) + Teams         | Report-only is on; here's your current-state report and how to check/fix   | Each team sees its own gap; we read the remediation curve |
| Supported Remediation | All teams + leadership progress view  | Both                             | The playbook, office hours, visible progress, recognition for early movers | Help teams fix at scale and build momentum                |
| Enforcement Warning   | All teams (managers cc'd)             | Email + Teams reminders          | Dated gate notice, countdown reminders, the waiver path                    | An unambiguous warning with a clear escape hatch          |
| Enforcement Live      | All teams                             | Both                             | Gate is on; what a block looks like; the waiver path; support              | Turn the gate on without breaking trust                   |

========================================

A few framing points to keep in mind as we review:

- This set is everything that needs to exist BEFORE enforcement — the enforcement artifacts (waiver, pipeline enforcement) get documented now but activated last.
- The gate date is an output, not an input. We set it after the toolkit exists and report-only shows us how fast teams actually remediate.
- New APIs get the gate effectively from day one; the existing estate gets the phased, supported, exception-aware path. We keep those two separate in every message.

Let me know what you'd add, cut, or re-sequence. Once we align, I'll start drafting the high-priority pieces.

Thanks,
[Your name]
