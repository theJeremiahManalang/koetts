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

Phase 3 final admission and bounded metadata-view work is in progress:

- Next uses explicit cloud HTTP transport; local Python execution fails closed in
  cloud/frontend-only mode. Individual uploads are bounded, then operations submit
  compact JSON. Browser-supplied artifact identities never establish trusted refs.
- The private API independently verifies service and Firebase identity, derives
  actors, separates reader/admin actions, rejects stale project hashes, and preserves
  idempotent intent recovery after accepted state changes.
- Shared audio streams through same-origin authenticated range requests. Cloud mode
  requires an explicit signing secret; no local signing-key fallback is selected.
- Hosted request quotas use transactional metadata and a persistent daily ledger.
  The monthly chapter driver now checks approved work and reserves capacity with
  enqueue; final tests and review remain.
- Shared reviews read immutable snapshots and check the exact project pointer in
  the same Firestore metadata transaction. They do not acquire unrecoverable API
  writer ownership. Actual project edits retain writer fencing and ownership.
- Projectless OCR derives stable identity from its intent token. Exhausted duplicate
  enqueue transactions can recover only an already-committed matching intent.

Frontend-only deployment guards remain enabled. This is not a deployed hosted product.

## Resolved monthly admission decision

On 30 October 2026 the user replied "1": new hosted projects require approved
shared chapter work. The application must check the work and its recorded approval
in the same transaction as monthly reservation and operation creation. The monthly
allowance counts verified work IDs. Creation does not implicitly link the project.
Local creation remains unchanged; standalone OCR creates no durable project.

The driver and UI gating are being verified. Phase 3 review must confirm this
remaining requirement before phase 4 implementation begins. The prior critical
question is resolved; do not ask it again or keep treating it as a blocker.

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
OCR is fixed; the user has now resolved monthly identity policy. Driver acceptance
and review remain. Independent
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

Finish phase 3 approved-work driver acceptance, bounded metadata views, and review.
Then implement phase 4 budget controls, reference-aware cleanup, narrow infrastructure,
rollout/rollback preparation, and monitoring. Only after offline completion and review
request concrete authorization for the separately gated live validation phase.
The full goal remains active and incomplete; do not mark it complete.

## Current verification work after policy resolution

Approved-work backend and UI changes are uncommitted. The first full check exposed a
hanging full-workspace React test fixture and a TypeScript nullability error. The
fixture is now a bounded request-context harness, and eligible work state is captured
before await. The owned obsolete test processes were verified and terminated; this
was not a product runtime hang. Pinned isolated typecheck and focused tests passed.

A repeated first-enqueue emulator contention failure exposed namespace initialization
range-lock cycles. Binding initialization now uses a separate root-only transaction
before domain mutation; read-only calls do not initialize and fail closed on orphaned
records. Expanded race/orphan regressions require parent emulator acceptance.

A worker is removing readonly cloud snapshot/enqueue overfetch through accepted
manifest metadata. It owns workflow snapshot/fingerprint helpers, resolution.page_image
existence injection, and CloudApplication snapshot/source-fingerprint methods. Another
worker completed only CloudApplication upload/binding initialization. Preserve these
concurrent edits. No phase 4 implementation, deployment, or paid call has begun.

## Phase 3 policy implementation verification

The approved-work driver is implemented. It validates the bound shared work and
its explicit admin approval in the same Firestore transaction as chapter allowance
and enqueue. Distinct work IDs count once per UTC month; no automatic project link
is created. The UI requires verified approved/published context before uploading,
and work identity participates in retry keys. Tests cover missing/pending/fake work,
approval races, five-work capacity, same-work replacements, and idempotent retries.

Namespace initialization now uses a root-only initialization transaction, avoiding
first-mutation range-lock cycles. It rechecks concurrent valid root publication and
rejects orphan reads. The initial added UI fixture hung; a bounded context harness
replaced it. TypeScript work-state narrowing and two new metadata test fixtures were
corrected; no product auth bypass or live provider call was used.

Read-only cloud snapshots/source fingerprints now use accepted immutable manifest
checksums rather than hydrate source/audio bytes. Actual asset fetch and worker
restore still verify exact generation bytes. Export review hydrates only required
export files. The interrupted worker's changes were inspected and verified by the
parent after daemon restart.

Final pinned acceptance: /tmp/hosted-phase3-accepted-final-check.log passed 263 Python
tests (71 optional skips), 86 web tests, repository checks, Ruff, typecheck and build.
/tmp/hosted-phase3-policy-accepted-firestore.log passed 82 loopback/demo tests.
The daemon restart removed child handles; no old process was assumed live.
Rendered approved-work UI QA is being rebuilt in a disposable fixture. Next: commit
phase 3 policy and bounded-view changes, run independent Standards/Spec review and
resolve findings before phase 4. No deployment or paid call is authorized yet.

## Phase 3 closed; phase 4 in progress (2026-10-30)

The earlier pending phase 3 statements above are superseded by this checkpoint.
Approved-work admission and metadata-only views were committed as `79f3121`.
Independent Standards review found one optional duplication smell; Spec review
reported no findings. Artifact lookups were consolidated in `fef5b8a`, with a
read-only follow-up confirming preserved local and metadata behavior. All 33
workflow tests, Ruff and diff checks passed. The final HTTP verification passed
local and frontend-only checks in `/tmp/hosted-phase3-policy-final-http.log`; its
initial sandbox attempt could not write the pinned uv cache and was rerun with
required environment access.

Rendered UI QA passed missing, pending and approved work contexts; verified two
bounded uploads followed by one enqueue containing the work ID; retained images
on a controlled failure; and passed desktop/mobile overflow and browser error
checks. Evidence: `/tmp/hosted-approved-work-browser-evidence.json`. This used
synthetic auth/backend fixtures, not live Google or provider calls.

Phase 4 starts at `fef5b8a`. Current uncommitted changes add a fail-closed durable
USD-micro budget ledger and integrate it into hosted enqueue, transactional
claims, extraction startup and every paid-call boundary. Provider allowance and
measured stage caps require explicit developer configuration; no automatic USD80
renewal occurs. Infrastructure reports use interval highwater marks and latch a
pause. Conservative reservations survive retries and completion; explicit audited
reconciliation cannot erase outstanding reservations or call debits. Production
status/pause HTTP endpoints require both explicit service permissions and Firebase
admin identity. Published playback and identity remain independent of this gate.

The offline rollout record tool captures the candidate SHA/dirty state and explicit
prior software rollback targets; it does not discover or invent cloud state.
`docs/hosted-rollout.md` describes preparation and durable-data-preserving rollback.

Verification: first new ledger emulator run failed three test-fixture cases using
inactive transactions or reading a reservation before its deferred writer committed.
Fixtures were corrected. Worker rerun passed all 88 emulator tests. Parent rerun is
session 55183, log `/tmp/hosted-phase4-budget-firestore-fixed.log`. Normal acceptance
is session 84434, log `/tmp/hosted-phase4-budget-check.log`. New runtime pause tests
passed (15 runtime tests total); three HTTP production-control tests passed with
normal environment access. The sandboxed HTTP test process stopped making progress;
its exact PID 20389 was identified and terminated after the equivalent tests passed.

Remaining phase 4 work: authenticated budget notification ingestion and operator
configuration tooling, quota visibility in the product, reference-aware seven-day
cleanup with promotion-race protection, narrow IAM/declarative infrastructure and
secret configuration, rollback evidence, then full independent Standards/Spec
review and all fixes. Phase 5 remains separately gated: no deployment, paid test,
real production approvals or publication has been authorized or performed.
The full goal remains active and incomplete.
