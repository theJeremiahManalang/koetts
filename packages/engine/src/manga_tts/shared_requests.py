"""Local transactional store for shared chapter requests.

SQLite coordinates one host. Cloud persistence is a separate adapter.
"""

from __future__ import annotations

import sqlite3
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

