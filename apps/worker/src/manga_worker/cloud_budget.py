"""Durable, fail-closed cloud cost ledger for hosted operations.

All money values are integer USD micro-units. Operator authorization is owned
by the caller; every operator mutation records its actor and reason.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

from .cloud_revisions import SCHEMA_VERSION, _FirestoreHostedStore


_MAX_KEY_BYTES = 512
_MICROS_PER_USD = 1_000_000
_PROVIDER_ALLOWANCE_MAX = 80 * _MICROS_PER_USD
_INFRA_PAUSE = 15 * _MICROS_PER_USD
_ALERTS = (10 * _MICROS_PER_USD, _INFRA_PAUSE, 20 * _MICROS_PER_USD)
_STAGES = {"magi", "pipeline"}


@dataclass(frozen=True)
class BillingPeriod:
    """One validated UTC billing month used by reports and explicit closeout."""

    value: str

    def __post_init__(self):
        if not isinstance(self.value, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", self.value):
            raise ValueError("Billing period must use YYYY-MM format")
        date.fromisoformat(self.value + "-01")

    @classmethod
    def from_interval(cls, value):
        if not isinstance(value, str) or not re.match(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:$|T)", value):
            raise ValueError("Infrastructure report requires an ISO date or aware timestamp")
        if len(value) == 10:
            start = date.fromisoformat(value)
        else:
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if instant.tzinfo is None or instant.utcoffset() is None:
                raise ValueError("Infrastructure report requires an aware timestamp")
            start = instant.astimezone(timezone.utc).date()
        return cls(f"{start.year:04d}-{start.month:02d}")


def _money(value, label: str, *, maximum: int | None = None) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"Invalid {label}; expected nonnegative integer USD micros")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} exceeds its maximum")
    return value


def _key(value, label: str, *, document_id: bool = False) -> str:
    if (not isinstance(value, str) or not value or len(value.encode("utf-8")) > _MAX_KEY_BYTES
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
            or (document_id and (value in {".", ".."} or "/" in value))):
        raise ValueError(f"Invalid {label}")
    return value


def _operator(actor: str, reason: str) -> tuple[str, str]:
    actor = _key(actor, "operator actor")
    reason = _key(reason, "operator reason")
    return actor, reason


def _stage_config(stages) -> dict:
    if not isinstance(stages, dict) or set(stages) != _STAGES:
        raise ValueError("Stage caps for magi and pipeline are required")
    result = {}
    for name, value in stages.items():
        if not isinstance(value, dict) or set(value) != {
                "infrastructure_micro", "provider_micro", "provider_call_micro", "max_provider_calls"}:
            raise ValueError("Invalid cloud budget stage cap")
        infra = _money(value["infrastructure_micro"], "infrastructure cap")
        provider = _money(value["provider_micro"], "provider operation cap")
        call = _money(value["provider_call_micro"], "provider call cap")
        calls = value["max_provider_calls"]
        if not isinstance(calls, int) or isinstance(calls, bool) or calls < 0:
            raise ValueError("Invalid provider call bound")
        if infra == 0 or (calls > 0 and call == 0):
            raise ValueError("Infrastructure and enabled provider calls require positive cost caps")
        if call * calls > provider:
            raise ValueError("Provider call bound exceeds operation cap")
        result[name] = {"infrastructure_micro": infra, "provider_micro": provider,
                        "provider_call_micro": call, "max_provider_calls": calls}
    return result


class CloudBudgetExceeded(RuntimeError):
    """A durable cloud budget, pause, or reservation check rejected work."""


def _require_production_open(state):
    if (state["paused"] or state["infrastructure_reported_micro"]
            + state["infrastructure_reserved_micro"] >= _INFRA_PAUSE):
        raise CloudBudgetExceeded("Hosted cloud work is paused")


class CloudBudgetLedger(_FirestoreHostedStore):
    """Separate Firestore control namespace for conservative cost accounting."""

    @property
    def _control(self):
        return self.root.collection("cloud_budget_v1").document("control")

    @property
    def _reservations(self):
        return self.root.collection("cloud_budget_v1").document("ledger").collection("reservations")

    @property
    def _calls(self):
        return self.root.collection("cloud_budget_v1").document("ledger").collection("provider_calls")

    @property
    def _intervals(self):
        return self.root.collection("cloud_budget_v1").document("ledger").collection("infra_intervals")

    @property
    def _settlements(self):
        return self.root.collection("cloud_budget_v1").document("ledger").collection("settlements")

    @property
    def _closed_infra_months(self):
        return self.root.collection("cloud_budget_v1").document("ledger").collection("closed_infra_months")

    @property
    def _events(self):
        return self.root.collection("cloud_budget_v1").document("audit").collection("events")

    def _has_budget_records(self, transaction):
        return any(list(collection.limit(1).stream(transaction=transaction))
                   for collection in (self._reservations, self._calls, self._intervals,
                                      self._settlements, self._closed_infra_months, self._events))

    def _settlement_ref(self, operation_key):
        key = _key(operation_key, "operation key")
        return self._settlements.document(hashlib.sha256(key.encode()).hexdigest())

    @staticmethod
    def _settlement_value(snapshot, operation_key):
        if not snapshot.exists:
            return None
        value = snapshot.to_dict()
        expected = {"schema_version", "operation_key", "actor", "reason", "operation_id", "fence",
                    "execution_names", "provider_released_micro", "evidence"}
        if (not isinstance(value, dict) or set(value) != expected
                or value.get("schema_version") != SCHEMA_VERSION
                or isinstance(value.get("schema_version"), bool)
                or value.get("operation_key") != operation_key
                or not isinstance(value.get("operation_id"), str) or not value["operation_id"]
                or not isinstance(value.get("fence"), int) or isinstance(value.get("fence"), bool)
                or value["fence"] < 1 or not isinstance(value.get("execution_names"), list)
                or not all(isinstance(name, str) and name for name in value["execution_names"])
                or not isinstance(value.get("evidence"), str) or not value["evidence"]):
            raise ValueError("Corrupt hosted cloud budget settlement")
        _operator(value.get("actor"), value.get("reason"))
        _money(value.get("provider_released_micro"), "settled provider reservation")
        if len(value["execution_names"]) != len(set(value["execution_names"])):
            raise ValueError("Corrupt hosted cloud budget settlement")
        return value

    @staticmethod
    def _closed_infra_month_value(snapshot, billing_period):
        if not snapshot.exists:
            return None
        value = snapshot.to_dict()
        expected = {"schema_version", "billing_period", "actor", "reason", "evidence"}
        if (not isinstance(value, dict) or set(value) != expected
                or value.get("schema_version") != SCHEMA_VERSION
                or isinstance(value.get("schema_version"), bool)
                or value.get("billing_period") != billing_period):
            raise ValueError("Corrupt closed infrastructure billing period")
        _operator(value.get("actor"), value.get("reason"))
        _key(value.get("evidence"), "billing reconciliation evidence")
        return value

    @staticmethod
    def _control_value(snapshot):
        if not snapshot.exists:
            return None
        state = snapshot.to_dict()
        expected = {"schema_version", "configured", "provider_allowance_micro", "stages",
                    "infrastructure_reported_micro", "infrastructure_reserved_micro",
                    "provider_reserved_micro", "provider_used_micro", "paused", "pause_reason"}
        if (not isinstance(state, dict) or set(state) != expected
                or state.get("schema_version") != SCHEMA_VERSION
                or isinstance(state.get("schema_version"), bool) or state.get("configured") is not True
                or not isinstance(state.get("paused"), bool)
                or (state.get("pause_reason") is not None and
                    (not isinstance(state["pause_reason"], str) or not state["pause_reason"]))):
            raise ValueError("Corrupt hosted cloud budget control")
        try:
            _money(state["provider_allowance_micro"], "provider allowance", maximum=_PROVIDER_ALLOWANCE_MAX)
            for key in ("infrastructure_reported_micro", "infrastructure_reserved_micro",
                        "provider_reserved_micro", "provider_used_micro"):
                _money(state[key], key)
            _stage_config(state["stages"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Corrupt hosted cloud budget control") from None
        if state["paused"] != (state["pause_reason"] is not None):
            raise ValueError("Corrupt hosted cloud budget control")
        if (state["provider_reserved_micro"] + state["provider_used_micro"]
                > state["provider_allowance_micro"]):
            raise ValueError("Corrupt hosted cloud budget control")
        return state

    @staticmethod
    def _reservation_value(snapshot, key, stage=None):
        if not snapshot.exists:
            return None
        value = snapshot.to_dict()
        expected = {"schema_version", "operation_key", "stage", "infrastructure_micro",
                    "provider_micro", "provider_remaining_micro", "provider_call_micro",
                    "max_provider_calls", "provider_calls_used"}
        if (not isinstance(value, dict) or set(value) != expected
                or value.get("schema_version") != SCHEMA_VERSION
                or isinstance(value.get("schema_version"), bool)
                or value.get("operation_key") != key or value.get("stage") not in _STAGES
                or (stage is not None and value.get("stage") != stage)):
            raise ValueError("Corrupt hosted cloud budget reservation")
        for field in ("infrastructure_micro", "provider_micro", "provider_remaining_micro", "provider_call_micro"):
            _money(value.get(field), field)
        for field in ("max_provider_calls", "provider_calls_used"):
            count = value.get(field)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError("Corrupt hosted cloud budget reservation")
        if (value["provider_remaining_micro"] > value["provider_micro"]
                or value["provider_calls_used"] > value["max_provider_calls"]
                or value["provider_call_micro"] * value["max_provider_calls"] > value["provider_micro"]
                or value["provider_remaining_micro"] != value["provider_micro"]
                - value["provider_calls_used"] * value["provider_call_micro"]):
            raise ValueError("Corrupt hosted cloud budget reservation")
        return value

    def configure(self, actor: str, reason: str, *, provider_allowance_micro: int, stages: dict,
                  evidence: str | None = None) -> None:
        """Initialize/update explicit operator caps; never renews automatically."""
        actor, reason = _operator(actor, reason)
        if evidence is not None:
            evidence = _key(evidence, "configuration evidence")
        allowance = _money(provider_allowance_micro, "provider allowance", maximum=_PROVIDER_ALLOWANCE_MAX)
        caps = _stage_config(stages)
        ref = self._control
        event_ref = self._events.document(hashlib.sha256(("configure\0" + actor + "\0" + reason).encode()).hexdigest())

        def operation(transaction):
            bound = self._binding(transaction)
            current_snap = ref.get(transaction=transaction)
            event_snap = event_ref.get(transaction=transaction)
            current = self._control_value(current_snap)
            if not bound and current is not None:
                raise ValueError("Cloud budget exists without hosted namespace binding")
            if event_snap.exists:
                raise ValueError("Duplicate cloud budget audit event")
            if current is None:
                if self._has_budget_records(transaction):
                    raise ValueError("Cloud budget records exist without their control ledger")
                current = {"schema_version": SCHEMA_VERSION, "configured": True,
                           "infrastructure_reported_micro": 0, "infrastructure_reserved_micro": 0,
                           "provider_reserved_micro": 0, "provider_used_micro": 0,
                           "paused": False, "pause_reason": None}
            if current["provider_reserved_micro"] + current["provider_used_micro"] > allowance:
                raise CloudBudgetExceeded("New provider allowance is below committed and reserved cost")
            result = {**current, "provider_allowance_micro": allowance, "stages": caps}
            transaction.set(ref, result)
            transaction.create(event_ref, self._audit("configure", actor, reason,
                {"provider_allowance_micro": allowance, "stages": caps, "evidence": evidence}))
            return None, bound

        self._run(operation, bind_if_missing=True)

    @staticmethod
    def _audit(action, actor, reason, details):
        return {"schema_version": SCHEMA_VERSION, "action": action, "actor": actor,
                "reason": reason, "details": details}

    def status(self) -> dict:
        """Read-only status; absent control stays absent and provider untouched."""
        def read(transaction):
            bound = self._binding(transaction)
            state = self._control_value(self._control.get(transaction=transaction))
            if state is None and self._has_budget_records(transaction):
                raise ValueError("Cloud budget records exist without their control ledger")
            return state, bound

        state = self._run(read)
        if state is None:
            return {"configured": False, "paused": True, "reason": "uninitialized",
                    "alert_thresholds_micro": list(_ALERTS)}
        return {"configured": True, "paused": state["paused"], "pause_reason": state["pause_reason"],
                "provider_allowance_micro": state["provider_allowance_micro"],
                "provider_reserved_micro": state["provider_reserved_micro"],
                "provider_used_micro": state["provider_used_micro"],
                "infrastructure_reported_micro": state["infrastructure_reported_micro"],
                "infrastructure_reserved_micro": state["infrastructure_reserved_micro"],
                "infrastructure_alert_thresholds_micro": list(_ALERTS)}

    def inspect(self, operation_key: str) -> dict:
        """Read one operation's retained reservation and permanent settlement marker."""
        key = _key(operation_key, "operation key")
        reservation_ref = self._reservations.document(hashlib.sha256(key.encode()).hexdigest())
        settlement_ref = self._settlement_ref(key)

        def read(transaction):
            bound = self._binding(transaction)
            reservation_snap = reservation_ref.get(transaction=transaction)
            settlement_snap = settlement_ref.get(transaction=transaction)
            reservation = self._reservation_value(reservation_snap, key)
            settlement = self._settlement_value(settlement_snap, key)
            if not bound and (reservation is not None or settlement is not None):
                raise ValueError("Hosted cloud budget records exist without their namespace binding")
            calls = []
            for snapshot in self._calls.stream(transaction=transaction):
                value = snapshot.to_dict()
                if isinstance(value, dict) and value.get("operation_key") == key:
                    calls.append(value)
            calls.sort(key=lambda item: item.get("call_id", ""))
            return {"operation_key": key, "reservation": reservation, "settlement": settlement,
                    "provider_calls": calls}, bound
        return self._run(read)

    def settle(self, actor: str, reason: str, operation_key: str, *, evidence: str,
               operation_store, execution_status) -> dict:
        """Close one terminal operation after independently checking every submitted Cloud Run execution.

        Cloud Run is queried before entering Firestore's transaction. The
        operation and attempt snapshot is then re-read transactionally and must
        remain identical before the immutable settlement marker is written.
        Caller-supplied booleans are never accepted as stop evidence.
        """
        actor, reason = _operator(actor, reason)
        key = _key(operation_key, "operation key")
        evidence = _key(evidence, "settlement evidence")
        snapshot = operation_store.settlement_snapshot(key)
        if not isinstance(snapshot, dict):
            raise CloudBudgetExceeded("Operation settlement evidence is malformed")
        operation_id = snapshot.get("operation_id")
        fence = snapshot.get("fence")
        if (not isinstance(operation_id, str) or not operation_id
                or not isinstance(fence, int) or isinstance(fence, bool) or fence < 1
                or snapshot.get("status") not in {"complete", "failed"}
                or snapshot.get("provider_outcome_pending") is not False
                or snapshot.get("active_slot") is not False
                or not isinstance(snapshot.get("attempts"), list)):
            raise CloudBudgetExceeded("Operation is not terminal and safe to settle")
        execution_names = []
        for attempt in snapshot["attempts"]:
            if not isinstance(attempt, dict):
                raise CloudBudgetExceeded("Operation attempt evidence is malformed")
            if attempt.get("state") in {"running", "uncertain"}:
                raise CloudBudgetExceeded("Operation still has an active or uncertain attempt")
            submitted = attempt.get("submitted")
            name = attempt.get("execution_name")
            if not isinstance(submitted, bool):
                raise CloudBudgetExceeded("Operation attempt submission state is unknown")
            if submitted:
                if not isinstance(name, str) or not name:
                    raise CloudBudgetExceeded("Submitted attempt has no confirmed execution identity")
                execution_names.append(name)
            elif name is not None:
                raise CloudBudgetExceeded("Unsubmitted attempt has a conflicting execution identity")
        if len(execution_names) != len(set(execution_names)):
            raise CloudBudgetExceeded("Cloud Run execution identity is duplicated across attempts")
        for name in execution_names:
            state = execution_status(name)
            if state not in {"succeeded", "failed", "cancelled"}:
                raise CloudBudgetExceeded("Cloud Run execution is active or its terminal outcome is unknown")

        control_ref = self._control
        reservation_ref = self._reservations.document(hashlib.sha256(key.encode()).hexdigest())
        settlement_ref = self._settlement_ref(key)
        record = {"schema_version": SCHEMA_VERSION, "operation_key": key,
                  "actor": actor, "reason": reason, "operation_id": operation_id, "fence": fence,
                  "execution_names": execution_names, "evidence": evidence}

        def operation(transaction):
            bound = self._binding(transaction)
            if not bound:
                raise CloudBudgetExceeded("Hosted cloud budget namespace is uninitialized")
            state = self._control_value(control_ref.get(transaction=transaction))
            reservation = self._reservation_value(reservation_ref.get(transaction=transaction), key)
            existing_snap = settlement_ref.get(transaction=transaction)
            existing = self._settlement_value(existing_snap, key)
            current = operation_store.settlement_snapshot(key, transaction=transaction)
            if current != snapshot:
                raise CloudBudgetExceeded("Operation changed during settlement; inspect and retry")
            if state is None or reservation is None:
                raise CloudBudgetExceeded("Cloud operation has no durable budget reservation")
            if existing is not None:
                raise CloudBudgetExceeded("Cloud operation key is already permanently settled")
            released = reservation["provider_remaining_micro"]
            if released > state["provider_reserved_micro"]:
                raise ValueError("Corrupt hosted provider reservation totals")
            record["provider_released_micro"] = released
            updated = {**state, "provider_reserved_micro": state["provider_reserved_micro"] - released}
            transaction.set(control_ref, updated)
            transaction.create(settlement_ref, record)
            event_ref = self._events.document(hashlib.sha256(
                ("settle\0" + key + "\0" + actor + "\0" + reason).encode()).hexdigest())
            transaction.create(event_ref, self._audit("settle", actor, reason,
                {"operation_key_sha256": hashlib.sha256(key.encode()).hexdigest(),
                 "operation_id": operation_id, "fence": fence,
                 "execution_names": execution_names, "provider_released_micro": released,
                 "evidence": evidence}))
            return {**record}, bound
        return self._run(operation)

    def prepare_reservation(self, operation_key: str, stage: str):
        """Return a tx callback that reads first and returns a zero-read writer.

        Compose it first in a transaction: call the returned callback, then do
        other read/write admission callbacks, then invoke its returned writer,
        followed by enqueue writes. This preserves Firestore's read-before-write
        requirement across combined ledgers.
        """
        key = _key(operation_key, "operation key")
        if stage not in _STAGES:
            raise ValueError("Invalid cloud budget stage")
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        control_ref = self._control
        reservation_ref = self._reservations.document(key_hash)
        settlement_ref = self._settlement_ref(key)

        def read_in_transaction(transaction):
            if not self._binding(transaction):
                raise CloudBudgetExceeded("Hosted cloud budget namespace is uninitialized")
            control_snap = control_ref.get(transaction=transaction)
            reservation_snap = reservation_ref.get(transaction=transaction)
            settlement_snap = settlement_ref.get(transaction=transaction)
            if self._settlement_value(settlement_snap, key) is not None:
                raise CloudBudgetExceeded("Settled cloud operation key is permanently closed")
            state = self._control_value(control_snap)
            if state is None:
                raise CloudBudgetExceeded("Hosted cloud budget is uninitialized")
            prior = self._reservation_value(reservation_snap, key, stage)
            if prior is not None:
                writer = lambda: None
                if prior["stage"] != stage:
                    raise CloudBudgetExceeded("Operation key already reserved for another stage")
                if state["paused"]:
                    raise CloudBudgetExceeded("Hosted cloud work is paused")
                return writer
            if state["paused"]:
                raise CloudBudgetExceeded("Hosted cloud work is paused")
            cap = state["stages"][stage]
            if state["infrastructure_reported_micro"] + state["infrastructure_reserved_micro"] + cap["infrastructure_micro"] >= _INFRA_PAUSE:
                raise CloudBudgetExceeded("Infrastructure cost threshold reached")
            if state["provider_reserved_micro"] + state["provider_used_micro"] + cap["provider_micro"] > state["provider_allowance_micro"]:
                raise CloudBudgetExceeded("Provider allowance exhausted")
            updated = {**state,
                       "infrastructure_reserved_micro": state["infrastructure_reserved_micro"] + cap["infrastructure_micro"],
                       "provider_reserved_micro": state["provider_reserved_micro"] + cap["provider_micro"]}
            record = {"schema_version": SCHEMA_VERSION, "operation_key": key, "stage": stage,
                      "infrastructure_micro": cap["infrastructure_micro"],
                      "provider_micro": cap["provider_micro"],
                      "provider_remaining_micro": cap["provider_micro"],
                      "provider_call_micro": cap["provider_call_micro"],
                      "max_provider_calls": cap["max_provider_calls"], "provider_calls_used": 0}

            def writer():
                transaction.set(control_ref, updated)
                transaction.create(reservation_ref, record)
            return writer

        return read_in_transaction

    def check_dispatch_in_transaction(self, transaction, operation_key: str) -> bool:
        """Check a reservation using caller transaction reads only."""
        key = _key(operation_key, "operation key")
        ref = self._reservations.document(hashlib.sha256(key.encode()).hexdigest())
        settlement_ref = self._settlement_ref(key)
        bound = self._binding(transaction)
        if not bound:
            raise CloudBudgetExceeded("Hosted cloud budget namespace is uninitialized")
        state = self._control_value(self._control.get(transaction=transaction))
        if self._settlement_value(settlement_ref.get(transaction=transaction), key) is not None:
            raise CloudBudgetExceeded("Settled cloud operation key is permanently closed")
        reservation = self._reservation_value(ref.get(transaction=transaction), key)
        if state is None or reservation is None:
            raise CloudBudgetExceeded("Hosted cloud operation has no durable reservation")
        _require_production_open(state)
        return True

    def check_dispatch(self, operation_key: str) -> None:
        def operation(transaction):
            return self.check_dispatch_in_transaction(transaction, operation_key), True
        self._run(operation)

    def authorize_provider(self, operation_key: str, call_id: str) -> int:
        """Idempotently debit one configured maximum-cost provider call."""
        key = _key(operation_key, "operation key")
        call_id = _key(call_id, "provider call ID")
        reservation_ref = self._reservations.document(hashlib.sha256(key.encode()).hexdigest())
        settlement_ref = self._settlement_ref(key)
        call_ref = self._calls.document(hashlib.sha256(call_id.encode()).hexdigest())
        control_ref = self._control

        def operation(transaction):
            bound = self._binding(transaction)
            if not bound:
                raise CloudBudgetExceeded("Hosted cloud budget namespace is uninitialized")
            state = self._control_value(control_ref.get(transaction=transaction))
            reservation_snap = reservation_ref.get(transaction=transaction)
            settlement_snap = settlement_ref.get(transaction=transaction)
            call_snap = call_ref.get(transaction=transaction)
            if self._settlement_value(settlement_snap, key) is not None:
                raise CloudBudgetExceeded("Settled cloud operation key is permanently closed")
            reservation = self._reservation_value(reservation_snap, key)
            if state is None or reservation is None:
                raise CloudBudgetExceeded("Provider call has no durable operation reservation")
            if call_snap.exists:
                value = call_snap.to_dict()
                if (not isinstance(value, dict) or set(value) != {"schema_version", "operation_key", "call_id", "amount_micro"}
                        or value.get("schema_version") != SCHEMA_VERSION or value.get("operation_key") != key
                        or value.get("call_id") != call_id):
                    raise CloudBudgetExceeded("Provider call ID already used")
                _money(value.get("amount_micro"), "provider call debit")
                return value["amount_micro"], bound
            _require_production_open(state)
            amount = reservation["provider_call_micro"]
            if (reservation["provider_calls_used"] >= reservation["max_provider_calls"]
                    or amount > reservation["provider_remaining_micro"]
                    or amount > state["provider_reserved_micro"]):
                raise CloudBudgetExceeded("Provider operation reservation exhausted")
            updated_state = {**state,
                             "provider_reserved_micro": state["provider_reserved_micro"] - amount,
                             "provider_used_micro": state["provider_used_micro"] + amount}
            updated_reservation = {**reservation,
                                   "provider_remaining_micro": reservation["provider_remaining_micro"] - amount,
                                   "provider_calls_used": reservation["provider_calls_used"] + 1}
            transaction.set(control_ref, updated_state)
            transaction.set(reservation_ref, updated_reservation)
            transaction.create(call_ref, {"schema_version": SCHEMA_VERSION, "operation_key": key,
                                          "call_id": call_id, "amount_micro": amount})
            return amount, bound
        return self._run(operation)

    def observe_report(self, interval_start: str, reported_micro: int, event_id: str) -> dict:
        """Apply interval highwater reports once; threshold latch never clears."""
        interval_start = _key(interval_start, "report interval", document_id=True)
        event_id = _key(event_id, "report event ID")
        amount = _money(reported_micro, "reported infrastructure cost")
        month = BillingPeriod.from_interval(interval_start).value
        interval_ref = self._intervals.document(interval_start)
        closed_month_ref = self._closed_infra_months.document(month)
        event_ref = self._events.document(hashlib.sha256(("report\0" + event_id).encode()).hexdigest())
        control_ref = self._control

        def operation(transaction):
            bound = self._binding(transaction)
            if not bound:
                raise CloudBudgetExceeded("Hosted cloud budget namespace is uninitialized")
            control_snap = control_ref.get(transaction=transaction)
            interval_snap = interval_ref.get(transaction=transaction)
            event_snap = event_ref.get(transaction=transaction)
            closed_month_snap = closed_month_ref.get(transaction=transaction)
            state = self._control_value(control_snap)
            if state is None:
                raise CloudBudgetExceeded("Hosted cloud budget is uninitialized")
            closed_month = self._closed_infra_month_value(closed_month_snap, month)
            if event_snap.exists:
                event = event_snap.to_dict()
                if (not isinstance(event, dict) or event.get("action") != "infrastructure_report"
                        or not isinstance(event.get("details"), dict)
                        or event["details"].get("event_id") != event_id
                        or event["details"].get("interval_start") != interval_start
                        or event["details"].get("reported_micro") != amount):
                    raise CloudBudgetExceeded("Report event ID already used")
                if closed_month is not None:
                    return {"ignored": True, "reason": "reconciled_billing_period",
                            "paused": state["paused"]}, bound
                current = interval_snap.to_dict() if interval_snap.exists else {"reported_micro": 0}
                return {"reported_micro": current["reported_micro"], "paused": state["paused"]}, bound
            if closed_month is not None:
                return {"ignored": True, "reason": "reconciled_billing_period",
                        "paused": state["paused"]}, bound
            if interval_snap.exists:
                previous = interval_snap.to_dict()
                if (not isinstance(previous, dict) or set(previous) != {"schema_version", "interval_start", "reported_micro"}
                        or previous.get("schema_version") != SCHEMA_VERSION or previous.get("interval_start") != interval_start):
                    raise ValueError("Corrupt infrastructure report interval")
                highwater = _money(previous.get("reported_micro"), "interval highwater")
            else:
                highwater = 0
            new_highwater = max(highwater, amount)
            delta = new_highwater - highwater
            total = state["infrastructure_reported_micro"] + delta
            pause = state["paused"] or total >= _INFRA_PAUSE
            updated = {**state, "infrastructure_reported_micro": total,
                       "paused": pause, "pause_reason": state["pause_reason"] or ("infrastructure_threshold" if pause else None)}
            transaction.set(control_ref, updated)
            transaction.set(interval_ref, {"schema_version": SCHEMA_VERSION, "interval_start": interval_start,
                                           "reported_micro": new_highwater})
            transaction.create(event_ref, self._audit("infrastructure_report", "provider", "reported cost",
                                                      {"event_id": event_id, "interval_start": interval_start,
                                                       "reported_micro": amount, "highwater_micro": new_highwater}))
            return {"reported_micro": total, "paused": pause, "alert_thresholds_micro": list(_ALERTS)}, bound
        return self._run(operation)

    def set_paused(self, actor: str, reason: str, *, paused: bool, evidence: str | None = None) -> None:
        actor, reason = _operator(actor, reason)
        if evidence is not None:
            evidence = _key(evidence, "pause/resume evidence")
        if not isinstance(paused, bool):
            raise ValueError("paused must be boolean")
        self._operator_mutation("pause" if paused else "resume", actor, reason,
                                lambda state: {**state, "paused": paused, "pause_reason": reason if paused else None},
                                details={"evidence": evidence})

    def reconcile(self, actor: str, reason: str, *, evidence: str, billing_period: str,
                  infrastructure_reported_micro: int,
                  infrastructure_reserved_micro: int, provider_reserved_micro: int,
                  provider_used_micro: int) -> None:
        """Apply explicit billed-month closeout, retaining all provider debits.

        Evidence identifies the billing export/invoice reviewed by the operator.
        Infrastructure reported cost may reset for a new billing month; settled
        infrastructure reservations may be released only by this explicit step.
        """
        actor, reason = _operator(actor, reason)
        evidence = _key(evidence, "billing reconciliation evidence")
        billing_period = BillingPeriod(billing_period).value
        values = {"infrastructure_reported_micro": _money(infrastructure_reported_micro, "reported infrastructure cost"),
                  "infrastructure_reserved_micro": _money(infrastructure_reserved_micro, "infrastructure reservations"),
                  "provider_reserved_micro": _money(provider_reserved_micro, "provider reservations"),
                  "provider_used_micro": _money(provider_used_micro, "provider usage")}
        def update(state):
            if values["provider_reserved_micro"] + values["provider_used_micro"] > state["provider_allowance_micro"]:
                raise CloudBudgetExceeded("Reconciled provider amounts exceed allowance")
            return {**state, **values}
        def validate(transaction):
            infrastructure_reserved = 0
            provider_reserved = 0
            settlements = {}
            for snapshot in self._settlements.stream(transaction=transaction):
                value = snapshot.to_dict()
                if not isinstance(value, dict) or not isinstance(value.get("operation_key"), str):
                    raise ValueError("Corrupt hosted cloud budget settlement")
                settlement = self._settlement_value(snapshot, value["operation_key"])
                settlements[settlement["operation_key"]] = settlement
            for snapshot in self._reservations.stream(transaction=transaction):
                value = snapshot.to_dict()
                if not isinstance(value, dict):
                    raise ValueError("Corrupt hosted cloud budget reservation")
                reservation = self._reservation_value(snapshot, value.get("operation_key"))
                if reservation["operation_key"] not in settlements:
                    infrastructure_reserved += reservation["infrastructure_micro"]
                    provider_reserved += reservation["provider_remaining_micro"]
            provider_used = 0
            for snapshot in self._calls.stream(transaction=transaction):
                value = snapshot.to_dict()
                if (not isinstance(value, dict)
                        or set(value) != {"schema_version", "operation_key", "call_id", "amount_micro"}
                        or value.get("schema_version") != SCHEMA_VERSION
                        or not isinstance(value.get("operation_key"), str)
                        or not isinstance(value.get("call_id"), str)):
                    raise ValueError("Corrupt hosted provider call ledger")
                provider_used += _money(value.get("amount_micro"), "provider call debit")
            if (values["infrastructure_reserved_micro"] < infrastructure_reserved
                    or values["provider_reserved_micro"] < provider_reserved
                    or values["provider_used_micro"] != provider_used):
                raise CloudBudgetExceeded("Reconciliation cannot reduce totals below unsettled reservations or durable debits")
        closeout_ref = self._closed_infra_months.document(billing_period)
        def validate_closeout(transaction):
            validate(transaction)
            if closeout_ref.get(transaction=transaction).exists:
                raise ValueError("Billing period is already reconciled")
        self._operator_mutation("reconcile", actor, reason, update, validate=validate_closeout,
                                details={"evidence": evidence, "billing_period": billing_period, **values},
                                after_write=lambda transaction: transaction.create(closeout_ref, {
                                    "schema_version": SCHEMA_VERSION, "billing_period": billing_period,
                                    "actor": actor, "reason": reason, "evidence": evidence}))

    def _operator_mutation(self, action, actor, reason, update, *, validate=None, details=None, after_write=None):
        ref = self._control
        event_id = hashlib.sha256((action + "\0" + actor + "\0" + reason).encode()).hexdigest()
        event_ref = self._events.document(event_id)
        def operation(transaction):
            bound = self._binding(transaction)
            snapshot = ref.get(transaction=transaction)
            event_snap = event_ref.get(transaction=transaction)
            state = self._control_value(snapshot)
            if state is None:
                raise CloudBudgetExceeded("Hosted cloud budget is uninitialized")
            if event_snap.exists:
                raise ValueError("Duplicate cloud budget audit event")
            if validate is not None:
                validate(transaction)
            transaction.set(ref, update(state))
            if after_write is not None:
                after_write(transaction)
            transaction.create(event_ref, self._audit(action, actor, reason, details or {}))
            return None, bound
        self._run(operation)
