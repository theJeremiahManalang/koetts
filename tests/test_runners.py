"""Integration checks with deterministic models; no downloaded weights needed."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from comic_text_detector import ComicTextDetector
from runners import validate_options
import run


class RunnerTests(unittest.TestCase):
    def test_capability_validation(self):
        for task in ("detect", "all"):
            validate_options("comic-text-detector", task)
        for task in ("ocr", "ground"):
            with self.assertRaisesRegex(ValueError, "detection only"):
                validate_options("comic-text-detector", task)
        with self.assertRaises(ValueError):
            validate_options("comic-text-detector", "all", Path("captions.json"))

    def test_ctd_conversion_and_masks(self):
        runner = ComicTextDetector.__new__(ComicTextDetector)
        block = SimpleNamespace(xyxy=[1, 2, 8, 9], to_dict=lambda: {"xyxy": [1, 2, 8, 9], "vertical": True})
        seen = []
        mask = np.zeros((10, 10), dtype=np.uint8)
        def detector(pixels):
            seen.append(pixels[0, 0].tolist())
            return mask, mask, [block]
        runner.detector = detector
        result = runner.predict([Image.new("RGB", (10, 10), (10, 20, 30))])
        self.assertEqual(seen, [[30, 20, 10]])
        self.assertEqual(result["detections"][0]["texts"], [[1, 2, 8, 9]])
        self.assertTrue(result["detections"][0]["text_blocks"][0]["vertical"])
        with tempfile.TemporaryDirectory() as tmp:
            names = runner.save_artifacts(tmp, "page")
            for name in names.values():
                with Image.open(Path(tmp) / name) as saved:
                    self.assertEqual(saved.size, (10, 10))
        runner.detector = lambda pixels: (mask, mask, [])
        self.assertEqual(runner.predict([Image.new("RGB", (10, 10))])["detections"][0]["texts"], [])
        with self.assertRaises(ValueError):
            runner.predict([], "detect")

    def test_model_folders_metadata_and_non_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "page.png"
            Image.new("RGB", (20, 20)).save(source)
            for model in ("magi", "comic-text-detector", "magi"):
                fake = SimpleNamespace(model_id=model, revision="test-revision", device="cpu",
                                       predict=lambda *args: {"detections": [{"texts": [[1, 1, 10, 10]]}]})
                argv = ["run.py", "--model", model, "--task", "detect", "--input", str(source), "--output", str(root / "out")]
                with patch("sys.argv", argv), patch("run.create_runner", return_value=fake), contextlib.redirect_stdout(io.StringIO()):
                    run.main()
            self.assertEqual(len(list((root / "out" / "magi").iterdir())), 2)
            self.assertEqual(len(list((root / "out" / "comic-text-detector").iterdir())), 1)
            for path in (root / "out").glob("*/*/*.json"):
                data = json.loads(path.read_text())
                self.assertEqual(data["model_key"], path.parent.parent.name)
                self.assertEqual(data["revision"], "test-revision")
                self.assertTrue(path.with_suffix(".detections.png").is_file())

    def test_unsupported_task_fails_before_loading(self):
        with patch("sys.argv", ["run.py", "--model", "comic-text-detector", "--task", "ocr", "--input", "missing.png"]), patch("run.create_runner") as factory, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                run.main()
            self.assertEqual(error.exception.code, 2)
            factory.assert_not_called()

    def test_missing_source_has_setup_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "source missing"):
                ComicTextDetector(repo=Path(tmp))

    def test_onnx_constructor_reports_cpu_and_weight_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "inference.py").write_text("# test upstream placeholder")
            weights = root / "test.onnx"
            weights.write_bytes(b"test checkpoint")
            fake_torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))
            with patch.dict("sys.modules", {"torch": fake_torch}), patch("comic_text_detector.importlib.import_module") as importer, patch("comic_text_detector.subprocess.check_output", side_effect=OSError), patch("sys.path", list(__import__("sys").path)), contextlib.redirect_stdout(io.StringIO()):
                runner = ComicTextDetector("auto", root, weights)
                self.assertEqual(runner.device, "cpu")
                self.assertEqual(len(runner.metadata["weights_sha256"]), 64)
                self.assertIsNone(runner.revision)
                self.assertEqual(importer.return_value.TextDetector.call_args.kwargs["device"], "cpu")
                with self.assertRaisesRegex(ValueError, "OpenCV CPU"):
                    ComicTextDetector("cuda", root, weights)


if __name__ == "__main__":
    unittest.main()
