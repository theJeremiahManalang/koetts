"""Prior-reader rollback acceptance against loopback Firestore and frozen fake GCS."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from manga_tts import schemas


class _DeleteFailure(TimeoutError):
    pass


class _PreconditionFailed(RuntimeError):
    code = 412


class _Blob:
    def __init__(self, bucket, name, generation=None):
        self.bucket, self.name = bucket, name
        self.requested_generation = generation
        self.generation = generation

    def upload_from_filename(self, *_args, **_kwargs):
        if self.name in self.bucket.objects:
            raise _PreconditionFailed("object already exists")
        if _kwargs.get("if_generation_match") != 0:
            raise AssertionError("fixture uploads must be create only")
        generation = str(self.bucket.next_generation)
        self.bucket.next_generation += 1
        self.bucket.objects[self.name] = (generation, Path(_args[0]).read_bytes())
        self.bucket.created[self.name] = datetime.now(timezone.utc)
        self.generation = int(generation)

    def delete(self, *_args, **_kwargs):
        self.bucket.delete_exact(self.name, self.requested_generation, _kwargs.get("if_generation_match"))

    def reload(self):
        current = self.bucket.objects.get(self.name)
        if current is None:
            raise FileNotFoundError(self.name)
        self.generation = int(current[0])

    def download_to_filename(self, filename):
        current = self.bucket.objects.get(self.name)
        if current is None or (self.requested_generation is not None
                               and str(self.requested_generation) != current[0]):
            raise FileNotFoundError(self.name)
        Path(filename).write_bytes(current[1])
        self.generation = int(current[0])


class _Bucket:
    name = "rollback-fixture-bucket"

    def __init__(self):
        self.objects: dict[str, tuple[str, bytes]] = {}
        self.created = {}
        self.next_generation = 1
        self.fail_next_delete = False
        self.delete_requests = []

    def blob(self, name, generation=None):
        return _Blob(self, name, generation)

    def list_blobs(self, prefix=None):
        for name, (generation, _contents) in list(self.objects.items()):
            if prefix is None or name.startswith(prefix):
                blob = _Blob(self, name, int(generation))
                blob.generation = int(generation)
                blob.time_created = self.created.get(name)
                yield blob

    def delete_exact(self, name, requested_generation, precondition):
        self.delete_requests.append((name, requested_generation, precondition))
        if self.fail_next_delete:
            self.fail_next_delete = False
            raise _DeleteFailure("injected uncertain exact-generation delete")
        current = self.objects.get(name)
        if current is None:
            error = FileNotFoundError(name)
            error.code = 404
            raise error
        if str(requested_generation) != current[0] or int(precondition) != int(current[0]):
            error = RuntimeError("generation precondition mismatch")
            error.code = 412
            raise error
        del self.objects[name]


@unittest.skipUnless(os.environ.get("FIRESTORE_EMULATOR_HOST"), "No Firestore emulator configured")
class CloudRollbackAcceptanceTests(unittest.TestCase):
    def setUp(self):
        from google.cloud import firestore

        host = os.environ["FIRESTORE_EMULATOR_HOST"]
        if host.split(":")[0] not in {"127.0.0.1", "localhost", "[::1]"}:
            raise ValueError("Rollback acceptance requires a loopback Firestore emulator")
        self.client = firestore.Client(project="demo-cloud-rollback", database="rollback-tests")
        self.addCleanup(self.client.close)
        self.dataset = "rollback-" + uuid.uuid4().hex
        self.bucket = _Bucket()

    def test_prior_api_reads_candidate_state_without_writes_during_pending_gc_recovery(self):
        from manga_worker.cloud import CloudSettings
        from manga_worker.cloud_application import CloudApplication
        from manga_worker.cloud_gc import ArtifactCollection, ReferenceAwareCollector
        from tests.unit.engine.test_audio_pipeline import PipelineTests

        with tempfile.TemporaryDirectory(prefix="hosted-rollback-") as directory:
            root = Path(directory)
            storage = Mock()
            storage.bucket.return_value = self.bucket
            settings = CloudSettings("demo-cloud-rollback", "rollback-tests", self.dataset,
                                     self.bucket.name, "pilot/rollback")
            candidate = CloudApplication(settings, firestore_client=self.client, storage_client=storage,
                                         cache_root=root / "candidate-cache")
            candidate.budget.configure("rollback-fixture", "synthetic rollback fixture",
                provider_allowance_micro=80_000_000, stages={
                    stage: {"infrastructure_micro": 1_000, "provider_micro": 1_000,
                            "provider_call_micro": 100, "max_provider_calls": 10}
                    for stage in ("magi", "pipeline")})

            fixture = PipelineTests()
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
            fixture.approve()
            fixture.router.render_selected(schemas.RenderCommand(scene_ids=["scene_001"]))
            fixture.router.export_audio(schemas.RenderSelection(scene_ids=["scene_001"]))
            project_id = uuid.uuid4().hex
            with candidate.stores.persistence.acquire(project_id, "rollback-fixture-writer") as writer:
                revision = writer.commit(fixture.router.root, schemas.dump(fixture.router.project), None)

            actor = {"kind": "firebase", "uid": "rollback-reader", "project_id": settings.project}
            request = candidate.shared({"action": "submit", "title": "Rollback chapter",
                                        "chapter": "1", "notes": ""}, actor)
            work_id = request["work_id"]
            candidate.shared({"action": "approve", "work_id": work_id}, actor)
            candidate.shared({"action": "link", "work_id": work_id, "project_id": project_id,
                              "revision": revision.project_hash}, actor)
            prepared = candidate.shared({"action": "prepare", "work_id": work_id,
                                         "revision": revision.project_hash}, actor)
            reviewed = candidate.shared({"action": "review", "work_id": work_id,
                                         "candidate_id": prepared["id"],
                                         "revision": revision.project_hash}, actor)
            publication = candidate.shared({"action": "publish", "work_id": work_id,
                "review_id": reviewed["id"], "revision": revision.project_hash,
                "expected_publication": None}, actor)
            published = candidate.shared_requests.publication(work_id)
            published_ref = candidate.stores.shared_artifacts.references.get(
                published["checksums"]["chapter_narration.wav"])
            published_bytes = self.bucket.objects[published_ref.object_id][1]
            published_generation = self.bucket.objects[published_ref.object_id][0]

            # Leave durable operation, checkpoint, reservation and provider debit evidence.
            op = candidate.operations.enqueue(idempotency_key="rollback-checkpoint-" + uuid.uuid4().hex,
                payload={"action": "extract"}, project_id=project_id, stage="magi",
                revision=revision.project_hash, source_fingerprint="fixture-source",
                configuration_fingerprint="fixture-config")
            claim = candidate.operations.claim(op.operation_id)
            self.assertIsNotNone(claim)
            candidate.budget.authorize_provider(op.idempotency_key, "rollback-provider-call")
            accepted = {"accepted": True, "project_hash": revision.project_hash,
                        "fixture_audio_checksum": published_ref.sha256}
            candidate.operations.heartbeat(claim, checkpoint=accepted, provider_result_checkpointed=True)
            candidate.operations.complete(claim, {"accepted_checkpoint": accepted})
            candidate.budget.set_paused("rollback-fixture", "rollback acceptance pause", paused=True,
                                        evidence="offline-test")

            orphan = self._put_object(b"candidate orphan eligible for cleanup")
            collector = ReferenceAwareCollector(candidate.stores,
                ArtifactCollection(self.client, self.dataset, candidate.stores.artifacts.artifact_store_id))
            self.bucket.fail_next_delete = True
            with self.assertRaises(_DeleteFailure):
                collector.collect("projects/demo-cloud-rollback/locations/us-east4/jobs/gc/executions/rollback")
            maintenance_before = self._maintenance_documents()
            self.assertEqual(len(maintenance_before), 1)
            state_before = json.loads(maintenance_before[0][1])
            self.assertTrue(state_before["owner"])
            gc_runs_before = self._collection_documents("gc_runs")
            self.assertTrue(gc_runs_before)
            self.assertEqual(self.bucket.objects[orphan[0]][0], orphan[1])
            self.assertEqual(self.bucket.delete_requests[-1], (orphan[0], int(orphan[1]), int(orphan[1])))

            # Capture all existing hosted/shared document trees before old-reader activity.
            before = self._hosted_tree()
            fake_state = {"objects": {name: [generation, contents.hex()]
                                      for name, (generation, contents) in self.bucket.objects.items()},
                          "next_generation": self.bucket.next_generation}
            bucket_file = root / "bucket.json"
            bucket_file.write_text(json.dumps(fake_state), encoding="utf-8")
            evidence_file = root / "legacy-reader-result.json"
            self._run_archived_reader(root, bucket_file, evidence_file,
                {"project": settings.project, "database": settings.database, "dataset": self.dataset,
                 "bucket": self.bucket.name, "namespace": settings.namespace,
                 "project_id": project_id, "revision": revision.project_hash,
                 "work_id": work_id, "publication_id": publication["id"],
                 "published_bytes": published_bytes.hex(), "service_token": "offline-service-token",
                 "user_token": "offline-user-token"})
            legacy = json.loads(evidence_file.read_text(encoding="utf-8"))
            self.assertEqual(legacy["snapshot_revision"], revision.project_hash)
            self.assertIn(project_id, [row["id"] for row in legacy["projects"]])
            self.assertEqual(legacy["catalog_count"], 1)
            self.assertEqual(legacy["published_bytes"], published_bytes.hex())
            self.assertEqual(legacy["enqueue_status"], 403)
            self.assertEqual(legacy["coordinate_status"], 403)
            self.assertEqual(legacy["module_paths_checked"], 4)

            after = self._hosted_tree()
            self.assertEqual(after, before, "prior-reader API must not change any hosted/shared records")
            self.assertEqual(self._maintenance_documents(), maintenance_before)
            self.assertEqual(self._collection_documents("gc_runs"), gc_runs_before)
            self.assertEqual(self.bucket.objects[orphan[0]], (orphan[1], b"candidate orphan eligible for cleanup"))
            self.assertEqual(self.bucket.objects[published_ref.object_id], (published_generation, published_bytes))
            self.assertEqual(self.bucket.delete_requests[-1], (orphan[0], int(orphan[1]), int(orphan[1])))

            # Current candidate can still recover the durable chain after the old read-only process exits.
            state = candidate.stores.revisions._artifact_maintenance.get().to_dict()
            owner = state["owner"]
            result = collector.recover(owner,
                "projects/demo-cloud-rollback/locations/us-east4/jobs/gc/executions/recovery",
                lambda _execution: "failed")
            self.assertEqual(result, {"status": "recovered", "replayed_deletions": 1})
            self.assertNotIn(orphan[0], self.bucket.objects)
            self.assertEqual(self.bucket.objects[published_ref.object_id], (published_generation, published_bytes))
            self.assertIsNone(candidate.stores.revisions._artifact_maintenance.get().to_dict()["owner"])

    def _put_object(self, contents):
        import hashlib

        name = "pilot/rollback/" + hashlib.sha256(contents).hexdigest()
        generation = str(self.bucket.next_generation)
        self.bucket.next_generation += 1
        self.bucket.objects[name] = (generation, contents)
        self.bucket.created[name] = datetime.now(timezone.utc) - timedelta(days=10)
        return name, generation

    def _hosted_tree(self):
        roots = (self.client.collection("hosted_workflow_v1").document(self.dataset),
                 self.client.collection("shared_workflow_v1").document(self.dataset))
        return tuple(entry for root in roots for entry in self._walk_document(root))

    def _walk_document(self, document):
        snapshot = document.get()
        result = []
        if snapshot.exists:
            result.append((snapshot.reference.path, json.dumps(snapshot.to_dict(), sort_keys=True,
                separators=(",", ":"), default=str)))
        for collection in sorted(document.collections(), key=lambda item: item.id):
            for reference in sorted(collection.list_documents(), key=lambda item: item.id):
                result.extend(self._walk_document(reference))
        return tuple(result)

    def _maintenance_documents(self):
        return self._collection_documents("maintenance")

    def _collection_documents(self, name):
        collection = self.client.collection("hosted_workflow_v1").document(self.dataset).collection(name)
        return tuple((snapshot.reference.path, json.dumps(snapshot.to_dict(), sort_keys=True,
            separators=(",", ":"), default=str)) for snapshot in sorted(collection.stream(), key=lambda item: item.id))

    def _run_archived_reader(self, temporary_root, bucket_file, result_file, inputs):
        repo = Path(__file__).resolve().parents[2]
        archive_root = temporary_root / "prior-source"
        archive = subprocess.run(["git", "archive", "fef5b8add2e22dd98e45283aa7ddbd600a5f3609"],
                                 cwd=repo, check=True, stdout=subprocess.PIPE).stdout
        import tarfile
        import io
        archive_root.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            tar.extractall(archive_root, filter="data")
        script = temporary_root / "legacy_reader.py"
        script.write_text(_LEGACY_READER.lstrip("\\\n"), encoding="utf-8")
        environment = dict(os.environ)
        environment["GEMINI_API_KEY"] = ""
        environment["GOOGLE_API_KEY"] = ""
        environment["PYTHONPATH"] = os.pathsep.join(str(archive_root / path) for path in (
            "apps/worker/src", "packages/engine/src", "packages/vision/src"))
        environment["ROLLBACK_INPUTS"] = json.dumps({**inputs, "bucket_file": str(bucket_file),
                                                      "result_file": str(result_file)})
        environment["LEGACY_ARCHIVE_ROOT"] = str(archive_root)
        subprocess.run([sys.executable, str(script)], cwd=temporary_root, env=environment,
                       check=True, capture_output=True, text=True, timeout=40)


_LEGACY_READER = r'''\
import json, os
from pathlib import Path
from fastapi.testclient import TestClient
from manga_worker.http_api import create_app
from manga_worker.http_auth import BoundaryConfig
from manga_worker.cloud import CloudSettings
from manga_worker.cloud_application import CloudApplication

root = Path(os.environ["LEGACY_ARCHIVE_ROOT"]).resolve()
modules = [__import__(name, fromlist=["x"]) for name in
           ("manga_worker.http_api", "manga_worker.http_auth", "manga_worker.cloud_application", "manga_tts")]
assert all(root in Path(module.__file__).resolve().parents for module in modules), [m.__file__ for m in modules]
value = json.loads(os.environ["ROLLBACK_INPUTS"])
state = json.loads(Path(value["bucket_file"]).read_text())

class Blob:
    def __init__(self, bucket, name, generation=None): self.bucket, self.name, self.requested, self.generation = bucket, name, generation, generation
    def upload_from_filename(self, *a, **k): raise AssertionError("legacy reader attempted upload")
    def delete(self, *a, **k): raise AssertionError("legacy reader attempted delete")
    def reload(self):
        item = self.bucket.objects.get(self.name)
        if item is None: raise FileNotFoundError(self.name)
        self.generation = int(item[0])
    def download_to_filename(self, filename):
        item = self.bucket.objects.get(self.name)
        if item is None or (self.requested is not None and str(self.requested) != item[0]): raise FileNotFoundError(self.name)
        Path(filename).write_bytes(item[1])
        self.generation = int(item[0])
class Bucket:
    name = value["bucket"]
    def __init__(self): self.objects = {k: (v[0], bytes.fromhex(v[1])) for k, v in state["objects"].items()}
    def blob(self, name, generation=None): return Blob(self, name, generation)
bucket = Bucket()
class Storage:
    def bucket(self, _name): return bucket

settings = CloudSettings(value["project"], value["database"], value["dataset"], value["bucket"], value["namespace"])
from google.cloud import firestore
firestore_client = firestore.Client(project=value["project"], database=value["database"])
hosted = CloudApplication(settings, firestore_client=firestore_client, storage_client=Storage(), cache_root=Path(value["result_file"]).parent / "legacy-cache")
audience = "https://rollback-fixture.invalid"
config = BoundaryConfig(value["project"], audience, {"offline-service": frozenset({"identity", "snapshot", "shared"})}, "cloud")
def service(token): return {"sub":"offline-service", "iss":"https://accounts.google.com", "aud":audience}
def user(token, session): return {"sub":"rollback-reader", "iss":"https://securetoken.google.com/" + value["project"], "aud":value["project"], "admin":True}
app = create_app(config, service_verifier=service, user_verifier=user, hosted=hosted)
headers = {"Authorization":"Bearer " + value["service_token"], "X-Koetts-User-Token":value["user_token"]}
with TestClient(app) as client:
    identity = client.get("/identity", headers=headers)
    assert identity.status_code == 200, identity.text
    projects = client.get("/projects", headers=headers)
    assert projects.status_code == 200, projects.text
    snapshot = client.get("/projects/" + value["project_id"], headers=headers)
    assert snapshot.status_code == 200, snapshot.text
    catalog = client.post("/shared", headers={**headers, "Content-Type":"application/json"}, json={"action":"catalog"})
    assert catalog.status_code == 200, catalog.text
    audio = client.get("/shared/published/" + value["work_id"] + "?publication_id=" + value["publication_id"], headers=headers)
    assert audio.status_code == 200, audio.text
    assert audio.content.hex() == value["published_bytes"], "legacy reader must retrieve exact published bytes"
    enqueue = client.post("/operations", headers={**headers, "Content-Type":"application/json", "Idempotency-Key":"rollback-write"}, json={"action":"extract"})
    assert enqueue.status_code == 403, enqueue.text
    coordinate = client.post("/internal/coordinator", headers=headers)
    assert coordinate.status_code == 403, coordinate.text
    result = {"snapshot_revision":snapshot.json()["revision"], "projects":projects.json()["projects"],
              "catalog_count":len(catalog.json()), "published_bytes":audio.content.hex(),
              "enqueue_status":enqueue.status_code, "coordinate_status":coordinate.status_code,
              "module_paths_checked":len(modules)}
Path(value["result_file"]).write_text(json.dumps(result), encoding="utf-8")
firestore_client.close()
'''


if __name__ == "__main__":
    unittest.main()
