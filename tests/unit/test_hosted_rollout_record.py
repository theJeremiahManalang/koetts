import argparse
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.hosted_rollout_record import build_record, write_record


class HostedRolloutRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "record-test@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Record Test"], cwd=self.root, check=True)
        (self.root / "tracked.txt").write_text("candidate\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.root, check=True)
        self.args = argparse.Namespace(
            project="koetts-9bf7f", database="koetts-default", region="us-east4",
            dataset="pilot-clean", bucket="koetts-pilot-artifacts", namespace="pilot/artifacts",
            rollback_web="koetts-build-prior-001", rollback_api="ABSENT",
            rollback_magi_image="us-east4-docker.pkg.dev/example/magi@sha256:" + "a" * 64,
            rollback_pipeline_image="us-east4-docker.pkg.dev/example/pipeline@sha256:" + "b" * 64,
            evidence_path=[str(self.root / "evidence" / "preflight.json")],
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_record_captures_candidate_and_explicit_targets_without_verifying_deploy(self):
        record = build_record(self.args, self.root)
        self.assertEqual(record["verification_status"], "pending")
        self.assertEqual(record["candidate"]["clean"], True)
        self.assertRegex(record["candidate"]["sha"], r"^[0-9a-f]{40,64}$")
        self.assertEqual(record["target"]["database"], "koetts-default")
        self.assertEqual(record["rollback_targets"]["api_revision"], "ABSENT")
        self.assertIn("does not verify cloud state", record["notes"][0])

    def test_dirty_git_state_is_recorded(self):
        (self.root / "untracked.txt").write_text("local change\n", encoding="utf-8")
        record = build_record(self.args, self.root)
        self.assertFalse(record["candidate"]["clean"])
        self.assertTrue(any("untracked.txt" in entry for entry in record["candidate"]["status_entries"]))

    def test_missing_or_placeholder_inputs_rejected(self):
        for field, value in (("bucket", ""), ("rollback_web", "PREVIOUS_WEB_REVISION")):
            with self.subTest(field=field):
                setattr(self.args, field, value)
                with self.assertRaises(ValueError):
                    build_record(self.args, self.root)
        self.args.bucket = "koetts-pilot-artifacts"

    def test_malformed_target_and_mutable_job_image_rejected(self):
        self.args.region = "us-east4/../bad"
        with self.assertRaisesRegex(ValueError, "region has invalid syntax"):
            build_record(self.args, self.root)
        self.args.region = "us-east4"
        self.args.rollback_magi_image = "registry.example/magi:latest"
        with self.assertRaisesRegex(ValueError, "immutable sha256 image digest"):
            build_record(self.args, self.root)

    def test_empty_evidence_path_rejected(self):
        self.args.evidence_path = [""]
        with self.assertRaisesRegex(ValueError, "explicit path"):
            build_record(self.args, self.root)

    def test_output_is_exclusive_and_json(self):
        output = Path(self.temp.name) / "record.json"
        record = build_record(self.args, self.root)
        self.assertEqual(write_record(record, output), output)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), record)
        with self.assertRaisesRegex(ValueError, "already exists"):
            write_record(record, output)

    def test_output_and_evidence_paths_reject_data_or_cache_locations(self):
        unsafe = Path(self.temp.name) / "results" / "rollout.json"
        with self.assertRaisesRegex(ValueError, "cannot be inside"):
            write_record({}, unsafe)
        self.args.evidence_path = [str(Path(self.temp.name) / ".aws" / "credentials.json")]
        with self.assertRaisesRegex(ValueError, "cannot be inside"):
            build_record(self.args, self.root)


if __name__ == "__main__":
    unittest.main()
