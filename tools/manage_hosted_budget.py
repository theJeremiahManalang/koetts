"""Interactively prepare and optionally apply hosted budget limits.

The wizard writes a private stage-cap file and delegates ledger changes to the
existing audited cloud operator. It prints a plan unless ``--execute`` is set.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from decimal import Decimal, InvalidOperation

from manga_worker.cloud_budget import _stage_config

MICROS_PER_USD = 1_000_000
PROVIDER_ALLOWANCE_MAX_MICRO = 80 * MICROS_PER_USD


def _usd(prompt: str, input_fn) -> int:
    raw = input_fn(prompt).strip()
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        raise ValueError("Enter a valid USD amount.") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError("Enter a finite, nonnegative USD amount.")
    micros = amount * MICROS_PER_USD
    if micros != micros.to_integral_value():
        raise ValueError("Enter a nonnegative USD amount with at most six decimal places.")
    return int(micros)


def _calls(prompt: str, input_fn) -> int:
    raw = input_fn(prompt).strip()
    if not re.fullmatch(r"0|[1-9][0-9]*", raw):
        raise ValueError("Enter a nonnegative whole number of calls.")
    return int(raw)


def _default_output(root: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return root / "results" / "hosted-budget" / f"stage-caps-{timestamp}.json"


def _write_private(path: Path, stages: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise ValueError("Output directory must not be a symlink.")
    if os.stat(path.parent).st_mode & 0o077:
        raise ValueError("Output directory must be private (permissions 700 or stricter).")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(stages, output, indent=2, sort_keys=True)
            output.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-allowance-usd", type=Decimal,
                        help="overall provider allowance; prompts when omitted")
    parser.add_argument("--stage-caps", type=Path,
                        help="reuse a previously reviewed caps JSON instead of prompting")
    parser.add_argument("--actor", required=True, help="audited operator identity")
    parser.add_argument("--reason", required=True, help="why limits are changing")
    parser.add_argument("--evidence", required=True, help="ticket, checklist, or test record")
    parser.add_argument("--output", type=Path, help="private output JSON path")
    parser.add_argument("--execute", action="store_true", help="write limits to the live ledger")
    return parser


def main(argv=None, *, input_fn=input, print_fn=print) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.stage_caps and args.output:
            raise ValueError("Use either --stage-caps or --output, not both.")
        allowance = (_usd("Overall provider allowance (USD): ", input_fn)
                     if args.provider_allowance_usd is None else
                     _amount_to_micros(args.provider_allowance_usd))
        if allowance > PROVIDER_ALLOWANCE_MAX_MICRO:
            raise ValueError("Provider allowance exceeds the USD 80 maximum.")
        if args.stage_caps:
            output = args.stage_caps.resolve()
            stages = _read_caps(output)
        else:
            stages = {}
            for stage in ("magi", "pipeline"):
                print_fn(f"Configure {stage} stage:")
                stages[stage] = {
                    "infrastructure_micro": _usd("  Infrastructure cap (USD): ", input_fn),
                    "provider_micro": _usd("  Provider operation cap (USD): ", input_fn),
                    "provider_call_micro": _usd("  Provider call cap (USD): ", input_fn),
                    "max_provider_calls": _calls("  Maximum provider calls: ", input_fn),
                }
            stages = _stage_config(stages)
        if any(stages["magi"][field] for field in ("provider_micro", "provider_call_micro", "max_provider_calls")):
            raise ValueError("The magi stage does not use provider calls; keep its provider caps at zero.")
        if sum(stage["provider_micro"] for stage in stages.values()) > allowance:
            raise ValueError("Combined provider operation caps exceed the overall provider allowance.")
        if not args.stage_caps:
            root = Path(__file__).resolve().parents[1]
            output = args.output or _default_output(root)
            if not output.is_absolute():
                output = root / output
            _write_private(output, stages)
            print_fn(f"Stage caps saved: {output}")

        from manga_worker.cloud_operator import main as operator_main

        command = [
            "configure",
            "--provider-allowance-micro", str(allowance),
            "--stage-caps", str(output),
            "--actor", args.actor,
            "--reason", args.reason,
            "--evidence", args.evidence,
        ]
        if args.execute:
            command.append("--execute")
        return operator_main(command)
    except (InvalidOperation, OSError, ValueError) as exc:
        print_fn(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2


def _amount_to_micros(amount: Decimal) -> int:
    if not amount.is_finite() or amount < 0:
        raise ValueError("Provider allowance must be a nonnegative USD amount.")
    micros = amount * MICROS_PER_USD
    if micros != micros.to_integral_value():
        raise ValueError("USD amounts support at most six decimal places.")
    return int(micros)


def _read_caps(path: Path) -> dict:
    try:
        stages = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read stage caps: {exc}") from None
    return _stage_config(stages)


if __name__ == "__main__":
    raise SystemExit(main())
