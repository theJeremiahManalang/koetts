# Hosted service implementation

## Objective and authorization

Implement the full approved plan in docs/hosted-service-plan.md on
feat/hosted-service, based on main 0bdacc5cd0092cf33d53afb4d12f6b64b5ba16bb.
The user authorized implementation, substantial commits using caveman-commit,
independent Standards/Spec review per phase, fixes before advancing, and questions
for critical decisions. This remains the active, incomplete goal.

Deployment, paid inference/provider tests, human cast/script/audio approvals and
publication require separate authorization. None occurred. Preserve local results,
samples, model caches, credentials and unrelated changes. No push was requested.

## Decisions

Use existing project koetts-9bf7f, backend koetts, region us-east4, named Firestore
koetts-default, and a clean hosted dataset. Do not migrate local data implicitly.
Public Google signup; trusted admins approve production. Hosted creation requires
approved shared work, five distinct work IDs/UTC month and 40 pages/work.
Reader quotas are five pending and ten new/day UTC; duplicates are free.
Infrastructure target USD10/month, desired ceiling USD20 (not guaranteed), pause
at reported USD15 or earlier conservative reservations. Login/playback continue.
Provider allowance is separate, at most USD80, never assumed available or renewed.
CPU jobs first, global slot/stage, three application attempts, 30 minutes,
platform retries zero. Uncertain paid outcomes hold capacity. CPU benchmark failure
blocks launch; no automatic GPU escalation. All audio/range access authenticates.

## Current state

Phases 0–3 passed scoped reviews and fixes. Phase 4 offline implementation and
acceptance passed final review through 8703d04. Runtime source and manifests are
authoritative; docs/alignment-status.md records scope evidence.

Phase 4 commits: 34dc01c durable cost controls, 9cb6b7f billing notifications,
b0578df private infrastructure, 12d8b01 settlement/GC and cold namespace fix,
8cbd95f admin controls, 364c4a6 shared policy helpers, 8703d04 rollback acceptance
and publication GC roots. Full review baseline fef5b8a. Standards found three
maintainability issues, all fixed in 364c4a6. Spec required offline rollback proof,
fixed in 8703d04. Both independent final follow-ups report no remaining findings.
The review agents first failed from usage limits; retries completed successfully.

Important contracts: cloud_budget composes read-before-write reservation closures,
failclosed configured caps, permanent settlement markers and explicit closeout.
GC maintenance is non-expiring; promotion epochs prevent upload races. Roots cover
accepted revision history, operation references, shared catalog and publication
review checksums. Recovery requires confirmed terminal prior execution and replays
uncertain deletion chains. Prior software cannot recover this protocol safely.

The rollback test archives actual fef5b8a source and checks imported module paths.
Old HTTP reads candidate snapshot/catalog/exact published bytes without changing
complete hosted/shared Firestore trees or GCS generations. Enqueue/coordination
are denied; shared permission is not universally read-only. Candidate then recovers
interrupted GC. Provider keys are cleared. Real rollback must stop collectors and
workers and resolve held barriers with compatible software before serving old API.

## Verification

Use Node22.22.3 from /home/ssuish/.nvm/versions/node/v22.22.3/bin, npm10.9.8,
uv0.11.16/Python3.11.15. Default Node24 broke an existing Undici fixture; pinned
Node22 passed. Cache/network/loopback restrictions may require escalation.

- /tmp/hosted-phase4-reviewed-firestore.log: 104 tests passed, loopback/demo only.
- /tmp/hosted-phase4-rollback-keyless.log: focused keyless rollback passed.
- /tmp/hosted-phase4-contention-stress.log: ten cold-start stress cases passed.
- Repository/Ruff/Python/90 web tests/typecheck passed after fixes.
- /tmp/hosted-phase4-webpack-build.log: production webpack build passed.
- /tmp/hosted-phase4-operations-accepted-http.log: production-webpack HTTP passed
  studio and frontend-only paths. Command: npm run test:http -- --webpack.
- Default npm run check reached build then Turbopack failed creating process/port
  under environment restrictions. Do not claim complete default-check success or
  verified App Hosting adapter/default bundler behavior.
- Terraform1.17.1 fmt/validate passed with locked Google/google-beta7.46.2.
  Binary /tmp/hosted-infra-terraform-1.17.1/terraform. No cloud plan/apply.
- Admin UI synthetic desktop/mobile QA passed. Retained evidence:
  /tmp/manga-phase4-quota-qa.Tf6oEa/artifacts/browser-qa.json and screenshots.
  Fixture server stopped. This establishes no real Google session behavior.

Cold binding diagnosis isolated Firestore read-lock upgrades: repeated cold races
failed while prebinding passed. Atomic conditional create plus bounded idempotent
retry fixed them. Temporary probe /tmp/hosted-contention-probe is outside repository
and inactive unless explicitly injected. No production provider retries added.

## Remaining work / next action

Commit phase 4 evidence and documentation routing after repository checks. Obtain
separate phase 5 authorization required by docs/hosted-service-plan.md:122 before
cloud deployment or paid tests. Read-only preflight can prepare concrete targets.
Do not mark goal complete: no images deployed, real rollback targets captured,
secret versions verified, or live IAM/storage/restart/session/playback/rollback/
billing/CPU-quality/provider-cost acceptance proven. No automatic publication.
Record actual revisions, commands, costs and acceptance evidence during authorized
phase 5. Keep provider balance explicit and production/schedulers paused until
acceptance. Ask for consequential new decisions; implementation approval persists.


## Read-only preflight continuation

Previous goal turn made progress: phase 4 reviews closed and evidence committed
as 1cc6e42. Separate phase 5 approval and incremental spending cap were requested;
no answer has arrived. This continuation did not interpret automation as approval.
Read-only gcloud queries now establish existing web revision
koetts-build-2026-10-21-002 (100%), existing API revision koetts-s3-api-00001-gl5
and its immutable image (recorded in docs/hosted-rollout.md), and no regional jobs.
Terraform's API default collides with that existing service. Ask whether to use a
new candidate API (recommended) or adopt existing resources under reviewed import;
do not apply unchanged. Local Docker is an unavailable WSL Desktop shim. Remote
builds also require deployment/test cost authorization. No cloud state changed.


## Authorization blocker audit

The phase 5 authorization condition persists across three consecutive goal turns.
The first completed offline reviews and evidence; the second completed useful
read-only preflight; the third revalidated a clean tree, the explicit plan gate,
and the unanswered authorization request. No live process is pending. Further
implementation acceptance requires deployment and bounded paid tests. The goal
remains incomplete and is blocked pending user approval, incremental spending cap,
and the existing-API collision decision. Recommended choice: separate candidate
API, preserving the existing service. Automation continuation is not approval.
