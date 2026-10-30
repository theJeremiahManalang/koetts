import unittest

from manga_worker.cloud_budget import _key, _money, _operator, _stage_config


class CloudBudgetValidationTests(unittest.TestCase):
    def test_money_accepts_only_nonnegative_integer_micros(self):
        self.assertEqual(_money(12, "amount"), 12)
        for value in (True, -1, 1.0, float("nan"), float("inf"), "10"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _money(value, "amount")

    def test_allowance_maximum_is_enforced(self):
        with self.assertRaises(ValueError):
            _money(80_000_001, "provider allowance", maximum=80_000_000)

    def test_operator_fields_and_mandatory_stage_caps(self):
        with self.assertRaises(ValueError):
            _operator("", "change")
        self.assertEqual(_operator("operator/team", "invoice / closeout"),
                         ("operator/team", "invoice / closeout"))
        self.assertEqual(_key("namespace/operation-key", "operation key"),
                         "namespace/operation-key")
        with self.assertRaises(ValueError):
            _stage_config({"magi": {}})
        stage = {"infrastructure_micro": 5, "provider_micro": 100,
                 "provider_call_micro": 25, "max_provider_calls": 4}
        self.assertEqual(_stage_config({"magi": stage, "pipeline": stage})["magi"]["provider_micro"], 100)
        with self.assertRaises(ValueError):
            _stage_config({"magi": {**stage, "provider_call_micro": 26}, "pipeline": stage})
        with self.assertRaises(ValueError):
            _stage_config({"magi": {**stage, "infrastructure_micro": 0}, "pipeline": stage})
        with self.assertRaises(ValueError):
            _stage_config({"magi": {**stage, "provider_call_micro": 0}, "pipeline": stage})
        no_paid_calls = {**stage, "provider_micro": 0, "provider_call_micro": 0, "max_provider_calls": 0}
        self.assertEqual(_stage_config({"magi": no_paid_calls, "pipeline": stage})["magi"]["max_provider_calls"], 0)
