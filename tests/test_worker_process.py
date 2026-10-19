"""Process interruption, writer exclusion, and recovery using temporary projects."""
import hashlib
import os
import shutil
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path

import test_audio_pipeline as fixtures

from manga_tts import PipelineConfig, PipelineRouter, schemas
from manga_tts.storage import read_json, write_json
from web_workflow import snapshot


class WorkerProcessTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.PipelineTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.approve()
        self.root = fixture.root / "web"
        self.project = uuid.uuid4().hex
        self.workspace = self.root / "projects" / self.project
        shutil.copytree(fixture.router.root, self.workspace)

    def router(self):
        router = PipelineRouter(PipelineConfig(workspace=self.workspace),
                                client_factory=lambda: self.fail("Unexpected provider client"))
        router.load_project()
        return router

    def request(self, action, command, revision=None):
        job = uuid.uuid4().hex
        write_json(self.root / "jobs" / (job + ".request.json"), {
            "project": self.project, "action": action, "command": command,
            "revision": revision if revision is not None else snapshot(self.router())["revision"],
        })
        return job

    def spawn(self, job, mode="normal"):
        repo = Path(__file__).resolve().parents[1]
        env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(repo), str(repo / "tests")]),
               "GEMINI_API_KEY": ""}
        child = subprocess.Popen([sys.executable, str(repo / "tests/worker_process.py"),
                                  str(self.root), job, mode], env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def cleanup():
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)
        self.addCleanup(cleanup)
        return child

    def finish(self, child, job):
        self.assertEqual(child.wait(timeout=20), 0)
        return read_json(self.root / "jobs" / (job + ".json"))

    def test_killed_worker_reuses_checkpoint_and_excludes_competing_writer(self):
        original_revision = snapshot(self.router())["revision"]
        job = self.request("render", {"scene_ids": ["scene_001"]})
        child = self.spawn(job, "interrupt")
        deadline = time.monotonic() + 20
        while not (self.root / "second-segment-started").exists():
            self.assertIsNone(child.poll(), "Worker exited before checkpoint barrier")
            self.assertLess(time.monotonic(), deadline, "Checkpoint barrier timed out")
            time.sleep(.02)
        state_path = self.workspace / "project.json"
        checkpoint = state_path.read_bytes()
        state = read_json(state_path)
        takes = [take for values in state["takes"].values() for take in values]
        self.assertEqual(len(takes), 1)
        take = takes[0]
        audio = self.workspace / take["path"]
        audio_before = audio.read_bytes()
        self.assertEqual(hashlib.sha256(audio_before).hexdigest(), take["audio_sha256"])
        lock = self.workspace.with_suffix(".lock")
        self.assertEqual(int(lock.read_text()), child.pid)

        competing = self.request("rename", {"title": "Rejected competing writer"})
        result = self.finish(self.spawn(competing), competing)
        self.assertEqual(result["status"], "failed")
        self.assertIn("locked", result["message"])
        self.assertEqual(state_path.read_bytes(), checkpoint)
        self.assertTrue(lock.exists())

        child.kill()
        child.wait(timeout=10)
        self.assertIsNotNone(child.returncode)
        self.assertTrue(lock.exists())
        self.assertEqual(state_path.read_bytes(), checkpoint)
        self.assertEqual(audio.read_bytes(), audio_before)
        self.assertEqual(read_json(self.root / "jobs" / (job + ".json"))["status"], "running")
        # Only this test-owned lock is removed, after its recorded owner has exited.
        lock.unlink()

        stale = self.request("rename", {"title": "Rejected stale edit"}, original_revision)
        result = self.finish(self.spawn(stale), stale)
        self.assertEqual(result["status"], "failed")
        self.assertIn("changed in another session", result["message"])
        self.assertEqual(state_path.read_bytes(), checkpoint)

        resumed = self.request("render", {"scene_ids": ["scene_001"]})
        result = self.finish(self.spawn(resumed), resumed)
        self.assertEqual(result["status"], "complete", result)
        self.assertFalse(lock.exists())
        self.assertEqual(len((self.root / "render-calls.jsonl").read_text().splitlines()), 3)
        self.assertEqual(audio.read_bytes(), audio_before)
        router = self.router()
        self.assertEqual(sum(map(len, router.project.takes.values())), 2)
        self.assertIn(take["take_id"], router.project.selected_takes.values())
        selection = schemas.RenderSelection(scene_ids=["scene_001"])
        exported = router.export_audio(selection)
        expected = hashlib.sha256(Path(exported.wav_path).read_bytes()).hexdigest()
        bundle = router.bundle_project(self.root / "recovered.zip")
        restored = PipelineRouter(PipelineConfig(workspace=self.root / "restored"),
                                  client_factory=lambda: self.fail("Unexpected provider client"))
        restored.restore_project(bundle)
        actual = restored.export_audio(selection)
        self.assertEqual(hashlib.sha256(Path(actual.wav_path).read_bytes()).hexdigest(), expected)
