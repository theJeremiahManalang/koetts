"""Contract tests for the model-to-script-to-audio boundary; no weights required."""
import copy
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from character_analysis import normalize_page
from web_audio import validate_script, generate
from web_analyze import analyze


class CharacterAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (400, 300), "white")
        self.detection = {"panels": [[200, 0, 400, 300], [0, 0, 190, 300]],
                          "texts": [[250, 20, 350, 80], [20, 20, 120, 80]],
                          "characters": [[250, 100, 350, 280], [20, 100, 120, 280]],
                          "character_cluster_labels": [0, 0], "is_essential_text": [True, False],
                          "text_character_associations": [[0, 0], [1, 1]]}
        self.ocr = {"ocr_texts": ["Left", "Right"], "bboxes": [[20, 20, 120, 80], [250, 20, 350, 80]]}

    def test_ocr_is_matched_by_geometry_not_index_and_rtl_is_preserved(self):
        page = normalize_page(self.detection, self.ocr, self.image, "p1", "rtl")
        self.assertEqual([l["text"] for l in page["lines"]], ["Left", "Right"])
        self.assertEqual(page["lines"][0]["appearance_id"], "p1_chr_2")
        self.assertFalse(page["lines"][0]["included"])
        self.assertTrue(page["appearances"][0]["crop"].startswith("data:image/png;base64,"))

    def test_ltr_changes_panel_and_bubble_order(self):
        ocr = {"ocr_texts": ["Right", "Left"], "bboxes": list(reversed(self.ocr["bboxes"]))}
        page = normalize_page(self.detection, ocr, self.image, "p1", "ltr")
        self.assertEqual([l["text"] for l in page["lines"]], ["Left", "Right"])
        detection = {"panels": [[0, 0, 400, 300]], "texts": ocr["bboxes"]}
        page = normalize_page(detection, ocr, self.image, "p1", "ltr")
        self.assertEqual([l["text"] for l in page["lines"]], ["Left", "Right"])

    def test_ambiguous_speaker_is_not_guessed(self):
        self.detection["text_character_associations"].append([0, 1])
        page = normalize_page(self.detection, self.ocr, self.image, "p1", "rtl")
        self.assertIsNone(page["lines"][1]["appearance_id"])
        self.assertEqual(len(page["lines"][1]["speaker_candidates"]), 2)

    def test_missing_ocr_is_visible_and_page_clusters_are_scoped(self):
        self.ocr = {"ocr_texts": [], "bboxes": []}
        a = normalize_page(self.detection, self.ocr, self.image, "p1", "rtl")
        b = normalize_page(self.detection, self.ocr, self.image, "p2", "rtl")
        self.assertEqual(len(a["lines"]), 2)
        self.assertFalse(a["lines"][0]["included"])
        self.assertNotEqual(a["appearances"][0]["group_id"], b["appearances"][0]["group_id"])

    def test_malformed_ocr_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_page(self.detection, {"ocr_texts": ["Hi"], "bboxes": []}, self.image, "p1", "rtl")

    def test_cache_reuses_inference_but_not_different_image(self):
        with tempfile.TemporaryDirectory() as tmp, patch("web_analyze.__file__", str(Path(tmp) / "web_analyze.py")), patch("magi.Magi") as model:
            root = Path(tmp)
            path = root / "image.png"
            self.image.save(path)
            model.return_value.predict.return_value = {"detections": [self.detection], "ocr": [self.ocr]}
            manifest = root / "manifest.json"
            data = {"direction": "rtl", "images": [{"path": str(path), "name": "image.png"}, {"path": str(path), "name": "second.png"}]}
            manifest.write_text(json.dumps(data))
            first = analyze(manifest)
            self.assertEqual(len(first["pages"]), 2)
            self.assertNotEqual(first["pages"][0]["id"], first["pages"][1]["id"])
            data["direction"] = "ltr"
            manifest.write_text(json.dumps(data))
            second = analyze(manifest)
            self.assertEqual(model.return_value.predict.call_count, 1)
            self.assertEqual(first["pages"][0]["image_hash"], second["pages"][0]["image_hash"])
            Image.new("RGB", (400, 300), "black").save(path)
            third = analyze(manifest)
            self.assertEqual(model.return_value.predict.call_count, 2)
            self.assertNotEqual(first["pages"][0]["image_hash"], third["pages"][0]["image_hash"])


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.script = {"characters": [{"id": "hero", "voice": "Voice A"}],
                       "appearances": [{"id": "crop", "character_id": "hero"}],
                       "lines": [{"id": "line", "sequence": 1, "text": "Hello", "included": True,
                                  "appearance_id": "crop", "character_id": "hero", "voice": "Voice A"}]}

    def test_unknown_voice_speaker_empty_text_and_bad_sequence_rejected(self):
        self.assertEqual(len(validate_script(self.script, ["Voice A"])), 1)
        for field, value in [("voice", "Missing"), ("character_id", None), ("text", " "), ("sequence", 2), ("appearance_id", "missing")]:
            bad = copy.deepcopy(self.script)
            bad["lines"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_script(bad, ["Voice A"])

    def test_off_panel_character_allowed_and_excluded_empty_line_ignored(self):
        self.script["lines"][0]["appearance_id"] = None
        self.script["lines"].append({"id": "skip", "sequence": 2, "text": "", "included": False})
        self.assertEqual(len(validate_script(self.script, ["Voice A"])), 1)

    def test_audio_cache_and_assembly(self):
        def fake_speech(args):
            job = json.loads(Path(args[0]).read_text(encoding="utf-8"))
            with wave.open(job["output"], "wb") as audio:
                audio.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
                audio.writeframes(b"\0\0" * 2205)
        with tempfile.TemporaryDirectory() as tmp, patch("web_audio.ROOT", Path(tmp)), patch("web_audio.voices", return_value=["Voice A"]), patch("web_audio.speech", side_effect=fake_speech) as synth:
            output = Path(tmp) / "chapter.wav"
            self.script["lines"].append({**self.script["lines"][0], "id": "line2", "sequence": 2})
            generate(self.script, output)
            self.assertEqual(synth.call_count, 1)
            with wave.open(str(output), "rb") as audio:
                self.assertEqual(audio.getnframes(), 2205 * 2 + int(22050 * .3))
            self.script["lines"][1]["text"] = "Changed"
            generate(self.script, output)
            self.assertEqual(synth.call_count, 2)


if __name__ == "__main__":
    unittest.main()
