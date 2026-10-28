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
