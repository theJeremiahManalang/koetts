"""Hosted application boundary checks against loopback Firestore and fake GCS."""
from __future__ import annotations

import os
import hashlib
import tempfile
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

from manga_tts import schemas
from manga_tts.operations import OperationConflict
from manga_tts.storage import digest
from manga_tts.schemas import WorkflowError


@unittest.skipUnless(os.environ.get("FIRESTORE_EMULATOR_HOST"), "No Firestore emulator configured")
class CloudApplicationTests(unittest.TestCase):
    def setUp(self):
        from google.cloud import firestore
        host = os.environ["FIRESTORE_EMULATOR_HOST"]
        if host.split(":")[0] not in {"127.0.0.1", "localhost", "[::1]"}:
            raise ValueError("Hosted application tests require loopback Firestore")
        self.client = firestore.Client(project="demo-hosted-application", database="application-tests")
        self.addCleanup(self.client.close)
        self.settings = None

    def _application(self, directory):
        from manga_worker.cloud import CloudSettings
        from manga_worker.cloud_application import CloudApplication
        from tests.unit.worker.test_cloud_artifacts import FakeBucket
        bucket = FakeBucket()
        storage = Mock()
        storage.bucket.return_value = bucket
        settings = CloudSettings("demo-hosted-application", "application-tests", "app-" + uuid.uuid4().hex,
                                 bucket.name, "pilot/app")
        self.settings = settings
        return CloudApplication(settings, firestore_client=self.client, storage_client=storage,
                                cache_root=Path(directory) / "scratch")

    def _seed_exported_project(self, app, root):
        from tests.unit.engine.test_audio_pipeline import PipelineTests
        fixture = PipelineTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.approve()
        fixture.router.render_selected(schemas.RenderCommand(scene_ids=["scene_001"]))
        fixture.router.export_audio(schemas.RenderSelection(scene_ids=["scene_001"]))
        project_id = uuid.uuid4().hex
        with app.stores.persistence.acquire(project_id, "fixture") as writer:
            revision = writer.commit(fixture.router.root, schemas.dump(fixture.router.project), None)
        return project_id, revision

    def test_fresh_scratch_reader_request_review_publication_and_playback(self):
        from manga_worker.cloud_application import CloudApplication
        with tempfile.TemporaryDirectory() as directory:
            app = self._application(directory)
            project_id, revision = self._seed_exported_project(app, Path(directory))
            actor = {"kind": "firebase", "uid": "reader-1", "project_id": self.settings.project}
            request = app.shared({"action": "submit", "reader": "forged-reader", "actor": "forged-actor",
                                  "title": "Synthetic", "chapter": "1", "notes": "private"}, actor)
            self.assertEqual(request["status"], "pending")
            reader_requests = app.shared({"action": "requests", "reader": "forged-reader"}, actor)
            self.assertEqual(reader_requests[0]["notes"], "private")
            self.assertEqual(reader_requests[0]["id"], request["id"])
            admin = {"kind": "firebase", "uid": "admin-1", "project_id": self.settings.project}
            app.shared({"action": "approve", "work_id": request["work_id"]}, admin)
            approved_work = app.shared({"action": "work", "actor": "forged-actor"}, admin)[0]
            self.assertEqual(approved_work["approved_by"], '["demo-hosted-application","admin-1"]')
            link = app.shared({"action": "link", "work_id": request["work_id"], "project_id": project_id}, admin)
            self.assertEqual(link["project_id"], project_id)
            fence_before_stale = app.stores.revisions._project(project_id).get().to_dict()["last_fence"]
            with self.assertRaises(WorkflowError) as stale_prepare:
                app.shared({"action": "prepare", "work_id": request["work_id"], "revision": "0" * 64}, admin)
            self.assertEqual(stale_prepare.exception.detail.code, "revision_conflict")
            self.assertEqual(app.stores.revisions._project(project_id).get().to_dict()["last_fence"], fence_before_stale)
            self.assertIsNone(app.shared({"action": "work"}, admin)[0]["candidate"])
            candidate = app.shared({"action": "prepare", "work_id": request["work_id"],
                                    "revision": revision.project_hash}, admin)
            fence_before_stale = app.stores.revisions._project(project_id).get().to_dict()["last_fence"]
            with self.assertRaises(WorkflowError) as stale_review:
                app.shared({"action": "review", "work_id": request["work_id"], "revision": "0" * 64,
                            "candidate_id": candidate["id"]}, admin)
            self.assertEqual(stale_review.exception.detail.code, "revision_conflict")
            self.assertEqual(app.stores.revisions._project(project_id).get().to_dict()["last_fence"], fence_before_stale)
            self.assertIsNone(app.shared({"action": "work"}, admin)[0]["review"])
            review = app.shared({"action": "review", "work_id": request["work_id"],
                                 "candidate_id": candidate["id"], "revision": revision.project_hash}, admin)
            publication = app.shared({"action": "publish", "work_id": request["work_id"],
                                      "review_id": review["id"], "revision": revision.project_hash,
                                      "expected_publication": None}, admin)
            self.assertEqual(publication["id"], app.shared({"action": "published", "work_id": request["work_id"]}, actor)["publication_id"])
            audio = app.published_path(request["work_id"], publication["id"])
            self.assertGreater(audio.stat().st_size, 0)
            storage = Mock()
            storage.bucket.return_value = app.stores.artifacts.bucket
            fresh = CloudApplication(self.settings, firestore_client=self.client,
                                     storage_client=storage, cache_root=Path(directory) / "fresh")
            self.assertEqual(fresh.snapshot(project_id)["revision"], revision.project_hash)

    def test_upload_manifest_is_owned_immutable_and_operation_pins_current_revision(self):
        from manga_worker.cloud_application import CloudApplication
        from manga_tts.persistence import ArtifactRef
        with tempfile.TemporaryDirectory() as directory:
            app = self._application(directory)
            project_id, revision = self._seed_exported_project(app, Path(directory))
            actor = {"kind": "firebase", "uid": "owner", "project_id": self.settings.project}
            token = uuid.uuid4().hex
            source = Path(directory) / "cast.zip"
            source.write_bytes(b"trusted upload bytes")
            uploaded = app.upload(token, "cast.zip", source, actor)
            self.assertEqual(uploaded["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                app.upload(token, "cast.zip", source, {**actor, "uid": "intruder"})
            changed = Path(directory) / "changed.zip"
            changed.write_bytes(b"other bytes")
            with self.assertRaisesRegex(ValueError, "immutable"):
                app.upload(token, "cast.zip", changed, actor)
            with self.assertRaisesRegex(ValueError, "filename"):
                app.upload(uuid.uuid4().hex, "arbitrary.txt", source, actor)
            empty = Path(directory) / "empty.zip"
            empty.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                app.upload(uuid.uuid4().hex, "cast.zip", empty, actor)
            bad_image = Path(directory) / "bad-image"
            bad_image.write_bytes(b"not an image")
            with self.assertRaisesRegex(ValueError, "valid image"):
                app.upload(uuid.uuid4().hex, "0.png", bad_image, actor)
            payload = {"action": "cast-import", "project": project_id, "revision": revision.project_hash,
                       "project_revision_id": "forged", "upload_token": token, "actor": actor,
                       "cloud_uploads": {"cast.zip": vars(ArtifactRef("evil/path", "1", "f" * 64))},
                       "source_hashes": ["0" * 64]}
            operation = app.enqueue_operation(payload, "idempotency-key")
            self.assertEqual(operation.payload["project_revision_id"], revision.revision_id)
            self.assertEqual(operation.revision, revision.project_hash)
            self.assertEqual(operation.payload["cloud_uploads"]["cast.zip"]["sha256"], uploaded["sha256"])
            self.assertNotEqual(operation.source_fingerprint, digest({"uploads": ["0" * 64], "project_evidence": []}))
            self.assertEqual(app.operation_status(operation.operation_id)["id"], operation.operation_id)
            self.assertEqual(app.list_projects()["projects"][0]["id"], project_id)

            from PIL import Image
            image = Path(directory) / "pixel.png"
            Image.new("RGB", (1, 1), "white").save(image)
            image_token = uuid.uuid4().hex
            app.upload(image_token, "1.png", image, actor)
            app.upload(image_token, "0.png", image, actor)
            create = app.enqueue_operation({"action": "create", "mode": "images", "project": uuid.uuid4().hex,
                                            "upload_token": image_token, "images": ["1.png", "0.png"],
                                            "actor": actor}, "ordered-image-operation")
            self.assertEqual(create.payload["images"], ["0.png", "1.png"])

            wrong_bucket = type(app.stores.artifacts.bucket)()
            wrong_bucket.name = "another-test-bucket"
            wrong_storage = Mock()
            wrong_storage.bucket.return_value = wrong_bucket
            wrong_settings = replace(self.settings, bucket=wrong_bucket.name)
            wrong = CloudApplication(wrong_settings, firestore_client=self.client, storage_client=wrong_storage,
                                    cache_root=Path(directory) / "wrong-bucket")
            with self.assertRaisesRegex(ValueError, "different schema or artifact store"):
                wrong.upload(uuid.uuid4().hex, "cast.zip", source, actor)

    def test_snapshot_rejects_project_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._application(directory)
            project_id, revision = self._seed_exported_project(app, Path(directory))
            app.stores.revisions._revision(project_id, revision.revision_id).update({"project_hash": "0" * 64})
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                app.snapshot(project_id)

    def test_asset_read_downloads_only_the_requested_manifest_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._application(directory)
            project_id, revision = self._seed_exported_project(app, Path(directory))
            manifest = app.stores.persistence.read_manifest(revision.manifest)
            target = manifest.entries["input/page_001.png"].artifact.object_id
            unrelated = {entry.artifact.object_id for path, entry in manifest.entries.items()
                         if path.startswith(("takes/", "exports/", "references/"))}
            bucket = app.stores.artifacts.bucket
            bucket.requests.clear()
            path = app.asset_path(project_id, "input/page_001.png")
            self.assertTrue(path.is_file())
            downloaded = {name for name, generation in bucket.requests if generation is not None}
            self.assertIn(target, downloaded)
            self.assertFalse(downloaded & unrelated)

    def test_stale_enqueue_is_rejected_and_completed_idempotent_retry_returns_original(self):
        from manga_tts.storage import read_json
        with tempfile.TemporaryDirectory() as directory:
            app = self._application(directory)
            project_id, revision = self._seed_exported_project(app, Path(directory))
            actor = {"kind": "firebase", "uid": "admin", "project_id": self.settings.project}
            stale = {"action": "rename", "project": project_id, "revision": "0" * 64,
                     "command": {"title": "stale"}, "actor": actor}
            with self.assertRaises(WorkflowError) as conflict:
                app.enqueue_operation(stale, "stale-key")
            self.assertEqual(conflict.exception.detail.code, "revision_conflict")
            self.assertEqual(app.stores.persistence.current(project_id), revision)
            self.assertIsNone(app.operation_by_key("stale-key"))

            request = {"action": "rename", "project": project_id, "revision": revision.project_hash,
                       "command": {"title": "Renamed"}, "actor": actor}
            first = app.enqueue_operation(request, "rename-key")
            claim = app.operations.claim(first.operation_id)
            self.assertIsNotNone(claim)
            app.operations.complete(claim, {"renamed": True})

            workspace = Path(directory) / "advanced-project"
            with app.stores.persistence.acquire(project_id, "advance") as writer:
                writer.load(workspace)
                data = read_json(workspace / "project.json")
                data["title"] = "Renamed"
                advanced = writer.commit(workspace, data, revision.revision_id)
            self.assertNotEqual(advanced.revision_id, revision.revision_id)
            recovered = app.enqueue_operation(request, "rename-key")
            self.assertEqual(recovered.operation_id, first.operation_id)
            changed = {**request, "command": {"title": "Different intent"}}
            with self.assertRaises(OperationConflict) as idempotency:
                app.enqueue_operation(changed, "rename-key")
            self.assertEqual(idempotency.exception.code, "idempotency_conflict")


if __name__ == "__main__":
    unittest.main()
