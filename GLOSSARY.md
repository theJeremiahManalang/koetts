# Manga audiobook production

This glossary distinguishes reviewed production material, recoverable audio work,
and reader-facing publication.

## Language

**Chapter work**:
The shared effort to produce audio for one requested manga chapter and audio
configuration. Multiple readers can request the same chapter work.
_Avoid_: Reader request, studio project

**Reader request**:
One reader's request for a chapter work, including that reader's original notes.
_Avoid_: Chapter work, production operation

**Take**:
A recorded version of one audio segment. Multiple takes may exist; a selected
take is the version chosen for use in an export.
_Avoid_: Export, publication

**Local checkpoint**:
Saved production progress that includes completed takes and their referenced audio,
allowing local processing to resume from that progress.
_Avoid_: Cloud durability, publication

**Export**:
A compiled audio deliverable for a selected set of scenes, with its accompanying
script and timing information. An export may still await human audio review.
_Avoid_: Publication, take

**Publication**:
A reviewed export made available to readers through an explicit admin decision.
_Avoid_: Export, completed render

**Audition candidate**:
An unchanged copy of an export prepared for an admin to inspect before recording
an audio-review decision.
_Avoid_: Publication, selected take

**Audio review**:
An admin's explicit decision that an exact export is ready for publication. The
decision does not prove that the admin listened to it.
_Avoid_: Script approval, publication

**Operation**:
One requested production action with pinned inputs and an observable outcome. An
operation may require more than one worker attempt.
_Avoid_: Attempt, worker process

**Attempt**:
One finite worker execution for an operation.
_Avoid_: Operation

**Stage slot**:
A capacity allowance for simultaneous work in one production stage.
_Avoid_: Worker, operation

**Lease**:
A temporary claim that lets a worker hold a stage slot. Expiry signals that ownership
needs reconciliation; it does not prove that the worker stopped.
_Avoid_: Timeout, completion

**Fence**:
A nonreused generation attached to ownership, used to distinguish current work from
stale work.
_Avoid_: Revision

**Idempotency key**:
A token that makes repeated delivery of one intended request refer to the same
operation.
_Avoid_: Operation ID

**Uncertain outcome**:
A worker or provider may have started work, but the result cannot be confirmed. It
requires reconciliation before retry or release.
_Avoid_: Failed operation
