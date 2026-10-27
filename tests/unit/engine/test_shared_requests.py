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
            store.approve(first["work_id"])
            self.assertEqual(store.list_reader("bob")[0]["status"], "approved")
            store.delete("alice", first["id"])
            self.assertEqual(store.list_reader("alice"), [])
            self.assertEqual(store.list_reader("bob")[0]["status"], "approved")
            with self.assertRaises(ValueError):
                store.delete("alice", second["id"])
            self.assertEqual(SharedRequests(Path(directory) / "shared.sqlite3").list_reader("bob")[0]["id"], second["id"])


if __name__ == "__main__":
    unittest.main()
