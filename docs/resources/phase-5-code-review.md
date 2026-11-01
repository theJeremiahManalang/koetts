# Phase 5 checkpoint code review

This is a code-review record, not full live production acceptance. The feature
branch remains `feat/hosted-service`, based on main at
`0bdacc5cd0092cf33d53afb4d12f6b64b5ba16bb`.

## Standards

Independent review of `75b0f5b...109c539` found no hard documented-standard
violations and one judgment-call smell: the log-filter helper accepted an unused
project argument. Project scoping already belongs to the gcloud invocation.
Commit `cb970be` removed the argument and repaired fresh-checkout copying to include
resources and infrastructure source while excluding secrets and generated state.

Independent follow-up review of `109c539...4b3b7a7` found no remaining Standards
findings. The follow-up includes the HTTP budget-denial regression fix.

## Spec

Independent review of `75b0f5b...109c539` found no code findings. Deployment scope
matches the approved backend and existing east-region frontend cutover; old API,
durable data, manual paid-call ownership and production pause are preserved.

Independent follow-up review of `109c539...4b3b7a7` found no findings. The HTTP fix
preserves the existing sanitized `429 production_paused` contract instead of
wrapping a budget rejection as generic 400. It does not resume production, enable
schedules, modify user claims or initiate provider calls.

## Acceptance evidence

- The initial pinned full acceptance suite passed: repository checks, lint,
  333 Python tests (93 optional skips), 90 web tests, typecheck and production build.
- Fresh-checkout acceptance passed frozen installs, repository checks, 333 Python
  tests (93 skips), 90 web tests, a lightweight environment without torch, and
  external-directory CLI entrypoints. Its copied source predates the new regression.
- The injected HTTP regression first failed deterministically with `400 != 429`,
  then passed after the one-line fix. All 15 HTTP unit tests, the full Python suite
  (334 tests, 93 optional skips), and disposable studio/frontend-only production
  HTTP checks passed after the fix. No live provider was used.

Reviewers inspected immutable diffs; acceptance commands were run separately.
Private logs remain under ignored `results/phase5-20261101`. Live manual access
logs are in `results/admin-project-create-20261101`. They confirm login-related
identity access, upload and metadata requests, plus two failed creation requests.

## Remaining gates

The user explicitly chose to keep production paused rather than enable a CPU trial.
Do not start extraction, enable dispatch or make Gemini calls. Manual full-flow,
CPU/model quality/performance, session revocation, authenticated playback, recovery,
rollback and cost reconciliation still require evidence. Phase 5 is not complete.
See [status](../STATUS.md), [authorization](../plans/phase-5-authorization.md), and
[manual validation](hosted-manual-validation.md).

Review totals: Standards 0 unresolved (1 smell fixed); Spec 0 findings. Remaining
live acceptance gates are not represented as passed code checks.

The API fix was subsequently deployed as `koetts-api-00003-fx8`, using the immutable
image built by `ec6667fc-bf83-42d1-aa1b-3460dcb33e36` from commit `4b3b7a7`.
The saved Terraform plan changed only the API image. Ready status, matching digest,
paused ledger, zero provider allowance and both paused schedules were verified.
Post-deployment manual notification-message verification remains pending.

## Event-driven dispatch and status delivery

Phase one (`9def19c...4188ae4`) adds transactionally committed dispatch signals,
authenticated Eventarc delivery, stage-specific Cloud Run Job dispatch, TTL, the
required Firestore stage index, and a recovery-only schedule. Standards and Spec
reviews found no remaining findings. Review-time concerns about composite index
starvation and wake-up retries while paused were fixed before the phase was cleared.

Phase two (`4188ae4...7c3efd0`) adds private Firestore-backed SSE status delivery,
Studio reconnect from saved operation state, and authorization rechecks. Standards
and Spec reviews found no remaining findings. The mounted Studio test verifies
reconnect without resubmission or recurring `?job=` requests; backend tests verify
current/terminal updates and stream closure after admin revocation.

Focused phase-two checks passed: 15 web tests, two backend SSE tests, typecheck,
build, Ruff, repository checks, and Terraform formatting. The full web suite passed
99/100 on unsupported Node 24; the pre-existing multipart stream test fails with
`ReadableStream is already closed`. HTTP acceptance setup could not download
`google-cloud-core` because DNS was unavailable. Firestore integration tests are
skipped without an emulator. Offline `terraform validate` passed. A remote Terraform plan, apply and live stream
test were not run because managed-cloud status and network-policy readiness were unavailable;
production and both schedulers remain paused. Apply requires a reviewed concrete
plan and the user's authorization for the new Eventarc resources.
