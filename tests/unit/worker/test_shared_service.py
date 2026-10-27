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


if __name__ == "__main__":
    unittest.main()
