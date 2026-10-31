# Implementation status

Updated 1 November 2026. Runtime source, manifests and lockfiles establish behavior.
This record distinguishes offline acceptance from deployed behavior. Detailed earlier
scope evidence is preserved in the [chronological archive](archive/alignment-status-through-2026-10-31.md).

## Current outcome

The local studio and shared review/publication workflow are implemented. Hosted
storage, distributed operations, authenticated transport, reader quotas, cost
controls, collection and infrastructure configuration passed offline phase reviews.
Gemini now uses GCP service identity through the Google Gen AI SDK. The full hosted
production workflow is not yet accepted live. The backend and guarded frontend
are deployed; manual acceptance remains pending.

| Scope | Evidence and state |
| --- | --- |
| Local architecture scopes S0–S4 | Historical acceptance and review evidence retained in the chronological archive; these scopes are distinct from hosted phase numbers |
| Hosted phases 0–2 | Plan, immutable persistence and fenced jobs reviewed; implementation and fixes recorded in the archive |
| Hosted phase 3 | Approved-work admission and metadata views in `79f3121`; final review fix `fef5b8a`; offline HTTP and synthetic browser acceptance |
| Hosted phase 4 | Budget, billing notifications, Terraform, settlement/GC and controls through `8703d04`; Standards fixes `364c4a6`; Spec rollback proof `8703d04`; both follow-up reviews clear |
| API/region decisions | API default `koetts-api`; new compute/storage `us-central1`; initial frontend `us-east4`, later migration to `us-central1`; see infrastructure and rollout guides |
| GCP Gemini migration | `d9eb6f1`, review fixes `821c02e`, evidence `40182c8`; ADC/project plus `us` inference endpoint; no API-key fallback; both reviews clear |
| Hosted phase 5 | Backend provisioned; frontend `koetts-build-2026-10-31-004` serves 100% with new API URL and authenticated cloud admin UI. Manual production/identity/recovery/billing/playback acceptance remains pending |

## Latest verification

These are recorded results from the GCP Gemini implementation, not checks rerun
by this documentation cleanup:

- Repository, Ruff, Python suite, 90 web tests and TypeScript checks passed.
  Initial migration run recorded 330 Python tests with 93 optional skips; later
  SDK-wire and blank-configuration tests also passed in final acceptance.
- The disposable loopback Firestore suite passed 104 tests, including rollback,
  quota/budget races and reference-aware collection. No live database was used.
- Production webpack HTTP acceptance passed studio and frontend-only paths.
  Default Turbopack failed under environment process/port restrictions; the full
  default `npm run check` is not claimed green.
- Terraform formatting and provider schema validation passed without plan/apply.
- The three Mermaid infrastructure diagrams passed syntax parsing.
- SDK wire fixtures use synthetic credentials and mock HTTP transport. They prove
  request mapping and WAV handling, not real model access, voice quality or cost.

Temporary logs referenced by the active handoff are supplementary evidence and
may not survive environment replacement. Source tests and committed review/fix
records remain available; refresh live preflight and checks before rollout.

## Authorization and remaining work

Deployment is approved for the new backend and existing frontend cutover, within
USD 5 infrastructure/build spend. The user runs paid Gemini tests manually within
USD 5; the agent captures available logs and initiates no model calls. Publication
intent is approved; human cast/script decisions, exact-export audio review and the
admin publication decision remain explicit. Regional frontend migration and old
API retirement are excluded.

Live provisioning and cutover completed on 2026-11-01 (Asia/Taipei):

- New private API `koetts-api-00002-w5s` is ready in `us-central1`.
- Frontend `koetts-build-2026-10-31-004` serves 100% in `us-east4`, with the new API
  URL and signing-secret version 1. Admin access uses `MANGA_FRONTEND_ONLY=0` and
  `MANGA_EXECUTION_MODE=cloud`; production remains paused.
- Both Scheduler jobs are PAUSED. Existing `koetts-s3-api-00001-gl5` is preserved.
- Artifact storage privacy, named Firestore browser denial rules, absence of public
  API invokers, and unauthenticated API denial were verified. Public browse/login
  returned 200; Studio/dashboard use streamed Login redirects for unauthenticated
  visitors; unauthenticated admin/workflow API requests returned 401.
- Pinned Node 22 HTTP acceptance passed both modes after the tracing-root change;
  typecheck, repository checks, Ruff and 10 infrastructure tests passed. Exact
  Firebase adapter 14.0.21 passed locally and the final hosted build succeeded.

The user accepted combined project monitoring: USD 20 budget, USD 10/15/20 alerts,
and USD 15 production pause inclusive of Gemini. The user reviews the cost breakdown
in GCP. Budget/topic/subscription configuration is provisioned. Real billing notification
delivery was verified after initializing the ledger; the October interval was
recorded with a preliminary reported amount of zero, which does not establish
final charges. The ledger is explicitly paused, with zero provider allowance and
zero provider call caps. Infrastructure hold caps are USD 5 per stage and are not
measured production estimates. Configure measured stage caps before activation.

Manual local and hosted admin-flow acceptance, CPU/model performance, session
revocation, authenticated playback, recovery and rollback remain pending. Operator
impersonation of the frontend identity was denied; no access grants were expanded.
Full hosted production remains gated. Do not claim that the entire phase is complete.
See the [decision record](plans/phase-5-authorization.md),
[manual validation guide](resources/hosted-manual-validation.md),
[hosted plan](plans/hosted-service-plan.md),
[infrastructure](resources/hosted-infrastructure.md) and
[rollout](resources/hosted-rollout.md).


## Phase 5 checkpoint review

Deployment checkpoint `109c539` was reviewed against phase start `75b0f5b` with
independent Standards and Spec axes. Standards reported no hard violations and one
unused-parameter smell in the log collector; the parameter was removed. Spec
reported no code findings; live acceptance gates remain open.

The full pinned `npm run check` passed before the project-creation regression fix:
333 Python tests (93 optional skips), 90 web tests, lint, typecheck and production
build. Fresh-checkout acceptance also passed frozen installs, repository checks,
those test suites, absence of torch, and external-directory CLI entrypoints. The
fresh-copy helper now includes developer resources and infrastructure source while
excluding credentials, local Terraform state/inputs and generated caches.


## Manual access evidence and project-creation denial

The user confirmed hosted login and single-image upload. Captured logs show
successful `/identity`, `/projects`, `/shared`, `/production/status` and upload
requests. These establish basic authenticated transport and storage access, not
session revocation, processing quality or full production acceptance.

Two creation attempts returned 400. An injected regression proved that the HTTP
enqueue wrapper converted `CloudBudgetExceeded` into a generic invalid-request
response. The fix preserves the existing sanitized 429 `production_paused` handler.
The regression failed with 400 before the fix and passed afterward. All 15 HTTP
unit tests, the full Python suite (334 tests, 93 optional skips), and disposable
studio/frontend-only HTTP acceptance passed. Production remains paused by the
user's explicit choice; no extraction trial or Gemini call is authorized to run.
