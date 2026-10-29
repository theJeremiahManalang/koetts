"""Hosted revision and artifact-reference acceptance against a local emulator only."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from manga_tts.persistence import ArtifactRef, PersistenceConflict, ProjectRevision


@unittest.skipUnless(os.environ.get("FIRESTORE_EMULATOR_HOST"), "No Firestore emulator configured")
class FirestoreHostedPersistenceTests(unittest.TestCase):
    def setUp(self):
        from google.cloud import firestore

        host = os.environ["FIRESTORE_EMULATOR_HOST"]
        if host.split(":")[0] not in {"127.0.0.1", "localhost", "[::1]"}:
            raise ValueError("Firestore tests require a loopback emulator")
        self.client = firestore.Client(project="demo-hosted-workflow", database="hosted-tests")
        self.addCleanup(self.client.close)
        self.dataset = "test-" + uuid.uuid4().hex
        self.artifact_store_id = "gcs-v1:" + uuid.uuid4().hex + uuid.uuid4().hex
        from manga_worker.cloud_revisions import FirestoreArtifactReferences, FirestoreRevisionStore

        self.revisions = FirestoreRevisionStore(self.client, self.dataset, self.artifact_store_id)
        self.artifacts = FirestoreArtifactReferences(self.client, self.dataset, self.artifact_store_id)
        self.manifest = ArtifactRef("projects/test/manifest.json", "1", "a" * 64)

    def revision(self, revision_id, parent, fence):
        return ProjectRevision(revision_id, parent, self.manifest, "b" * 64, fence)

    def test_shared_publication_survives_complete_scratch_replacement(self):
        from manga_tts.shared_requests import ExportSnapshot, SharedRequests
        from manga_worker.cloud import CloudSettings, cloud_stores
        from tests.unit.worker.test_cloud_artifacts import FakeBucket
        from unittest.mock import Mock

        bucket = FakeBucket()
        storage = Mock()
        storage.bucket.return_value = bucket
        settings = CloudSettings("demo-hosted-workflow", "hosted-tests", self.dataset,
                                 bucket.name, "pilot/artifacts")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stores = cloud_stores(settings, root / "first", firestore_client=self.client, storage_client=storage)
            shared = SharedRequests(root / "unused.sqlite3", metadata=stores.shared_metadata,
                                    artifacts=stores.shared_artifacts)
            request = shared.submit("reader", "Manga", "1", "private note")
            shared.approve(request["work_id"], "admin")
            link = shared.link_project(request["work_id"], "project", "admin")
            source = root / "source.wav"
            source.write_bytes(b"accepted synthetic audio")
            snapshot = ExportSnapshot(work_id=request["work_id"], link_id=link["id"], project_id="project",
                                      revision="revision", export_id="export", settings_hash="settings",
                                      artifacts={"chapter_narration.wav": source})
            candidate = shared.prepare_audio_review(snapshot, actor="admin")
            review = shared.approve_audio_review(snapshot, candidate_id=candidate["id"], actor="admin")
            publication = shared.publish_review(snapshot, review_id=review["id"], actor="admin", expected_publication=None)
            source.unlink()
            shutil.rmtree(root / "first", ignore_errors=True)
            fresh = cloud_stores(settings, root / "second", firestore_client=self.client, storage_client=storage)
            recovered = SharedRequests(root / "other-unused.sqlite3", metadata=fresh.shared_metadata,
                                       artifacts=fresh.shared_artifacts)
            audio = recovered.published_artifact(request["work_id"], "chapter_narration.wav", publication["id"])
            self.assertEqual(audio.read_bytes(), b"accepted synthetic audio")
            self.assertEqual(recovered.list_reader("reader")[0]["status"], "published")
            self.assertEqual(recovered.list_reader("another-reader"), [])
            self.assertFalse((root / "unused.sqlite3").exists())
            self.assertFalse((root / "other-unused.sqlite3").exists())

    def test_competing_owners_stale_release_and_monotonic_fence_after_release(self):
        first = self.revisions.acquire("project", "worker-a")
        with self.assertRaises(PersistenceConflict) as conflict:
            self.revisions.acquire("project", "worker-b")
        self.assertEqual(conflict.exception.code, "writer_conflict")
        stale = type(first)(first.project_id, "worker-other", first.value)
        with self.assertRaises(PersistenceConflict) as conflict:
            self.revisions.release(stale)
        self.assertEqual(conflict.exception.code, "stale_fence")
        self.revisions.release(first)
        second = self.revisions.acquire("project", "worker-b")
        self.assertEqual(second.value, first.value + 1)

    def test_recovery_requires_literal_true_and_preserves_fence_sequence(self):
        first = self.revisions.acquire("project", "worker-a")
        for value in (False, 1, "true", None):
            with self.assertRaises(PersistenceConflict):
                self.revisions.recover(first, value)
        self.revisions.recover(first, True)
        second = self.revisions.acquire("project", "worker-b")
        self.assertEqual(second.value, first.value + 1)

    def test_expected_parent_stale_owner_and_duplicate_revision_are_rejected(self):
        fence = self.revisions.acquire("project", "worker")
        with self.assertRaises(PersistenceConflict) as conflict:
            self.revisions.commit("missing-parent", fence, self.revision("r1", "missing-parent", fence.value))
        self.assertEqual(conflict.exception.code, "revision_conflict")
        revision = self.revision("r1", None, fence.value)
        self.revisions.commit(None, fence, revision)
        self.assertEqual(self.revisions.current("project"), revision)
        with self.assertRaises(PersistenceConflict):
            self.revisions.commit(None, fence, revision)
        self.revisions.release(fence)
        with self.assertRaises(PersistenceConflict) as conflict:
            self.revisions.commit("r1", fence, self.revision("r2", "r1", fence.value))
        self.assertEqual(conflict.exception.code, "stale_fence")

    def test_concurrent_commits_from_same_parent_have_exactly_one_winner(self):
        fence = self.revisions.acquire("project", "worker")

        def commit(revision_id):
            try:
                self.revisions.commit(None, fence, self.revision(revision_id, None, fence.value))
                return revision_id
            except PersistenceConflict:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(commit, ("r1", "r2")))
        self.assertEqual(sum(value is not None for value in outcomes), 1)
        self.assertIn(self.revisions.current("project").revision_id, {"r1", "r2"})

    def test_restart_reads_durable_revision_and_binding_rejects_other_store(self):
        fence = self.revisions.acquire("project", "worker")
        revision = self.revision("r1", None, fence.value)
        self.revisions.commit(None, fence, revision)
        from manga_worker.cloud_revisions import FirestoreRevisionStore

        restarted = FirestoreRevisionStore(self.client, self.dataset, self.artifact_store_id)
        self.assertEqual(restarted.get_revision("project", "r1"), revision)
        self.assertEqual(restarted.current("project"), revision)
        foreign = FirestoreRevisionStore(self.client, self.dataset, "gcs-v1:" + uuid.uuid4().hex + uuid.uuid4().hex)
        with self.assertRaises(ValueError):
            foreign.current("project")
        self.assertEqual(restarted.current("project"), revision)

    def test_artifact_reference_idempotency_conflict_and_restart(self):
        with self.assertRaises(FileNotFoundError):
            self.artifacts.get("c" * 64)
        artifact = ArtifactRef("namespace/" + "c" * 64, "17", "c" * 64)
        self.artifacts.put(artifact)
        self.artifacts.put(artifact)
        self.assertEqual(self.artifacts.get(artifact.sha256), artifact)
        changed_generation = ArtifactRef(artifact.object_id, "18", artifact.sha256)
        with self.assertRaises(ValueError):
            self.artifacts.put(changed_generation)
        from manga_worker.cloud_revisions import FirestoreArtifactReferences

        restarted = FirestoreArtifactReferences(self.client, self.dataset, self.artifact_store_id)
        self.assertEqual(restarted.get(artifact.sha256), artifact)
        foreign = FirestoreArtifactReferences(self.client, self.dataset, "gcs-v1:" + uuid.uuid4().hex + uuid.uuid4().hex)
        with self.assertRaises(ValueError):
            foreign.get(artifact.sha256)

    def test_project_persistence_restores_after_restart_with_injected_gcs(self):
        from manga_tts.persistence import ProjectPersistence
        from manga_tts.storage import write_json
        from manga_worker.cloud_artifacts import GCSArtifactStore
        from tests.unit.engine import test_audio_pipeline as fixtures
        from tests.unit.worker.test_cloud_artifacts import FakeBucket

        fixture = fixtures.PipelineTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            shutil.copytree(fixture.router.root, source)
            (source / "input").mkdir(parents=True, exist_ok=True)
            (source / "input/page.png").write_bytes(b"hosted page")
            state = fixture.router.project.model_dump(mode="json")
            state["title"] = "Cloud restore"
            write_json(source / "project.json", state)
            bucket = FakeBucket()
            artifacts = GCSArtifactStore(bucket, "hosted/projects")
            persistence = ProjectPersistence(artifacts, self.revisions)
            writer = persistence.acquire("restore-project", "writer")
            committed = writer.commit(source, state, expected_revision_id=None)
            writer.release()

            from manga_worker.cloud_revisions import FirestoreRevisionStore

            restarted = ProjectPersistence(
                GCSArtifactStore(bucket, "hosted/projects"),
                FirestoreRevisionStore(self.client, self.dataset, self.artifact_store_id),
            )
            reader = restarted.acquire("restore-project", "reader")
            destination = root / "restored"
            loaded = reader.load(destination)
            self.assertEqual(loaded, committed)
            self.assertEqual((destination / "project.json").read_bytes(), (source / "project.json").read_bytes())
            self.assertEqual((destination / "input/page.png").read_bytes(), (source / "input/page.png").read_bytes())
            reader.release()

    def test_upload_and_pointer_failures_leave_prior_revision_restorable(self):
        from manga_tts.persistence import ProjectPersistence
        from manga_tts.storage import read_json, write_json
        from manga_worker.cloud_artifacts import GCSArtifactStore
        from manga_worker.cloud_revisions import FirestoreRevisionStore
        from tests.unit.engine import test_audio_pipeline as fixtures
        from tests.unit.worker.test_cloud_artifacts import FakeBucket

        fixture = fixtures.PipelineTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            shutil.copytree(fixture.router.root, source)
            (source / "input").mkdir(parents=True, exist_ok=True)
            (source / "input/page.png").write_bytes(b"hosted page")
            original = fixture.router.project.model_dump(mode="json")
            write_json(source / "project.json", original)
            bucket = FakeBucket()
            gcs = GCSArtifactStore(bucket, "hosted/projects")
            first_writer = ProjectPersistence(gcs, self.revisions).acquire("recover-project", "first")
            first = first_writer.commit(source, original, expected_revision_id=None)
            first_writer.release()

            class FailingUploads:
                def __init__(self, delegate):
                    self.delegate = delegate
                    self.fail = False

                def put_file(self, path):
                    if self.fail:
                        self.fail = False
                        raise OSError("injected GCS upload failure")
                    return self.delegate.put_file(path)

                def copy_to(self, artifact, destination):
                    return self.delegate.copy_to(artifact, destination)

            class FailingPointer:
                def __init__(self, delegate):
                    self.delegate = delegate

                def __getattr__(self, name):
                    return getattr(self.delegate, name)

                def commit(self, *args, **kwargs):
                    raise OSError("injected revision pointer failure")

            changed = {**original, "title": "Uncommitted change"}
            upload_store = FailingUploads(gcs)
            upload_store.fail = True
            upload_writer = ProjectPersistence(upload_store, self.revisions).acquire("recover-project", "upload-failure")
            with self.assertRaisesRegex(OSError, "upload failure"):
                upload_writer.commit(source, changed, expected_revision_id=first.revision_id)
            upload_writer.release()

            pointer_writer = ProjectPersistence(gcs, FailingPointer(self.revisions)).acquire(
                "recover-project", "pointer-failure")
            with self.assertRaisesRegex(OSError, "pointer failure"):
                pointer_writer.commit(source, changed, expected_revision_id=first.revision_id)
            pointer_writer.release()

            fresh = ProjectPersistence(
                GCSArtifactStore(bucket, "hosted/projects"),
                FirestoreRevisionStore(self.client, self.dataset, self.artifact_store_id),
            )
            recovery = fresh.acquire("recover-project", "recovery")
            destination = root / "recovered"
            self.assertEqual(recovery.load(destination), first)
            self.assertEqual(read_json(destination / "project.json")["title"], original["title"])
            recovery.release()

    def test_invalid_namespace_and_corrupt_binding_fail_closed(self):
        from manga_worker.cloud_revisions import FirestoreRevisionStore

        with self.assertRaises(ValueError):
            FirestoreRevisionStore(self.client, "../bad", self.artifact_store_id)
        self.revisions.root.set({"schema_version": 999, "artifact_store_id": self.artifact_store_id})
        with self.assertRaises(ValueError):
            self.revisions.acquire("project", "worker")


if __name__ == "__main__":
    unittest.main()
