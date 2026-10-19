# Current application architecture

Source inspection: 19 October 2026. This describes implemented boundaries, not a
new runtime verification. Historical test results remain in the baseline and
validation record. Reinspect affected source when implementation changes.

## Local production studio

The studio at `/` uses `web/app/page.tsx` and active workspaces in
`web/components/`. Browser state owns unsaved review drafts. Shared TypeScript
contracts are in `web/lib/types.ts`; Python commands are in `manga_tts/schemas.py`.

`web/app/api/workflow/route.ts` uses `web/lib/workflow.ts` to stage requests and
launch `web_workflow.py`. The browser polls saved jobs. Python routes operations
through `PipelineRouter` in `manga_tts/router.py`; the CLI uses the same engine.
The engine owns validated applied state, approval validity, takes, and export.
MAGI extraction preserves evidence; Gemini planning and synthesis are provider
adapters. See the [audio workflow](AUDIO_WORKFLOW.md) for domain semantics.

Persistence defaults to local files under `results/web/`: projects contain
state/assets/takes; sibling directories contain jobs, uploads, and bundles. CLI/web
use workspace writer locks and expected-state fingerprints. S1 adds the
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

The in-memory adapters exist for local contract tests only. No Firestore/GCS adapter,
distributed scheduler, or cloud durability is implemented. Node concurrency limits
remain process local.

The web worker reports stale project-hash rejection with a machine-readable
`failure_code`. Server-owned project metadata uses the router commit seam, alongside
engine mutations. The project-hash value in snapshots remains the expected-state
contract; durable revision IDs are separate.

The bridge in `web/lib/python.ts` selects `PYTHON_EXECUTABLE`, then the repository
virtual environment, then `python`. Check interpreter availability before startup.
Dependency manifests and `web/package.json` are authoritative for dependencies and
available commands. Older duplicate components/tests require reachability checks
before removal.

## Reader demo and hosting

Browse, manga details, and reader pages use `web/app/data/manga.ts` sample data.
The request form stores requests in browser storage; `/requests` is missing and
Listen is inactive. No shared requests, roles, publication, or hosted production
backend are implemented.

`firebase.json` targets the `web/` App Hosting application. Its frontend-only mode
in `web/apphosting.yaml` and Next configuration redirects the home route and guards
workflow/extraction/asset APIs with HTTP 503. The local studio remains loopback
bound with origin checks. These checks are not user authentication.

See [target-design.md](target-design.md) for the accepted migration destination.
See [the historical baseline](current-app-baseline.md) for deeper inspection notes;
its recorded checks are not current pass claims.
