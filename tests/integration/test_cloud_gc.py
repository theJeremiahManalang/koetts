"""Reference-aware collector checks against loopback Firestore and fake GCS."""
from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from manga_tts.operations import OperationConflict
from manga_tts.persistence import ArtifactRef


class _DeleteFailure(TimeoutError):
    pass


class _PreconditionFailed(RuntimeError):
    code = 412


class _TimedBlob:
    def __init__(self, bucket, name, generation=None):
        self.bucket, self.name, self.generation = bucket, name, generation
        self.requested_generation = generation
        self.time_created = None

    def upload_from_filename(self, filename, if_generation_match=None):
        if if_generation_match != 0:
            raise AssertionError("fixture uploads must be create only")
        if self.name in self.bucket.objects:
            raise _PreconditionFailed("object already exists")
        generation = str(self.bucket.next_generation)
        self.bucket.next_generation += 1
        self.bucket.objects[self.name] = (generation, Path(filename).read_bytes())
        self.generation = int(generation)
        self.bucket.created[self.name] = self.bucket.now

    def reload(self):
        self.generation = int(self.bucket.objects[self.name][0])

    def download_to_filename(self, filename):
        generation, contents = self.bucket.objects[self.name]
        if self.requested_generation is not None and str(self.requested_generation) != generation:
            raise FileNotFoundError(self.name)
        Path(filename).write_bytes(contents)
        self.generation = int(generation)

    def delete(self, if_generation_match=None):
        self.bucket.delete_requests.append((self.name, self.requested_generation, if_generation_match))
        if self.bucket.fail_deletes:
            self.bucket.fail_deletes = False
            raise _DeleteFailure("injected uncertain delete")
        current = self.bucket.objects.get(self.name)
        if current is None:
            error = FileNotFoundError(self.name)
            error.code = 404
            raise error
        if if_generation_match != int(current[0]) or str(self.requested_generation) != current[0]:
            error = RuntimeError("generation mismatch")
            error.code = 412
            raise error
        del self.bucket.objects[self.name]
        self.bucket.created.pop(self.name, None)


class _TimedBucket:
    name = "gc-fixture-bucket"

    def __init__(self):
        self.objects = {}
        self.created = {}
        self.next_generation = 1
        self.now = datetime.now(timezone.utc)
        self.fail_deletes = False
        self.delete_requests = []

    def blob(self, name, generation=None):
        blob = _TimedBlob(self, name, generation)
        blob.time_created = self.created.get(name)
        return blob

    def list_blobs(self, prefix=None):
        for name, (generation, _) in list(self.objects.items()):
            if prefix is None or name.startswith(prefix):
                blob = self.blob(name, int(generation))
                blob.generation = int(generation)
                yield blob


@unittest.skipUnless(os.environ.get("FIRESTORE_EMULATOR_HOST"), "No Firestore emulator configured")
class CloudGcIntegrationTests(unittest.TestCase):
    def setUp(self):
        from google.cloud import firestore

        host = os.environ["FIRESTORE_EMULATOR_HOST"]
        if host.split(":")[0] not in {"127.0.0.1", "localhost", "[::1]"}:
            raise ValueError("GC tests require a loopback Firestore emulator")
        self.client = firestore.Client(project="demo-cloud-gc", database="gc-tests")
        self.addCleanup(self.client.close)
        self.dataset = "test-" + uuid.uuid4().hex
        self.bucket = _TimedBucket()
        self.now = datetime.now(timezone.utc)

    def _app(self, directory):
        from manga_worker.cloud import CloudSettings
        from manga_worker.cloud_application import CloudApplication

        storage = Mock()
        storage.bucket.return_value = self.bucket
        settings = CloudSettings("demo-cloud-gc", "gc-tests", self.dataset,
                                 self.bucket.name, "pilot/gc")
        app = CloudApplication(settings, firestore_client=self.client, storage_client=storage,
                               cache_root=Path(directory) / "cache")
        app.budget.configure("gc-fixture", "synthetic fixture", provider_allowance_micro=80_000_000,
                             stages={stage: {"infrastructure_micro": 1000, "provider_micro": 1000,
                                             "provider_call_micro": 100, "max_provider_calls": 10}
                                     for stage in ("magi", "pipeline")})
        return app

    def _collector(self, app):
        from manga_worker.cloud_gc import ArtifactCollection, ReferenceAwareCollector

        maintenance = ArtifactCollection(app.client, self.dataset, app.stores.artifacts.artifact_store_id)
        return ReferenceAwareCollector(app.stores, maintenance, clock=lambda: self.now), maintenance

    def _artifact(self, app, directory, contents, *, age_days=10):
        source = Path(directory) / ("file-" + uuid.uuid4().hex)
        source.write_bytes(contents)
        ref = app.stores.artifacts.put_file(source)
        self.bucket.created[ref.object_id] = self.now - timedelta(days=age_days)
        return ref

    def _execution(self, value=None):
        return value or f"projects/demo-cloud-gc/locations/us-central1/jobs/gc/executions/{uuid.uuid4().hex}"

    def test_deletes_only_old_unreferenced_objects_and_retires_old_staging_records(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._app(directory)
            collector, maintenance = self._collector(app)
            project_id, revision = self._seed_project(app)
            manifest = app.stores.persistence.read_manifest(revision.manifest)
            project_artifacts = {entry.artifact for entry in manifest.entries.values()}
            self.assertGreaterEqual(len(project_artifacts), 2, "fixture must include project and source artifacts")

            shared_ref = self._artifact(app, directory, b"accepted shared catalog bytes")
            app.stores.shared_artifacts.references.put(shared_ref)
            old_orphan = self._artifact(app, directory, b"unreferenced old bytes")
            fresh = self._artifact(app, directory, b"new object", age_days=1)
            staged_old = self._artifact(app, directory, b"old unreferenced staging")
            staged_fresh = self._artifact(app, directory, b"fresh upload reference")
            uploads = app.uploads
            uploads.document("old-" + uuid.uuid4().hex).set({
                "owner_uid": "fixture", "project_id": "demo-cloud-gc", "files": {"cast.zip": vars(staged_old)},
                "updated_at": (self.now - timedelta(days=9)).timestamp(),
            })
            uploads.document("fresh-" + uuid.uuid4().hex).set({
                "owner_uid": "fixture", "project_id": "demo-cloud-gc", "files": {"cast.zip": vars(staged_fresh)},
                "updated_at": self.now.timestamp(),
            })
            token = uuid.uuid4().hex
            staged_pinned = self._enqueue_pinning_operation(app, directory, project_id, revision, token)
            uploads.document(token).update({"updated_at": (self.now - timedelta(days=9)).timestamp()})

            result = collector.collect(self._execution())
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["retired_uploads"], 1)
            self.assertNotIn(old_orphan.object_id, self.bucket.objects)
            self.assertNotIn(staged_old.object_id, self.bucket.objects)
            self.assertIn(fresh.object_id, self.bucket.objects)
            self.assertIn(staged_pinned.object_id, self.bucket.objects)
            self.assertIn(staged_fresh.object_id, self.bucket.objects)
            self.assertIn(shared_ref.object_id, self.bucket.objects)
            for ref in project_artifacts:
                with self.subTest(project_artifact=ref.object_id):
                    stored = self.bucket.objects.get(ref.object_id)
                    self.assertIsNotNone(stored)
                    self.assertEqual(stored[0], ref.generation)
            self.assertTrue(all(requested == precondition for _, requested, precondition
                                in self.bucket.delete_requests))
            self.assertTrue(uploads.document(token).get().exists)

    def test_pending_delete_holds_barrier_and_recovery_replays_exact_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._app(directory)
            collector, maintenance = self._collector(app)
            orphan = self._artifact(app, directory, b"delete uncertain")
            self.bucket.fail_deletes = True
            with self.assertRaises(_DeleteFailure):
                collector.collect(self._execution())
            state = maintenance._artifact_maintenance.get().to_dict()
            self.assertIsNotNone(state["owner"])
            self.assertEqual(maintenance.recovery_artifacts(state["owner"]).__next__(), orphan)
            with self.assertRaises(OperationConflict) as live:
                collector.recover(state["owner"], self._execution(), lambda _: "running")
            self.assertEqual(live.exception.code, "collection_execution_live")
            with self.assertRaises(OperationConflict):
                collector.recover(state["owner"], self._execution(), lambda _: "unknown")

            result = collector.recover(state["owner"], self._execution(), lambda _: "failed")
            self.assertEqual(result, {"status": "recovered", "replayed_deletions": 1})
            self.assertNotIn(orphan.object_id, self.bucket.objects)
            self.assertEqual(self.bucket.delete_requests[-1],
                             (orphan.object_id, int(orphan.generation), int(orphan.generation)))
            self.assertIsNone(maintenance._artifact_maintenance.get().to_dict()["owner"])

    def test_missing_project_owner_with_revision_subcollection_fails_before_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._app(directory)
            collector, _ = self._collector(app)
            orphan = self._artifact(app, directory, b"must survive invalid roots")
            missing_owner = app.stores.revisions._project("missing-owner")
            missing_owner.collection("revisions").document("accepted-revision").set({"fixture": True})

            with self.assertRaisesRegex(ValueError, "no project ownership record"):
                collector.collect(self._execution())

            self.assertIn(orphan.object_id, self.bucket.objects)
            self.assertEqual(self.bucket.delete_requests, [])

    def test_missing_current_revision_fails_before_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._app(directory)
            collector, _ = self._collector(app)
            orphan = self._artifact(app, directory, b"must survive missing pointer")
            app.stores.revisions.ensure_binding()
            app.stores.revisions._project("missing-current").set({
                "schema_version": 1, "project_id": "missing-current", "last_fence": 0,
                "owner_id": None, "active_fence": None, "current_revision_id": "gone",
            })

            with self.assertRaisesRegex(ValueError, "Current project revision is missing"):
                collector.collect(self._execution())

            self.assertIn(orphan.object_id, self.bucket.objects)
            self.assertEqual(self.bucket.delete_requests, [])

    def test_recovery_chain_retains_original_replay_log_after_second_interruption(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._app(directory)
            collector, maintenance = self._collector(app)
            orphan = self._artifact(app, directory, b"recovery chain")
            self.bucket.fail_deletes = True
            with self.assertRaises(_DeleteFailure):
                collector.collect(self._execution())
            first_owner = maintenance._artifact_maintenance.get().to_dict()["owner"]
            self.bucket.fail_deletes = True
            with self.assertRaises(_DeleteFailure):
                collector.recover(first_owner, self._execution(), lambda _: "failed")
            second_owner = maintenance._artifact_maintenance.get().to_dict()["owner"]
            self.assertNotEqual(first_owner, second_owner)
            self.assertEqual(list(maintenance.recovery_artifacts(second_owner)), [orphan, orphan])
            result = collector.recover(second_owner, self._execution(), lambda _: "cancelled")
            self.assertEqual(result["replayed_deletions"], 2)
            self.assertNotIn(orphan.object_id, self.bucket.objects)

    def test_active_writer_stage_slot_and_running_or_uncertain_operations_block_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._app(directory)
            collector, _ = self._collector(app)
            owner = app.stores.revisions.acquire("active-project", "writer")
            self.assertEqual(collector.collect(self._execution())["status"], "busy")
            app.stores.revisions.release(owner)

            slots = app.operations._slots
            slots.document("magi").set({"operation_id": "occupied"})
            self.assertEqual(collector.collect(self._execution())["status"], "busy")
            slots.document("magi").delete()

            for status in ("running", "reconciliation_required"):
                operation_id = "fixture-" + status
                self._seed_operation(app, operation_id, status)
                self.assertEqual(collector.collect(self._execution())["status"], "busy")
                app.operations._operation_ref(operation_id).delete()

    def test_reads_and_playback_remain_available_while_collection_barrier_is_held(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._app(directory)
            collector, maintenance = self._collector(app)
            project_id, revision = self._seed_project(app)
            actor = {"kind": "firebase", "uid": "gc-reader", "project_id": "demo-cloud-gc"}
            request = app.shared({"action": "submit", "title": "GC playback", "chapter": "1", "notes": ""}, actor)
            app.shared({"action": "approve", "work_id": request["work_id"]}, actor)
            app.shared({"action": "link", "work_id": request["work_id"], "project_id": project_id,
                        "revision": revision.project_hash}, actor)
            candidate = app.shared({"action": "prepare", "work_id": request["work_id"],
                                    "revision": revision.project_hash}, actor)
            review = app.shared({"action": "review", "work_id": request["work_id"],
                                 "candidate_id": candidate["id"], "revision": revision.project_hash}, actor)
            publication = app.shared({"action": "publish", "work_id": request["work_id"],
                                      "review_id": review["id"], "revision": revision.project_hash,
                                      "expected_publication": None}, actor)
            fence = maintenance.begin(self._execution())
            self.assertIsNotNone(fence)
            self.assertEqual(app.snapshot(project_id)["revision"], revision.project_hash)
            self.assertEqual(app.list_projects()["projects"][0]["id"], project_id)
            self.assertGreater(app.published_path(request["work_id"], publication["id"]).stat().st_size, 0)
            upload_source = Path(directory) / "barrier-upload.zip"
            upload_source.write_bytes(b"valid upload while the collection fence is held")
            with self.assertRaises(OperationConflict):
                app.upload(uuid.uuid4().hex, "cast.zip", upload_source, {
                    "kind": "firebase", "uid": actor["uid"], "project_id": "demo-cloud-gc"})
            maintenance.finish(fence)

    def test_epoch_capture_then_upload_io_and_enqueue_io_reject_stale_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._app(directory)
            collector, _ = self._collector(app)
            project_id, revision = self._seed_project(app)
            actor = {"kind": "firebase", "uid": "fixture", "project_id": "demo-cloud-gc"}
            source = Path(directory) / "upload.zip"
            source.write_bytes(b"frozen upload bytes")
            original_put = app.stores.artifacts.put_file

            def collect_during_upload(path):
                result = original_put(path)
                collector.collect(self._execution())
                return result

            app.stores.artifacts.put_file = collect_during_upload
            with self.assertRaises(OperationConflict) as conflict:
                app.upload(uuid.uuid4().hex, "cast.zip", source, actor)
            self.assertEqual(conflict.exception.code, "artifact_epoch_changed")
            app.stores.artifacts.put_file = original_put

            upload_token = uuid.uuid4().hex
            app.upload(upload_token, "cast.zip", source, actor)
            original_verified = app._verified_uploads

            def collect_after_upload_verification(request, verified_actor):
                result = original_verified(request, verified_actor)
                collector.collect(self._execution())
                return result

            app._verified_uploads = collect_after_upload_verification
            with self.assertRaises(OperationConflict) as conflict:
                app.enqueue_operation({"action": "cast-import", "project": project_id,
                                       "revision": revision.project_hash, "upload_token": upload_token,
                                       "actor": actor}, "stale-gc-epoch")
            self.assertEqual(conflict.exception.code, "artifact_epoch_changed")

    def test_catalog_promotion_using_pre_collection_epoch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._app(directory)
            collector, _ = self._collector(app)
            stale_epoch = app.stores.revisions.artifact_epoch()
            artifact = self._artifact(app, directory, b"catalog promotion race", age_days=1)

            self.assertEqual(collector.collect(self._execution())["status"], "complete")
            with self.assertRaises(OperationConflict) as conflict:
                app.stores.shared_artifacts.references.put(artifact, expected_epoch=stale_epoch)

            self.assertEqual(conflict.exception.code, "artifact_epoch_changed")
            self.assertNotIn(artifact.sha256, list(
                snapshot.id for snapshot in app.stores.revisions.root.collection("artifact_references").stream()
            ))

    def _seed_project(self, app):
        from manga_tts import schemas
        from tests.unit.engine.test_audio_pipeline import PipelineTests

        fixture = PipelineTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.approve()
        fixture.router.render_selected(schemas.RenderCommand(scene_ids=["scene_001"]))
        fixture.router.export_audio(schemas.RenderSelection(scene_ids=["scene_001"]))
        project_id = uuid.uuid4().hex
        with app.stores.persistence.acquire(project_id, "gc-fixture-writer") as writer:
            revision = writer.commit(fixture.router.root, schemas.dump(fixture.router.project), None)
        return project_id, revision

    @staticmethod
    def _seed_operation(app, operation_id, status):
        now = 1000.0
        value = {
            "schema_version": 1, "operation_id": operation_id, "idempotency_key": operation_id,
            "request_fingerprint": "request", "project_id": "fixture-project", "stage": "pipeline",
            "payload": {"action": "rename", "project": "fixture-project"},
            "revision": None, "source_fingerprint": "source", "configuration_fingerprint": "config",
            "status": status, "attempt_count": 1, "fence": 1,
            "lease_expires_at": now + 30 if status == "running" else None,
            "provider_outcome_pending": status == "reconciliation_required", "progress": {},
            "checkpoint": None, "result": None, "failure_code": None, "message": "fixture",
            "created_at": now, "updated_at": now, "attempt_started_at": now,
        }
        app.operations._operation_ref(operation_id).set(value)

    def _enqueue_pinning_operation(self, app, directory, project_id, revision, token):
        source = Path(directory) / ("pin-" + uuid.uuid4().hex + ".zip")
        source.write_bytes(b"fixture")
        # A cast archive is treated as an opaque upload by this acceptance path.
        app.upload(token, "cast.zip", source, {"kind": "firebase", "uid": "fixture",
                                                "project_id": "demo-cloud-gc"})
        staged = app.uploads.document(token).get().to_dict()["files"]["cast.zip"]
        app.enqueue_operation({"action": "cast-import", "project": project_id,
                               "revision": revision.project_hash, "upload_token": token,
                               "actor": {"kind": "firebase", "uid": "fixture",
                                         "project_id": "demo-cloud-gc"}}, "gc-pinned-token")
        return ArtifactRef(**staged)


if __name__ == "__main__":
    unittest.main()
