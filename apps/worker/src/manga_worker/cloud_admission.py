"""Transactional monthly admission limits for hosted chapter production."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Callable

from manga_tts.operations import OperationConflict

from .cloud_revisions import SCHEMA_VERSION, _FirestoreHostedStore


_CHAPTER_ID = re.compile(r"[a-f0-9]{32}\Z")
_MAX_OPERATION_KEY_BYTES = 512
_MAX_CHAPTERS_PER_MONTH = 5
_MAX_PAGES_PER_CHAPTER = 40


class ProductionLimitExceeded(OperationConflict):
    """A hosted production admission exceeded a fixed pilot limit."""


class CloudChapterAdmission(_FirestoreHostedStore):
    """Reserve one server-identified chapter against the monthly hosted cap.

    Admission keys are globally idempotent. A reservation is retained even if
    later production fails; starting a distinct chapter consumes the allowance.
    """

    def __init__(self, client, dataset: str, artifact_store_id: str, *, clock: Callable | None = None):
        super().__init__(client, dataset, artifact_store_id)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @staticmethod
    def _month(now: datetime) -> str:
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Admission clock must return an aware datetime")
        return now.astimezone(timezone.utc).strftime("%Y-%m")

    @staticmethod
    def _validate_inputs(chapter_identity: str, operation_key: str, page_count: int) -> str:
        if not isinstance(chapter_identity, str) or not _CHAPTER_ID.fullmatch(chapter_identity):
            raise ValueError("Invalid hosted chapter identity")
        if (not isinstance(operation_key, str) or not operation_key
                or len(operation_key.encode("utf-8")) > _MAX_OPERATION_KEY_BYTES):
            raise ValueError("Invalid production operation key")
        if any(ord(character) < 32 or ord(character) == 127 for character in operation_key):
            raise ValueError("Invalid production operation key")
        if (not isinstance(page_count, int) or isinstance(page_count, bool)
                or not 1 <= page_count <= _MAX_PAGES_PER_CHAPTER):
            raise ValueError("Hosted chapter must contain between 1 and 40 pages")
        return hashlib.sha256(operation_key.encode("utf-8")).hexdigest()

    def prepare(self, chapter_identity: str, operation_key: str, page_count: int):
        """Validate and freeze month before a caller enters a retryable transaction."""
        key_hash = self._validate_inputs(chapter_identity, operation_key, page_count)
        month = self._month(self.clock())

        def reserve_in_transaction(transaction):
            self.reserve_in_transaction(
                transaction, chapter_identity, operation_key, page_count, month=month,
                _key_hash=key_hash,
            )

        return reserve_in_transaction

    @property
    def _months(self):
        return self.root.collection("production_months")

    @property
    def _admissions(self):
        return self.root.collection("production_admissions")

    @staticmethod
    def _month_chapters(snapshot, month: str) -> list[str]:
        if not snapshot.exists:
            return []
        value = snapshot.to_dict()
        chapters = value.get("chapter_ids") if isinstance(value, dict) else None
        if (not isinstance(value, dict)
                or set(value) != {"schema_version", "month", "chapter_ids"}
                or value.get("schema_version") != SCHEMA_VERSION
                or isinstance(value.get("schema_version"), bool)
                or value.get("month") != month
                or not isinstance(chapters, list)
                or len(chapters) > _MAX_CHAPTERS_PER_MONTH
                or any(not isinstance(chapter, str) or not _CHAPTER_ID.fullmatch(chapter)
                       for chapter in chapters)
                or len(chapters) != len(set(chapters))):
            raise ValueError("Corrupt hosted production month ledger")
        return chapters

    @staticmethod
    def _admission_record(snapshot, operation_key: str) -> dict | None:
        if not snapshot.exists:
            return None
        value = snapshot.to_dict()
        expected = {"schema_version", "operation_key", "month", "chapter_identity", "page_count"}
        if (not isinstance(value, dict) or set(value) != expected
                or value.get("schema_version") != SCHEMA_VERSION
                or isinstance(value.get("schema_version"), bool)
                or value.get("operation_key") != operation_key
                or not isinstance(value.get("month"), str)
                or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value["month"])
                or not isinstance(value.get("chapter_identity"), str)
                or not _CHAPTER_ID.fullmatch(value["chapter_identity"])
                or not isinstance(value.get("page_count"), int)
                or isinstance(value.get("page_count"), bool)
                or not 1 <= value["page_count"] <= _MAX_PAGES_PER_CHAPTER):
            raise ValueError("Corrupt hosted production admission")
        return value

    def reserve_in_transaction(
        self, transaction, chapter_identity: str, operation_key: str, page_count: int,
        *, month: str | None = None, _key_hash: str | None = None,
    ) -> None:
        """Stage a reservation in a caller-owned Firestore transaction.

        ``prepare`` is the retry-safe entry point for transaction callbacks; its
        closure supplies the UTC month captured before Firestore can retry.
        """
        key_hash = self._validate_inputs(chapter_identity, operation_key, page_count)
        if _key_hash is not None and _key_hash != key_hash:
            raise ValueError("Invalid production operation key hash")
        month = month or self._month(self.clock())
        if not isinstance(month, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
            raise ValueError("Invalid production admission month")
        month_ref = self._months.document(month)
        admission_ref = self._admissions.document(key_hash)
        binding_exists = self._binding(transaction)
        if not binding_exists:
            for collection in ("production_months", "production_admissions"):
                if list(self.root.collection(collection).limit(1).stream(transaction=transaction)):
                    raise ValueError("Hosted dataset has orphaned production records without a namespace binding")

        admission_snapshot = admission_ref.get(transaction=transaction)
        month_snapshot = month_ref.get(transaction=transaction)
        # All transaction reads complete before any write is staged.
        prior = self._admission_record(admission_snapshot, operation_key)
        chapters = self._month_chapters(month_snapshot, month)
        if prior is not None:
            if (prior["chapter_identity"] != chapter_identity
                    or prior["page_count"] != page_count):
                raise OperationConflict(
                    "idempotency_conflict",
                    "This production key already belongs to a different chapter admission.",
                )
            return

        if chapter_identity not in chapters:
            if len(chapters) >= _MAX_CHAPTERS_PER_MONTH:
                raise ProductionLimitExceeded(
                    "production_limit",
                    "The hosted monthly chapter production limit has been reached.",
                )
            chapters = sorted((*chapters, chapter_identity))

        transaction.set(month_ref, {
            "schema_version": SCHEMA_VERSION,
            "month": month,
            "chapter_ids": chapters,
        })
        transaction.create(admission_ref, {
            "schema_version": SCHEMA_VERSION,
            "operation_key": operation_key,
            "month": month,
            "chapter_identity": chapter_identity,
            "page_count": page_count,
        })

    def reserve(self, chapter_identity: str, operation_key: str, page_count: int) -> None:
        """Atomically reserve chapter capacity; duplicate matching calls are no-ops."""
        callback = self.prepare(chapter_identity, operation_key, page_count)

        def operation(transaction):
            binding_exists = self._binding(transaction)
            callback(transaction)
            return None, binding_exists

        self._run(operation, bind_if_missing=True)
