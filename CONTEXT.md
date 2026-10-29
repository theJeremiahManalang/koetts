# Hosted service implementation

## Objective and authorization

Implement the approved full GCP/Firebase hosted-product plan on `feat/hosted-service`.
The branch starts from main commit `0bdacc5cd0092cf33d53afb4d12f6b64b5ba16bb`.
The user authorized implementation, substantial commits using caveman-commit,
independent Standards/Spec code review per phase, and fixing findings before
advancing. Ask the user when critical decisions are needed.

Deployment, paid generation/inference tests, human production approvals, and real
publication remain separately gated. None occurred during this implementation.
Keep saved local results, credentials, model caches, and legacy requests intact.

The authoritative specification and pilot limits are in
[the hosted plan](docs/hosted-service-plan.md). Runtime source establishes behavior;
[alignment status](docs/alignment-status.md) records phase evidence.

## Current implementation

Phases 0–2 passed their scoped reviews. Cloud artifacts and revisions are optional
worker adapters. Firestore operations coordinate stage/project slots, attempts,
fences, dispatch intent, and execution reconciliation. Finite Cloud Run jobs restore
accepted checkpoints into disposable scratch. Local SQLite and CLI behavior remain.

Phase 3 is implemented except for the critical monthly-admission identity driver:

- Next uses explicit cloud HTTP transport; local Python execution fails closed in
  cloud/frontend-only mode. Individual uploads are bounded, then operations submit
  compact JSON. Browser-supplied artifact identities never establish trusted refs.
- The private API independently verifies service and Firebase identity, derives
  actors, separates reader/admin actions, rejects stale project hashes, and preserves
  idempotent intent recovery after accepted state changes.
- Shared audio streams through same-origin authenticated range requests. Cloud mode
  requires an explicit signing secret; no local signing-key fallback is selected.
- Hosted request quotas use transactional metadata and a persistent daily ledger.
  A monthly chapter ledger and atomic enqueue hook exist, but are not wired to
  production until the user resolves chapter identity policy.
- Shared reviews read immutable snapshots and check the exact project pointer in
  the same Firestore metadata transaction. They do not acquire unrecoverable API
  writer ownership. Actual project edits retain writer fencing and ownership.
- Projectless OCR derives stable identity from its intent token. Exhausted duplicate
  enqueue transactions can recover only an already-committed matching intent.

Frontend-only deployment guards remain enabled. This is not a deployed hosted product.

## Critical decision still pending

An asynchronous question was sent and no answer has arrived:

1. Require approved shared chapter work before hosted project creation (recommended).
2. Allow unlinked projects; each new project consumes one monthly chapter allowance.

Do not infer an answer from elapsed time or automatic goal continuations. This choice
changes the production identity driver and monthly admission tests. Phase 3 cannot
close, and phase 4 cannot begin, until the driver is implemented and reviewed.

## Commits and review

- `92083d9`: cloud persistence; phase 1 Standards/Spec review was clean.
- `6cc4ebc`: distributed jobs; duplicate helper fixed in `06d4808`, then clean review.
- `1db72bf`: hosted transport/intake checkpoint, reviewed against `06d4808`.
- `fa1cfc3`: fixed unstable projectless OCR retry identity.
- `912b532`: unified shared metadata dispatch and removed unused workspace helper.
- `fd33acc`: replaced short API review writer claims with transactional revision guards.
- `7133eab`: recovered matching committed intents after SDK transaction contention.
- `064f9f4`: corrected the hosted workspace footer label.

Phase 3 Standards review found no hard violations and two maintainability findings;
both were fixed. Spec review found OCR idempotency and unwired monthly admission.
OCR is fixed; monthly admission remains the explicit policy blocker. Independent
rechecks found no new material issue in revision guards or contention recovery.
Review does not establish live provider/platform behavior.

## Verification

Use Node 22.22.3/npm 10.9.8 and uv 0.11.16/Python 3.11.

- `npm run check` passed: 251 Python tests ran with 62 optional skips; 80 web tests
  passed; repository checks, Ruff, typecheck, and production build passed. Log:
  `/tmp/hosted-phase3-reviewed-check.log`.
- `npm run test:firestore` passed 73 loopback/demo tests, including the normal-suite
  emulator skips, guarded publication races, atomic admission, and interrupted
  rendering. Log: `/tmp/hosted-phase3-guard-firestore.log`.
- `npm run test:http` passed local production studio and frontend-only boundaries
  after shared dispatch refactoring. Log: `/tmp/hosted-phase3-reviewed-http.log`.
- The direct pinned-Node hosted OCR retry regression passed after review fixes.
- One emulator run exhausted SDK retries under duplicate first-enqueue contention.
  The matching-intent recovery fix has deterministic coverage; the subsequent full
  emulator run passed. A separate stale-revision fixture was corrected to supply a
  valid expected hash while retaining independent stale-rejection tests.

Browser plugin was unavailable. Cached Playwright/Chromium tested a disposable
synthetic-identity/private-transport app with Next webpack dev fallback: two separate
68-byte uploads, one 301-byte operation submission, and a controlled failure that
retained selections. No app console/page errors, external requests, or mobile
horizontal overflow were observed. Evidence: `/tmp/hosted-phase3-browser-evidence.json`,
private API JSONL, server log, and desktop/selection/failure/mobile screenshots with
the same prefix. The owned server and disposable source copy were removed.
This does not verify real Google sign-in or the App Hosting production adapter.

Container builds remain unverified because Docker is unavailable. No live GCS
semantics, deployed job settings, paid-provider compatibility, or listening quality
are claimed. Temporary evidence can disappear between environments; rerun checks
when needed rather than treating missing logs or old process handles as live work.

## Next action

Obtain the monthly identity decision, implement the production admission driver
atomically with enqueue, add its end-to-end tests, and finish phase 3 review.
Then implement phase 4 budget controls, reference-aware cleanup, narrow infrastructure,
rollout/rollback preparation, and monitoring. Only after offline completion and review
request concrete authorization for the separately gated live validation phase.
The full goal remains active and incomplete; do not mark it complete.
