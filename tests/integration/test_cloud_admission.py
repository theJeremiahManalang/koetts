"""Hosted production admission checks against a loopback Firestore emulator only."""
from __future__ import annotations

import os
import hashlib
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from manga_tts.operations import OperationConflict
from manga_worker.cloud_admission import CloudChapterAdmission, ProductionLimitExceeded


@unittest.skipUnless(os.environ.get("FIRESTORE_EMULATOR_HOST"), "No Firestore emulator configured")
class CloudChapterAdmissionTests(unittest.TestCase):
    def setUp(self):
        from google.cloud import firestore
        host = os.environ["FIRESTORE_EMULATOR_HOST"]
        if host.split(":")[0] not in {"127.0.0.1", "localhost", "[::1]"}:
            raise ValueError("Production admission tests require a loopback Firestore emulator")
        self.client = firestore.Client(project="demo-cloud-admission", database="admission-tests")
        self.addCleanup(self.client.close)
        self.artifact_store_id = "gcs-v1:" + uuid.uuid4().hex * 2
        self.dataset = "admission-" + uuid.uuid4().hex
        self.now = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
        self.store = CloudChapterAdmission(
            self.client, self.dataset, self.artifact_store_id, clock=lambda: self.now
        )

    @staticmethod
    def chapter(index):
        return f"{index:032x}"

    def reserve(self, index, key=None, pages=10):
        self.store.reserve(self.chapter(index), key or f"operation-{index}", pages)

    def _month_record(self, month="2026-10"):
        return (self.store.root.collection("production_months").document(month).get().to_dict())

    def test_admission_and_enqueue_commit_together_and_duplicate_does_not_charge(self):
        from manga_worker.cloud_operations import FirestoreOperationStore

        operations = FirestoreOperationStore(self.client, self.dataset, self.artifact_store_id)
        reservation = self.store.prepare(self.chapter(1), "intent/one", 20)
        def interrupted(transaction):
            reservation(transaction)
            raise RuntimeError("Synthetic failure before operation commit")
        arguments = dict(idempotency_key="intent/one", project_id=self.chapter(1), stage="magi",
                         payload={"action": "create"}, revision=None, source_fingerprint="source",
                         configuration_fingerprint="configuration")
        with self.assertRaises(RuntimeError):
            operations.enqueue(**arguments, admission=interrupted)
        self.assertIsNone(self._month_record())
        with self.assertRaises(FileNotFoundError):
            operations.get_by_key("intent/one")
        original = operations.enqueue(**arguments, admission=reservation)
        def unexpected(transaction):
            raise AssertionError("Duplicate operation must not reserve again")
        recovered = operations.enqueue(**arguments, admission=unexpected)
        self.assertEqual(original.operation_id, recovered.operation_id)
        self.assertEqual(self._month_record()["chapter_ids"], [self.chapter(1)])

    def test_rejected_monthly_admission_never_creates_an_operation(self):
        from manga_worker.cloud_operations import FirestoreOperationStore

        for index in range(1, 6):
            self.reserve(index)
        operations = FirestoreOperationStore(self.client, self.dataset, self.artifact_store_id)
        with self.assertRaises(ProductionLimitExceeded):
            operations.enqueue(idempotency_key="sixth-intent", project_id=self.chapter(6), stage="magi",
                               payload={"action": "create"}, revision=None, source_fingerprint="source",
                               configuration_fingerprint="configuration",
                               admission=self.store.prepare(self.chapter(6), "sixth-intent", 40))
        with self.assertRaises(FileNotFoundError):
            operations.get_by_key("sixth-intent")

    def test_five_distinct_chapters_allowed_and_sixth_rejected(self):
        for index in range(1, 6):
            self.reserve(index)
        with self.assertRaises(ProductionLimitExceeded) as caught:
            self.reserve(6)
        self.assertEqual(caught.exception.code, "production_limit")
        self.assertEqual(len(self._month_record()["chapter_ids"]), 5)

    def test_concurrent_last_slot_has_one_winner(self):
        for index in range(1, 5):
            self.reserve(index)

        def submit(index):
            try:
                self.reserve(index)
                return "accepted"
            except ProductionLimitExceeded:
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, (5, 6)))
        self.assertCountEqual(results, ["accepted", "rejected"])
        self.assertEqual(len(self._month_record()["chapter_ids"]), 5)

    def test_matching_duplicate_after_month_rollover_keeps_original_admission(self):
        identity = self.chapter(1)
        self.store.reserve(identity, "stable-key", 12)
        self.now = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
        self.store.reserve(identity, "stable-key", 12)
        ref = self.store._admissions.document(hashlib.sha256(b"stable-key").hexdigest())
        admission = ref.get().to_dict()
        self.assertEqual(admission["month"], "2026-10")
        self.assertFalse(self.store.root.collection("production_months").document("2026-11").get().exists)

    def test_distinct_keys_for_same_chapter_count_once_in_month(self):
        self.store.reserve(self.chapter(1), "first-intent", 8)
        self.store.reserve(self.chapter(1), "second-intent", 8)
        self.assertEqual(self._month_record()["chapter_ids"], [self.chapter(1)])

    def test_invalid_page_counts_fail_before_writes(self):
        for pages in (0, 41, True, 1.5):
            with self.subTest(pages=pages), self.assertRaises(ValueError):
                self.reserve(1, f"invalid-{pages}", pages)
        self.assertFalse(self.store.root.get().exists)

    def test_changed_input_for_existing_key_conflicts(self):
        self.store.reserve(self.chapter(1), "stable-key", 10)
        with self.assertRaises(OperationConflict) as caught:
            self.store.reserve(self.chapter(2), "stable-key", 10)
        self.assertEqual(caught.exception.code, "idempotency_conflict")
        with self.assertRaises(OperationConflict):
            self.store.reserve(self.chapter(1), "stable-key", 11)
        self.assertEqual(self._month_record()["chapter_ids"], [self.chapter(1)])

    def test_namespace_binding_mismatch_fails_closed(self):
        self.reserve(1)
        other = CloudChapterAdmission(
            self.client, self.dataset, "gcs-v1:" + "f" * 64, clock=lambda: self.now
        )
        with self.assertRaisesRegex(ValueError, "different schema or artifact store"):
            other.reserve(self.chapter(2), "other-key", 10)
        self.assertEqual(self._month_record()["chapter_ids"], [self.chapter(1)])
