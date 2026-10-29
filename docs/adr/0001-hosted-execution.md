# ADR 0001: Run hosted production as durable cloud jobs

- Status: Accepted for implementation
- Date: 2026-10-29

## Context

The product needs shared reader requests, private source artifacts, recoverable
production, and published playback across multiple application instances. The
current web process starts local Python subprocesses; operation slots and project
files live on one host. App Hosting instances cannot provide durable shared project
state or distributed coordination. Production also makes paid provider calls, so a
lost response cannot safely trigger an automatic retry.

The existing engine already defines artifact and revision storage seams, and the
worker has a separately authenticated HTTP boundary. The project already uses
Firebase Auth, App Hosting, and a named Firestore database.

## Decision

Keep Next.js on Firebase App Hosting. Use Firestore for shared operation/revision
coordination and Cloud Storage for immutable project, evidence, and audio artifacts.
Use private Cloud Run Jobs for finite processing, dispatched and reconciled by a
private scheduled coordinator. Keep local adapters for local use. Require durable
checkpoints and ownership fencing; resolve uncertain provider execution before
retrying. Authenticate every published audio range request through the application
before streaming private storage objects.

Start with scale-to-zero CPU jobs and a measured pilot budget. A failed CPU benchmark
blocks full hosted launch and triggers a separate compute/budget decision; it never
silently enables GPU resources. The detailed pilot limits and acceptance gates live
in [`hosted-service-plan.md`](../hosted-service-plan.md).

## Consequences

- Cross-service writes need recoverable state transitions because Firestore and
  Cloud Storage do not share an atomic transaction.
- Dispatch can take up to one minute. Scheduler delivery and job creation must be
  idempotent.
- Durable coordination and storage add adapters, IAM policy, recovery logic, and
  measured operating cost.
- Per-request audio authorization adds application proxy work and latency, while
  preserving session and revocation checks for new range requests.
- Local operation remains available through local adapters; cloud state is not
  silently mixed with local artifacts.

## Alternatives considered

- Keep production on one local host: rejected because it cannot serve a shared,
  recoverable hosted workflow.
- Run long production inside App Hosting requests: rejected because request-bound
  web compute does not provide the required durable execution contract.
- Use short-lived signed audio URLs: rejected for the pilot because copied URLs
  remain usable until expiry after logout or role revocation.
- Enable GPU jobs without a CPU benchmark: rejected because cost and model
  compatibility have not been measured against the pilot envelope.
