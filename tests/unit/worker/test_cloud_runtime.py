"""Cloud worker lifecycle tests with injected persistence and provider seams."""
from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path

from tests.unit.engine import test_audio_pipeline as fixtures
from manga_tts import schemas
from manga_tts.operations import Operation, OperationClaim, OperationConflict, OperationPolicy
from manga_tts.persistence import (
    ArtifactRef,
    InMemoryArtifactStore,
    InMemoryRevisionStore,
    ProjectPersistence,
    ProjectRevision,
)
from manga_tts.storage import digest
from manga_worker.cloud_runtime import CloudRuntime


OPERATION_ID = "a" * 32
PROJECT_ID = "b" * 32
UPLOAD_TOKEN = "c" * 32


def operation(*, payload=None, checkpoint=None, stage="pipeline"):
    return Operation(
        operation_id=OPERATION_ID,
        idempotency_key="runtime-test",
        request_fingerprint="request",
        project_id=PROJECT_ID,
        stage=stage,
        payload=payload or {
            "project": PROJECT_ID,
            "action": "create",
            "mode": "chapter",
            "upload_token": UPLOAD_TOKEN,
            "source_hashes": [],
            "cloud_uploads": {},
        },
        revision=None,
        source_fingerprint="source",
        configuration_fingerprint="config",
        status="running",
        attempt_count=1,
        fence=7,
        lease_expires_at=1000.0,
        worker_pid=None,
        worker_created_at=None,
        provider_outcome_pending=False,
        progress={},
        checkpoint=checkpoint,
        result=None,
        failure_code=None,
        message="Starting worker.",
        created_at=1.0,
        updated_at=1.0,
        attempt_started_at=1.0,
    )


class MemoryOperationStore:
    policy = OperationPolicy(heartbeat_seconds=60, lease_seconds=120)

    def __init__(self, value):
        self.value = value
        self.checkpoint = value.checkpoint
        self.registered = []
        self.progress = []
        self.completed = None
        self.failures = []
        self.provider_pending = False
        self.order = []
        self.duplicate = False
        self.events = []
        self.reject_completion = False
        self.lose_heartbeat = False
        self.heartbeat_lost = threading.Event()

    def get(self, operation_id):
        assert operation_id == self.value.operation_id
        return replace(self.value, checkpoint=self.checkpoint)

    def register_execution(self, claim, execution_name):
        assert claim.fence == self.value.fence
        if self.duplicate:
            raise OperationConflict("duplicate_worker", "Duplicate execution")
        self.registered.append(execution_name)
        return self.value

    def heartbeat(self, claim, progress=None, checkpoint=None, provider_result_checkpointed=False):
        if self.lose_heartbeat:
            self.heartbeat_lost.set()
            raise OperationConflict("stale_fence", "Operation fence is no longer current.")
        if checkpoint is not None:
            self.checkpoint = dict(checkpoint)
        self.progress.append((dict(progress or {}), dict(checkpoint) if checkpoint is not None else None,
                              provider_result_checkpointed))
        self.order.append("checkpoint" if checkpoint is not None else "heartbeat")

    def mark_provider_call_pending(self, claim):
        self.order.append("provider_pending")
        self.provider_pending = True

    def complete(self, claim, result):
        if self.reject_completion:
            raise OperationConflict("stale_fence", "Operation fence is no longer current.")
        self.order.append("complete")
        self.completed = result

    def fail(self, claim, message, failure_code, retryable=False):
        self.order.append("fail")
        self.events.append("fail")
        self.failures.append((message, failure_code, retryable))
        if self.provider_pending:
            self.value = self.value.__class__(**{
                **vars(self.value),
                "status": "reconciliation_required",
                "provider_outcome_pending": True,
            })

    def mark_uncertain(self, claim, message):
        self.order.append("uncertain")
        self.events.append("uncertain")
        self.value = replace(self.value, status="reconciliation_required")


class MemoryArtifacts:
    def __init__(self, content=b"uploaded chapter"):
        self.content = content
        self.ref = ArtifactRef("objects/chapter", "3", hashlib.sha256(content).hexdigest())
        self.uploads = []
        self.outputs = []

    def copy_to(self, ref, destination):
        assert ref == self.ref
        self.uploads.append(ref)
        Path(destination).write_bytes(self.content)

    def put_file(self, path):
        content = Path(path).read_bytes()
        ref = ArtifactRef("objects/" + hashlib.sha256(content).hexdigest(), "1",
                          hashlib.sha256(content).hexdigest())
        self.outputs.append((ref, content))
        return ref


class MemoryWriter:
    def __init__(self, persistence, project_revision=None):
        self.persistence = persistence
        self.project_revision = project_revision
        self.released = False
        self.release_error = False

    def load(self, workspace):
        if self.project_revision is not None:
            data = self.persistence.project_data or {"title": "accepted"}
            (Path(workspace) / "project.json").write_text(json.dumps(data), encoding="utf-8")
        return self.project_revision

    def release(self):
        if self.release_error:
            raise OSError("writer release response was lost")
        self.released = True
        self.persistence.events.append("release")
        self.persistence.release_order.append("release")


class MemoryPersistence:
    def __init__(self, revision=None):
        self.revision = revision
        self.project_data = None
        self.writer = None
        self.release_order = []
        self.release_error = False
        self.events = []

    def acquire(self, project_id, owner_id):
        assert project_id == PROJECT_ID
        assert owner_id.startswith(f"hosted-{OPERATION_ID}-")
        self.writer = MemoryWriter(self, self.revision)
        self.writer.release_error = self.release_error
        return self.writer

    def current(self, project_id):
        return self.revision


class CloudRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.value = operation()
        self.store = MemoryOperationStore(self.value)
        self.persistence = MemoryPersistence()
        self.store.events = self.persistence.events
        self.artifacts = MemoryArtifacts()
        self.runtime = CloudRuntime(
            self.store,
            self.persistence,
            self.artifacts,
            self.root,
            source_verifier=self.verify_source,
            stop_process=lambda: None,
        )
        self.executions = []

    def tearDown(self):
        self.temporary.cleanup()

    def verify_source(self, op, request, *, root):
        self.assertEqual(request["project"], PROJECT_ID)
        if op.payload.get("cloud_uploads"):
            self.assertEqual((Path(root) / "uploads" / UPLOAD_TOKEN / "chapter.zip").read_bytes(),
                             self.artifacts.content)

    def test_duplicate_delivery_exits_before_writer_or_engine(self):
        self.store.duplicate = True
        called = []
        self.runtime.perform_operation = lambda *args, **kwargs: called.append("engine")

        self.assertFalse(self.runtime.run(OperationClaim(OPERATION_ID, 7), "execution-one"))

        self.assertEqual(called, [])
        self.assertIsNone(self.persistence.writer)

    def _ocr_runtime(self, texts=None):
        payload = {
            "action": "ocr",
            "upload_token": UPLOAD_TOKEN,
            "cloud_uploads": {"panel.png": vars(self.artifacts.ref)},
            "source_hashes": [self.artifacts.ref.sha256],
        }
        self.value = operation(payload=payload, stage="magi")
        self.store.value = self.value
        verified = []

        def verify(op, request, *, root):
            image = Path(root) / "uploads" / UPLOAD_TOKEN / "panel.png"
            self.assertEqual(request["action"], "ocr")
            self.assertEqual(op.source_fingerprint, "source")
            self.assertTrue(image.is_file())
            verified.append(image)

        runtime = CloudRuntime(
            self.store,
            self.persistence,
            self.artifacts,
            self.root,
            extractor=lambda image: {"texts": texts if texts is not None else ["line one", "line two"]},
            source_verifier=verify,
            stop_process=lambda: None,
        )
        return runtime, verified

    def test_ocr_materializes_verified_panel_and_completes_only_text_result_without_project_write(self):
        runtime, verified = self._ocr_runtime()

        self.assertTrue(runtime.run(OperationClaim(OPERATION_ID, 7), "magi-execution"))

        self.assertEqual(len(verified), 1)
        self.assertEqual(self.store.completed, {"texts": ["line one", "line two"]})
        self.assertIsNone(self.persistence.writer)
        self.assertEqual(self.persistence.release_order, [])
        self.assertFalse((self.root / "attempts" / OPERATION_ID / "7" / "projects").exists())
        self.assertEqual(self.store.order, ["complete"])

    def test_duplicate_ocr_execution_does_not_extract_twice(self):
        runtime, _ = self._ocr_runtime()
        self.store.duplicate = True
        extracted = []
        runtime.extractor = lambda image: extracted.append(image)

        self.assertFalse(runtime.run(OperationClaim(OPERATION_ID, 7), "magi-duplicate"))

        self.assertEqual(extracted, [])
        self.assertIsNone(self.store.completed)
        self.assertIsNone(self.persistence.writer)

    def test_fenced_ocr_completion_is_not_accepted(self):
        runtime, _ = self._ocr_runtime()
        self.store.reject_completion = True

        self.assertTrue(runtime.run(OperationClaim(OPERATION_ID, 7), "magi-stale"))

        self.assertIsNone(self.store.completed)
        self.assertEqual(self.store.failures[0][1], "stale_fence")
        self.assertIsNone(self.persistence.writer)

    def test_heartbeat_fence_loss_during_ocr_prevents_result_completion(self):
        runtime, _ = self._ocr_runtime()
        self.store.lose_heartbeat = True
        self.store.policy = OperationPolicy(heartbeat_seconds=1, lease_seconds=120)

        def wait_for_fence_loss(image):
            self.assertTrue(self.store.heartbeat_lost.wait(timeout=2))
            return {"texts": ["must not be accepted"]}

        runtime.extractor = wait_for_fence_loss
        self.assertTrue(runtime.run(OperationClaim(OPERATION_ID, 7), "magi-heartbeat-lost"))

        self.assertIsNone(self.store.completed)
        self.assertEqual(self.store.failures[0][1], "stale_fence")
        self.assertIsNone(self.persistence.writer)

    def test_invalid_ocr_response_has_sanitized_failure(self):
        runtime, _ = self._ocr_runtime()
        runtime.extractor = lambda image: {"texts": ["valid", 7], "secret": "provider content"}

        self.assertTrue(runtime.run(OperationClaim(OPERATION_ID, 7), "magi-invalid"))

        self.assertIsNone(self.store.completed)
        self.assertEqual(self.store.failures, [("OCR returned an invalid response.", "invalid_ocr_response", False)])
        self.assertIsNone(self.persistence.writer)

    def test_persisted_uploads_and_request_are_the_only_engine_inputs(self):
        self.value = operation(payload={
            "project": PROJECT_ID,
            "action": "create",
            "mode": "chapter",
            "upload_token": UPLOAD_TOKEN,
            "source_hashes": [],
            "cloud_uploads": {"chapter.zip": vars(self.artifacts.ref)},
            "title": "trusted persisted title",
        })
        self.store.value = self.value

        def perform(router, request, progress, **kwargs):
            self.executions.append((request.copy(), Path(kwargs["root"])))
            return {"accepted": True}

        self.runtime.perform_operation = perform
        self.assertTrue(self.runtime.run(OperationClaim(OPERATION_ID, 7), "projects/test/locations/r/jobs/pipeline/executions/e1"))

        request, scratch = self.executions[0]
        self.assertEqual(request["title"], "trusted persisted title")
        self.assertEqual(request["project"], PROJECT_ID)
        self.assertEqual(scratch, self.root / "attempts" / OPERATION_ID / "7")
        self.assertEqual(self.artifacts.uploads, [self.artifacts.ref])
        self.assertEqual(self.store.completed["accepted"], True)
        self.assertTrue(self.persistence.writer.released)
        self.assertEqual(self.persistence.release_order, ["release"])

    def test_checkpoint_requires_committed_revision_and_completion_follows_release(self):
        project = {"title": "durably accepted"}
        project_hash = digest(project)
        revision = ProjectRevision("revision-8", None, self.artifacts.ref, project_hash, 8)
        self.persistence.revision = revision
        self.persistence.project_data = project
        self.value = operation(payload={
            "project": PROJECT_ID,
            "action": "create",
            "mode": "chapter",
            "upload_token": UPLOAD_TOKEN,
            "source_hashes": [],
            "cloud_uploads": {},
            "project_revision_id": "revision-8",
        })
        self.store.value = self.value

        def perform(router, request, progress, **kwargs):
            project_path = self.root / "attempts" / OPERATION_ID / "7" / "projects" / PROJECT_ID / "project.json"
            project_path.write_text(json.dumps(project), encoding="utf-8")
            progress("Planning accepted.", stage="planning", status="complete")
            return {"planned": True}

        self.runtime.perform_operation = perform
        self.runtime.run(OperationClaim(OPERATION_ID, 7), "projects/test/locations/r/jobs/pipeline/executions/e2")

        checkpoint = next(item[1] for item in self.store.progress if item[1] is not None)
        self.assertEqual(checkpoint["project_hash"], project_hash)
        self.assertEqual(checkpoint["revision_id"], "revision-8")
        self.assertEqual(self.store.progress[-1][2], True)
        self.assertEqual(self.persistence.release_order + self.store.order[-1:], ["release", "complete"])
        self.assertEqual(self.store.completed["project_revision_id"], "revision-8")

    def test_failure_after_provider_boundary_keeps_ambiguous_outcome_for_reconciliation(self):
        def perform(router, request, progress, *, before_provider, **kwargs):
            before_provider()
            raise RuntimeError("provider text must not leak")

        self.runtime.perform_operation = perform
        self.runtime.run(OperationClaim(OPERATION_ID, 7), "projects/test/locations/r/jobs/pipeline/executions/e3")

        self.assertEqual(self.store.value.status, "reconciliation_required")
        self.assertTrue(self.store.value.provider_outcome_pending)
        self.assertNotIn("provider text", self.store.failures[0][0])
        self.assertEqual(self.store.failures[0][1], "worker_failed")
        self.assertTrue(self.persistence.writer.released)
        self.assertLess(self.store.order.index("provider_pending"), self.store.order.index("fail"))
        self.assertLess(self.store.events.index("release"), self.store.events.index("fail"))

    def test_provider_base_revision_is_checkpointed_before_pending_and_keeps_render_baseline(self):
        accepted = ProjectRevision("revision-base", None, self.artifacts.ref, "d" * 64, 5)
        self.persistence.revision = accepted
        self.value = operation(
            payload={
                "project": PROJECT_ID,
                "action": "plan",
                "revision": "revision-base",
                "project_revision_id": "revision-base",
                "cloud_uploads": {},
            },
            checkpoint={"baseline_take_ids": ["take-existing"], "segment_id": "seg-3"},
        )
        self.store.value = self.value
        self.store.checkpoint = self.value.checkpoint

        def perform(router, request, progress, *, before_provider, **kwargs):
            before_provider()
            return {}

        self.runtime.perform_operation = perform
        self.runtime.run(OperationClaim(OPERATION_ID, 7), "projects/test/locations/r/jobs/pipeline/executions/e5")

        self.assertEqual(self.store.checkpoint, {
            "baseline_take_ids": ["take-existing"],
            "segment_id": "seg-3",
            "provider_base_revision_id": "revision-base",
        })
        self.assertEqual(self.store.order[:2], ["checkpoint", "provider_pending"])

    def test_writer_release_failure_holds_operation_for_reconciliation(self):
        self.persistence.release_error = True
        self.runtime.perform_operation = lambda router, request, progress, **kwargs: {"done": True}

        self.runtime.run(OperationClaim(OPERATION_ID, 7), "projects/test/locations/r/jobs/pipeline/executions/e6")

        self.assertEqual(self.store.failures, [])
        self.assertIn("uncertain", self.store.order)
        self.assertIsNone(self.store.completed)
        self.assertEqual(self.store.value.status, "reconciliation_required")

    def test_retry_can_reuse_only_an_exact_accepted_checkpoint(self):
        accepted_project = {"title": "accepted checkpoint"}
        accepted_hash = digest(accepted_project)
        current = ProjectRevision("revision-later", "revision-pinned", self.artifacts.ref, accepted_hash, 9)
        self.persistence.revision = current
        self.persistence.project_data = accepted_project
        self.value = operation(
            payload={
                "project": PROJECT_ID,
                "action": "render",
                "revision": "revision-pinned",
                "project_revision_id": "revision-pinned",
                "cloud_uploads": {},
            },
            checkpoint={"project_hash": accepted_hash, "revision_id": "revision-later", "segment_id": "seg-4"},
        )
        self.store.value = self.value

        self.runtime.perform_operation = lambda router, request, progress, **kwargs: {
            "resumed_from": request["project_revision_id"]
        }
        self.assertTrue(self.runtime.run(OperationClaim(OPERATION_ID, 7), "projects/test/locations/r/jobs/pipeline/executions/e4"))
        self.assertEqual(self.store.completed["resumed_from"], "revision-later")

    def test_actual_project_persistence_restores_accepted_revision_after_runtime_restart(self):
        fixture = fixtures.PipelineTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        artifacts = InMemoryArtifactStore()
        persistence = ProjectPersistence(artifacts, InMemoryRevisionStore())
        seed = persistence.acquire(PROJECT_ID, "seed-writer")
        base_project = schemas.dump(fixture.router.project)
        base = seed.commit(fixture.router.root, base_project, expected_revision_id=None)
        seed.release()
        payload = {
            "project": PROJECT_ID,
            "action": "rename",
            "revision": digest(base_project),
            "project_revision_id": base.revision_id,
            "cloud_uploads": {},
        }
        first_store = MemoryOperationStore(operation(payload=payload))

        def commit_reviewed_change(router, request, progress, **kwargs):
            router.load_project()
            router.update_metadata({"title": "Accepted by first execution"})
            progress("Change saved.", status="saved", segment_id="seg-accepted")
            return {"changed": True}

        first_runtime = CloudRuntime(
            first_store,
            persistence,
            artifacts,
            self.root,
            perform_operation=commit_reviewed_change,
            source_verifier=lambda *args, **kwargs: None,
            stop_process=lambda: None,
        )
        first_runtime.run(
            OperationClaim(OPERATION_ID, 7),
            "projects/test/locations/r/jobs/pipeline/executions/e7",
        )
        accepted = persistence.current(PROJECT_ID)
        self.assertIsNotNone(accepted)
        self.assertEqual(first_store.checkpoint["revision_id"], accepted.revision_id)
        self.assertEqual(first_store.completed["project_revision_id"], accepted.revision_id)

        retry_operation = replace(
            operation(payload=payload, checkpoint=first_store.checkpoint),
            fence=8,
            attempt_count=2,
        )
        retry_store = MemoryOperationStore(retry_operation)
        observed_titles = []

        def restore_checkpoint(router, request, progress, **kwargs):
            router.load_project()
            observed_titles.append(router.project.title)
            return {"resumed": True}

        retry_runtime = CloudRuntime(
            retry_store,
            persistence,
            artifacts,
            self.root,
            perform_operation=restore_checkpoint,
            source_verifier=lambda *args, **kwargs: None,
            stop_process=lambda: None,
        )
        retry_runtime.run(
            OperationClaim(OPERATION_ID, 8),
            "projects/test/locations/r/jobs/pipeline/executions/e8",
        )

        self.assertEqual(observed_titles, ["Accepted by first execution"])
        self.assertEqual(retry_store.completed["project_revision_id"], accepted.revision_id)


if __name__ == "__main__":
    unittest.main()
