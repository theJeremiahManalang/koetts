# S4 shared requests and publication

Objective: implement the approved four-phase S4 plan on
`feat/shared-managed-request`. The user approved automatic continuation through
phase gates and passing, scoped commits. All four phases and local acceptance are
complete; the completion evidence is in `docs/alignment-status.md`.

## Decisions and boundaries

- Deduplicate by whitespace-normalized, case-folded title, chapter number and the
  default audio configuration. Each reader owns a separate request and original notes.
- Reader statuses are pending, approved and published. Admins see all notes and link
  one existing valid studio project per chapter work. Relinking invalidates old review
  identities and retains any accepted publication.
- Admin audition candidates are immutable copies. Explicit review and publication
  remain separate decisions bound to revision, export version, settings and checksums.
- Published audio requires verified reader identity plus an expiring token. Source
  images stay private. Future manga-page API and cloud shared storage remain outside S4.
- No live publication, paid generation, model inference, deployment or credential change
  was performed. Tests use synthetic decisions and audio in disposable workspaces.

## Completed work

Engine request/review/publication storage, trusted worker orchestration, authenticated
Next routes, reader token/range delivery, request/admin/studio integration, published
catalog and playback are implemented. CLI and web exports share version invalidation.
Reader and admin audition audio survive same-user renewal. Reader accessibility
controls remain available. Old browser-local data is untouched and is not imported.

Changed boundaries include `manga_tts.shared_requests`, shared router export metadata,
`manga_worker.shared` and workflow services, web identity/shared APIs and existing
request/library/studio screens. Documentation and acceptance tests cover these paths.
See `docs/alignment-status.md` for the requirement-by-requirement evidence.

## Verification

Pinned Node 22.22.3/npm 10.9.8 and uv 0.11.16/Python 3.11.15 were used for final gates.

- `PATH=/home/ssuish/.nvm/versions/node/v22.22.3/bin:$PATH UV_CACHE_DIR=/tmp/manga-s4-uv-cache npm run check`
  passed: repo checks, Ruff, 117 Python tests (two optional skips), 55 web tests,
  typecheck and production build. Log: `/tmp/manga-s4-complete-check.log`.
- `PATH=/home/ssuish/.nvm/versions/node/v22.22.3/bin:$PATH UV_CACHE_DIR=/tmp/manga-s4-uv-cache npm run test:http`
  passed studio and frontend-only checks, including the complete fake-backed S4 flow.
  Log: `/tmp/manga-s4-complete-http.log`.
- `PATH=/home/ssuish/.nvm/versions/node/v22.22.3/bin:$PATH UV_CACHE_DIR=/tmp/manga-s4-uv-cache .venv/bin/python /tmp/manga-s4-browser-runner.py`
  passed Chromium at 1440×900 and 390×844, including actual playback/seeking, reader
  and admin renewal, accessibility, requests, publication and linked studio navigation.
  Log: `/tmp/manga-s4-pinned-browser.log`. Browser dependencies and fixture identities
  were replaced only in the disposable copy. Screenshots are temporary `/tmp` artifacts.
- Pinned `npm run build` passed after the final contrast adjustment. Pinned
  `npm run check:repo` and `git diff --check` passed after the documentation update.

The full suite skips HTTP without an externally supplied server (the separate runner
executes it) and external sample compatibility without a supplied sample. Initial
sandbox/cache build failures and earlier Node 24 checks are recorded separately in
alignment evidence; final pinned gates passed.

## Review and next action

Two-axis review against `ede54cd946143fa6f9c2a1fc847aacff6520b479` found no remaining
S4 spec gap. All blocking standards findings were fixed and re-reviewed, including
CLI export identity, audio-path integrity, review recovery and reader/admin renewal.
The trusted-snapshot data-clump observation was resolved with an immutable typed
`ExportSnapshot` at the existing locked worker boundary.

Next eligible work: resolve the S5 cloud inputs when that scope is assigned. No S4
work or external blocker remains. Cloud rollout authorization is not implied.

## FastAPI hardening follow-up

The user authorized resolving review findings, hardening the existing FastAPI API,
and pushing this branch with a pull request to main once review is clean.

Blocking identity verification, JSON decoding and workspace/queue calls now run in
worker threads. Operation requests enforce a 5 MiB streamed limit, unambiguous JSON
and headers, finite numbers, and bounded credentials. Private responses carry
no-store and nosniff headers; unexpected errors remain sanitized. Configuration
fails closed and service permissions are immutable. A shared initialization lock
prevents concurrent first Firebase requests from rejecting valid credentials.
Hosted verification mode remains unable to process workspaces.

Changed paths: worker HTTP API/authentication and their unit tests, engine shared
requests and trusted worker snapshot orchestration, plus architecture/alignment docs.

Pinned `npm run check` passed after the main hardening changes: 123 Python tests
(two optional skips), 55 web tests, repository checks, Ruff, typecheck and production
build. Log: `/tmp/s4-hardening-check.log`. The subsequent initialization-race fix
passed all 14 HTTP unit tests and Ruff. External sample compatibility remains skipped;
no live identity provider, inference or deployment was exercised.

Independent Standards and Spec re-review confirmed zero remaining findings after
`35b87f3`. Pinned `npm run test:http` passed studio and frontend-only integration
checks (`/tmp/s4-hardening-http.log`). Repository pointer validation and diff checks
also passed after documentation updates.

Branch pushed. Pull request #16 is open against main:
https://github.com/theJeremiahManalang/koetts/pull/16
GitHub reports the branch mergeable; Workspace checks are running.
Next action: inspect CI results; merge requires a separate instruction. No external blocker.

## PR #15 compatibility review

The user requested a read-only implementation review of PR #15 against their PR #16.
Pinned main: `ede54cd946143fa6f9c2a1fc847aacff6520b479`; PR #15:
`a5215cf5684f54b12f5e651f1e1b1f0230b7523d`; PR #16:
`8e6e67a296c46c5110013908d19604fa472fe6b9`.

Fetched both heads and inspected their three-dot diffs from main. A disposable
`git merge-tree --write-tree origin/pr-16 origin/pr-15` simulation returned conflict
status 1: seven content conflicts, with nine changed files overlapping. Output is
`/tmp/pr15-pr16-merge.txt`. No actual merge or application source edit was performed.

PR #15's Firestore `manga_requests` collection and `/api/requests` interfaces do not
implement PR #16's shared chapter-work identities, deduplication, project links or
publication fulfillment. Its dashboard replaces reviewed publication with manual
progress statuses. Taking its requests page also restores an import of the catalog
fixture deleted by PR #16. Its Delete interface retains browser-local behavior and
has commented-out confirmation controls, regressing PR #16's server deletion.
Independent Standards and Spec reviews examined these boundaries. This review used
source inspection and merge simulation; it did not run a resolved combined build or
live Firestore tests. No external comments, review submission or merge was authorized.

Next action: report integration blockers. Reconciliation should preserve one shared
request/publication contract and port selected UI improvements; introducing Firestore
requires an explicit adapter and existing-data migration decision. No implementation
or merge is included in this review request.

## Approved Firestore implementation — in progress

The user approved the proposed Firestore/dashboard plan with “Implement the plan”
and requires one commit per bounded phase (five commits). Keep PR #16's workflow;
port presentation/navigation only, retaining pending/approved/published statuses.
All shared metadata will support an explicitly selected Firestore backend, while
artifacts and processing remain local and hosted guards stay enabled. Leave the six
legacy manga_requests documents untouched; start a separate versioned namespace.
Read-only inspection found no results/web/shared.sqlite3 in this checkout.

Phase 1 started: extracted immutable artifact storage and verification into
manga_tts.shared_artifacts.LocalSharedArtifacts, with a disposable local verification
cache independent of metadata. SharedRequests now uses that artifact boundary;
existing artifact locations remain unchanged. These edits are uncommitted because
phase 1 still needs its metadata transaction interface extraction. Preserve the
preexisting uncommitted compatibility-review checkpoint in this file.

Checks: `UV_CACHE_DIR=/tmp/manga-s4-uv-cache uv run --locked python -m unittest
 tests.unit.engine.test_shared_requests tests.unit.worker.test_shared_service
 tests.unit.worker.test_web_workflow -q` passed 35 tests. Ruff for changed Python
modules and git diff --check passed. Full acceptance not yet run for this work.

Next action: finish metadata persistence separation, add focused boundary tests,
run full Python suite and commit completed phase 1. Then implement Firestore adapter,
dashboard improvements, cutover preflight, and final emulator/integration review as
four further bounded commits. No live data writes, deployment or PR update performed.


### Phase 1 completion

Metadata separation is complete: engine transaction protocols and SQLite adapter
are in shared_metadata.py; SharedRequests owns storage-independent decisions;
shared_artifacts.py owns immutable bytes and its disposable verification cache.
Existing SQLite schema, artifact locations and shared HTTP response shapes remain
compatible. Candidate/review/publication identities are allocated outside retryable
callbacks; file operations occur before those callbacks.

Verification: full Python discovery passed 124 tests with two optional skips
(`/tmp/firestore-phase1-python.log`); all 35 existing shared tests passed. The added
rollback/retry regression passed in the five-test shared engine suite. Ruff passed
for changed modules/tests; no live data writes occurred. Phase 1 commit includes
this evidence and the earlier compatibility review checkpoint.

Next action: implement the worker-owned Firestore metadata adapter with explicit
project/database/dataset configuration, transactional uniqueness records and local
artifact-store binding; retain SQLite as default. Remaining phases are unchanged.

### Phase 2 completion

Added worker-owned FirestoreSharedMetadata and explicit backend selection. Required
Firestore settings are FIREBASE_PROJECT_ID, FIRESTORE_DATABASE_ID and
MANGA_SHARED_DATASET. SQLite stays default. Metadata transactions buffer all writes
until reads finish, use uniqueness documents and explicit candidate/review sequences,
and bind the namespace to .shared-artifact-store-id. No artifact I/O runs in SDK
retry callbacks. google-cloud-firestore==2.34.1 is an optional worker dependency;
pinned uv lock regeneration changed solver marker formatting without upgrading SDKs.

Verification: root `npm run test:python` passed 133 tests (eight optional skips),
log /tmp/firestore-phase2-python.log. Six Firestore emulator tests and three worker
service tests passed together, log /tmp/firestore-phase2-emulator.log. Emulator uses
only demo-shared-workflow/shared-tests on 127.0.0.1:8787; no live data writes.
Ruff, repository checks and diff checks passed. Initial retry tests injected the
wrong SDK failure point, then retained synthetic server locks; the corrected fixture
rolls back before raising a commit conflict and proves stable identities/one copy.

An installed Firestore emulator is running under exec session 36597, port8787;
log /tmp/firestore-emulator-phase2.log. Revalidate this handle before reusing it.
Next action: phase 3 dashboard presentation/navigation on existing /api/shared
contracts, then phase 4 cutover preflight and phase 5 final acceptance/review.

### Phase 3 completion

Ported selected dashboard improvements onto /api/shared endpoints. Added batched,
project-scoped requester profile names with safe fallback and no email exposure;
kept individual notes and all #16 link/audition/review/publication controls. Added
readable icon actions with hover/focus tooltips, active admin navigation, and Studio
context keyed by shared work. Preparing an unlinked work starts without reopening
or deleting an unrelated saved project; operation recovery still takes precedence.
No #15 request API, fixture catalog or manual status workflow was restored.

Verification: pinned npm run test:web passed all17 test files after updating the
existing mocked auth boundary for AccountNav. New tests cover batched/private names,
profile outages and Studio preparation. Pinned typecheck/build passed. Pinned
npm run test:http passed studio and frontend-only checks. Logs:
/tmp/firestore-phase3-{web,typecheck,build,http}.log. Repository checks and diff
checks passed. No live profile lookup or data write was performed.

Next action: phase 4 read-only cutover preflight and runtime refusal of unsafe
backend changes, then phase 5 emulator runner/full acceptance/independent review.

### Phase 4 completion

Added shared_cutover read-only CLI and runtime cutover guards. It inventories local
SQLite in read-only mode, target collections/schema/artifact owner and legacy count.
Explicit binding blocks silent SQLite fallback. App-stopped rollback removes only
an empty-target binding; initialized Firestore requires reconciliation. Existing
SQLite data, schema/identity mismatches and orphan/unknown target collections block
activation. Environment example and developer documentation describe these steps.

Live read-only preflight passed for koetts-9bf7f/koetts-default/local-studio:
no local shared DB, no target namespace, no identity/binding, six legacy records.
Report: /tmp/firestore-phase4-live-preflight.json. No live writes or migration applied.
Emulator+service13 tests passed (/tmp/firestore-phase4-emulator.log). Root Python
137 tests passed,12 optional skips (/tmp/firestore-phase4-python.log). Ruff, repository
pointer checks and diff checks passed. Next: phase5 reproducible emulator runner,
shared backend contract parity, full acceptance, independent Standards/Spec review.

### Phase 5 completion and handoff

All five approved phases are implemented. Phase commits so far:276493f (metadata/
artifacts),47de463 (Firestore),044b96e (dashboard),4016c91 (cutover); the final phase
commit contains emulator tooling/CI, shared contract parity and review fixes.

Independent Standards/Spec review against original PR16 head8e6e67a plus the final
working tree reports zero remaining findings. Resolved atomic-marker startup and
crash-durability findings with a common temp/fsync/link/directory-sync helper. Even
matching existing bindings synchronize before remote operations. Empty rollback
synchronizes directory removal. Concurrent marker writers see one complete value.

Final verification, pinned Node22.22.3/npm10.9.8 and uv0.11.16/Python3.11.15:
- npm run check passed: repository boundaries/pointers, Ruff,143 Python tests
  (17 optional skips),58 web tests,typecheck,production build.
  Log:/tmp/firestore-final-check.log.
- npm run test:firestore passed24 tests using a disposable version/checksum-pinned
  loopback emulator and demo project. Includes15 emulator tests, the shared SQLite
  contract and worker service regressions. Log:/tmp/firestore-final-emulator.log.
- npm run test:http passed the entire synthetic local S4 flow with explicit
  emulator-backed Firestore metadata, and separately passed frontend-only guards.
  Log:/tmp/firestore-final-http.log. Backend environment was inherited by the
  disposable runner; it did not select SQLite for the shared flow.
- uv run --locked python tools/verify_fresh_checkout.py passed frozen installs,
  checks/tests, lightweight environment and external-directory entrypoints.
  Log:/tmp/firestore-final-onboarding.log.
- Final binding synchronization change passed the dedicated24-test emulator gate
  and Ruff. Repository checks/diff checks passed after documentation updates.

The15 normal-discovery emulator skips are covered by the separate emulator gate;
external sample compatibility remains skipped. HTTP's normal-discovery skip is
covered by the separate runner. Live read-only preflight confirmed six excluded
legacy records, no target namespace or local SQLite data; no migration required.
No live Firestore writes, real human review/publication, inference, paid generation,
IAM/rules change or deployment occurred. Production hosted integration remains S5.

PR16 is the existing handoff target:
https://github.com/theJeremiahManalang/koetts/pull/16
Next action after branch update: inspect CI/review PR16. Merge and deployment require
separate instruction. No implementation blocker remains.

## Hosted service implementation — phase 0

- Objective: implement approved full GCP/Firebase hosted-service plan on
  `feat/hosted-service`, created from fetched `origin/main` at the prior main head.
- Authorization: user instructed implementation, separate feature branch, a
  `$caveman-commit` for each substantial phase, and `$code-review` after each phase
  with review findings fixed before advancing. User confirmed hosted pilot limits,
  separate infrastructure/provider budgets, clean cloud dataset, request quotas,
  authenticated audio streaming, and CPU failure blocking full hosted launch.
- Phase 0 scope: documentation only. Added `docs/hosted-service-plan.md` as
  implementation spec, recorded resolved S5 planning choices in `docs/target-design.md`,
  and added ADR 0001 for the distributed hosted execution choice. These do not claim
  cloud integration or live verification.
- Decisions: public Google signup; five pending and ten successful new requests per
  reader per UTC day; five new chapter works/month and forty pages/chapter; twenty
  active readers as sizing target, not signup cap. Infrastructure target USD 10/month,
  desired maximum USD 20 (not guaranteed); alert at 10/15/20 and pause new production
  at reported USD 15 or earlier when reservations exhaust allowance. Existing
  developer-controlled USD 80 provider budget is separate. Scale-to-zero CPU jobs,
  one slot per stage, one-minute coordinator; Cloud Run retries zero and durable
  operation ceiling three, 30-minute timeout, 15-second heartbeat, 60-second lease.
  Keep existing Firebase project/backend/database, use us-east4 regional resources,
  and use a clean cloud dataset. Preserve referenced artifacts; collect only
  unreferenced temporary objects after seven days. Authenticate each audio range
  request through same-origin streaming.
- Changed paths: `docs/hosted-service-plan.md`, `docs/target-design.md`,
  `docs/adr/0001-hosted-execution.md`, `CONTEXT.md`.
- Checks: `uv run --locked python tools/check_repo.py` passed; `git diff --check`
  passed. Phase review remains required before phase 1.
- Blockers: no phase 0 blocker. Live deployment, CPU benchmark, paid-provider test,
  and hosted acceptance remain gated as specified.
- Next action: run scoped documentation checks, review/fix findings, commit phase 0,
  then begin durable cloud persistence only after phase review is clean.

### Phase 0 review resolution

Standards review found one conflicting-authority finding and duplicate policy lists.
Spec review found the same stale S5 status plus ambiguous pending-quota wording.
Resolved by making hosted-service-plan the single policy authority, replacing stale
open decisions with remaining implementation/measurement inputs, and specifying
five outstanding pending requests at any time separately from ten new requests/day.
No runtime behavior changed. Phase 0 implementation commit: 5c41b81.

### Hosted phase 1 — ready for review

Phase0 Standards/Spec rechecks both clean at248d219; implemented phase1 from that
fixed point. Worker cloud.py builds explicit cloud stores; cloud_artifacts.py handles
frozen create-only uploads, verified exact generations and disposable shared caches;
cloud_revisions.py owns Firestore revisions, fences and artifact references. Optional
worker cloud extra pins existing SDK versions without dependency upgrades. Shared
cloud selector and stable storage identity preserve local defaults and fail closed.
Docs, environment example and emulator runner describe/exercise the boundary.

Checks: /tmp/hosted-phase1-check.log passed pinned full check:162 Python tests with
24 skips,58 web tests,Ruff,repo,typecheck/build. /tmp/hosted-phase1-firestore.log
passed34 tests (10 hosted), demo projects/loopback only. Focused artifact/settings
tests passed13 after final cache namespace check; Ruff/diff check pass.
/tmp/hosted-phase1-http.log production HTTP plus frontend-only checks passed.
/tmp/hosted-phase1-onboarding.log frozen fresh-checkout passed with pinned Node22;
initial Node24 attempt failed EBADENGINE and was corrected. Workers' first sandbox
HTTP discovery stalled and was interrupted; authoritative escalated root suite passed.

Authorization unchanged: implementation/commits/reviews approved, deployment, paid
inference/provider tests and human publication remain gated. Existing local data and
legacy records preserved. No phase1 live durability claim. Next: commit phase1, run
independent Standards/Spec review from248d219, fix findings and recheck before phase2.

### Hosted phase 1 review complete

Implementation commit92083d9, reviewed against248d219. Independent Standards and
Spec axes both report zero findings. Persistence phase is complete for offline
implementation; no live cloud durability claim. Phase2 may now begin: abstract the
operation store, transactional Firestore scheduling/attempts/outbox, finite jobs and
execution-identity reconciliation. Keep PID reconciliation local-only.

### Hosted phase 2 — implementation ready for review

Phase2 starts at8dd4b42 after clean phase1 reviews. Added common OperationStore
protocol, injected workflow store/root seams, Firestore operation store, Cloud Run
v2 job control, dispatcher/reconciler, finite worker runtime, service-only coordinator
and image targets/context allowlist. CloudStores exposes artifacts/revisions and
ProjectPersistence.current reads accepted revision without scratch mutation.

Integration fixes: v2 LRO metadata.name and CONDITION states; only completionTime
permits terminal treatment; uncertain rows remain candidates; pending intent recovery
uses CAS while submitting intents never blindly re-run; empty execution cannot prove
stop; failed writer release retains slot. Writer release precedes operation completion
or retryable failure. Provider base revision is persisted before calls. Restart test
terminates a synthetic render after accepted first segment, requires explicit operator
retry for uncertain next call, then restores fresh scratch without regenerating first.

Checks: /tmp/hosted-phase2-final-check.log passed218 Python tests(43 optional skips),
58 web tests,Ruff,repo,typecheck/build. /tmp/hosted-phase2-final-firestore.log passed50
loopback/demo tests, covering15 operations+10 persistence+1 real-engine interrupted
render plus prior shared contracts. Docker image builds remain unverified: Docker
unavailable in this WSL environment. /tmp/hosted-phase2-http.log running under exec
session73198; revalidate handle before claiming result. No paid/live cloud work.

Changed boundaries: engine operations/persistence, worker cloud modules/workflow/HTTP,
focused unit/emulator tests, image files and documentation. Next: commit phase2, run
Standards/Spec review from8dd4b42, implement findings and recheck before phase3.
Final task remains full hosted product; browser transport, public quotas, cost controls,
reference-aware cleanup, deployment preparation and separately authorized live gates
are not yet complete.

### Hosted phase 2 review resolution

Phase2 implementation6cc4ebc reviewed independently against8dd4b42. Standards found
one duplicate ProjectPersistence.current definition introduced during integration;
removed duplicate and retained original behavior plus docstring. Spec found zero
phase2 findings. Correct earlier handoff wording: current() already existed; this
phase only documents it, rather than adding a new API. Affected persistence/runtime
unittest suite passed21 tests after fix. HTTP exec73198 is complete, exit0; log
/tmp/hosted-phase2-http.log passes production and frontend-only checks.

Zero-platform-retry policy is specified for deployment; actual deployed job templates
have not been created or verified. Docker build and real Cloud Run/GCS behavior remain
unverified. Next: commit fix, recheck Standards finding, then phase3 hosted transport,
public intake quotas and authenticated streaming. No cloud deployment authorized.
