"""Explicit developer CLI for hosted cloud budget controls.

Plans are the default. SDK clients are constructed only after argument and
configuration validation and only when ``--execute`` is present.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from .cloud import CloudSettings
from .cloud_artifacts import artifact_store_identity
from .cloud_budget import BillingPeriod, CloudBudgetLedger, _key, _money, _operator, _stage_config


def _parser():
    parser = argparse.ArgumentParser(prog="python -m manga_worker.cloud_operator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def common(name, *, mutation=False):
        command = subparsers.add_parser(name)
        command.add_argument("--execute", action="store_true", help="apply the operation (otherwise print a plan)")
        if mutation:
            command.add_argument("--actor", required=True)
            command.add_argument("--reason", required=True)
            command.add_argument("--evidence", required=True)
        return command

    common("status")
    inspect = common("inspect")
    inspect.add_argument("--operation-key", required=True)
    configure = common("configure", mutation=True)
    configure.add_argument("--provider-allowance-micro", required=True, type=int)
    configure.add_argument("--stage-caps", required=True, type=Path)
    common("pause", mutation=True)
    resume = common("resume", mutation=True)
    settle = common("settle", mutation=True)
    settle.add_argument("--operation-key", required=True)
    reconcile = common("reconcile", mutation=True)
    reconcile.add_argument("--infrastructure-reported-micro", required=True, type=int)
    reconcile.add_argument("--infrastructure-reserved-micro", required=True, type=int)
    reconcile.add_argument("--provider-reserved-micro", required=True, type=int)
    reconcile.add_argument("--provider-used-micro", required=True, type=int)
    reconcile.add_argument("--billing-period", required=True, help="Closed infrastructure billing month (YYYY-MM)")
    return parser


def _read_caps(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read stage caps JSON: {exc}") from None
    return _stage_config(value)


def _validate(args):
    if args.command in {"configure", "pause", "resume", "settle", "reconcile"}:
        _operator(args.actor, args.reason)
        _key(args.evidence, "evidence reference")
    if args.command == "configure":
        _money(args.provider_allowance_micro, "provider allowance", maximum=80_000_000)
        args.stage_caps_value = _read_caps(args.stage_caps)
    elif args.command == "inspect":
        _key(args.operation_key, "operation key")
    elif args.command == "reconcile":
        args.billing_period = BillingPeriod(args.billing_period).value
        for field in ("infrastructure_reported_micro", "infrastructure_reserved_micro",
                      "provider_reserved_micro", "provider_used_micro"):
            _money(getattr(args, field), field)
    if args.command == "settle":
        args.region = os.environ.get("MANGA_CLOUD_REGION", "")
        args.job_names = {"magi": os.environ.get("MANGA_MAGI_JOB", ""),
                          "pipeline": os.environ.get("MANGA_PIPELINE_JOB", "")}
        if not args.region or not all(args.job_names.values()):
            raise ValueError("Explicit MANGA_CLOUD_REGION, MANGA_MAGI_JOB, and MANGA_PIPELINE_JOB are required")
        if (not re.fullmatch(r"[a-z]+-[a-z]+[0-9]+", args.region)
                or any(not re.fullmatch(r"[a-z]([-a-z0-9]*[a-z0-9])?", name)
                       for name in args.job_names.values())):
            raise ValueError("Cloud Run region and job names must be valid resource names")
    if args.execute:
        args.settings = CloudSettings.from_environment()
    return args


def _connect(settings):
    """Create Firestore client only after all local validation and explicit execution."""
    from google.cloud import firestore
    client = firestore.Client(project=settings.project, database=settings.database)
    return client, CloudBudgetLedger(client, settings.dataset, artifact_store_identity(settings.bucket, settings.namespace))


def _plan(args):
    values = {key: value for key, value in vars(args).items()
              if key not in {"execute", "stage_caps_value", "stage_caps", "region", "job_names"}}
    if getattr(args, "stage_caps", None):
        values["stage_caps_path"] = str(args.stage_caps)
        values["stages"] = args.stage_caps_value
    values["stage_caps"] = values.pop("stage_caps", None)
    return {"mode": "plan", "action": args.command, "changes_cloud_state": args.command in {
        "configure", "pause", "resume", "settle", "reconcile"}, "arguments": values}


def _execute(args):
    settings = args.settings
    client, ledger = _connect(settings)
    try:
        if args.command == "status":
            result = ledger.status()
        elif args.command == "inspect":
            result = ledger.inspect(args.operation_key)
        elif args.command == "configure":
            ledger.configure(args.actor, args.reason, provider_allowance_micro=args.provider_allowance_micro,
                             stages=args.stage_caps_value, evidence=args.evidence)
            result = ledger.status()
        elif args.command in {"pause", "resume"}:
            ledger.set_paused(args.actor, args.reason, paused=args.command == "pause", evidence=args.evidence)
            result = ledger.status()
        elif args.command == "settle":
            from .cloud_jobs import CloudRunJobs
            from .cloud_operations import FirestoreOperationStore
            operations = FirestoreOperationStore(client, settings.dataset, artifact_store_identity(settings.bucket, settings.namespace))
            jobs = CloudRunJobs(settings.project, args.region, args.job_names)
            result = ledger.settle(args.actor, args.reason, args.operation_key, evidence=args.evidence,
                                   operation_store=operations, execution_status=jobs.status)
        elif args.command == "reconcile":
            ledger.reconcile(args.actor, args.reason, evidence=args.evidence,
                             billing_period=args.billing_period,
                             infrastructure_reported_micro=args.infrastructure_reported_micro,
                             infrastructure_reserved_micro=args.infrastructure_reserved_micro,
                             provider_reserved_micro=args.provider_reserved_micro,
                             provider_used_micro=args.provider_used_micro)
            result = ledger.status()
        else:  # pragma: no cover - parser constrains the command set
            raise ValueError("Unsupported cloud operator command")
        return {"mode": "executed", "action": args.command, "result": result}
    finally:
        close = getattr(client, "close", None)
        if close:
            close()


def main(argv=None):
    parser = _parser()
    try:
        args = _validate(parser.parse_args(argv))
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    try:
        output = _execute(args) if args.execute else _plan(args)
    except Exception:
        print(json.dumps({"error": "Cloud operator action failed; details withheld."}, sort_keys=True))
        return 2
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover - covered through main
    raise SystemExit(main())
