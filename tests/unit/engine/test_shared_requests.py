"""Behavior of shared chapter requests."""

import tempfile
import unittest
from pathlib import Path

from manga_tts.shared_requests import SharedRequests


class SharedRequestsTest(unittest.TestCase):
    def test_readers_share_work_but_only_see_their_own_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SharedRequests(Path(directory) / "shared.sqlite3")
            first = store.submit("alice", "  Echoes   of Tomorrow ", "001", "")
            second = store.submit("bob", "echoes of tomorrow", "1", "note")
            self.assertEqual(first["work_id"], second["work_id"])
            self.assertNotEqual(first["id"], second["id"])
            self.assertEqual([item["id"] for item in store.list_reader("alice")], [first["id"]])
            self.assertEqual([item["id"] for item in store.list_reader("bob")], [second["id"]])
            self.assertEqual(store.submit("alice", "echoes of tomorrow", "1", "")["id"], first["id"])
            store.approve(first["work_id"], "administrator")
            self.assertEqual(store.list_reader("bob")[0]["status"], "approved")
            store.delete("alice", first["id"])
            self.assertEqual(store.list_reader("alice"), [])
            self.assertEqual(store.list_reader("bob")[0]["status"], "approved")
            with self.assertRaises(ValueError):
                store.delete("alice", second["id"])
            self.assertEqual(SharedRequests(Path(directory) / "shared.sqlite3").list_reader("bob")[0]["id"], second["id"])

    def test_admin_lists_shared_work_and_approvals_are_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SharedRequests(Path(directory) / "shared.sqlite3")
            work = store.submit("alice", "Manga", "1", "")
            store.submit("bob", "Manga", "1", "")
            self.assertEqual(len(store.list_work()), 1)
            store.approve(work["work_id"], "administrator")
            self.assertEqual(store.list_work()[0]["approved_by"], "administrator")

    def test_admin_sees_each_readers_original_note(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SharedRequests(Path(directory) / "shared.sqlite3")
            first = store.submit("alice", "Manga", "1", "Alice note")
            store.submit("bob", "Manga", "1", "Bob note")
            store.submit("alice", "Manga", "1", "Replacement note")
            self.assertEqual(
                {request["notes"] for request in store.work_requests(first["work_id"])},
                {"Alice note", "Bob note"},
            )


if __name__ == "__main__":
    unittest.main()
