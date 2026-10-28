"""Local immutable artifacts and disposable verification cache for shared audio."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path


def _file_checksum(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


class LocalSharedArtifacts:
    """Keep artifact bytes and file-identity verification local to one data root."""

    def __init__(self, root: Path):
        self.directory = Path(root) / "shared-artifacts"
        self.database = Path(root) / "shared-artifact-cache.sqlite3"
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS verified_artifacts (
                checksum TEXT PRIMARY KEY, device INTEGER NOT NULL, inode INTEGER NOT NULL,
                size INTEGER NOT NULL, modified_ns INTEGER NOT NULL, changed_ns INTEGER NOT NULL
            )""")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.database, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def store(self, source: Path):
        """Copy immutable content before recording any review or publication pointer."""
        directory = self.directory
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
                if _file_checksum(target) != checksum:
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

    def verified(self, checksum: str):
        """Cache verification only while the immutable file's identity stays unchanged."""
        if not re.fullmatch(r"[a-f0-9]{64}", checksum):
            raise ValueError("Invalid artifact checksum")
        path = self.directory / checksum
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError("Artifact is unavailable")
                identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                with self._connect() as db:
                    cached = db.execute(
                        "SELECT device, inode, size, modified_ns, changed_ns FROM verified_artifacts WHERE checksum = ?",
                        (checksum,),
                    ).fetchone()
                # Windows reports creation time as ctime on supported Python
                # versions, so it cannot prove that file contents are unchanged.
                if os.name != "nt" and cached and tuple(cached) == identity:
                    return path
                digest = hashlib.sha256()
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
                after = os.fstat(source.fileno())
                after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                if digest.hexdigest() != checksum or identity != after_identity:
                    raise ValueError("Artifact checksum mismatch")
                with self._connect() as db:
                    db.execute(
                        "INSERT INTO verified_artifacts VALUES (?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(checksum) DO UPDATE SET device = excluded.device, inode = excluded.inode, "
                        "size = excluded.size, modified_ns = excluded.modified_ns, changed_ns = excluded.changed_ns",
                        (checksum, *identity),
                    )
                return path
        except OSError:
            raise ValueError("Artifact is unavailable") from None

