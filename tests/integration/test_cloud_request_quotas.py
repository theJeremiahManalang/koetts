"""Hosted reader quota acceptance against a local Firestore emulator only."""
import os
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from manga_tts.shared_requests import IntakeQuotaExceeded, ReaderIntakePolicy, SharedRequests


@unittest.skipUnless(os.environ.get("FIRESTORE_EMULATOR_HOST"), "No Firestore emulator configured")
class FirestoreReaderQuotaTests(unittest.TestCase):
    def setUp(self):
        from google.cloud import firestore
        from manga_worker.shared_firestore import FirestoreSharedMetadata

        host = os.environ["FIRESTORE_EMULATOR_HOST"]
        if host.split(":")[0] not in {"127.0.0.1", "localhost", "[::1]"}:
            raise ValueError("Firestore tests require a loopback emulator")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.client = firestore.Client(project="demo-shared-workflow", database="shared-tests")
        self.metadata = FirestoreSharedMetadata(
            self.client, "quota-" + uuid.uuid4().hex, uuid.uuid4().hex
        )
        self.store = SharedRequests(
            self.root / "unused.sqlite3", metadata=self.metadata, intake_policy=ReaderIntakePolicy()
        )
        self.addCleanup(self.client.close)

    def test_concurrent_submissions_at_pending_threshold_allow_only_one(self):
        for index in range(1, 5):
            self.store.submit("alice", "Manga", str(index), "")

        def submit(chapter):
            try:
                return self.store.submit("alice", "Manga", str(chapter), "")
            except IntakeQuotaExceeded as error:
                return error

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, (5, 6)))
        created = [result for result in results if isinstance(result, dict)]
        rejected = [result for result in results if isinstance(result, IntakeQuotaExceeded)]
        self.assertEqual(len(created), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].code, "pending_limit")
        self.assertEqual(len(self.store.list_reader("alice")), 5)
        self.assertFalse((self.root / "unused.sqlite3").exists())

    def test_approved_work_request_does_not_consume_pending_capacity(self):
        approved = self.store.submit("admin-reader", "Manga", "1", "")
        self.store.approve(approved["work_id"], "admin")
        request = self.store.submit("alice", "manga", "01", "")
        self.assertEqual(request["status"], "approved")
        for index in range(2, 7):
            self.store.submit("alice", "Manga", str(index), "")
        with self.assertRaises(IntakeQuotaExceeded) as error:
            self.store.submit("alice", "Manga", "7", "")
        self.assertEqual(error.exception.code, "pending_limit")

