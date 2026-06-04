# Guiding Principles

> The design tenets and the reasoning behind each. Point here when a design choice is challenged, instead of re-litigating. One or two lines of rationale per principle.

## GitHub is the single source of truth
Specs and rulesets live in GitHub; flow is GitHub → Studio only.

## Enablement before enforcement
Visibility and tooling come first; the gate comes last and only when teams have had a fair window.

## Strict for new, exception-aware for existing
New APIs meet the bar from day one; the existing estate gets a phased, waiver-aware path.

## The gate is decoupled from runtime
Spec conformance is a separate concern from the gateway deploy mechanics.

## Feedback flows through the pipeline, not Studio seats
Teams hold Consumer roles; pipeline output is their governance feedback channel.

## Patterns over one-offs
600 APIs failing the same rules is ~15 patterns; remediate by pattern.

## Transparency, no ambush
The full timeline is public from the start; nothing blocks without warning.
