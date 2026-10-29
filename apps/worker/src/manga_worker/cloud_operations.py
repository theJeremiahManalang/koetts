"""Transactional Firestore operation coordination for hosted finite workers."""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from collections.abc import Mapping
from dataclasses import replace

from manga_tts.operations import (
    Operation,
    OperationClaim,
    OperationConflict,
    OperationPolicy,
)

from .cloud_revisions import SCHEMA_VERSION, _FirestoreHostedStore, _document_id

_MAX_PAYLOAD_BYTES = 700 * 1024


def _json(value) -> str:
    _assert_json_value(value)
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _assert_json_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise ValueError("JSON values must be finite")
    if isinstance(value, list):
        for item in value:
            _assert_json_value(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _assert_json_value(item)
        return
    raise TypeError("Value is not strict JSON")


def _valid_integer(value, minimum=0):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _valid_time(value, optional=False):
    if value is None:
        return optional
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class FirestoreOperationStore(_FirestoreHostedStore):
    """Hosted operation store. Firestore owns dispatch intent; Cloud Run owns execution."""

    def __init__(self, client, dataset: str, artifact_store_id: str, policy: OperationPolicy | None = None):
        super().__init__(client, dataset, artifact_store_id)
        self.policy = policy or OperationPolicy()

    @property
    def _operations(self):
        return self.root.collection("operations")

    @property
    def _slots(self):
        return self.root.collection("operation_stage_slots")

    @property
    def _projects(self):
        return self.root.collection("operation_project_slots")

    def _operation_ref(self, operation_id):
        return self._operations.document(_document_id(operation_id, "operation ID"))

    def _slot_ref(self, stage, number):
        return self._slots.document(f"{stage}-{number}")

    def _project_ref(self, project_id):
        return self._projects.document(_document_id(project_id, "project ID"))

    @staticmethod
    def _operation(snapshot):
        if not snapshot.exists:
            raise FileNotFoundError("Operation was not found")
        data = snapshot.to_dict()
        try:
            expected = {
                "schema_version",
                "operation_id",
                "idempotency_key",
                "request_fingerprint",
                "project_id",
                "stage",
                "payload",
                "revision",
                "source_fingerprint",
                "configuration_fingerprint",
                "status",
                "attempt_count",
                "fence",
                "lease_expires_at",
                "provider_outcome_pending",
                "progress",
                "checkpoint",
                "result",
                "failure_code",
                "message",
                "created_at",
                "updated_at",
                "attempt_started_at",
            }
            if (
                not isinstance(data, dict)
                or set(data) != expected
                or data.get("schema_version") != SCHEMA_VERSION
                or isinstance(data.get("schema_version"), bool)
            ):
                raise ValueError
            op = Operation(
                operation_id=data["operation_id"],
                idempotency_key=data["idempotency_key"],
                request_fingerprint=data["request_fingerprint"],
                project_id=data["project_id"],
                stage=data["stage"],
                payload=data["payload"],
                revision=data["revision"],
                source_fingerprint=data["source_fingerprint"],
                configuration_fingerprint=data["configuration_fingerprint"],
                status=data["status"],
                attempt_count=data["attempt_count"],
                fence=data["fence"],
                lease_expires_at=data["lease_expires_at"],
                worker_pid=None,
                worker_created_at=None,
                provider_outcome_pending=data["provider_outcome_pending"],
                progress=data["progress"],
                checkpoint=data["checkpoint"],
                result=data["result"],
                failure_code=data["failure_code"],
                message=data["message"],
                created_at=data["created_at"],
                updated_at=data["updated_at"],
                attempt_started_at=data["attempt_started_at"],
            )
            if (
                op.operation_id != snapshot.id
                or not isinstance(op.operation_id, str)
                or not op.operation_id
                or not isinstance(op.idempotency_key, str)
                or not op.idempotency_key.strip()
                or len(op.idempotency_key) > 200
                or any(ord(character) < 32 for character in op.idempotency_key)
                or not isinstance(op.request_fingerprint, str)
                or not op.request_fingerprint
                or not isinstance(op.project_id, str)
                or not op.project_id
                or op.stage not in {"magi", "pipeline"}
                or not isinstance(op.payload, dict)
                or not isinstance(op.progress, dict)
                or (op.checkpoint is not None and not isinstance(op.checkpoint, dict))
                or (op.result is not None and not isinstance(op.result, dict))
                or op.status not in {"queued", "running", "complete", "failed", "reconciliation_required"}
                or not _valid_integer(op.attempt_count)
                or not _valid_integer(op.fence)
                or op.attempt_count != op.fence
                or op.attempt_count > 1000000
                or (op.status != "queued" and op.attempt_count == 0)
                or not _valid_time(op.lease_expires_at, optional=True)
                or not _valid_time(op.attempt_started_at, optional=True)
                or not _valid_time(op.created_at)
                or not _valid_time(op.updated_at)
                or (op.status == "running" and op.lease_expires_at is None)
                or (op.status != "running" and op.lease_expires_at is not None)
                or (op.attempt_count == 0 and op.attempt_started_at is not None)
                or (op.attempt_count > 0 and op.attempt_started_at is None)
                or not isinstance(op.provider_outcome_pending, bool)
                or not isinstance(op.message, str)
                or (op.failure_code is not None and not isinstance(op.failure_code, str))
                or (op.revision is not None and not isinstance(op.revision, str))
                or not all(
                    isinstance(value, str) and value for value in (op.source_fingerprint, op.configuration_fingerprint)
                )
            ):
                raise ValueError
            _document_id(op.project_id, "project ID")
            if (
                len(_json(op.payload).encode("utf-8")) > _MAX_PAYLOAD_BYTES
                or not isinstance(_json(op.progress), str)
                or (op.checkpoint is not None and not isinstance(_json(op.checkpoint), str))
                or (op.result is not None and not isinstance(_json(op.result), str))
            ):
                raise ValueError
            return op
        except (KeyError, TypeError, ValueError):
            raise ValueError("Corrupt hosted operation") from None

    def _get_tx(self, transaction, operation_id):
        snap = self._operation_ref(operation_id).get(transaction=transaction)
        return self._operation(snap)

    @staticmethod
    def _idempotency_record(snapshot, requested_key):
        value = snapshot.to_dict()
        if (
            not isinstance(value, dict)
            or set(value) != {"operation_id", "idempotency_key"}
            or not isinstance(value.get("operation_id"), str)
            or not value["operation_id"]
            or not isinstance(value.get("idempotency_key"), str)
            or not value["idempotency_key"]
            or hashlib.sha256(value["idempotency_key"].encode()).hexdigest() != snapshot.id
        ):
            raise ValueError("Corrupt hosted operation idempotency record")
        if value["idempotency_key"] != requested_key:
            raise OperationConflict("idempotency_conflict", "Idempotency identity hash collided.")
        return value

    @staticmethod
    def _validate_claim(claim):
        if (
            not isinstance(claim, OperationClaim)
            or not isinstance(claim.operation_id, str)
            or not claim.operation_id
            or not _valid_integer(claim.fence, 1)
        ):
            raise OperationConflict("stale_fence", "Invalid worker claim.")

    def _attempt(self, snapshot, operation, claim):
        if operation.stage not in self.policy.stage_capacities:
            raise ValueError("Operation stage is not enabled by this hosted policy")
        if not snapshot.exists:
            raise OperationConflict("stale_fence", "Attempt record is missing.")
        value = snapshot.to_dict()
        expected = {
            "attempt",
            "fence",
            "state",
            "started_at",
            "ended_at",
            "provider_outcome_pending",
            "message",
            "dispatch_state",
            "execution_name",
            "worker_registered",
            "execution_stopped_confirmed",
            "slot_number",
        }
        states = {
            "running",
            "complete",
            "failed",
            "retryable_failure",
            "uncertain",
            "operator_failed",
            "operator_retry",
            "worker_stopped",
            "dispatch_interrupted",
        }
        if (
            not isinstance(value, dict)
            or set(value) != expected
            or not _valid_integer(value.get("attempt"), 1)
            or not _valid_integer(value.get("fence"), 1)
            or value["fence"] != claim.fence
            or value["attempt"] != claim.fence
            or value["attempt"] != operation.attempt_count
            or value["attempt"] > self.policy.max_attempts
            or value.get("state") not in states
            or not _valid_time(value.get("started_at"))
            or not _valid_time(value.get("ended_at"), optional=True)
            or not isinstance(value.get("provider_outcome_pending"), bool)
            or not isinstance(value.get("message"), str)
            or value.get("dispatch_state") not in {"pending", "submitting", "started", "not_submitted"}
            or (
                value.get("execution_name") is not None
                and (not isinstance(value.get("execution_name"), str) or not value["execution_name"])
            )
            or not isinstance(value.get("worker_registered"), bool)
            or not isinstance(value.get("execution_stopped_confirmed"), bool)
            or not _valid_integer(value.get("slot_number"), 1)
            or value["slot_number"] > self.policy.stage_capacities[operation.stage]
            or (
                value["worker_registered"] and (value["execution_name"] is None or value["dispatch_state"] != "started")
            )
            or (value["dispatch_state"] == "started" and not value["worker_registered"])
            or (value["execution_stopped_confirmed"] and value["execution_name"] is None)
            or (operation.status == "running" and value["state"] != "running")
            or (operation.status == "reconciliation_required" and value["state"] != "uncertain")
            or (operation.status == "complete" and value["state"] != "complete")
            or (value["state"] == "running" and value["ended_at"] is not None)
            or (value["state"] != "running" and value["ended_at"] is None)
        ):
            raise ValueError("Corrupt hosted operation attempt")
        return value

    def enqueue(
        self,
        *,
        idempotency_key: str,
        payload: Mapping,
        project_id: str,
        stage: str,
        revision: str | None,
        source_fingerprint: str,
        configuration_fingerprint: str,
        request_fingerprint: str | None = None,
        admission=None,
    ) -> Operation:
        if (
            not isinstance(idempotency_key, str)
            or not idempotency_key.strip()
            or len(idempotency_key) > 200
            or any(ord(c) < 32 for c in idempotency_key)
        ):
            raise ValueError("A valid idempotency key is required")
        if (
            not isinstance(project_id, str)
            or not project_id
            or not isinstance(stage, str)
            or stage not in self.policy.stage_capacities
        ):
            raise ValueError("Project and supported operation stage are required")
        _document_id(project_id, "project ID")
        if revision is not None and not isinstance(revision, str):
            raise ValueError("Invalid operation revision")
        if not all(isinstance(value, str) and value for value in (source_fingerprint, configuration_fingerprint)):
            raise ValueError("Operation fingerprints are required")
        if request_fingerprint is not None and (not isinstance(request_fingerprint, str) or not request_fingerprint):
            raise ValueError("Invalid request fingerprint")
        payload_value = dict(payload)
        payload_json = _json(payload_value)
        if len(payload_json.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
            raise ValueError("Operation payload exceeds the hosted document limit")
        payload_value = json.loads(payload_json)
        fingerprint = request_fingerprint or hashlib.sha256(payload_json.encode()).hexdigest()
        now, operation_id = time.time(), uuid.uuid4().hex
        ref = self._operation_ref(operation_id)
        key_ref = self.root.collection("operation_idempotency_keys").document(
            hashlib.sha256(idempotency_key.encode()).hexdigest()
        )
        doc = {
            "schema_version": SCHEMA_VERSION,
            "operation_id": operation_id,
            "idempotency_key": idempotency_key,
            "request_fingerprint": fingerprint,
            "project_id": project_id,
            "stage": stage,
            "payload": payload_value,
            "revision": revision,
            "source_fingerprint": source_fingerprint,
            "configuration_fingerprint": configuration_fingerprint,
            "status": "queued",
            "attempt_count": 0,
            "fence": 0,
            "lease_expires_at": None,
            "provider_outcome_pending": False,
            "progress": {},
            "checkpoint": None,
            "result": None,
            "failure_code": None,
            "message": "Waiting for a worker.",
            "created_at": now,
            "updated_at": now,
            "attempt_started_at": None,
        }

        def operation(tx):
            bound = self._binding(tx)
            key_snapshot = key_ref.get(transaction=tx)
            if key_snapshot.exists:
                key_doc = self._idempotency_record(key_snapshot, idempotency_key)
                existing = self._operation_ref(key_doc["operation_id"]).get(transaction=tx)
                op = self._operation(existing)
                if op.idempotency_key != idempotency_key:
                    raise ValueError("Hosted operation idempotency record does not match its operation")
                if op.request_fingerprint != fingerprint:
                    raise OperationConflict(
                        "idempotency_conflict", "This idempotency key already belongs to a different request."
                    )
                return op, bound
            # Admission shares this commit. Existing intent retries return above
            # without consuming capacity again.
            if admission is not None:
                admission(tx)
            tx.create(ref, doc)
            tx.create(key_ref, {"operation_id": operation_id, "idempotency_key": idempotency_key})
            return Operation(
                **{k: v for k, v in doc.items() if k != "schema_version"}, worker_pid=None, worker_created_at=None
            ), bound

        return self._run(operation, bind_if_missing=True)

    def get(self, operation_id: str) -> Operation:
        def operation(tx):
            bound = self._binding(tx)
            return self._get_tx(tx, operation_id), bound

        return self._run(operation)

    def get_by_key(self, idempotency_key: str) -> Operation:
        if (
            not isinstance(idempotency_key, str)
            or not idempotency_key.strip()
            or len(idempotency_key) > 200
            or any(ord(c) < 32 for c in idempotency_key)
        ):
            raise ValueError("A valid idempotency key is required")
        key_ref = self.root.collection("operation_idempotency_keys").document(
            hashlib.sha256(idempotency_key.encode()).hexdigest()
        )

        def operation(tx):
            bound = self._binding(tx)
            snapshot = key_ref.get(transaction=tx)
            if not snapshot.exists:
                raise FileNotFoundError("Operation was not found")
            key = self._idempotency_record(snapshot, idempotency_key)
            operation = self._get_tx(tx, key["operation_id"])
            if operation.idempotency_key != idempotency_key:
                raise ValueError("Hosted operation idempotency record does not match its operation")
            return operation, bound

        return self._run(operation)

    def _active(self, tx, claim, allow_uncertain=False):
        self._validate_claim(claim)
        op = self._get_tx(tx, claim.operation_id)
        if op.fence != claim.fence or op.status not in (
            {"running", "reconciliation_required"} if allow_uncertain else {"running"}
        ):
            raise OperationConflict("stale_fence", "Worker fence is no longer current.")
        attempt_ref = self._operation_ref(claim.operation_id).collection("attempts").document(str(claim.fence))
        attempt_snapshot = attempt_ref.get(transaction=tx)
        attempt = self._attempt(attempt_snapshot, op, claim)
        slot_number = self._slot_number(tx, op, claim)
        project_ref = self._project_ref(op.project_id)
        project_snapshot = project_ref.get(transaction=tx)
        if not project_snapshot.exists:
            raise OperationConflict("stale_fence", "Worker no longer owns its project slot.")
        project = project_snapshot.to_dict()
        if (
            not isinstance(project, dict)
            or set(project) != {"operation_id", "stage", "slot_number", "fence"}
            or project.get("operation_id") != claim.operation_id
            or project.get("stage") != op.stage
            or not _valid_integer(project.get("slot_number"), 1)
            or project.get("slot_number") != slot_number
            or not _valid_integer(project.get("fence"), 1)
            or project["fence"] != claim.fence
            or not _valid_integer(attempt.get("slot_number"), 1)
            or attempt["slot_number"] != slot_number
            or attempt["slot_number"] > self.policy.stage_capacities[op.stage]
        ):
            raise OperationConflict("stale_fence", "Worker project slot identity is invalid.")
        slot_ref = self._slot_ref(op.stage, slot_number)
        return op, slot_ref

    def _slot_number(self, tx, op, claim):
        for number in range(1, self.policy.stage_capacities[op.stage] + 1):
            snap = self._slot_ref(op.stage, number).get(transaction=tx)
            if snap.exists:
                value = snap.to_dict()
                if (
                    isinstance(value, dict)
                    and set(value) == {"operation_id", "project_id", "fence"}
                    and value.get("operation_id") == claim.operation_id
                    and value.get("project_id") == op.project_id
                    and _valid_integer(value.get("fence"), 1)
                    and value["fence"] == claim.fence
                ):
                    return number
        raise OperationConflict("stale_fence", "Worker no longer owns its stage slot.")

    def claim(self, operation_id: str, now: float | None = None) -> OperationClaim | None:
        return self._claim(operation_id, now)

    def _claim(self, operation_id, now=None):
        now = time.time() if now is None else now
        if not _valid_time(now):
            raise ValueError("Claim timestamp must be finite")

        # Identity/time fixed across Firestore transaction retries.
        def operation(tx):
            bound = self._binding(tx)
            ref = self._operation_ref(operation_id)
            snap = ref.get(transaction=tx)
            op = self._operation(snap)
            if op.status != "queued":
                return None, bound
            if op.attempt_count > self.policy.max_attempts:
                raise ValueError("Hosted operation exceeded its configured attempt limit")
            if op.attempt_count >= self.policy.max_attempts:
                tx.update(
                    ref,
                    {
                        "status": "failed",
                        "failure_code": "attempt_limit",
                        "message": "Worker attempt limit reached.",
                        "updated_at": now,
                    },
                )
                return None, bound
            project_ref = self._project_ref(op.project_id)
            project = project_ref.get(transaction=tx)
            if project.exists:
                return None, bound
            available = None
            for number in range(1, self.policy.stage_capacities[op.stage] + 1):
                slot_ref = self._slot_ref(op.stage, number)
                slot = slot_ref.get(transaction=tx)
                if not slot.exists and available is None:
                    available = (number, slot_ref)
            if available is None:
                return None, bound
            number, slot_ref = available
            attempt, fence = op.attempt_count + 1, op.fence + 1
            attempt_ref = ref.collection("attempts").document(str(fence))
            attempt_doc = {
                "attempt": attempt,
                "fence": fence,
                "state": "running",
                "started_at": now,
                "ended_at": None,
                "provider_outcome_pending": False,
                "message": "",
                "dispatch_state": "pending",
                "execution_name": None,
                "worker_registered": False,
                "execution_stopped_confirmed": False,
                "slot_number": number,
            }
            tx.update(
                ref,
                {
                    "status": "running",
                    "attempt_count": attempt,
                    "fence": fence,
                    "lease_expires_at": now + self.policy.lease_seconds,
                    "provider_outcome_pending": False,
                    "failure_code": None,
                    "message": "Starting worker.",
                    "updated_at": now,
                    "attempt_started_at": now,
                },
            )
            tx.create(attempt_ref, attempt_doc)
            tx.create(slot_ref, {"operation_id": operation_id, "project_id": op.project_id, "fence": fence})
            tx.create(
                project_ref, {"operation_id": operation_id, "stage": op.stage, "slot_number": number, "fence": fence}
            )
            return OperationClaim(operation_id, fence), bound

        return self._run(operation, bind_if_missing=True)

    def claim_next(self, now: float | None = None) -> OperationClaim | None:
        now = time.time() if now is None else now

        # A bounded candidate page prevents unbounded transaction reads.
        def candidates(tx):
            bound = self._binding(tx)
            from google.cloud.firestore_v1.base_query import FieldFilter

            query = self._operations.where(filter=FieldFilter("status", "==", "queued"))
            query = query.order_by("created_at").limit(100)
            rows = list(query.stream(transaction=tx))
            return [row.id for row in rows], bound

        ids = self._run(candidates)
        for operation_id in ids:
            claim = self._claim(operation_id, now)
            if claim is not None:
                return claim
        return None

    def attempt(self, claim: OperationClaim) -> dict:
        def operation(tx):
            bound = self._binding(tx)
            self._validate_claim(claim)
            op = self._get_tx(tx, claim.operation_id)
            if op.fence != claim.fence:
                raise OperationConflict("stale_fence", "Worker fence is no longer current.")
            snap = (
                self._operation_ref(claim.operation_id)
                .collection("attempts")
                .document(str(claim.fence))
                .get(transaction=tx)
            )
            return self._attempt(snap, op, claim), bound

        return self._run(operation)

    def register_execution(self, claim: OperationClaim, execution_name: str) -> Operation:
        if not isinstance(execution_name, str) or not execution_name.strip():
            raise ValueError("Execution name is required")
        now = time.time()

        def operation(tx):
            bound = self._binding(tx)
            op, _ = self._active(tx, claim)
            ref = self._operation_ref(claim.operation_id).collection("attempts").document(str(claim.fence))
            snap = ref.get(transaction=tx)
            attempt = self._attempt(snap, op, claim)
            recorded = attempt.get("execution_name")
            if attempt.get("worker_registered") or (recorded is not None and recorded != execution_name):
                raise OperationConflict("duplicate_worker", "A Cloud Run execution already owns this attempt.")
            tx.update(ref, {"execution_name": execution_name, "worker_registered": True, "dispatch_state": "started"})
            tx.update(
                self._operation_ref(claim.operation_id),
                {"lease_expires_at": now + self.policy.lease_seconds, "updated_at": now},
            )
            return replace(op, lease_expires_at=now + self.policy.lease_seconds, updated_at=now), bound

        return self._run(operation, bind_if_missing=True)

    def begin_dispatch(self, claim: OperationClaim) -> bool:
        def operation(tx):
            bound = self._binding(tx)
            op, _ = self._active(tx, claim)
            ref = self._operation_ref(claim.operation_id).collection("attempts").document(str(claim.fence))
            snap = ref.get(transaction=tx)
            attempt = self._attempt(snap, op, claim)
            if attempt.get("dispatch_state") != "pending":
                return False, bound
            tx.update(ref, {"dispatch_state": "submitting"})
            return True, bound

        return self._run(operation, bind_if_missing=True)

    def record_execution(self, claim: OperationClaim, execution_name: str) -> None:
        if not isinstance(execution_name, str) or not execution_name.strip():
            raise ValueError("Execution name is required")

        def operation(tx):
            bound = self._binding(tx)
            op, _ = self._active(tx, claim, allow_uncertain=True)
            ref = self._operation_ref(claim.operation_id).collection("attempts").document(str(claim.fence))
            snap = ref.get(transaction=tx)
            value = self._attempt(snap, op, claim)
            old = value.get("execution_name")
            if old is not None and old != execution_name:
                raise OperationConflict(
                    "duplicate_worker", "A different Cloud Run execution already owns this attempt."
                )
            if old is None:
                tx.update(ref, {"execution_name": execution_name})
            return None, bound

        self._run(operation, bind_if_missing=True)

    def confirm_execution_stopped(self, claim: OperationClaim, execution_name: str) -> None:
        if not isinstance(execution_name, str) or not execution_name.strip():
            raise ValueError("Execution name is required")

        def operation(tx):
            bound = self._binding(tx)
            op, _ = self._active(tx, claim, allow_uncertain=True)
            ref = self._operation_ref(claim.operation_id).collection("attempts").document(str(claim.fence))
            snap = ref.get(transaction=tx)
            value = self._attempt(snap, op, claim)
            if value.get("execution_name") != execution_name:
                raise OperationConflict("execution_mismatch", "Stopped execution does not match the recorded attempt.")
            tx.update(ref, {"execution_stopped_confirmed": True})
            return None, bound

        self._run(operation, bind_if_missing=True)

    def heartbeat(self, claim, progress=None, checkpoint=None, provider_result_checkpointed=False):
        now = time.time()

        def operation(tx):
            bound = self._binding(tx)
            op, _ = self._active(tx, claim)
            merged = dict(op.progress)
            merged.update(progress or {})
            merged = json.loads(_json(merged))
            message = str(merged.get("message", op.message))[:400]
            updates = {
                "progress": merged,
                "message": message,
                "lease_expires_at": now + self.policy.lease_seconds,
                "updated_at": now,
            }
            if checkpoint is not None:
                updates["checkpoint"] = json.loads(_json(dict(checkpoint)))
            if provider_result_checkpointed:
                updates["provider_outcome_pending"] = False
            ref = self._operation_ref(claim.operation_id)
            attempt_ref = ref.collection("attempts").document(str(claim.fence))
            attempt = self._attempt(attempt_ref.get(transaction=tx), op, claim)
            updated = replace(
                op,
                progress=merged,
                message=message,
                lease_expires_at=now + self.policy.lease_seconds,
                updated_at=now,
                checkpoint=updates.get("checkpoint", op.checkpoint),
                provider_outcome_pending=False if provider_result_checkpointed else op.provider_outcome_pending,
            )
            tx.update(ref, updates)
            if provider_result_checkpointed:
                tx.update(attempt_ref, {"provider_outcome_pending": False})
            return updated, bound

        return self._run(operation, bind_if_missing=True)

    def mark_provider_call_pending(self, claim):
        now = time.time()

        def operation(tx):
            bound = self._binding(tx)
            op, _ = self._active(tx, claim)
            ref = self._operation_ref(claim.operation_id)
            attempt_ref = ref.collection("attempts").document(str(claim.fence))
            self._attempt(attempt_ref.get(transaction=tx), op, claim)
            tx.update(ref, {"provider_outcome_pending": True, "updated_at": now})
            tx.update(attempt_ref, {"provider_outcome_pending": True})
            return replace(op, provider_outcome_pending=True, updated_at=now), bound

        return self._run(operation, bind_if_missing=True)

    def _finish(self, claim, status, message, failure_code=None, result=None, retryable=False):
        if not isinstance(message, str) or (failure_code is not None and not isinstance(failure_code, str)):
            raise ValueError("Operation failure details are invalid")
        now = time.time()
        safe = message[:400]

        def operation(tx):
            bound = self._binding(tx)
            op, slot_ref = self._active(tx, claim)
            ref = self._operation_ref(claim.operation_id)
            attempt_ref = ref.collection("attempts").document(str(claim.fence))
            self._attempt(attempt_ref.get(transaction=tx), op, claim)
            project_ref = self._project_ref(op.project_id)
            if status == "complete":
                final, state, release, safe_message = "complete", "complete", True, "Ready for review."
            elif op.provider_outcome_pending:
                final, state, release, safe_message = (
                    "reconciliation_required",
                    "uncertain",
                    False,
                    "The provider outcome is uncertain. Reconcile before retrying.",
                )
            elif retryable and op.attempt_count < self.policy.max_attempts:
                final, state, release, safe_message = "queued", "retryable_failure", True, safe
            else:
                final, state, release, safe_message = "failed", "failed", True, safe
            updates = {
                "status": final,
                "failure_code": failure_code if final != "complete" else None,
                "message": safe_message,
                "lease_expires_at": None if final != "running" else op.lease_expires_at,
                "updated_at": now,
            }
            if result is not None:
                updates["result"] = result
            tx.update(ref, updates)
            tx.update(attempt_ref, {"state": state, "ended_at": now, "message": safe_message})
            if release:
                tx.delete(slot_ref)
                tx.delete(project_ref)
            updated = replace(
                op,
                status=final,
                failure_code=updates["failure_code"],
                message=safe_message,
                lease_expires_at=updates["lease_expires_at"],
                updated_at=now,
                result=result if result is not None else op.result,
            )
            return updated, bound

        return self._run(operation, bind_if_missing=True)

    def complete(self, claim, result):
        return self._finish(claim, "complete", "Ready for review.", result=json.loads(_json(result)))

    def fail(self, claim, message, failure_code, retryable=False):
        return self._finish(claim, "failed", message, failure_code, retryable=retryable)

    def mark_uncertain(self, claim, message):
        if not isinstance(message, str):
            raise ValueError("Uncertainty message is required")
        now = time.time()
        safe = message[:400]

        def operation(tx):
            bound = self._binding(tx)
            op, _ = self._active(tx, claim, allow_uncertain=True)
            ref = self._operation_ref(claim.operation_id)
            attempt_ref = ref.collection("attempts").document(str(claim.fence))
            self._attempt(attempt_ref.get(transaction=tx), op, claim)
            tx.update(
                ref,
                {
                    "status": "reconciliation_required",
                    "lease_expires_at": None,
                    "failure_code": "execution_uncertain",
                    "message": safe,
                    "updated_at": now,
                },
            )
            tx.update(attempt_ref, {"state": "uncertain", "ended_at": now, "message": safe})
            return replace(
                op,
                status="reconciliation_required",
                lease_expires_at=None,
                failure_code="execution_uncertain",
                message=safe,
                updated_at=now,
            ), bound

        return self._run(operation, bind_if_missing=True)

    def resolve_uncertain(self, operation_id, action):
        if action not in {"fail", "retry"}:
            raise ValueError("Choose fail or retry")
        now = time.time()

        def operation(tx):
            bound = self._binding(tx)
            ref = self._operation_ref(operation_id)
            snap = ref.get(transaction=tx)
            op = self._operation(snap)
            if op.status != "reconciliation_required":
                raise OperationConflict("invalid_transition", "Operation does not need reconciliation.")
            if action == "retry" and op.attempt_count >= self.policy.max_attempts:
                raise OperationConflict("retry_limit", "Operation reached its attempt limit.")
            claim = OperationClaim(operation_id, op.fence)
            active, slot_ref = self._active(tx, claim, allow_uncertain=True)
            attempt_ref = ref.collection("attempts").document(str(op.fence))
            attempt_snap = attempt_ref.get(transaction=tx)
            attempt = self._attempt(attempt_snap, active, claim)
            if attempt.get("execution_stopped_confirmed") is not True:
                raise OperationConflict(
                    "execution_live", "Cloud Run execution must be confirmed stopped before reconciliation."
                )
            project_ref = self._project_ref(op.project_id)
            if action == "fail":
                updated = replace(
                    op,
                    status="failed",
                    lease_expires_at=None,
                    message="Operator resolved the uncertain operation as failed.",
                    updated_at=now,
                )
                tx.update(
                    ref,
                    {
                        "status": "failed",
                        "lease_expires_at": None,
                        "message": "Operator resolved the uncertain operation as failed.",
                        "updated_at": now,
                    },
                )
                tx.update(attempt_ref, {"state": "operator_failed", "ended_at": now})
            else:
                updated = replace(
                    op,
                    status="queued",
                    lease_expires_at=None,
                    provider_outcome_pending=False,
                    failure_code=None,
                    message="Operator requested retry; provider billing may repeat.",
                    updated_at=now,
                )
                tx.update(
                    ref,
                    {
                        "status": "queued",
                        "lease_expires_at": None,
                        "provider_outcome_pending": False,
                        "failure_code": None,
                        "message": "Operator requested retry; provider billing may repeat.",
                        "updated_at": now,
                    },
                )
                tx.update(attempt_ref, {"state": "operator_retry", "ended_at": now})
            tx.delete(slot_ref)
            tx.delete(project_ref)
            return updated, bound

        return self._run(operation, bind_if_missing=True)

    def _query(self, filter_field, value, order_field, now):
        def operation(tx):
            bound = self._binding(tx)
            from google.cloud.firestore_v1.base_query import FieldFilter

            query = self._operations.where(filter=FieldFilter(filter_field, "==", value))
            query = query.order_by(order_field).limit(100)
            return [self._operation(s) for s in query.stream(transaction=tx)], bound

        return self._run(operation)

    def expired(self, now=None):
        now = time.time() if now is None else now
        # Query results bounded; coordinator can call repeatedly after reconciliation.
        return [
            op
            for op in self._query("status", "running", "lease_expires_at", now)
            if op.lease_expires_at is not None and op.lease_expires_at < now
        ]

    def timed_out(self, now=None):
        now = time.time() if now is None else now
        cutoff = now - self.policy.attempt_timeout_seconds
        return [
            op
            for op in self._query("status", "running", "attempt_started_at", now)
            if op.attempt_started_at is not None and op.attempt_started_at <= cutoff
        ]

    def reconciliation_required(self):
        return self._query("status", "reconciliation_required", "updated_at", time.time())

    def record_recovery_checkpoint(self, claim, project_hash):
        if not isinstance(project_hash, str) or not project_hash:
            raise ValueError("Project hash is required")
        now = time.time()

        def operation(tx):
            bound = self._binding(tx)
            op, _ = self._active(tx, claim, allow_uncertain=True)
            if op.payload.get("action") != "render":
                raise OperationConflict("invalid_checkpoint", "Only render operations can resume project checkpoints.")
            checkpoint = dict(op.checkpoint or {})
            checkpoint.update(project_hash=project_hash, recovered=True)
            updated = replace(op, checkpoint=checkpoint, updated_at=now)
            ref = self._operation_ref(claim.operation_id)
            tx.update(ref, {"checkpoint": checkpoint, "updated_at": now})
            return updated, bound

        return self._run(operation, bind_if_missing=True)

    def reconcile_checkpoint(self, claim: OperationClaim, checkpoint: Mapping) -> Operation:
        """Merge a checkpoint after stop confirmation, preserving provider uncertainty."""
        if not isinstance(checkpoint, Mapping):
            raise ValueError("Operation checkpoint must be a mapping")
        checkpoint_value = json.loads(_json(dict(checkpoint)))
        if len(_json(checkpoint_value).encode("utf-8")) > _MAX_PAYLOAD_BYTES:
            raise ValueError("Operation checkpoint exceeds the hosted document limit")
        now = time.time()

        def operation(tx):
            bound = self._binding(tx)
            op, _ = self._active(tx, claim, allow_uncertain=True)
            attempt_ref = self._operation_ref(claim.operation_id).collection("attempts").document(str(claim.fence))
            attempt = self._attempt(attempt_ref.get(transaction=tx), op, claim)
            if attempt["execution_stopped_confirmed"] is not True:
                raise OperationConflict(
                    "execution_live", "Cloud Run execution must be confirmed stopped before checkpoint reconciliation."
                )
            merged = dict(op.checkpoint or {})
            merged.update(checkpoint_value)
            if len(_json(merged).encode("utf-8")) > _MAX_PAYLOAD_BYTES:
                raise ValueError("Operation checkpoint exceeds the hosted document limit")
            updated = replace(op, checkpoint=merged, updated_at=now)
            ref = self._operation_ref(claim.operation_id)
            tx.update(ref, {"checkpoint": merged, "updated_at": now})
            return updated, bound

        return self._run(operation, bind_if_missing=True)

    def worker_stopped(self, claim, now=None):
        now = time.time() if now is None else now
        if not _valid_time(now):
            raise ValueError("Worker stop timestamp must be finite")

        def operation(tx):
            bound = self._binding(tx)
            op, slot_ref = self._active(tx, claim, allow_uncertain=True)
            ref = self._operation_ref(claim.operation_id)
            attempt_ref = ref.collection("attempts").document(str(claim.fence))
            attempt_snap = attempt_ref.get(transaction=tx)
            attempt = self._attempt(attempt_snap, op, claim)
            if attempt.get("execution_stopped_confirmed") is not True:
                raise OperationConflict(
                    "execution_live", "Cloud Run execution must be confirmed stopped before releasing capacity."
                )
            project_ref = self._project_ref(op.project_id)
            if op.provider_outcome_pending:
                message = "Worker stopped, but provider outcome is uncertain. Choose fail or retry to release capacity."
                tx.update(
                    ref,
                    {
                        "status": "reconciliation_required",
                        "lease_expires_at": None,
                        "failure_code": "execution_uncertain",
                        "message": message,
                        "updated_at": now,
                    },
                )
                tx.update(attempt_ref, {"state": "uncertain", "ended_at": now, "message": message})
                updated = replace(
                    op,
                    status="reconciliation_required",
                    lease_expires_at=None,
                    failure_code="execution_uncertain",
                    message=message,
                    updated_at=now,
                )
            else:
                retry = op.attempt_count < self.policy.max_attempts
                status = "queued" if retry else "failed"
                message = (
                    "Worker stopped; safe work returned to the queue." if retry else "Worker attempt limit reached."
                )
                tx.update(
                    ref,
                    {
                        "status": status,
                        "lease_expires_at": None,
                        "message": message,
                        "updated_at": now,
                        "failure_code": None if retry else "attempt_limit",
                    },
                )
                tx.update(attempt_ref, {"state": "worker_stopped", "ended_at": now, "message": message})
                tx.delete(slot_ref)
                tx.delete(project_ref)
                updated = replace(
                    op,
                    status=status,
                    lease_expires_at=None,
                    failure_code=None if retry else "attempt_limit",
                    message=message,
                    updated_at=now,
                )
            return updated, bound

        return self._run(operation, bind_if_missing=True)

    def hold_live_worker(self, claim, now=None):
        now = time.time() if now is None else now
        if not _valid_time(now):
            raise ValueError("Worker heartbeat timestamp must be finite")

        def operation(tx):
            bound = self._binding(tx)
            op, _ = self._active(tx, claim, allow_uncertain=True)
            ref = self._operation_ref(claim.operation_id)
            if op.status == "reconciliation_required":
                tx.update(ref, {"updated_at": now})
                return replace(op, updated_at=now), bound
            tx.update(ref, {"lease_expires_at": now + self.policy.lease_seconds, "updated_at": now})
            return replace(op, lease_expires_at=now + self.policy.lease_seconds, updated_at=now), bound

        return self._run(operation, bind_if_missing=True)

    def recover_unsubmitted(self, claim: OperationClaim, now: float | None = None) -> Operation:
        """Release an expired claim only when dispatch CAS proves no Run request began."""
        now = time.time() if now is None else now
        if not _valid_time(now):
            raise ValueError("Recovery timestamp must be finite")

        def operation(tx):
            bound = self._binding(tx)
            op, slot_ref = self._active(tx, claim)
            if op.lease_expires_at is None or op.lease_expires_at >= now:
                raise OperationConflict("lease_active", "Operation lease has not expired.")
            ref = self._operation_ref(claim.operation_id)
            attempt_ref = ref.collection("attempts").document(str(claim.fence))
            attempt = self._attempt(attempt_ref.get(transaction=tx), op, claim)
            if (
                attempt["dispatch_state"] != "pending"
                or attempt["execution_name"] is not None
                or attempt["worker_registered"]
                or attempt["execution_stopped_confirmed"]
                or attempt["provider_outcome_pending"]
                or op.provider_outcome_pending
            ):
                raise OperationConflict(
                    "dispatch_started", "Attempt may have reached Cloud Run and needs reconciliation."
                )

            retry = op.attempt_count < self.policy.max_attempts
            status = "queued" if retry else "failed"
            failure_code = None if retry else "attempt_limit"
            message = (
                "Dispatch was not submitted; operation returned to the queue."
                if retry
                else "Worker attempt limit reached."
            )
            updated = replace(
                op,
                status=status,
                lease_expires_at=None,
                failure_code=failure_code,
                message=message,
                updated_at=now,
            )
            tx.update(
                ref,
                {
                    "status": status,
                    "lease_expires_at": None,
                    "failure_code": failure_code,
                    "message": message,
                    "updated_at": now,
                },
            )
            tx.update(
                attempt_ref,
                {
                    "state": "dispatch_interrupted",
                    "dispatch_state": "not_submitted",
                    "ended_at": now,
                    "message": message,
                },
            )
            project_ref = self._project_ref(op.project_id)
            tx.delete(slot_ref)
            tx.delete(project_ref)
            return updated, bound

        return self._run(operation, bind_if_missing=True)
