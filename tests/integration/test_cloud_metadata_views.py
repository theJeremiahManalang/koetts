"""Hosted metadata views must not hydrate immutable project assets."""
from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock

from manga_tts import schemas


class CountingBlob:
    def __init__(self, bucket, name, generation=None):
        from tests.unit.worker.test_cloud_artifacts import FakeBlob

        self._inner = FakeBlob(bucket, name, generation)
        self.bucket = bucket
        self.name = name
        self.generation = generation

    def __getattr__(self, name):
        return getattr(self._inner, name)

    @property
    def generation(self):
        return self._inner.generation

    @generation.setter
    def generation(self, value):
        self._inner.generation = value

    def download_to_filename(self, filename):
        self.bucket.downloaded.append((self.name, self.generation))
        self._inner.download_to_filename(filename)
        self.generation = self._inner.generation


class CountingBucket:
    name = "metadata-view-test-bucket"

    def __init__(self):
        from tests.unit.worker.test_cloud_artifacts import FakeBucket

        self._inner = FakeBucket()
        self.objects = self._inner.objects
        self.next_generation = self._inner.next_generation
        self.requests = self._inner.requests
        self.downloaded = []

    def blob(self, name, generation=None):
        self.requests.append((name, generation))
        return CountingBlob(self, name, generation)


@unittest.skipUnless(os.environ.get("FIRESTORE_EMULATOR_HOST"), "No Firestore emulator configured")
class CloudMetadataViewTests(unittest.TestCase):
    def setUp(self):
        from google.cloud import firestore

        host = os.environ["FIRESTORE_EMULATOR_HOST"]
        if host.split(":")[0] not in {"127.0.0.1", "localhost", "[::1]"}:
            raise ValueError("Hosted metadata tests require loopback Firestore")
        self.client = firestore.Client(project="demo-cloud-metadata-views", database="metadata-views")
        self.addCleanup(self.client.close)

    def test_snapshot_and_enqueue_use_manifest_checksums_without_downloading_assets(self):
        from manga_worker.cloud import CloudSettings
        from manga_worker.cloud_application import CloudApplication
        from tests.unit.engine.test_audio_pipeline import PipelineTests

        with tempfile.TemporaryDirectory() as directory:
            bucket = CountingBucket()
            storage = Mock()
            storage.bucket.return_value = bucket
            settings = CloudSettings("demo-cloud-metadata-views", "metadata-views", "app-" + uuid.uuid4().hex,
                                     bucket.name, "pilot/metadata")
            app = CloudApplication(settings, firestore_client=self.client, storage_client=storage,
                                   cache_root=Path(directory) / "scratch")
            app.budget.configure("fixture-developer", "synthetic metadata caps",
                                 provider_allowance_micro=0, stages={
                                     stage: {"infrastructure_micro": 1000, "provider_micro": 0,
                                             "provider_call_micro": 0, "max_provider_calls": 0}
                                     for stage in ("magi", "pipeline")
                                 })

            fixture = PipelineTests()
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
            fixture.approve()
            fixture.router.render_selected(schemas.RenderCommand(scene_ids=["scene_001"]))
            fixture.router.export_audio(schemas.RenderSelection(scene_ids=["scene_001"]))
            project_id = uuid.uuid4().hex
            with app.stores.persistence.acquire(project_id, "metadata-view-fixture") as writer:
                revision = writer.commit(fixture.router.root, schemas.dump(fixture.router.project), None)

            manifest = app.stores.persistence.read_manifest(revision.manifest)
            asset_refs = {entry.artifact.object_id for path, entry in manifest.entries.items()
                          if path != "project.json"}
            bucket.downloaded.clear()

            snapshot = app.snapshot(project_id)
            self.assertEqual(snapshot["revision"], revision.project_hash)
            actor = {"kind": "firebase", "uid": "metadata-view-user", "project_id": settings.project}
            operation = app.enqueue_operation({"action": "plan", "project": project_id,
                                               "revision": revision.project_hash, "actor": actor},
                                              "metadata-only-plan-" + uuid.uuid4().hex)
            self.assertTrue(operation.source_fingerprint)
            self.assertFalse(asset_refs.intersection(name for name, _ in bucket.downloaded))
            self.assertLessEqual(len(bucket.downloaded), 3)


if __name__ == "__main__":
    unittest.main()
