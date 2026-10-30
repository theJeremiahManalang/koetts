"""Reference-aware collection under a fenced artifact-promotion barrier.

The barrier never expires. An interrupted collector requires confirmed execution
termination and replay of exact-generation deletions before production resumes.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from manga_tts.operations import OperationConflict
from manga_tts.persistence import ArtifactRef

from .cloud import CloudSettings, cloud_stores
from .cloud_operations import FirestoreOperationStore
from .cloud_revisions import (
    SCHEMA_VERSION, FirestoreArtifactReferences, FirestoreRevisionStore,
    _FirestoreHostedStore, _revision_from_document,
)


@dataclass(frozen=True)
class CollectionFence:
    owner: str
    epoch: int
    execution_name: str


class ArtifactCollection(_FirestoreHostedStore):
    """Serialize collection against all project owners and artifact promotions."""

    def _held(self, transaction, fence):
        state = self._maintenance_state(transaction)
        if (state["owner"], state["epoch"], state["execution_name"]) != (
                fence.owner, fence.epoch, fence.execution_name):
            raise OperationConflict("stale_collection", "Artifact collection fence is no longer current.")
        return state

    def _transaction(self, operation):
        from google.cloud import firestore

        @firestore.transactional
        def execute(transaction):
            if not self._binding(transaction):
                raise ValueError("Artifact collection requires a bound dataset")
            return operation(transaction)
        return execute(self.client.transaction())

    def _run_ref(self, owner):
        if not isinstance(owner, str) or not re.fullmatch(r"[a-f0-9]{32}", owner):
            raise ValueError("Invalid collection identity")
        return self.root.collection("gc_runs").document(owner)

    @staticmethod
    def _execution(value):
        if not isinstance(value, str) or not re.fullmatch(
                r"projects/[A-Za-z0-9_-]+/locations/[a-z0-9-]+/jobs/[a-z0-9-]+/executions/[a-z0-9-]+", value):
            raise ValueError("Explicit collector execution identity required")
        return value

    def begin(self, execution_name: str) -> CollectionFence | None:
        execution_name = self._execution(execution_name)
        self.ensure_binding()
        owner = uuid.uuid4().hex

        def acquire(transaction):
            state = self._maintenance_state(transaction)
            if state["owner"] is not None:
                return None
            # Claim transactions and writer acquisitions read the maintenance
            # document before writing. Updating it serializes their admission.
            for collection in ("operation_stage_slots", "operation_project_slots"):
                if list(self.root.collection(collection).limit(1).stream(transaction=transaction)):
                    return None
            for snapshot in self.root.collection("operations").stream(transaction=transaction):
                operation = FirestoreOperationStore._operation(snapshot)
                if operation.status in {"running", "reconciliation_required"}:
                    return None
            for snapshot in self.root.collection("projects").stream(transaction=transaction):
                project = FirestoreRevisionStore._project_state(snapshot, snapshot.id)
                if project["owner_id"] is not None:
                    return None
            fence = CollectionFence(owner, state["epoch"] + 1, execution_name)
            transaction.set(self._artifact_maintenance, {
                "schema_version": SCHEMA_VERSION, "epoch": fence.epoch,
                "owner": owner, "execution_name": execution_name,
            })
            transaction.create(self._run_ref(owner), {
                "execution_name": execution_name, "epoch": fence.epoch, "status": "collecting", "recovery_of": None,
            })
            return fence
        return self._transaction(acquire)

    def finish(self, fence: CollectionFence):
        def release(transaction):
            state = self._held(transaction, fence)
            pending = list(self._run_ref(fence.owner).collection("deletions").stream(transaction=transaction))
            if any(snapshot.to_dict().get("status") != "deleted" for snapshot in pending):
                raise OperationConflict("collection_pending", "Exact-generation deletions require reconciliation.")
            transaction.set(self._artifact_maintenance, {**state, "owner": None, "execution_name": None})
            transaction.update(self._run_ref(fence.owner), {"status": "complete"})
        self._transaction(release)

    def record_deletion(self, fence, artifact):
        identity = hashlib.sha256((artifact.object_id + "\0" + artifact.generation).encode()).hexdigest()
        document = self._run_ref(fence.owner).collection("deletions").document(identity)

        def record(transaction):
            self._held(transaction, fence)
            prior = document.get(transaction=transaction)
            value = {"artifact": vars(artifact), "status": "pending"}
            if prior.exists:
                if prior.to_dict().get("artifact") != vars(artifact):
                    raise ValueError("Collection deletion identity conflict")
            else:
                transaction.create(document, value)
        self._transaction(record)
        return document

    def mark_deleted(self, fence, document):
        def mark(transaction):
            self._held(transaction, fence)
            transaction.update(document, {"status": "deleted"})
        self._transaction(mark)

    def retire_upload(self, fence, snapshot):
        def retire(transaction):
            self._held(transaction, fence)
            current = snapshot.reference.get(transaction=transaction)
            if not current.exists or current.to_dict() != snapshot.to_dict():
                raise ValueError("Staging upload changed under the collection barrier")
            transaction.delete(snapshot.reference)
        self._transaction(retire)

    def recover(self, previous_owner, execution_name, execution_status):
        """Take over only after a known old execution stops, retaining its replay log."""
        prior_ref = self._run_ref(previous_owner)
        prior = prior_ref.get()
        value = prior.to_dict() if prior.exists else None
        if not isinstance(value, dict) or not isinstance(value.get("execution_name"), str):
            raise ValueError("Collection recovery identity is unavailable")
        if execution_status(value["execution_name"]) not in {"succeeded", "failed", "cancelled"}:
            raise OperationConflict("collection_execution_live", "Collector execution is not confirmed stopped.")
        execution_name = self._execution(execution_name)
        owner = uuid.uuid4().hex

        def takeover(transaction):
            state = self._maintenance_state(transaction)
            current = prior_ref.get(transaction=transaction)
            if (state["owner"] != previous_owner or state["execution_name"] != value["execution_name"]
                    or not current.exists or current.to_dict() != value):
                raise OperationConflict("stale_collection", "Collection recovery identity changed.")
            fence = CollectionFence(owner, state["epoch"] + 1, execution_name)
            transaction.set(self._artifact_maintenance, {
                "schema_version": SCHEMA_VERSION, "epoch": fence.epoch,
                "owner": owner, "execution_name": execution_name,
            })
            transaction.create(self._run_ref(owner), {
                "execution_name": execution_name, "epoch": fence.epoch,
                "status": "collecting", "recovery_of": previous_owner,
            })
            transaction.update(prior_ref, {"status": "recovering", "recovered_by": owner})
            return fence
        fence = self._transaction(takeover)
        return fence

    def recovery_artifacts(self, owner):
        """Replay the full recovery chain, including an interrupted recovery itself."""
        seen = set()
        while owner is not None:
            if owner in seen:
                raise ValueError("Corrupt collection recovery chain")
            seen.add(owner)
            document = self._run_ref(owner)
            snapshot = document.get()
            value = snapshot.to_dict() if snapshot.exists else None
            if not isinstance(value, dict) or "recovery_of" not in value:
                raise ValueError("Missing collection recovery record")
            for deletion in document.collection("deletions").stream():
                yield ArtifactRef(**deletion.to_dict()["artifact"])
            owner = value["recovery_of"]


class ReferenceAwareCollector:
    def __init__(self, stores, maintenance: ArtifactCollection, *, clock=None):
        self.stores = stores
        self.maintenance = maintenance
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _ref(self, raw):
        artifact = ArtifactRef(**raw)
        self.stores.artifacts.validate_ref(artifact)
        return artifact

    def _references(self, value):
        if isinstance(value, dict):
            if {"object_id", "generation", "sha256"}.issubset(value):
                yield self._ref({key: value[key] for key in ("object_id", "generation", "sha256")})
            else:
                for child in value.values():
                    yield from self._references(child)
        elif isinstance(value, list):
            for child in value:
                yield from self._references(child)

    def _roots(self, cutoff):
        root = self.maintenance.root
        protected = set()
        upload_tokens = set()

        def protect(artifact):
            self.stores.artifacts.validate_ref(artifact)
            protected.add((artifact.object_id, artifact.generation))

        # list_documents includes missing parents with subcollections. A query
        # stream alone would silently omit orphaned accepted revisions.
        for document in root.collection("projects").list_documents():
            project = document.get()
            if not project.exists:
                raise ValueError("Accepted revisions have no project ownership record")
            state = FirestoreRevisionStore._project_state(project, project.id)
            revisions = set()
            for snapshot in project.reference.collection("revisions").stream():
                revisions.add(snapshot.id)
                revision = _revision_from_document(snapshot.to_dict(), project.id, snapshot.id)
                protect(revision.manifest)
                manifest = self.stores.persistence.read_manifest(revision.manifest)
                for entry in manifest.entries.values():
                    protect(entry.artifact)
            if state["current_revision_id"] is not None and state["current_revision_id"] not in revisions:
                raise ValueError("Current project revision is missing")
        for document in root.collection("operations").list_documents():
            snapshot = document.get()
            operation = FirestoreOperationStore._operation(snapshot)
            token = operation.payload.get("upload_token")
            if token is not None:
                upload_tokens.add(token)
            for artifact in self._references(snapshot.to_dict()):
                protect(artifact)
        catalog = set()
        for snapshot in root.collection("artifact_references").stream():
            artifact = FirestoreArtifactReferences._artifact_from_document(
                snapshot.to_dict(), snapshot.id, self.maintenance.artifact_store_id,
            )
            protect(artifact)
            catalog.add(artifact.sha256)
        shared = self.maintenance.client.collection("shared_workflow_v1").document(self.maintenance.dataset)
        binding = shared.get()
        if binding.exists:
            state = binding.to_dict()
            if (state.get("schema_version") != SCHEMA_VERSION or isinstance(state.get("schema_version"), bool)
                    or state.get("artifact_store_id") != self.maintenance.artifact_store_id
                    or not isinstance(state.get("sequence"), int) or isinstance(state.get("sequence"), bool)
                    or state["sequence"] < 0):
                raise ValueError("Shared artifact identity or schema does not match collector")
        for table in ("export_candidates", "audio_reviews", "publications"):
            for snapshot in shared.collection(table).stream():
                checksums = snapshot.to_dict().get("checksums")
                if (not binding.exists or not isinstance(checksums, dict)
                        or any(value not in catalog for value in checksums.values())):
                    raise ValueError("Shared artifact references are incomplete")
        retired = []
        for snapshot in root.collection("uploads").stream():
            value = snapshot.to_dict()
            files = value.get("files")
            timestamp = value.get("updated_at")
            if (set(value) - {"owner_uid", "project_id", "files", "updated_at"}
                    or not isinstance(value.get("owner_uid"), str) or not value["owner_uid"]
                    or value.get("project_id") != self.maintenance.client.project or not isinstance(files, dict)):
                raise ValueError("Corrupt staging upload")
            # Pre-timestamp records are retained, never guessed old enough.
            if timestamp is not None and (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                                          or not math.isfinite(timestamp) or timestamp < 0):
                raise ValueError("Corrupt staging upload timestamp")
            artifacts = [self._ref(raw) for raw in files.values()]
            if snapshot.id in upload_tokens or timestamp is None or timestamp >= cutoff.timestamp():
                for artifact in artifacts:
                    protect(artifact)
            else:
                retired.append(snapshot)
        return protected, retired

    def _delete(self, fence, artifact):
        self.stores.artifacts.validate_ref(artifact)
        document = self.maintenance.record_deletion(fence, artifact)
        try:
            self.stores.artifacts.bucket.blob(artifact.object_id, generation=int(artifact.generation)).delete(
                if_generation_match=int(artifact.generation),
            )
        except Exception as error:
            if getattr(error, "code", None) != 404 and getattr(error, "status_code", None) != 404:
                # A timed-out RPC may still delete remotely. Keep the barrier
                # until exact-generation replay makes future promotion safe.
                raise
        self.maintenance.mark_deleted(fence, document)

    def collect(self, execution_name):
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Collector requires an aware clock")
        fence = self.maintenance.begin(execution_name)
        if fence is None:
            return {"status": "busy", "deleted": 0, "retired_uploads": 0}
        cutoff = now.astimezone(timezone.utc) - timedelta(days=7)
        protected, retired = self._roots(cutoff)
        candidates = []
        namespace = self.stores.artifacts.namespace + "/"
        for blob in self.stores.artifacts.bucket.list_blobs(prefix=namespace):
            checksum = blob.name[len(namespace):] if blob.name.startswith(namespace) else ""
            created = blob.time_created
            if (not re.fullmatch(r"[a-f0-9]{64}", checksum) or not isinstance(created, datetime)
                    or created.tzinfo is None or created >= cutoff):
                continue
            artifact = self._ref({"object_id": blob.name, "generation": str(blob.generation), "sha256": checksum})
            if (artifact.object_id, artifact.generation) not in protected:
                candidates.append(artifact)
        # No deletion occurs until the complete root/manifest scan succeeds.
        for snapshot in retired:
            self.maintenance.retire_upload(fence, snapshot)
        for artifact in candidates:
            self._delete(fence, artifact)
        self.maintenance.finish(fence)
        return {"status": "complete", "deleted": len(candidates), "retired_uploads": len(retired)}

    def recover(self, previous_owner, execution_name, execution_status):
        fence = self.maintenance.recover(previous_owner, execution_name, execution_status)
        count = 0
        for artifact in self.maintenance.recovery_artifacts(previous_owner):
            self._delete(fence, artifact)
            count += 1
        self.maintenance.finish(fence)
        return {"status": "recovered", "replayed_deletions": count}


def main():
    from .cloud_runtime import _execution_identity

    execution, project, region = _execution_identity()
    settings = CloudSettings.from_environment()
    if settings.project != project or os.environ.get("CLOUD_RUN_JOB") != os.environ.get("MANGA_GC_JOB"):
        raise ValueError("Collector job identity does not match configured infrastructure")
    stores = cloud_stores(settings, Path(tempfile.gettempdir()) / "manga-gc-cache")
    maintenance = ArtifactCollection(stores.revisions.client, settings.dataset, stores.artifacts.artifact_store_id)
    collector = ReferenceAwareCollector(stores, maintenance)
    recovery = os.environ.get("MANGA_GC_RECOVER_OWNER")
    if recovery:
        from .cloud_jobs import CloudRunJobs

        # This client is used only to verify termination of the configured GC
        # job, never to dispatch pipeline or inference work.
        job = os.environ["MANGA_GC_JOB"]
        reader = CloudRunJobs(project, region, {"magi": job, "pipeline": job})
        result = collector.recover(recovery, execution, reader.status)
    else:
        result = collector.collect(execution)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
