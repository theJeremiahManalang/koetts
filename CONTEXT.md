# Active task: phase 5 deployment and manual-validation handoff

## Objective and authorization

The user approved deployment of the hosted backend and cutover of the existing
frontend (option B), within USD 5 incremental infrastructure/build spend. The
frontend stays in us-east4; new API/jobs/artifacts use us-central1. Frontend regional
migration and retirement of koetts-s3-api remain excluded.

The user runs paid Gemini calls manually within USD 5; the agent captures available
logs and must not initiate model calls. One approved chapter sample, at most 40
pages, one planning action and one short synthesis action were selected; exact
sample/length and measured production limits remain to be settled by the manual
validation. Both local and hosted admin flows require manual acceptance. Publication
intent is approved, but exact-export human cast/script/audio-review and admin
publication decisions remain required. No audiobook was published.

Combined project monitoring is accepted: USD 20 budget, USD 10/15/20 alerts,
USD 15 production pause inclusive of infrastructure and Gemini. The user monitors
the cost breakdown in GCP; separate SKU budgets are not a prerequisite.

## Current live state

Project koetts-9bf7f, database koetts-default in nam5. Branch feat/hosted-service,
Phase 5 review baseline 75b0f5bac39a. Git history records the checkpoint commits;
deployment source hashes record
the dirty candidate; do not identify deployed source solely by HEAD.

- API: koetts-api-00003-fx8 ready, private, canonical URL
  https://koetts-api-gu5jb64hpq-uc.a.run.app. URI and configured audiences match.
- Frontend: koetts-build-2026-10-31-004 serves 100% in us-east4 at
  https://koetts--koetts-9bf7f.us-east4.hosted.app. Its API URL and signing-secret
  reference were verified. MANGA_FRONTEND_ONLY=0 and MANGA_EXECUTION_MODE=cloud
  enable admin navigation; production remains paused. Stage-only MANGA_STANDALONE_WEB=1 is deployed.
- Old API koetts-s3-api-00001-gl5 remains preserved, unchanged.
- CPU jobs koetts-magi, koetts-pipeline, koetts-artifact-gc exist. No task-owned
  inference job or paid Gemini call was started. Both hosted-coordinator and
  hosted-artifact-gc Scheduler jobs are PAUSED.
- New bucket koetts-9bf7f-hosted-artifacts-us-central1, managed prefix
  hosted/pilot_20261101/, clean dataset hosted_pilot_20261101. Public access
  prevention enforced, uniform access enabled, soft delete disabled. Existing
  buckets/local state were not adopted or migrated.
- New Artifact Registry repository koetts-hosted in us-central1 was created via
  gcloud outside Terraform. Three immutable image digests are in ignored tfvars
  and build evidence.
- Signing-secret hosted-audio-signing-key version 1 generated in memory. Bytes
  were never printed or stored in Terraform; frontend receives a secret reference.
- Combined billing budget ID 35812220-da85-4ad5-876f-562c39dc7f6d, account
  015A92-BF8230-2032AA. Real Pub/Sub billing interval ingestion verified.
- Budget controls initialized and explicitly PAUSED. Provider allowance and call
  caps are ZERO. USD 5 infrastructure caps per stage are hold-only setup values,
  not measured production estimates. DO NOT resume with these setup caps.

## Deployment and verification evidence

Private, ignored results/phase5-20261101 contains source manifests, Terraform
plans/apply logs/outputs, build metadata/logs, public HTTP checks, live configuration
metadata and budget status/delivery evidence. Preserve ignored infra/hosted/
phase5.auto.tfvars.json, local Terraform state and backups; there is no remote
Terraform backend. Never delete or recreate durable cloud data to roll back.

Backend Cloud Build 1253ba16-0971-4ec5-8bff-f71f664766c4 succeeded. Initial Terraform
apply failed at billing-budget creation because ADC lacked quota project; explicit
billing_project and user_project_override fixed it. Resumed apply succeeded. Actual
API URI was then discovered and reviewed URL/audience updates applied. Removed
unnecessary datastore.entities.delete from budget operator role before provisioning.

Frontend builds 44324eb0-9df6-49ef-8c41-85fa5e27fa43 (missing app-local lock) and
c7029165-39c8-4312-9f2c-cb5670cbb78f (nested standalone adapter path) failed before
promotion. App-only staging with deterministic root-lock/override projection and
explicit standalone tracing fixed packaging. Exact adapter14.0.21 passed locally;
final Cloud Build f355931c-78ec-44ad-9e0b-8bbea05bd5bd and App Hosting rollout
succeeded. Clean stage /tmp/manga-apphosting-flat-final-20261101; regenerate using
tools/prepare_apphosting_source.py for future deployments, not raw checkout deploy.

Verified live: API has no public invokers and returns403 without credentials;
Firestore browser rules deny all; billing topic has system publisher; frontend
browse/login200, unauthenticated auth diagnostic/production/workflow401. Current
Studio/dashboard use streamed Login redirects for unauthenticated visitors. Frontend service-account impersonation was denied; no grants expanded.
Authenticated frontend/admin/session/playback acceptance remains manual.

Final deployment log capture found billing-report429 retries against uninitialized
ledger. Initialization with provider calls disabled, then explicit pause, recovered
real report ingestion. October interval reported preliminary zero; no final charge
reconciliation claimed. Logs: results/phase5-deployment-final-20261101 and
results/phase5-billing-recovery-20261101. Baseline earlier in
results/phase5-baseline-20261101. Raw logs remain private and uncommitted.

Checks: pinned Node22.22.3/npm10.9.8 HTTP production acceptance passed studio and
frontend-only modes after final Next config change; typecheck passed. Repository
checks, Ruff on both helpers,10 infrastructure unit tests, Terraform schema/plan
validation, lock consistency and exact local adapter output checks passed. Initial
sandbox DNS/provider process failures recovered with authorized escalation. Next
still warns about dynamic filesystem tracing in lib/python.ts. Full npm run check passed before the HTTP regression fix (333 Python/93 skips,
90 web); afterward full Python334/93 and required HTTP acceptance passed. Manual
full admin/provider acceptance is not claimed.

## Changed paths

Dockerfile.s3 installs cloud extras; cloudbuild.hosted.yaml builds three images;
infra/hosted/main.tf narrows operator permissions; versions.tf sets quota project.
apps/web/apphosting.yaml switches API and signing-secret reference; next.config.mjs
selects app-only tracing for staging. firebase.json excludes infrastructure/state
from uploads. tools/prepare_apphosting_source.py stages a clean standalone web app;
tools/capture_hosted_logs.py captures narrow API/jobs and east-region frontend logs.

Docs record combined policy, authorization, deployment, manual acceptance and
staging procedure: STATUS, hosted-service-plan, phase-5-authorization, hosted cost/
infrastructure/rollout/manual-validation guides, APP_HOSTING and docs/README.

## Remaining work / next action

Handoff current guarded deployment for manual sign-in/backend diagnostics. Capture
and review the user's exact UTC test window with the log helper. Before full hosted
admin/production testing, establish measured operation/call caps, configure the
user-controlled provider allowance, verify remaining identity/recovery/benchmark/
playback/rollback acceptance, and explicitly enable production under those controls.
Do not initiate Gemini calls or publish an unspecified export. Cloud admin
navigation is enabled; keep schedules and ledger paused until applicable gates pass. Phase 5
is not complete. Actual infrastructure/build charges remain delayed/unreconciled.

Final billing-recovery capture confirms HTTP200, no warnings/errors in that window.
Final repository checks and git diff --check passed. No outstanding deployment processes.


## Active follow-up: hosted admin access

User cannot access admin flow. Confirmed root and /admin/requests redirect every
user when MANGA_FRONTEND_ONLY=1. Within approved deployment/manual-testing scope,
changed source apphosting.yaml to MANGA_FRONTEND_ONLY=0 and MANGA_EXECUTION_MODE=cloud
(BUILD/RUNTIME); no route/role changes. Read live ledger before deploy: PAUSED and
provider allowance0. Schedules remain paused; do not enable paid production.
Pinned web tests passed24/24. Clean stage /tmp/koetts-admin-access-20261101; App
Hosting deploy session60273, log results/phase5-20261101/admin-access-deploy.log.
Wait deploy then verify actual env and unauthenticated studio/dashboard redirects
to login rather than blanket Browse. Async question asks which Google account user
signs in with, to verify existing admin claim; no role promotion authorized for an
unidentified account. Updated manual-validation guide with exact paths and first
non-processing manual pass. Authenticated full flow and provider limits remain open.

Read-only Firebase lookup verified the user-identified account already has
admin:true and disabled:false. No claims or roles changed. Access blocker is
website-only mode, not missing admin privilege.

Admin access deploy completed: build29b0506f-bc92-4cb3-ad08-edab330f740a, serving
revision koetts-build-2026-10-31-004 at100%. Actual environment flags verified.
Unauthenticated / and /admin/requests return HTTP200 streamed Login redirects,
not server errors or Browse redirects; browse/login200. Verification evidence:
results/phase5-20261101/admin-access-serving.json and admin-access-http.json.
No role changes, provider calls, schedule activation or production resume.
Next: user signs out/in and tests dashboard/studio/backend diagnostic; capture their
window for review. Processing remains blocked until measured limits/activation.


## Goal continuation: checkpoint and review

Previous turn made progress: cloud admin access was deployed/verified. Full pinned
`npm run check` passed:333 Python tests,93 optional skips,90 web tests, lint,
typecheck and production build (results/phase5-20261101/phase5-full-check.log).
Preparing deployment checkpoint commit against phase-start75b0f5b, then independent
Standards/Spec review. Fresh-checkout worker owns only tools/verify_fresh_checkout.py
to include resources/infra safely and run disposable onboarding acceptance.

User reports successful hosted login/upload but project create notification error
and sometimes disabled button. Captured logs results/admin-project-create-20261101:
/identity200, uploads200, /shared200, /production/status200, /operations400 twice.
Found potential HTTP catch masking CloudBudgetExceeded(RuntimeError) as400; build
ASGI regression to prove429 production_paused is preserved. No agent provider calls
or production resume. User exact notification text still unavailable.


Checkpoint109c539 committed. Independent code-review against75b0f5b: Standards
0hard violations,1smell unused project parameter in log filter; removed. Spec0code
findings; remaining live gates acknowledged. Fresh-checkout helper fixed and
verified with pinned tooling:333Python/93skips,90web, no torch, CLIentrypoints.
User explicitly chose KEEP PRODUCTION PAUSED when offered oneCPU-onlytrial.
Do not resume or enable dispatch. ASGI regression reproduced wrong400vs429 in
0.068s with injected paused backend; one-line exception propagation fix passes
all15HTTPunit tests. Default-sandbox test hung and was explicitly stopped (130);
escalated synthetic regression then ran red and green. Next commit tools/review
fixes, then API regression fix and independent follow-up review before deployment.

Tool review/fresh-copy fixes committed cb970be. API budget-denial fix verified:
15HTTPunit,334Python/93optional skips, and pinned disposable studio/frontend-only
HTTP acceptance passed (http-budget-denial-regression.log, python-budget-fix.log,
http-budget-fix-acceptance.log). User confirms hosted login/upload; actual logs
showidentity/projects/shared/status/upload200 and create400. Captures do not
prove session revocation or full production acceptance. Next commit minimal API
exception fix plus regression, run independent follow-up reviews, build/deploy
API-only update. Keep production/schedules/providercalls disabled.


## Goal continuation outcome

Manual acceptance follow-up: user completed the checklist on revision
`b411be03a2cd2842f3e597d25008df6aaed422eb` with Opera GX. Local Google sign-in is
resolved; local upload/admin/request/approval pass. Standalone local creation is
intended, but the UI lacked a mode label. Hosted login, dashboard, API diagnostic,
upload and paused-denial pass; direct Studio after upload reported Create enabled.
Source trace found stale selected-work eligibility across URL navigation; hosted
server admission and production pause remain authoritative. Implemented URL-reactive
selection, matching-ID gating, and explicit context labels. RCA:
`docs/resources/phase-5-manual-acceptance-review.md`; updated checklist and docs
pointers. Focused mounted-Studio navigation/upload/context/draft tests 19 pass; typecheck and build pass. Full web
suite 89/90 under unsupported Node 24/npm 11; multipart stream test fails with a
closed ReadableStream. HTTP suite setup also fails on DNS while downloading `h11`.
Node 22.22.3 unavailable. No browser package; manual live
retest pending. Production/schedulers remain paused; no paid calls. Review delta
against `b411be0` next, then deploy only after review and request user manual retest.

Commits109c539 deployment, cb970be Standards/fresh-checkout fixes,4b3b7a7 HTTP
paused-error regression. Independent Standards and Spec follow-up reviews of
109c539...4b3b7a7 both clear; original Standards smell resolved. Review record:
docs/resources/phase-5-code-review.md. Branch ancestry verified main merge-base
0bdacc5cd0092cf33d53afb4d12f6b64b5ba16bb.

API-only build ec6667fc-bf83-42d1-aa1b-3460dcb33e36 succeeded; immutable image
sha256:d642438d400fdd8385c948eb746795ab41bb696bcd81115addc25d684869e107.
Reviewed Terraform plan changed only API image, applied successfully; revision
koetts-api-00003-fx8 ready, digest matches. Previous revision02 remains rollback
target. Post-rollout SDK read verified paused ledger/provider allowance0, gcloud
verified both schedules PAUSED. No image extraction, Gemini call or publication.

User explicitly chose KEEP PRODUCTION PAUSED; do not ask again or resume. An async
manual question asks whether retrying Create now yields the paused notification;
no answer yet. User's sometimes-disabled Create also requires approved-work
selection from dashboard; guide updated. Full phase5 cannot be declared complete:
manual full-flow/CPU/model quality, session revocation, authenticated playback,
restart/rollback and finalcost evidence remain pending, with processing intentionally
disabled. This goal turn made progress (commits/reviews/regression/deployment), not
a blocked/no-progress turn. Continue independent acceptance work if available;
never run paid models or override the production pause.

Latest manual-acceptance remediation: commits `50ea875`, `4b6abed`, and `4ec5db3`.
Final Standards and Spec reviews against `b411be0` found no remaining findings.
Mounted Studio navigation test covers approved work, removing the query, switching
to another work with delayed verification, and button enablement only after the new
work verifies. The user-reported hosted Create failure remains pending manual retest.
Local standalone creation is preserved and labeled. Typecheck, production build,
19 focused UI/upload/context tests, repo check and diff check passed. Full web suite
was 89/90 under unsupported Node24; HTTP acceptance setup hit DNS failure downloading
`h11`. Sanitized App Hosting source staged at `/tmp/koetts-apphosting-acceptance-50ea875`.
Remote deployment was not attempted because managed-cloud readiness tooling and the
network policy snapshot were unavailable. After cloud runtime readiness is available,
deploy the frontend under existing authorization and request the hosted retest. Keep
production and schedulers paused; no paid calls or publication.

Local Gemini configuration follow-up: user requested explicit project + ADC or a
configured client. Added `GOOGLE_CLOUD_PROJECT=koetts-9bf7f` and
`GOOGLE_CLOUD_LOCATION=us` to ignored `apps/web/.env.local` without changing other
settings. ADC credential file exists at gcloud's standard path, but credentials were
not validated or read and no Google API/model call was made. Managed-cloud status
and network-policy snapshot remain unavailable; gcloud's config directory is
read-only here. Next: user completes/validates `gcloud auth application-default login`
in their local terminal, then restarts the dev server. Do not initiate Gemini calls.

Hosted async delivery implementation: phase one Eventarc dispatch and phase two SSE status delivery are committed and independently reviewed against `9def19c` and `4188ae4`; both Standards and Spec axes are clear. Phase one commits: 1354457, d05eec6, 46bf1a2, 0310348, 8c2f4af, eaaf30e, 4188ae4. Phase two commits: 49ed3bc, fe2405d, 37a9a4f, 7c3efd0. Studio reconnects from saved operation state, checks admin authorization on events and every 30 seconds while idle, rotates the stream after five minutes, and does not submit duplicate work. Local keeps polling.

Checks: 15 focused web tests, two backend SSE tests, typecheck, production build, Ruff, repository links/boundaries, and Terraform formatting passed. Full web suite was 99/100 under unsupported Node24; the existing multipart stream test fails with `ReadableStream is already closed`. HTTP acceptance setup could not download `google-cloud-core` because DNS failed. Firestore emulator tests skipped because no loopback emulator is configured. Offline `terraform validate` passed. A remote Terraform plan, apply, and live stream test remain pending because managed-cloud status tooling is unavailable and the network-policy snapshot is missing. Production and schedulers remain paused; no paid calls occurred.

Next: obtain current managed-cloud readiness, produce a valid Terraform plan for Eventarc, TTL and index, then request apply authorization. After apply, deploy frontend/API revisions and perform approved live SSE and delivery checks before production readiness. Preserve the user's recorded local admin/audio pass and request a hosted retest; do not resume production or run provider calls without authorization.

Refreshed the sanitized App Hosting source using the final reviewed phase-two code at
`/tmp/koetts-apphosting-async-49ed3bc`. The current worktree is clean at `e56f259`;
Eventarc/IAM/Firestore index and TTL resources are in Terraform, and offline
`terraform validate` passes. Do not attempt plan/apply until managed-cloud status and
network policy are available; no remote changes have occurred.

## Review follow-up: 9def19c...639a3f8

The user requested the code-review skill and explicitly selected baseline
`9def19c`. Independent Standards and Spec reviews covered
`git diff 9def19c...HEAD` at `639a3f8`. This review supersedes the earlier clear
review conclusions for production readiness. Standards found one documented
violation: the asynchronous Eventarc endpoint performs blocking authorization,
adapter construction and cloud dispatch on the event loop, contrary to
`docs/ARCHITECTURE.md:117`. One judgement-call smell is duplicated polling/SSE
operation completion handling in Studio.

Spec found three P1 blockers: `watch_public` returns a three-item transaction
result although `_run` expects `(result, binding_exists)`; the Firestore watch
callback receives a snapshot list but treats it as a single snapshot; Eventarc
uses the compute region `us-central1` instead of the existing Firestore database
location `nam5`. The first causes valid SSE subscriptions to return HTTP 400; the
second breaks change delivery after the first is fixed; the third prevents the
proposed trigger from deploying against the approved database. Separate Eventarc
source location from the Cloud Run destination region.

Evidence was source inspection, installed Firestore SDK watch implementation and
official Eventarc documentation. No tests were run during this review. Only this
handoff was changed; no runtime fixes, deployment, model calls or production
resume occurred. Next action: remediate these findings and add regression coverage
that exercises the actual store transaction and SDK callback contracts before
repeating focused checks and review. Live acceptance remains outstanding.

## Review remediation completed

User authorized fixes and repeat review. Fixed transaction result shape, Firestore
snapshot-list handling, and worker-thread execution of Eventarc authorization and
dispatch. Extracted shared Studio terminal/reconciliation handling. Eventarc now
uses `firestore_database_location` (default `nam5`), independently of destination
`region`. Added store regression coverage and thread assertions; updated infra
coverage and operational documentation. Runtime files, tests, Terraform and this
handoff are the changed paths; no deployment or paid calls occurred.

Checks: backend store regression 1 pass, hosted HTTP unit tests 8 pass, infra unit
tests 11 pass, Ruff, repository checker, Terraform fmt and validate, web typecheck
and production build pass. Terraform provider startup required sandbox escalation;
validation then passed. Initial pytest invocation failed because pytest is not
installed; infrastructure checks passed under unittest. Default uv cache is
read-only; direct installed Python repository checker passed. Build retains the
existing dynamic filesystem tracing warning. Web checks use unsupported Node24.
Independent Standards and Spec re-reviews of `9def19c` through the working tree
both found zero remaining findings. Full production HTTP acceptance and live
Eventarc/SSE acceptance were not rerun. Production remains paused; next action is
reviewed cloud plan/apply authorization and hosted acceptance under existing gates.
Focused web checks: 10 tests passed with `--test-isolation=none`; default isolated
runner failed without useful diagnostics. The existing source assertion was
updated to follow shared terminal handling. No claim of a full-suite pass.

## Approved test/CI audit and remediation (2026-11-02)

User approved audit, workflow/test refactoring, contract additions and local
verification against baseline `7e9e908`. Inventory: one workflow, 55 Python files
under tests including helpers, 25 web test files; no other tracked test trees.
Report: docs/resources/test-ci-audit.md, linked from docs/README.md.

Changed .github/workflows/ci.yml: fast preflight, parallel five-suite acceptance
matrix, preserved final check gate, PR concurrency cancellation, existing npm/uv
caches, emulator jar cache, explicit Java21 and retained failure logs. The existing
checksum-pinned disposable emulator supplies backing service; container omitted to
avoid duplicating readiness/lifecycle. tools/verify_shared_firestore.py accepts
--log-file to preserve diagnostics. Web tests remove redundant source-text checks
and tautology, use fake timers/deferred responses, and add parameterized endpoint
and SSE authorization/validation/error/cancellation contracts. Python tests use
condition notifications and explicit contention signals, extend real listener
terminal-result coverage, add SSE denial/missing/error/cleanup contracts, and remove
dead mock setup. Legitimate optional skips and bounded condition polling remain.

Emulator execution exposed real bare-bool transaction result in
cloud_operations.repair_dispatch_signals. Both branches now return (result,bound).
Existing integration test covers repair and rate limiting; no duplicate added.
Independent Standards review of CI/tools/web and Spec review of tests plus
follow-up CI/runtime review found zero remaining findings.

Final pinned Node22.22.3/npm10.9.8 checks: npm run check PASS (347 Python/97
prerequisite skips,104 web,lint,typecheck,build); test:http PASS; test:firestore
PASS all108 after initial failure/fix; verify_fresh_checkout.py PASS. Existing
Next dynamic filesystem tracing warning remains. Logs /tmp/manga-audit-final-check.log,
/tmp/manga-audit-http.log, /tmp/manga-audit-firestore-final.log,
/tmp/manga-audit-onboarding.log. Sandbox loopback/uv cache limits required escalated
local runs; no cloud/provider calls, production resume or deployment occurred.
No GitHub-hosted run performed; next action is user review/commit/push and remote CI.
