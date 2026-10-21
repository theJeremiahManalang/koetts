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

### Resolved for S1 — edit ownership and fencing

Project writes use exclusive ownership. Competing edits receive a typed conflict
until the current worker reaches a known terminal result and releases ownership.
Each ownership handoff increments a monotonic fence that is never reused. A revision
commit requires the active owner, fence, and expected parent revision. An interrupted
worker keeps its ownership fenced until recovery confirms that execution stopped;
S1 introduced no timeout or automatic takeover policy. S2 now resolves local lease
expiry and uncertain-outcome reconciliation; distributed reconciliation remains in
the S5 cloud scope.

### Resolved for S3 — identity and approval attribution

Firebase's boolean `admin: true` custom claim grants studio access. Only trusted
administrative tooling provisions it; browser roles and forwarded identity headers
never grant authority. Existing accounts are retained without automatic promotion.

The private Python API independently verifies a Google service ID token against
its configured audience and an explicit subject/action allowlist, then verifies
exactly one Firebase user ID token or session cookie with revocation checks.
Next sends the service token in both Authorization and X-Serverless-Authorization:
Cloud Run consumes the latter while the application verifies the full former.
User credentials use separate headers and never appear in URLs or saved operations.

Verified actor identity is pinned server-side in queued requests. Cast and scene
approval records persist atomically with approved state and retain reviewed revision,
subject fingerprint, timestamp and operation identity. CLI actors are explicitly local.
Historical projects default to empty history without rewriting their fingerprints.

The authorized S3 cloud rollout is authentication verification only. Frontend-only
hosting remains enabled; private API project, asset and operation access stays
unavailable until S5 supplies durable storage and hosted execution. This restriction
does not prevent local testing of short-operation HTTP contracts.

### Resolved for S2 — local operation scheduling and recovery

The local studio stores durable operations in a SQLite database under
`results/web/operations.sqlite3`. Its transactional slots coordinate processes on
one host only; Firestore and hosted execution remain S5 work. Local defaults allow
one MAGI operation and one pipeline operation at a time, with one active operation
per project across both stages.

Each intended request supplies an idempotency key. Repeating the key with the same
normalized inputs returns the same operation; reusing it with changed inputs is a
conflict. The operation pins the expected project hash, source checksums and
configuration fingerprint. Upload bytes are hashed at intake; existing project
visual evidence used by planning (page images, cast references, and appearance
crops) is hashed when queued and checked again before execution. Workers resolve
request data from storage and report progress, checkpoint/output pointers, attempt,
fence, lease and local process identity.

The operation store owns a ceiling of three total attempts; the durable worker makes
one provider request per attempt, leaving retries to this single authority. A
30-minute attempt timeout uses 15-second heartbeats and 60-second leases. Lease
expiry triggers process identity reconciliation using PID and process creation time;
expiry alone never releases a slot. A provider result that has been checkpointed is
resolved work and may resume automatically. A possibly submitted call without a
durable result becomes `reconciliation_required`, retains its slot, and requires an
explicit local `fail` or `retry` decision. Retrying may repeat provider billing.
SQLite/WAL is not the distributed production scheduler and must stay on local storage.

Existing JSON job files remain untouched and readable for polling. New enqueues use
SQLite; old queued/running jobs are not imported or automatically restarted.

| Decision or measurement | Must be resolved before |
| --- | --- |
| Production global stage capacities, dispatcher, timeout/retry policy, and hosted execution reconciliation | S5 cloud integration |
| Request deduplication identity, chapter/configuration key, lifecycle/status rules | S4 request persistence |
| Dispatcher choice; Workflows/Eventarc/scheduler use; bucket layout | S5 infrastructure integration |
| Retention periods, reference tracking, deletion and recovery policy | S5 cleanup implementation |
| Project/regions, budget, service IAM, secrets, actual deployed state | S5 provisioning/deployment |
| MAGI resources/startup and Gemini/MP3 compatibility and listening quality | S5 live compatibility and sizing acceptance |

The resolved 1/1 capacity defaults apply to the same-host local SQLite scheduler;
they do not establish production global limits. Cloud adapters and hosted stage
capacity remain open for S5.
