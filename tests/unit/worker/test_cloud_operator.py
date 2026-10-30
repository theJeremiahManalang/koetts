import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from manga_worker.cloud_operator import main


class CloudOperatorTests(unittest.TestCase):
    def test_default_mode_emits_plan_without_constructing_cloud_client(self):
        with patch("manga_worker.cloud_operator._connect") as connect, patch("builtins.print") as output:
            self.assertEqual(main(["pause", "--actor", "dev", "--reason", "maintenance",
                                  "--evidence", "ticket:42"]), 0)
        connect.assert_not_called()
        value = json.loads(output.call_args.args[0])
        self.assertEqual(value["mode"], "plan")
        self.assertTrue(value["changes_cloud_state"])
        self.assertEqual(value["arguments"]["reason"], "maintenance")

    def test_bad_stage_caps_rejected_before_connecting_clients(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "caps.json"
            path.write_text(json.dumps({"magi": {}, "pipeline": {}}), encoding="utf-8")
            with patch("manga_worker.cloud_operator._connect") as connect, patch("builtins.print") as output:
                self.assertEqual(main(["configure", "--provider-allowance-micro", "100",
                                       "--stage-caps", str(path), "--actor", "dev", "--reason", "setup",
                                       "--evidence", "review:1"]), 2)
            connect.assert_not_called()
            self.assertIn("error", json.loads(output.call_args.args[0]))

    def test_execute_status_uses_read_only_budget_status(self):
        ledger = unittest.mock.Mock()
        ledger.status.return_value = {"configured": False, "paused": True}
        client = unittest.mock.Mock()
        settings = unittest.mock.Mock()
        with patch("manga_worker.cloud_operator.CloudSettings.from_environment", return_value=settings), \
                patch("manga_worker.cloud_operator._connect", return_value=(client, ledger)), \
                patch("builtins.print") as output:
            self.assertEqual(main(["status", "--execute"]), 0)
        ledger.status.assert_called_once_with()
        client.close.assert_called_once_with()
        self.assertEqual(json.loads(output.call_args.args[0])["result"], {"configured": False, "paused": True})

    def test_settle_execute_validates_then_injects_operation_and_cloud_run_clients(self):
        settings = unittest.mock.Mock(project="demo", dataset="pilot", bucket="bucket",
                                      namespace="pilot/artifacts")
        client = unittest.mock.Mock()
        ledger = unittest.mock.Mock()
        ledger.settle.return_value = {"provider_released_micro": 10}
        operations = unittest.mock.Mock()
        jobs = unittest.mock.Mock()
        jobs.status.return_value = "succeeded"
        environment = {"MANGA_CLOUD_REGION": "us-east4", "MANGA_MAGI_JOB": "magi-job",
                       "MANGA_PIPELINE_JOB": "pipeline-job"}
        with patch.dict("os.environ", environment, clear=False), \
                patch("manga_worker.cloud_operator.CloudSettings.from_environment", return_value=settings) as config, \
                patch("manga_worker.cloud_operator._connect", return_value=(client, ledger)) as connect, \
                patch("manga_worker.cloud_operations.FirestoreOperationStore", return_value=operations), \
                patch("manga_worker.cloud_jobs.CloudRunJobs", return_value=jobs) as jobs_factory, \
                patch("builtins.print") as output:
            self.assertEqual(main(["settle", "--execute", "--actor", "dev", "--reason", "close",
                                  "--evidence", "ticket:3", "--operation-key", "operation/3"]), 0)
        config.assert_called_once_with()
        connect.assert_called_once_with(settings)
        jobs_factory.assert_called_once_with("demo", "us-east4", {"magi": "magi-job", "pipeline": "pipeline-job"})
        ledger.settle.assert_called_once_with("dev", "close", "operation/3", evidence="ticket:3",
                                              operation_store=operations, execution_status=jobs.status)
        client.close.assert_called_once_with()
        self.assertEqual(json.loads(output.call_args.args[0])["mode"], "executed")

    def test_invalid_settlement_job_names_reject_before_any_cloud_client(self):
        settings = unittest.mock.Mock()
        environment = {"MANGA_CLOUD_REGION": "us-east4", "MANGA_MAGI_JOB": "bad/job",
                       "MANGA_PIPELINE_JOB": "pipeline-job"}
        with patch.dict("os.environ", environment, clear=False), \
                patch("manga_worker.cloud_operator.CloudSettings.from_environment", return_value=settings) as config, \
                patch("manga_worker.cloud_operator._connect") as connect, \
                patch("builtins.print") as output:
            self.assertEqual(main(["settle", "--execute", "--actor", "dev", "--reason", "close",
                                  "--evidence", "ticket:3", "--operation-key", "operation/3"]), 2)
        config.assert_not_called()
        connect.assert_not_called()
        self.assertIn("valid resource names", json.loads(output.call_args.args[0])["error"])

    def test_execution_errors_are_redacted_and_close_firestore_client(self):
        settings = unittest.mock.Mock()
        client = unittest.mock.Mock()
        ledger = unittest.mock.Mock()
        ledger.status.side_effect = RuntimeError("secret credential response")
        with patch("manga_worker.cloud_operator.CloudSettings.from_environment", return_value=settings), \
                patch("manga_worker.cloud_operator._connect", return_value=(client, ledger)), \
                patch("builtins.print") as output:
            self.assertEqual(main(["status", "--execute"]), 2)
        client.close.assert_called_once_with()
        rendered = output.call_args.args[0]
        self.assertNotIn("secret credential response", rendered)
        self.assertEqual(json.loads(rendered)["error"], "Cloud operator action failed; details withheld.")


if __name__ == "__main__":
    unittest.main()
