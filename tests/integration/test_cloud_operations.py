"""Firestore operation coordination tests; emulator only, never a live project."""

import os
import threading
import time
import unittest
import uuid
from unittest.mock import Mock
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
        from manga_worker.cloud_operations import FirestoreOperationStore

        for round_number in range(3):
            store = self.store if round_number == 0 else FirestoreOperationStore(
                self.client,
                "test-" + uuid.uuid4().hex,
                "gcs-v1:" + uuid.uuid4().hex * 2,
                policy=OperationPolicy(max_attempts=3, stage_capacities={"magi": 1, "pipeline": 1}),
            )

            def submit(_):
                return store.enqueue(
                    idempotency_key="same-key",
                    payload={"action": "extract"},
                    project_id="project",
                    stage="magi",
                    revision="rev",
                    source_fingerprint="source",
                    configuration_fingerprint="config",
                )

            with ThreadPoolExecutor(max_workers=4) as pool:
                operations = list(pool.map(submit, range(4)))
            self.assertEqual(len({op.operation_id for op in operations}), 1)
            self.assertEqual(store.get_by_key("same-key").operation_id, operations[0].operation_id)
            binding = store.root.get().to_dict()
            self.assertEqual(binding, {
                "schema_version": 1,
                "artifact_store_id": store.artifact_store_id,
            })
            self.assertEqual(len(list(store.root.collection("operations").stream())), 1)
            self.assertEqual(len(list(store.root.collection("operation_idempotency_keys").stream())), 1)

        store = FirestoreOperationStore(
            self.client,
            "test-" + uuid.uuid4().hex,
            "gcs-v1:" + uuid.uuid4().hex * 2,
            policy=OperationPolicy(max_attempts=3, stage_capacities={"magi": 1, "pipeline": 1}),
        )
        with ThreadPoolExecutor(max_workers=4) as pool:
            different = list(pool.map(lambda i: store.enqueue(
                idempotency_key=f"fresh-{i}", payload={"action": "extract"}, project_id="project",
                stage="magi", revision="rev", source_fingerprint="source",
                configuration_fingerprint="config",
            ), range(4)))
        self.assertEqual(len({op.operation_id for op in different}), 4)
        self.assertEqual(len(list(store.root.collection("operations").stream())), 4)
        self.assertEqual(len(list(store.root.collection("operation_idempotency_keys").stream())), 4)
        self.assertEqual(store.root.get().to_dict(), {
            "schema_version": 1,
            "artifact_store_id": store.artifact_store_id,
        })

        with self.assertRaises(OperationConflict) as caught:
            store.enqueue(
                idempotency_key="fresh-0", payload={"action": "different"}, project_id="project",
                stage="magi", revision="rev", source_fingerprint="source",
                configuration_fingerprint="config",
            )
        self.assertEqual(caught.exception.code, "idempotency_conflict")

    def test_slash_in_idempotency_key_matches_sqlite_behavior(self):
        operation = self.enqueue("reader/request/42")
        self.assertEqual(self.store.get_by_key("reader/request/42").operation_id, operation.operation_id)
        self.assertEqual(self.enqueue("reader/request/42").operation_id, operation.operation_id)

    def test_reads_reject_operations_under_a_missing_namespace_binding(self):
        operation = self.enqueue("unbound-read")
        self.store.root.delete()

        with self.assertRaisesRegex(ValueError, "without a namespace binding"):
            self.store.get(operation.operation_id)
        with self.assertRaisesRegex(ValueError, "without a namespace binding"):
            self.store.get_by_key("unbound-read")
        self.assertFalse(self.store.root.get().exists)

    def test_exhausted_duplicate_transaction_recovers_only_matching_committed_intent(self):
        from google.api_core.exceptions import Aborted
        from unittest.mock import patch

        original = self.store._run
        injected = False
        def committed_then_ambiguous(callback, *, bind_if_missing=False):
            nonlocal injected
            result = original(callback, bind_if_missing=bind_if_missing)
            if bind_if_missing and not injected:
                injected = True
                raise ValueError("Failed to commit transaction in 5 attempts") from Aborted("Synthetic contention")
            return result
        with patch.object(self.store, "_run", side_effect=committed_then_ambiguous):
            recovered = self.enqueue("ambiguous-duplicate")
        self.assertTrue(injected)
        self.assertEqual(recovered.operation_id, self.store.get_by_key("ambiguous-duplicate").operation_id)
        self.assertEqual(len(list(self.store.root.collection("operations").stream())), 1)
        with self.assertRaises(OperationConflict):
            self.enqueue("ambiguous-duplicate", payload={"action": "changed"})

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
        signals = list(self.store.root.collection("dispatch_signals").stream())
        self.assertEqual(len(signals), 4, "enqueue and capacity release each commit a wake-up signal")
        self.assertTrue(all(signal.to_dict()["stage"] in {"magi", "pipeline"} for signal in signals))
        self.assertEqual(self.store.claim(blocked_stage.operation_id, now=11).fence, 1)

    def test_claim_next_filters_queued_work_by_stage(self):
        magi = self.enqueue("queued-magi", project="magi-project")
        pipeline = self.enqueue("queued-pipeline", project="pipeline-project", stage="pipeline")
        claim = self.store.claim_next(stage="pipeline")
        self.assertEqual(claim.operation_id, pipeline.operation_id)
        self.assertEqual(self.store.get(magi.operation_id).status, "queued")

    def test_watch_public_delivers_initial_and_changed_operation_state(self):
        operation = self.enqueue("status-stream")
        received = []
        changed_condition = threading.Condition()
        def changed(value, version):
            with changed_condition:
                received.append((value, version))
                changed_condition.notify_all()
        def wait_for(predicate):
            with changed_condition:
                self.assertTrue(changed_condition.wait_for(
                    lambda: any(predicate(value) for value, _ in received if value), timeout=5,
                ), f"Firestore listener did not deliver expected state: {received}")
        initial, initial_version, watcher = self.store.watch_public(operation.operation_id, changed)
        self.addCleanup(watcher.unsubscribe)
        self.assertEqual(initial["id"], operation.operation_id)
        self.assertEqual(initial["status"], "queued")
        wait_for(lambda value: value["status"] == "queued")
        claim = self.store.claim(operation.operation_id)
        self.store.heartbeat(claim, progress={"message": "Rendering"})
        wait_for(lambda value: value["message"] == "Rendering")
        self.store.complete(claim, {"segments": ["segment-1"]})
        wait_for(lambda value: value["status"] == "complete")
        terminal = next(value for value, _ in received if value and value["status"] == "complete")
        self.assertEqual(terminal["result"], {"segments": ["segment-1"]})
        self.assertTrue(all(version >= initial_version for _, version in received))

    def test_dispatch_signal_stage_is_validated_and_ttl_bound(self):
        self.enqueue("signal")
        snapshot = next(iter(self.store.root.collection("dispatch_signals").stream()))
        signal = snapshot.to_dict()
        self.assertEqual(signal["stage"], "magi")
        self.assertAlmostEqual(signal["expire_at"].timestamp() - signal["created_at"], 7 * 86400, delta=1)
        self.assertEqual(self.store.dispatch_signal_stage(snapshot.id), "magi")
        self.assertIsNone(self.store.dispatch_signal_stage("f" * 32))

    def test_recovery_repairs_missing_signals_only_for_free_stages_and_is_rate_limited(self):
        self.enqueue("repair-signal")
        now = time.time()
        self.store.budget = Mock(status=Mock(return_value={"configured": True, "paused": True}))
        self.assertEqual(self.store.repair_dispatch_signals(now), 0)
        self.store.budget.status.return_value = {"configured": True, "paused": False}
        self.assertEqual(self.store.repair_dispatch_signals(now), 1)
        self.assertEqual(self.store.repair_dispatch_signals(now + 30), 0)
        self.store._slot_ref("magi", 1).set({"operation_id": "active"})
        self.assertEqual(self.store.repair_dispatch_signals(now + 61), 0)

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

    def test_absent_cloud_run_start_can_be_resolved_only_from_submitting_uncertain_attempt(self):
        operation = self.enqueue("absent-dispatch")
        claim = self.store.claim(operation.operation_id, now=10)
        self.assertTrue(self.store.begin_dispatch(claim))
        self.store.mark_uncertain(claim, "Cloud Run start returned HTTPError")

        resolved = self.store.resolve_dispatch_absent(operation.operation_id, "retry")
        attempt = self.store.attempt(claim)

        self.assertEqual(resolved.status, "queued")
        self.assertEqual(attempt["state"], "operator_retry")
        self.assertEqual(attempt["dispatch_state"], "not_submitted")
        self.assertTrue(attempt["execution_stopped_confirmed"])
        self.assertIsNone(attempt["execution_name"])
        self.assertIsNone(self.store._slot_ref(operation.stage, 1).get().to_dict())

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
