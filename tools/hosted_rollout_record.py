"""Create an offline, exclusive phase 4 hosted rollout evidence record."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


_PROTECTED_PARTS = {
    ".aws", ".cache", ".firebase", ".git", ".next", ".venv", "cache", "caches",
    "credentials", "data", "models", "node_modules", "results", "secrets",
}
_PLACEHOLDER = re.compile(r"^(?:<.*>|YOUR_.+|IMAGE_DIGEST|PREVIOUS_.+|TBD|TODO)$", re.IGNORECASE)


def _required_text(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned or _PLACEHOLDER.fullmatch(cleaned):
        raise ValueError(f"{label} must be an explicit value, not blank or a placeholder")
    if any(ord(character) < 32 for character in cleaned):
        raise ValueError(f"{label} contains a control character")
    return cleaned


def _safe_path(value: str | Path, label: str) -> Path:
    if not str(value).strip():
        raise ValueError(f"{label} must be an explicit path")
    path = Path(value).expanduser().resolve()
    if any(part.lower() in _PROTECTED_PARTS for part in path.parts):
        raise ValueError(f"{label} cannot be inside a data, cache, dependency, or credential directory")
    return path


def _git_state(repo: Path) -> dict:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=repo,
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=repo,
            check=True, capture_output=True, text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f"Could not capture Git candidate state: {exc}") from exc
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", sha):
        raise ValueError("Git returned an invalid candidate SHA")
    entries = [line for line in status.splitlines() if line]
    return {"sha": sha, "clean": not entries, "status_entries": entries}


def build_record(args: argparse.Namespace, repo: Path) -> dict:
    """Validate operator inputs and build a record; perform no cloud operations."""
    fields = {
        "project": _required_text(args.project, "project"),
        "database": _required_text(args.database, "database"),
        "region": _required_text(args.region, "region"),
        "dataset": _required_text(args.dataset, "dataset"),
        "bucket": _required_text(args.bucket, "bucket"),
        "namespace": _required_text(args.namespace, "namespace"),
    }
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", fields["project"]):
        raise ValueError("project has invalid syntax")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}|\(default\)", fields["database"]):
        raise ValueError("database has invalid syntax")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", fields["dataset"]):
        raise ValueError("dataset has invalid syntax")
    if not re.fullmatch(r"[a-z]+-[a-z0-9]+[0-9]", fields["region"]):
        raise ValueError("region has invalid syntax")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,220}[a-z0-9]", fields["bucket"]):
        raise ValueError("bucket has invalid syntax")
    if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", fields["namespace"]):
        raise ValueError("namespace has invalid syntax")
    rollback = {
        "web_revision": _required_text(args.rollback_web, "web rollback target"),
        "api_revision": _required_text(args.rollback_api, "API rollback target"),
        "magi_image": _required_text(args.rollback_magi_image, "magi image rollback target"),
        "pipeline_image": _required_text(args.rollback_pipeline_image, "pipeline image rollback target"),
    }
    for name in ("web_revision", "api_revision"):
        if rollback[name] != "ABSENT" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@-]*", rollback[name]):
            raise ValueError(f"{name.replace('_', ' ')} has invalid syntax")
    for name in ("magi_image", "pipeline_image"):
        if rollback[name] != "ABSENT" and not re.search(r"@sha256:[0-9a-f]{64}$", rollback[name]):
            raise ValueError(f"{name.replace('_', ' ')} must be an immutable sha256 image digest or ABSENT")
    if not args.evidence_path:
        raise ValueError("At least one acceptance evidence path is required")
    evidence_paths = [str(_safe_path(value, "Evidence path")) for value in args.evidence_path]
    if len(set(evidence_paths)) != len(evidence_paths):
        raise ValueError("Acceptance evidence paths must be unique")
    return {
        "record_type": "hosted-rollout-preparation",
        "record_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "verification_status": "pending",
        "candidate": _git_state(repo),
        "target": fields,
        "rollback_targets": rollback,
        "acceptance_evidence_paths": evidence_paths,
        "notes": [
            "Record captures operator-supplied values; it does not verify cloud state or deployment.",
            "Phase 4 budget controls and reference-aware cleanup remain pending acceptance evidence.",
        ],
    }


def write_record(record: dict, output: str | Path) -> Path:
    """Create JSON exactly once. Existing files and symlinks are never replaced."""
    target = _safe_path(output, "Output path")
    if not target.parent.is_dir():
        raise ValueError("Output parent directory must already exist")
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    try:
        with target.open("x", encoding="utf-8") as stream:
            stream.write(payload)
    except FileExistsError as exc:
        raise ValueError(f"Output already exists: {target}") from exc
    except OSError as exc:
        raise ValueError(f"Could not create output file: {exc}") from exc
    return target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New JSON path; parent directory must exist")
    for name in ("project", "database", "region", "dataset", "bucket", "namespace"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--rollback-web", required=True, help="Captured prior web serving revision")
    parser.add_argument("--rollback-api", required=True, help="Captured prior API revision, or ABSENT if confirmed absent")
    parser.add_argument("--rollback-magi-image", required=True, help="Prior magi job image digest, or ABSENT if confirmed absent")
    parser.add_argument("--rollback-pipeline-image", required=True, help="Prior pipeline job image digest, or ABSENT if confirmed absent")
    parser.add_argument("--evidence-path", action="append", required=True, help="Acceptance evidence file path; repeat as needed")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    try:
        record = build_record(args, repo)
        target = write_record(record, args.output)
    except ValueError as exc:
        print(f"hosted-rollout-record: {exc}", file=sys.stderr)
        return 2
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
