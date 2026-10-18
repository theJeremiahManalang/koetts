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
        self.assertEqual(state["pages"][0]["original_path"], "input/page_001.png")
        self.assertEqual(state["pages"][0]["annotated_path"], "input/previews/page_001_annotated.jpg")
        self.assertNotIn("api_key", state["project"])

    def test_snapshot_handles_missing_image_variants(self):
        (self.workspace / "input/previews/page_001_annotated.jpg").unlink()
        self.assertIsNone(self.current()["pages"][0]["annotated_path"])
        self.assertEqual(self.current()["pages"][0]["original_path"], "input/page_001.png")
        (self.workspace / "input/page_001.png").unlink()
        page = self.current()["pages"][0]
        self.assertIsNone(page["original_path"])
        self.assertIsNone(page["preview_path"])

    def test_rename_persists_without_invalidating_approvals(self):
        before = self.current()
        result = self.job("rename", {"title": "  My Manga Chapter  "})
        self.assertEqual(result["status"], "complete", result)
        after = self.current()
        self.assertEqual(after["project"]["title"], "My Manga Chapter")
        self.assertEqual(after["project"]["chapter_id"], before["project"]["chapter_id"])
        self.assertEqual(after["approved_scenes"], before["approved_scenes"])
        self.assertEqual(after["cast_approved"], before["cast_approved"])
        saved = (self.workspace / "project.json").read_bytes()
        for title in ("", " ", "x" * 121, "bad\ntitle", 123):
            self.assertEqual(self.job("rename", {"title": title})["status"], "failed")
            self.assertEqual((self.workspace / "project.json").read_bytes(), saved)

    def test_source_review_status_is_saved_and_invalidated(self):
        state = self.current()
        self.assertFalse(state["workflow_status"]["sources_reviewed"])
        fields = ("source_id", "include", "speaker_id", "text", "delivery", "emotion", "style", "pacing", "order", "scene_id", "turn_group", "reaction")
        command = {"sources": [{k: s[k] for k in fields} for s in state["project"]["sources"]]}
        result = self.job("sources", command)
        self.assertEqual(result["status"], "complete", result)
        self.assertTrue(self.current()["workflow_status"]["sources_reviewed"])
        project = read_json(self.workspace / "project.json")
        project["sources"][0]["text"] += " changed"
        write_json(self.workspace / "project.json", project)
        self.assertFalse(self.current()["workflow_status"]["sources_reviewed"])

    def test_scene_batch_is_atomic_and_saves_explicit_approvals(self):
        project = read_json(self.workspace / "project.json")
        project["scenes"].append({"scene_id": "scene_002", "title": "Second scene", "context": "", "turns": []})
        write_json(self.workspace / "project.json", project)
        fields = ("turn_id", "include", "speaker_id", "text", "delivery", "emotion", "style", "pacing", "silence_sec")
        first = project["scenes"][0]
        command = {"scenes": [{"scene_id": first["scene_id"], "title": "Reviewed first scene", "context": first["context"], "turns": [{k: t[k] for k in fields} for t in first["turns"]], "approve": True}, {"scene_id": "scene_002", "title": "Second scene", "context": "Saved second draft", "turns": [], "approve": False}]}
        saved = (self.workspace / "project.json").read_bytes()
        invalid = json.loads(json.dumps(command))
        invalid["scenes"][1]["scene_id"] = "missing"
        self.assertEqual(self.job("script-batch", invalid)["status"], "failed")
        self.assertEqual((self.workspace / "project.json").read_bytes(), saved)
        invalid = {"scenes": [command["scenes"][0], command["scenes"][0]]}
        self.assertEqual(self.job("script-batch", invalid)["status"], "failed")
        self.assertEqual((self.workspace / "project.json").read_bytes(), saved)
        result = self.job("script-batch", command)
        self.assertEqual(result["status"], "complete", result)
        state = self.current()
        self.assertEqual(state["project"]["scenes"][0]["title"], "Reviewed first scene")
        self.assertEqual(state["project"]["scenes"][1]["context"], "Saved second draft")
        self.assertEqual(state["approved_scenes"], [first["scene_id"]])

    def test_image_and_panel_order_persist_without_changing_image_identity(self):
        project = read_json(self.workspace / "project.json")
        page = project["chapter"]["pages"][0]
        second = json.loads(json.dumps(page))
        second.update(page_id="page_002", page_index=2, image_filename="page_002.png")
        project["chapter"]["pages"].append(second)
        write_json(self.workspace / "project.json", project)
        fields = ("source_id", "include", "speaker_id", "text", "delivery", "emotion", "style", "pacing", "order", "scene_id", "turn_group", "reaction")
        panels = [p["panel_id"] for p in page["panels"]]
        command = {"sources": [{k: s[k] for k in fields} for s in project["sources"]], "page_order": ["page_002", page["page_id"]], "panel_order": {page["page_id"]: list(reversed(panels))}}
        result = self.job("sources", command)
        self.assertEqual(result["status"], "complete", result)
        state = self.current()
        self.assertEqual([p["page_id"] for p in state["pages"]], command["page_order"])
        original = next(p for p in state["pages"] if p["page_id"] == page["page_id"])
        self.assertEqual(original["preview_path"], "input/page_001.png")
        self.assertEqual(original["annotated_path"], "input/previews/page_001_annotated.jpg")
        self.assertEqual([p["panel_id"] for p in original["panels"]], list(reversed(panels)))
        self.assertTrue(state["workflow_status"]["sources_reviewed"])
        saved = (self.workspace / "project.json").read_bytes()
        invalid = json.loads(json.dumps(command))
        invalid["page_order"] = [page["page_id"], page["page_id"]]
        self.assertEqual(self.job("sources", invalid)["status"], "failed")
        self.assertEqual((self.workspace / "project.json").read_bytes(), saved)
        invalid = json.loads(json.dumps(command))
        invalid["panel_order"] = {page["page_id"]: ["unknown_panel"]}
        self.assertEqual(self.job("sources", invalid)["status"], "failed")
        self.assertEqual((self.workspace / "project.json").read_bytes(), saved)

    def test_batch_cast_saves_new_characters_and_assignments_together(self):
        before = self.current()["project"]
        fields = ("name", "voice", "pronunciation", "acting_notes")
        cast = [{"speaker_id": sid, **{k: c.get(k, "") for k in fields}} for sid, c in before["cast"].items()]
        cast.append({"speaker_id": "CHARACTER_batch", "name": "Batch character", "voice": "Kore", "pronunciation": "", "acting_notes": ""})
        appearances = [{"char_id": a["char_id"], "speaker_id": "CHARACTER_batch", "rejected": False} for a in before["appearances"]]
        command = {"cast": cast, "appearances": appearances, "new_characters": [{"speaker_id": "CHARACTER_batch", "char_id": appearances[0]["char_id"]}], "approve": True}
        saved = (self.workspace / "project.json").read_bytes()
        invalid = json.loads(json.dumps(command))
        invalid["new_characters"][0]["char_id"] = "missing"
        self.assertEqual(self.job("cast", invalid)["status"], "failed")
        self.assertEqual((self.workspace / "project.json").read_bytes(), saved)
        result = self.job("cast", command)
        self.assertEqual(result["status"], "complete", result)
        current = self.current()
        self.assertTrue(current["cast_approved"])
        self.assertTrue(all(a["speaker_id"] == "CHARACTER_batch" for a in current["project"]["appearances"]))
        self.assertEqual(current["project"]["cast"]["CHARACTER_batch"]["references"], ["input/" + before["appearances"][0]["crop_path"]])
        self.assertNotIn("pending_characters", current["project"])

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
        self.assertEqual(self.current()["workflow_status"]["audio_ready_scenes"], [])
        real_router = PipelineRouter
        patch.object(web_workflow, "PipelineRouter", lambda config: real_router(config, client_factory=lambda: object(), renderer_factory=lambda c, m: lambda request: fixtures.wav_bytes())).start()
        state = self.job("render", {"scene_ids": ["scene_001"], "regenerate": []})
        self.assertEqual(state["status"], "complete")
        self.assertEqual(len(state["result"]["segments"]), 2)
        self.assertEqual(self.current()["workflow_status"]["audio_ready_scenes"], ["scene_001"])
        self.assertEqual(self.job("export", {"scene_ids": ["scene_001"]})["status"], "complete")
        self.assertEqual(self.current()["workflow_status"]["exported_scenes"], ["scene_001"])
        self.assertEqual(self.job("rename", {"title": "Exported chapter"})["status"], "complete")
        self.assertEqual(self.current()["workflow_status"]["exported_scenes"], ["scene_001"])
        self.assertTrue((self.workspace / "exports/chapter_narration.wav").is_file())
        self.assertEqual(self.job("bundle")["status"], "complete")
        self.assertTrue((self.root / "downloads" / (self.project_id + ".zip")).is_file())
        import zipfile
        with zipfile.ZipFile(self.root / "downloads" / (self.project_id + ".zip")) as bundle:
            self.assertEqual(json.loads(bundle.read("project.json"))["title"], "Exported chapter")
        project = read_json(self.workspace / "project.json")
        project["settings"]["scene_pause"] += .1
        write_json(self.workspace / "project.json", project)
        self.assertEqual(self.current()["workflow_status"]["exported_scenes"], [])
        project["settings"]["scene_pause"] -= .1
        write_json(self.workspace / "project.json", project)
        self.assertEqual(self.current()["workflow_status"]["audio_ready_scenes"], ["scene_001"])
        take = next(iter(project["takes"].values()))[0]
        (self.workspace / take["path"]).write_bytes(b"corrupted audio")
        self.assertEqual(self.current()["workflow_status"]["audio_ready_scenes"], [])

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

    def test_script_approval_explains_excluded_source_and_preserves_saved_work(self):
        from manga_tts.cli import review_document
        project = read_json(self.workspace / "project.json")
        turn = next(t for t in project["scenes"][0]["turns"] if t["include"] and t["source_ids"])
        source = next(s for s in project["sources"] if s["source_id"] == turn["source_ids"][0])
        source["include"] = False
        write_json(self.workspace / "project.json", project)
        router = PipelineRouter(PipelineConfig(workspace=self.workspace))
        router.load_project()
        command = review_document(router.project, "script", "scene_001")["command"]
        command["approve"] = True
        before = (self.workspace / "project.json").read_bytes()
        state = self.job("script-batch", {"scenes": [command]})
        self.assertEqual(state["status"], "failed")
        self.assertIn("excluded source", state["message"])
        self.assertIn("Uncheck Include", state["message"])
        self.assertEqual((self.workspace / "project.json").read_bytes(), before)

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
