"""Crash-safe local identities used before binding remote shared metadata."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile


def persist_once(target: Path, contents: str) -> None:
    """Publish a complete file without replacing another process's binding."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            pass
        sync_parent(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def sync_parent(target: Path) -> None:
    """Persist a local identity's directory entry on supported filesystems."""
    if hasattr(os, "O_DIRECTORY"):
        descriptor = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
