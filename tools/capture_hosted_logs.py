"""Capture a narrow, read-only hosted validation log window with gcloud."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = "koetts-9bf7f"
DEFAULT_REGION = "us-central1"
FRONTEND_REGION = "us-east4"
JOBS = ("koetts-magi", "koetts-pipeline", "koetts-artifact-gc")


def _utc_rfc3339(value: str, label: str) -> str:
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)", value):
        raise ValueError(f"--{label} must be RFC3339 UTC (end with Z or +00:00)")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"--{label} is not a valid RFC3339 timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ValueError(f"--{label} must be UTC")
    return parsed.isoformat().replace("+00:00", "Z")


def _output_directory(value: str) -> Path:
    requested = Path(value)
    if not requested.is_absolute():
        requested = ROOT / requested
    target = requested.resolve()
    results = (ROOT / "results").resolve()
    if target == results or results not in target.parents:
        raise ValueError("output must be a new directory beneath the repository results/ directory")
    if target.exists():
        raise ValueError(f"output directory already exists: {target}")
    target.mkdir(parents=True, mode=0o700)
    os.chmod(target, 0o700)
    return target


def _filter(project: str, region: str, since: str, until: str) -> str:
    clauses = [
        f'timestamp >= "{since}"',
        f'timestamp <= "{until}"',
        f'resource.type="cloud_run_revision" AND resource.labels.service_name="koetts-api" AND resource.labels.location="{region}"',
    ]
    clauses.append(
        f'(resource.type="cloud_run_revision" AND resource.labels.service_name="koetts" AND resource.labels.location="{FRONTEND_REGION}")'
    )
    clauses.extend(
        f'(resource.type="cloud_run_job" AND resource.labels.job_name="{job}" AND resource.labels.location="{region}")'
        for job in JOBS
    )
    return " AND ".join([clauses[0], clauses[1], "(" + " OR ".join(clauses[2:]) + ")"])


def _summary(entries: list[dict], project: str, region: str, since: str, until: str) -> dict:
    severity = Counter(str(item.get("severity", "DEFAULT")) for item in entries)
    resources = Counter(str(item.get("resource", {}).get("type", "unknown")) for item in entries)
    status = Counter()
    for item in entries:
        code = item.get("httpRequest", {}).get("status")
        if code is None:
            payload = item.get("jsonPayload", {})
            code = payload.get("status") if isinstance(payload, dict) else None
        if code is not None:
            status[str(code)] += 1
    times = [str(item["timestamp"]) for item in entries if item.get("timestamp")]
    return {
        "capture_status": "completed",
        "project": project,
        "region": region,
        "since": since,
        "until": until,
        "entry_count": len(entries),
        "time_range_observed": {"first": min(times) if times else None, "last": max(times) if times else None},
        "severity_counts": dict(sorted(severity.items())),
        "http_or_payload_status_counts": dict(sorted(status.items())),
        "resource_type_counts": dict(sorted(resources.items())),
        "scope": {"cloud_run_service": "koetts-api", "cloud_run_jobs": list(JOBS),
                  "frontend_service": "koetts", "frontend_region": FRONTEND_REGION},
        "limitations": [
            "Logs are operational evidence for the selected window, not proof of complete system behavior.",
            "Log counts and severity do not establish Gemini usage, model cost, or billing accuracy.",
        ],
    }


def capture(project: str, region: str, since: str, until: str, output: str) -> Path:
    since = _utc_rfc3339(since, "since")
    until = _utc_rfc3339(until, "until")
    if datetime.fromisoformat(since.replace("Z", "+00:00")) >= datetime.fromisoformat(until.replace("Z", "+00:00")):
        raise ValueError("--since must be earlier than --until")
    target = _output_directory(output)
    query = _filter(project, region, since, until)
    try:
        result = subprocess.run(
            ["gcloud", "logging", "read", query, f"--project={project}", "--format=json"],
            cwd=ROOT, check=True, capture_output=True, text=True, timeout=180,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"gcloud logging read failed: {exc}") from exc
    try:
        entries = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("gcloud returned invalid JSON; no capture files were written") from exc
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise RuntimeError("gcloud returned an unexpected JSON shape; no capture files were written")
    for filename, content in (
        ("logs.json", json.dumps(entries, indent=2, sort_keys=True) + "\n"),
        ("summary.json", json.dumps(_summary(entries, project, region, since, until), indent=2, sort_keys=True) + "\n"),
    ):
        path = target / filename
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
        os.chmod(path, 0o600)
    return target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, help="RFC3339 UTC start, for example 2026-11-01T00:00:00Z")
    parser.add_argument("--until", required=True, help="RFC3339 UTC end, for example 2026-11-01T01:00:00Z")
    parser.add_argument("--output", required=True, help="New directory under results/, e.g. results/hosted-validation-20261101T010000Z")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--region", default=DEFAULT_REGION)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        target = capture(args.project, args.region, args.since, args.until, args.output)
    except (ValueError, RuntimeError) as exc:
        print(f"capture-hosted-logs: {exc}", file=sys.stderr)
        return 2
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
