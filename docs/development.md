# Developer setup

## Reproducible installation

Use uv 0.11.16, Python 3.11.15, Node 22.22.3, and npm 10.9.8. `.python-version`, `.nvmrc`, package engine constraints, and uv's required-version setting define the supported environment. With nvm, run `nvm install` and `nvm use` at the root. Install the pinned uv version using the official [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

```bash
uv sync --frozen
npm ci
npm run check:repo
```

uv creates one root `.venv` and installs editable workspace packages plus development tools. The default includes review/audio, API, and synthetic-test dependencies; PyTorch and model inference dependencies remain optional. npm installs one root workspace tree from `package-lock.json`. Run package commands through root scripts so onboarding and CI use the same paths.

To update dependencies, edit the owning package manifest and regenerate `uv.lock` or the root npm lockfile. CI rejects stale locks. Do not hand-maintain parallel requirements files or nested npm locks.

## Run and configure

Copy `apps/web/.env.example` to `apps/web/.env.local` on first setup, preserving any existing settings. Follow [Firebase authentication](FIREBASE_AUTH.md) for Google login, server credentials, and trusted admin claims. Browser-visible Firebase settings are public configuration; server credentials remain private. Gemini uses Application Default Credentials (ADC).

```bash
npm run dev
# http://127.0.0.1:3000
```

The web server selects the root uv environment automatically. `PYTHON_EXECUTABLE` can select another absolute interpreter with the worker packages installed. Workers execute installed Python modules, not repository scripts. For new planning and synthesis, set `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION=us`. The engine uses Google Gen AI SDK 2.33+ in enterprise mode with ADC, locally (`gcloud auth application-default login`) or through an attached workload service account on GCP. Gemini API keys are not supported as a fallback. The `provider_configured` indicator reports only whether a project is configured; it does not verify ADC, model access, live provider readiness, or budget admission. Offline fixtures verify the `generate_content` mapping and unary WAV handling, not live access or output quality. Reviewing existing state and synthetic tests make no paid calls.

`MANGA_DATA_ROOT` optionally selects an absolute local state directory. Checkout defaults preserve `results/web`; installed workers outside a checkout default to `~/.local/share/manga-studio`. Web and worker receive the same resolved data directory. `MANGA_REPO_ROOT` optionally selects an absolute checkout root for unusual web launchers. Each web server instance must use one consistent state directory.

Installed `manga-tts`, `manga-vision`, `manga-worker`, and `manga-ocr` commands work from any directory. From the root, use `uv run <command>`. For external working directories, invoke the absolute `.venv/bin/<command>` (Windows: `.venv\Scripts\<command>.exe`) or `uv run --project /absolute/checkout <command>`.

## Optional vision environment

```bash
uv sync --frozen --extra vision-cpu
# Or, on a compatible Linux/Windows CUDA 12.4 host:
uv sync --frozen --extra vision-cuda
```

These extras are mutually exclusive. They select explicit PyTorch indexes and preserve the existing pinned model stack. CUDA is not supported on macOS. The default lightweight environment supports synthetic extraction tests without either extra. `uv sync --frozen` returns to the lightweight environment. See [model setup](MODELS.md) before real inference; loading weights is separate from dependency resolution.

## Checks and team workflow

```bash
npm run check              # boundaries, lint, Python/web tests, typecheck, build
npm run test:http          # disposable studio + frontend-only production checks
uv run python tools/verify_fresh_checkout.py
```

If the environment blocks Turbopack's worker process/port binding, verify the
supported production webpack fallback explicitly with
`npm run build --workspace @manga/web -- --webpack` and
`npm run test:http -- --webpack`. Record the default build failure separately;
these checks do not establish App Hosting's default bundler or monorepo adapter
behavior. The HTTP runner's default remains the normal production build.

Python tests are grouped under `tests/unit/{engine,vision,worker}` and `tests/integration`. Run selected cases with `uv run python -m unittest tests.unit.worker.test_paths -v`. Cross-process fixture helpers live under `tests/helpers`.

Optional external-project compatibility uses `MANGA_TTS_SAMPLE_PROJECT`; standalone HTTP integration uses `MANGA_WEB_TEST_URL`. The disposable HTTP runner supplies its own temporary server and fake identity adapter. It copies source and Node dependencies, creates a frozen uv environment, clears provider keys, and preserves repository results. Loopback and child processes must be permitted. Its `--dev` option checks development transport rather than production compilation.

Use [contribution guidance](../CONTRIBUTING.md) for review and dependency changes. [Architecture](architecture.md) defines ownership; [audio workflow](AUDIO_WORKFLOW.md) defines review and recovery. Static import checks enforce package direction and route/feature separation.

## Troubleshooting

For runtime-engine errors, select the pinned Node version before reinstalling dependencies. For missing Python modules, run `uv sync --frozen`; installing Node dependencies does not install Python packages. For workspace conflicts, reload saved state and follow workflow recovery rather than bypassing fingerprints or locks. For build port restrictions, rerun in an environment permitting local build processes with a fresh generated cache.

[App Hosting](APP_HOSTING.md) covers frontend-only hosting. [Private API deployment](S3_DEPLOYMENT.md) covers its separate service image. Build/configuration updates do not authorize deployment.

## Migration from the flat checkout

| Previous interface | Current interface |
| --- | --- |
| `web/` and package commands inside it | `apps/web/`; root npm commands |
| `python run.py ...` | `uv run manga-vision ...` |
| `python web_workflow.py ...` | `uv run manga-worker ...` |
| `python web_extract.py IMAGE` | `uv run manga-ocr IMAGE` |
| Root `files`, `magi`, `runners`, `config` imports | `manga_vision.files`, `.magi`, `.runners`, `.config` |
| `manga_tts.http_api` / `.http_auth` | `manga_worker.http_api` / `.http_auth` |
| Handwritten requirements and local pip installs | Root uv workspace and frozen synchronization |

The `manga_tts` engine namespace, project files, operation protocol, approval semantics, and default repository result directory remain compatible. No compatibility aliases remain for removed starter interfaces. Retain existing `apps/web/.env.local` and repository `results/` when moving an existing checkout.

### Existing-checkout onboarding, step by step

**Warning: this is a codebase and tooling migration, not a documentation-only update.** Old paths, root Python scripts, Python environments, and Node installation commands are no longer supported. Existing project data does not need a format migration.

1. Stop the old Next.js server, CLI sessions, and Python workers. Let active rendering finish or follow the documented uncertain-operation recovery procedure. Do not switch revisions while a worker owns a project.
2. Commit or stash your own tracked edits. Before switching branches, back up ignored environment files and project results outside the checkout. The following Bash example creates a private backup directory; retain its printed path until onboarding succeeds:

   ```bash
   MIGRATION_BACKUP=$(mktemp -d "$HOME/manga-migration.XXXXXX")
   printf 'Migration backup: %s\n' "$MIGRATION_BACKUP"
   mkdir -p "$MIGRATION_BACKUP/web-env"
   for file in web/.env*; do
     if [ -f "$file" ] && [ "$(basename "$file")" != ".env.example" ]; then
       cp -p "$file" "$MIGRATION_BACKUP/web-env/"
     fi
   done
   if [ -d results ]; then cp -a results "$MIGRATION_BACKUP/results"; fi
   ```

   On Windows, copy the same environment files and `results/` to a private directory outside the repository. Keep model caches in place; this migration does not require downloading weights again. Never commit the backup or credentials.
3. Retire the old dependency environments before switching. Move `.venv`, `web/node_modules`, and `web/.next` into separate directories under that backup if present. Do not reuse an old pip-managed environment as the new locked environment. Keep it only for rollback to its original path.
4. Fetch and switch to the migration branch (`git fetch origin`, then `git switch --track origin/chore/repo-management` for a new local tracking branch). If you already have that branch locally, use `git switch chore/repo-management` instead. After merge, update `main` with `git pull --ff-only` instead of switching to the PR branch. The GitHub repository may now appear as `theJeremiahManalang/koetts`; the previous repository URL redirects to the same repository.
5. Install/select uv 0.11.16, Node 22.22.3, and npm 10.9.8. From the repository root run:

   ```bash
   nvm install
   nvm use
   uv --version
   node --version
   npm --version
   uv sync --frozen
   npm ci
   ```

   `nvm` is optional; another Node version manager is fine. The checked-in runtime versions and engine checks remain authoritative. uv obtains the pinned Python version when needed.
6. Restore the backed-up environment values to `apps/web/`, matching each original filename. For the common `.env.local` case:

   ```bash
   if [ -f "$MIGRATION_BACKUP/web-env/.env.local" ]; then
     cp -p "$MIGRATION_BACKUP/web-env/.env.local" apps/web/.env.local
   fi
   ```

   For a new clone with no old environment, copy `apps/web/.env.example` to `apps/web/.env.local` and follow the Firebase setup guide. Clear any old `PYTHON_EXECUTABLE` override with `unset PYTHON_EXECUTABLE`, or update it to the new absolute `.venv` interpreter. Keep Gemini and administrative credentials server-side.
7. Keep the original `results/` directory in place. If onboarding into a different clone, copy the backed-up `results/` into that clone's repository root. If data lives elsewhere, set the same absolute `MANGA_DATA_ROOT` for the web server and worker. Never overwrite a nonempty project directory or copy a database while its workers are active.
8. Run acceptance checks and start the server from the root:

   ```bash
   npm run check
   npm run test:http
   npm run dev
   ```

   Open the studio, sign in as a trusted admin, and inspect an existing project before starting new generation. Review requires no model download or paid provider call. Install a vision extra only if performing new extraction; default onboarding intentionally excludes PyTorch.
9. Update local scripts, IDE run configurations, scheduled tasks, and deployment build contexts using the migration table above. Restore the original checkpoint/operation recovery flow rather than bypassing writer locks. Keep backups until existing-project review and needed checks succeed.

For rollback, stop all new workers, return to the previous revision, and restore dependency environments and environment files to their original paths. Restore data backups only through the normal recovery process; do not overwrite newer production progress. This PR does not run a database-format migration or deploy services.

## Optional Firestore shared metadata

SQLite remains the default shared workflow backend. Firestore is an explicit local
metadata alternative, not hosted production or distributed artifact storage. Use
one dataset per local data root. The existing database is Standard edition,
`koetts-9bf7f/koetts-default`; the legacy `manga_requests` collection is excluded and
left untouched. Browser Firestore access remains denied; access uses server ADC.
Install a packaged worker with its `firestore` extra when using that adapter.

Stop web servers and shared-workflow clients before changing backends. Export
`FIREBASE_PROJECT_ID`, `FIRESTORE_DATABASE_ID`, `MANGA_SHARED_DATASET`, and the same
absolute `MANGA_DATA_ROOT` used by the application. Inspect before activation:

```bash
uv run --locked python -m manga_worker.shared_cutover
```

The default command only reads SQLite/Firestore metadata and reports counts, schema,
artifact identity and blockers. It does not initialize a namespace, import old
requests or delete data. Nonempty SQLite, foreign artifacts, unsupported schemas
and orphan/unexpected target collections block activation. Resolve such findings
with a separately reviewed preservation/migration plan; never infer reviews from
legacy progress labels.

When the report is ready, explicitly select `MANGA_SHARED_BACKEND=firestore` in the
local server environment and restart. First use creates a local target binding;
first successful mutation initializes versioned remote metadata. Immutable artifacts,
workspace operations and signing keys remain under the same local root. Preserve
`.shared-artifact-store-id` and `.shared-backend.json` with its backups. Configuration
or provider failures never fall back to SQLite. Hosted guards remain unchanged.

Before any target initialization, rollback is possible with the application stopped:

```bash
uv run --locked python -m manga_worker.shared_cutover --release-empty-binding
```

This explicit command removes only the local binding, after proving the target is
completely empty. Then unset `MANGA_SHARED_BACKEND` to return to SQLite. Once the
Firestore target exists or contains metadata, the command refuses rollback;
reconciliation is required. Do not delete binding files to bypass that protection.
This feature does not deploy the app, change IAM/rules or migrate live data.

Run shared backend acceptance from the repository root:

```bash
npm run test:firestore
```

The runner starts a disposable loopback Firestore emulator, uses only the
`demo-shared-workflow` project and a synthetic named database, and runs the same
request contract against SQLite and Firestore alongside review/publication and
cutover regressions. It requires Java 11 or newer. It reuses or downloads the
SHA-256-verified emulator version pinned in the runner; set
`FIRESTORE_EMULATOR_JAR` to supply that exact jar offline. CI runs this command.
Ordinary Python discovery skips emulator tests when no emulator is configured;
those skips are not Firestore acceptance evidence.

## Cloud persistence adapters

The hosted pilot specification is [the hosted service plan](hosted-service-plan.md).
Cloud persistence adapters are optional worker dependencies:

```bash
uv sync --locked --package manga-worker --extra cloud --extra api
```

`CloudSettings` requires `FIREBASE_PROJECT_ID`, `FIRESTORE_DATABASE_ID`,
`MANGA_CLOUD_DATASET`, `MANGA_ARTIFACT_BUCKET`, and `MANGA_ARTIFACT_NAMESPACE`.
Select a clean dataset and canonical namespace for the hosted pilot. Do not reuse
the same-host Firestore dataset: its metadata binds to local artifact identity.
The cloud factory uses attached ADC and never falls back to SQLite or local bytes.
`MANGA_SHARED_BACKEND=cloud` selects cloud metadata and artifacts at the worker
service boundary. This is not an activation command for the hosted product;
frontend-only and private API verification guards remain enabled.

Project artifacts and shared audio use exact GCS generations and SHA-256 checksums.
Firestore stores conditional revision ownership and durable shared artifact references
under `hosted_workflow_v1/{dataset}`; shared request metadata remains under
`shared_workflow_v1/{dataset}`. Both bind to the same bucket/namespace identity.
Scratch caches are disposable. These adapters do not yet replace local operation
scheduling, workspace dispatch, or the hosted transport. No local data is imported.

The Firestore acceptance runner also covers hosted revision/reference transactions.
GCS behavior is tested with injected provider fakes; this does not establish real
bucket IAM, GCS semantics, or deployed durability. Those remain live acceptance gates.

## Hosted operation adapters

The optional Firestore operation store implements the same durable operation shape
as local SQLite, while keeping cloud execution identities separate from local PIDs.
Claims reserve global stage and project slots and persist dispatch intent before
Cloud Run is called. A lost start response is reconciled using the recorded execution
or matching execution environment; it never triggers a blind repeat of `jobs.run`.
Only an intent still transactionally proven unsubmitted can be safely retired without
an execution identity. Lease expiry alone never proves that a submitted job stopped.

Cloud mode adds `POST /internal/coordinator`, requiring an explicitly allowlisted
service subject with the `coordinate` action. It does not require or impersonate a
Firebase user. `S3_API_MODE=verification` and local mode refuse coordination; cloud
mode still refuses hosted project/operation/asset routes until transport integration.
Keep App Hosting frontend-only mode enabled. These are construction contracts, not
instructions to change deployed settings before the rollout gates pass.

The coordinator requires the cloud storage variables above, `MANGA_CLOUD_REGION`, and
explicit `MANGA_MAGI_JOB` / `MANGA_PIPELINE_JOB` names. Runtime code falls back to
`us-east4` when `MANGA_CLOUD_REGION` is absent; the hosted Terraform target explicitly
selects `us-central1` for the new API, jobs, and GCS bucket.
`Dockerfile.jobs` has `pipeline` and CPU `magi` targets and a dedicated build-context
allowlist. Jobs require explicit `CLOUD_RUN_PROJECT` and `CLOUD_RUN_LOCATION`; Cloud
Run supplies `CLOUD_RUN_JOB` and `CLOUD_RUN_EXECUTION`. Dispatch overrides provide only
the persisted operation ID and fence. Task retry zero and 30-minute timeout belong
to the reviewed deployment configuration; the application owns the attempt ceiling.

This target configuration does not establish deployment or authorize phase-5 live
calls. The worker restores pinned revisions and uploads into disposable scratch, persists
provider uncertainty before calls, and acknowledges accepted checkpoints only after
cloud persistence. After confirmed termination, the coordinator verifies/restores
the accepted manifest and recovers matching writer ownership. Uncertain provider
outcomes retain their slots until explicit operator resolution; accepted audio remains
eligible for reuse. The emulator gate exercises interrupted rendering with synthetic
audio and fresh scratch, not real model or provider compatibility.

## Hosted web transport and public intake

`MANGA_EXECUTION_MODE=cloud` selects authenticated private HTTP transport instead
of local Python. Unknown execution modes fail closed; the Python bridge itself also
refuses subprocess execution in cloud or frontend-only mode. Keep the checked-in
App Hosting frontend-only guard enabled until the complete hosted release passes
its acceptance gates. This setting is not deployment authorization.

Hosted studio uploads use one raw binary request per file, at most 10 MiB each,
followed by a compact JSON operation submission. Image creation accepts at most
40 pages; local studio limits remain unchanged. Upload manifests bind immutable
filenames to the verified admin and exact GCS references. Client-supplied artifact
references and revision IDs never establish trusted storage identity. Expected
project hashes still reject stale edits and review decisions. Idempotent retries
return the original operation even after that operation advances project state.

In cloud mode, `/api/extract` returns a queued operation with HTTP 202 instead of
running inference in the request. Supply `Idempotency-Key` and poll the existing
workflow status endpoint for its `result.texts`. Local extraction retains its
synchronous response. Ordinary reads and HTTP intake never initialize inference.

The private API independently authenticates service and user identities for shared
requests. Reader identities and admin approval actors come from verified credentials,
never request fields. Hosted reader intake allows five outstanding pending requests
and ten successful new requests per UTC day. Duplicate requests do not count again;
deletion does not refund daily quota. Approved/published work adds no pending count.
The daily ledger commits atomically with new requests.

Hosted playback keeps the same-origin reader-bound audio token and checks a valid
session on every request, including byte ranges. Set server-only
`MANGA_AUDIO_SIGNING_KEY` to the canonical base64 encoding of exactly 32 random
bytes through Secret Manager. Missing or invalid keys never select a local-file
fallback. Private responses stream through the application with `private, no-store`
and `nosniff`; draft assets and audition audio remain admin-only.

Hosted project creation requires a valid `work_id` for approved shared chapter work.
The server checks the work and its recorded approval inside the same transaction
as monthly reservation and operation creation. The allowance counts distinct work
IDs; retries and replacement projects for the same work do not consume another
chapter slot. Creation never implicitly links a project. Open the studio from the
approved request dashboard, then attach the intended project explicitly.
Do not enable hosted production before operational cost controls and the remaining
acceptance gates are complete.
