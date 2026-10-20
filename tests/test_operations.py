"""Durable operation queue contract tests."""
from __future__ import annotations

import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path

from manga_tts.operations import (
    LocalOperationService,
    OperationConflict,
    OperationPolicy,
    OperationStage,
    SQLiteOperationStore,
)


def _claim_in_process(database: str, operation_id: str, barrier, results) -> None:
    barrier.wait(timeout=10)
    claim = SQLiteOperationStore(database).claim(operation_id)
    results.put((operation_id, claim.fence if claim else None))


class SQLiteOperationStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "operations.sqlite3"
        self.store = SQLiteOperationStore(self.database)

    def enqueue(
        self,
        key: str,
        action: str = "rename",
        stage: OperationStage = "pipeline",
    ):
        return self.store.enqueue(
            idempotency_key=key,
            payload={"action": action, "project": "a" * 32, "revision": "r1"},
            project_id="a" * 32,
            stage=stage,
            revision="r1",
            source_fingerprint="source-v1",
            configuration_fingerprint="config-v1",
        )

    def test_same_idempotency_key_and_payload_returns_one_operation(self) -> None:
        first = self.enqueue("submit-1")
        duplicate = self.enqueue("submit-1")

        self.assertEqual(duplicate.operation_id, first.operation_id)
        self.assertEqual(duplicate.request_fingerprint, first.request_fingerprint)

    def test_reusing_idempotency_key_for_changed_payload_conflicts(self) -> None:
        self.enqueue("submit-1")

        with self.assertRaises(OperationConflict) as raised:
            self.enqueue("submit-1", action="export")

        self.assertEqual(raised.exception.code, "idempotency_conflict")

    def test_stage_claim_capacity_and_independent_stages(self) -> None:
        pipeline_a = self.enqueue("pipeline-a")
        pipeline_b = self.enqueue("pipeline-b")
        magi = self.store.enqueue(
            idempotency_key="magi-a",
            payload={"action": "extract", "project": "b" * 32},
            project_id="b" * 32,
            stage="magi",
            revision=None,
            source_fingerprint="images-v1",
            configuration_fingerprint="config-v1",
        )

        claim_a = self.store.claim(pipeline_a.operation_id)
        blocked = self.store.claim(pipeline_b.operation_id)
        magi_claim = self.store.claim(magi.operation_id)

        self.assertIsNotNone(claim_a)
        self.assertIsNone(blocked)
        self.assertIsNotNone(magi_claim)

    def test_claim_next_serializes_one_project_across_stages(self) -> None:
        pipeline = self.enqueue("project-a-pipeline", stage="pipeline")
        same_project_magi = self.enqueue("project-a-magi", action="extract", stage="magi")
        other_project = self.store.enqueue(
            idempotency_key="project-b-magi",
            payload={"action": "extract", "project": "b" * 32},
            project_id="b" * 32,
            stage="magi",
            revision=None,
            source_fingerprint="images-v1",
            configuration_fingerprint="config-v1",
        )

        first = self.store.claim_next()
        second = self.store.claim_next()

        assert first is not None
        assert second is not None
        self.assertEqual(first.operation_id, pipeline.operation_id)
        self.assertEqual(second.operation_id, other_project.operation_id)
        self.assertEqual(self.store.get(same_project_magi.operation_id).status, "queued")

    def test_competing_process_claims_respect_the_single_stage_slot(self) -> None:
        first = self.enqueue("process-a")
        second = self.store.enqueue(
            idempotency_key="process-b",
            payload={"action": "rename", "project": "b" * 32},
            project_id="b" * 32,
            stage="pipeline",
            revision="r1",
            source_fingerprint="source-v1",
            configuration_fingerprint="config-v1",
        )
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(3)
        results = context.Queue()
        processes = [
            context.Process(
                target=_claim_in_process,
                args=(str(self.database), item.operation_id, barrier, results),
            )
            for item in (first, second)
        ]
        for process in processes:
            process.start()
        barrier.wait(timeout=10)
        claims = [results.get(timeout=15) for _ in processes]
        for process in processes:
            process.join(timeout=15)
            self.assertEqual(process.exitcode, 0)

        self.assertEqual(sum(fence is not None for _, fence in claims), 1)

    def test_timed_out_worker_detected_even_when_heartbeat_keeps_lease_fresh(self) -> None:
        operation = self.enqueue("timed-out")
        claim = self.store.claim(operation.operation_id, now=100)
        assert claim is not None
        overdue = self.store.timed_out(now=100 + self.store.policy.attempt_timeout_seconds + 1)

        self.assertEqual([item.operation_id for item in overdue], [operation.operation_id])

    def test_expired_unstarted_dispatch_requeues_without_releasing_attempt_limit(self) -> None:
        operation = self.enqueue("unstarted")
        claim = self.store.claim(operation.operation_id, now=100)
        assert claim is not None

        result = LocalOperationService(self.store).reconcile_expired(now=161)

        self.assertEqual(result[0].status, "queued")
        second = self.store.claim(operation.operation_id, now=162)
        self.assertIsNotNone(second)
        self.assertEqual(self.store.get(operation.operation_id).attempt_count, 2)

    def test_stopped_provider_worker_requires_operator_resolution_and_keeps_slot(self) -> None:
        operation = self.enqueue("provider-unknown")
        claim = self.store.claim(operation.operation_id, now=100)
        assert claim is not None
        self.store.register_worker(claim, 4242, 1.0)
        self.store.mark_provider_call_pending(claim)
        now = time.time() + self.store.policy.lease_seconds + 1

        from unittest.mock import patch
        with patch("manga_tts.operations.process_identity", return_value=False):
            result = LocalOperationService(self.store).reconcile_expired(
                recover_workspace=lambda _: True,
                now=now,
            )

        self.assertEqual(result[0].status, "reconciliation_required")
        self.assertIsNone(self.store.claim(self.enqueue("blocked-provider").operation_id, now=now + 1))
        self.store.resolve_uncertain(operation.operation_id, "fail")
        self.assertEqual(self.store.get(operation.operation_id).status, "failed")

    def test_stale_fence_cannot_complete_newer_attempt(self) -> None:
        operation = self.enqueue("pipeline-a")
        first = self.store.claim(operation.operation_id)
        assert first is not None
        self.store.fail(
            first,
            "Worker stopped before side effects.",
            failure_code="worker_stopped",
            retryable=True,
        )
        second = self.store.claim(operation.operation_id)
        assert second is not None

        with self.assertRaises(OperationConflict) as raised:
            self.store.complete(first, {"old": True})

        self.assertEqual(raised.exception.code, "stale_fence")
        self.store.complete(second, {"new": True})
        self.assertEqual(self.store.get(operation.operation_id).result, {"new": True})

    def test_retry_ceiling_counts_initial_attempt(self) -> None:
        store = SQLiteOperationStore(
            self.database,
            policy=OperationPolicy(max_attempts=2),
        )
        operation = store.enqueue(
            idempotency_key="limited",
            payload={"action": "rename"},
            project_id="b" * 32,
            stage="pipeline",
            revision="r1",
            source_fingerprint="source-v1",
            configuration_fingerprint="config-v1",
        )
        first = store.claim(operation.operation_id)
        assert first is not None
        store.fail(first, "safe", "safe_failure", retryable=True)
        second = store.claim(operation.operation_id)
        assert second is not None
        store.fail(second, "safe", "safe_failure", retryable=True)

        self.assertIsNone(store.claim(operation.operation_id))
        self.assertEqual(store.get(operation.operation_id).status, "failed")

    def test_uncertain_outcome_holds_capacity_until_explicit_resolution(self) -> None:
        operation = self.enqueue("uncertain")
        claim = self.store.claim(operation.operation_id)
        assert claim is not None
        self.store.mark_uncertain(claim, "Provider result unknown.")

        blocked = self.enqueue("blocked")
        self.assertIsNone(self.store.claim(blocked.operation_id))
        self.assertEqual(self.store.get(operation.operation_id).status, "reconciliation_required")

        self.store.resolve_uncertain(operation.operation_id, "fail")
        self.assertEqual(self.store.get(operation.operation_id).status, "failed")
        self.assertIsNotNone(self.store.claim(self.store.get_by_key("blocked").operation_id))


if __name__ == "__main__":
    unittest.main()
