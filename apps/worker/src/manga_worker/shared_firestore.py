"""Firestore metadata adapter for a single local shared-workflow dataset.

Only metadata is remote. The dataset is bound to one local artifact store; this
adapter does not make workspace locks or artifact bytes distributed.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from manga_tts.shared_metadata import KEYS

SCHEMA_VERSION = 1
UNIQUE_FIELDS = {
    "chapter_work": ("title_key", "chapter", "configuration"),
    "reader_requests": ("work_id", "reader"),
    "work_projects": ("project_id",),
}


def _unique_key(table, fields, record):
    value = [table, [[field, record[field]] for field in fields]]
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


class FirestoreSharedMetadata:
    """Buffer metadata writes until all transactional reads have completed."""

    def __init__(self, client, dataset: str, artifact_store_id: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", dataset):
            raise ValueError("Invalid shared dataset")
        if not re.fullmatch(r"[a-f0-9]{32}|gcs-v1:[a-f0-9]{64}", artifact_store_id):
            raise ValueError("Invalid artifact store identity")
        self.client = client
        self.root = client.collection("shared_workflow_v1").document(dataset)
        self.artifact_store_id = artifact_store_id

    def run(self, operation):
        from google.cloud import firestore

        @firestore.transactional
        def execute(transaction):
            root = self.root.get(transaction=transaction)
            state = root.to_dict() if root.exists else {
                "schema_version": SCHEMA_VERSION, "artifact_store_id": self.artifact_store_id, "sequence": 0,
            }
            if state.get("schema_version") != SCHEMA_VERSION or state.get("artifact_store_id") != self.artifact_store_id:
                raise ValueError("Shared dataset belongs to a different schema or artifact store")
            unit = _FirestoreTransaction(self.root, transaction, state)
            result = operation(unit)
            if unit.pending:
                unit.flush()
                transaction.set(self.root, state)
            return result
        return execute(self.client.transaction())


class _FirestoreTransaction:
    def __init__(self, root, transaction, state):
        self.root = root
        self.transaction = transaction
        self.state = state
        self.pending = {}
        self.loaded = {}

    def _ref(self, table, key):
        if table not in KEYS and table != "unique_keys":
            raise ValueError("Unknown metadata collection")
        if not isinstance(key, str) or not key or "/" in key:
            raise ValueError("Invalid metadata identity")
        return self.root.collection(table).document(key)

    def get(self, table, key):
        identity = (table, key)
        if identity in self.pending:
            value = self.pending[identity]
        else:
            if identity not in self.loaded:
                document = self._ref(table, key).get(transaction=self.transaction)
                self.loaded[identity] = document.to_dict() if document.exists else None
            value = self.loaded[identity]
        return dict(value) if value is not None else None

    def find(self, table, **filters):
        self._ref(table, "validate")
        fields = UNIQUE_FIELDS.get(table)
        if fields and set(filters) == set(fields):
            index = self.get("unique_keys", _unique_key(table, fields, filters))
            record = self.get(table, index["key"]) if index else None
            if record and any(record.get(field) != value for field, value in filters.items()):
                raise ValueError("Shared uniqueness index is inconsistent")
            return [record] if record else []
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self.root.collection(table)
        for field, value in filters.items():
            query = query.where(filter=FieldFilter(field, "==", value))
        records = {doc.id: doc.to_dict() for doc in query.stream(transaction=self.transaction)}
        for (pending_table, key), value in self.pending.items():
            if pending_table == table:
                if value is None:
                    records.pop(key, None)
                else:
                    records[key] = value
        return [dict(record) for record in records.values() if all(record.get(field) == value for field, value in filters.items())]

    def put(self, table, record):
        key = record[KEYS[table]]
        previous = self.get(table, key)
        record = dict(record)
        fields = UNIQUE_FIELDS.get(table)
        if fields:
            index_key = _unique_key(table, fields, record)
            index = self.get("unique_keys", index_key)
            if index and index["key"] != key:
                raise ValueError("Shared uniqueness conflict")
            if previous:
                old_key = _unique_key(table, fields, previous)
                if old_key != index_key:
                    self.pending[("unique_keys", old_key)] = None
            self.pending[("unique_keys", index_key)] = {"key": key}
        if table in {"export_candidates", "audio_reviews"} and not previous:
            self.state["sequence"] += 1
            record["sequence"] = self.state["sequence"]
        self.pending[(table, key)] = record

    def delete(self, table, key):
        previous = self.get(table, key)
        if previous and table in UNIQUE_FIELDS:
            self.pending[("unique_keys", _unique_key(table, UNIQUE_FIELDS[table], previous))] = None
        self.pending[(table, key)] = None

    def flush(self):
        for (table, key), record in self.pending.items():
            reference = self._ref(table, key)
            if record is None:
                self.transaction.delete(reference)
            else:
                self.transaction.set(reference, record)


def artifact_store_identity(root: Path) -> str:
    """Persist one identity atomically across local application processes."""
    import uuid

    from .shared_local import persist_once

    target = root / ".shared-artifact-store-id"
    persist_once(target, uuid.uuid4().hex)
    if target.is_symlink():
        raise ValueError("Invalid artifact store identity file")
    value = target.read_text()
    if not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Invalid artifact store identity file")
    return value
