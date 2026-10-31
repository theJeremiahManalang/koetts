# Phase 5 authorization and deployment record

Updated 1 November 2026 (Asia/Taipei). This record distinguishes authorized work,
deployed configuration, live observations and acceptance still requiring evidence.

## Accepted scope

The user approved backend deployment and cutover of the existing frontend (option B),
with USD 5 incremental infrastructure/build spend and USD 5 Gemini test spend.
Build retries count against the infrastructure allowance. The user runs paid Gemini
calls manually; the agent may capture and review logs but may not initiate them.
These campaign allowances are not guaranteed billing caps or separate billing budgets.
Actual charges remain delayed and unreconciled.

Use project `koetts-9bf7f`, named Firestore database `koetts-default` in `nam5`,
new API/jobs/artifacts in `us-central1`, and existing frontend in `us-east4`.
Frontend regional migration, retirement of `koetts-s3-api`, GPU use and migration
of local projects or existing buckets are excluded from this deployment.

The user accepted combined project monitoring: USD 20 budget, USD 10/15/20 alerts,
and USD 15 production pause including infrastructure and Gemini. The user monitors
the breakdown in GCP; separate service/SKU budgets are not a launch prerequisite.
The application provider allowance remains a separate admission control.

Both local and hosted admin flows require manual testing with separate evidence:
candidate, tester, timestamps, steps, expected/observed behavior and blocking defects.
One explicitly approved chapter sample (maximum 40 pages), one planning action and
one short synthesis action were selected. The exact sample and synthesis length
remain unconfirmed; retries count within call/spend limits. File presence alone
(e.g. `images/page1.jpg`) does not approve model processing.

Publication intent is approved. Human cast/script decisions, exact-export audio
review and the admin publication decision remain required. No audiobook has been
published by this deployment.

## Deployed configuration

| Resource | Verified state |
| --- | --- |
| API | Private `koetts-api-00003-fx8`, `us-central1`; URL `https://koetts-api-gu5jb64hpq-uc.a.run.app`; configured audiences match |
| Frontend | `koetts-build-2026-10-31-004`, 100% traffic in `us-east4`; `MANGA_FRONTEND_ONLY=0`, `MANGA_EXECUTION_MODE=cloud` |
| Prior API | `koetts-s3-api-00001-gl5` preserved unchanged |
| Jobs | `koetts-magi`, `koetts-pipeline`, `koetts-artifact-gc`; no task-owned inference execution |
| Schedules | `hosted-coordinator` and `hosted-artifact-gc` PAUSED |
| Artifact bucket | New `koetts-9bf7f-hosted-artifacts-us-central1`; private, uniform access, soft delete disabled |
| Namespace | Dataset `hosted_pilot_20261101`, object prefix `hosted/pilot_20261101/`; no local data imported |
| Image repository | `koetts-hosted` in `us-central1`, created through gcloud outside Terraform |
| Signing key | `hosted-audio-signing-key@1`, frontend runtime reference; bytes generated in memory and never recorded |
| Billing | Budget `35812220-da85-4ad5-876f-562c39dc7f6d`; real report interval recorded in Firestore |

The admin-access follow-up enabled cloud navigation because website-only mode
redirected even admins to Browse. This enables manual navigation and request-approval
testing while production remains paused. A read-only lookup confirmed the
user-identified account already has `admin: true` and is enabled; no claims changed.

The budget ledger is initialized and explicitly PAUSED. Provider allowance and call
caps are ZERO. Infrastructure hold caps are USD 5 per stage; they are blocked setup
reservations, not measured operating estimates. Do not resume with these setup caps.
Replace them with measured operation/call bounds before production activation.

## Verification and recovery evidence

Terraform's first apply failed at budget creation because local ADC lacked a quota
project. Explicit provider quota attribution fixed the failure; resumed provisioning
and canonical-URL updates succeeded. No destructive changes were applied. Operator
Firestore delete permission was removed before provisioning.

Backend build `1253ba16-0971-4ec5-8bff-f71f664766c4` succeeded. Two frontend attempts
failed before promotion: `44324eb0-9df6-49ef-8c41-85fa5e27fa43` lacked an app-local
lock, and `c7029165-39c8-4312-9f2c-cb5670cbb78f` produced nested standalone output.
A sanitized app-only stage projects the root lock, npm overrides and package-manager
pin without resolving new dependency versions. Exact Firebase adapter 14.0.21 passed
locally. Build `f355931c-78ec-44ad-9e0b-8bbea05bd5bd` completed the guarded cutover;
`29b0506f-bc92-4cb3-ad08-edab330f740a` subsequently enabled cloud admin navigation.

Live observations establish private API invocation denial, named-database browser
rules denying all access, private artifact bucket settings and paused schedules.
Browse/Login return 200. Unauthenticated Studio and request-dashboard responses
contain Next.js streamed redirects to Login, not server errors. Unauthenticated
API/admin mutations are denied. Operator impersonation of the frontend identity
was denied; no grants were expanded to bypass it. Authenticated end-to-end
frontend/admin verification still requires the user's manual session.

Initial billing notifications returned 429 against the uninitialized ledger.
Initialization with provider calls disabled, followed by explicit pause, recovered
real report ingestion. A subsequent push returned HTTP 200 and an October interval
was recorded. Its preliminary reported zero does not establish final charges.

Private evidence lives under ignored `results/phase5-20261101`,
`results/phase5-deployment-final-20261101` and
`results/phase5-billing-recovery-20261101`. These include source manifests, build
metadata/logs, plan/apply outputs, deployed configuration, HTTP checks and ledger
status. Keep raw logs private. Local Terraform state and ignored explicit inputs
must be preserved; no remote state backend is configured.

## Remaining acceptance gates

- Complete and record manual local and hosted admin tests. Capture matching log
  windows with the [manual validation guide](../resources/hosted-manual-validation.md).
- Establish representative CPU extraction quality, latency, memory and cost bounds.
  A failed CPU benchmark blocks launch; it does not authorize a GPU.
- Record user-operated Gemini planning/synthesis results and observed costs, then
  configure conservative operation/call caps and the intended provider allowance.
- Verify real identity/session revocation, authenticated byte-range playback,
  durable restart recovery, reservations/pause behavior, cleanup safety and rollback.
- Explicitly activate production and scheduling only after applicable acceptance
  gates and measured limits pass. Navigation access does not activate processing.
- Record actual charges and reconcile the campaign allowances before further spend.

Phase 5 is not complete. Use the [hosted plan](hosted-service-plan.md),
[infrastructure guide](../resources/hosted-infrastructure.md),
[cost controls](../resources/hosted-cost-controls.md) and
[rollout runbook](../resources/hosted-rollout.md) for implementation and recovery.
