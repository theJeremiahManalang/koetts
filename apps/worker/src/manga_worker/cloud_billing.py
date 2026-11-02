"""Validate authenticated Pub/Sub Cloud Billing reports before ledger ingestion."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING


@dataclass(frozen=True)
class BillingNotificationConfig:
    billing_account: str
    budget: str
    subscription: str

    def __post_init__(self):
        if not re.fullmatch(r"[A-F0-9]{6}(?:-[A-F0-9]{6}){2}", self.billing_account):
            raise ValueError("Explicit billing account required")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.budget):
            raise ValueError("Explicit billing budget required")
        if not re.fullmatch(r"projects/[A-Za-z0-9_-]+/subscriptions/[A-Za-z0-9._~-]{3,255}", self.subscription):
            raise ValueError("Explicit billing subscription required")

    @classmethod
    def from_environment(cls):
        return cls(*(os.environ.get(name, "") for name in (
            "MANGA_BILLING_ACCOUNT_ID", "MANGA_BILLING_BUDGET_ID", "MANGA_BILLING_SUBSCRIPTION",
        )))


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate billing report field")
        result[key] = value
    return result


def _reject_number(value):
    raise ValueError("Invalid billing report number")


def _amount(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ValueError(f"Invalid {label}")
    try:
        amount = Decimal(value)
        if not amount.is_finite() or abs(amount) > Decimal("1000000000"):
            raise ValueError(f"Invalid {label}")
        return amount
    except InvalidOperation as error:
        raise ValueError(f"Invalid {label}") from error


def parse_billing_notification(envelope: dict, config: BillingNotificationConfig) -> tuple[str, int, str]:
    """Return normalized interval, conservatively rounded USD micros, event ID.

    OIDC authentication is a separate mandatory HTTP boundary. Payload identity
    checks supplement that boundary; they do not authenticate an arbitrary sender.
    """
    if not isinstance(envelope, dict) or envelope.get("subscription") != config.subscription:
        raise ValueError("Unexpected billing subscription")
    message = envelope.get("message")
    if not isinstance(message, dict):
        raise ValueError("Invalid Pub/Sub message")
    attributes = message.get("attributes")
    if (not isinstance(attributes, dict)
            or attributes.get("billingAccountId") != config.billing_account
            or attributes.get("budgetId") != config.budget
            or attributes.get("schemaVersion") != "1.0"):
        raise ValueError("Unexpected billing report identity")
    message_id = message.get("messageId")
    if not isinstance(message_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", message_id):
        raise ValueError("Invalid Pub/Sub message identity")
    encoded = message.get("data")
    if not isinstance(encoded, str) or len(encoded) > 24_000:
        raise ValueError("Invalid billing report data")
    try:
        report = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"),
                            parse_float=Decimal, parse_int=int, object_pairs_hook=_unique_fields,
                            parse_constant=_reject_number)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValueError("Invalid billing report data") from error
    if not isinstance(report, dict) or report.get("currencyCode") != "USD":
        raise ValueError("Expected USD billing report")
    if _amount(report.get("budgetAmount"), "budget amount") != 20:
        raise ValueError("Expected the USD 20 hosted pilot budget")
    cost = _amount(report.get("costAmount"), "reported cost")
    interval = report.get("costIntervalStart")
    if not isinstance(interval, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", interval):
        raise ValueError("Expected an RFC3339 billing interval")
    try:
        start = datetime.fromisoformat(interval.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as error:
        raise ValueError("Invalid billing interval") from error
    normalized = start.isoformat().replace("+00:00", "Z")
    # Credits may make a report negative. They cannot refund accepted reservations
    # or lower the interval highwater; clamp to zero before conservative rounding.
    micros = int((max(cost, Decimal(0)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING))
    event_id = hashlib.sha256((config.subscription + "\0" + message_id).encode()).hexdigest()
    return normalized, micros, event_id
