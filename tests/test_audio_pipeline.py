"""Offline integration tests: real files/contracts, synthetic predictions and PCM."""
import copy
import io
import json
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

from PIL import Image

from manga_tts import PipelineConfig, PipelineRouter, schemas
from manga_tts.cli import apply_review, review_document, workspace_lock
from manga_tts.extraction import extract_chapter, layout_order, reconcile_texts
from manga_tts.storage import extract_zip, read_json, recover_ocr


class FakeMagi:
    def predict(self, images, task):
        return {"detections": [{"panels": [[0, 0, 200, 200]],
                    "texts": [[100, 10, 190, 50], [10, 60, 90, 100], [100, 110, 190, 150]],
                    "characters": [[10, 100, 80, 190]], "character_cluster_labels": [0],
                    "is_essential_text": [True, True, True],
                    "text_character_associations": [[0, 0]]}],
                "ocr": [{"ocr_texts": ["Second line", "First line", "Third line"],
                         "bboxes": [[10, 60, 90, 100], [100, 10, 190, 50], [100, 110, 190, 150]]}]}


def wav_bytes(frames=2400):
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\x01\x00" * frames)
    return out.getvalue()


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.page = self.root / "page.png"
        Image.new("RGB", (200, 200), "white").save(self.page)
        self.chapter = extract_chapter([self.page], self.root / "chapter.zip", runner=FakeMagi())
        self.cast = self.root / "cast.zip"
        with zipfile.ZipFile(self.cast, "w") as z:
            z.writestr("cast.json", json.dumps({"characters": [
                {"speaker_id": s, "name": s, "is_generic": True, "voice": v}
                for s, v in [("A", "Kore"), ("B", "Puck"), ("C", "Leda")]]}))
        self.calls = []
        def render(request):
            self.calls.append(copy.deepcopy(request))
            return wav_bytes()
        self.router = PipelineRouter(PipelineConfig(workspace=self.root / "project"),
                                     client_factory=lambda: object(), renderer_factory=lambda c, m: render)
        self.router.create_project(self.chapter, self.cast)

    def approve(self):
        cast = review_document(self.router.project, "cast")
        for appearance in cast["command"]["appearances"]:
            appearance["speaker_id"] = "A"
        apply_review(self.router, cast, approve=True)
        sources = review_document(self.router.project, "sources")
        for source, speaker in zip(sources["command"]["sources"], ["A", "B", "C"]):
            source["speaker_id"] = speaker
        apply_review(self.router, sources)
        apply_review(self.router, review_document(self.router.project, "script", "scene_001"), approve=True)

    def test_extraction_order_and_ocr_are_independent(self):
        p = self.router.project
        self.assertEqual([s.text for s in p.sources], ["First line", "Second line", "Third line"])
        self.assertEqual(p.sources[0].magi_links[0]["char_id"], "p001_chr_01")
        self.assertTrue((self.router.root / "input/page_001.png").exists())
        self.assertIsNone(p.cast_approval)
        self.assertEqual(self.calls, [])

    def test_three_speakers_export_restore_and_offline_cache(self):
        self.approve()
        selection = schemas.RenderSelection(scene_ids=["scene_001"])
        segments = self.router.inspect_segments(selection)
        self.assertEqual(len(segments), 2)
        self.assertEqual(self.calls, [])
        self.router.render_selected(schemas.RenderCommand(scene_ids=selection.scene_ids))
        self.assertEqual(len(self.calls), 2)
        result = self.router.export_audio(selection)
        audio = Path(result.wav_path).read_bytes()
        with wave.open(result.wav_path) as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (1, 2, 24000))
            self.assertEqual(wav.getnframes(), 4800 + 2880)
        timeline = read_json(Path(result.export_directory) / "timeline.json")
        self.assertEqual(timeline["total_duration_sec"], .32)
        bundle = self.router.bundle_project(self.root / "project.zip")
        restored = PipelineRouter(PipelineConfig(workspace=self.root / "restored"))
        restored.restore_project(bundle)
        restored.render_selected(schemas.RenderCommand(scene_ids=selection.scene_ids))
        self.assertEqual(Path(restored.export_audio(selection).wav_path).read_bytes(), audio)

    def test_compiled_mp3_exports_all_or_specific_scenes_in_chapter_order(self):
        import subprocess

        from imageio_ffmpeg import get_ffmpeg_exe
        self.approve()
        draft = review_document(self.router.project, "sources")
        for index, source in enumerate(draft["command"]["sources"], 1):
            source["scene_id"] = f"scene_{index:03d}"
        apply_review(self.router, draft)
        ids = [scene.scene_id for scene in self.router.project.scenes]
        for scene_id in ids:
            apply_review(self.router, review_document(self.router.project, "script", scene_id), approve=True)
        self.router.render_selected(schemas.RenderCommand(scene_ids=ids))
        calls = len(self.calls)
        for selection in (list(reversed(ids)), [ids[2], ids[0]]):
            result = self.router.export_audio(schemas.RenderSelection(scene_ids=selection), mp3=True)
            directory = Path(result.export_directory)
            timeline = read_json(directory / "timeline.json")
            expected = [scene_id for scene_id in ids if scene_id in selection]
            self.assertEqual([s["scene_id"] for s in timeline["scenes"]], expected)
            self.assertEqual([s["scene_id"] for s in read_json(directory / "approved_script.json")], expected)
            mp3 = directory / "chapter_narration.mp3"
            self.assertGreater(mp3.stat().st_size, 0)
            decoded = subprocess.run([get_ffmpeg_exe(), "-v", "error", "-i", str(mp3), "-f", "s16le", "-acodec", "pcm_s16le", "-"], check=True, capture_output=True)
            self.assertAlmostEqual(len(decoded.stdout) / 2 / 24000, timeline["total_duration_sec"], places=2)
            self.assertEqual(len(self.calls), calls)  # Export never generates speech.
        self.router.export_audio(schemas.RenderSelection(scene_ids=[ids[1]]))
        self.assertFalse((directory / "chapter_narration.mp3").exists())

    def test_stale_review_rejected_and_failed_approval_is_atomic(self):
        draft = review_document(self.router.project, "cast")
        before = (self.router.root / "project.json").read_bytes()
        with self.assertRaises(schemas.WorkflowError):
            apply_review(self.router, draft, approve=True)
        self.assertEqual((self.router.root / "project.json").read_bytes(), before)
        apply_review(self.router, draft)
        # Change one applied field so an old snapshot cannot overwrite it.
        newer = review_document(self.router.project, "cast")
        newer["command"]["cast"][0]["name"] = "New narrator"
        apply_review(self.router, newer)
        with self.assertRaisesRegex(ValueError, "stale"):
            apply_review(self.router, draft)

    def test_partial_render_checkpoint_and_retry(self):
        self.approve()
        calls = []
        def fail_second(request):
            calls.append(request)
            if len(calls) == 2:
                raise TimeoutError("synthetic timeout")
            return wav_bytes()
        self.router._renderer = fail_second
        command = schemas.RenderCommand(scene_ids=["scene_001"])
        with self.assertRaises(schemas.WorkflowError):
            self.router.render_selected(command)
        self.assertEqual(sum(map(len, self.router.project.takes.values())), 1)
        self.router.load_project()
        self.router.render_selected(command)
        self.assertEqual(len(self.calls), 1)  # only the unfinished segment

    def test_changed_text_requires_reapproval_and_corruption_blocks_export(self):
        self.approve()
        command = schemas.RenderCommand(scene_ids=["scene_001"])
        self.router.render_selected(command)
        take = next(iter(self.router.project.takes.values()))[0]
        (self.router.root / take.path).write_bytes(b"bad audio")
        with self.assertRaises(schemas.WorkflowError):
            self.router.export_audio(schemas.RenderSelection(scene_ids=command.scene_ids))
        draft = review_document(self.router.project, "script", "scene_001")
        draft["command"]["turns"][0]["text"] = "Changed dialogue"
        apply_review(self.router, draft)
        with self.assertRaises(schemas.WorkflowError):
            self.router.render_selected(command)

    def test_invalid_audio_not_retained(self):
        self.approve()
        self.router._renderer = lambda request: b"not a WAV"
        with self.assertRaises(schemas.WorkflowError):
            self.router.render_selected(schemas.RenderCommand(scene_ids=["scene_001"]))
        self.assertEqual(self.router.project.takes, {})
        self.assertEqual(list(self.router.root.rglob("*.tmp.wav")), [])

    def test_regeneration_retains_old_take_and_other_segments(self):
        self.approve()
        command = schemas.RenderCommand(scene_ids=["scene_001"])
        self.router.render_selected(command)
        old = copy.deepcopy(self.router.project.takes)
        self.router.render_selected(schemas.RenderCommand(scene_ids=["scene_001"], regenerate=["scene_001_001"]))
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(sorted(map(len, self.router.project.takes.values())), [1, 2])
        for signature, takes in old.items():
            self.assertEqual(self.router.project.takes[signature][0].take_id, takes[0].take_id)

    def test_intentional_silence_and_narrator_separation(self):
        self.approve()
        draft = review_document(self.router.project, "script", "scene_001")
        turn = draft["command"]["turns"][1]
        turn.update(text="", silence_sec=.25)
        apply_review(self.router, draft, approve=True)
        self.router.insert_narration(schemas.NarrationInsert(scene_id="scene_001", position=0,
            text="A new morning.", evidence_source_ids=[self.router.project.sources[0].source_id]))
        apply_review(self.router, review_document(self.router.project, "script", "scene_001"), approve=True)
        selection = schemas.RenderSelection(scene_ids=["scene_001"])
        segments = self.router.inspect_segments(selection)
        self.assertEqual(len(segments), 4)
        self.assertIsNone(segments[2].request)
        self.assertEqual(segments[0].turns[0].speaker_id, "NARRATOR")
        self.router.render_selected(schemas.RenderCommand(scene_ids=selection.scene_ids))
        self.assertEqual(len(self.calls), 3)
        result = self.router.export_audio(selection)
        timeline = read_json(Path(result.export_directory) / "timeline.json")
        # Only narrator -> first dialogue gets a .12 gap; silence is not padded twice.
        self.assertEqual(timeline["total_duration_sec"], .67)

    def test_excluded_source_never_spoken(self):
        self.approve()
        draft = review_document(self.router.project, "sources")
        draft["command"]["sources"][1]["include"] = False
        apply_review(self.router, draft)
        apply_review(self.router, review_document(self.router.project, "script", "scene_001"), approve=True)
        self.router.render_selected(schemas.RenderCommand(scene_ids=["scene_001"]))
        spoken = [t["text"] for r in self.calls for t in r["input"][0]["content"]]
        self.assertEqual(spoken, ["First line", "Third line"])

    def test_restore_rejects_nonempty_and_bad_archive_leaves_no_project(self):
        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "keep.txt").write_text("keep")
        with self.assertRaises(schemas.WorkflowError):
            PipelineRouter(PipelineConfig(workspace=occupied)).restore_project(self.chapter)
        self.assertEqual((occupied / "keep.txt").read_text(), "keep")
        target = self.root / "invalid"
        with self.assertRaises(schemas.WorkflowError):
            PipelineRouter(PipelineConfig(workspace=target)).restore_project(self.chapter)
        self.assertFalse(target.exists())


class GeometryAndSafetyTests(unittest.TestCase):
    def test_rtl_and_ltr_rows(self):
        regions = [[0, 0, 40, 40], [50, 0, 90, 40], [0, 50, 90, 100]]
        self.assertEqual(layout_order(regions), [1, 0, 2])
        self.assertEqual(layout_order(regions, "ltr"), [0, 1, 2])

    def test_contained_multiline_and_ambiguous_ocr(self):
        assigned, unmatched, _ = reconcile_texts([[0, 0, 100, 100]], [("one", [10, 10, 50, 20]), ("two", [10, 30, 50, 40])])
        self.assertEqual(assigned[0], [0, 1])
        self.assertEqual(unmatched, [])
        _, unmatched, diagnostics = reconcile_texts([[0, 0, 100, 100]] * 2, [("one", [10, 10, 50, 20])])
        self.assertEqual(unmatched, [0])
        self.assertEqual(diagnostics[0]["code"], "ambiguous_ocr")

    def test_import_does_not_rematch_already_reconciled_ambiguity(self):
        chapter = {"pages": [{"page_id": "p1", "texts": [
            {"bbox": [0, 0, 10, 10], "ocr_text": "", "ocr_indices": []},
            {"bbox": [0, 0, 10, 10], "ocr_text": "Hello", "ocr_indices": [0]}]}]}
        raw = {"p1": {"ocr": {"ocr_texts": ["Hello"], "bboxes": [[0, 0, 10, 10]]}}}
        recovered = recover_ocr(chapter, raw)
        self.assertEqual([t["ocr_text"] for t in recovered["pages"][0]["texts"]], ["", "Hello"])

    def test_archive_traversal_and_workspace_lock(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad = root / "bad.zip"
            with zipfile.ZipFile(bad, "w") as z:
                z.writestr("../escape.txt", "no")
            with self.assertRaises(ValueError):
                extract_zip(bad, root / "target")
            self.assertFalse((root / "escape.txt").exists())
            with workspace_lock(root / "project"):
                with self.assertRaises(ValueError):
                    with workspace_lock(root / "project"):
                        pass


if __name__ == "__main__":
    unittest.main()
