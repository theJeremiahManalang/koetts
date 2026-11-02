# Architecture alignment implementation plan

Updated 19 October 2026. Read [current architecture](../ARCHITECTURE.md) and [the accepted target](../TARGET_DESIGN.md) first. This plan applies to the existing app in [the supplied baseline](../archive/current-app-baseline.md), not a new web application.

The S0–S5 scopes below are the original architecture sequence. Current hosted
implementation and live acceptance use the phases in the [hosted plan](hosted-service-plan.md).
Use [current status](../STATUS.md) to distinguish completed offline work
from outstanding deployment gates.

## Scope selection

Execute one selected scope per implementation assignment. Stop at that scope's acceptance boundary and report evidence; do not automatically continue into later scopes. Minimal supporting edits outside a scope's likely files are allowed when required by its contract, and must be explained.

| Scope | Outcome | Depends on |
| --- | --- | --- |
| S0 | Verified app baseline and reproducible local checks | Actual target checkout |
| S1 | Durable revisions, immutable manifests and checkpoint persistence | S0 |
| S2 | Durable operations and recoverable finite worker execution | S1 |
| S3 | Reader/admin authorization and authenticated API boundary | S0; S1 for persisted audit/revisions |
| S4 | Shared requests, reviewed publication and real reader playback | S1, S2, S3 |
| S5 | Cloud adapters, deployment integration and operational recovery evidence | S1–S4; cloud inputs |

Recommended order: S0, S1, S2, S3, S4, S5. S1–S4 can develop locally with injected identities/providers. Keep hosted processing disabled until S3 access controls and S5 service integration are verified. No scope is complete merely because scaffolding exists.

Before implementing a dependent contract, resolve its open decision in
[target-design.md](../TARGET_DESIGN.md). Local fakes can support independent work,
but cannot establish unresolved production policy.

## S0 — Stabilize and verify the existing app

Likely files: `apps/web/package.json`, lockfile, Next/TypeScript configuration, Python workspace manifests and root uv lockfile, existing test configuration and runtime launcher.

Inspect repository instructions, active imports, route handlers, `apps/worker/src/manga_worker/workflow.py`, extraction, CLI and engine. Reproduce frontend tests, typecheck, production build and Python tests using the target's documented commands. Diagnose missing Python selection, MP3 dependency and reported build failures from actual output. Distinguish environmental restrictions from code defects. Make only necessary runtime/configuration fixes; retain existing dependency tooling unless evidence requires a change.

Acceptance:

- A documented local startup and explicit Python interpreter selection work in the available environment.
- Tests/typecheck/build have exact outcomes and commands; missing dependencies, skips and environment blocks are separately recorded. An environment-blocked build remains unverified.
- Existing working-tree edits are preserved, and obsolete duplicate UI/tests are mapped by reachability before any cleanup.
- Record results and blockers in `docs/STATUS.md` in the target repository.

Excluded: persistence migration, UI redesign, cloud deployment and feature additions.

## S1 — Durable revisions and artifact persistence

Likely boundaries: engine persistence seam, new application persistence services, existing worker snapshot/loading code and focused tests. Choose locations consistent with the target repo instead of moving the entire project into a new layout.

Implement artifact-store and transactional revision-store interfaces with local test implementations and a specified production contract. Model immutable revision ID, parent, manifest identity/checksum and current-project pointer. Manifest entries map engine-relative paths to immutable object identities, generations and checksums. Preserve the current project-hash expected-revision check at the API/CLI seam.

Persist and verify artifacts before committing a pointer. Add edit ownership/fencing and explicit conflict results. For worker conflicts, specify whether edits are blocked or stale results remain unpromoted. Add a tested checkpoint seam that acknowledges required artifact persistence before success and propagates failures; preserve existing local mode. A failing pointer commit may leave collectible orphan artifacts, never a partially current revision.

Acceptance:

- Competing commits have one winner; stale revisions/fences are rejected without changing the pointer.
- Failure after upload but before pointer commit preserves prior state.
- Remote checkpoint failure is visible; restart restores the last accepted checkpoint and referenced audio.
- Existing approval, hash checks, local recovery, CLI and project-bundle regressions remain intact.

Excluded: queue dispatch, real cloud provisioning, reader/catalog changes. Fake-store tests do not establish Firestore/GCS integration correctness; S5 must verify actual transaction/precondition semantics.

## S2 — Durable queue and finite workers

Likely boundaries: `apps/web/lib/workflow.ts`, workflow route, `apps/worker/src/manga_worker/workflow.py`, worker entry points and application operation/dispatcher services.

Separate the current local subprocess executor from a durable execution adapter. Keep local execution available. API enqueue returns an operation ID only after persistence. Define operation states and legal transitions, pinned revision/source/configuration, dedupe key, attempt count, fence, lease, external execution identity, progress and checkpoint/output pointers.

Use transactional global slots for MAGI and pipeline stages. Workers accept operation ID/fence and resolve trusted parameters server-side. Adapt existing extraction/planning/render/export rather than rewriting them. Planning persists an unapplied proposal; rendering preflights approvals; export synthesizes nothing. Add reconciliation for dispatch crashes, stale leases, unfinished jobs and uncertain outcomes. Resolve the S2 policy decisions in `../TARGET_DESIGN.md` before implementing production scheduling; enforce the accepted retry ceiling under one authority.

Acceptance:

- Duplicate enqueue/dispatch represents one logical operation; competing claims respect stage limits.
- Worker termination after accepted segment persistence resumes without regenerating that segment.
- Stale completion cannot overwrite newer state; uncertain executions retain capacity until reconciled safely.
- New durable progress works with existing UI polling; local mode remains testable.

Excluded: real cloud jobs/IAM deployment, publication and frontend redesign.

## S3 — Authentication and API authorization

Likely boundaries: Next server routes, Python HTTP adapter, identity verification, asset authorization, Firestore rules and audit services.

Add Firebase reader/admin identity with trusted role provisioning. Require admin authorization for studio edits, uploads, generation, private evidence and draft audio. Provide short-operation Python HTTP endpoints wrapping existing commands/application services. Verify Cloud Run caller identity separately from Firebase user identity; authorize internal service callers per action. Preserve safe `WorkflowError` transport. Protect cookie mutations against CSRF where applicable.

Keep browser database access denied. Remove dependence on loopback/origin checks as user authorization; retain useful transport checks. Include legacy `/api/extract` and asset handlers in access coverage. Record actor, revision and decision for approvals without replacing engine validity fingerprints.

Acceptance:

- Anonymous/reader requests cannot invoke admin or internal actions or read drafts.
- Forged identity headers, wrong service audience/identity and self-granted admin roles fail.
- Expected-revision conflicts remain enforced after authorization.
- Status/readiness and ordinary review never instantiate a paid provider.

Excluded: catalog/request fulfillment, public rollout and replacing the studio UI.

## S4 — Requests, audio approval, publication and playback

Likely boundaries: existing browse/manga/read/request routes, new missing requests route, persisted catalog/request/publication services and audio review UI.

Replace hardcoded statuses and browser-only requests with persisted chapter/configuration identities, deduplicated requests, reader-safe status and admin approval/fulfillment. Readers submit manga/chapter references; admins supply authorized source images. Use explicit source fixtures/adapters; automated scraping and external catalog integration are deferred. Readers see shared published catalog/audio and their own requests. Implement `/requests` or update navigation to the actual supported route.

Add an explicit persisted admin audio-review decision bound to exact export version, revision, settings and artifact checksums. The app records a review decision, not a claim that it can prove a human listened. Publish only that reviewed export through an atomic pointer commit; link publication to request fulfillment and catalog status. Keep old published audio during replacement work/failure.

Wire Listen and reader playback to authorized published artifacts with short-lived URLs, expiry refresh and range seeking. Reuse current screens. Treat manga page delivery and audio delivery as distinct sources.

Acceptance:

- One local fake-backed flow covers request → admin approval → existing production review/render → export review → publication → reader playback.
- Duplicate requests share work by the documented chapter/configuration key.
- Drafts/unreviewed or changed exports cannot publish; failed replacement keeps existing publication usable.
- Request status/catalog reflect publication; missing navigation and inactive Listen action are resolved.

Excluded: translation, word alignment, shared manga-wide cast and unrelated visual redesign.

## S5 — Real cloud integration and deployment evidence

Resolve S5 inputs listed in `../TARGET_DESIGN.md` and verify current official platform documentation before infrastructure implementation. Add real Firestore/GCS adapters, Cloud Run API/worker containers, execution workflow, event ingestion and scheduled reconciliation. Bind configuration to the existing Next app root and actual Firebase backend; verify backend identity against configuration and deployed state.

Package the existing MAGI runtime and measure representative input before sizing. Validate archive/object identities and preserve required review evidence before exact-generation ingest deletion. Implement reference-aware retention under the resolved retention policy. Establish actual origins/CORS, URL refresh/seeking and secret injection. Keep deployment/paid-generation execution distinct from local preparation and obtain any missing execution authorization before those steps.

Acceptance:

- Real adapter integration tests prove conditional writes, generation preconditions, stale fences and restart recovery.
- Deployment checks prove user/service access denial, upload/event deduplication, global stage limits, dispatch reconciliation and partial-render resume.
- Cleanup retains queued/active/referenced objects and uses terminal-failure/supersession timestamps.
- MAGI/Gemini/MP3 compatibility, listening quality, measured resources and production build evidence are recorded separately from synthetic tests.
- Missing project/region/budget/credentials or execution authorization are explicit blockers; templates and mocks are not deployment completion.

## Required scope completion report

Update `docs/STATUS.md` with scope ID, completed acceptance checks, changed boundaries/files, decisions, exact verification results, environment/external blockers and next eligible scope. Record failure/skip details. If a prerequisite fails, complete independent work within the selected scope and report the blocked acceptance criteria. Do not mark blocked criteria passed or broaden the assignment to compensate.
