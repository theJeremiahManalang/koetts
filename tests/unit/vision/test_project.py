"""Local plumbing tests. These do NOT claim to test neural-model accuracy."""
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from manga_vision.files import image_paths, load_image, read_captions, save_overlay, write_json
from manga_vision.magi import Magi


class ProjectTests(unittest.TestCase):
    def test_images_captions_and_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Image.new("L", (100, 60), 255).save(root / "page.png")
            paths = image_paths(root)
            image = load_image(paths[0])
            self.assertEqual(image.mode, "RGB")
            caption_path = root / "captions.json"
            caption_path.write_text(json.dumps({"page.png": "A girl waves."}), encoding="utf-8")
            self.assertEqual(read_captions(caption_path, paths), ["A girl waves."])
            caption_path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Missing"):
                read_captions(caption_path, paths)
            prediction = {"ocr_texts": ["Hello!"], "bboxes": [[10, 20, 80, 40]]}
            write_json(root / "result.json", prediction)
            self.assertEqual(json.loads((root / "result.json").read_text()), prediction)
            save_overlay(image, prediction, "ocr", root / "overlay.png")
            with Image.open(root / "overlay.png") as overlay:
                self.assertEqual(overlay.size, image.size)
                self.assertNotEqual(overlay.getpixel((10, 20)), image.getpixel((10, 20)))

    def test_dispatch_and_caption_validation_without_weights(self):
        calls = []
        def record(name):
            def predict(*args):
                calls.append(name)
                return [{}]
            return predict
        # Bypass loading only in this test, substituting a fake model to check
        # routing and input validation without downloading large weights.
        runner = Magi.__new__(Magi)
        runner.torch = SimpleNamespace(inference_mode=nullcontext)
        runner.processor = object()
        runner.model = SimpleNamespace(
            predict_detections_and_associations=record("detect"),
            predict_ocr=record("ocr"),
            predict_character_grounding=record("ground"),
        )
        self.assertEqual(set(runner.predict([object()])), {"detections", "ocr"})
        self.assertEqual(calls, ["detect", "ocr"])
        calls.clear()
        result = runner.predict([object()], captions=["A girl."])
        self.assertEqual(set(result), {"detections", "ocr", "grounding"})
        self.assertEqual(calls, ["detect", "ocr", "ground"])
        with self.assertRaises(ValueError):
            runner.predict([object()], task="ground")
        with self.assertRaises(ValueError):
            runner.predict([object()], captions=[])
        with self.assertRaises(ValueError):
            runner.predict([object()], captions=["A {girl}."])
        with self.assertRaises(ValueError):
            runner.predict([])


if __name__ == "__main__":
    unittest.main()
