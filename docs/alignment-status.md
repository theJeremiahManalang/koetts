# Architecture alignment acceptance evidence

## S0 — Complete, 19 October 2026

Assignment: reproduce the existing application baseline and deepen local worker
interruption/recovery evidence. This report records fresh execution, not a claim
inherited from the historical baseline. No runtime API, schema, engine, dependency
manifest, lockfile, build-tool selection, or cloud configuration changed.

All S0 acceptance criteria passed after resolving the local verification environment.
Initial Python and build failures are retained below.

### State at the S0 checkpoint

S1 was the next eligible scope at that checkpoint; its edit ownership, stale-worker
promotion, and fence lifecycle decision was unresolved in `target-design.md`.
No later scope had been implemented at the time of this S0 report.

### Requirement mapping

| Requirement / observable invariant | Fresh evidence and initial gap | Change and verification | Result |
| --- | --- | --- | --- |
| Local startup uses an available, compatible Python interpreter | No repository `.venv` or `python`; system `python3` is 3.10.12, below documented 3.11+ | Used installed Python 3.11.15 in a temporary audio environment. Production HTTP runner explicitly supplies its own interpreter to Next. Updated startup instructions. | Passed: actual worker snapshot, restore, mutations, and export through loopback Next server |
| Frontend tests, typecheck, production build have reproducible outcomes | Existing Node dependencies present; initial sandbox build could not bind an internal port | Ran existing npm scripts. Preserved failed build cache and reran default build with fresh cache and execution permissions. | Passed: frontend assertions, typecheck, and default Turbopack build; initial failures recorded separately |
| Backend contracts survive baseline verification | Initial discovery had seven import errors due to missing Pillow | Installed existing audio manifest into temporary environment; ran full discovery including real MP3 encoding/decoding | Passed: 46 discovered, 44 passed, two optional skips |
| A competing writer cannot change saved project state | CLI and worker use the same exclusive sibling lock | While actual render worker waits on its second segment, another worker attempts rename; failure leaves checkpoint bytes and owner lock unchanged | Passed in `test_worker_process.py` |
| An interrupted render preserves completed audio; restart reuses it | Existing test covered renderer exception, not process death | Kill child after first checkpoint and during second renderer call; wait for exit, verify retained bytes/hash, remove only test-owned stale lock, restart with current fingerprint | Passed: first take identity/audio retained, only unfinished segment generated |
| Stale mutation cannot overwrite checkpoint | Worker compares supplied project fingerprint before mutation | Separate child submits pre-render fingerprint after interruption; HTTP test submits old fingerprint after successful rename | Passed: failed jobs; saved project bytes or returned snapshot unchanged |
| Recovery remains exportable and restorable | Existing engine exposes export and bundle seams | Export resumed project, bundle/restore into empty temporary workspace, compare compiled WAV hashes | Passed without provider client |
| Local API, reader demo, and hosted frontend-only boundary survive | HTTP test previously required externally managed server and wrote into repository results | Added disposable runtime runner; production studio and frontend-only builds/servers run separately | Passed: five page routes, upload/restore/poll/reuse/export/bundle/range response, redirect, all processing guards |
| Existing edits, supplied samples/results, duplicate code remain intact | Initial tree: modified `AGENTS.md`, untracked `docs/agents/`; older UI/test copies exist | Preserved existing edits. All new worker/HTTP projects use temporary directories; no duplicate removal | Passed; no result/sample changes |

### Execution paths and boundaries

- **Studio:** `web/app/page.tsx` imports workspaces from `web/components/`.
  Review helpers used by those components are `web/lib/script-review.ts` and
  `web/lib/source-order.ts`. Same-named workspaces in `web/app/` are not the active
  root-page imports. TypeScript's broad include still encompasses these older files.
  `npm test` selects `web/tests/*.test.cjs`; duplicate tests under `web/lib/` are not
  selected. No cleanup was performed.
- **Workflow:** `web/app/api/workflow/route.ts` validates/stages requests and calls
  `web/lib/workflow.ts`. Node persists request/job JSON, launches `web_workflow.py`,
  and exposes polling. Python `run_job` acquires `manga_tts.cli.workspace_lock`;
  `perform` validates the expected project fingerprint before applied mutations.
  Typed operations enter `PipelineRouter`; CLI review/application reaches the same
  engine and writer lock. Node's two-job limit remains process-local.
- **Checkpoint:** `PipelineRouter.render_selected` supplies `_commit` to
  `tts.render_scene`. Validated WAV data is placed in its take path before project
  state is saved. `_commit` validates and saves the candidate before publishing
  in-memory state and notifying observers. A checkpoint includes selected-take
  metadata and referenced audio; notification is not itself persistence.
  `storage.write_json` replaces a temporary JSON file. The new test proves process
  restart recovery at a completed checkpoint, not filesystem power-loss durability.
- **Interruption:** forced termination leaves the Python job `running` and its
  sibling lock present. Recovery remains manual: confirm the recorded owner exited,
  remove its stale lock, reload saved state, and submit a new job with current
  fingerprint. No automatic job reconciliation, retries, lease, or fence was added.
- **Artifacts:** engine project state, evidence, takes, exports, and bundles remain
  local. `web/app/api/asset/route.ts` enforces path boundaries and serves ranged WAV
  playback and bundle downloads. Export synthesizes nothing. Export is not a
  multi-file publication transaction; interrupted export is not claimed atomic.
- **Extraction/hosting:** legacy `web/app/api/extract/route.ts` independently retains
  interpreter precedence. Workflow, extraction, and asset handlers retain frontend-only
  503 guards; `web/next.config.mjs` retains the `/` to `/browse` redirect. Reader
  pages still use demo data. Loopback/origin checks remain transport checks, not auth.

Changed boundaries: test harnesses and acceptance documentation only.
`tests/worker_process.py` injects an offline renderer in a child process while
executing the real Python worker. `tests/test_worker_process.py` owns temporary
fixtures, synchronization, termination, writer exclusion, and restart checks.
`tests/test_web_http.py` now verifies stale HTTP mutation rejection.
`tests/verify_local_http.py` owns a disposable runtime copy and server lifecycle;
production mode uses the unchanged `npm run build` and `npm start` scripts.
`web/README.md`, `docs/README.md`, and root `GLOSSARY.md` document the verified
boundary and terms. No consequential architectural tradeoff required an ADR.

### Reproduction commands and observed outcomes

Commands below ran from the repository root unless a working directory is shown.
Python, Node, npm, and uv versions were Python 3.11.15, Node v24.18.0, npm 11.16.0,
and uv 0.11.16. Installed Next was 16.4.0. Existing npm dependencies/lockfile were
used; neither npm dependency installation nor a model download was needed.

```bash
# Discover an installed interpreter without changing the host cache.
UV_CACHE_DIR=/tmp/manga-s0-uv-cache uv python list --only-installed

# Prepare the isolated verification environment using an existing interpreter.
UV_CACHE_DIR=/tmp/manga-s0-uv-cache uv venv \
  --python /home/ssuish/.local/share/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python3.11 \
  /tmp/manga-s0-venv
UV_CACHE_DIR=/tmp/manga-s0-uv-cache uv pip install \
  --python /tmp/manga-s0-venv/bin/python -r requirements-audio.txt

# Full offline regression suite, including new process recovery test.
/tmp/manga-s0-venv/bin/python -m unittest discover -s tests -v \
  > /tmp/manga-s0-python-tests.log 2>&1

# Actual production builds, loopback servers, HTTP suite, and hosting guards.
/tmp/manga-s0-venv/bin/python tests/verify_local_http.py \
  > /tmp/manga-s0-http-production.log 2>&1
```

Dependency installation and loopback/build execution used the tool's execution
permission mechanism. On this host a sandboxed dependency fetch cannot reach the
registry. The HTTP runner copies dependencies rather than symlinking them outside
Turbopack's runtime root. It clears the Gemini key, runs against ephemeral ports,
terminates server process groups, and deletes all temporary projects. Tests use
synthetic human-review fixtures; no actual review or publication decision is made.

| Command / working directory | Observed final outcome |
| --- | --- |
| `npm test` / `web/` | Exit 0; eight assertions across two files passed. A later run rendered file-level totals; `npm test -- --test-reporter=tap` again reported eight passing assertions. |
| `npm run typecheck` / `web/` | Exit 0, including repeat after final frontend build |
| `npm run build` / `web/`, fresh `.next` and execution permissions | Exit 0; compile, TypeScript, page data, static pages, optimization completed; all nine application routes listed |
| Python discovery above | Exit 0; 46 tests, 44 passed, two skipped; final full run 3.018 seconds |
| Production HTTP runner above | Exit 0; two default production builds passed; HTTP integration test passed in 3.578 seconds on final run; both studio and frontend-only HTTP checks passed. Repeated after strengthening process-group cleanup. |
| `/tmp/manga-s0-venv/bin/python -m unittest discover -s tests -p test_worker_process.py -v` | Exit 0; focused process recovery test passed in 1.546 seconds |
| `git diff --check` | Exit 0; no whitespace errors |

The production runner checks HTTP 200 plus HTML for `/`, `/browse`, `/request`,
`/manga/echoes-of-tomorrow`, and `/read/echoes-of-tomorrow/chapter-1`.
Its HTTP integration test restores a synthetic approved project, polls jobs,
rejects a stale rename without changing snapshot, inspects/reuses audio, exports,
bundles, downloads, and validates a 206 WAV byte range. Existing missing-header and
traversal denials also passed. Frontend-only checks assert redirect to `/browse`
and 503 for workflow GET/POST, asset GET, and extraction POST.

The process recovery test verifies exactly three renderer calls: first completed
segment, interrupted second segment, and resumed second segment. It checks the
first take remains selected and its WAV bytes and recorded SHA-256 match before
and after termination/restart. Synthetic segment WAV SHA-256:
`2296dedfc652d804a8bea53c0ef86651f1304f4464859574b2ce52d43d6392a2`.
The compiled export hash is compared to the restored bundle's export within the
test. Random temporary paths, job IDs, take IDs, and bundles are not golden files.
Tests recreate these artifacts; no private or generated production audio is stored
in this report. `/tmp` logs are session artifacts, not required permanent evidence.

Audio environment snapshot (from `uv pip freeze --python /tmp/manga-s0-venv/bin/python`):

```text
annotated-types==0.8.0
anyio==4.15.1
certifi==2026.10.18
cffi==2.1.1
charset-normalizer==3.5.2
cryptography==50.0.2
distro==1.9.0
google-auth==2.62.0
google-genai==2.31.0
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.20
imageio-ffmpeg==0.6.0
pillow==12.3.0
pyasn1==0.6.4
pyasn1-modules==0.4.2
pycparser==3.11
pydantic==2.14.1
pydantic-core==2.50.1
requests==2.34.2
sniffio==1.3.1
tenacity==9.1.4
typing-extensions==4.16.0
typing-inspection==0.4.4
urllib3==2.8.0
websockets==16.1.1
```

### Failures, skips, and limits

- **Resolved dependency/environment failure:** initial
  `python3 -m unittest discover -s tests -v` used system Python 3.10.12 and produced
  seven import errors for missing `PIL`, plus one sample skip. It established no
  backend pass. The final isolated Python 3.11 environment supersedes this result.
- **Resolved setup attempts:** plain `uv python list --only-installed` could not
  write the host uv cache. A temporary cache resolved that restriction. An initial
  `uv venv --python 3.11` with a separate empty install directory attempted an
  unavailable runtime fetch; selecting the already installed absolute interpreter
  avoided downloading Python. Sandboxed dependency fetch retried without success;
  the execution-permitted installation succeeded.
- **Resolved build environment failure:** initial `npm run build` failed with
  `Operation not permitted (os error 1)` while Turbopack processed CSS and bound an
  internal port. Repeating with permissions but the existing `.next` still failed.
  The same source built in the disposable runtime. Moving checkout `.next` to
  `/tmp/manga-s0-original-next` using
  `mv web/.next /tmp/manga-s0-original-next` from the repository root and repeating
  `npm run build` in `web/` with permissions passed.
  This supports a fresh-cache retry, not a source/configuration defect. Failed
  artifacts remain preserved in `/tmp`; no bundler change or Webpack fallback ran.
- **Expected offline skips:** full discovery skipped HTTP integration because no
  external `MANGA_WEB_TEST_URL` was supplied; the production runner subsequently
  executed that test successfully against its own server. Sample compatibility
  remained skipped: `MANGA_TTS_SAMPLE_PROJECT` was unset and a fresh scan found no
  `results/**/project.json` candidates. Supplied source image was not modified.
- **Unverified, outside S0:** live MAGI weights/inference, Gemini compatibility,
  listening quality, browser interaction/visual accessibility, power-loss durability,
  real Firestore/GCS behavior, distributed scheduling/fences, authenticated access,
  publication, cloud deployment, and paid-provider billing. MP3 acceptance here
  establishes real local encode/decode with synthetic audio, not listening quality.

There are no remaining S0 acceptance blockers. Missing default host Python and
internal-port restrictions remain environmental conditions handled by explicit
interpreter selection, permitted execution, and fresh build artifacts. Do not
weaken runtime guards or infer future-scope acceptance from these local tests.

## S1 — Complete, 19 October 2026

Assignment: add a durable revision and artifact persistence seam while keeping the
local filesystem studio as the runtime default. No Project v2 schema migration,
cloud adapter, dispatcher, deployment, publication, or paid provider call was added.

### Decision and changed behavior

- Project writes have one exclusive owner. Each handoff increments a nonreused
  fence; commits require the active owner, fence, and expected parent revision.
  Competing edits return typed conflicts. An interrupted owner remains fenced until
  recovery confirms the worker stopped. S1 adds no timeout or automatic takeover;
  lease expiry and distributed reconciliation remain S2 decisions.
- `manga_tts.persistence` defines artifact/revision store protocols, immutable
  manifest/revision records, and in-memory test adapters. Artifact files stream
  through exact object generations and SHA-256 checks before pointer promotion.
  The current project hash remains the web expected-revision value; durable IDs are
  separate.
- `PipelineRouter` accepts an optional keyword-only writer session. Segment
  checkpoints advance the durable pointer before notification. Restore verifies a
  full manifest in staging before replacing the workspace. Cast reference overlays
  stay staged until pointer commit. If pointer promotion succeeds but local
  materialization fails, the worker reports `checkpoint_materialization_pending`;
  the accepted revision must be reloaded before another commit.
- `docs/target-design.md` records the ownership decision. `docs/architecture.md`
  describes the persistence contract and its unimplemented cloud adapters.

### Acceptance evidence

| Requirement | Evidence | Result |
| --- | --- | --- |
| Competing commits have one winner; stale revisions/fences do not move the pointer | `test_competing_commits_have_one_winner_and_stale_pointer_stays_unchanged`, `test_writer_ownership_blocks_edits_and_stale_fence_cannot_commit_after_recovery`, and `test_router_reports_stale_fence_as_typed_conflict` | Passed |
| Upload, verification, or pointer failure preserves the prior revision | `test_uploaded_artifacts_do_not_promote_when_pointer_commit_fails`, `test_artifact_verification_failure_keeps_prior_revision_current`, `test_workspace_overlay_waits_for_pointer_commit`, and `test_failed_cast_import_does_not_overwrite_current_workspace_assets` | Passed |
| Checkpoint failure is visible; restart restores accepted state and referenced audio | `test_checkpoint_failure_does_not_acknowledge_or_promote_audio`, `test_router_checkpoint_survives_new_writer_and_reuses_accepted_audio`, and `test_failed_restore_keeps_existing_workspace_intact` | Passed |
| Existing project-hash conflicts return a machine-readable result; metadata uses the persistence seam | `test_stale_edits_fail_without_changing_project` and `test_transport_metadata_advances_the_same_revision_pointer` | Passed |
| Post-pointer local refresh failure is explicit and prevents a later stale commit | `test_post_commit_materialization_failure_is_reported_as_accepted_checkpoint` | Passed |
| Local approval, hash, recovery, CLI, and bundle behavior remains compatible | Full Python discovery and existing audio/process/web workflow tests below | Passed |

### Fresh verification

Python 3.11.15 came from `/tmp/manga-s0-venv`; Node was v24.18.0 and npm 11.16.0.

| Command / working directory | Outcome |
| --- | --- |
| `/tmp/manga-s0-venv/bin/python -m unittest discover -s tests -v` / repository root | Exit 0; 59 tests run, 57 passed, two optional skips |
| `/tmp/manga-s0-venv/bin/python -m unittest discover -s tests -p 'test_persistence.py' -v` / repository root | Exit 0; 13 passed |
| Ruff 0.16.7 `check` and `check --select I` on `manga_tts/persistence.py`, `manga_tts/router.py`, `manga_tts/storage.py`, `web_workflow.py`, `tests/test_persistence.py`, and `tests/test_web_workflow.py` | Exit 0; both checks reported all checks passed |
| Pyright 1.1.414 / same six S1 Python files | Exit 0; zero errors, warnings, or informationals using Python 3.11.15 and basic checking mode. Temporary config removed after the check. |
| `npm test` / `web/` | Exit 0; eight assertions passed |
| `npm run typecheck` / `web/` | Exit 0 |
| `npm run build` / `web/` | Exit 0; Next.js 16.4.0 Turbopack production build completed and listed all 11 routes |
| `git diff --check` / repository root | Exit 0; no whitespace errors |

The two full-suite skips were expected: no external `MANGA_TTS_SAMPLE_PROJECT` and
no `MANGA_WEB_TEST_URL`. The focused worker recovery suite passed separately (one
test); audio pipeline and web workflow suites passed separately (15 and 14 tests).
No model download, live MAGI inference, Gemini synthesis, or cloud operation ran.

The repo-wide Ruff scan still reports four out-of-scope findings: `files.py`
(`TRY004`), `magi.py` (`C408`), `tests/test_audio_pipeline.py` (`SIM117`), and
`tests/test_cast_speakers.py` (`F841`). The six S1 Python files listed in the table
pass both default Ruff rules and import sorting.

### Limits and next scope

Only in-memory adapters validate the application contract; Firestore/GCS transaction,
object-generation, and service-identity behavior remain unverified and belong to S5.
The local studio still uses filesystem persistence by default.

## S2 — Complete, 20 October 2026

Post-implementation S1/S2 review and recovery fixes are recorded in
[the review evidence](s1-s2-review.md), including independent review results,
restart and upload regressions, and current validation limits. This follow-up
supersedes the earlier absence-of-findings claim for the reviewed recovery paths.

Assignment: add a durable same-host operation queue and recoverable finite local
workers while preserving the existing workflow engine, JSON job polling, and UI
contract. Cloud storage, hosted execution, publication, and paid generation remain
out of scope.

### Decisions and changed behavior

- `docs/target-design.md` resolves S2 policies. SQLite/WAL coordinates one local
  database only, with one MAGI slot and one pipeline slot and one active operation
  per project. Firestore and distributed coordination remain S5 work.
- An `Idempotency-Key` binds one normalized request to one operation. Changed input
  under the same key conflicts; `GET ?key=` recovers an operation after a lost
  enqueue response. Browser storage retains multiple pending keys so one new request
  cannot overwrite another operation's lost-response key. Upload bytes and existing
  project visual evidence are fingerprinted when queued and checked again before
  worker execution, alongside the pinned project hash and configuration fingerprint.
- The operation store owns three total attempts. Each durable worker attempt makes
  at most one provider request. Workers heartbeat every 15 seconds, use 60-second
  leases, and have a 30-minute timeout. A stale worker is recovered only after
  confirming PID plus process creation time and reconciling the project lock.
- A provider call without a durable result enters `reconciliation_required` and
  retains its stage slot. The local `web_workflow.py reconcile` command requires an
  explicit fail or retry decision; retry may repeat billing. Safe stopped work with
  a durable segment checkpoint returns to the queue and resumes from that checkpoint.
- Existing JSON job files are read-only polling fallbacks for IDs absent from
  SQLite. New workers receive only operation ID and fence and load parameters from
  the store. The UI stops polling on uncertain outcomes and directs the operator to
  local reconciliation.
- `GLOSSARY.md` defines Operation, Attempt, Stage slot, Lease, Fence, Idempotency key,
  and Uncertain outcome. No ADR was needed; the local scheduling choices remain
  within this scope and do not settle the S5 cloud adapter.

### Acceptance evidence

| Requirement | Evidence | Result |
| --- | --- | --- |
| Duplicate enqueue returns the same operation; key reuse with changed payload conflicts | `test_same_idempotency_key_and_payload_returns_one_operation`, `test_reusing_idempotency_key_for_changed_payload_conflicts`, and local HTTP key lookup/conflict coverage | Passed |
| Competing transactions respect stage capacity and project exclusivity | `test_stage_claim_capacity_and_independent_stages`, `test_claim_next_serializes_one_project_across_stages`, and `test_competing_process_claims_respect_the_single_stage_slot` | Passed |
| Retries have one authority and stop at three total attempts | `test_retry_ceiling_counts_initial_attempt` and `test_durable_worker_leaves_retry_authority_with_operation_store` | Passed |
| Stale fence cannot complete a newer attempt | `test_stale_fence_cannot_complete_newer_attempt` | Passed |
| Changed source image is rejected before a queued planning operation reaches a provider | `test_queued_plan_rejects_changed_visual_evidence_before_provider_call` | Passed |
| Changed appearance crop is rejected before a queued planning operation reaches a provider | `test_queued_plan_rejects_changed_appearance_crop_before_provider_call` | Passed |
| Changed upload bytes are rejected before import | `test_queued_upload_rejects_changed_bytes_before_import` | Passed |
| Dispatch crash and stale worker recovery preserve slot safety | `test_expired_unstarted_dispatch_requeues_without_releasing_attempt_limit`, `test_timed_out_worker_detected_even_when_heartbeat_keeps_lease_fresh`, and process-identity recovery paths | Passed |
| Uncertain provider outcomes retain capacity until an operator decision | `test_stopped_provider_worker_requires_operator_resolution_and_keeps_slot` and `test_uncertain_outcome_holds_capacity_until_explicit_resolution` | Passed |
| Restart resumes a persisted render segment without regenerating it | `test_worker_stopped_between_segments_requeues_from_saved_checkpoint` and `test_interrupted_render_resumes_after_operator_resolution_without_repeating_saved_segment` | Passed |
| API idempotency, lost-response lookup, legacy JSON polling, and existing workflow HTTP behavior work | `tests/test_web_http.py` under the disposable production HTTP runner | Passed |
| Existing frontend compiles with the reconciliation state and polling changes | `npm test`, `npm run typecheck`, `npm run build`, and studio/frontend-only HTTP checks | Passed |

### Fresh verification

Python 3.11.15 from `/tmp/manga-s2-venv` ran the full suite after final review and
fixes. Node was v24.18.0, npm 11.16.0, and Next.js 16.4.0.

| Command / working directory | Outcome |
| --- | --- |
| `/tmp/manga-s2-venv/bin/python -m unittest discover -s tests -v` / repository root | Exit 0; 80 tests, 78 passed, two expected skips |
| `/tmp/manga-s2-venv/bin/python -m unittest test_operations test_web_workflow test_operation_worker_process test_worker_process -v` with `PYTHONPATH=tests` | Exit 0; 36 affected tests passed |
| Ruff `check` and `check --select I` on changed Python files | Exit 0; both passed |
| Pyright 1.1.414 on changed Python files | Exit 0; zero errors, warnings, or informationals |
| `npm test` / `web/` | Exit 0; ten tests passed |
| `npm run typecheck` / `web/` | Exit 0 |
| `npm run build` / `web/` | Exit 0; production build completed and listed all 11 routes |
| `/tmp/manga-s2-venv/bin/python tests/verify_local_http.py` / repository root | Exit 0; disposable studio HTTP integration passed and frontend-only HTTP guards passed |
| `git diff --check a5e59a2...HEAD` / repository root | Exit 0; no whitespace errors |

The full discovery skips were expected: no `MANGA_TTS_SAMPLE_PROJECT` was supplied,
and no external `MANGA_WEB_TEST_URL` was configured. The disposable HTTP runner
started its own studio server and passed the HTTP workflow test.

### Final review

The Standards review found no hard documented-rule breaches or remaining
judgement-call smells. The Spec review found no remaining requirements gaps. Earlier
review findings for safe checkpoint resume, source-byte pinning, pending idempotency
key recovery, and acceptance path inventory were fixed and rechecked.

No real Firestore, Cloud Run, live MAGI/Gemini inference, paid provider call, or
publication work ran. SQLite WAL is not a multi-host scheduler. Process recovery
tests validate local process identity and checkpoint reuse, not filesystem power-loss
durability.

S2 has no remaining acceptance blockers. S3 is the next eligible scope in
`architecture-alignment-plan.md`.

## S3 — Local implementation verified; live admin acceptance blocked, 22 October 2026

The user explicitly approved completing S3 and deploying authentication boundaries
in the existing KoeTTS project. Hosted generation, publication, S4 shared requests
and S5 production storage/execution remain excluded. No admin was promoted, no user
was impersonated and no paid provider call ran.

### Implemented boundaries

- Same-user token renewal retains the mounted studio/request form. Pending or
  failed session verification makes protected content inert and blocks studio API
  requests. Inline reauthentication restores access; sign-out or UID change removes
  the private workspace. `authorizationReady` is separate from initial loading.
- `require-admin.ts` retains a verified principal for the exact request. Workflow
  enqueue overwrites caller actor metadata with Firebase UID/project and persists
  that identity in the durable operation, without storing tokens or cookies.
- Cast and single/batch scene approvals commit audit records atomically with their
  validity fingerprints. Records include actor, reviewed revision, subject,
  decision, approval fingerprint, timestamp and operation identity. Retry deduplication
  and legacy empty-history serialization preserve existing compatibility. CLI actors
  are explicitly local. Audit survives project bundles and restore.
- `manga_tts/http_auth.py` independently verifies Google issuer/audience/signature,
  service subject/action permission, and exactly one revoked-checked Firebase user
  credential. `http_api.py` wraps snapshot and durable enqueue/poll services in local
  mode. Its default verification mode refuses project, asset and operation access
  before touching workspaces. Readiness and identity require no provider clients.
- `GET /api/auth/backend` verifies both identities from App Hosting without exposing
  user identity in its response. Existing local subprocess execution remains default.
  Production has no authentication-fixture environment switch: the HTTP runner replaces
  the external SDK only inside its disposable copied source tree.

### Acceptance checks from this task

Commands ran from the repository root unless specified. Python was 3.11.15; Node
was 24.18.0; Next.js was 16.4.0. The temporary Python environment and first logs
disappeared during execution-environment restart; these outcomes were observed
directly in this task and are not inherited S2 claims.

| Check | Result |
| --- | --- |
| `/tmp/manga-s3-venv/bin/python -m unittest discover -s tests -v` | 100 run; 98 passed; two expected skips: external sample and externally managed HTTP server |
| Focused approval audit suite | Seven passed: trusted/local identity, retry dedupe, failed save, failed revision-pointer commit, bundle recovery, forged metadata denial and legacy serialization |
| Focused Python HTTP suite | Seven passed; includes real workspace snapshot, durable idempotency and stale-revision failure, independent identity denials and unavailable asset delivery |
| Focused process recovery suite after adapter update | Six passed; retained segment and forced-regeneration recovery remain intact |
| `npm test` in `web/` | 32 passed after hosted-origin correction, including real React DOM request/studio draft continuity, proxy CSRF regression and backend diagnostic credential separation |
| `npm run typecheck` and `npm run build` in `web/` | Passed; build includes `/api/auth/backend` |
| `/tmp/manga-s3-venv/bin/python tests/verify_local_http.py` | Passed two disposable production builds, authenticated studio workflow and frontend-only denial/unavailability checks |
| Scoped Ruff and Pyright | Passed changed Python runtime/test files; Pyright zero errors/warnings with explicit temporary Python 3.11 environment/import paths |
| API-only dependency smoke | Fresh environment installed only `requirements-api.txt`; API factory imported without extraction/generation dependencies |
| Native Chromium via Playwright | Request notes and studio upload survive pending/failed renewal in the same mounted DOM; native inert blocks focus in both and request-submit pointer interaction; retry/recovery, UID switch and sign-out pass; no page errors |
| Independent Standards and Spec reviews | Zero actionable findings on each axis |

Native browser command was `node /tmp/s3-browser/run.cjs`, with temporary
Playwright/esbuild tooling and real application components. Firebase/navigation
were mocked at external boundaries; child review UI used fixtures. Studio submission
was not attempted without a valid project. The Browser plugin was unavailable, so
regular Playwright used installed Chromium. Durable React DOM regression coverage
is `web/tests/auth-drafts.test.cjs`; browser screenshots/harness are temporary.

Initial full discovery failed six subprocess cases because its injected router
factory did not accept the new optional approval context. The fixture now forwards
constructor options and all six pass. The first disposable build rejected the
fixture SDK's one-argument signatures; matching SDK signatures fixed that harness.
An intermediate test-only indentation error was fixed before final discovery.
No runtime guard was weakened. Locked dependencies were synchronized; production
audit reported four inherited high advisories in the unused Firebase Firestore/gRPC
dependency chain. No broad Firebase downgrade or unrelated dependency remediation ran.

### Live deployment evidence

Private API project/region: `koetts-9bf7f` / `us-east4`. Revision:
`koetts-s3-api-00001-gl5`. Image digest:
`sha256:bd5cf2fac59d9733ee408d847eb80b6795ab9c40b7840534b06163d336a43cc2`.
Cloud Build: `f2bf2888-ed20-4dce-92fc-08e1e8e106f8`. The earlier image build was
superseded before deployment after strict service-subject validation was added.
Only 19 source files (about 216 KiB) entered the reviewed API build context;
no uploads, results, credentials or model caches were included.

The API uses its dedicated runtime account with custom role
`projects/koetts-9bf7f/roles/koettsS3AuthVerifier`, containing only
`firebaseauth.users.get`. Invocation initially allowed App Hosting and the
dedicated verification account; no public invoker exists. Temporary verifier
minting/invocation grants were removed after probes. Final IAM inspection confirms
only App Hosting invokes the API and no temporary user binding remains on its account.
Verification mode,
zero minimum/one maximum instances, one CPU and 512 MiB remain configured.

`python3 tests/verify_s3_identity.py` passed against the deployed service:
anonymous platform denial 403, authorized readiness 200, missing/forged/duplicate
Firebase credentials 401, and a separately forwarded wrong-audience service token
401. Service tokens stayed in memory. Direct IAM Credentials ID-token minting
avoided granting broader access-token impersonation rights.

Named Firestore database `koetts-default` already deploys explicit deny-all browser
rules; no rules or database provisioning changed. One existing admin and no reader
accounts were discovered. Google sign-in was already enabled. The actual App Hosting
hostname was added to authorized domains while preserving prior entries.

Frontend rollout `build-2026-10-21-001` succeeded, but real Chromium found initial
session DELETE rejected with 403 `Invalid origin.` The browser sent the correct
public Origin; Next's request URL reflected the internal proxy. Traffic was restored
to `koetts-build-2026-10-18-001` while correcting this. The user also observed session
failure and a diagnostic 404 during rollback. No unauthorized access succeeded.

The correction configures the exact canonical `MANGA_APP_ORIGIN` server-side.
CSRF still requires an explicit matching Origin and rejects cross-site requests,
invalid configured origins and forged forwarded-host headers. Its regression test
failed before the fix and passed afterward. All 32 web tests and production build
passed; focused independent Standards and Spec follow-up reviews found no issues.
A corrected frontend rollout `build-2026-10-21-002` succeeded and serves 100% of
traffic. Live public checks passed: home redirects to Browse; Browse/login return
200; anonymous diagnostic/workflow/extraction/assets return 401; missing-origin
session mutation returns 403; canonical-origin session DELETE returns 200 with
Secure/HttpOnly/SameSite=Strict cookie flags; attacker origin with forged forwarded
host returns 403; canonical-origin POST without user token returns 401.
Native Chromium also confirms session DELETE200 on login and Browse, enabled
Google button, no visible session error, three demo stories and zero runtime errors.
No Google sign-in was attempted by the agent.
The previous frontend revision remains the rollback target. See [S3 deployment](S3_DEPLOYMENT.md) for rollout,
cost limits and rollback. The user successfully signed in after the correction and
reported the diagnostic's `Administrator access required.` response. Inspection
confirmed a reader account now exists alongside the unchanged existing admin;
live reader denial is therefore confirmed. The user cannot access the existing
admin account. Successful frontend-to-private-API admin verification is blocked
by that access limitation; it is not claimed passed. The approved scope excludes
automatic role promotion, so existing roles remain unchanged. An existing admin
must run the diagnostic, or a separately authorized designated-admin provisioning
task must establish another trusted administrator before this live criterion closes.
Revoked-user behavior is verified offline, not by modifying the live admin's sessions.

Implementation and deployment are committed in `8ae3968` on
`feat/architecture-alignment`. This report distinguishes completed local contracts,
successful authentication-only deployment, and the blocked positive live admin
check. It does not establish S4 or S5 completion.
