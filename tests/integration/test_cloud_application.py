"""Hosted application boundary checks against loopback Firestore and fake GCS."""
from __future__ import annotations

import os
import hashlib
import json
import tempfile
import unittest
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
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
        app = CloudApplication(settings, firestore_client=self.client, storage_client=storage,
                               cache_root=Path(directory) / "scratch")
        app.budget.configure("fixture-developer", "synthetic acceptance caps",
                             provider_allowance_micro=80_000_000, stages={
                                 stage: {"infrastructure_micro": 1000, "provider_micro": 1000,
                                         "provider_call_micro": 100, "max_provider_calls": 10}
                                 for stage in ("magi", "pipeline")
                             })
        return app

    def _approved_work(self, app, actor, *, title=None, chapter="1"):
        request = app.shared({"action": "submit", "title": title or uuid.uuid4().hex,
                              "chapter": chapter, "notes": "fixture"}, actor)
        app.shared({"action": "approve", "work_id": request["work_id"]}, actor)
        return request["work_id"]

    def _image_upload(self, app, directory, actor, count=1):
        from PIL import Image
        token = uuid.uuid4().hex
        image = Path(directory) / f"page-{uuid.uuid4().hex}.png"
        Image.new("RGB", (1, 1), "white").save(image)
        for index in range(count):
            app.upload(token, f"{index}.png", image, actor)
        return token

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
            link = app.shared({"action": "link", "work_id": request["work_id"], "project_id": project_id,
                               "revision": revision.project_hash}, admin)
            self.assertEqual(link["project_id"], project_id)
            ownership = app.stores.revisions._project(project_id).get().to_dict()
            fence_before_stale = ownership["last_fence"]
            with self.assertRaises(WorkflowError) as stale_prepare:
                app.shared({"action": "prepare", "work_id": request["work_id"], "revision": "0" * 64}, admin)
            self.assertEqual(stale_prepare.exception.detail.code, "revision_conflict")
            self.assertEqual(app.stores.revisions._project(project_id).get().to_dict()["last_fence"], fence_before_stale)
            self.assertIsNone(app.shared({"action": "work"}, admin)[0]["candidate"])
            candidate = app.shared({"action": "prepare", "work_id": request["work_id"],
                                    "revision": revision.project_hash}, admin)
            self.assertEqual(app.stores.revisions._project(project_id).get().to_dict(), ownership)
            fence_before_stale = app.stores.revisions._project(project_id).get().to_dict()["last_fence"]
            with self.assertRaises(WorkflowError) as stale_review:
                app.shared({"action": "review", "work_id": request["work_id"], "revision": "0" * 64,
                            "candidate_id": candidate["id"]}, admin)
            self.assertEqual(stale_review.exception.detail.code, "revision_conflict")
            self.assertEqual(app.stores.revisions._project(project_id).get().to_dict()["last_fence"], fence_before_stale)
            self.assertIsNone(app.shared({"action": "work"}, admin)[0]["review"])
            review = app.shared({"action": "review", "work_id": request["work_id"],
                                 "candidate_id": candidate["id"], "revision": revision.project_hash}, admin)
            self.assertEqual(app.stores.revisions._project(project_id).get().to_dict(), ownership)
            publication = app.shared({"action": "publish", "work_id": request["work_id"],
                                      "review_id": review["id"], "revision": revision.project_hash,
                                      "expected_publication": None}, admin)
            self.assertEqual(publication["id"], app.shared({"action": "published", "work_id": request["work_id"]}, actor)["publication_id"])
            self.assertEqual(app.stores.revisions._project(project_id).get().to_dict(), ownership)
            app.budget.set_paused("fixture-admin", "verify published playback during pause", paused=True)
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
            work_id = self._approved_work(app, actor)
            create = app.enqueue_operation({"action": "create", "mode": "images", "project": uuid.uuid4().hex,
                                            "upload_token": image_token, "images": ["1.png", "0.png"],
                                            "work_id": work_id, "actor": actor}, "ordered-image-operation")
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

    def test_shared_review_flow_preserves_active_worker_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._application(directory)
            project_id, revision = self._seed_exported_project(app, Path(directory))
            admin = {"kind": "firebase", "uid": "admin", "project_id": self.settings.project}
            request = app.shared({"action": "submit", "title": "Active writer", "chapter": "1", "notes": ""}, admin)
            app.shared({"action": "approve", "work_id": request["work_id"]}, admin)
            app.shared({"action": "link", "work_id": request["work_id"], "project_id": project_id,
                        "revision": revision.project_hash}, admin)

            with app.stores.persistence.acquire(project_id, "active-finite-job"):
                project_ref = app.stores.revisions._project(project_id)
                ownership = project_ref.get().to_dict()
                self.assertEqual(ownership["owner_id"], "active-finite-job")
                candidate = app.shared({"action": "prepare", "work_id": request["work_id"],
                                        "revision": revision.project_hash}, admin)
                review = app.shared({"action": "review", "work_id": request["work_id"],
                                     "candidate_id": candidate["id"], "revision": revision.project_hash}, admin)
                app.shared({"action": "publish", "work_id": request["work_id"], "review_id": review["id"],
                            "revision": revision.project_hash, "expected_publication": None}, admin)
                self.assertEqual(project_ref.get().to_dict(), ownership)

    def test_project_pointer_race_rejects_candidate_write(self):
        from manga_worker.shared_firestore import FirestoreSharedMetadata

        with tempfile.TemporaryDirectory() as directory:
            app = self._application(directory)
            project_id, revision = self._seed_exported_project(app, Path(directory))
            admin = {"kind": "firebase", "uid": "admin", "project_id": self.settings.project}
            request = app.shared({"action": "submit", "title": "Pointer race", "chapter": "1", "notes": ""}, admin)
            app.shared({"action": "approve", "work_id": request["work_id"]}, admin)
            app.shared({"action": "link", "work_id": request["work_id"], "project_id": project_id,
                        "revision": revision.project_hash}, admin)

            original_run = FirestoreSharedMetadata.run
            advanced = False

            def race_before_transaction(metadata, operation):
                nonlocal advanced
                if metadata.project_guard is not None and not advanced:
                    advanced = True
                    workspace = Path(directory) / "advanced"
                    with app.stores.persistence.acquire(project_id, "concurrent-commit") as writer:
                        writer.load(workspace)
                        from manga_tts.storage import read_json
                        state = read_json(workspace / "project.json")
                        state["title"] = "Advanced during review"
                        writer.commit(workspace, state, revision.revision_id)
                return original_run(metadata, operation)

            with unittest.mock.patch.object(FirestoreSharedMetadata, "run", race_before_transaction):
                with self.assertRaises(OperationConflict) as conflict:
                    app.shared({"action": "prepare", "work_id": request["work_id"],
                                "revision": revision.project_hash}, admin)
            self.assertEqual(conflict.exception.code, "revision_conflict")
            self.assertTrue(advanced)
            self.assertIsNone(app.shared({"action": "work"}, admin)[0]["candidate"])

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

    def test_pause_blocks_new_enqueue_and_claim_but_keeps_duplicate_intent_and_requests(self):
        from manga_worker.cloud_budget import CloudBudgetExceeded

        with tempfile.TemporaryDirectory() as directory:
            app = self._application(directory)
            actor = {"kind": "firebase", "uid": "creator", "project_id": self.settings.project}
            work = self._approved_work(app, actor)
            token = self._image_upload(app, directory, actor)
            payload = {"action": "create", "mode": "images", "project": uuid.uuid4().hex,
                       "upload_token": token, "actor": actor, "work_id": work}
            queued = app.enqueue_operation(payload, "budget-intent")
            reserved = app.budget.status()["infrastructure_reserved_micro"]
            app.budget.set_paused("fixture-admin", "pause acceptance", paused=True)
            self.assertEqual(app.enqueue_operation(payload, "budget-intent").operation_id, queued.operation_id)
            self.assertIsNone(app.operations.claim(queued.operation_id))
            self.assertEqual(app.operations.get(queued.operation_id).attempt_count, 0)
            with self.assertRaises(CloudBudgetExceeded):
                app.enqueue_operation({**payload, "project": uuid.uuid4().hex}, "blocked-new-intent")
            self.assertEqual(app.budget.status()["infrastructure_reserved_micro"], reserved)
            with self.assertRaises(FileNotFoundError):
                app.operations.get_by_key("blocked-new-intent")
            request = app.shared({"action": "submit", "title": uuid.uuid4().hex,
                                  "chapter": "2", "notes": "still available"}, actor)
            self.assertEqual(request["status"], "pending")

    def test_create_requires_real_approved_work_and_rechecks_current_status(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._application(directory)
            actor = {"kind": "firebase", "uid": "creator", "project_id": self.settings.project}
            token = self._image_upload(app, directory, actor)
            base = {"action": "create", "mode": "images", "project": uuid.uuid4().hex,
                    "upload_token": token, "actor": actor}
            for key, payload in (("missing-work", base), ("null-work", {**base, "work_id": None}),
                                 ("fake-work", {**base, "work_id": "a" * 32})):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    app.enqueue_operation(payload, key)
                with self.assertRaises(FileNotFoundError):
                    app.operations.get_by_key(key)
            pending = app.shared({"action": "submit", "title": uuid.uuid4().hex,
                                  "chapter": "1", "notes": ""}, actor)["work_id"]
            with self.assertRaisesRegex(ValueError, "Approved shared chapter"):
                app.enqueue_operation({**base, "work_id": pending}, "pending-work")
            for collection in ("production_months", "production_admissions"):
                self.assertEqual(list(app.admission.root.collection(collection).limit(1).stream()), [])

            approved = self._approved_work(app, actor)
            app.client.collection("shared_workflow_v1").document(self.settings.dataset).collection(
                "chapter_work").document(approved).update({"status": "pending"})
            accepted = {**base, "work_id": approved}
            with self.assertRaisesRegex(ValueError, "Approved shared chapter"):
                app.enqueue_operation(accepted, "approval-race")
            with self.assertRaises(FileNotFoundError):
                app.operations.get_by_key("approval-race")
            self.assertEqual(list(app.admission.root.collection("production_months").limit(1).stream()), [])

    def test_monthly_quota_counts_distinct_work_once_and_rejects_sixth_operation(self):
        from manga_worker.cloud_admission import ProductionLimitExceeded
        with tempfile.TemporaryDirectory() as directory:
            app = self._application(directory)
            actor = {"kind": "firebase", "uid": "creator", "project_id": self.settings.project}
            work_ids = []
            for index in range(1, 6):
                work_id = self._approved_work(app, actor, title=f"Monthly {index}")
                work_ids.append(work_id)
                token = self._image_upload(app, directory, actor)
                app.enqueue_operation({"action": "create", "mode": "images", "project": uuid.uuid4().hex,
                                       "upload_token": token, "work_id": work_id, "actor": actor}, f"monthly-{index}")
            sixth = self._approved_work(app, actor, title="Monthly 6")
            token = self._image_upload(app, directory, actor)
            payload = {"action": "create", "mode": "images", "project": uuid.uuid4().hex,
                       "upload_token": token, "work_id": sixth, "actor": actor}
            with self.assertRaises(ProductionLimitExceeded):
                app.enqueue_operation(payload, "monthly-6")
            with self.assertRaises(FileNotFoundError):
                app.operations.get_by_key("monthly-6")
            # A different project and intent still represent the same chapter.
            token = self._image_upload(app, directory, actor)
            app.enqueue_operation({"action": "create", "mode": "images", "project": uuid.uuid4().hex,
                                   "upload_token": token, "work_id": work_ids[0], "actor": actor}, "same-work-new-project")
            month = app.admission._month(app.admission.clock())
            chapters = app.admission.root.collection("production_months").document(month).get().to_dict()["chapter_ids"]
            self.assertEqual(set(chapters), set(work_ids))

    def test_lost_response_retry_keeps_original_admission_after_work_status_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._application(directory)
            actor = {"kind": "firebase", "uid": "creator", "project_id": self.settings.project}
            work_id = self._approved_work(app, actor)
            token = self._image_upload(app, directory, actor)
            payload = {"action": "create", "mode": "images", "project": uuid.uuid4().hex,
                       "upload_token": token, "work_id": work_id, "actor": actor}
            first = app.enqueue_operation(payload, "lost-create-response")
            work_ref = app.client.collection("shared_workflow_v1").document(self.settings.dataset).collection(
                "chapter_work").document(work_id)
            work_ref.update({"status": "pending"})
            recovered = app.enqueue_operation(payload, "lost-create-response")
            self.assertEqual(recovered.operation_id, first.operation_id)
            changed = {**payload, "work_id": "f" * 32}
            with self.assertRaises(OperationConflict) as conflict:
                app.enqueue_operation(changed, "lost-create-response")
            self.assertEqual(conflict.exception.code, "idempotency_conflict")

    def test_concurrent_monthly_threshold_has_one_operation_winner(self):
        from manga_worker.cloud_admission import ProductionLimitExceeded
        with tempfile.TemporaryDirectory() as directory:
            app = self._application(directory)
            actor = {"kind": "firebase", "uid": "creator", "project_id": self.settings.project}
            for index in range(1, 5):
                work_id = self._approved_work(app, actor, title=f"Concurrent {index}")
                token = self._image_upload(app, directory, actor)
                app.enqueue_operation({"action": "create", "mode": "images", "project": uuid.uuid4().hex,
                                       "upload_token": token, "work_id": work_id, "actor": actor},
                                      f"concurrent-prefill-{index}")
            candidates = []
            for index in (5, 6):
                work_id = self._approved_work(app, actor, title=f"Concurrent {index}")
                token = self._image_upload(app, directory, actor)
                candidates.append((index, {"action": "create", "mode": "images", "project": uuid.uuid4().hex,
                                           "upload_token": token, "work_id": work_id, "actor": actor}))

            def submit(item):
                index, payload = item
                try:
                    app.enqueue_operation(payload, f"concurrent-final-{index}")
                    return "accepted"
                except ProductionLimitExceeded:
                    return "rejected"

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(submit, candidates))
            self.assertCountEqual(outcomes, ["accepted", "rejected"])
            month = app.admission._month(app.admission.clock())
            chapters = app.admission.root.collection("production_months").document(month).get().to_dict()["chapter_ids"]
            self.assertEqual(len(chapters), 5)

    def test_archive_page_count_is_validated_and_over_limit_does_not_reserve(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._application(directory)
            actor = {"kind": "firebase", "uid": "creator", "project_id": self.settings.project}
            work_id = self._approved_work(app, actor)
            archive = Path(directory) / "chapter.zip"
            chapter = {"chapter_id": "fixture", "pages": [
                {"page_id": f"page-{index}", "page_index": index, "texts": [], "characters": []}
                for index in range(41)]}
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("chapter_analysis.json", json.dumps(chapter))
            token = uuid.uuid4().hex
            app.upload(token, "chapter.zip", archive, actor)
            with self.assertRaisesRegex(ValueError, "40 pages"):
                app.enqueue_operation({"action": "create", "mode": "chapter", "project": uuid.uuid4().hex,
                                       "upload_token": token, "work_id": work_id, "actor": actor}, "too-many-pages")
            for collection in ("production_months", "production_admissions"):
                self.assertEqual(list(app.admission.root.collection(collection).limit(1).stream()), [])
            with self.assertRaises(FileNotFoundError):
                app.operations.get_by_key("too-many-pages")


if __name__ == "__main__":
    unittest.main()
