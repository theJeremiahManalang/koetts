> Historical import, superseded by the active documentation index in [../README.md](../README.md). Statements of agreement in this snapshot are not current decisions.

# Architecture alignment handoff

Updated 19 October 2026. This checkout contains the target Next.js/Python app.
The [supplied baseline](current-app-baseline.md) records historical inspection;
verify current source and rerun checks before relying on it.

## Purpose and document authority

Incrementally migrate the existing local production studio and disconnected reader demo into the intended shared reader/admin application. Preserve working UI, MAGI extraction and engine behavior.

- [Implementation plan](../plans/architecture-alignment-plan.md): scope IDs, dependencies, boundaries and acceptance checks.
- [Scope prompts](../plans/architecture-alignment-prompt.md): start exactly one bounded scope.
- Cloud design (`cloud-deployment-design.md`) and setup checklist
  (`gcp-firebase-setup-checklist.md`) were referenced by the imported plan but are
  absent here. Their concurrency, retry, retention, and infrastructure decisions
  are unavailable inputs, not defaults to invent. Continue independent scope work;
  resolve those inputs before implementing behavior that depends on them.
- Current local workflow: [audio guide](../../resources/AUDIO_WORKFLOW.md).
- Current frontend hosting boundary: [App Hosting guide](../../resources/APP_HOSTING.md).

The repository contains `web/`, `web_workflow.py`, and the extraction/CLI adapters.
Inspect those existing implementations; preserve them through the migration.

## Current implementation and required alignment

| Area | Supplied target-app baseline | Required change |
| --- | --- | --- |
| Studio | Active Next.js UI in `web/components/`, studio at `/` | Preserve views and drafts; add authenticated admin access and remote-backed operations |
| Reader | Sample catalog, placeholder reader, inactive Listen action | Connect catalog/chapter status and published playback to persistent records |
| Requests | Browser-local request storage; missing `/requests` route | Shared deduplicated requests, status and admin fulfillment |
| Processing | `web/lib/workflow.ts` launches `web_workflow.py`; browser polls persisted local jobs | Durable queue, finite cloud workers, execution identity and recovery |
| Extraction | Existing `manga_tts/extraction.py` MAGI/OCR pipeline | Package and benchmark the real implementation; preserve images, crops and diagnostics |
| Domain | Typed router commands, exact approvals, takes and exports | Reuse these rules behind application services |
| Revisions | Whole-project hashes on web/CLI commands; process-local router counter | Preserve conflict checks and add durable revision identity, transactional commits and fencing |
| Concurrency | PID locks and Node-process limits | Distributed claims, editing leases, global stage limits and reconciliation |
| Storage | `results/web/` project/assets/jobs/uploads/bundles | Immutable Storage artifacts and Firestore coordination/pointers |
| Access | Loopback/origin checks; no user identity | Firebase reader/admin roles and separate service authorization |
| Publication | Audition/export exist; no recorded audio approval or catalog linkage | Exact-export review decision and atomic publication pointer |
| Hosting | Frontend-only mode disables processing routes | Connect App Hosting to IAM-protected API and finite jobs |

## Target responsibilities

Keep the existing Next.js app on Firebase App Hosting, including server routes. Server routes validate users and call a short-operation Python API on Cloud Run using service identity. Long planning/render/extraction operations go to finite jobs rather than request-bound subprocesses.

Firestore owns requests, operations, leases, revision metadata and publication pointers. Immutable Storage snapshots own pipeline state and referenced artifacts. Use separate private ingest, project and audio buckets. Workflows dispatch and monitor machine stages; Eventarc notifies ingest; scheduled reconciliation recovers stranded work and handles cleanup. Human review waits in durable records.

The agreed initial limits are one active MAGI execution and one active pipeline execution shared by planning/render/export. Refer to the cloud design for retry and retention policy rather than duplicating their implementation in UI or independent services.

## Preserve these contracts

- Keep `PipelineRouter` and strict commands as the domain seam. Preserve current target-app batch edits, speaker synchronization, source ordering, extraction evidence, CLI and portable project behavior.
- Keep Generate, Apply, Approve, Render, Export, audio review and Publish distinct. Script approval fingerprints establish state validity; new audit records establish who approved what and when.
- Preserve exact approved text, approval invalidation, source lineage, whole-selection preflight, checksummed take reuse, explicit regeneration and per-segment recovery.
- Preserve whole-project hash conflict checks. A durable cloud revision is separate from the process-local integer revision and project schema version.
- Keep local development usable during migration. Introduce an explicit local/cloud execution boundary rather than silently removing the existing local mode.
- Keep the active `web/components/` implementation. Confirm import reachability before removing obsolete `web/app/` duplicates or duplicate tests.

## Critical persistence and recovery seams

Inspect the target router before changing persistence. Local JSON replacement, PID locks and a saved job file do not provide cross-container durability. Observer subscriptions are not remote checkpoint acknowledgments.

Write and verify immutable objects first, then conditionally commit their manifest pointer under the expected revision and fence. A checkpoint references all required assets, not just JSON. Propagate remote persistence failure before reporting durable success. Preserve local persistence defaults through an explicit seam.

Export overwrites fixed local filenames and is not transactional: upload each completed export to a unique immutable version before review/publication. Review must bind to the exact export and settings; a changed export needs a new decision. Publication replacement must preserve the old pointer on failure.

Reconcile actual external execution before reclaiming expired leases. Align provider/SDK, job and workflow retries under one authority; the current five-attempt engine default must not multiply cloud retries. Represent uncertain provider outcomes without promising exactly-once billing.

## Verification and remaining inputs

The supplied baseline reports eight frontend tests passing and typecheck passing; Python reports 45 tests with 42 passing, two skipped and one missing `imageio_ffmpeg` dependency error. Production build was unverified after environment/TypeScript configuration failures. These are historical results to reproduce, not checks performed during this handoff.

MAGI already exists in the app. Its cloud compute sizing, startup behavior and live output quality still need measurement. Gemini model/SDK compatibility, live speech quality, actual deployed Firebase state, source API/version metadata, trusted admin provisioning, region and budget remain unverified.

Framework selection is not a greenfield task: retain Next.js. Select a Python HTTP framework only after inspecting existing dependencies and adapters. Translation, word/bubble alignment, shared manga-wide cast and extraction-rerun reconciliation are separate product scopes, not prerequisites for this migration.
