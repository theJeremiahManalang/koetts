# Current application architecture

Source map updated: 28 October 2026. This describes implemented boundaries, not a
new runtime verification. Historical test results remain in the baseline and
validation record. Reinspect affected source when implementation changes.

## Workspace ownership

The root uv/npm workspaces own dependency installation and lockfiles. Deployable adapters live in `apps/web` and `apps/worker`; reusable production/image code lives in `packages/engine` and `packages/vision`. `manga_tts` and `manga_vision` remain the public Python namespaces; worker adapters now use `manga_worker`. Legacy root scripts and import aliases were removed after updating callers.

Web features follow a directed graph: identity is independent; library uses identity; requests uses library and identity; studio uses identity. Features import no route adapter. The shared wire types remain owned by studio and are consumed by server transport. Domain unit tests and cross-application integration tests have separate owners.

## Local production studio

The studio at `/` uses `apps/web/app/page.tsx` and active workspaces in
`apps/web/features/studio/`. Browser state owns unsaved review drafts. Shared TypeScript
contracts are in `apps/web/features/studio/types.ts`; Python commands are in `packages/engine/src/manga_tts/schemas.py`.

`apps/web/app/api/workflow/route.ts` persists each request with an idempotency key before
returning an operation ID. `apps/web/lib/workflow.ts` claims queued work and starts finite
local Python subprocesses. The browser polls operations and can recover a lost enqueue
response by key. Python workers resolve pinned parameters from the operation store,
then route production work through `PipelineRouter` in `packages/engine/src/manga_tts/router.py`; the CLI
uses the same engine.
The engine owns validated applied state, approval validity, takes, and export.
`packages/vision/` owns model identity, image helpers, and the lazy MAGI adapter. MAGI extraction preserves evidence; Gemini planning and synthesis are provider
adapters. See the [audio workflow](AUDIO_WORKFLOW.md) for domain semantics.

Persistence defaults to local files under `results/web/`: projects contain
state/assets/takes; sibling directories contain the SQLite operation database,
legacy job records, uploads, and bundles. The operation database stores request
fingerprints, expected project hashes, source/configuration fingerprints, attempts,
fences, leases, local process identities, progress, checkpoints, and outputs. Upload
bytes and existing project visual evidence are fingerprinted at enqueue; workers
recheck those inputs before using them. Its
same-host transactions enforce one MAGI slot and one pipeline slot, plus one active
operation per project across stages. Workers heartbeat leases and compare fences
before accepting completion. A provider outcome that cannot be confirmed retains its
slot until an operator resolves it. SQLite does not coordinate multiple hosts.

CLI/web use workspace writer locks and expected-state fingerprints. S1 adds the
`manga_tts.persistence.ProjectPersistence` contract; `PipelineRouter` can receive
an acquired `ProjectWriter` session. Artifact adapters stream files by immutable
object identity and exact generation, with a SHA-256 checksum. A revision records
its ID, parent, manifest reference/checksum, project hash, and fence. The revision
store atomically moves the current pointer only when expected parent, active owner,
and fence match. Load verifies the complete manifest into a staged workspace before
replacing the local view. A pre-pointer failure leaves the old revision current;
uploaded artifacts may remain unreferenced for later collection.

If pointer promotion succeeds but local materialization fails, the router reports
`checkpoint_materialization_pending`; the revision remains accepted, and another
commit requires reloading that revision first.

The in-memory adapters exist for project-revision contract tests only. Optional
worker-owned GCS artifact and Firestore revision adapters now implement the storage
protocols, with explicit cloud construction and exact-generation shared artifact
references. Live cloud durability is not yet established. A worker-owned Firestore operation adapter and
finite Cloud Run dispatcher/runtime now provide offline-tested distributed scheduling
contracts; hosted browser transport and rollout are still pending. Legacy JSON job
files remain readable for existing IDs; new local work uses SQLite.

The web worker reports stale project-hash rejection with a machine-readable
`failure_code`. Server-owned project metadata uses the router commit seam, alongside
engine mutations. The project-hash value in snapshots remains the expected-state
contract; durable revision IDs are separate.

S3 adds independently authenticated short-operation HTTP contracts in
`apps/worker/src/manga_worker/http_api.py`. The default verification mode authorizes identities but
refuses all project, asset and operation access before touching workspaces. Local
mode wraps the same snapshot and durable queue services; requests never run long
generation inline. Service audience/subject/action checks and Firebase user checks
are separate. The existing Next studio retains local subprocess execution.

Approval audit records are part of project state, saved in the same commit as cast
and scene decisions. Web actors come from verified request identity; worker retries
retain that actor and operation identity. Local CLI actors are labeled separately.

The bridge in `apps/web/lib/python.ts` invokes installed `manga_worker` modules using `PYTHON_EXECUTABLE` or the root uv environment. Repository discovery ascends to the root npm manifest; explicit absolute `MANGA_REPO_ROOT` supports unusual launchers. `MANGA_DATA_ROOT` pins the same local state directory for Node and Python workers. Installed workers use their documented user-data fallback outside a checkout.

The uv workspace has one lockfile and a lightweight default environment; optional CPU/CUDA vision extras retain the existing model stack. The worker app owns HTTP/OCR/workflow adapters. The engine package owns production decisions and imports no application code. Vision owns image/model utilities and imports no engine code. Root repository checks enforce these directions.

## Local shared requests and playback

The local shared service stores chapter work, individual requests, project links,
audio-review decisions and publication pointers in `results/web/shared.sqlite3`.
SQLite coordinates one host. Duplicate readers share chapter work but retain separate
requests and notes. An admin links an existing studio project, prepares an immutable
export snapshot, auditions it, records a review and explicitly publishes it. A
transaction updates the publication pointer and reader status only after artifact
verification; replacement failures retain the previous publication.

Immutable audio and supporting export artifacts are content-addressed under
`results/web/shared-artifacts`. Review and publication compare the exact project
revision, export identity, settings, link identity and artifact checksums under the
workspace lock. CLI and web exports use the same versioning boundary. Readers access
only published audio and their own requests. Audio URLs require a verified reader
session and a short-lived token, refresh during playback, and support byte ranges.
Production source images remain private; reader page delivery is not implemented.
Old browser-local demo requests are not imported or deleted.

`firebase.json` targets the `apps/web/` App Hosting application. Its frontend-only mode
in `apps/web/apphosting.yaml` and Next configuration redirects the home route and guards
workflow/extraction/asset and local shared APIs with HTTP 503 after authorization.
The local studio remains loopback bound with origin checks, in addition to user
authentication. Hosted processing and cloud shared storage remain S5 work.

See [target-design.md](target-design.md) for the accepted migration destination.
See [the historical baseline](archive/current-app-baseline.md) for deeper inspection notes;
its recorded checks are not current pass claims.

The private FastAPI adapter runs blocking credential verification and workspace I/O
in worker threads. Local operation enqueue accepts at most 5 MiB of JSON, rejects
ambiguous headers, duplicate fields and non-finite numbers, and validates bounded
credentials before external verification. Private responses disable caching and
content sniffing. Firebase app initialization is serialized across concurrent first
requests. These controls preserve the separate hosted verification-only boundary.

Shared metadata has an explicit worker-owned Firestore adapter, selected with
`MANGA_SHARED_BACKEND=firestore`, `FIREBASE_PROJECT_ID`, `FIRESTORE_DATABASE_ID`, and
`MANGA_SHARED_DATASET`. SQLite remains the default. Firestore datasets live beneath
`shared_workflow_v1/{dataset}` and bind to a persisted local artifact-store identity.
Transactional uniqueness records coordinate chapter/configuration deduplication,
reader/work identity and project links. Publication pointers and chapter status
commit together. Candidate/review order uses an explicit sequence, and retryable
callbacks contain metadata operations only. Artifact bytes, verification cache,
production workspaces and locks remain local; hosted shared routes stay disabled.
The legacy `manga_requests` collection is not read, migrated or modified.

`MANGA_SHARED_BACKEND=cloud` explicitly selects Firestore metadata with GCS shared
artifacts using a clean cloud dataset. The cloud dataset binds to a stable bucket
and namespace identity; it does not use local identity files. Firestore stores exact
artifact generations behind the shared checksum contract. Local materializations
are disposable caches. This storage selection does not enable hosted routes or
replace local operation scheduling. See the [hosted plan](hosted-service-plan.md).

## Hosted transport under implementation

Explicit `MANGA_EXECUTION_MODE=cloud` selects server-only Next-to-Python HTTP for
studio, shared metadata and artifact requests. Local subprocess calls fail closed
in that mode. The private service independently verifies service and user identity;
readers receive only shared catalog, their own requests and published audio. Admin
actions retain expected project hashes, pinned actors and engine review decisions.
Uploads are bounded individual objects whose immutable references remain server-owned.
Cloud OCR is a finite queued operation; published audio streams through authenticated
same-origin byte-range routes using the configured signing secret.

Hosted reader quotas and an atomic monthly production ledger are implemented. The
monthly ledger's chapter identity driver is pending the user's explicit decision
about approved shared work versus unlinked project admission. The checked-in
frontend-only guards remain enabled; cost controls, deployment and live acceptance
remain separate unfinished gates. This is not evidence of a launched hosted product.
