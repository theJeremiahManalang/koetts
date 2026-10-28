"""Inspect shared-store activation without importing, deleting or rewriting user data."""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from manga_tts.shared_metadata import KEYS

from .paths import data_root


@dataclass(frozen=True)
class FirestoreSettings:
    project: str
    database: str
    dataset: str

    @classmethod
    def from_environment(cls):
        values = [os.environ.get(name, "") for name in
                  ("FIREBASE_PROJECT_ID", "FIRESTORE_DATABASE_ID", "MANGA_SHARED_DATASET")]
        if any(not value or value != value.strip() or "/" in value for value in values):
            raise ValueError("Explicit shared project, database and dataset required")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", values[2]):
            raise ValueError("Invalid shared dataset")
        return cls(*values)

    def client(self):
        from google.cloud import firestore

        return firestore.Client(project=self.project, database=self.database)


def sqlite_inventory(root: Path):
    path = root / "shared.sqlite3"
    if not path.exists():
        return {"exists": False, "counts": {}}
    if path.is_symlink():
        raise ValueError("Shared SQLite database must not be a symlink")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        unknown = tables - set(KEYS) - {"verified_artifacts"}
        if unknown:
            raise ValueError("Unexpected SQLite shared schema")
        counts = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in KEYS if table in tables}
        return {"exists": True, "counts": counts}


def local_identity(root: Path):
    path = root / ".shared-artifact-store-id"
    if not path.exists():
        return None
    if path.is_symlink():
        raise ValueError("Invalid artifact store identity")
    identity = path.read_text()
    if not re.fullmatch(r"[a-f0-9]{32}", identity):
        raise ValueError("Invalid artifact store identity")
    return identity


def read_binding(root: Path):
    path = root / ".shared-backend.json"
    if not path.exists():
        return None
    if path.is_symlink():
        raise ValueError("Invalid shared backend binding")
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or set(value) != {"project", "database", "dataset"}:
        raise ValueError("Invalid shared backend binding")
    return value


def target_inventory(client, settings: FirestoreSettings):
    reference = client.collection("shared_workflow_v1").document(settings.dataset)
    document = reference.get()
    state = document.to_dict() if document.exists else None
    counts = {}
    for collection in reference.collections():
        counts[collection.id] = collection.count().get()[0][0].value
    return {"exists": document.exists, "state": state, "counts": counts}


def inspect_cutover(root: Path, client, settings: FirestoreSettings, *, include_legacy=True):
    from .shared_firestore import SCHEMA_VERSION

    source = sqlite_inventory(root)
    target = target_inventory(client, settings)
    identity = local_identity(root)
    binding = read_binding(root)
    blockers = []
    if any(source["counts"].values()):
        blockers.append("SQLite contains workflow data; explicit preservation/reconciliation is required")
    if binding is not None and binding != asdict(settings):
        blockers.append("Local data root is bound to a different Firestore target")
    state = target["state"]
    if state is not None:
        if state.get("schema_version") != SCHEMA_VERSION:
            blockers.append("Target schema version is unsupported")
        if identity is None or state.get("artifact_store_id") != identity:
            blockers.append("Target belongs to a different or unavailable local artifact store")
    if any(target["counts"].values()) and state is None:
        blockers.append("Target contains orphan metadata without a dataset identity")
    if set(target["counts"]) - set(KEYS) - {"unique_keys"}:
        blockers.append("Target contains unexpected metadata collections")
    result = {"target": asdict(settings), "sqlite": source,
              "schema_version": state.get("schema_version") if state else None,
              "target_counts": target["counts"], "artifact_store_identity": identity,
              "target_exists": target["exists"], "binding": binding,
              "ready": not blockers, "blockers": blockers}
    if include_legacy:
        result["legacy_manga_requests"] = {
            "count": client.collection("manga_requests").count().get()[0][0].value,
            "action": "leave untouched; excluded from new workflow",
        }
    return result


def bind_firestore(root: Path, client, settings: FirestoreSettings):
    """Fail closed before activation; a binding prevents accidental SQLite fallback."""
    if any(sqlite_inventory(root)["counts"].values()):
        raise ValueError("SQLite contains workflow data; explicit reconciliation required")
    existing = read_binding(root)
    if existing == asdict(settings):
        return
    report = inspect_cutover(root, client, settings, include_legacy=False)
    if not report["ready"]:
        raise ValueError("Shared backend activation blocked; run cutover preflight")
    root.mkdir(parents=True, exist_ok=True)
    target = root / ".shared-backend.json"
    try:
        with target.open("x") as output:
            json.dump(asdict(settings), output, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError:
        if read_binding(root) != asdict(settings):
            raise ValueError("Shared backend binding changed") from None


def release_empty_binding(root: Path, client, settings: FirestoreSettings):
    """Explicit offline rollback before any remote metadata has been written."""
    if read_binding(root) != asdict(settings):
        raise ValueError("No matching backend binding")
    target = target_inventory(client, settings)
    if target["exists"] or any(target["counts"].values()):
        raise ValueError("Firestore has been initialized; reconciliation is required")
    (root / ".shared-backend.json").unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-empty-binding", action="store_true",
                        help="With the app stopped, remove only a local binding to a completely empty target")
    args = parser.parse_args()
    try:
        settings = FirestoreSettings.from_environment()
        root = data_root()
        client = settings.client()
        try:
            if args.release_empty_binding:
                release_empty_binding(root, client, settings)
            report = inspect_cutover(root, client, settings)
        finally:
            client.close()
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["ready"] else 1
    except Exception:
        print(json.dumps({"ready": False, "error": "Shared cutover inspection failed; check configuration, credentials and source integrity."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
