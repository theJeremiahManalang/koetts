# Hosted artifact collection

The collector removes only unreferenced temporary objects older than seven days
from the explicitly configured clean bucket namespace. It does not inspect local
results, model caches, credentials, samples, or other bucket namespaces. Accepted
revision history and referenced shared audio are retained.

## Roots and age checks

`manga_worker.cloud_gc` scans every accepted project revision and its verified
manifest, operation payload/checkpoint/result references, the durable shared
artifact catalog, and staging uploads. Upload records referenced by any operation
remain roots. Other uploads remain roots until seven days after their last
successful upload. Records without a trusted timestamp are preserved. Candidate,
review and publication checksums must resolve through the shared artifact catalog.

Missing ownership records, missing current revisions, mismatched dataset bindings,
incomplete shared references, malformed references, or unverifiable manifests abort
collection before any object deletion. Collection lists missing project parents
as well as existing records; a normal document query would omit orphan revisions.
All root and object-list checks finish before retiring old staging metadata or
deleting an object. Objects with unknown names or timestamps are preserved.

## Promotion barrier

Reference scans alone cannot protect an old orphan that becomes referenced between
the scan and deletion. The collector therefore acquires a Firestore maintenance
barrier only when no project writer, running/uncertain operation, or stage/project
slot remains. Writer acquisition, claims, new enqueues and artifact-catalog writes
read this barrier transactionally. Collection changes its epoch before scanning.

Uploads capture the epoch before GCS I/O and check it again when committing their
metadata. Enqueue captures it before reading upload references and checks it in
the operation transaction. Shared artifact promotion follows the same rule.
An upload started before collection cannot publish a stale reference after the
barrier is released. Its caller must retry from the upload boundary.

Identity checks, reader requests, snapshots, published catalog and playback do not
require this mutation barrier to be open. GC never deletes referenced published
audio. Production status exposes whether collection is active and the current
epoch; it does not initialize inference or provider clients.

## Exact-generation deletion and recovery

Before each deletion, a durable run record stores the exact object generation and
checksum. GCS receives both the exact generation and an `if_generation_match`
precondition. Successful deletion or an exact-generation 404 is recorded before
the barrier can be released. A different generation is never deleted by replay.

The barrier has no time-based expiry. An interrupted job, failed reference scan,
or uncertain delete leaves it held. A timed-out delete RPC can still complete on
the server; clearing a lease would permit a new reference to race that request.
Recovery must first confirm that the recorded collector execution has stopped
through Cloud Run's authoritative terminal status. An active or unknown execution
cannot be recovered.

Run recovery through a new execution of the configured GC job with the explicit
`MANGA_GC_RECOVER_OWNER` run ID. The job validates its own configured project/job
identity. Its recovery reads only the configured GC job's execution state, takes
a new fence, and replays every exact-generation deletion in the full recovery
chain before opening the barrier. If recovery itself fails, the next recovery
retains the chain. Do not edit or delete maintenance, run, or deletion records to
force recovery. Correct corrupt reference metadata before retrying recovery.

The checked-in daily Scheduler trigger starts paused. Unpause it only during a
separately authorized rollout after IAM, timeout, reference preservation and
recovery acceptance pass. GC uses the light CPU image without provider or signing
secrets. Maintenance, storage, soft-delete retention and reads can still incur
costs while production is paused.

## Rollback boundary

Before rolling back software, pause both production dispatch and GC scheduling,
confirm existing collector executions have stopped, and complete any held-barrier
recovery. A rollback target that does not understand the promotion epoch must not
write while a collector is active. Preserve the bucket, all revisions, reference
catalogs, operations, and maintenance evidence. Actual live rollback and IAM
behavior remain separately gated acceptance, not claims made by this runbook.
