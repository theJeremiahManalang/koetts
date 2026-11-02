"""Reject unrelated or malformed reports before they can alter production limits."""
import base64
import copy
import json
import unittest

from manga_worker.cloud_billing import BillingNotificationConfig, parse_billing_notification


class BillingNotificationTests(unittest.TestCase):
    def setUp(self):
        self.config = BillingNotificationConfig("ABC123-DEF456-ABC789", "pilot-budget",
                                                "projects/demo-controls/subscriptions/hosted-budget")

    def envelope(self, report=None):
        report = report or {"costAmount": 15.0000001, "budgetAmount": 20, "currencyCode": "USD",
                            "costIntervalStart": "2026-10-01T00:00:00-07:00"}
        return {"subscription": self.config.subscription, "message": {
            "messageId": "12345", "attributes": {"billingAccountId": self.config.billing_account,
            "budgetId": self.config.budget, "schemaVersion": "1.0"},
            "data": base64.b64encode(json.dumps(report).encode()).decode(),
        }}

    def test_rounds_cost_up_and_normalizes_interval_and_idempotency(self):
        envelope = self.envelope()
        interval, micros, event_id = parse_billing_notification(envelope, self.config)
        self.assertEqual(interval, "2026-10-01T07:00:00Z")
        self.assertEqual(micros, 15_000_001)
        self.assertEqual(parse_billing_notification(copy.deepcopy(envelope), self.config)[2], event_id)
        envelope["message"]["messageId"] = "12346"
        self.assertNotEqual(parse_billing_notification(envelope, self.config)[2], event_id)

    def test_unrelated_subscription_budget_account_and_schema_rejected(self):
        for field in ("subscription", "billingAccountId", "budgetId", "schemaVersion"):
            with self.subTest(field=field):
                envelope = self.envelope()
                target = envelope if field == "subscription" else envelope["message"]["attributes"]
                target[field] = "unrelated"
                with self.assertRaises(ValueError):
                    parse_billing_notification(envelope, self.config)

    def test_wrong_currency_budget_amount_and_ambiguous_interval_rejected(self):
        base = {"costAmount": 15, "budgetAmount": 20, "currencyCode": "USD",
                "costIntervalStart": "2026-10-01T00:00:00Z"}
        for field, value in (("costAmount", True), ("costAmount", "15"), ("costAmount", float("inf")),
                             ("budgetAmount", 200), ("currencyCode", "TWD"),
                             ("costIntervalStart", "2026-10-01"),
                             ("costIntervalStart", "2026-02-30T00:00:00Z")):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                parse_billing_notification(self.envelope({**base, field: value}), self.config)
        self.assertEqual(parse_billing_notification(self.envelope({**base, "costAmount": -5}), self.config)[1], 0)

    def test_invalid_encoded_data_and_duplicate_fields_rejected(self):
        envelope = self.envelope()
        for encoded in ("%%%", base64.b64encode(b'{"costAmount":1,"costAmount":2}').decode(),
                        base64.b64encode(b"\xff").decode(), "A" * 24_001):
            with self.subTest(encoded=encoded[:20]), self.assertRaises(ValueError):
                envelope["message"]["data"] = encoded
                parse_billing_notification(envelope, self.config)
