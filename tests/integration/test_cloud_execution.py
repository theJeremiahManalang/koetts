"""A terminated hosted render resumes accepted audio from entirely new scratch."""
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock

from manga_tts import PipelineRouter, schemas
from manga_tts.operations import OperationClaim
from manga_tts.storage import digest


@unittest.skipUnless(os.environ.get("FIRESTORE_EMULATOR_HOST"), "No Firestore emulator configured")
class HostedExecutionTests(unittest.TestCase):
    def test_terminated_render_reuses_accepted_segment_after_operator_reconciliation(self):
        from google.cloud import firestore
        from manga_worker.cloud import CloudSettings, cloud_stores
        from manga_worker.cloud_coordinator import project_recovery
        from manga_worker.cloud_operations import FirestoreOperationStore
        from manga_worker.cloud_runtime import CloudRuntime
        from manga_worker.workflow import operation_pipeline_config
        from tests.unit.engine.test_audio_pipeline import PipelineTests, wav_bytes
        from tests.unit.worker.test_cloud_artifacts import FakeBucket

        if os.environ["FIRESTORE_EMULATOR_HOST"].split(":")[0] not in {"127.0.0.1", "localhost"}:
            raise ValueError("Hosted execution tests require a loopback emulator")
        client = firestore.Client(project="demo-cloud-execution", database="execution-tests")
        self.addCleanup(client.close)
        fixture = PipelineTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.approve()
        project_id = "b" * 32
        bucket = FakeBucket()
        storage = Mock()
        storage.bucket.return_value = bucket
        settings = CloudSettings("demo-cloud-execution", "execution-tests", "test-" + uuid.uuid4().hex,
                                 bucket.name, "pilot/artifacts")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stores = cloud_stores(settings, root / "cache", firestore_client=client, storage_client=storage)
            with stores.persistence.acquire(project_id, "fixture") as writer:
                revision = writer.commit(fixture.router.root, schemas.dump(fixture.router.project), None)
            operations = FirestoreOperationStore(client, settings.dataset, stores.artifacts.artifact_store_id)
            payload = {"action": "render", "project": project_id, "revision": revision.project_hash,
                       "project_revision_id": revision.revision_id, "command": {"scene_ids": ["scene_001"]}}
            operation = operations.enqueue(idempotency_key="render-once", payload=payload,
                                           project_id=project_id, stage="pipeline", revision=revision.project_hash,
                                           source_fingerprint=digest({"uploads": [], "project_evidence": []}),
                                           configuration_fingerprint=digest({}))
            claim = operations.claim(operation.operation_id)
            self.assertIsNotNone(claim)
            completed_calls = []
            attempts = []
            interrupt = [True]

            def render(request):
                attempts.append(request)
                if interrupt[0] and len(attempts) == 2:
                    raise SystemExit("synthetic process termination")
                completed_calls.append(request)
                return wav_bytes()

            def router(workspace, writer, request):
                return PipelineRouter(operation_pipeline_config(workspace), persistence=writer,
                                      client_factory=lambda: object(), renderer_factory=lambda *_: render)

            runtime = CloudRuntime(operations, stores.persistence, stores.artifacts, root / "first",
                                   router_factory=router)
            execution = "projects/demo-cloud-execution/locations/us-east4/jobs/pipeline/executions/first"
            with self.assertRaises(SystemExit):
                runtime.run(claim, execution)
            stopped = operations.get(operation.operation_id)
            self.assertTrue(stopped.provider_outcome_pending)
            self.assertEqual(len(completed_calls), 1)
            operations.confirm_execution_stopped(claim, execution)
            self.assertTrue(project_recovery(stores, operations)(stopped, claim))
            uncertain = operations.worker_stopped(claim)
            self.assertEqual(uncertain.status, "reconciliation_required")
            # This is a synthetic explicit operator retry, never automatic consent.
            operations.resolve_uncertain(operation.operation_id, "retry")
            second_claim = operations.claim(operation.operation_id)
            self.assertEqual(second_claim.fence, claim.fence + 1)
            interrupt[0] = False
            fresh = cloud_stores(settings, root / "fresh-cache", firestore_client=client, storage_client=storage)
            second = CloudRuntime(operations, fresh.persistence, fresh.artifacts, root / "second", router_factory=router)
            self.assertTrue(second.run(OperationClaim(operation.operation_id, second_claim.fence),
                                       execution.replace("/first", "/second")))
            final = operations.get(operation.operation_id)
            self.assertEqual(final.status, "complete", final.message)
            self.assertEqual(len(completed_calls), 2, "Accepted first segment must not be generated twice")
            self.assertEqual(len(attempts), 3, "Only interrupted segment should be attempted again")
            self.assertIsNone(final.worker_pid)
