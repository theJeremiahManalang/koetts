"""Installed worker paths are explicit and independent of invocation directory."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from manga_worker.paths import data_root, repository_root


class WorkerPathTests(unittest.TestCase):
    def test_explicit_data_root_and_relative_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"MANGA_DATA_ROOT": directory}):
                self.assertEqual(data_root(), Path(directory))
            with patch.dict(os.environ, {"MANGA_DATA_ROOT": "relative"}):
                with self.assertRaisesRegex(ValueError, "absolute"):
                    data_root()

    def test_packaged_commands_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "MANGA_DATA_ROOT": str(Path(directory) / "data"), "GEMINI_API_KEY": ""}
            for module in ("manga_tts", "manga_vision", "manga_worker.workflow", "manga_worker.extract"):
                result = subprocess.run([sys.executable, "-m", module, "--help"], cwd=directory,
                                        env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([sys.executable, "-m", "manga_worker.workflow", "claim-next"],
                                    cwd=directory, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "null")
            self.assertTrue((Path(directory) / "data/operations.sqlite3").is_file())

    def test_checkout_default_keeps_existing_results_location(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(data_root(), repository_root() / "results/web")
