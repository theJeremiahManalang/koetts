"""Finite operation worker interruption, reconciliation, and checkpoint reuse."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import test_audio_pipeline as fixtures

import web_workflow
from manga_tts import PipelineConfig, PipelineRouter, schemas
from manga_tts.operations import LocalOperationService, SQLiteOperationStore
from manga_tts.storage import read_json


class OperationWorkerProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = fixtures.PipelineTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.approve()
        self.root = fixture.root / "web"
        self.project_id = uuid.uuid4().hex
        self.workspace = self.root / "projects" / self.project_id
        shutil.copytree(fixture.router.root, self.workspace)
        root_patch = patch.object(web_workflow, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.store = SQLiteOperationStore(self.root / "operations.sqlite3")

    def spawn(self, operation_id: str, fence: int, mode: str) -> subprocess.Popen:
        repository = Path(__file__).resolve().parents[1]
        environment = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join([str(repository), str(repository / "tests")]),
            "GEMINI_API_KEY": "",
        }
        process = subprocess.Popen(
            [sys.executable, str(repository / "tests/operation_worker_process.py"),
             str(self.root), operation_id, str(fence), mode],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        def cleanup() -> None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)

        self.addCleanup(cleanup)
        return process

    def test_interrupted_render_resumes_after_operator_resolution_without_repeating_saved_segment(self) -> None:
        router = PipelineRouter(PipelineConfig(workspace=self.workspace))
        router.load_project()
        request = {
            "action": "render",
            "project": self.project_id,
            "revision": web_workflow.snapshot(router)["revision"],
            "command": {"scene_ids": ["scene_001"], "regenerate": []},
        }
        operation = self.store.enqueue(
            idempotency_key="interrupted-render",
            payload=request,
            project_id=self.project_id,
            stage="pipeline",
            revision=request["revision"],
            source_fingerprint=web_workflow.operation_source_fingerprint(request),
            configuration_fingerprint="render-v1",
        )
        first_claim = self.store.claim(operation.operation_id)
        assert first_claim is not None
        child = self.spawn(operation.operation_id, first_claim.fence, "interrupt")
        deadline = time.monotonic() + 30
        while not (self.root / "second-segment-started").exists():
            self.assertIsNone(child.poll(), "Worker exited before the interruption barrier")
            self.assertLess(time.monotonic(), deadline, "Render checkpoint barrier timed out")
            time.sleep(.02)

        saved_state = read_json(self.workspace / "project.json")
        saved_takes = [take for group in saved_state["takes"].values() for take in group]
        self.assertEqual(len(saved_takes), 1)
        first_take = saved_takes[0]
        first_audio = self.workspace / first_take["path"]
        first_audio_hash = hashlib.sha256(first_audio.read_bytes()).hexdigest()
        self.assertEqual(first_audio_hash, first_take["audio_sha256"])

        child.kill()
        child.wait(timeout=10)
        service = LocalOperationService(self.store)
        recovered = service.reconcile_expired(
            web_workflow.recover_operation_workspace,
            now=time.time() + self.store.policy.lease_seconds + 1,
        )
        self.assertEqual(recovered[0].status, "reconciliation_required")
        checkpoint = self.store.get(operation.operation_id).checkpoint
        assert checkpoint is not None
        self.assertEqual(checkpoint["segment_id"], "scene_001_001")

        self.store.resolve_uncertain(operation.operation_id, "retry")
        second_claim = self.store.claim(operation.operation_id)
        assert second_claim is not None
        result = self.spawn(operation.operation_id, second_claim.fence, "normal")
        self.assertEqual(result.wait(timeout=30), 0)

        completed = self.store.get(operation.operation_id)
        self.assertEqual(completed.status, "complete")
        self.assertEqual(len((self.root / "render-calls.jsonl").read_text().splitlines()), 3)
        final_state = read_json(self.workspace / "project.json")
        final_takes = [take for group in final_state["takes"].values() for take in group]
        self.assertEqual(len(final_takes), 2)
        retained = next(take for take in final_takes if take["take_id"] == first_take["take_id"])
        self.assertEqual(hashlib.sha256((self.workspace / retained["path"]).read_bytes()).hexdigest(), first_audio_hash)

    def test_worker_stopped_between_segments_requeues_from_saved_checkpoint(self) -> None:
        self.check_worker_stopped_between_segments([])

    def test_saved_planning_proposal_completes_after_restart_without_provider_call(self) -> None:
        router = PipelineRouter(PipelineConfig(workspace=self.workspace))
        router.load_project()
        operation = web_workflow.enqueue_operation({
            "action": "plan", "project": self.project_id,
            "revision": web_workflow.snapshot(router)["revision"],
        }, "planning-checkpoint")
        claim = self.store.claim(operation.operation_id)
        assert claim is not None
        child = self.spawn(operation.operation_id, claim.fence, "plan-checkpoint")
        deadline = time.monotonic() + 30
        while not (self.root / "first-segment-saved").exists():
            self.assertIsNone(child.poll(), "Worker exited before saving proposal")
            self.assertLess(time.monotonic(), deadline, "Planning checkpoint timed out")
            time.sleep(.02)
        accepted = read_json(self.workspace / "project.json")
        self.assertIsNotNone(accepted["proposal"])
        child.kill()
        child.wait(timeout=10)
        recovered = LocalOperationService(self.store).reconcile_expired(
            web_workflow.recover_operation_workspace,
            now=time.time() + self.store.policy.lease_seconds + 1,
        )
        self.assertEqual(recovered[0].status, "queued")
        (self.root / "planning-called").unlink()
        retry = self.store.claim(operation.operation_id)
        assert retry is not None
        resumed = self.spawn(operation.operation_id, retry.fence, "plan-normal")
        self.assertEqual(resumed.wait(timeout=30), 0)
        self.assertEqual(self.store.get(operation.operation_id).status, "complete")
        self.assertFalse((self.root / "planning-called").exists())
        self.assertEqual(read_json(self.workspace / "project.json"), accepted)

    def test_forced_regeneration_resumes_without_repeating_accepted_replacement(self) -> None:
        self.check_worker_stopped_between_segments(["scene_001_001", "scene_001_002"])

    def test_forced_regeneration_recovers_commit_before_progress_notification(self) -> None:
        self.check_worker_stopped_between_segments(
            ["scene_001_001", "scene_001_002"], mode="before-notification",
        )

    def test_forced_regeneration_recovers_failed_progress_notification(self) -> None:
        self.check_worker_stopped_between_segments(
            ["scene_001_001", "scene_001_002"], mode="failed-notification",
        )

    def check_worker_stopped_between_segments(self, regenerate: list[str], mode="between-checkpoints") -> None:
        router = PipelineRouter(
            PipelineConfig(workspace=self.workspace), client_factory=lambda: object(),
            renderer_factory=lambda _client, _model: lambda request: fixtures.wav_bytes(),
        )
        router.load_project()
        if regenerate:
            router.render_selected(schemas.RenderCommand(scene_ids=["scene_001"], regenerate=[]))
        initial_takes = {
            take["take_id"] for group in read_json(self.workspace / "project.json")["takes"].values() for take in group
        }
        revision = web_workflow.snapshot(router)["revision"]
        request = {
            "action": "render",
            "project": self.project_id,
            "revision": revision,
            "command": {"scene_ids": ["scene_001"], "regenerate": regenerate},
        }
        operation = self.store.enqueue(
            idempotency_key="safe-checkpoint-restart",
            payload=request,
            project_id=self.project_id,
            stage="pipeline",
            revision=revision,
            source_fingerprint=web_workflow.operation_source_fingerprint(request),
            configuration_fingerprint="render-v1",
        )
        first_claim = self.store.claim(operation.operation_id)
        assert first_claim is not None
        child = self.spawn(operation.operation_id, first_claim.fence, mode)
        deadline = time.monotonic() + 30
        while not (self.root / "first-segment-saved").exists():
            self.assertIsNone(child.poll(), "Worker exited before persisting the first segment")
            self.assertLess(time.monotonic(), deadline, "Render checkpoint barrier timed out")
            time.sleep(.02)

        state = read_json(self.workspace / "project.json")
        takes = [take for group in state["takes"].values() for take in group]
        self.assertEqual(len(takes), len(initial_takes) + 1)
        first_take = next(take for take in takes if take["take_id"] not in initial_takes)
        first_hash = hashlib.sha256((self.workspace / first_take["path"]).read_bytes()).hexdigest()

        if mode != "failed-notification":
            child.kill()
        child.wait(timeout=10)
        if mode == "failed-notification":
            self.assertEqual(self.store.get(operation.operation_id).status, "reconciliation_required")
            web_workflow.reconcile_operation(operation.operation_id, "retry")
        else:
            recovered = LocalOperationService(self.store).reconcile_expired(
                web_workflow.recover_operation_workspace,
                now=time.time() + self.store.policy.lease_seconds + 1,
            )
            if mode == "before-notification":
                self.assertEqual(recovered[0].status, "reconciliation_required")
                web_workflow.reconcile_operation(operation.operation_id, "retry")
            else:
                self.assertEqual(recovered[0].status, "queued")
                self.assertFalse(recovered[0].provider_outcome_pending)

        second_claim = self.store.claim(operation.operation_id)
        assert second_claim is not None
        resumed = self.spawn(operation.operation_id, second_claim.fence, "normal")
        self.assertEqual(resumed.wait(timeout=30), 0)

        self.assertEqual(self.store.get(operation.operation_id).status, "complete")
        self.assertEqual(len((self.root / "render-calls.jsonl").read_text().splitlines()), 2)
        final = read_json(self.workspace / "project.json")
        retained = next(
            take
            for group in final["takes"].values()
            for take in group
            if take["take_id"] == first_take["take_id"]
        )
        self.assertEqual(hashlib.sha256((self.workspace / retained["path"]).read_bytes()).hexdigest(), first_hash)


if __name__ == "__main__":
    unittest.main()
