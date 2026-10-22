# S3 authentication deployment

This runbook prepares the authorized authentication rollout in `koetts-9bf7f`
(project number `907898221016`), region `us-east4`. It is a deployment plan,
not evidence that deployment or live acceptance has succeeded. Record actual
revisions, commands and acceptance results in `alignment-status.md`.

## Baseline and intended changes

The discovered App Hosting backend is `koetts`, with public URL
`https://koetts--koetts-9bf7f.us-east4.hosted.app` and Cloud Run URL
`https://koetts-gu5jb64hpq-uk.a.run.app`. Its existing serving revision is
`koetts-build-2026-10-18-001`. Reconfirm that revision before rollout; preserve
any newer revision as the rollback target instead. The backend identity is
`firebase-app-hosting-compute@koetts-9bf7f.iam.gserviceaccount.com`, subject
`111180949335785966002`.

Deploy the private `koetts-s3-api` service using `Dockerfile.s3`, with a dedicated
runtime service account, request-based billing, minimum zero instances, maximum
one instance, one CPU and 512 MiB memory. Bind the process to `0.0.0.0:$PORT`.
Use `S3_API_MODE=verification`; configure project ID, the canonical service URL as
service-token audience, and an explicit service-subject/action allowlist.
Authentication diagnostics require only readiness and identity permissions.

Grant service invocation to the App Hosting runtime identity and the specific
verification identity. Grant the API runtime identity only the Firebase Auth
user-read capability needed for revoked-token checks. Verify the exact required
permission before granting a narrowly scoped role. Record each added binding;
restore only task-owned bindings on rollback. Public invokers and broad project
roles are outside this rollout.

The service has no workspace volumes, storage credentials, model cache, provider
keys or inference configuration. After successful authentication, project and
operation endpoints return unavailable responses. App Hosting retains
`MANGA_FRONTEND_ONLY=1`, minimum zero instances and maximum two instances. Its
new server diagnostic endpoint forwards a Google service token and exactly one
Firebase user credential to Python.

The existing named Firestore database is `koetts-default`. Inspect its deployed
rules and configure explicit browser deny-all access for that database if needed;
do not create another database or replace rules for an unrelated database.
Resolve the old `my-web-app` redirect hostname against the actual `koetts` public
hostname before publishing Firebase Auth configuration. Preserve valid existing
local and Firebase auth-handler entries.

## Preflight and rollout

1. Confirm authenticated deployment identity, billing, enabled services, existing
   admin claim (`admin: true`), Firebase web configuration, backend identity and
   Firestore rules. Do not assign or promote an admin account. Save current
   backend/service configuration, traffic, IAM, relevant Auth settings and rules
   in a private deployment evidence directory. Do not commit tokens or cookies.
2. Complete the production build and offline acceptance checks. Review the image
   build context to exclude private uploads, `results/`, credentials and caches.
   Build the API image from `Dockerfile.s3` and record its immutable digest.
3. Create the dedicated runtime identity only if absent. Record its numeric
   subject and the verification caller subject. Apply the reviewed narrow IAM
   changes, then deploy a private API revision with the limits above. For an
   existing service, use a no-traffic tagged candidate; retain its previous
   serving revision. For first creation there is no previous API revision:
   private IAM remains the access gate while validating the initial revision.
4. Configure the canonical API audience and explicit permissions using a reviewed
   environment file. Tagged candidate requests must still mint tokens for the
   canonical service audience. Verify readiness privately, then all API denial
   cases before configuring frontend traffic. Promote the accepted API revision.
5. Configure Firebase web variables, the private API URL and exact public
   `MANGA_APP_ORIGIN` for App Hosting. Next can receive an internal proxy URL;
   session CSRF must compare against the configured public origin, never trust
   forwarded-host headers. A missing/wrong value can reject valid session requests.
   Retain frontend-only mode. Roll out through App Hosting; capture its build,
   rollout and resulting serving revision. Do not manually deploy an unrelated
   frontend image over the managed backend.
6. Verify anonymous diagnostic rejection, reader denial, valid existing-admin
   sign-in and the admin diagnostic response. Verify wrong audience, unauthorized
   service subject, revoked user credentials and duplicate user credentials are
   rejected; verify authenticated project/operation requests remain unavailable.
   Confirm ordinary review and readiness do not initialize provider clients.
   Remove candidate tags when acceptance is complete.

Cloud Run's documented candidate and rollback command shapes are:

```bash
gcloud run deploy koetts-s3-api --project koetts-9bf7f --region us-east4 \
  --image IMAGE_DIGEST --service-account RUNTIME_SERVICE_ACCOUNT \
  --no-allow-unauthenticated --cpu-throttling --min-instances 0 \
  --max-instances 1 --cpu 1 --memory 512Mi --env-vars-file REVIEWED_ENV_FILE \
  --no-traffic --tag s3-candidate

gcloud run services update-traffic koetts-s3-api --project koetts-9bf7f \
  --region us-east4 --to-revisions ACCEPTED_API_REVISION=100
```

Replace uppercase placeholders with captured concrete values. The first command
is for an existing service; omit `--no-traffic` for its initial creation. A tag
provides a test URL and does not replace IAM authentication. See Google's
[private service authentication](https://cloud.google.com/run/docs/authenticating/service-to-service)
and [revision rollout documentation](https://cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration).

## Failure and rollback

Stop the rollout if an unauthorized request succeeds, the API cannot independently
verify both identities, hosted processing becomes available, private state appears
in logs, or existing-admin sign-in fails. Keep the previous frontend serving until
the private API passes acceptance.

For an existing API service, route traffic to its captured previous revision:

```bash
gcloud run services update-traffic koetts-s3-api --project koetts-9bf7f \
  --region us-east4 --to-revisions PREVIOUS_API_REVISION=100
```

Use App Hosting's rollout controls to restore the captured frontend build. If
immediate containment is needed, route its underlying `koetts` service to the
captured previous serving revision, then reconcile App Hosting's managed rollout
state. The initial known fallback is `koetts-build-2026-10-18-001`; use the refreshed
preflight value when it differs. Restore task-changed Auth settings and database
rules from the captured versions. Revoke only newly added invocation/runtime
bindings. For a first-created API, remove its invocation grants and delete that
service if the rollout is abandoned. Retain evidence and previous images until
rollback verification succeeds; do not delete pre-existing accounts or artifacts.

## Cost estimate and limits

With request-based billing and minimum zero instances, the intended idle compute
baseline is zero after scale-down. This is not a total-project zero-cost estimate:
startup and requests consume CPU/memory; network transfer, logs, image storage,
Cloud Build and App Hosting builds can add usage charges. Existing frontend,
Firestore and other project resources retain their own charges. Exact monthly
cost cannot be estimated reliably before measuring traffic, build duration and
artifact retention against current regional rates and account allowances.

The API maximum of one instance and frontend maximum of two limit configured
scale; they are not a hard billing cap. Review the billing budget and retained
images/builds after rollout. Consult current [Cloud Run pricing](https://cloud.google.com/run/pricing)
and [Firebase App Hosting costs](https://firebase.google.com/docs/app-hosting/costs)
before reporting a monetary estimate. No paid model generation is part of this
verification deployment.

## Reproduce identity acceptance

With gcloud authenticated and the verifier granted only
`iam.serviceAccounts.getOpenIdToken` on the dedicated service account, run:

```bash
python3 tests/verify_s3_identity.py
```

The script calls IAM Credentials `generateIdToken` directly. It keeps credentials
in memory, checks private readiness/denials and never impersonates a Firebase user.
Unlike gcloud's general impersonation flow, it needs no
`iam.serviceAccounts.getAccessToken` grant. Remove temporary verifier minting and
invocation bindings after acceptance.

In a real browser, first verify anonymous `/login` finishes session clearing
without an origin error. Then sign in with the existing admin and open
`/api/auth/backend` on the public hostname. Expected result is
`{"verified":true,"mode":"verification"}`. Do not share tokens or session cookies.
This human sign-in check is distinct from the synthetic offline identity tests.
