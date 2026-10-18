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

Persistence is local under `results/web/`: projects contain state/assets/takes;
sibling directories contain jobs, uploads, and bundles. CLI/web use workspace
writer locks and expected-state fingerprints. Node concurrency limits are process
local. These mechanisms do not provide distributed scheduling or cloud durability.

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
