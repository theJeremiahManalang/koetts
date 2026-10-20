"""Optional read-only compatibility check against a supplied output project.

Set MANGA_TTS_SAMPLE_PROJECT to the unpacked project directory. All rendering and
export writes happen in a temporary copy; no credentials or provider calls.
"""
import hashlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from manga_tts import PipelineConfig, PipelineRouter
from manga_tts.schemas import RenderCommand, RenderSelection


@unittest.skipUnless(os.environ.get("MANGA_TTS_SAMPLE_PROJECT"), "No external sample supplied")
class SampleCompatibilityTests(unittest.TestCase):
    def test_saved_project_reproduces_existing_audio(self):
        source = Path(os.environ["MANGA_TTS_SAMPLE_PROJECT"])
        expected = hashlib.sha256((source / "exports/chapter_narration.wav").read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "project"
            shutil.copytree(source, root)
            def forbidden():
                self.fail("Sample reuse unexpectedly requested an API client")
            router = PipelineRouter(PipelineConfig(workspace=root), client_factory=forbidden)
            project = router.load_project()
            scenes = [s.scene_id for s in project.scenes]
            router.render_selected(RenderCommand(scene_ids=scenes))
            result = router.export_audio(RenderSelection(scene_ids=scenes))
            self.assertEqual(hashlib.sha256(Path(result.wav_path).read_bytes()).hexdigest(), expected)
            bundle = router.bundle_project(Path(td) / "saved.zip")
            restored = PipelineRouter(PipelineConfig(workspace=Path(td) / "restored"), client_factory=forbidden)
            restored.restore_project(bundle)
            result = restored.export_audio(RenderSelection(scene_ids=scenes))
            self.assertEqual(hashlib.sha256(Path(result.wav_path).read_bytes()).hexdigest(), expected)
