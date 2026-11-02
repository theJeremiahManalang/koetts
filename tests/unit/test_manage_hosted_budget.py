"""Tests for the private hosted budget configuration wizard."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.manage_hosted_budget import main


class ManageHostedBudgetTests(unittest.TestCase):
    def test_default_mode_writes_private_caps_and_prints_operator_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "caps.json"
            answers = iter(("5", "5", "0", "0", "0", "5", "5", "5", "1"))
            with patch("manga_worker.cloud_operator.main", return_value=0) as operator:
                result = main([
                    "--output", str(output), "--actor", "admin@example.com",
                    "--reason", "manual test", "--evidence", "test-123",
                ], input_fn=lambda _: next(answers), print_fn=lambda _: None)

            self.assertEqual(result, 0)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            caps = json.loads(output.read_text())
            self.assertEqual(caps["magi"]["max_provider_calls"], 0)
            self.assertEqual(caps["pipeline"]["provider_call_micro"], 5_000_000)
            args = operator.call_args.args[0]
            self.assertIn("--provider-allowance-micro", args)
            self.assertIn("5000000", args)
            self.assertNotIn("--execute", args)

    def test_execute_is_forwarded_only_when_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "caps.json"
            answers = iter(("5", "5", "0", "0", "0", "5", "5", "5", "1"))
            with patch("manga_worker.cloud_operator.main", return_value=0) as operator:
                main([
                    "--output", str(output), "--actor", "admin@example.com",
                    "--reason", "manual test", "--evidence", "test-123", "--execute",
                ], input_fn=lambda _: next(answers), print_fn=lambda _: None)

            self.assertIn("--execute", operator.call_args.args[0])

    def test_invalid_provider_caps_fail_before_writing_or_cloud_operator(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "caps.json"
            answers = iter(("5", "5", "1", "1", "1", "5", "5", "5", "1"))
            with patch("manga_worker.cloud_operator.main") as operator:
                result = main([
                    "--output", str(output), "--actor", "admin@example.com",
                    "--reason", "manual test", "--evidence", "test-123",
                ], input_fn=lambda _: next(answers), print_fn=lambda _: None)

            self.assertEqual(result, 2)
            self.assertFalse(output.exists())
            operator.assert_not_called()
