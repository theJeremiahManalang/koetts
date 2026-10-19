# Architecture alignment acceptance evidence

## S0 — Complete, 19 October 2026

Assignment: reproduce the existing application baseline and deepen local worker
interruption/recovery evidence. This report records fresh execution, not a claim
inherited from the historical baseline. No runtime API, schema, engine, dependency
manifest, lockfile, build-tool selection, or cloud configuration changed.

All S0 acceptance criteria passed after resolving the local verification environment.
Initial Python and build failures are retained below. S1 is the next eligible scope;
its edit ownership, stale-worker promotion, and fence lifecycle decision remains
unresolved in `target-design.md` and must be settled before dependent implementation.
No later scope was implemented.

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
