"""Explicit local data location, independent of the caller's working directory."""
import os
from pathlib import Path


def repository_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "uv.lock").is_file() and (parent / "package.json").is_file():
            return parent
    return None


def data_root() -> Path:
    configured = os.environ.get("MANGA_DATA_ROOT")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise ValueError("MANGA_DATA_ROOT must be an absolute path")
        return path
    root = repository_root()
    return root / "results" / "web" if root else Path.home() / ".local" / "share" / "manga-studio"
