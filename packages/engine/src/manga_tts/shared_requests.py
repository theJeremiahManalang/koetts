"""Local transactional store for shared chapter requests.

SQLite coordinates one host. Cloud persistence is a separate adapter.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

from .shared_artifacts import LocalSharedArtifacts


def _manga_id(title_key: str) -> str:
    return hashlib.sha256(title_key.encode("utf-8")).hexdigest()[:32]


def _file_checksum(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


@dataclass(frozen=True, kw_only=True)
class ExportSnapshot:
    """Export identity and files derived by the worker under its workspace lock.

    This groups trusted application inputs; constructing it grants no authority.
    Callers retain the workspace lock through the associated store mutation.
    """

    work_id: str
    link_id: str
    project_id: str
    revision: str
    export_id: str
    settings_hash: str
    artifacts: Mapping[str, Path]

    def __post_init__(self):
        object.__setattr__(self, "artifacts", MappingProxyType(dict(self.artifacts)))

    def checksums(self) -> dict[str, str]:
        return {name: _file_checksum(path) for name, path in self.artifacts.items()}


@dataclass(frozen=True, kw_only=True)
class ReaderIntakePolicy:
    """Optional hosted limits for newly created reader requests."""

    max_pending: int = 5
    max_new_per_utc_day: int = 10

    def __post_init__(self):
        if self.max_pending < 1 or self.max_new_per_utc_day < 1:
            raise ValueError("Reader intake limits must be positive")


class IntakeQuotaExceeded(ValueError):
    """A reader request exceeded an enabled intake quota."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class SharedRequests:
    """Shared workflow decisions independent of metadata storage and artifact transport."""

    def __init__(self, database: Path, *, metadata=None, artifacts=None, intake_policy=None, clock=None):
        from .shared_metadata import SQLiteSharedMetadata

        self.database = Path(database)
        self.artifacts = artifacts if artifacts is not None else LocalSharedArtifacts(self.database.parent)
        self.metadata = metadata if metadata is not None else SQLiteSharedMetadata(self.database)
        self.intake_policy = intake_policy
        self.clock = clock if clock is not None else _now

    def submit(self, reader: str, title: str, chapter: str, notes: str):
        title = " ".join(title.split())
        if not reader or not title or len(title) > 200 or len(notes) > 4000:
            raise ValueError("Invalid request")
        if not chapter.isascii() or not chapter.isdigit() or not 1 <= int(chapter) <= 9999:
            raise ValueError("Invalid chapter")
        work = dict(id=uuid.uuid4().hex, title=title, title_key=title.casefold(), chapter=int(chapter),
                    configuration="default", status="pending")
        created_at = _timestamp(self.clock())
        request = dict(id=uuid.uuid4().hex, reader=reader, notes=notes, created_at=created_at)

        def submit(tx):
            existing = tx.find("chapter_work", title_key=work["title_key"], chapter=work["chapter"], configuration="default")
            current = existing[0] if existing else work
            prior = tx.find("reader_requests", work_id=current["id"], reader=reader)
            record = prior[0] if prior else {**request, "work_id": current["id"]}
            if not prior and self.intake_policy is not None:
                self._check_intake_quota(tx, reader, created_at,
                                         adds_pending=current["status"] == "pending")
            if not existing:
                tx.put("chapter_work", work)
            if not prior:
                tx.put("reader_requests", record)
                if self.intake_policy is not None:
                    self._record_daily_request(tx, reader, created_at)
            return {**_fields(record, "id", "work_id", "notes", "created_at"),
                    **_fields(current, "title", "chapter", "status"), "duplicate": bool(prior)}
        return self.metadata.run(submit)

    def _check_intake_quota(self, tx, reader, created_at, *, adds_pending):
        policy = self.intake_policy
        if adds_pending:
            pending = 0
            for request in tx.find("reader_requests", reader=reader):
                work = tx.get("chapter_work", request["work_id"])
                if work and work["status"] == "pending":
                    pending += 1
            if pending >= policy.max_pending:
                raise IntakeQuotaExceeded("pending_limit", "Too many pending reader requests")
        utc_day = _utc_day(created_at)
        daily = tx.get("reader_daily_quotas", _quota_id(reader, utc_day))
        if daily and daily["count"] >= policy.max_new_per_utc_day:
            raise IntakeQuotaExceeded("daily_limit", "Daily reader request limit reached")

    @staticmethod
    def _record_daily_request(tx, reader, created_at):
        utc_day = _utc_day(created_at)
        identity = _quota_id(reader, utc_day)
        daily = tx.get("reader_daily_quotas", identity)
        tx.put("reader_daily_quotas", {"id": identity, "reader": reader,
                                      "utc_day": utc_day, "count": (daily["count"] if daily else 0) + 1})

    def list_reader(self, reader):
        def read(tx):
            requests = tx.find("reader_requests", reader=reader)
            result = []
            for request in sorted(requests, key=lambda r: (r["created_at"], r["id"])):
                work = tx.get("chapter_work", request["work_id"])
                result.append({**_fields(request, "id", "work_id", "notes", "created_at"),
                               **_fields(work, "title", "chapter", "status"), "manga_id": _manga_id(work["title_key"])})
            return result
        return self.metadata.run(read)

    def list_work(self):
        def read(tx):
            result = []
            for work in sorted(tx.find("chapter_work"), key=lambda r: (r["title_key"], r["chapter"])):
                approval = tx.get("work_approvals", work["id"])
                result.append({**_fields(work, "id", "title", "chapter", "status"),
                               "approved_by": approval["actor"] if approval else None})
            return result
        return self.metadata.run(read)

    def work_requests(self, work_id):
        return self.metadata.run(lambda tx: [_fields(r, "id", "reader", "notes", "created_at") for r in
                                sorted(tx.find("reader_requests", work_id=work_id), key=lambda r: (r["created_at"], r["id"]))])

    def get_link(self, work_id):
        return self.metadata.run(lambda tx: _without_sequence(tx.get("work_projects", work_id)))

    def link_project(self, work_id, project_id, actor):
        if not project_id or not actor:
            raise ValueError("Project and actor required")
        link = dict(work_id=work_id, id=uuid.uuid4().hex, project_id=project_id, actor=actor, created_at=_now())

        def commit(tx):
            work = tx.get("chapter_work", work_id)
            previous = tx.get("work_projects", work_id)
            used = tx.find("work_projects", project_id=project_id)
            if not work or work["status"] not in ("approved", "published"):
                raise ValueError("Approved work required")
            if previous and previous["project_id"] == project_id:
                return _without_sequence(previous)
            if used:
                raise ValueError("Project already linked")
            tx.put("work_projects", link)
            return link
        return self.metadata.run(commit)

    def prepare_audio_review(self, snapshot: ExportSnapshot, *, actor: str):
        if not actor or not snapshot.revision or not snapshot.export_id or not snapshot.settings_hash or not snapshot.artifacts:
            raise ValueError("Incomplete audio review")
        checksums = {name: self.artifacts.store(path) for name, path in snapshot.artifacts.items()}
        record = _export_record(snapshot, actor, checksums)

        def commit(tx):
            link = tx.get("work_projects", snapshot.work_id)
            if not _same_link(link, snapshot):
                raise ValueError("Project link changed during review")
            tx.put("export_candidates", record)
            return _without_created(record)
        return self.metadata.run(commit)

    def candidate_artifact(self, candidate_id, name):
        record = self.metadata.run(lambda tx: tx.get("export_candidates", candidate_id))
        if not record or name not in record["checksums"]:
            raise ValueError("Candidate artifact not found")
        return self.artifacts.verified(record["checksums"][name])

    def review_state(self, work_id):
        def read(tx):
            link = tx.get("work_projects", work_id)
            candidates = tx.find("export_candidates", work_id=work_id)
            reviews = tx.find("audio_reviews", work_id=work_id)
            candidates = [r for r in candidates if link and r["link_id"] == link["id"]]
            reviews = [r for r in reviews if link and r["link_id"] == link["id"]]
            if not candidates:
                return {"candidate": None, "review": None}
            candidate = max(candidates, key=lambda r: r["sequence"])
            review = max(reviews, key=lambda r: r["sequence"]) if reviews else None
            relation = tx.get("review_candidates", review["id"]) if review else None
            return {"candidate": _fields(candidate, "id", "revision", "export_id"),
                    "review": {**_fields(review, "id", "revision", "export_id"), "candidate_id": relation["candidate_id"]}
                    if review and relation else None}
        return self.metadata.run(read)

    def approve_audio_review(self, snapshot: ExportSnapshot, *, candidate_id: str, actor: str):
        if not actor:
            raise ValueError("Audio review actor required")
        checksums = snapshot.checksums()
        self._verify_checksums(checksums)
        record = _export_record(snapshot, actor, checksums)

        def commit(tx):
            link = tx.get("work_projects", snapshot.work_id)
            candidate = tx.get("export_candidates", candidate_id)
            if not _matches(candidate, link, snapshot, checksums):
                raise ValueError("Export no longer matches prepared audio")
            tx.put("audio_reviews", record)
            tx.put("review_candidates", {"review_id": record["id"], "candidate_id": candidate_id})
            return {**_without_created(record), "candidate_id": candidate_id}
        return self.metadata.run(commit)

    def publication(self, work_id):
        def read(tx):
            publication = tx.get("publications", work_id)
            if not publication:
                return None
            review = tx.get("audio_reviews", publication["review_id"])
            return {**_without_sequence(publication), "checksums": review["checksums"]}
        return self.metadata.run(read)

    def catalog(self):
        def read(tx):
            result = []
            for publication in tx.find("publications"):
                work = tx.get("chapter_work", publication["work_id"])
                result.append({"work_id": work["id"], "title": work["title"], "chapter": work["chapter"],
                               "manga_id": _manga_id(work["title_key"]), "publication_id": publication["id"],
                               "_sort": (work["title_key"], work["chapter"])})
            return [{k: v for k, v in row.items() if k != "_sort"} for row in sorted(result, key=lambda r: r["_sort"])]
        return self.metadata.run(read)

    def publish_review(self, snapshot: ExportSnapshot, *, review_id: str, actor: str, expected_publication: str | None):
        if not actor:
            raise ValueError("Publication actor required")
        checksums = snapshot.checksums()
        self._verify_checksums(checksums)
        record = dict(id=uuid.uuid4().hex, work_id=snapshot.work_id, review_id=review_id, actor=actor, created_at=_now())

        def commit(tx):
            link = tx.get("work_projects", snapshot.work_id)
            review = tx.get("audio_reviews", review_id)
            prior = tx.get("publications", snapshot.work_id)
            work = tx.get("chapter_work", snapshot.work_id)
            if not _matches(review, link, snapshot, checksums):
                raise ValueError("Export no longer matches audio review")
            if prior and prior["review_id"] == review_id:
                return _fields(prior, "id", "work_id", "review_id")
            if (prior["id"] if prior else None) != expected_publication:
                raise ValueError("Publication changed; reload before publishing")
            tx.put("publications", record)
            tx.put("chapter_work", {**work, "status": "published"})
            return _fields(record, "id", "work_id", "review_id")
        return self.metadata.run(commit)

    def _verify_checksums(self, checksums):
        for checksum in checksums.values():
            self.artifacts.verified(checksum)

    def published_artifact(self, work_id, name, expected_publication=None):
        publication = self.publication(work_id)
        if (not publication or name not in publication["checksums"]
                or (expected_publication is not None and publication["id"] != expected_publication)):
            raise ValueError("Published artifact not found")
        return self.artifacts.verified(publication["checksums"][name])

    def approve(self, work_id, actor):
        if not actor:
            raise ValueError("Approval actor required")
        record = dict(work_id=work_id, actor=actor, created_at=_now())

        def commit(tx):
            work = tx.get("chapter_work", work_id)
            if not work or work["status"] != "pending":
                raise ValueError("Pending work not found")
            tx.put("chapter_work", {**work, "status": "approved"})
            tx.put("work_approvals", record)
        return self.metadata.run(commit)

    def delete(self, reader, request_id):
        def commit(tx):
            record = tx.get("reader_requests", request_id)
            if not record or record["reader"] != reader:
                raise ValueError("Request not found")
            tx.delete("reader_requests", request_id)
        return self.metadata.run(commit)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _timestamp(value):
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        timestamp = datetime.fromisoformat(value)
    else:
        raise ValueError("Clock must return a datetime or ISO timestamp")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Clock timestamp must include a timezone")
    return timestamp.astimezone(timezone.utc).isoformat()


def _utc_day(timestamp):
    return datetime.fromisoformat(timestamp).astimezone(timezone.utc).date().isoformat()


def _quota_id(reader, utc_day):
    identity = json.dumps([reader, utc_day], ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _fields(record, *keys):
    return {key: record[key] for key in keys}


def _without_sequence(record):
    return {k: v for k, v in record.items() if k != "sequence"} if record is not None else None


def _without_created(record):
    return {k: v for k, v in record.items() if k != "created_at"}


def _export_record(snapshot, actor, checksums):
    return dict(id=uuid.uuid4().hex, work_id=snapshot.work_id, link_id=snapshot.link_id,
                project_id=snapshot.project_id, actor=actor, revision=snapshot.revision,
                export_id=snapshot.export_id, settings_hash=snapshot.settings_hash, checksums=checksums, created_at=_now())


def _same_link(link, snapshot):
    return bool(link and link["id"] == snapshot.link_id and link["project_id"] == snapshot.project_id)


def _matches(record, link, snapshot, checksums):
    return bool(_same_link(link, snapshot) and record and record["work_id"] == snapshot.work_id
                and record["link_id"] == snapshot.link_id and record["project_id"] == snapshot.project_id
                and (record["revision"], record["export_id"], record["settings_hash"]) ==
                (snapshot.revision, snapshot.export_id, snapshot.settings_hash) and record["checksums"] == checksums)
