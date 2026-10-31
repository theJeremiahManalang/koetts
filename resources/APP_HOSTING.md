# Firebase App Hosting setup

The checkout is linked to Firebase project `koetts-9bf7f` (KoeTTS). The existing
App Hosting frontend backend is `koetts` in `us-east4`. Deployments use local
source, not automatic GitHub rollouts. This is the current frontend placement;
the planned frontend move to `us-central1` is a separate future migration.

Public URL: https://koetts--koetts-9bf7f.us-east4.hosted.app

## Monorepo build boundary

Run source commands from the repository root. `apps/web` is the configured application directory; the root npm workspace and lockfile remain the dependency authority. Keep those files in source uploads, and retain `apps/web/apphosting.yaml` beside the app manifest. Verify the provider's detected build root and root lockfile before rollout. A local build does not establish that the hosted adapter or configured runtime Node version has been verified.

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
phase-5 workflow has been deployed or live-verified. The currently configured
`S3_API_URL` still points to the historical `koetts-s3-api` verification service
in `us-east4`, which remains the verification target until an authorized cutover.

App Hosting remains frontend-only (`MANGA_FRONTEND_ONLY=1`). It does not host
Python workflow processing or make Gemini calls. Do not enable hosted generation
or run phase-5 paid/live validation from this setup guide.

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

App Hosting sets `MANGA_FRONTEND_ONLY=1` at build time and runtime. In this
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
plan. Keep frontend-only mode enabled until its rollout gates and cutover are
complete.

Validate the production website before rollout:

From the repository root, run `npm ci` and `npm run check`. Run
`npm run test:http` for the local production HTTP boundary.

Verify the adapter-generated production startup accepts the assigned port on the
container network interface. The existing local `start` script binds to loopback;
it has deliberately not been changed as part of configuration initialization.

If provider features are enabled later, use App Hosting secrets backed by Secret
Manager. Gemini uses the pipeline service identity; do not grant model inference to the frontend. Never commit credentials or place them in `NEXT_PUBLIC_` variables.
Firestore is not required to initialize or host the website.

The existing admin-only private-API diagnostic still targets the historical
verification service until cutover. It does not enable hosted generation or move
local projects into container filesystems. See [the historical S3 runbook](../docs/archive/S3_DEPLOYMENT.md).

## Deploy later

After cloud initialization and the application readiness checks above, deploy
only the intended App Hosting backend from the repository root:

```powershell
npx --yes firebase-tools@latest deploy --only apphosting:koetts --project koetts-9bf7f
```

If you changed the backend ID, update both the command and `firebase.json`.

References:
- https://firebase.google.com/docs/app-hosting/alt-deploy
- https://firebase.google.com/docs/app-hosting/configure
