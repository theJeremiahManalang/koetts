# Hosted service implementation plan

This plan defines the full GCP/Firebase hosted pilot. It is a specification, not
evidence of cloud integration, live model compatibility, deployment, or acceptance.
The accepted product and persistence invariants remain in
[`target-design.md`](target-design.md); implementation evidence belongs in
[`alignment-status.md`](alignment-status.md).

Each substantial phase has a fixed review point: commit its implementation, review
the commit against phase start with independent Standards and Spec axes, fix all
findings, and record checks/findings in `CONTEXT.md` before beginning the next phase.

## Pilot limits and operating decisions

- Launch to public Google signups. Require trusted admin approval before any
  production. A reader request never starts paid work.
- Allow at most five outstanding pending requests per reader at any time, plus
  ten successful new requests per reader per UTC day. Enforce counters transactionally. An idempotent duplicate does not
  consume another request. A request removed by its owner follows existing S4 rules.
- Size initial pilot for five new chapter works per UTC month, at most forty source
  pages per chapter, and twenty active readers. Twenty readers is a sizing target,
  not a signup cap. Enforce the chapter and page limits at production admission.
- Every new hosted project requires approved shared chapter work. Verify the work
  and its recorded admin approval in the operation transaction, and count distinct
  work IDs against the monthly allowance. Retries and replacement projects for the
  same work do not consume another chapter slot. Creation does not implicitly link
  the project to the work; explicit admin linking remains separate. Local creation
  retains its existing behavior.
- Target total project spend of USD 10/month. Configure a project-filtered USD 20
  alert budget with notifications at USD 10, 15, and 20. This includes Gemini model
  charges as well as infrastructure, but is not a guaranteed ceiling: billing is
  delayed and existing traffic and services can keep accruing charges. Pause new
  extraction and generation at USD 15 reported project spend, or earlier when
  conservative reservations exhaust the remaining allowance. Keep login and
  published playback available. Resuming production requires explicit admin action.
- Keep the application provider allowance (at most USD 80) as a separate developer-
  configured admission control. It is not a separate billing account, Gemini credit,
  or infrastructure-only budget. Never launch work without admission against
  configured production limits. Do not automatically retry an uncertain paid call.
- Start with scale-to-zero CPU Cloud Run Jobs and one global slot per stage. Run a
  representative CPU benchmark before enabling hosted extraction. If it misses
  quality, time, memory, or budget limits, block full hosted launch and revisit
  compute and budget explicitly; do not silently switch to GPU.
- Use one-minute Cloud Scheduler dispatch and reconciliation. Set Cloud Run Job
  task retries to zero; the durable operation service owns at most three total
  attempts, with 30-minute attempt timeout, 15-second heartbeat, and 60-second
  lease. Reconcile execution identity and checkpoints before releasing a lease.
  An uncertain external outcome retains its slot until an explicit admin decision.
- Keep the existing Firebase project and `koetts-default` Firestore database.
  Put new regional compute and artifact storage in `us-central1`. Keep the
  existing App Hosting frontend in `us-east4` initially, then migrate it to
  `us-central1` through a separately verified frontend cutover. Preserve the
  current backend until the replacement passes authentication, playback and
  rollback checks. Use a clean cloud dataset. Do not import local projects, legacy requests, or local
  publication records as part of this pilot.
- Use the Google Gen AI SDK with enterprise mode and Application Default
  Credentials (ADC). Set `GOOGLE_CLOUD_PROJECT` to the existing project and use
  inference location `us`, independently of `us-central1` compute and storage.
  Only the pipeline job receives `aiplatform.endpoints.predict`; the frontend,
  API, Magi job, and collector receive no Gemini provider key or inference grant.
  Keep the audio-signing secret frontend-only.
- Retain accepted and referenced artifacts. Remove only unreferenced temporary
  artifacts after seven days, using reference-aware collection.
- Authenticate every published audio request and range request through the
  same-origin application path. Verify the session and publication before streaming
  private GCS bytes. Preserve byte-range seeking and prevent shared caching.

## Phases and acceptance

### Phase 0 — Lock decisions and review plan

Record this plan, resolved S5 choices, scope boundaries, and task evidence. Review
the phase diff for standards and spec before starting implementation.

Acceptance: repository checks and diff checks pass; a two-axis review reports no
unresolved findings. No application or cloud behavior is claimed as implemented.

### Phase 1 — Durable cloud persistence

Implement GCS artifact storage and Firestore revision ownership behind the current
engine protocols. Address artifacts by exact object generation and checksum. Persist
and verify artifacts before atomically advancing a conditional revision pointer.
Bind shared metadata to the stable cloud bucket/dataset identity, not a local
directory. Keep local adapters as local defaults and fail closed on cloud errors.

Acceptance: emulator and injected-store tests cover competing owners, stale fences,
conditional revisions, upload/checksum/pointer failure, restart recovery, and safe
materialization. Existing local persistence and publication tests still pass.

### Phase 2 — Distributed operation coordination and jobs

Abstract the local SQLite operation contract and add a transactional Firestore
implementation for idempotency, stage slots, fencing, attempt records, and dispatch
intent. Add finite Cloud Run CPU jobs and a private, one-minute coordinator for
dispatch and reconciliation. Keep one authoritative application retry ceiling and
zero platform retries. Resume only from durable accepted checkpoints; reconcile
uncertain provider outcomes before any retry.

Acceptance: emulator and fault-injection tests cover concurrent claims, duplicate
delivery, quota reservations, stale workers, crashes around dispatch, job termination
after accepted checkpoints, uncertain outcomes, and no duplicate paid retry. Local
SQLite scheduling remains usable.

### Phase 3 — Hosted API, storage, and reader paths

Add explicit hosted mode and authenticated Next-to-private-API transport for studio,
requests, assets, and operations. Preserve separate Cloud Run caller and Firebase
user verification. Use bounded object uploads and trusted artifact references, not
chapter-sized request bodies. Materialize projects in disposable worker storage;
acknowledge checkpoints only after their referenced audio and evidence are durable.
Serve private published audio through authenticated same-origin streaming and
byte-range requests. Enforce UTC reader quotas transactionally. Preserve frontend
guards until the complete path passes acceptance.

Acceptance: offline and emulator-backed flow covers request, admin approval,
production, exact export review, publication, catalog and authenticated playback.
Anonymous/reader users cannot access admin operations, drafts, source artifacts,
unpublished audio, or another reader's notes. Request, page, and monthly production
limits resist concurrent submissions and retries. Local behavior remains covered.

### Phase 4 — Operations, cost controls, and rollout preparation

Use dedicated service identities and narrow IAM. Keep browser Firestore access
denied, buckets private, secrets in Secret Manager, and ordinary reads free of
provider initialization. Add idempotent budget reservations, threshold alerts,
production pause controls, quota visibility, and reference-aware seven-day orphan
collection. Record candidates and rollback targets before any rollout.

Acceptance: failure injection proves production pause preserves login and playback,
cleanup preserves all live references, and rollback retains durable state. Code
review each phase and implement all findings before advancing.

### Phase 5 — Separately authorized live validation

Only after offline implementation and review, obtain task authorization for cloud
deployment, representative CPU inference, and a tightly bounded provider test. Verify
App Hosting's monorepo build, deployed IAM, Firestore/GCS preconditions, restart
recovery, real session revocation, measured quality/performance/cost, browser
playback, rollback, and actual billing controls. Record revisions, commands, costs,
and acceptance evidence. Human cast/script decisions, audio review, and publication
remain explicit. Keep this phase gated; this document alone authorizes no deployment,
paid calls, account changes, or publication.
