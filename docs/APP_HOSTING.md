# Firebase App Hosting setup

The checkout is linked to Firebase project `koetts-9bf7f` (KoeTTS). The App
Hosting backend is `koetts` in `us-east4`. Deployments use local source,
not automatic GitHub rollouts.

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

## Complete cloud initialization when ready

Run these commands from the repository root. Replace `YOUR_PROJECT_ID` with the
actual Firebase project ID; do not use the Atlas project from the example workflow.

```powershell
npx --yes firebase-tools@latest login
npx --yes firebase-tools@latest init apphosting --project YOUR_PROJECT_ID
```

Select the existing Blaze project. Select an existing App Hosting backend or
create one named `koetts`, choose a supported region, and set the
application root to `web`. Choose a Node.js runtime supported by both App Hosting
and the installed Next.js version. Keep the checked-in runtime settings when
prompted about overwriting `apps/web/apphosting.yaml` and review any generated changes.
The initialization flow may create cloud resources; run it only when ready to
associate this checkout with the real project.

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

For an operational hosted studio, first add a deployed processing backend,
durable storage, and authentication/authorization. Keep frontend-only mode enabled
until that integration is ready.

Validate the production website before rollout:

From the repository root, run `npm ci` and `npm run check`. Run
`npm run test:http` for the local production HTTP boundary.

Verify the adapter-generated production startup accepts the assigned port on the
container network interface. The existing local `start` script binds to loopback;
it has deliberately not been changed as part of configuration initialization.

If provider features are enabled later, use App Hosting secrets backed by Secret
Manager. Do not commit `GEMINI_API_KEY` or place it in a `NEXT_PUBLIC_` variable.
Firestore is not required to initialize or host the website.

The S3 authentication rollout adds an admin-only private-API diagnostic while
retaining frontend-only mode. It does not enable hosted generation or move local
projects into container filesystems. See [the S3 runbook](S3_DEPLOYMENT.md).

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
