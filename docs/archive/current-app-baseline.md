# Current application baseline

Historical source names below describe the original checkout. Source hyperlinks now follow the current owning files where those interfaces moved.


Inspection date: 2026-10-19.

The repository contains a functional local audiobook production pipeline and a disconnected demo catalog. It does not implement a shared hosted workflow, authentication, request fulfillment, or publication integration.

This baseline covers the working tree at inspection time, including existing uncommitted changes. The inspection read the supplied instructions, `web/AGENTS.md`, source, configuration, tests, and architecture/workflow guides. Documentation was treated as intent and checked against code. No source edits, package installations, paid API calls, or cloud mutations were performed during inspection. Git status remained unchanged; checks generated build artifacts only.

## 1. Purpose and user flows

The application supports human-reviewed manga-to-audio production:

- Import images, an extracted chapter ZIP, or a saved project.
- Resolve character identities and voices.
- Optionally generate and load an AI proposal.
- Correct source text, order, grouping, and speakers.
- Approve exact scene scripts.
- Generate, audition, regenerate, select takes, and export audio.

The studio lives at `/`. Its operational role is a single local editor/operator; there is no implemented role system. See `Home` in [web/app/page.tsx](../../apps/web/app/page.tsx).

A separate reader-facing surface exists:

- `/browse` displays three hardcoded sample manga.
- `/manga/[id]` displays sample chapter statuses; its “Listen” button has no handler.
- `/read/[mangaId]/[chapterId]` displays placeholder artwork.
- `/request` saves requests only in browser `localStorage`; it does not submit them to a backend.
- “My Requests” links to `/requests`, which has no route.

Sources: [sample catalog](../../apps/web/features/library/fixtures/catalog.ts), [browse page](../../apps/web/app/browse/page.tsx), [manga details](../../apps/web/app/manga/[id]/page.tsx), [reader](../../apps/web/app/read/[mangaId]/[chapterId]/page.tsx), and [request form](../../apps/web/app/request/page.tsx).

## 2. Structure and execution

- **Frontend and server:** Next.js App Router, React, TypeScript, Tailwind/PostCSS, and Sonner notifications. Installed versions at inspection were Next.js 16.4.0, React 19.3.0, and TypeScript 5.9.3.
- **Application backend:** The synchronous Python `PipelineRouter`, with separate modules for extraction, resolution, script review, storage, and synthesis.
- **Adapters:** MAGI through PyTorch/Transformers; Gemini through `google-genai`; optional MP3 encoding through system FFmpeg or `imageio-ffmpeg`.
- **Entry points:** Next.js routes, `web_workflow.py`, `python -m manga_tts`, and the original inference CLI `run.py`. The legacy OCR bridge remains in `web_extract.py`.
- **Dependencies:** Extraction versions are pinned in `requirements.txt`; audio dependencies use ranges in `requirements-audio.txt`. An npm lockfile exists; the Python dependency graph is not fully locked.

Sources: [package manifest](../../apps/web/package.json), [router](../../packages/engine/src/manga_tts/router.py), [CLI](../../packages/engine/src/manga_tts/cli.py), [extraction requirements](../../packages/vision/pyproject.toml), and [audio requirements](../../packages/engine/pyproject.toml).

To run locally, prepare a Python 3.11+ environment and install the required dependencies. Inside `web/`, run `npm ci`, then `npm run dev`. The server binds to loopback on port 3000. Production commands are `npm run build`, then `npm start`.

The Python bridge selects `PYTHON_EXECUTABLE`, the repository `.venv`, then `python`. At inspection, this checkout had no `.venv` and no `python` command. An explicit interpreter configuration is required in this environment. See [web/lib/python.ts](../../apps/web/lib/python.ts).

Identical obsolete workspace components remain under `web/app/`; the active studio imports `web/components/`. Duplicate frontend tests remain under `web/lib/`; npm runs `web/tests/`.

## 3. Architecture and state ownership

The browser owns editable React drafts, selection, navigation, and unsaved-change state. Successful commands reload authoritative snapshots. Studio browser storage retains active project/job identifiers; unsaved drafts remain in memory.

Next.js routes validate transport, stage uploads, launch Python subprocesses, and return HTTP 202 job identifiers. The browser polls persisted job status every second. Python performs synchronous operations inside each worker.

`PipelineRouter` owns validated project state, returns detached snapshots, and saves before publishing successful mutations. It is neither an HTTP service nor a scheduler. See `launch` in [web/lib/workflow.ts](../../apps/web/lib/workflow.ts), `perform` and `run_job` in [web_workflow.py](../../apps/worker/src/manga_worker/workflow.py), and `PipelineRouter._commit` in [manga_tts/router.py](../../packages/engine/src/manga_tts/router.py).

Persistence is filesystem-based:

- `results/web/projects/<id>/project.json` stores the applied project.
- Project folders contain evidence, references, a proposal cache, takes, and exports.
- Sibling folders contain job requests/status, temporary uploads, and downloadable bundles.
- There is no database, object storage, shared request registry, or account ownership.

There is no authentication or authorization. Workflow and asset routes use loopback-host and origin checks; workflow POST also requires a custom header. The legacy `/api/extract` route lacks those origin/header checks. These controls support local execution, not user isolation.

External dependencies are the pinned Hugging Face MAGI weights/custom code, Gemini planning/speech APIs, and optional FFmpeg. MAGI loads per worker; there is no persistent inference service. Gemini clients initialize lazily.

Firebase configuration hosts the website only: `MANGA_FRONTEND_ONLY=1` redirects `/` to `/browse`, and all three processing/asset handlers return HTTP 503. No deployed Python backend is configured. See [web/apphosting.yaml](../../apps/web/apphosting.yaml) and [web/next.config.mjs](../../apps/web/next.config.mjs).

## 4. Manga-TTS integration

### Chapter ingestion and analysis

**Implemented.** `extract_chapter` preserves explicit image sequence, normalizes EXIF orientation/RGB, runs MAGI detection/OCR, and stores images, crops, overlays, raw predictions, hashes, and diagnostics. Geometry reconciles OCR with bubbles; unmatched or ambiguous text remains reviewable. The default preserves model order; an optional RTL/LTR whitespace heuristic exists. Initial scenes follow pages. See [manga_tts/extraction.py](../../packages/engine/src/manga_tts/extraction.py), particularly `extract_chapter` and `reconcile_texts`.

### Cast resolution

**Implemented.** Users can import a reference ZIP or create characters from detected crops. The active UI stages new characters with assignments for batch save. Named imports require references; generic shared voices may omit them. `UNKNOWN` remains unresolved; `NARRATOR` is separate. `sync_cast_speakers` fills unambiguous links while preserving manual/proposed assignments. See [cast workspace](../../apps/web/features/studio/cast-workspace.tsx) and [manga_tts/script.py](../../packages/engine/src/manga_tts/script.py).

### Proposals

**Implemented; provider-dependent.** `propose_plan` sends visual/text evidence to Gemini for assignments, corrected text/order, scene boundaries, acting, and evidence-linked narration. Generation stores the proposal without applying it. Explicit loading validates coverage and references, rebuilds turns, and clears approvals. It does not approve automatically. See [manga_tts/resolution.py](../../packages/engine/src/manga_tts/resolution.py) and `PipelineRouter.apply_proposal`.

### Source review and script approval

**Implemented.** Sources support inclusion, wording, speakers, image/panel/dialogue order, scenes, groups, and acting. Saving sources rebuilds dialogue turns and replaces final dialogue edits. Scene review edits the authoritative spoken transcript. Batch save publishes all edits and explicit approvals together. See [manga_tts/script.py](../../packages/engine/src/manga_tts/script.py), including `review_sources`, `rebuild_turns`, `review_scene`, and `approve_scene`.

### Speech generation

**Implemented adapter; live compatibility unverified.** Approved scenes compile into requests capped at two speakers and the configured character budget. Narration is separated; silence is generated locally. Oversized individual turns are rejected. The adapter calls `client.interactions.create`, expecting encoded WAV output. See `compile_segments` and `render_scene` in [manga_tts/tts.py](../../packages/engine/src/manga_tts/tts.py), and `GeminiRenderer` in [manga_tts/gemini.py](../../packages/engine/src/manga_tts/gemini.py).

### Audio review

**Implemented.** The studio provides browser playback, duration/clipping display, retained take selection, and targeted regeneration. There is no persisted “audio approved” decision or mandatory listening gate.

### Export and publication

**Export is implemented.** It assembles selected scenes in chapter order into WAV, optional MP3, script/cast JSON, a segment timeline, a manifest, and a resumable ZIP. Export never synthesizes.

**Publication is missing.** Exports do not enter the catalog, update chapter status, fulfill requests, or create public audio links.

Other absent stages include translation, word/bubble alignment, reconciliation across extraction reruns, a shared manga-wide cast registry, and cloud scheduling.

## 5. Contracts and safeguards

### Data and API contracts

Strict Pydantic commands reject unknown fields. Saved/vendor contracts preserve extra evidence. Version-2 `Project` contains chapter evidence, cast, appearances, editable sources, authoritative scene turns, proposal, approvals, settings, takes, and selections. TypeScript interfaces manually mirror subsets; there is no generated shared contract. See [manga_tts/schemas.py](../../packages/engine/src/manga_tts/schemas.py) and [web/lib/types.ts](../../apps/web/features/studio/types.ts).

`/api/workflow` GET lists projects or returns a job/snapshot. POST accepts multipart creation/import or JSON action commands with a project identifier and revision. `/api/asset` serves permitted path categories with byte-range support. `/api/extract` returns the legacy `{texts}` output. See [workflow route](../../apps/web/app/api/workflow/route.ts), [asset route](../../apps/web/app/api/asset/route.ts), and [extraction route](../../apps/web/app/api/extract/route.ts).

### Approval rules

Cast approval requires resolved/rejected appearances and a character cast. Scene approval checks source coverage/order, included speakers, text, narration evidence, tags, and silence. Synthesis checks current cast and scene fingerprints again. Relevant edits invalidate approvals.

Source-review status is informational; it is not an independent synthesis gate. Fingerprints record state validity, not reviewer identity or audit history.

Text requiring normalization, unrecoverable replacement characters, unsupported vocal tags, empty speech, and punctuation-only speech block approval unless corrected, excluded, or represented appropriately. See `validate_scene` in [manga_tts/script.py](../../packages/engine/src/manga_tts/script.py) and [manga_tts/cleaner.py](../../packages/engine/src/manga_tts/cleaner.py).

### Revisions and concurrency

Web commands and CLI review documents compare whole-project hashes. The router’s integer revision is process-local. CLI and web workers share exclusive PID lock files; direct router callers must enforce single-writer ownership.

Next.js also limits concurrent jobs to two, with one per project, within the Node process. There is no distributed queue, durable dispatch, cancellation, heartbeat, or automatic orphan recovery. See `workspace_lock` in [manga_tts/cli.py](../../packages/engine/src/manga_tts/cli.py) and `launch` in [web/lib/workflow.ts](../../apps/web/lib/workflow.ts).

### Caching and retries

The planning cache hashes the prompt/schema/model, normalized data, and image evidence. The audio cache hashes the exact request/model/silence/policy; reuse verifies WAV format and checksum. Selection remains segment-specific.

Defaults are nine synthesis requests per minute per renderer and five total attempts. Retries cover selected transient HTTP/network failures; uncertain timeouts can duplicate billing. See [manga_tts/resolution.py](../../packages/engine/src/manga_tts/resolution.py), [manga_tts/tts.py](../../packages/engine/src/manga_tts/tts.py), and `retry_api` in [manga_tts/gemini.py](../../packages/engine/src/manga_tts/gemini.py).

### Storage and recovery

JSON replacement is atomic, and successful audio is checkpointed per segment. Prior takes are retained. ZIP imports reject traversal, symlinks, duplicate paths, excessive entries, and contents over 1 GB. The web upload limit is 128 MB; image mode permits ten images of up to ten MB each.

Restore stages files before publishing into an empty workspace. Version-1 migration clears approvals and current selections. Export files overwrite fixed names and are not one transaction. Crashed workers can leave stale locks or unfinished jobs. See [manga_tts/storage.py](../../packages/engine/src/manga_tts/storage.py), `PipelineRouter.load_project`, and [web_workflow.py](../../apps/worker/src/manga_worker/workflow.py).

## 6. Verification

The following checks ran without provider calls or cloud changes:

| Check | Result |
| --- | --- |
| `npm test` | 8 passed. |
| `npm run typecheck -- --incremental false` | Passed. |
| Python syntax parsing | 29 files passed; no bytecode written. |
| Both CLI help entry points | Passed. |
| Python suite using existing cached dependencies and Python 3.13.11 | 45 tests: 42 passed, 2 skipped, 1 dependency error. |
| MP3 test | Dependency error: `imageio_ffmpeg` missing; actual MP3 encoding unverified. |
| External sample compatibility test | Skipped: no external sample supplied. |
| Optional HTTP integration test | Skipped: no local web test server configured. |
| `npm run build` | Blocked: Turbopack build-worker port binding returned `Operation not permitted`; escalation retry had the same result. |
| Webpack build fallback | Failed: `Could not parse output from TypeScript's --showConfig.` |

The default system Python 3.10 initially failed imports because Pillow was missing. Existing cached Pillow/Pydantic packages enabled the offline suite without installation. The production build remains unverified in this environment.

Tests exercise real temporary storage/review/render/export paths using synthetic predictions/audio: stale edits, atomic approvals, speaker synchronization, segmentation, exclusions, corruption, regeneration, partial recovery, archives, restore, and worker jobs.

No live MAGI/Gemini generation or browser visual checks were performed. Provider retry, proposal generation, and migration lack dedicated tests in the current suite.

Sources: [backend integration tests](../../tests/unit/engine/test_audio_pipeline.py), [speaker tests](../../tests/unit/engine/test_cast_speakers.py), [worker tests](../../tests/unit/worker/test_web_workflow.py), [optional HTTP test](../../tests/integration/test_web_http.py), and [frontend tests](../../apps/web/tests/script-review.test.cjs).

## 7. Implementation status and uncertainties

- **Executable and offline-tested:** The core review pipeline, approval gates, synthesis orchestration with an injected renderer, WAV export, caching, recovery, and worker commands.
- **Implemented but externally dependent:** Real MAGI analysis, Gemini planning/speech, and MP3 encoding. Accuracy, quality, configured model availability, and SDK response compatibility are not established.
- **Mocks and scaffolding:** Catalog statuses, reader artwork, the listening button, browser-only requests, and implied administrator fulfillment.
- **Configuration only:** Firebase website deployment configuration exists; actual deployed state was not inspected.
- **Documentation intent/history:** The workflow guide broadly matches code. The historical walkthrough describes the superseded OCR UI. Research alternatives remain unintegrated.
- **Concrete drift:** `firebase.json` specifies backend ID `koetts`; the hosting guide names `my-web-app`. The web guide describes immediate crop-character saving, while the active UI uses batch drafts. Historical successful validation records do not establish success in the current environment.

Sources: [firebase.json](../../firebase.json), [hosting guide](../../docs/APP_HOSTING.md), [web guide](../../apps/web/README.md), [workflow guide](../../docs/AUDIO_WORKFLOW.md), [historical walkthrough](../archive/CODE_WALKTHROUGH.md), [research notes](TEXT_EXTRACTION_RESEARCH.md), and [validation history](VALIDATION.md).

## Context for architecture review

The current system is a single-operator, filesystem-backed Python production pipeline behind a local Next.js studio, with an independent demo reader website.

Important constraints are explicit state-bound approvals, single-writer workspaces, per-segment checkpoints, provider-dependent generation, and local storage/process lifetime. Hosted mode disables processing.

Unresolved questions for the intended architecture are user/role ownership, durable job execution, shared manga/cast identity, request fulfillment, audio approval semantics, the publication contract, and verified provider/runtime compatibility. Recommendations are deferred until the intended architecture is supplied.
