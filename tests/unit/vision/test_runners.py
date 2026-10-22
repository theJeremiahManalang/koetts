"""Integration checks with deterministic models; no downloaded weights needed."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from manga_vision import cli as run
from manga_vision.runners import validate_options


class RunnerTests(unittest.TestCase):
    def test_capability_validation(self):
        for task in ("detect", "ocr", "all"):
            validate_options("magi", task)
        validate_options("magi", "ground", Path("captions.json"))
        with self.assertRaisesRegex(ValueError, "requires --captions"):
            validate_options("magi", "ground")
        with self.assertRaisesRegex(ValueError, "Unknown model"):
            validate_options("unknown", "detect")

    def test_model_folders_metadata_and_non_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "page.png"
            Image.new("RGB", (20, 20)).save(source)
            for model in ("magi", "magi"):
                fake = SimpleNamespace(model_id=model, revision="test-revision", device="cpu",
                                       predict=lambda *args: {"detections": [{"texts": [[1, 1, 10, 10]]}]})
                argv = ["run.py", "--model", model, "--task", "detect", "--input", str(source), "--output", str(root / "out")]
                with patch("sys.argv", argv), patch("manga_vision.cli.create_runner", return_value=fake), contextlib.redirect_stdout(io.StringIO()):
                    run.main()
            self.assertEqual(len(list((root / "out" / "magi").iterdir())), 2)
            for path in (root / "out").glob("*/*/*.json"):
                data = json.loads(path.read_text())
                self.assertEqual(data["model_key"], path.parent.parent.name)
                self.assertEqual(data["revision"], "test-revision")
                self.assertTrue(path.with_suffix(".detections.png").is_file())

    def test_unsupported_task_fails_before_loading(self):
        with patch("sys.argv", ["run.py", "--model", "magi", "--task", "ground", "--input", "missing.png"]), patch("manga_vision.cli.create_runner") as factory, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                run.main()
            self.assertEqual(error.exception.code, 2)
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
