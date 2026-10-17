"""Web worker integration without network, model weights, or API credentials."""
import json
import shutil
import unittest
from unittest.mock import patch
import uuid

from manga_tts import PipelineConfig, PipelineRouter
from manga_tts.storage import read_json, write_json
import test_audio_pipeline as fixtures
import web_workflow


class WebWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PipelineTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.approve()
        self.root = self.fixture.root / "web"
        self.project_id = uuid.uuid4().hex
        self.workspace = self.root / "projects" / self.project_id
        shutil.copytree(self.fixture.router.root, self.workspace)
        self.addCleanup(patch.stopall)
        patch.object(web_workflow, "ROOT", self.root).start()

    def current(self):
        router = PipelineRouter(PipelineConfig(workspace=self.workspace))
        router.load_project()
        return web_workflow.snapshot(router)

    def job(self, action, command=None, **extra):
        job_id = uuid.uuid4().hex
        data = {"action": action, "project": self.project_id, "revision": self.current()["revision"], "command": command or {}, **extra}
        write_json(self.root / "jobs" / f"{job_id}.request.json", data)
        web_workflow.run_job(job_id)
        return read_json(self.root / "jobs" / f"{job_id}.json")

    def test_snapshot_reports_approval_and_evidence(self):
        state = self.current()
        self.assertTrue(state["cast_approved"])
        self.assertEqual(state["approved_scenes"], ["scene_001"])
        self.assertEqual(state["pages"][0]["preview_path"], "input/page_001.png")
        self.assertNotIn("api_key", state["project"])

    def test_create_character_from_crop_without_reference_zip(self):
        state = self.current()
        appearance = state["project"]["appearances"][0]
        result = self.job("cast-create", {"char_id": appearance["char_id"], "name": "New character", "voice": "Kore"})
        self.assertEqual(result["status"], "complete", result)
        current = self.current()
        assigned = current["project"]["appearances"][0]
        member = current["project"]["cast"][assigned["speaker_id"]]
        self.assertEqual(member["name"], "New character")
        self.assertEqual(member["references"], ["input/" + appearance["crop_path"]])
        self.assertTrue((self.workspace / member["references"][0]).is_file())
        self.assertFalse(assigned["rejected"])
        self.assertFalse(current["cast_approved"])
        self.assertEqual(current["approved_scenes"], [])
        before = (self.workspace / "project.json").read_bytes()
        for command in ({"char_id": "missing", "name": "Other", "voice": "Kore"},
                        {"char_id": appearance["char_id"], "name": " ", "voice": "Kore"},
                        {"char_id": appearance["char_id"], "name": "New character", "voice": "Kore"}):
            self.assertEqual(self.job("cast-create", command)["status"], "failed")
            self.assertEqual((self.workspace / "project.json").read_bytes(), before)

    def test_inspect_render_export_and_bundle_jobs(self):
        state = self.job("inspect", {"scene_ids": ["scene_001"]})
        self.assertEqual(state["status"], "complete")
        self.assertEqual(len(state["result"]["segments"]), 2)
        real_router = PipelineRouter
        patch.object(web_workflow, "PipelineRouter", lambda config: real_router(config, client_factory=lambda: object(), renderer_factory=lambda c, m: lambda request: fixtures.wav_bytes())).start()
        state = self.job("render", {"scene_ids": ["scene_001"], "regenerate": []})
        self.assertEqual(state["status"], "complete")
        self.assertEqual(len(state["result"]["segments"]), 2)
        self.assertEqual(self.job("export", {"scene_ids": ["scene_001"]})["status"], "complete")
        self.assertTrue((self.workspace / "exports/chapter_narration.wav").is_file())
        self.assertEqual(self.job("bundle")["status"], "complete")
        self.assertTrue((self.root / "downloads" / (self.project_id + ".zip")).is_file())

    def test_stale_edits_fail_without_changing_project(self):
        before = (self.workspace / "project.json").read_bytes()
        state = self.job("settings", {}, revision="outdated")
        self.assertEqual(state["status"], "failed")
        self.assertIn("another session", state["message"])
        self.assertEqual((self.workspace / "project.json").read_bytes(), before)

    def test_validation_failure_does_not_echo_rejected_text(self):
        state = self.job("sources", {"sources": "PRIVATE_INVALID_TEXT"})
        self.assertEqual(state["status"], "failed")
        self.assertNotIn("PRIVATE_INVALID_TEXT", json.dumps(state))

    def test_restore_upload_job_and_staging_cleanup(self):
        project = uuid.uuid4().hex
        job = uuid.uuid4().hex
        staging = self.root / "uploads" / job
        staging.mkdir(parents=True)
        self.fixture.router.bundle_project(staging / "chapter.zip")
        write_json(self.root / "jobs" / f"{job}.request.json", {"project": project, "action": "create", "mode": "restore"})
        web_workflow.run_job(job)
        self.assertEqual(read_json(self.root / "jobs" / f"{job}.json")["status"], "complete")
        self.assertTrue((self.root / "projects" / project / "project.json").is_file())
        self.assertFalse(staging.exists())

    def test_reject_invalid_identifiers(self):
        for value in ("../project", "/tmp", "", "a" * 33):
            with self.assertRaises(ValueError):
                web_workflow.identifier(value)


if __name__ == "__main__":
    unittest.main()
