# Implementation status

Updated 31 October 2026. Runtime source, manifests and lockfiles establish behavior.
This record distinguishes offline acceptance from deployed behavior. Detailed earlier
scope evidence is preserved in the [chronological archive](archive/alignment-status-through-2026-10-31.md).

## Current outcome

The local studio and shared review/publication workflow are implemented. Hosted
storage, distributed operations, authenticated transport, reader quotas, cost
controls, collection and infrastructure configuration passed offline phase reviews.
Gemini now uses GCP service identity through the Google Gen AI SDK. The full hosted
product has not been deployed or accepted live by this task.

| Scope | Evidence and state |
| --- | --- |
| Local architecture scopes S0–S4 | Historical acceptance and review evidence retained in the chronological archive; these scopes are distinct from hosted phase numbers |
| Hosted phases 0–2 | Plan, immutable persistence and fenced jobs reviewed; implementation and fixes recorded in the archive |
| Hosted phase 3 | Approved-work admission and metadata views in `79f3121`; final review fix `fef5b8a`; offline HTTP and synthetic browser acceptance |
| Hosted phase 4 | Budget, billing notifications, Terraform, settlement/GC and controls through `8703d04`; Standards fixes `364c4a6`; Spec rollback proof `8703d04`; both follow-up reviews clear |
| API/region decisions | API default `koetts-api`; new compute/storage `us-central1`; initial frontend `us-east4`, later migration to `us-central1`; see infrastructure and rollout guides |
| GCP Gemini migration | `d9eb6f1`, review fixes `821c02e`, evidence `40182c8`; ADC/project plus `us` inference endpoint; no API-key fallback; both reviews clear |
| Hosted phase 5 | Live deployment, CPU/model performance, IAM/session/storage/billing/playback and rollback acceptance remain unverified and separately gated |

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

Implementation and the ADC migration were approved. Cloud deployment, paid
CPU/model/provider tests and real publication were not authorized by those
approvals. Human cast/script/audio decisions remain explicit. No task-owned
phase 5 cloud mutation or paid provider call has been performed.

Before live execution, obtain a bounded deployment/test authorization and separate
incremental infrastructure/build and model-call allowances. Confirm the new bucket,
clean dataset/namespace, actual image digests, service URLs, secret versions and
rollback targets. Resolve model-versus-infrastructure billing attribution: the
current project-filtered USD 20 budget includes Gemini model charges, while the
provider ledger remains a separate application allowance.

Use the [hosted plan](hosted-service-plan.md) for acceptance requirements,
[infrastructure](hosted-infrastructure.md) for inputs,
[Mermaid diagrams](hosted-infrastructure-diagram.md) for topology, and
[rollout](hosted-rollout.md) for cutover and recovery. Existing deployment
observations are dated snapshots, not fresh assertions of current cloud state.
