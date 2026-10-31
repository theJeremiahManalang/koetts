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
