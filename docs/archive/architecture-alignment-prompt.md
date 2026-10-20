> Historical import, superseded by the active documentation index in [../README.md](../README.md). Statements of agreement in this snapshot are not current decisions.

# Prompts for scoped architecture alignment

Use exactly one prompt in this existing Next.js/Python checkout. Start with S0.
Read the handoff for current document locations and missing migration inputs;
subsequent scopes require prerequisite evidence from the implementation plan.

Each prompt authorizes local implementation and verification within one scope. It does not request execution of later scopes, paid generation or cloud resource changes. Use fakes/emulators as appropriate and clearly identify what they do not verify.

## S0 — Start here: verify and stabilize

```text
Implement S0 only from docs/architecture-alignment-plan.md.
Read docs/architecture-handoff.md and docs/current-app-baseline.md first, then
applicable repository instructions including web/AGENTS.md. Confirm this is the
actual app checkout with web/, web_workflow.py and manga_tts/extraction.py.
If those are absent, report the wrong-checkout blocker rather than scaffolding
another application.

Inspect and reproduce the current baseline. Diagnose Python interpreter selection,
MP3 dependency and production-build failures from current evidence. Make necessary
local runtime/configuration fixes, preserve existing edits and working features,
and avoid unrelated dependency upgrades or UI cleanup. Map duplicate UI/tests
before considering removal. Treat the supplied baseline's test results as historical.

Run the relevant existing frontend/backend checks. Distinguish code defects,
missing dependencies, skips and environment restrictions. Write a concise
scope report to docs/alignment-status.md with exact results and remaining blockers.
Stop at S0's acceptance boundary. Do not start storage, queue, auth or UI migration.
```

## S1 — Revisions and checkpoint persistence

```text
Implement S1 only from docs/architecture-alignment-plan.md.
Read docs/architecture-handoff.md, docs/current-app-baseline.md and
 docs/alignment-status.md. Confirm the actual target app and inspect applicable
repository instructions. Verify S0 prerequisite evidence; treat any remaining
baseline blocker explicitly rather than claiming it passed.

Preserve the existing Next.js studio, MAGI extraction, typed router commands,
whole-project hash checks, CLI and local mode. Implement immutable artifact
manifests, durable revision/pointer contracts, expected-revision commits and
ownership/fencing through application persistence interfaces with local test
implementations. Add a tested persistence seam for per-segment checkpoints;
remote failure must propagate before durable success. Inspect current target
source before selecting a seam; observer callbacks are not acknowledgments.

Prove competing commit conflicts, stale fence rejection, upload/pointer failure
ordering and restart from the last accepted checkpoint with intact assets.
Run affected engine/worker regressions. Update docs/alignment-status.md with
acceptance evidence, decisions and production-adapter verification still needed.
Stop at S1. Do not implement queue dispatch, publication or deploy cloud resources.
```

## S2 — Operations and worker recovery

```text
Implement S2 only from docs/architecture-alignment-plan.md.
Read docs/architecture-handoff.md, docs/cloud-deployment-design.md and
 docs/alignment-status.md. Inspect repository instructions and verify S1 contracts
and acceptance evidence before relying on them.

Adapt the existing workflow route/helper and web_workflow.py behind explicit
local/durable execution adapters. Reuse existing extraction/planning/render/export.
Implement persisted operations, deduplication, pinned input revisions, transactional
stage slots, fencing, execution identity, progress and reconciliation. Preserve
UI polling and local mode. Follow the cloud design's stage limits and retry ceiling;
verify engine/SDK retries do not multiply the chosen authority. Reconcile uncertain
execution/provider outcomes before retrying. Use fake executors/providers locally.

Prove duplicate dispatch safety, competing claims, crash recovery, segment resume
and stale completion rejection. Keep Generate/Apply/Approve/Render/Export separate.
Update docs/alignment-status.md with exact evidence and unresolved integration
checks. Stop at S2; do not deploy jobs or add reader/publication features.
```

## S3 — Identity and authorization

```text
Implement S3 only from docs/architecture-alignment-plan.md.
Read docs/architecture-handoff.md, docs/cloud-deployment-design.md,
 docs/gcp-firebase-setup-checklist.md and docs/alignment-status.md.
Inspect repository instructions and verify the required S0/S1 evidence.

Add reader/admin Firebase user authorization and a short-operation Python API
around existing commands/application services. Retain Next.js server routes and
the studio. Separate user identity from service identity and allowlist internal
service actions. Cover workflow, assets and legacy extraction routes. Preserve
expected-revision checks, safe errors and local development through explicit
injected identity adapters. Keep production verification fail-closed; test identities
must never become a hosted authentication bypass. Add actor-bound approval audit.

Test anonymous/reader denial, forged identities, internal action authorization,
draft isolation, revision conflicts and no-provider readiness/review. Verify current
official identity/platform documentation while implementing these boundaries.
Update docs/alignment-status.md and stop at S3. Do not expose hosted processing,
change cloud IAM or add catalog/publication features in this scope.
```

## S4 — Requests through publication

```text
Implement S4 only from docs/architecture-alignment-plan.md.
Read docs/architecture-handoff.md, docs/cloud-deployment-design.md and
 docs/alignment-status.md. Inspect repository instructions and verify S1–S3
prerequisite evidence.

Connect the existing reader demo to the production workflow. Replace browser-only
requests and sample statuses with persisted requests/catalog records. Resolve the
missing requests route and inactive Listen action using current screens. Use an
explicit fixture/source adapter where external manga API details remain unknown.

Add an admin audio-review decision bound to an immutable exact export version,
revision/settings/artifacts. Publish through an atomic pointer update, fulfill
linked requests and expose only published playback to readers. Preserve prior
publication during failed replacement. Support expiring URL refresh and seeking.
Keep the current studio and all engine approval rules; review does not prove
that a human listened. Do not implement translation or word-level alignment.

Prove the fake-backed request-to-publication flow, deduplication, draft denial,
changed/unreviewed export rejection and publication preservation. Update
 docs/alignment-status.md with results and remaining live checks. Stop at S4;
do not deploy or perform paid generation.
```

## S5 — Cloud integration and deployment preparation

```text
Implement S5 from docs/architecture-alignment-plan.md, beginning with local cloud
adapter/container/workflow preparation and verification. Read the handoff, cloud
design, setup checklist and docs/alignment-status.md; inspect repository instructions
and verify S1–S4 prerequisite evidence. Confirm the actual Next.js root/backend
configuration rather than copying historical names.

Implement real Firestore/GCS adapters, API/worker containers, finite execution
workflow, event ingestion and scheduled reconciliation. Package the existing MAGI
implementation; identify the benchmark needed for resource sizing. Preserve local
mode. Verify current official platform documentation and align service identities,
retry authority, immutable artifacts, generation preconditions and cleanup policy.

Run available local/emulator/integration checks and prepare concrete deployment
configuration without inventing project/region/budget/credentials. Before actual
cloud mutations or paid provider tests, identify the exact execution steps and
obtain any authorization not already provided. Missing execution authorization
blocks those steps only; finish local preparation and report its limits.

Update docs/alignment-status.md with conditional-write/recovery/access evidence,
remaining live checks and operational blockers. Claim deployment completion only
with actual deployment and recovery evidence; configuration/mocks are insufficient.
```
