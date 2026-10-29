"""Firestore operation coordination tests; emulator only, never a live project."""

import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

from manga_tts.operations import OperationConflict, OperationPolicy


@unittest.skipUnless(os.environ.get("FIRESTORE_EMULATOR_HOST"), "No Firestore emulator configured")
class FirestoreOperationStoreTests(unittest.TestCase):
    def setUp(self):
        from google.cloud import firestore
        from manga_worker.cloud_operations import FirestoreOperationStore

        host = os.environ["FIRESTORE_EMULATOR_HOST"]
        if host.split(":")[0] not in {"127.0.0.1", "localhost", "[::1]"}:
            raise ValueError("Firestore tests require a loopback emulator")
        self.client = firestore.Client(project="demo-cloud-operations", database="operations-tests")
        self.addCleanup(self.client.close)
        self.store = FirestoreOperationStore(
            self.client,
            "test-" + uuid.uuid4().hex,
            "gcs-v1:" + uuid.uuid4().hex * 2,
            policy=OperationPolicy(max_attempts=3, stage_capacities={"magi": 1, "pipeline": 1}),
        )

    def enqueue(self, key, *, project="project", stage="magi", payload=None):
        return self.store.enqueue(
            idempotency_key=key,
            payload=payload or {"action": "extract"},
            project_id=project,
            stage=stage,
            revision="rev",
            source_fingerprint="source",
            configuration_fingerprint="config",
        )

    def test_same_key_contention_and_changed_input_conflict(self):
        def submit(_):
            return self.enqueue("same-key")

        with ThreadPoolExecutor(max_workers=4) as pool:
            operations = list(pool.map(submit, range(4)))
        self.assertEqual(len({op.operation_id for op in operations}), 1)
        self.assertEqual(self.store.get_by_key("same-key").operation_id, operations[0].operation_id)
        with self.assertRaises(OperationConflict) as caught:
            self.enqueue("same-key", payload={"action": "different"})
        self.assertEqual(caught.exception.code, "idempotency_conflict")

    def test_slash_in_idempotency_key_matches_sqlite_behavior(self):
        operation = self.enqueue("reader/request/42")
        self.assertEqual(self.store.get_by_key("reader/request/42").operation_id, operation.operation_id)
        self.assertEqual(self.enqueue("reader/request/42").operation_id, operation.operation_id)

    def test_stage_and_project_capacity_and_stale_fence(self):
        first = self.enqueue("first", project="p1")
        blocked_stage = self.enqueue("second", project="p2")
        blocked_project = self.enqueue("third", project="p1", stage="pipeline")
        claim = self.store.claim(first.operation_id, now=10)
        self.assertEqual(claim.fence, 1)
        self.assertIsNone(self.store.claim(blocked_stage.operation_id, now=10))
        self.assertIsNone(self.store.claim(blocked_project.operation_id, now=10))
        with self.assertRaises(OperationConflict) as caught:
            self.store.heartbeat(type(claim)(claim.operation_id, claim.fence + 1))
        self.assertEqual(caught.exception.code, "stale_fence")
        self.store.complete(claim, {"ok": True})
        self.assertEqual(self.store.claim(blocked_stage.operation_id, now=11).fence, 1)

    def test_dispatch_attempt_and_duplicate_execution_delivery(self):
        operation = self.enqueue("dispatch")
        claim = self.store.claim(operation.operation_id, now=10)
        self.assertTrue(self.store.begin_dispatch(claim))
        self.assertFalse(self.store.begin_dispatch(claim))
        self.store.record_execution(claim, "jobs/worker/executions/one")
        self.assertEqual(self.store.attempt(claim)["execution_name"], "jobs/worker/executions/one")
        self.store.register_execution(claim, "jobs/worker/executions/one")
        with self.assertRaises(OperationConflict) as caught:
            self.store.register_execution(claim, "jobs/worker/executions/one")
        self.assertEqual(caught.exception.code, "duplicate_worker")

    def test_confirm_stop_requires_nonempty_execution_identity(self):
        operation = self.enqueue("stop-name")
        claim = self.store.claim(operation.operation_id, now=100)
        for execution_name in (None, ""):
            with self.subTest(execution_name=execution_name), self.assertRaises(ValueError):
                self.store.confirm_execution_stopped(claim, execution_name)
        self.assertTrue(self.store._slot_ref(operation.stage, 1).get().exists)

    def test_failure_and_uncertain_provider_hold_capacity_until_confirmed_stop(self):
        operation = self.enqueue("uncertain")
        claim = self.store.claim(operation.operation_id, now=10)
        self.store.record_execution(claim, "jobs/worker/executions/uncertain")
        self.store.register_execution(claim, "jobs/worker/executions/uncertain")
        self.store.mark_provider_call_pending(claim)
        failed = self.store.fail(claim, "provider failed", "provider_error", retryable=True)
        self.assertEqual(failed.status, "reconciliation_required")
        blocked = self.enqueue("other")
        self.assertIsNone(self.store.claim(blocked.operation_id, now=20))
        with self.assertRaises(OperationConflict):
            self.store.worker_stopped(claim, now=20)
        self.store.confirm_execution_stopped(claim, "jobs/worker/executions/uncertain")
        held = self.store.worker_stopped(claim, now=20)
        self.assertEqual(held.status, "reconciliation_required")
        self.assertEqual(self.store.resolve_uncertain(operation.operation_id, "retry").status, "queued")
        self.assertEqual(self.store.claim(blocked.operation_id, now=21).fence, 1)
        failed_attempt = self.store.get(operation.operation_id)
        self.assertEqual(failed_attempt.fence, claim.fence)

    def test_confirmed_uncertain_retry_preserves_attempt_limit(self):
        operation = self.enqueue("retry")
        for expected_fence in range(1, 4):
            claim = self.store.claim(operation.operation_id, now=expected_fence * 100)
            self.assertEqual(claim.fence, expected_fence)
            name = f"jobs/worker/executions/{expected_fence}"
            self.store.record_execution(claim, name)
            self.store.register_execution(claim, name)
            self.store.mark_provider_call_pending(claim)
            self.store.mark_uncertain(claim, "lost outcome")
            with self.assertRaises(OperationConflict):
                self.store.resolve_uncertain(operation.operation_id, "retry")
            self.store.confirm_execution_stopped(claim, name)
            if expected_fence < 3:
                self.assertEqual(self.store.resolve_uncertain(operation.operation_id, "retry").status, "queued")
            else:
                with self.assertRaises(OperationConflict) as caught:
                    self.store.resolve_uncertain(operation.operation_id, "retry")
                self.assertEqual(caught.exception.code, "retry_limit")
                self.assertEqual(self.store.resolve_uncertain(operation.operation_id, "fail").status, "failed")

    def test_payload_is_bounded_before_enqueue(self):
        with self.assertRaises(ValueError):
            self.enqueue("large", payload={"data": "x" * (710 * 1024)})
        self.assertEqual(list(self.store._operations.stream()), [])

    def test_corrupt_boolean_fences_and_missing_attempt_fail_closed(self):
        operation = self.enqueue("corrupt-operation")
        self.store.claim(operation.operation_id, now=10)
        self.store._operation_ref(operation.operation_id).update({"fence": True})
        with self.assertRaisesRegex(ValueError, "Corrupt hosted operation"):
            self.store.get(operation.operation_id)

        operation = self.enqueue("corrupt-attempt", stage="pipeline", project="project-2")
        claim = self.store.claim(operation.operation_id, now=10)
        with self.assertRaises(OperationConflict):
            self.store.heartbeat(type(claim)(claim.operation_id, True))
        attempt_ref = (
            self.store._operation_ref(operation.operation_id).collection("attempts").document(str(claim.fence))
        )
        attempt_ref.update({"fence": True})
        with self.assertRaisesRegex(ValueError, "Corrupt hosted operation attempt"):
            self.store.attempt(claim)
        attempt_ref.delete()
        with self.assertRaises(OperationConflict):
            self.store.heartbeat(claim)

    def test_malformed_operation_payload_status_counter_and_timestamp_fail_closed(self):
        corruptions = (
            {"payload": {"bad": float("nan")}},
            {"status": "unknown-state"},
            {"attempt_count": True},
            {"updated_at": float("nan")},
            {"unexpected_field": True},
        )
        for index, corruption in enumerate(corruptions):
            operation = self.enqueue(f"corrupt-field-{index}")
            self.store._operation_ref(operation.operation_id).update(corruption)
            with self.subTest(corruption=corruption), self.assertRaisesRegex(ValueError, "Corrupt hosted operation"):
                self.store.get(operation.operation_id)

    def test_release_requires_exact_project_slot_identity(self):
        operation = self.enqueue("corrupt-slot")
        claim = self.store.claim(operation.operation_id, now=10)
        project_ref = self.store._project_ref(operation.project_id)
        project_ref.update({"operation_id": "different-operation"})
        with self.assertRaises(OperationConflict):
            self.store.complete(claim, {"ok": True})
        self.assertTrue(project_ref.get().exists)
        self.assertTrue(self.store._slot_ref(operation.stage, 1).get().exists)
        project_ref.update({"operation_id": operation.operation_id})
        self.store._slot_ref(operation.stage, 1).update({"operation_id": "different-operation"})
        with self.assertRaises(OperationConflict):
            self.store.complete(claim, {"ok": True})
        self.assertTrue(self.store._slot_ref(operation.stage, 1).get().exists)
        self.store._slot_ref(operation.stage, 1).update({"operation_id": operation.operation_id})
        project_ref.update({"fence": True})
        with self.assertRaises(OperationConflict):
            self.store.complete(claim, {"ok": True})
        project_ref.update({"fence": claim.fence})
        self.store._slot_ref(operation.stage, 1).update({"fence": True})
        with self.assertRaises(OperationConflict):
            self.store.complete(claim, {"ok": True})

    def test_reconciliation_candidates_hold_and_reconcile_uncertain_execution(self):
        operation = self.enqueue("dispatch-uncertain")
        claim = self.store.claim(operation.operation_id, now=10)
        self.store.mark_uncertain(claim, "dispatch response lost")
        self.assertEqual([op.operation_id for op in self.store.reconciliation_required()], [operation.operation_id])
        self.store.record_execution(claim, "jobs/worker/executions/discovered")
        held = self.store.hold_live_worker(claim, now=20)
        self.assertEqual(held.status, "reconciliation_required")
        self.assertIsNone(held.lease_expires_at)
        self.store.confirm_execution_stopped(claim, "jobs/worker/executions/discovered")
        self.assertEqual(self.store.worker_stopped(claim, now=21).status, "queued")

    def test_unsubmitted_recovery_requires_expiry_and_caps_total_attempts(self):
        operation = self.enqueue("unsubmitted")
        for attempt_number in range(1, 4):
            claim_time = attempt_number * 100
            claim = self.store.claim(operation.operation_id, now=claim_time)
            self.assertEqual(claim.fence, attempt_number)
            with self.assertRaises(OperationConflict) as caught:
                self.store.recover_unsubmitted(claim, now=claim_time + 60)
            self.assertEqual(caught.exception.code, "lease_active")
            recovered = self.store.recover_unsubmitted(claim, now=claim_time + 61)
            expected_status = "queued" if attempt_number < 3 else "failed"
            self.assertEqual(recovered.status, expected_status)
            attempt = self.store.attempt(claim)
            self.assertEqual(attempt["dispatch_state"], "not_submitted")
            self.assertEqual(attempt["state"], "dispatch_interrupted")
        self.assertFalse(self.store._project_ref(operation.project_id).get().exists)
        self.assertFalse(self.store._slot_ref(operation.stage, 1).get().exists)

    def test_unsubmitted_recovery_races_dispatch_with_one_winner(self):
        operation = self.enqueue("dispatch-recovery-race")
        claim = self.store.claim(operation.operation_id, now=100)

        def begin():
            try:
                return ("begin", self.store.begin_dispatch(claim))
            except OperationConflict:
                return ("begin_conflict", False)

        def recover():
            try:
                return ("recover", self.store.recover_unsubmitted(claim, now=161).status)
            except OperationConflict:
                return ("recover_conflict", False)

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda callback: callback(), (begin, recover)))
        labels = {label for label, _ in outcomes}
        self.assertTrue(
            ("begin", "recover_conflict") == tuple(sorted(labels))
            or ("begin_conflict", "recover") == tuple(sorted(labels))
        )
        if "begin" in labels:
            self.assertEqual(self.store.attempt(claim)["dispatch_state"], "submitting")
            self.assertEqual(self.store.get(operation.operation_id).status, "running")
        else:
            self.assertEqual(self.store.attempt(claim)["dispatch_state"], "not_submitted")
            self.assertEqual(self.store.get(operation.operation_id).status, "queued")

    def test_reconcile_checkpoint_requires_stop_and_preserves_provider_uncertainty(self):
        operation = self.enqueue("checkpoint-reconcile", payload={"action": "render"})
        claim = self.store.claim(operation.operation_id, now=10)
        self.store.record_execution(claim, "jobs/worker/executions/checkpoint")
        self.store.mark_provider_call_pending(claim)
        self.store.mark_uncertain(claim, "lost worker result")
        with self.assertRaises(OperationConflict):
            self.store.reconcile_checkpoint(claim, {"project_hash": "hash-before-stop"})
        self.store.confirm_execution_stopped(claim, "jobs/worker/executions/checkpoint")
        updated = self.store.reconcile_checkpoint(claim, {"project_hash": "accepted-hash", "revision_id": "rev-2"})
        self.assertEqual(updated.checkpoint["revision_id"], "rev-2")
        self.assertTrue(updated.provider_outcome_pending)


if __name__ == "__main__":
    unittest.main()
