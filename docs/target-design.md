# Accepted project target

Confirmed with the user on 19 October 2026. This document records product and
architecture decisions. Implemented behavior is described in [architecture.md](architecture.md).
Scope boundaries and acceptance criteria live in [the implementation plan](architecture-alignment-plan.md).

## First shared release

A signed-in reader submits a manga/chapter reference and sees their own requests.
An admin supplies authorized manga images, performs extraction and cast/source/script
review, generates and auditions audio, reviews the exact export, and publishes it.
Readers browse the shared published catalog and play published chapter audio.

Readers can access published catalog/audio and their own requests. Trusted admins
can access studio operations, private source images, drafts, and generation.
Admin roles are provisioned through a trusted mechanism, never self-assigned.
Preserve the working local studio throughout migration.

Automated scraping, external catalog integration, translation, word synchronization,
shared manga-wide cast, and automatic reconciliation of extraction reruns are deferred.
Use explicit local source fixtures/adapters until a later source integration is scoped.

## Target responsibilities

- Next.js remains on Firebase App Hosting, with server routes as the web boundary.
- Firebase Auth supplies reader/admin identity; application authorization enforces access.
- Firestore holds shared metadata, requests, operation/revision coordination, and
  publication pointers. Cloud Storage holds immutable project/evidence/audio artifacts.
- Cloud Run hosts Python processing. Preserve `PipelineRouter` and existing engine
  adapters behind an explicit local/cloud execution boundary. Long work uses finite
  execution rather than request-bound web subprocesses.
- Conditional revision commits and fencing protect shared state. Persist and verify
  artifacts before promoting a manifest pointer. Acknowledged checkpoints must include
  referenced audio and evidence; observer notifications alone do not prove durability.
- Publication binds an admin review decision to the exact immutable export/settings.
  Failed replacement preserves the prior publication. Planning, applying proposals,
  script approval, rendering, export, audio review, and publication remain distinct.
- Reuse approved current takes and accepted segment checkpoints. Reconcile uncertain
  external execution before retries; exactly-once provider billing is not guaranteed.

These are target responsibilities, not claims that cloud resources or integration exist.

## Execution and human decisions

Agents complete one assigned scope and report acceptance evidence before taking a
new scope. Reversible implementation and offline verification are authorized within
that scope. Human approval remains explicit for cast/script decisions and publication.
Paid generation and cloud deployment need task authorization; existing authorization
remains valid without repeated requests. Documentation work alone authorizes neither.

## Unresolved decisions and blocking scopes

The imported cloud design/setup checklist are unavailable. Record resolutions here
before implementing dependent behavior; recover old inputs only if useful, rather
than treating their filenames as prerequisites.

| Decision or measurement | Must be resolved before |
| --- | --- |
| Distributed stage capacities, retry authority/ceiling, timeout and lease reconciliation policy | S2 production scheduling behavior |
| Request deduplication identity, chapter/configuration key, lifecycle/status rules | S4 request persistence |
| Edit ownership, stale-worker promotion, and fence lifecycle | S1 shared persistence contracts |
| Trusted admin provisioning and user/service identity transport | S3 authorization implementation |
| Dispatcher choice; Workflows/Eventarc/scheduler use; bucket layout | S5 infrastructure integration |
| Retention periods, reference tracking, deletion and recovery policy | S5 cleanup implementation |
| Project/regions, budget, service IAM, secrets, actual deployed state | S5 provisioning/deployment |
| MAGI resources/startup and Gemini/MP3 compatibility and listening quality | S5 live compatibility and sizing acceptance |

Old claims of one active MAGI and one active pipeline execution are proposals, not
confirmed global limits. Current local process limits are separate. Fake adapters
may expose configurable policies while dependent production decisions remain open;
report that limit explicitly. Resolve independent scope work without inventing policy.
