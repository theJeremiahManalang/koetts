"""Check the web OCR contract without downloading model weights."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from web_extract import extract_text


class WebExtractTests(unittest.TestCase):
    def test_returns_only_transcriptions_and_requests_ocr(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "panel.png"
            Image.new("RGB", (10, 20)).save(path)
            with patch("runners.create_runner") as factory:
                factory.return_value.predict.return_value = {
                    "ocr": [{"ocr_texts": ["Hello!", "", "こんにちは"], "bboxes": [[0, 0, 1, 1]]}]
                }
                self.assertEqual(extract_text(path), {"texts": ["Hello!", "こんにちは"]})
                factory.assert_called_once_with("magi")
                args = factory.return_value.predict.call_args.args
                self.assertEqual(args[1], "ocr")
                self.assertEqual(args[0][0].mode, "RGB")

    def test_invalid_image_fails_before_loading_model(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "panel.png"
            path.write_text("not an image")
            with patch("runners.create_runner") as factory:
                with self.assertRaises(OSError):
                    extract_text(path)
                factory.assert_not_called()

    def test_empty_prediction(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "panel.png"
            Image.new("RGB", (10, 10)).save(path)
            with patch("runners.create_runner") as factory:
                factory.return_value.predict.return_value = {"ocr": [{"ocr_texts": []}]}
                self.assertEqual(extract_text(path), {"texts": []})
