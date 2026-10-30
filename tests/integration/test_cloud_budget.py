"""Durable cost ledger checks against a loopback Firestore emulator only."""
from __future__ import annotations

import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

from manga_worker.cloud_budget import CloudBudgetExceeded, CloudBudgetLedger


@unittest.skipUnless(os.environ.get("FIRESTORE_EMULATOR_HOST"), "No Firestore emulator configured")
class CloudBudgetLedgerTests(unittest.TestCase):
    def setUp(self):
        from google.cloud import firestore
        host = os.environ["FIRESTORE_EMULATOR_HOST"]
        if host.split(":")[0] not in {"127.0.0.1", "localhost", "[::1]"}:
            raise ValueError("Cloud budget tests require a loopback Firestore emulator")
        self.client = firestore.Client(project="demo-cloud-budget", database="budget-tests")
        self.addCleanup(self.client.close)
        self.dataset = "budget-" + uuid.uuid4().hex
        self.artifact_store_id = "gcs-v1:" + uuid.uuid4().hex + uuid.uuid4().hex
        self.store = CloudBudgetLedger(self.client, self.dataset, self.artifact_store_id)
        from manga_worker.cloud_operations import FirestoreOperationStore
        self.operations = FirestoreOperationStore(self.client, self.dataset, self.artifact_store_id,
                                                  budget=self.store)
        self.stage_caps = {
            "magi": {"infrastructure_micro": 5_000_000, "provider_micro": 2_000_000,
                     "provider_call_micro": 500_000, "max_provider_calls": 4},
            "pipeline": {"infrastructure_micro": 2_000_000, "provider_micro": 1_000_000,
                         "provider_call_micro": 250_000, "max_provider_calls": 4},
        }

    def configure(self, *, allowance=80_000_000, stages=None):
        self.store.configure("operator", "pilot setup", provider_allowance_micro=allowance,
                             stages=stages or self.stage_caps)

    def reserve(self, key, stage="magi"):
        from google.cloud import firestore
        callback = self.store.prepare_reservation(key, stage)

        @firestore.transactional
        def execute(transaction):
            write = callback(transaction)
            write()
        execute(self.client.transaction())

    def _attempt_reservation(self, key, stage="magi"):
        from google.cloud import firestore
        callback = self.store.prepare_reservation(key, stage)

        @firestore.transactional
        def execute(transaction):
            callback(transaction)()
        return execute(self.client.transaction())

    def test_status_is_read_only_and_uninitialized_control_fails_closed(self):
        self.assertFalse(self.store.status()["configured"])
        self.assertFalse(self.store.root.get().exists)
        with self.assertRaises(CloudBudgetExceeded):
            self._attempt_reservation("intent", "magi")

    def test_transaction_callback_returns_deferred_writer_for_safe_composition(self):
        from google.cloud import firestore
        self.configure()
        reserve = self.store.prepare_reservation("intent-one", "magi")

        @firestore.transactional
        def enqueue(transaction):
            write_reservation = reserve(transaction)
            # An existing admission may stage its writes after all reads.
            admission = self.store.root.collection("test").document("admission")
            admission.get(transaction=transaction)
            transaction.set(admission, {"accepted": True})
            write_reservation()

        enqueue(self.client.transaction())

        @firestore.transactional
        def check_claim(transaction):
            return self.store.check_dispatch_in_transaction(transaction, "intent-one")

        self.assertTrue(check_claim(self.client.transaction()))
        self.reserve("intent-one")
        status = self.store.status()
        self.assertEqual(status["infrastructure_reserved_micro"], 5_000_000)
        self.assertEqual(status["provider_reserved_micro"], 2_000_000)

    def test_missing_control_cannot_erase_existing_reservations(self):
        self.configure()
        self.reserve("reserved-intent")
        self.store._control.delete()
        with self.assertRaisesRegex(ValueError, "without their control ledger"):
            self.store.status()
        with self.assertRaisesRegex(ValueError, "without their control ledger"):
            self.store.configure("operator", "attempt reinitialize", provider_allowance_micro=80_000_000,
                                 stages=self.stage_caps)

    def test_concurrent_reservations_cannot_cross_infrastructure_pause_threshold(self):
        self.configure(stages={**self.stage_caps, "magi": {**self.stage_caps["magi"], "infrastructure_micro": 7_500_000}})

        def reserve(index):
            try:
                self.reserve(f"operation-{index}", "magi")
                return "accepted"
            except CloudBudgetExceeded:
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(reserve, (1, 2)))
        self.assertCountEqual(outcomes, ["accepted", "rejected"])
        self.assertEqual(self.store.status()["infrastructure_reserved_micro"], 7_500_000)

    def test_provider_debits_are_idempotent_bounded_and_not_refunded_on_new_interval(self):
        self.configure()
        self.reserve("provider-op", "pipeline")
        amount = self.store.authorize_provider("provider-op", "call-1")
        self.assertEqual(amount, 250_000)
        self.assertEqual(self.store.authorize_provider("provider-op", "call-1"), amount)
        status = self.store.status()
        self.assertEqual(status["provider_used_micro"], amount)
        self.assertEqual(status["provider_reserved_micro"], 750_000)
        self.store.observe_report("2026-10-01", 100, "report-a")
        self.assertEqual(self.store.status()["provider_used_micro"], amount)

    def test_report_highwater_is_order_safe_and_pause_is_latched(self):
        self.configure()
        self.store.observe_report("2026-10-01", 9_000_000, "report-1")
        self.store.observe_report("2026-10-01", 8_000_000, "report-2")
        self.assertEqual(self.store.status()["infrastructure_reported_micro"], 9_000_000)
        self.store.observe_report("2026-10-02", 6_000_000, "report-3")
        self.assertTrue(self.store.status()["paused"])
        self.store.set_paused("operator", "review provider invoice", paused=False)
        self.assertFalse(self.store.status()["paused"])
        self.assertEqual(self.store.status()["infrastructure_reported_micro"], 15_000_000)
        with self.assertRaises(CloudBudgetExceeded):
            self._attempt_reservation("blocked", "magi")

    def test_explicit_reconciliation_can_adjust_ledger_and_is_audited(self):
        self.configure()
        self.reserve("reconcile-op")
        with self.assertRaises(CloudBudgetExceeded):
            self.store.reconcile("operator", "unsafe release", evidence="invoice:unreviewed",
                                 billing_period="2026-10", infrastructure_reported_micro=0,
                                 infrastructure_reserved_micro=0, provider_reserved_micro=0,
                                 provider_used_micro=0)
        self.store.reconcile("operator", "invoice closeout", billing_period="2026-10",
                             infrastructure_reported_micro=0,
                             evidence="billing-export:2026-10",
                             infrastructure_reserved_micro=5_000_000, provider_reserved_micro=2_000_000,
                             provider_used_micro=0)
        self.assertEqual(self.store.status()["infrastructure_reserved_micro"], 5_000_000)
        reported_before = self.store.status()["infrastructure_reported_micro"]
        ignored = self.store.observe_report("2026-10-01", 500, "late-october-report")
        self.assertEqual(ignored, {"ignored": True, "reason": "reconciled_billing_period", "paused": False})
        self.assertEqual(self.store.status()["infrastructure_reported_micro"], reported_before)
        self.store.observe_report("2026-11-01", 500, "november-report")
        events = list(self.store._events.stream())
        self.assertTrue(any(event.to_dict().get("action") == "reconcile" for event in events))

    def test_settlement_checks_run_execution_and_closes_operation_key_forever(self):
        self.configure()
        operation = self.operations.enqueue(
            idempotency_key="settle-me", payload={"action": "extract"}, project_id="settle-project",
            stage="magi", revision="rev", source_fingerprint="source",
            configuration_fingerprint="config")
        claim = self.operations.claim(operation.operation_id, now=100)
        self.operations.record_execution(claim, "projects/demo/locations/test/jobs/magi/executions/one")
        self.operations.register_execution(claim, "projects/demo/locations/test/jobs/magi/executions/one")
        self.operations.complete(claim, {"ok": True})
        statuses = []

        def status(name):
            statuses.append(name)
            return "succeeded"

        settlement = self.store.settle("operator", "terminal closeout", "settle-me",
                                       evidence="execution-check:one", operation_store=self.operations,
                                       execution_status=status)
        self.assertEqual(statuses, ["projects/demo/locations/test/jobs/magi/executions/one"])
        self.assertEqual(settlement["provider_released_micro"], 2_000_000)
        self.assertEqual(self.store.status()["provider_reserved_micro"], 0)
        self.assertEqual(self.store.status()["infrastructure_reserved_micro"], 5_000_000)
        self.assertEqual(self.store.status()["provider_used_micro"], 0)
        self.assertEqual(self.store.inspect("settle-me")["settlement"], settlement)
        with self.assertRaises(CloudBudgetExceeded):
            self.store.settle("operator", "duplicate closeout", "settle-me", evidence="execution-check:one",
                              operation_store=self.operations, execution_status=status)
        with self.assertRaises(CloudBudgetExceeded):
            self.store.authorize_provider("settle-me", "late-provider-call")
        with self.assertRaises(CloudBudgetExceeded):
            self._attempt_reservation("settle-me", "magi")

    def test_settlement_rejects_queued_or_active_or_unknown_execution(self):
        self.configure()
        queued = self.operations.enqueue(
            idempotency_key="queued", payload={"action": "extract"}, project_id="queued-project",
            stage="magi", revision="rev", source_fingerprint="source",
            configuration_fingerprint="config")
        with self.assertRaises(CloudBudgetExceeded):
            self.store.settle("operator", "queue cleanup", "queued", evidence="ticket:1",
                              operation_store=self.operations, execution_status=lambda _: "succeeded")
        active = self.operations.enqueue(
            idempotency_key="active", payload={"action": "extract"}, project_id="active-project",
            stage="pipeline", revision="rev", source_fingerprint="source",
            configuration_fingerprint="config")
        claim = self.operations.claim(active.operation_id, now=100)
        self.operations.record_execution(claim, "projects/demo/locations/test/jobs/pipeline/executions/live")
        self.operations.register_execution(claim, "projects/demo/locations/test/jobs/pipeline/executions/live")
        self.operations.mark_provider_call_pending(claim)
        with self.assertRaises(CloudBudgetExceeded):
            self.store.settle("operator", "uncertain cleanup", "active", evidence="ticket:2",
                              operation_store=self.operations, execution_status=lambda _: "active")

    def test_settlement_races_provider_authorization_without_losing_debits(self):
        self.configure()
        operation = self.operations.enqueue(
            idempotency_key="settle-race", payload={"action": "extract"}, project_id="race-project",
            stage="magi", revision="rev", source_fingerprint="source",
            configuration_fingerprint="config")
        claim = self.operations.claim(operation.operation_id, now=100)
        execution = "projects/demo/locations/test/jobs/magi/executions/race"
        self.operations.record_execution(claim, execution)
        self.operations.register_execution(claim, execution)
        self.operations.complete(claim, {"ok": True})

        def authorize():
            try:
                return ("authorized", self.store.authorize_provider("settle-race", "race-call"))
            except CloudBudgetExceeded:
                return ("closed", None)

        def settle():
            try:
                self.store.settle("operator", "race closeout", "settle-race", evidence="execution-check:race",
                                  operation_store=self.operations,
                                  execution_status=lambda _: "succeeded")
                return "settled"
            except CloudBudgetExceeded:
                # Authorization may commit first, forcing a fresh terminal snapshot.
                return "retry"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda fn: fn(), (authorize, settle)))
        if "retry" in results:
            self.store.settle("operator", "race closeout retry", "settle-race", evidence="execution-check:race",
                              operation_store=self.operations,
                              execution_status=lambda _: "succeeded")
        status = self.store.status()
        self.assertEqual(status["provider_reserved_micro"], 0)
        self.assertIn(status["provider_used_micro"], {0, 500_000})
        self.assertLessEqual(status["provider_reserved_micro"] + status["provider_used_micro"],
                             status["provider_allowance_micro"])
