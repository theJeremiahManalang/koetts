"""Local transactional store for shared chapter requests.

SQLite coordinates one host. Cloud persistence is a separate adapter.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path


class SharedRequests:
    """Store reader requests and their shared chapter work."""

    def __init__(self, database: Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS chapter_work (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    title_key TEXT NOT NULL, chapter INTEGER NOT NULL,
                    configuration TEXT NOT NULL, status TEXT NOT NULL,
                    UNIQUE(title_key, chapter, configuration)
                );
                CREATE TABLE IF NOT EXISTS reader_requests (
                    id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES chapter_work(id),
                    reader TEXT NOT NULL, notes TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(work_id, reader)
                );
                CREATE TABLE IF NOT EXISTS work_approvals (
                    work_id TEXT PRIMARY KEY REFERENCES chapter_work(id),
                    actor TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS work_projects (
                    work_id TEXT PRIMARY KEY REFERENCES chapter_work(id),
                    id TEXT NOT NULL UNIQUE, project_id TEXT NOT NULL UNIQUE,
                    actor TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS audio_reviews (
                    id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES chapter_work(id),
                    link_id TEXT NOT NULL, project_id TEXT NOT NULL, actor TEXT NOT NULL,
                    revision TEXT NOT NULL, export_id TEXT NOT NULL, settings_hash TEXT NOT NULL,
                    checksums TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def submit(self, reader: str, title: str, chapter: str, notes: str):
        title = " ".join(title.split())
        if not reader or not title or len(title) > 200 or len(notes) > 4000:
            raise ValueError("Invalid request")
        if not chapter.isascii() or not chapter.isdigit() or not 1 <= int(chapter) <= 9999:
            raise ValueError("Invalid chapter")
        with self._connect() as db:
            db.execute(
                "INSERT INTO chapter_work VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(title_key, chapter, configuration) DO NOTHING",
                (uuid.uuid4().hex, title, title.casefold(), int(chapter), "default", "pending"),
            )
            work_id = db.execute(
                "SELECT id FROM chapter_work WHERE title_key = ? AND chapter = ? AND configuration = ?",
                (title.casefold(), int(chapter), "default"),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO reader_requests(id, work_id, reader, notes) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(work_id, reader) DO NOTHING",
                (uuid.uuid4().hex, work_id, reader, notes),
            )
            return dict(db.execute(
                "SELECT r.id, r.work_id, r.notes, r.created_at, w.title, w.chapter, w.status "
                "FROM reader_requests r JOIN chapter_work w ON r.work_id = w.id "
                "WHERE r.work_id = ? AND r.reader = ?", (work_id, reader),
            ).fetchone())

    def list_reader(self, reader: str):
        with self._connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT r.id, r.work_id, r.notes, r.created_at, w.title, w.chapter, w.status "
                "FROM reader_requests r JOIN chapter_work w ON r.work_id = w.id "
                "WHERE r.reader = ? ORDER BY r.created_at, r.id", (reader,),
            )]

    def list_work(self):
        with self._connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT w.id, w.title, w.chapter, w.status, a.actor AS approved_by "
                "FROM chapter_work w LEFT JOIN work_approvals a ON a.work_id = w.id "
                "ORDER BY w.title_key, w.chapter"
            )]

    def work_requests(self, work_id: str):
        """List individual requests for an authorized administrator."""
        with self._connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id, reader, notes, created_at FROM reader_requests "
                "WHERE work_id = ? ORDER BY created_at, id", (work_id,),
            )]

    def get_link(self, work_id: str):
        with self._connect() as db:
            row = db.execute(
                "SELECT id, work_id, project_id, actor, created_at FROM work_projects WHERE work_id = ?",
                (work_id,),
            ).fetchone()
            return dict(row) if row else None

    def link_project(self, work_id: str, project_id: str, actor: str):
        """Attach an existing project; the caller verifies the project and actor."""
        if not project_id or not actor:
            raise ValueError("Project and actor required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            work = db.execute("SELECT status FROM chapter_work WHERE id = ?", (work_id,)).fetchone()
            if not work or work["status"] not in ("approved", "published"):
                raise ValueError("Approved work required")
            previous = db.execute("SELECT * FROM work_projects WHERE work_id = ?", (work_id,)).fetchone()
            if previous and previous["project_id"] == project_id:
                return dict(previous)
            if db.execute("SELECT 1 FROM work_projects WHERE project_id = ?", (project_id,)).fetchone():
                raise ValueError("Project already linked")
            db.execute(
                "INSERT INTO work_projects(work_id, id, project_id, actor) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(work_id) DO UPDATE SET id = excluded.id, project_id = excluded.project_id, "
                "actor = excluded.actor, created_at = CURRENT_TIMESTAMP",
                (work_id, uuid.uuid4().hex, project_id, actor),
            )
            return dict(db.execute("SELECT * FROM work_projects WHERE work_id = ?", (work_id,)).fetchone())

    def _store_artifact(self, source: Path):
        """Copy immutable content before recording any review or publication pointer."""
        directory = self.database.parent / "shared-artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            digest = hashlib.sha256()
            with source.open("rb") as incoming, tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
                temporary = Path(output.name)
                while chunk := incoming.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            checksum = digest.hexdigest()
            target = directory / checksum
            try:
                os.link(temporary, target)
            except FileExistsError:
                if self._checksum(target) != checksum:
                    raise ValueError("Stored artifact checksum mismatch") from None
            if hasattr(os, "O_DIRECTORY"):
                directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            return checksum
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def _checksum(path: Path):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def record_audio_review(self, work_id, link, actor, revision, export_id, settings_hash, artifacts):
        """Persist an explicit decision using a trusted, locked studio snapshot."""
        if not actor or not revision or not export_id or not settings_hash or not artifacts:
            raise ValueError("Incomplete audio review")
        checksums = {name: self._store_artifact(path) for name, path in artifacts.items()}
        review_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT * FROM work_projects WHERE work_id = ?", (work_id,)).fetchone()
            if not current or current["id"] != link["id"] or current["project_id"] != link["project_id"]:
                raise ValueError("Project link changed during review")
            db.execute(
                "INSERT INTO audio_reviews(id, work_id, link_id, project_id, actor, revision, export_id, settings_hash, checksums) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (review_id, work_id, link["id"], link["project_id"], actor, revision, export_id,
                 settings_hash, json.dumps(checksums, sort_keys=True)),
            )
        return {"id": review_id, "work_id": work_id, "link_id": link["id"], "project_id": link["project_id"],
                "actor": actor, "revision": revision, "export_id": export_id, "settings_hash": settings_hash,
                "checksums": checksums}

    def approve(self, work_id: str, actor: str):
        if not actor:
            raise ValueError("Approval actor required")
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE chapter_work SET status = 'approved' WHERE id = ? AND status = 'pending'",
                (work_id,),
            )
            if cursor.rowcount != 1:
                raise ValueError("Pending work not found")
            db.execute("INSERT INTO work_approvals(work_id, actor) VALUES (?, ?)", (work_id, actor))

    def delete(self, reader: str, request_id: str):
        with self._connect() as db:
            cursor = db.execute(
                "DELETE FROM reader_requests WHERE id = ? AND reader = ?", (request_id, reader),
            )
            if cursor.rowcount != 1:
                raise ValueError("Request not found")

