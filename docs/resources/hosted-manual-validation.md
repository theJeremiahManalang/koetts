# Hosted manual validation evidence

Use the [admin processing acceptance checklist](admin-processing-acceptance-checklist.md)
to record expected and actual behavior separately for local and hosted passes.
The prior manual pass and source-level findings are recorded in the
[phase 5 manual acceptance review](phase-5-manual-acceptance-review.md).

This guide records a human-run validation pass after an authorized deployment.
The log collector is read-only: it runs `gcloud logging read` for one explicit
UTC window and the `koetts-api`, `koetts-magi`, `koetts-pipeline`, and
`koetts-artifact-gc` Cloud Run resources in `us-central1`, plus the existing
`koetts` frontend in `us-east4`. It makes no provider
calls, starts no jobs, changes no cloud configuration, and does not inspect
credentials.

After the reviewed frontend and API are deployed, hosted Studio status should arrive
over authenticated `/api/workflow/events` SSE. During an approved hosted run, confirm
status changes arrive without recurring
`/api/workflow?job=` requests. Reload or disconnect and confirm the stream reconnects
to current operation state without submitting another operation. Sign out and
confirm the browser closes the stream; server authorization must also close a stream
within 30 seconds after revocation. The five-minute stream rotation should reconnect
to the current state. Local Studio retains its existing polling path.

## Admin access and first manual pass

The hosted admin UI requires `MANGA_FRONTEND_ONLY=0` and
`MANGA_EXECUTION_MODE=cloud`, plus a verified Firebase `admin: true` claim.
Frontend-only mode redirects all users, including admins, away from the studio
and request dashboard. The admin-access follow-up deploys cloud UI mode while
keeping the budget ledger and schedules paused and provider allowance zero.
Enabling navigation does not authorize or enable paid generation.

1. Open the deployed `/login` page and sign out/sign in again with the intended
   administrator account. This refreshes the claim and server session.
2. Open `/admin/requests` for the request dashboard, and `/` for the studio.
   A non-admin account must still be denied or redirected to Browse.
3. Open `/api/auth/backend` in the signed-in browser to check the frontend/private
   API identity path. Record status and sanitized error text; never copy cookies
   or tokens into evidence.
4. Create a test chapter request through `/request`, then approve it through
   `/admin/requests`. Check that approval alone starts no processing.
   Open Studio through an approved request's project-creation link so its work
   reference is selected. Opening Studio directly without an eligible work keeps
   project creation disabled; that is separate from production pause.
5. Confirm production status is paused. Do not resume using the setup cost caps.
   Extraction/generation require separately configured measured test limits and
   explicit activation; they remain blocked during this first access pass.

Locally, use the existing configured environment and pinned tooling:

```bash
MANGA_FRONTEND_ONLY=0 MANGA_EXECUTION_MODE=local npm run dev
```

Sign in at the local site with the admin account, then use the same dashboard and
studio paths. Local paid generation is user-operated and remains within the
approved Gemini campaign allowance. See [admin claim setup](../../resources/FIREBASE_AUTH.md)
if access still fails after refreshing the session.

## 1. Run local acceptance

From the repository root, capture the candidate and its local checks before
opening the hosted admin workflow:

```bash
git rev-parse HEAD
git status --short
npm run check:repo
npm run check
npm run test:http
```

Record each command, exit code, and relevant output path in the deployment
evidence. If a check is not applicable or cannot run, state why; do not report it
as passed. These checks establish local results only.

Manually test the local admin flow as well as the hosted flow. Keep separate
records for the two environments, including candidate, test window, tester,
steps, expected/observed behavior and blocking defects. Preserve relevant local
server output and browser errors privately; never record tokens or cookies.

## 2. Have the hosted administrator validate

The authorized project administrator should verify the deployed API is private
and healthy, the intended revisions and job images are serving, authentication
and denial cases behave as expected, and production remains paused until its
acceptance gates pass. Validate operational recovery, budget pause behavior, and
artifact cleanup only through the approved admin procedures. Record timestamps,
resource names, observed revisions/execution IDs, check outcomes, and links or
paths to evidence. Do not place access tokens, secret values, or credential
material in the evidence.

An operator with permission to read Cloud Logging can capture a narrow window
for review. Choose a new output directory for every capture; raw logs may contain
user or operational data and must stay private and uncommitted:

```bash
uv run python tools/capture_hosted_logs.py \
  --since 2026-11-01T00:00:00Z \
  --until 2026-11-01T01:00:00Z \
  --output results/hosted-validation-20261101T010000Z
```

Replace the example timestamps with the exact validation interval. The defaults
are project `koetts-9bf7f` and region `us-central1`; pass `--project` or
`--region` only when the authorized target differs. Output contains `logs.json`
with raw entries and `summary.json` with time, severity, HTTP/payload status and
resource counts. The output directory is mode `0700`; files are mode `0600`.
The command refuses an existing directory and any output outside the repository
`results/` directory, which is ignored by Git.

Review the summary and relevant raw entries against the administrator's
validation record. An empty result can mean no matching entries in that interval;
it does not prove a service or job was exercised. Logs are not a complete audit
trail and do not establish Gemini usage or model-cost accuracy. Reconcile billing
separately in the GCP console using the authorized billing view.

## 3. Preserve and share evidence

Keep raw logs in the private ignored output directory for authorized review. Do
not commit, publish, upload, or copy raw logs into an issue or report without the
administrator's approval of the exact export and destination. Share only a
reviewed summary when its contents and destination are approved. Keep the local
acceptance record, administrator observations, deployment target/revisions, and
log capture window together so the evidence can be traced to the same rollout.
