"""SQLite metadata transactions for the shared workflow; no artifact I/O."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeVar

T = TypeVar("T")
KEYS = {"chapter_work": "id", "reader_requests": "id", "work_approvals": "work_id",
        "work_projects": "work_id", "audio_reviews": "id", "export_candidates": "id",
        "review_candidates": "review_id", "publications": "work_id",
        "reader_daily_quotas": "id"}


class MetadataTransaction(Protocol):
    def get(self, table: str, key: str) -> dict | None: ...
    def find(self, table: str, **filters) -> list[dict]: ...
    def put(self, table: str, record: dict) -> None: ...
    def delete(self, table: str, key: str) -> None: ...


class SharedMetadata(Protocol):
    def run(self, operation: Callable[[MetadataTransaction], T]) -> T: ...


class SQLiteSharedMetadata:
    def __init__(self, database: Path):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as db:
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
                CREATE TABLE IF NOT EXISTS reader_daily_quotas (
                    id TEXT PRIMARY KEY, reader TEXT NOT NULL, utc_day TEXT NOT NULL,
                    count INTEGER NOT NULL CHECK(count >= 0), UNIQUE(reader, utc_day)
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
                CREATE TABLE IF NOT EXISTS export_candidates (
                    id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES chapter_work(id),
                    link_id TEXT NOT NULL, project_id TEXT NOT NULL, actor TEXT NOT NULL,
                    revision TEXT NOT NULL, export_id TEXT NOT NULL, settings_hash TEXT NOT NULL,
                    checksums TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS review_candidates (
                    review_id TEXT PRIMARY KEY REFERENCES audio_reviews(id),
                    candidate_id TEXT NOT NULL REFERENCES export_candidates(id)
                );
                CREATE TABLE IF NOT EXISTS publications (
                    work_id TEXT PRIMARY KEY REFERENCES chapter_work(id),
                    id TEXT NOT NULL UNIQUE, review_id TEXT NOT NULL REFERENCES audio_reviews(id),
                    actor TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS verified_artifacts (
                    checksum TEXT PRIMARY KEY, device INTEGER NOT NULL, inode INTEGER NOT NULL,
                    size INTEGER NOT NULL, modified_ns INTEGER NOT NULL, changed_ns INTEGER NOT NULL
                );
            """)

    def run(self, operation):
        db = sqlite3.connect(self.database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                return operation(_SQLiteTransaction(db))
        finally:
            db.close()


class _SQLiteTransaction:
    def __init__(self, db):
        self.db = db

    def get(self, table, key):
        rows = self.find(table, **{KEYS[table]: key})
        return rows[0] if rows else None

    def find(self, table, **filters):
        if table not in KEYS:
            raise ValueError("Unknown metadata table")
        columns = {row[1] for row in self.db.execute(f"PRAGMA table_info({table})")}
        if not filters.keys() <= columns:
            raise ValueError("Unknown metadata field")
        where = " AND ".join(f"{key} = ?" for key in filters) or "1"
        rows = self.db.execute(f"SELECT rowid AS sequence, * FROM {table} WHERE {where}", tuple(filters.values()))
        result = []
        for row in rows:
            record = dict(row)
            if "checksums" in record:
                record["checksums"] = json.loads(record["checksums"])
            result.append(record)
        return result

    def put(self, table, record):
        key = KEYS[table]
        record = {name: value for name, value in record.items() if name != "sequence"}
        columns = {row[1] for row in self.db.execute(f"PRAGMA table_info({table})")}
        if not record.keys() <= columns:
            raise ValueError("Unknown metadata field")
        values = [json.dumps(value, sort_keys=True) if name == "checksums" else value for name, value in record.items()]
        fields = ", ".join(record)
        updates = ", ".join(f"{name}=excluded.{name}" for name in record if name != key)
        self.db.execute(f"INSERT INTO {table} ({fields}) VALUES ({', '.join('?' for _ in record)}) "
                        f"ON CONFLICT({key}) DO UPDATE SET {updates}", values)

    def delete(self, table, key):
        if table == "reader_daily_quotas":
            raise ValueError("Reader daily quota records cannot be deleted")
        self.db.execute(f"DELETE FROM {table} WHERE {KEYS[table]} = ?", (key,))
