"""Application service for locally shared chapter requests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from manga_worker import workflow
from manga_worker.shared import SharedService


class SharedServiceTests(unittest.TestCase):
    def test_reader_requests_are_deduplicated_and_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(workflow, "ROOT", root):
                service = SharedService(root)
                alice = service.execute({"action": "submit", "reader": "alice", "title": "Manga", "chapter": "1", "notes": "first"})
                self.assertFalse(alice["duplicate"])
                duplicate = service.execute({"action": "submit", "reader": "alice", "title": "manga", "chapter": "01", "notes": "ignored"})
                self.assertTrue(duplicate["duplicate"])
                self.assertEqual(duplicate["notes"], "first")
                bob = service.execute({"action": "submit", "reader": "bob", "title": "manga", "chapter": "01", "notes": "second"})
                self.assertEqual(alice["work_id"], bob["work_id"])
                self.assertEqual([item["id"] for item in service.execute({"action": "requests", "reader": "alice"})], [alice["id"]])
                with self.assertRaises(ValueError):
                    service.execute({"action": "delete", "reader": "alice", "request_id": bob["id"]})
                service.execute({"action": "approve", "work_id": alice["work_id"], "actor": "admin"})
                admin_work = service.execute({"action": "work"})
                self.assertEqual({r["notes"] for r in admin_work[0]["requests"]}, {"first", "second"})
                self.assertEqual(service.execute({"action": "requests", "reader": "bob"})[0]["status"], "approved")

    def test_invalid_backend_and_incomplete_firestore_config_fail_without_fallback(self):
        import os

        for environment in ({"MANGA_SHARED_BACKEND": "unknown"}, {"MANGA_SHARED_BACKEND": "firestore"}):
            with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, environment, clear=True):
                root = Path(directory)
                with self.assertRaises(ValueError):
                    SharedService(root)
                self.assertFalse((root / "shared.sqlite3").exists())

    def test_artifact_store_identity_survives_restart_and_rejects_corruption(self):
        from manga_worker.shared_firestore import artifact_store_identity

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identity = artifact_store_identity(root)
            self.assertEqual(artifact_store_identity(root), identity)
            (root / ".shared-artifact-store-id").write_text("corrupt")
            with self.assertRaises(ValueError):
                artifact_store_identity(root)

    def test_concurrent_local_binding_publication_is_atomic_and_durable(self):
        from concurrent.futures import ThreadPoolExecutor
        import json
        from manga_worker.shared_local import persist_once

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "binding.json"
            values = [json.dumps({"dataset": str(index), "padding": "x" * 100000}) for index in range(8)]
            def write(value):
                persist_once(target, value)
                return json.loads(target.read_text())["dataset"]
            with ThreadPoolExecutor(max_workers=8) as pool:
                observed = list(pool.map(write, values))
            self.assertEqual(len(set(observed)), 1)
            self.assertIn(target.read_text(), values)
            self.assertEqual([entry.name for entry in target.parent.iterdir()], ["binding.json"])


if __name__ == "__main__":
    unittest.main()
