# Hosted production cost controls

This document describes the implemented ledger boundary. It does not establish
live billing configuration, measured model costs, or a guaranteed spending cap.
The phase 4 operational rollout remains incomplete until its notification,
operator tooling, cleanup, infrastructure and review evidence is recorded.

## Admission and execution

Hosted application construction always attaches `CloudBudgetLedger` to its
Firestore operation store. The coordinator and finite-job entrypoint attach the
same ledger. Local SQLite scheduling does not use this cloud policy.

An absent ledger rejects new operations. Developer configuration must supply an
explicit remaining provider allowance of at most USD 80 and conservative caps for
both job stages. No code assumes that the existing provider account still has
USD 80 available or renews that allowance each month. All money uses integer USD
micro-units; floating-point amounts, booleans, negative values, zero infrastructure
caps, and enabled zero-cost provider calls are rejected.

Enqueue reads the budget reservation before chapter-admission writes and commits
both ledgers with the operation. A failed chapter approval or quota check commits
neither reservation. An idempotent operation retry returns the original intent,
including while paused, without making another reservation. Infrastructure caps
must cover all three application attempts and associated CPU/memory time; provider
operation caps must cover the configured maximum call count and per-call bound.
Those bounds require measured workload evidence before production is enabled.

Claims check the reservation and pause state in their own Firestore transaction.
The finite job checks again before materializing/extracting, and each provider
boundary debits its configured call bound before marking a provider outcome
pending. Duplicate worker registration and uncertain-outcome reconciliation retain
their existing safeguards. Budget admission does not authorize a retry of an
uncertain paid call.

## Pause and visibility

New reservations reject when reported infrastructure cost plus retained
reservations would reach USD 15, or when the separate provider allowance cannot
cover the reservation. Infrastructure reports accumulate interval highwater marks;
duplicate or lower out-of-order reports cannot reduce costs or clear a pause.
USD 10, 15 and 20 thresholds are exposed as alert configuration. Delivery of actual
Cloud Billing notifications requires separately provisioned budget alerts and a
Pub/Sub push subscription; no live delivery is established by offline tests.

`GET /production/status` requires the private service's `production-status`
permission and a verified Firebase administrator. `POST /production/pause`
requires `production-control` and the same administrator check. Its exact JSON
body is `{ "paused": true, "reason": "operator explanation" }`; the actor is
derived from verified claims. Resume uses `paused: false` and a new reason.
Resume does not bypass exhausted reservation limits. Budget configuration and
provider allowance changes remain developer operations, not browser-admin APIs.

`POST /internal/billing-report` accepts authenticated Pub/Sub push envelopes. The
push identity needs only the private service's `budget-report` permission; this
path does not impersonate a Firebase user. Configure the exact expected
`MANGA_BILLING_ACCOUNT_ID`, `MANGA_BILLING_BUDGET_ID`, and
`MANGA_BILLING_SUBSCRIPTION`. The subscription must belong to the API project.
Provision its OIDC token with the canonical private service audience and preserve
the standard Authorization header for the independent credential verifier.

The envelope must match the configured subscription, billing account, budget and
schema version `1.0`. Its decoded report must use USD and the USD 20 pilot budget.
Cost amounts are parsed as decimals and rounded upward to micro-units; credits
cannot lower accepted highwater costs. RFC3339 interval offsets are normalized to
UTC. Pub/Sub message identity provides idempotency. Invalid identities, malformed
payloads, duplicate JSON fields and non-finite amounts are rejected before ledger
ingestion. These fields follow the official [Cloud Billing notification format](https://docs.cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications);
payload checks supplement the verified OIDC identity and never replace it.

Production pause does not gate identity, reader requests, published catalog, or
private published-audio retrieval. HTTP budget denials return a sanitized 429
with `production_paused`; job denials retain completed durable work and do not
cross the provider-pending boundary.

## Conservative accounting and recovery

Reservations are not automatically refunded at completion, after a crash, or on
calendar rollover. Provider debits are maximum-cost accounting entries rather
than a claim about the provider's final bill. Explicit audited reconciliation
cannot lower reserved totals below the durable reservations or erase recorded
provider debits. Settlement and operational reconciliation procedures still need
phase 4 implementation and acceptance before sustained monthly operation.

Missing or corrupt controls fail closed. Existing reservation, report or audit
records cannot be adopted by reinitializing a missing control document. Status
checks validate the namespace binding transactionally and do not create records
or initialize inference/provider clients. Never delete a ledger to reset a budget.

Billing reports are delayed. Login, playback, storage, builds, existing executions
and other services can continue accruing charges while production is paused.
The USD 10 target and desired USD 20 ceiling remain operating goals, not guarantees.
