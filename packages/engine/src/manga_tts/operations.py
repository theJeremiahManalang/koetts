"""Durable local operations and fenced finite worker claims.

SQLite coordinates processes on one host. The adapter stores pinned requests,
attempts, leases, stage slots, checkpoints, and observable results.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, Protocol

import psutil

OperationStatus = Literal[
    "queued", "running", "complete", "failed", "reconciliation_required"
]
OperationStage = Literal["magi", "pipeline"]
ReconciliationAction = Literal["fail", "retry"]


class OperationConflict(RuntimeError):
    """A key, state, or fence precondition failed without changing operation state."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class OperationPolicy:
    """Local stage limits and finite worker timing policy."""

    stage_capacities: Mapping[OperationStage, int] = field(
        default_factory=lambda: {"magi": 1, "pipeline": 1}
    )
    max_attempts: int = 3
    attempt_timeout_seconds: int = 30 * 60
    heartbeat_seconds: int = 15
    lease_seconds: int = 60

    def __post_init__(self) -> None:
        capacities = dict(self.stage_capacities)
        if not capacities or any(not stage or capacity < 1 for stage, capacity in capacities.items()):
            raise ValueError("Stage capacities must be positive")
        if self.max_attempts < 1:
            raise ValueError("At least one worker attempt is required")
        if min(self.attempt_timeout_seconds, self.heartbeat_seconds, self.lease_seconds) < 1:
            raise ValueError("Worker timing values must be positive")
        if self.lease_seconds <= self.heartbeat_seconds:
            raise ValueError("Lease duration must exceed the heartbeat interval")
        object.__setattr__(self, "stage_capacities", capacities)


@dataclass(frozen=True)
class Operation:
    """Persisted request, pinned inputs, latest attempt, and observable outcome."""

    operation_id: str
    idempotency_key: str
    request_fingerprint: str
    project_id: str
    stage: OperationStage
    payload: dict[str, Any]
    revision: str | None
    source_fingerprint: str
    configuration_fingerprint: str
    status: OperationStatus
    attempt_count: int
    fence: int
    lease_expires_at: float | None
    worker_pid: int | None
    worker_created_at: float | None
    provider_outcome_pending: bool
    progress: dict[str, Any]
    checkpoint: dict[str, Any] | None
    result: dict[str, Any] | None
    failure_code: str | None
    message: str
    created_at: float
    updated_at: float
    attempt_started_at: float | None

    def public(self) -> dict[str, Any]:
        """Return the workflow polling shape without internal request parameters."""
        return {
            "id": self.operation_id,
            "project": self.project_id,
            "status": self.status,
            "message": self.message,
            "failure_code": self.failure_code,
            "progress": self.progress,
            "result": self.result,
            "attempt": self.attempt_count,
        }


@dataclass(frozen=True)
class OperationClaim:
    operation_id: str
    fence: int


class OperationStore(Protocol):
    """Shared durable lifecycle. Process and cloud execution identities stay adapter-owned."""

    policy: OperationPolicy

    def enqueue(self, *, idempotency_key: str, payload: Mapping[str, Any], project_id: str,
                stage: OperationStage, revision: str | None, source_fingerprint: str,
                configuration_fingerprint: str, request_fingerprint: str | None = None) -> Operation: ...
    def get(self, operation_id: str) -> Operation: ...
    def get_by_key(self, idempotency_key: str) -> Operation: ...
    def claim(self, operation_id: str, now: float | None = None) -> OperationClaim | None: ...
    def claim_next(self, now: float | None = None) -> OperationClaim | None: ...
    def heartbeat(self, claim: OperationClaim, progress: Mapping[str, Any] | None = None,
                  checkpoint: Mapping[str, Any] | None = None,
                  provider_result_checkpointed: bool = False) -> Operation: ...
    def mark_provider_call_pending(self, claim: OperationClaim) -> Operation: ...
    def complete(self, claim: OperationClaim, result: dict[str, Any]) -> Operation: ...
    def fail(self, claim: OperationClaim, message: str, failure_code: str,
             retryable: bool = False) -> Operation: ...
    def mark_uncertain(self, claim: OperationClaim, message: str) -> Operation: ...
    def expired(self, now: float | None = None) -> list[Operation]: ...
    def timed_out(self, now: float | None = None) -> list[Operation]: ...
    def record_recovery_checkpoint(self, claim: OperationClaim, project_hash: str) -> Operation: ...
    def hold_live_worker(self, claim: OperationClaim, now: float | None = None) -> Operation: ...
    def worker_stopped(self, claim: OperationClaim, now: float | None = None) -> Operation: ...
    def resolve_uncertain(self, operation_id: str, action: ReconciliationAction) -> Operation: ...


class SQLiteOperationStore:
    """SQLite adapter with atomic same-host claims and operation fencing."""

    def __init__(self, database: str | Path, policy: OperationPolicy | None = None):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.policy = policy or OperationPolicy()
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    request_fingerprint TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    revision TEXT,
                    source_fingerprint TEXT NOT NULL,
                    configuration_fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    fence INTEGER NOT NULL DEFAULT 0,
                    lease_expires_at REAL,
                    worker_pid INTEGER,
                    worker_created_at REAL,
                    provider_outcome_pending INTEGER NOT NULL DEFAULT 0,
                    progress_json TEXT NOT NULL DEFAULT '{}',
                    checkpoint_json TEXT,
                    result_json TEXT,
                    failure_code TEXT,
                    message TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operation_attempts (
                    operation_id TEXT NOT NULL REFERENCES operations(operation_id),
                    attempt INTEGER NOT NULL,
                    fence INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL,
                    worker_pid INTEGER,
                    worker_created_at REAL,
                    provider_outcome_pending INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (operation_id, attempt),
                    UNIQUE (operation_id, fence)
                );
                CREATE TABLE IF NOT EXISTS stage_slots (
                    stage TEXT NOT NULL,
                    slot_number INTEGER NOT NULL,
                    operation_id TEXT NOT NULL UNIQUE REFERENCES operations(operation_id),
                    fence INTEGER NOT NULL,
                    PRIMARY KEY (stage, slot_number)
                );
                CREATE INDEX IF NOT EXISTS operations_queue_order
                    ON operations(status, created_at);
                CREATE INDEX IF NOT EXISTS operations_expired_leases
                    ON operations(status, lease_expires_at);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=5.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _transaction(self):
        return _OperationTransaction(self._connect())

    def enqueue(
        self,
        *,
        idempotency_key: str,
        payload: Mapping[str, Any],
        project_id: str,
        stage: OperationStage,
        revision: str | None,
        source_fingerprint: str,
        configuration_fingerprint: str,
        request_fingerprint: str | None = None,
    ) -> Operation:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 200:
            raise ValueError("A valid idempotency key is required")
        if any(ord(character) < 32 for character in idempotency_key):
            raise ValueError("Idempotency key contains control characters")
        if not project_id or stage not in self.policy.stage_capacities:
            raise ValueError("Project and supported operation stage are required")
        payload_json = _canonical_json(dict(payload))
        fingerprint = request_fingerprint or hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        now = time.time()
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT operation_id, request_fingerprint FROM operations WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                if existing["request_fingerprint"] != fingerprint:
                    raise OperationConflict(
                        "idempotency_conflict",
                        "This idempotency key already belongs to a different request.",
                    )
                return self._get(connection, existing["operation_id"])
            operation_id = uuid.uuid4().hex
            connection.execute(
                """INSERT INTO operations (
                    operation_id, idempotency_key, request_fingerprint, project_id, stage,
                    payload_json, revision, source_fingerprint, configuration_fingerprint,
                    status, message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'Waiting for a worker.', ?, ?)""",
                (
                    operation_id,
                    idempotency_key,
                    fingerprint,
                    project_id,
                    stage,
                    payload_json,
                    revision,
                    source_fingerprint,
                    configuration_fingerprint,
                    now,
                    now,
                ),
            )
            return self._get(connection, operation_id)

    def get(self, operation_id: str) -> Operation:
        with closing(self._connect()) as connection:
            return self._get(connection, operation_id)

    def get_by_key(self, idempotency_key: str) -> Operation:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT operation_id FROM operations WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError("Operation was not found")
            return self._get(connection, row["operation_id"])

    def _get(self, connection: sqlite3.Connection, operation_id: str) -> Operation:
        row = connection.execute(
            "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        if row is None:
            raise FileNotFoundError("Operation was not found")
        attempt = connection.execute(
            "SELECT started_at FROM operation_attempts WHERE operation_id = ? AND attempt = ?",
            (operation_id, row["attempt_count"]),
        ).fetchone()
        return Operation(
            operation_id=row["operation_id"],
            idempotency_key=row["idempotency_key"],
            request_fingerprint=row["request_fingerprint"],
            project_id=row["project_id"],
            stage=row["stage"],
            payload=json.loads(row["payload_json"]),
            revision=row["revision"],
            source_fingerprint=row["source_fingerprint"],
            configuration_fingerprint=row["configuration_fingerprint"],
            status=row["status"],
            attempt_count=row["attempt_count"],
            fence=row["fence"],
            lease_expires_at=row["lease_expires_at"],
            worker_pid=row["worker_pid"],
            worker_created_at=row["worker_created_at"],
            provider_outcome_pending=bool(row["provider_outcome_pending"]),
            progress=json.loads(row["progress_json"]),
            checkpoint=json.loads(row["checkpoint_json"]) if row["checkpoint_json"] else None,
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            failure_code=row["failure_code"],
            message=row["message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            attempt_started_at=attempt["started_at"] if attempt else None,
        )

    def claim(self, operation_id: str, now: float | None = None) -> OperationClaim | None:
        now = time.time() if now is None else now
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            if row is None:
                raise FileNotFoundError("Operation was not found")
            if row["status"] != "queued":
                return None
            if row["attempt_count"] >= self.policy.max_attempts:
                self._fail_unclaimed(connection, operation_id, now)
                return None
            if self._project_has_slot(connection, row["project_id"]):
                return None
            slot = self._available_slot(connection, row["stage"])
            if slot is None:
                return None
            return self._claim_locked(connection, row, slot, now)

    def claim_next(self, now: float | None = None) -> OperationClaim | None:
        """Atomically claim the oldest queued operation with an available stage slot."""
        now = time.time() if now is None else now
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT operation_id, project_id, stage FROM operations WHERE status='queued' ORDER BY created_at, operation_id"
            ).fetchall()
            for row in rows:
                if self._project_has_slot(connection, row["project_id"]):
                    continue
                slot = self._available_slot(connection, row["stage"])
                if slot is None:
                    continue
                current = connection.execute(
                    "SELECT * FROM operations WHERE operation_id=?", (row["operation_id"],)
                ).fetchone()
                if current["attempt_count"] >= self.policy.max_attempts:
                    self._fail_unclaimed(connection, row["operation_id"], now)
                    continue
                return self._claim_locked(connection, current, slot, now)
            return None

    def _available_slot(self, connection: sqlite3.Connection, stage: OperationStage) -> int | None:
        capacity = self.policy.stage_capacities[stage]
        occupied = {
            row["slot_number"]
            for row in connection.execute(
                "SELECT slot_number FROM stage_slots WHERE stage = ?", (stage,)
            )
        }
        return next((number for number in range(1, capacity + 1) if number not in occupied), None)

    def _claim_locked(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        slot_number: int,
        now: float,
    ) -> OperationClaim:
        operation_id = row["operation_id"]
        attempt = row["attempt_count"] + 1
        fence = row["fence"] + 1
        connection.execute(
            """UPDATE operations SET status='running', attempt_count=?, fence=?,
                lease_expires_at=?, worker_pid=NULL, worker_created_at=NULL,
                provider_outcome_pending=0, failure_code=NULL, message='Starting worker.', updated_at=?
                WHERE operation_id=? AND status='queued'""",
            (attempt, fence, now + self.policy.lease_seconds, now, operation_id),
        )
        connection.execute(
            """INSERT INTO operation_attempts
                (operation_id, attempt, fence, state, started_at)
                VALUES (?, ?, ?, 'running', ?)""",
            (operation_id, attempt, fence, now),
        )
        connection.execute(
            "INSERT INTO stage_slots(stage, slot_number, operation_id, fence) VALUES (?, ?, ?, ?)",
            (row["stage"], slot_number, operation_id, fence),
        )
        return OperationClaim(operation_id, fence)

    def register_worker(self, claim: OperationClaim, pid: int, created_at: float) -> Operation:
        now = time.time()
        with self._transaction() as connection:
            row = self._active_row(connection, claim)
            if row["worker_pid"] is not None:
                if row["worker_pid"] == pid and row["worker_created_at"] == created_at:
                    return self._get(connection, claim.operation_id)
                raise OperationConflict("duplicate_worker", "Another worker already owns this attempt.")
            connection.execute(
                "UPDATE operations SET worker_pid=?, worker_created_at=?, lease_expires_at=?, updated_at=? WHERE operation_id=?",
                (pid, created_at, now + self.policy.lease_seconds, now, claim.operation_id),
            )
            connection.execute(
                "UPDATE operation_attempts SET worker_pid=?, worker_created_at=? WHERE operation_id=? AND fence=?",
                (pid, created_at, claim.operation_id, claim.fence),
            )
            return self._get(connection, claim.operation_id)

    def heartbeat(
        self,
        claim: OperationClaim,
        progress: Mapping[str, Any] | None = None,
        checkpoint: Mapping[str, Any] | None = None,
        provider_result_checkpointed: bool = False,
    ) -> Operation:
        now = time.time()
        with self._transaction() as connection:
            row = self._active_row(connection, claim)
            operation_id = claim.operation_id
            merged = json.loads(row["progress_json"])
            if progress:
                merged.update(progress)
            checkpoint_json = row["checkpoint_json"]
            if checkpoint is not None:
                checkpoint_json = _canonical_json(dict(checkpoint))
            message = str(merged.get("message", row["message"]))[:400]
            connection.execute(
                """UPDATE operations SET progress_json=?, checkpoint_json=?, message=?,
                    provider_outcome_pending=CASE WHEN ? THEN 0 ELSE provider_outcome_pending END,
                    lease_expires_at=?, updated_at=? WHERE operation_id=?""",
                (
                    _canonical_json(merged),
                    checkpoint_json,
                    message,
                    int(provider_result_checkpointed),
                    now + self.policy.lease_seconds,
                    now,
                    operation_id,
                ),
            )
            if provider_result_checkpointed:
                connection.execute(
                    "UPDATE operation_attempts SET provider_outcome_pending=0 WHERE operation_id=? AND fence=?",
                    (operation_id, claim.fence),
                )
            return self._get(connection, operation_id)

    def mark_provider_call_pending(self, claim: OperationClaim) -> Operation:
        now = time.time()
        with self._transaction() as connection:
            self._active_row(connection, claim)
            connection.execute(
                "UPDATE operations SET provider_outcome_pending=1, updated_at=? WHERE operation_id=?",
                (now, claim.operation_id),
            )
            connection.execute(
                "UPDATE operation_attempts SET provider_outcome_pending=1 WHERE operation_id=? AND fence=?",
                (claim.operation_id, claim.fence),
            )
            return self._get(connection, claim.operation_id)

    def complete(self, claim: OperationClaim, result: dict[str, Any]) -> Operation:
        now = time.time()
        with self._transaction() as connection:
            self._active_row(connection, claim)
            connection.execute(
                """UPDATE operations SET status='complete', result_json=?, failure_code=NULL,
                    lease_expires_at=NULL, message='Ready for review.', updated_at=? WHERE operation_id=?""",
                (_canonical_json(result), now, claim.operation_id),
            )
            connection.execute(
                "UPDATE operation_attempts SET state='complete', ended_at=?, message='Ready for review.' WHERE operation_id=? AND fence=?",
                (now, claim.operation_id, claim.fence),
            )
            connection.execute("DELETE FROM stage_slots WHERE operation_id=? AND fence=?", (claim.operation_id, claim.fence))
            return self._get(connection, claim.operation_id)

    def fail(
        self,
        claim: OperationClaim,
        message: str,
        failure_code: str,
        retryable: bool = False,
    ) -> Operation:
        now = time.time()
        safe_message = message[:400]
        with self._transaction() as connection:
            row = self._active_row(connection, claim)
            operation_id = claim.operation_id
            if row["provider_outcome_pending"]:
                status = "reconciliation_required"
                attempt_state = "uncertain"
                safe_message = "The provider outcome is uncertain. Reconcile before retrying."
                lease_expires_at = None
                release = False
            elif retryable and row["attempt_count"] < self.policy.max_attempts:
                status = "queued"
                attempt_state = "retryable_failure"
                lease_expires_at = None
                release = True
            else:
                status = "failed"
                attempt_state = "failed"
                lease_expires_at = None
                release = True
            connection.execute(
                """UPDATE operations SET status=?, failure_code=?, message=?,
                    lease_expires_at=?, updated_at=? WHERE operation_id=?""",
                (status, failure_code, safe_message, lease_expires_at, now, operation_id),
            )
            connection.execute(
                "UPDATE operation_attempts SET state=?, ended_at=?, message=? WHERE operation_id=? AND fence=?",
                (attempt_state, now, safe_message, operation_id, claim.fence),
            )
            if release:
                connection.execute("DELETE FROM stage_slots WHERE operation_id=? AND fence=?", (operation_id, claim.fence))
            return self._get(connection, operation_id)

    def mark_uncertain(self, claim: OperationClaim, message: str) -> Operation:
        now = time.time()
        safe_message = message[:400]
        with self._transaction() as connection:
            row = self._active_row(connection, claim)
            return self._mark_uncertain_locked(connection, row, now, safe_message)

    def resolve_uncertain(
        self, operation_id: str, action: ReconciliationAction
    ) -> Operation:
        if action not in {"fail", "retry"}:
            raise ValueError("Choose fail or retry")
        now = time.time()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise FileNotFoundError("Operation was not found")
            if row["status"] != "reconciliation_required":
                raise OperationConflict("invalid_transition", "Operation does not need reconciliation.")
            if action == "retry" and row["attempt_count"] >= self.policy.max_attempts:
                raise OperationConflict("retry_limit", "Operation reached its attempt limit.")
            slot = connection.execute(
                "SELECT * FROM stage_slots WHERE operation_id=? AND fence=?",
                (operation_id, row["fence"]),
            ).fetchone()
            if slot is None:
                raise OperationConflict("stale_fence", "Operation no longer owns its stage slot.")
            if action == "fail":
                connection.execute(
                    "UPDATE operations SET status='failed', lease_expires_at=NULL, message='Operator resolved the uncertain operation as failed.', updated_at=? WHERE operation_id=?",
                    (now, operation_id),
                )
                connection.execute(
                    "UPDATE operation_attempts SET state='operator_failed', ended_at=? WHERE operation_id=? AND fence=?",
                    (now, operation_id, row["fence"]),
                )
            else:
                connection.execute(
                    """UPDATE operations SET status='queued', lease_expires_at=NULL,
                        worker_pid=NULL, worker_created_at=NULL, provider_outcome_pending=0,
                         failure_code=NULL,
                        message='Operator requested retry; provider billing may repeat.', updated_at=?
                        WHERE operation_id=?""",
                    (now, operation_id),
                )
                connection.execute(
                    "UPDATE operation_attempts SET state='operator_retry', ended_at=? WHERE operation_id=? AND fence=?",
                    (now, operation_id, row["fence"]),
                )
            connection.execute("DELETE FROM stage_slots WHERE operation_id=?", (operation_id,))
            return self._get(connection, operation_id)

    def expired(self, now: float | None = None) -> list[Operation]:
        now = time.time() if now is None else now
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT operation_id FROM operations WHERE status='running' AND lease_expires_at < ? ORDER BY created_at",
                (now,),
            ).fetchall()
            return [self._get(connection, row["operation_id"]) for row in rows]

    def timed_out(self, now: float | None = None) -> list[Operation]:
        now = time.time() if now is None else now
        cutoff = now - self.policy.attempt_timeout_seconds
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT o.operation_id FROM operations AS o
                    JOIN operation_attempts AS a
                    ON a.operation_id=o.operation_id AND a.fence=o.fence
                    WHERE o.status='running' AND a.started_at <= ? ORDER BY a.started_at""",
                (cutoff,),
            ).fetchall()
            return [self._get(connection, row["operation_id"]) for row in rows]

    def record_recovery_checkpoint(self, claim: OperationClaim, project_hash: str) -> Operation:
        now = time.time()
        with self._transaction() as connection:
            row = self._active_row(connection, claim, allow_uncertain=True)
            if row["payload_json"] and json.loads(row["payload_json"]).get("action") != "render":
                raise OperationConflict("invalid_checkpoint", "Only render operations can resume project checkpoints.")
            checkpoint = json.loads(row["checkpoint_json"]) if row["checkpoint_json"] else {}
            checkpoint.update(project_hash=project_hash, recovered=True)
            connection.execute(
                "UPDATE operations SET checkpoint_json=?, updated_at=? WHERE operation_id=?",
                (_canonical_json(checkpoint), now, claim.operation_id),
            )
            return self._get(connection, claim.operation_id)

    def recover_unstarted(self, claim: OperationClaim, now: float | None = None) -> Operation:
        """Return a dispatched but never-started attempt to the queue after lease expiry."""
        now = time.time() if now is None else now
        with self._transaction() as connection:
            row = self._active_row(connection, claim)
            operation_id = claim.operation_id
            if row["worker_pid"] is not None:
                raise OperationConflict("worker_registered", "Worker identity is already registered.")
            if row["lease_expires_at"] is None or row["lease_expires_at"] >= now:
                raise OperationConflict("lease_active", "Operation lease has not expired.")
            retry = row["attempt_count"] < self.policy.max_attempts
            status = "queued" if retry else "failed"
            message = "Dispatch did not start; operation returned to the queue." if retry else "Worker attempt limit reached."
            connection.execute(
                "UPDATE operations SET status=?, lease_expires_at=NULL, failure_code=?, message=?, updated_at=? WHERE operation_id=?",
                (status, None if retry else "attempt_limit", message, now, operation_id),
            )
            connection.execute(
                "UPDATE operation_attempts SET state='dispatch_interrupted', ended_at=?, message=? WHERE operation_id=? AND fence=?",
                (now, message, operation_id, claim.fence),
            )
            connection.execute("DELETE FROM stage_slots WHERE operation_id=? AND fence=?", (operation_id, claim.fence))
            return self._get(connection, operation_id)

    def worker_stopped(self, claim: OperationClaim, now: float | None = None) -> Operation:
        """Reconcile a confirmed dead process; ambiguous provider calls remain reserved."""
        now = time.time() if now is None else now
        with self._transaction() as connection:
            row = self._active_row(connection, claim)
            operation_id = claim.operation_id
            if row["provider_outcome_pending"]:
                return self._mark_uncertain_locked(
                    connection,
                    row,
                    now,
                    "Worker stopped, but provider outcome is uncertain. Choose fail or retry to release capacity.",
                )
            retry = row["attempt_count"] < self.policy.max_attempts
            status = "queued" if retry else "failed"
            message = "Worker stopped; safe work returned to the queue." if retry else "Worker attempt limit reached."
            connection.execute(
                "UPDATE operations SET status=?, lease_expires_at=NULL, worker_pid=NULL, worker_created_at=NULL, message=?, updated_at=? WHERE operation_id=?",
                (status, message, now, operation_id),
            )
            connection.execute(
                "UPDATE operation_attempts SET state='worker_stopped', ended_at=?, message=? WHERE operation_id=? AND fence=?",
                (now, message, operation_id, claim.fence),
            )
            connection.execute("DELETE FROM stage_slots WHERE operation_id=? AND fence=?", (operation_id, claim.fence))
            return self._get(connection, operation_id)

    def hold_live_worker(self, claim: OperationClaim, now: float | None = None) -> Operation:
        now = time.time() if now is None else now
        with self._transaction() as connection:
            self._active_row(connection, claim)
            connection.execute(
                "UPDATE operations SET lease_expires_at=?, updated_at=? WHERE operation_id=?",
                (now + self.policy.lease_seconds, now, claim.operation_id),
            )
            return self._get(connection, claim.operation_id)

    def _active_row(
        self, connection: sqlite3.Connection, claim: OperationClaim, *, allow_uncertain: bool = False,
    ) -> sqlite3.Row:
        operation_id = claim.operation_id
        row = connection.execute(
            "SELECT * FROM operations WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if row is None:
            raise FileNotFoundError("Operation was not found")
        statuses = {"running", "reconciliation_required"} if allow_uncertain else {"running"}
        if row["status"] not in statuses or row["fence"] != claim.fence:
            raise OperationConflict("stale_fence", "Worker fence is no longer current.")
        slot = connection.execute(
            "SELECT 1 FROM stage_slots WHERE operation_id=? AND fence=?", (operation_id, claim.fence)
        ).fetchone()
        if slot is None:
            raise OperationConflict("stale_fence", "Worker no longer owns its stage slot.")
        return row

    @staticmethod
    def _project_has_slot(connection: sqlite3.Connection, project_id: str) -> bool:
        return connection.execute(
            """SELECT 1 FROM stage_slots AS s JOIN operations AS o
                ON o.operation_id=s.operation_id WHERE o.project_id=? LIMIT 1""",
            (project_id,),
        ).fetchone() is not None

    def _fail_unclaimed(self, connection: sqlite3.Connection, operation_id: str, now: float) -> None:
        connection.execute(
            "UPDATE operations SET status='failed', failure_code='attempt_limit', message='Worker attempt limit reached.', updated_at=? WHERE operation_id=?",
            (now, operation_id),
        )

    def _mark_uncertain_locked(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        now: float,
        message: str,
    ) -> Operation:
        connection.execute(
            """UPDATE operations SET status='reconciliation_required', lease_expires_at=NULL,
                failure_code='execution_uncertain', message=?, updated_at=? WHERE operation_id=?""",
            (message, now, row["operation_id"]),
        )
        connection.execute(
            "UPDATE operation_attempts SET state='uncertain', ended_at=?, message=? WHERE operation_id=? AND fence=?",
            (now, message, row["operation_id"], row["fence"]),
        )
        return self._get(connection, row["operation_id"])


class LocalOperationService:
    """Apply process-identity checks before releasing stale local stage slots."""

    def __init__(self, store: SQLiteOperationStore):
        self.store = store

    def reconcile_expired(
        self,
        recover_workspace: Callable[[Operation], bool] | None = None,
        now: float | None = None,
    ) -> list[Operation]:
        now = time.time() if now is None else now
        reconciled = []
        candidates = {
            operation.operation_id: operation
            for operation in (*self.store.expired(now), *self.store.timed_out(now))
        }
        for operation in candidates.values():
            claim = OperationClaim(operation.operation_id, operation.fence)
            if operation.worker_pid is None or operation.worker_created_at is None:
                reconciled.append(self.store.recover_unstarted(claim, now))
                continue
            identity = process_identity(operation.worker_pid, operation.worker_created_at)
            if identity is True:
                if operation.attempt_started_at and now - operation.attempt_started_at >= self.store.policy.attempt_timeout_seconds:
                    identity = stop_process(operation.worker_pid, operation.worker_created_at)
                    if identity is not False:
                        reconciled.append(
                            self.store.mark_uncertain(
                                claim,
                                "Attempt timed out but the worker could not be confirmed stopped.",
                            )
                        )
                        continue
                else:
                    reconciled.append(self.store.hold_live_worker(claim, now))
                    continue
            if identity is False:
                safe_to_recover = recover_workspace(operation) if recover_workspace else True
                if safe_to_recover:
                    reconciled.append(self.store.worker_stopped(claim, now))
                else:
                    reconciled.append(
                        self.store.mark_uncertain(
                            claim,
                            "Worker stopped, but workspace ownership could not be reconciled safely.",
                        )
                    )
            else:
                reconciled.append(
                    self.store.mark_uncertain(
                        claim,
                        "Worker identity is unknown. Capacity remains reserved until operator reconciliation.",
                    )
                )
        return reconciled


def process_identity(pid: int, created_at: float) -> bool | None:
    """Return true for the same live process, false if stopped/reused, none if unknown."""
    try:
        process = psutil.Process(pid)
        actual_created = process.create_time()
        if abs(actual_created - created_at) > 0.01:
            return False
        return process.is_running()
    except psutil.NoSuchProcess:
        return False
    except (psutil.AccessDenied, OSError):
        return None


def stop_process(pid: int, created_at: float, grace_seconds: float = 10.0) -> bool | None:
    """Stop only the matching process; return whether termination was confirmed."""
    state = process_identity(pid, created_at)
    if state is not True:
        return state
    try:
        process = psutil.Process(pid)
        process.terminate()
        try:
            process.wait(timeout=grace_seconds)
        except psutil.TimeoutExpired:
            if abs(process.create_time() - created_at) > 0.01:
                return False
            process.kill()
            process.wait(timeout=grace_seconds)
        return process_identity(pid, created_at)
    except psutil.NoSuchProcess:
        return False
    except (psutil.AccessDenied, psutil.TimeoutExpired, OSError):
        return None


class _OperationTransaction:
    """Small context manager that makes every state transition a write transaction."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def __enter__(self) -> sqlite3.Connection:
        self.connection.execute("BEGIN IMMEDIATE")
        return self.connection

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
