# How Governance Works Here (The Model)

> The conceptual spine. Without this picture the gate looks arbitrary; with it, the gate is obviously just a checkpoint in a flow that already exists. No tool config — just the flow.

## The end-to-end flow
Narrate / simple diagram later: spec lives in GitHub → CI pushes it to Studio → rules evaluate it → it reaches a published/conformant state → the pipeline checks that state → only then does the gateway deploy.

## Where the checkpoint sits
Locate the gate in the flow. Make clear the gate reads Studio publish state and is separate from the gateway itself.

## What gets evaluated vs what doesn't
Specs are evaluated. Runtime, traffic, payloads are not.

## New APIs vs existing APIs
How the same flow is applied differently to each population.

## What you experience as a developer
The day-to-day: validate locally, push, see result, publish.
