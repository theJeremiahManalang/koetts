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
            self.assertEqual(store.list_reader("alice")[0]["manga_id"], "738c39fe73bd514480841509f501a0dd")
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

    def test_approved_work_has_one_project_and_relink_changes_its_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "shared.sqlite3"
            store = SharedRequests(database)
            first = store.submit("alice", "Manga", "1", "")
            second = store.submit("bob", "Manga", "2", "")
            with self.assertRaises(ValueError):
                store.link_project(first["work_id"], "project-one", "admin")
            store.approve(first["work_id"], "admin")
            store.approve(second["work_id"], "admin")
            link = store.link_project(first["work_id"], "project-one", "admin")
            self.assertEqual(store.link_project(first["work_id"], "project-one", "admin"), link)
            with self.assertRaises(ValueError):
                store.link_project(second["work_id"], "project-one", "admin")
            replacement = store.link_project(first["work_id"], "project-two", "admin")
            self.assertNotEqual(link["id"], replacement["id"])
            self.assertEqual(SharedRequests(database).get_link(first["work_id"]), replacement)
            self.assertEqual(store.link_project(second["work_id"], "project-one", "admin")["project_id"], "project-one")

    def test_metadata_retry_reuses_candidate_identity_without_recopying_artifacts(self):
        from unittest.mock import patch

        from manga_tts.shared_metadata import SQLiteSharedMetadata
        from manga_tts.shared_requests import ExportSnapshot

        class RetryMetadata:
            def __init__(self, backend):
                self.backend = backend
                self.identities = []

            def run(self, operation):
                class Retry(Exception):
                    pass

                def interrupted(tx):
                    result = operation(tx)
                    self.identities.append(result["id"])
                    raise Retry()

                try:
                    self.backend.run(interrupted)
                except Retry:
                    pass
                result = self.backend.run(operation)
                self.identities.append(result["id"])
                return result

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "shared.sqlite3"
            store = SharedRequests(database)
            work = store.submit("alice", "Manga", "1", "original")
            store.approve(work["work_id"], "admin")
            link = store.link_project(work["work_id"], "project-one", "admin")
            audio = root / "audio.wav"
            audio.write_bytes(b"synthetic audio")
            snapshot = ExportSnapshot(work_id=work["work_id"], link_id=link["id"], project_id="project-one",
                                      revision="revision", export_id="export", settings_hash="settings",
                                      artifacts={"chapter_narration.wav": audio})
            retry = RetryMetadata(SQLiteSharedMetadata(database))
            store.metadata = retry
            with patch.object(store.artifacts, "store", wraps=store.artifacts.store) as copy:
                candidate = store.prepare_audio_review(snapshot, actor="admin")
            self.assertEqual(copy.call_count, 1)
            self.assertEqual(retry.identities, [candidate["id"], candidate["id"]])
            recovered = SharedRequests(database)
            self.assertEqual(recovered.review_state(work["work_id"])["candidate"]["id"], candidate["id"])
            self.assertEqual(recovered.candidate_artifact(candidate["id"], "chapter_narration.wav").read_bytes(), audio.read_bytes())


if __name__ == "__main__":
    unittest.main()
