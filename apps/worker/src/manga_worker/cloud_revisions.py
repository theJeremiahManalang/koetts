"""Firestore ownership, revision, and artifact-reference adapters.

All documents live below ``hosted_workflow_v1/{dataset}``, which is bound to
one Firestore schema and one immutable artifact store identity. The SDK stays
optional for local users and is imported only when an operation runs.
"""
from __future__ import annotations

import re
from dataclasses import asdict

from manga_tts.persistence import ArtifactRef, PersistenceConflict, ProjectRevision, WriteFence


SCHEMA_VERSION = 1
_DATASET = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")
_STORE_ID = re.compile(r"gcs-v1:[a-f0-9]{64}\Z")
_CHECKSUM = re.compile(r"[a-f0-9]{64}\Z")
_GENERATION = re.compile(r"[1-9][0-9]*\Z")


def _document_id(value: str, label: str) -> str:
    if (not isinstance(value, str) or not value or value in {".", ".."}
            or "/" in value or len(value.encode("utf-8")) > 1500):
        raise ValueError(f"Invalid {label}")
    return value


def _validate_ref(artifact: ArtifactRef) -> None:
    if (not isinstance(artifact, ArtifactRef)
            or not isinstance(artifact.object_id, str) or not artifact.object_id
            or not _GENERATION.fullmatch(artifact.generation)
            or not _CHECKSUM.fullmatch(artifact.sha256)):
        raise ValueError("Invalid artifact reference")
    # GCSArtifactStore uses bucket and namespace to establish this identity.
    # The exact object name remains adapter-owned; binding prevents mixing stores.


def _revision_from_document(value: dict, project_id: str, revision_id: str) -> ProjectRevision:
    try:
        if (not isinstance(value, dict)
                or set(value) != {"schema_version", "project_id", "revision_id", "parent_revision_id", "manifest", "project_hash", "fence"}
                or value.get("schema_version") != SCHEMA_VERSION or isinstance(value.get("schema_version"), bool)
                or value.get("project_id") != project_id or value.get("revision_id") != revision_id):
            raise ValueError
        manifest = ArtifactRef(**value["manifest"])
        revision = ProjectRevision(
            revision_id=value["revision_id"], parent_revision_id=value["parent_revision_id"],
            manifest=manifest, project_hash=value["project_hash"], fence=value["fence"],
        )
        if (not isinstance(revision.project_hash, str) or not _CHECKSUM.fullmatch(revision.project_hash)
                or (revision.parent_revision_id is not None and
                    (not isinstance(revision.parent_revision_id, str) or not revision.parent_revision_id))
                or not isinstance(revision.fence, int) or isinstance(revision.fence, bool) or revision.fence < 1):
            raise ValueError
        _validate_ref(revision.manifest)
        return revision
    except (KeyError, TypeError, ValueError):
        raise ValueError("Corrupt hosted project revision") from None


class _FirestoreHostedStore:
    def __init__(self, client, dataset: str, artifact_store_id: str):
        if not isinstance(dataset, str) or not _DATASET.fullmatch(dataset):
            raise ValueError("Invalid hosted dataset")
        if not isinstance(artifact_store_id, str) or not _STORE_ID.fullmatch(artifact_store_id):
            raise ValueError("Invalid artifact store identity")
        self.client = client
        self.dataset = dataset
        self.artifact_store_id = artifact_store_id
        self.root = client.collection("hosted_workflow_v1").document(dataset)

    def _binding(self, transaction):
        snapshot = self.root.get(transaction=transaction)
        if not snapshot.exists:
            return False
        self._validate_binding(snapshot)
        return True

    def _validate_binding(self, snapshot):
        state = snapshot.to_dict()
        if (not isinstance(state, dict) or set(state) != {"schema_version", "artifact_store_id"}
                or state.get("schema_version") != SCHEMA_VERSION or isinstance(state.get("schema_version"), bool)
                or state.get("artifact_store_id") != self.artifact_store_id):
            raise ValueError("Hosted dataset belongs to a different schema or artifact store")

    @staticmethod
    def _contains_data(value) -> bool:
        if value is None or isinstance(value, FileNotFoundError):
            return False
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        return True

    def _has_orphan_records(self) -> bool:
        for collection in ("projects", "artifact_references", "operations", "operation_idempotency_keys",
                           "operation_stage_slots", "operation_project_slots", "uploads",
                           "production_months", "production_admissions", "cloud_budget_v1"):
            if list(self.root.collection(collection).limit(1).stream()):
                return True
        return False

    def ensure_binding(self) -> None:
        """Bind an empty dataset before a domain transaction writes any records."""
        from google.cloud import firestore

        # Check orphan namespaces before opening the single-document binding
        # transaction. Keeping collection range reads out of competing root
        # creation transactions avoids emulator/server lock cycles. All hosted
        # writers initialize first, so no supported writer can add children in
        # this interval without first creating the same root binding.
        snapshot = self.root.get()
        if snapshot.exists:
            self._validate_binding(snapshot)
            return
        if self._has_orphan_records():
            # A legitimate initializer may have published the root while the
            # collection scan was in flight. Accept that binding after checking
            # its identity; otherwise preserve the orphan rejection.
            snapshot = self.root.get()
            if snapshot.exists:
                self._validate_binding(snapshot)
                return
            raise ValueError("Hosted dataset has orphaned records without a namespace binding")

        @firestore.transactional
        def initialize(transaction):
            snapshot = self.root.get(transaction=transaction)
            if snapshot.exists:
                self._validate_binding(snapshot)
                return
            transaction.create(self.root, {
                "schema_version": SCHEMA_VERSION,
                "artifact_store_id": self.artifact_store_id,
            })

        initialize(self.client.transaction())

    def _run(self, operation, *, bind_if_missing: bool = False):
        from google.cloud import firestore

        if bind_if_missing:
            self.ensure_binding()

        @firestore.transactional
        def execute(transaction):
            # A mutation may proceed only under the binding established before
            # this transaction. If it vanished, fail closed instead of adopting
            # a namespace that changed between initialization and the write.
            if bind_if_missing and not self._binding(transaction):
                raise ValueError("Hosted dataset namespace binding is missing")
            result, binding_exists = operation(transaction)
            if not binding_exists and self._contains_data(result):
                raise ValueError("Hosted dataset has records without a namespace binding")
            return result

        return execute(self.client.transaction())


class FirestoreRevisionStore(_FirestoreHostedStore):
    """Transactional writer ownership and immutable project revisions."""

    def _project(self, project_id: str):
        _document_id(project_id, "project ID")
        return self.root.collection("projects").document(project_id)

    def _revision(self, project_id: str, revision_id: str):
        _document_id(revision_id, "revision ID")
        return self._project(project_id).collection("revisions").document(revision_id)

    @staticmethod
    def _project_state(snapshot, project_id):
        if not snapshot.exists:
            return {"schema_version": SCHEMA_VERSION, "project_id": project_id,
                    "last_fence": 0, "owner_id": None, "active_fence": None,
                    "current_revision_id": None}
        state = snapshot.to_dict()
        if (not isinstance(state, dict) or set(state) != {"schema_version", "project_id", "last_fence", "owner_id",
                                                          "active_fence", "current_revision_id"}
                or state.get("schema_version") != SCHEMA_VERSION or isinstance(state.get("schema_version"), bool)
                or state.get("project_id") != project_id):
            raise ValueError("Corrupt hosted project ownership state")
        last = state.get("last_fence")
        active = state.get("active_fence")
        owner = state.get("owner_id")
        current = state.get("current_revision_id")
        if (not isinstance(last, int) or isinstance(last, bool) or last < 0
                or (current is not None and (not isinstance(current, str) or not current))):
            raise ValueError("Corrupt hosted project ownership state")
        if owner is None:
            if active is not None:
                raise ValueError("Corrupt hosted project ownership state")
        elif (not isinstance(owner, str) or not owner or not isinstance(active, int)
              or isinstance(active, bool) or active < 1 or active != last):
            raise ValueError("Corrupt hosted project ownership state")
        return state

    @classmethod
    def _validated_project_state(cls, project, snapshot, project_id: str, transaction):
        if not snapshot.exists and list(project.collection("revisions").limit(1).stream(transaction=transaction)):
            raise ValueError("Hosted project has orphaned revisions without ownership state")
        return cls._project_state(snapshot, project_id)

    def current(self, project_id: str) -> ProjectRevision | None:
        project = self._project(project_id)

        def operation(transaction):
            bound = self._binding(transaction)
            project_snapshot = project.get(transaction=transaction)
            if project_snapshot.exists and not bound:
                raise ValueError("Hosted project exists without a namespace binding")
            state = self._validated_project_state(project, project_snapshot, project_id, transaction)
            revision_id = state["current_revision_id"]
            if revision_id is None:
                return None, bound
            revision_snapshot = self._revision(project_id, revision_id).get(transaction=transaction)
            if not revision_snapshot.exists:
                raise ValueError("Hosted project pointer references a missing revision")
            return _revision_from_document(revision_snapshot.to_dict(), project_id, revision_id), bound

        return self._run(operation)

    def active_owner(self, project_id: str) -> WriteFence | None:
        """Read ownership for reconciliation after authoritative execution termination."""
        project = self._project(project_id)

        def operation(transaction):
            bound = self._binding(transaction)
            project_snapshot = project.get(transaction=transaction)
            if project_snapshot.exists and not bound:
                raise ValueError("Hosted project exists without a namespace binding")
            state = self._project_state(project_snapshot, project_id)
            if state["owner_id"] is None:
                return None, bound
            return WriteFence(project_id, state["owner_id"], state["active_fence"]), bound

        return self._run(operation)

    def acquire(self, project_id: str, owner_id: str) -> WriteFence:
        project = self._project(project_id)
        _document_id(owner_id, "owner ID")

        def operation(transaction):
            bound = self._binding(transaction)
            snapshot = project.get(transaction=transaction)
            state = self._validated_project_state(project, snapshot, project_id, transaction)
            if state["owner_id"] is not None:
                raise PersistenceConflict("writer_conflict", "Another writer owns this project.")
            value = state["last_fence"] + 1
            updated = {**state, "last_fence": value, "owner_id": owner_id, "active_fence": value}
            transaction.set(project, updated)
            return WriteFence(project_id=project_id, owner_id=owner_id, value=value), bound

        return self._run(operation, bind_if_missing=True)

    def _end_ownership(self, fence: WriteFence, worker_stopped: bool | None = None) -> None:
        if not isinstance(fence, WriteFence) or not isinstance(fence.value, int) or isinstance(fence.value, bool):
            raise ValueError("Invalid writer fence")
        project = self._project(fence.project_id)

        def operation(transaction):
            bound = self._binding(transaction)
            snapshot = project.get(transaction=transaction)
            state = self._validated_project_state(project, snapshot, fence.project_id, transaction)
            if (state["owner_id"] != fence.owner_id or state["active_fence"] != fence.value):
                raise PersistenceConflict("stale_fence", "Writer ownership changed before release.")
            if worker_stopped is not None and worker_stopped is not True:
                raise PersistenceConflict("writer_conflict", "Ownership remains until the worker is confirmed stopped.")
            transaction.set(project, {**state, "owner_id": None, "active_fence": None})
            return None, bound

        self._run(operation, bind_if_missing=True)

    def release(self, fence: WriteFence) -> None:
        self._end_ownership(fence)

    def recover(self, fence: WriteFence, worker_stopped: bool) -> None:
        if worker_stopped is not True:
            raise PersistenceConflict("writer_conflict", "Ownership remains until the worker is confirmed stopped.")
        self._end_ownership(fence, worker_stopped=True)

    def commit(self, expected_revision_id: str | None, fence: WriteFence,
               revision: ProjectRevision) -> None:
        if not isinstance(fence, WriteFence):
            raise ValueError("Invalid writer fence")
        if not isinstance(revision, ProjectRevision):
            raise ValueError("Invalid project revision")
        if (not isinstance(fence.value, int) or isinstance(fence.value, bool) or fence.value < 1
                or not isinstance(revision.fence, int) or isinstance(revision.fence, bool) or revision.fence < 1
                or revision.parent_revision_id != expected_revision_id or revision.fence != fence.value):
            raise PersistenceConflict("revision_conflict", "Revision does not match its expected parent or fence.")
        _document_id(expected_revision_id, "expected revision ID") if expected_revision_id is not None else None
        _document_id(revision.revision_id, "revision ID")
        _validate_ref(revision.manifest)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "project_id": fence.project_id,
            **asdict(revision),
        }
        if _revision_from_document(payload, fence.project_id, revision.revision_id) != revision:
            raise ValueError("Invalid project revision")
        project = self._project(fence.project_id)
        revision_ref = self._revision(fence.project_id, revision.revision_id)

        def operation(transaction):
            bound = self._binding(transaction)
            project_snapshot = project.get(transaction=transaction)
            state = self._validated_project_state(project, project_snapshot, fence.project_id, transaction)
            revision_snapshot = revision_ref.get(transaction=transaction)
            if (state["owner_id"] != fence.owner_id or state["active_fence"] != fence.value
                    or revision.fence != state["last_fence"]):
                raise PersistenceConflict("stale_fence", "Writer fence is no longer current.")
            if state["current_revision_id"] != expected_revision_id:
                raise PersistenceConflict("revision_conflict", "Project revision changed before commit.")
            if revision_snapshot.exists:
                raise PersistenceConflict("revision_conflict", "Revision identity already exists.")
            transaction.create(revision_ref, payload)
            transaction.set(project, {**state, "current_revision_id": revision.revision_id})
            return None, bound

        self._run(operation, bind_if_missing=True)

    def get_revision(self, project_id: str, revision_id: str) -> ProjectRevision:
        revision_ref = self._revision(project_id, revision_id)

        def operation(transaction):
            bound = self._binding(transaction)
            snapshot = revision_ref.get(transaction=transaction)
            if not snapshot.exists:
                raise FileNotFoundError("Project revision is missing")
            return _revision_from_document(snapshot.to_dict(), project_id, revision_id), bound

        return self._run(operation)


class FirestoreArtifactReferences(_FirestoreHostedStore):
    """Create-only checksum references bound to the same hosted dataset."""

    def _reference(self, checksum: str):
        if not isinstance(checksum, str) or not _CHECKSUM.fullmatch(checksum):
            raise ValueError("Invalid artifact checksum")
        return self.root.collection("artifact_references").document(checksum)

    @staticmethod
    def _artifact_from_document(value: dict, checksum: str, artifact_store_id: str) -> ArtifactRef:
        if (not isinstance(value, dict)
                or set(value) != {"schema_version", "artifact_store_id", "object_id", "generation", "sha256"}
                or value.get("schema_version") != SCHEMA_VERSION or isinstance(value.get("schema_version"), bool)
                or value.get("artifact_store_id") != artifact_store_id or value.get("sha256") != checksum):
            raise ValueError("Corrupt hosted artifact reference")
        try:
            artifact = ArtifactRef(object_id=value["object_id"], generation=value["generation"], sha256=value["sha256"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Corrupt hosted artifact reference") from None
        _validate_ref(artifact)
        return artifact

    def get(self, checksum: str) -> ArtifactRef:
        reference = self._reference(checksum)

        def operation(transaction):
            bound = self._binding(transaction)
            snapshot = reference.get(transaction=transaction)
            if not snapshot.exists:
                return FileNotFoundError("Artifact reference is missing"), bound
            return self._artifact_from_document(snapshot.to_dict(), checksum, self.artifact_store_id), bound

        result = self._run(operation)
        if isinstance(result, FileNotFoundError):
            raise result
        return result

    def put(self, artifact: ArtifactRef) -> None:
        _validate_ref(artifact)
        reference = self._reference(artifact.sha256)

        def operation(transaction):
            bound = self._binding(transaction)
            snapshot = reference.get(transaction=transaction)
            if snapshot.exists:
                existing = self._artifact_from_document(snapshot.to_dict(), artifact.sha256, self.artifact_store_id)
                if existing != artifact:
                    raise ValueError("Artifact reference conflicts with existing checksum identity")
                return None, bound
            transaction.create(reference, {
                "schema_version": SCHEMA_VERSION,
                "artifact_store_id": self.artifact_store_id,
                "object_id": artifact.object_id,
                "generation": artifact.generation,
                "sha256": artifact.sha256,
            })
            return None, bound

        self._run(operation, bind_if_missing=True)
