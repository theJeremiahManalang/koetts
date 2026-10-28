"""Firestore emulator acceptance. Never connect these tests to a live project."""
import os
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from manga_tts.shared_requests import ExportSnapshot, SharedRequests


@unittest.skipUnless(os.environ.get("FIRESTORE_EMULATOR_HOST"), "No Firestore emulator configured")
class FirestoreSharedTests(unittest.TestCase):
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
        self.dataset = "test-" + uuid.uuid4().hex
        self.identity = uuid.uuid4().hex
        self.metadata = FirestoreSharedMetadata(self.client, self.dataset, self.identity)
        self.store = SharedRequests(self.root / "shared.sqlite3", metadata=self.metadata)
        self.addCleanup(self.client.close)

    def linked_snapshot(self):
        request = self.store.submit("alice", "Manga", "1", "original")
        self.store.approve(request["work_id"], "admin")
        link = self.store.link_project(request["work_id"], "project", "admin")
        source = self.root / "audio.wav"
        source.write_bytes(b"synthetic audio")
        return ExportSnapshot(work_id=request["work_id"], link_id=link["id"], project_id="project",
                              revision="revision", export_id="export", settings_hash="settings",
                              artifacts={"chapter_narration.wav": source})

    def test_concurrent_duplicate_requests_retain_original_notes_and_reader_isolation(self):
        def submit(index):
            return self.store.submit("alice", "  Manga ", "01", str(index))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(submit, range(4)))
        self.assertEqual(len({r["id"] for r in results}), 1)
        self.assertEqual(sum(not r["duplicate"] for r in results), 1)
        bob = self.store.submit("bob", "manga", "1", "bob note")
        self.assertEqual(bob["work_id"], results[0]["work_id"])
        self.assertEqual(len(self.store.list_work()), 1)
        with self.assertRaises(ValueError):
            self.store.delete("alice", bob["id"])
        self.store.delete("alice", results[0]["id"])
        self.assertEqual(self.store.list_reader("alice"), [])
        self.assertEqual(len(self.store.list_reader("bob")), 1)
        self.assertFalse((self.root / "shared.sqlite3").exists())

    def test_exact_review_publication_recovery_and_failed_replacement(self):
        snapshot = self.linked_snapshot()
        candidate = self.store.prepare_audio_review(snapshot, actor="admin")
        review = self.store.approve_audio_review(snapshot, candidate_id=candidate["id"], actor="admin")
        published = self.store.publish_review(snapshot, review_id=review["id"], actor="admin", expected_publication=None)
        recovered = SharedRequests(self.root / "shared.sqlite3", metadata=self.metadata)
        self.assertEqual(recovered.list_reader("alice")[0]["status"], "published")
        self.assertEqual(recovered.review_state(snapshot.work_id)["review"]["candidate_id"], candidate["id"])
        self.assertEqual(recovered.catalog()[0]["publication_id"], published["id"])
        original = recovered.published_artifact(snapshot.work_id, "chapter_narration.wav").read_bytes()
        snapshot.artifacts["chapter_narration.wav"].write_bytes(b"changed")
        with self.assertRaises(ValueError):
            recovered.publish_review(snapshot, review_id=review["id"], actor="admin", expected_publication=published["id"])
        self.assertEqual(recovered.published_artifact(snapshot.work_id, "chapter_narration.wav").read_bytes(), original)

    def test_relink_invalidates_review_and_releases_project_uniqueness(self):
        snapshot = self.linked_snapshot()
        candidate = self.store.prepare_audio_review(snapshot, actor="admin")
        self.store.link_project(snapshot.work_id, "new-project", "admin")
        self.assertIsNone(self.store.review_state(snapshot.work_id)["candidate"])
        with self.assertRaises(ValueError):
            self.store.approve_audio_review(snapshot, candidate_id=candidate["id"], actor="admin")
        other = self.store.submit("bob", "Manga", "2", "")
        self.store.approve(other["work_id"], "admin")
        self.store.link_project(other["work_id"], "project", "admin")

    def test_dataset_refuses_another_artifact_store(self):
        from manga_worker.shared_firestore import FirestoreSharedMetadata

        self.store.submit("alice", "Manga", "1", "")
        other = FirestoreSharedMetadata(self.client, self.dataset, uuid.uuid4().hex)
        with self.assertRaises(ValueError):
            other.run(lambda tx: tx.find("chapter_work"))

    def test_competing_publications_have_one_winner(self):
        snapshot = self.linked_snapshot()
        candidate = self.store.prepare_audio_review(snapshot, actor="admin")
        reviews = [self.store.approve_audio_review(snapshot, candidate_id=candidate["id"], actor="admin") for _ in range(2)]

        def publish(review):
            try:
                return self.store.publish_review(snapshot, review_id=review["id"], actor="admin", expected_publication=None)
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(publish, reviews))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(self.store.list_reader("alice")[0]["status"], "published")

    def test_transaction_retry_keeps_candidate_identity_and_copies_artifact_once(self):
        from unittest.mock import patch

        from google.api_core.exceptions import Aborted

        snapshot = self.linked_snapshot()
        backend = self.metadata
        identities = []

        class ObserveAttempts:
            def run(self, operation):
                def attempt(tx):
                    result = operation(tx)
                    identities.append(result["id"])
                    return result
                return backend.run(attempt)

        transaction = self.client.transaction()
        original_commit = transaction._commit
        attempts = []

        def commit():
            attempts.append(True)
            if len(attempts) == 1:
                transaction._rollback()
                raise Aborted("Injected commit conflict")
            return original_commit()

        self.store.metadata = ObserveAttempts()
        with patch.object(self.store.artifacts, "store", wraps=self.store.artifacts.store) as copy, patch.object(
            self.client, "transaction", return_value=transaction
        ), patch.object(transaction, "_commit", side_effect=commit):
            candidate = self.store.prepare_audio_review(snapshot, actor="admin")
        self.assertEqual(copy.call_count, 1)
        self.assertEqual(identities, [candidate["id"], candidate["id"]])
        self.store.metadata = backend
        self.assertEqual(self.store.review_state(snapshot.work_id)["candidate"]["id"], candidate["id"])
