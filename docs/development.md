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

Copy `apps/web/.env.example` to `apps/web/.env.local` on first setup, preserving any existing settings. Follow [Firebase authentication](FIREBASE_AUTH.md) for Google login, server credentials, and trusted admin claims. Browser-visible Firebase settings are public configuration; server credentials and `GEMINI_API_KEY` remain private.

```bash
npm run dev
# http://127.0.0.1:3000
```

The web server selects the root uv environment automatically. `PYTHON_EXECUTABLE` can select another absolute interpreter with the worker packages installed. Workers execute installed Python modules, not repository scripts. For new planning and synthesis, provide `GEMINI_API_KEY` in the server environment. Reviewing existing state and synthetic tests use no paid calls.

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
