# Current application architecture

Source inspection: 20 October 2026. This describes implemented boundaries, not a
new runtime verification. Historical test results remain in the baseline and
validation record. Reinspect affected source when implementation changes.

## Local production studio

The studio at `/` uses `web/app/page.tsx` and active workspaces in
`web/components/`. Browser state owns unsaved review drafts. Shared TypeScript
contracts are in `web/lib/types.ts`; Python commands are in `manga_tts/schemas.py`.

`web/app/api/workflow/route.ts` persists each request with an idempotency key before
returning an operation ID. `web/lib/workflow.ts` claims queued work and starts finite
local Python subprocesses. The browser polls operations and can recover a lost enqueue
response by key. Python workers resolve pinned parameters from the operation store,
then route production work through `PipelineRouter` in `manga_tts/router.py`; the CLI
uses the same engine.
The engine owns validated applied state, approval validity, takes, and export.
MAGI extraction preserves evidence; Gemini planning and synthesis are provider
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

The in-memory adapters exist for project-revision contract tests only. No
Firestore/GCS operation adapter, distributed scheduler, or cloud durability is
implemented. Legacy JSON job files remain readable for existing IDs; new work uses
SQLite.

The web worker reports stale project-hash rejection with a machine-readable
`failure_code`. Server-owned project metadata uses the router commit seam, alongside
engine mutations. The project-hash value in snapshots remains the expected-state
contract; durable revision IDs are separate.

S3 adds independently authenticated short-operation HTTP contracts in
`manga_tts/http_api.py`. The default verification mode authorizes identities but
refuses all project, asset and operation access before touching workspaces. Local
mode wraps the same snapshot and durable queue services; requests never run long
generation inline. Service audience/subject/action checks and Firebase user checks
are separate. The existing Next studio retains local subprocess execution.

Approval audit records are part of project state, saved in the same commit as cast
and scene decisions. Web actors come from verified request identity; worker retries
retain that actor and operation identity. Local CLI actors are labeled separately.

The bridge in `web/lib/python.ts` selects `PYTHON_EXECUTABLE`, then the repository
virtual environment, then `python`. Operation recovery uses `psutil` from
`requirements-audio.txt` to confirm local process identity. Check interpreter and
dependency availability before startup.
Dependency manifests and `web/package.json` are authoritative for dependencies and
available commands. Older duplicate components/tests require reachability checks
before removal.

## Reader demo and hosting

Browse, manga details, and reader pages use `web/app/data/manga.ts` sample data.
The request form stores requests in browser storage; `/requests` displays the local
list and Listen is inactive. Google sign-in and trusted admin claims protect the
studio page, workflow/extraction APIs and private assets. No shared requests,
publication or hosted production-processing backend are implemented.

`firebase.json` targets the `web/` App Hosting application. Its frontend-only mode
in `web/apphosting.yaml` and Next configuration redirects the home route and guards
workflow/extraction/asset APIs with HTTP 503. The local studio remains loopback
bound with origin checks. These checks are not user authentication.

See [target-design.md](target-design.md) for the accepted migration destination.
See [the historical baseline](current-app-baseline.md) for deeper inspection notes;
its recorded checks are not current pass claims.
