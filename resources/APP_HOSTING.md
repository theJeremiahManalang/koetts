# Firebase App Hosting setup

The checkout is linked to Firebase project `koetts-9bf7f` (KoeTTS). The existing
App Hosting frontend backend is `koetts` in `us-east4`. Deployments use local
source, not automatic GitHub rollouts. This is the current frontend placement;
the planned frontend move to `us-central1` is a separate future migration.

Public URL: https://koetts--koetts-9bf7f.us-east4.hosted.app

## Monorepo build boundary

Run preparation from the repository root. The app directory is `apps/web` and
root npm manifests remain authoritative. Direct source deployment from the raw
checkout failed live with `Missing Lock File` at `/workspace/apps/web` on
2026-11-01. Firebase documents native monorepo support for Nx and Turborepo;
this repository uses plain npm workspaces.

Use `tools/prepare_apphosting_source.py --output /tmp/koetts-apphosting-UNIQUE`
to create a sanitized app-only source tree. The helper places the web app at
the stage root, derives its deployment lock from the canonical root lock without
resolving new versions, and projects root npm overrides and the package-manager
pin into its manifest. Its stage-only Firebase config targets the existing backend
with `rootDir: "."`. The stage-only `MANGA_STANDALONE_WEB=1` setting makes Next.js
use the app root for tracing so the Firebase adapter can locate standalone output.
Local development retains the normal workspace roots. The derived manifest and
lock exist only in staging; do not commit a second workspace lockfile. Unexpected
workspace links fail preparation. Dependencies, generated outputs, credentials,
local data and infrastructure state are excluded.

Deploy from the generated tree using the pinned Node/npm tooling. Record the
source candidate, staging manifest and actual App Hosting build result; a local
build alone does not establish hosted adapter acceptance. See the official
[framework support](https://firebase.google.com/docs/app-hosting/frameworks-tooling)
and [monorepo guide](https://firebase.google.com/docs/app-hosting/monorepos).

## Configuration

- `firebase.json` targets the Next.js app in `apps/web/` with backend ID
  `koetts` for KoeTTS. Change this ID if using a differently named backend.
- `apps/web/apphosting.yaml` configures the website runtime: 1 CPU, 512 MiB RAM,
  zero minimum instances, two maximum instances, and concurrency of 40.
- Local dependencies, generated output, project data, model weights, assistant
  settings, and environment files are excluded from source uploads.
- No credentials or provider secrets are included. `.firebaserc` records the
  selected Firebase project; it contains no credentials.

The instance limit controls serving capacity; it is not a billing cap. Builds,
storage, traffic, and other services may still incur charges on Blaze.

## Existing hosted services and target

The existing Firestore database is `koetts-default` in `nam5`. New hosted API,
Cloud Run jobs, and GCS artifacts target `us-central1`; the new API service name
is `koetts-api`. These are target settings, not proof that the replacement API or
phase-5 workflow has been deployed or live-verified. The deployed phase 5 `S3_API_URL` points to
`https://koetts-api-gu5jb64hpq-uc.a.run.app`. Frontend revision `koetts-build-2026-10-31-004` serves 100% after cutover. It
also references `hosted-audio-signing-key@1` at runtime only.

The admin-access follow-up configures `MANGA_FRONTEND_ONLY=0` and
`MANGA_EXECUTION_MODE=cloud` so verified admins can reach the studio and request
dashboard for manual acceptance. Processing still occurs only through the private
backend; the frontend does not run Python or call Gemini. Production remains
paused with provider calls disabled until test limits and activation are ready.

## Initialize a different Firebase project

The current checkout is already linked to `koetts-9bf7f`; do not run initialization
to recreate its existing backend. For a separate project, replace `YOUR_PROJECT_ID`
with its actual project ID. These commands may create resources.

```powershell
npx --yes firebase-tools@latest login
npx --yes firebase-tools@latest init apphosting --project YOUR_PROJECT_ID
```

Select the intended Blaze project and backend, set the application root to
`apps/web`, and choose a supported Node.js runtime. Keep the checked-in runtime
settings when prompted about overwriting `apps/web/apphosting.yaml`, then review
all generated changes. This is setup guidance only, not authorization to deploy.

GitHub integration is optional. No automatic deployment workflow is installed.

## Frontend deployment mode

`MANGA_FRONTEND_ONLY=1` is the fallback website-only mode. In this
mode, `/` redirects to `/browse`, and all workflow, extraction, and asset handlers
reject anonymous/reader requests with 401/403. Verified admins receive HTTP 503
before reading uploads, accessing project files, or starting Python.
The local studio remains available at `/` when this variable is unset.

The checked-in reader and request screens use the local shared API, which is
unavailable in frontend-only mode. They show an unavailable state rather than a
shared catalog or browser-local request submission. A previously deployed version
may differ; inspect deployed behavior before rollout. No Python processing or
Gemini calls are provided by this frontend deployment.

The separate hosted API, jobs, and storage target is documented in the hosted
plan. After private API readiness, cutover and paused budget initialization, cloud admin
navigation may be enabled for manual acceptance. Keep the budget ledger and schedules
paused until production acceptance and measured limits are ready.

Validate the production website before rollout:

From the repository root, run `npm ci` and `npm run check`. Run
`npm run test:http` for the local production HTTP boundary.

Verify the adapter-generated production startup accepts the assigned port on the
container network interface. The existing local `start` script binds to loopback;
it has deliberately not been changed as part of configuration initialization.

If provider features are enabled later, use App Hosting secrets backed by Secret
Manager. Gemini uses the pipeline service identity; do not grant model inference to the frontend. Never commit credentials or place them in `NEXT_PUBLIC_` variables.
Firestore is not required to initialize or host the website.

The admin-only private-API diagnostic uses the new cloud API URL after phase 5
cutover. Authenticated diagnostic verification remains part of manual acceptance. It does not enable hosted generation or move
local projects into container filesystems. See [the historical S3 runbook](../docs/archive/S3_DEPLOYMENT.md).

## Deploy later

After cloud initialization and readiness checks, prepare a new source stage from
the repository root, then deploy only the intended backend from that stage:

```bash
python tools/prepare_apphosting_source.py --output /tmp/koetts-apphosting-UNIQUE
cd /tmp/koetts-apphosting-UNIQUE
firebase deploy --only apphosting:koetts --project koetts-9bf7f --non-interactive
```

If you changed the backend ID, update both the command and `firebase.json`.

References:
- https://firebase.google.com/docs/app-hosting/alt-deploy
- https://firebase.google.com/docs/app-hosting/configure
