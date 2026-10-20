"""Revision and immutable-artifact persistence contracts.

Cloud adapters can implement the two store protocols with transactional pointer
updates and immutable object generations. The in-memory adapters here exist only
for deterministic local contract and recovery tests; the studio still defaults
to its filesystem persistence in :mod:`manga_tts.storage`.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Protocol, Self

from .schemas import Project, ProjectV1
from .storage import digest, load_project, read_json, write_json


@dataclass(frozen=True)
class ArtifactRef:
    """Immutable object identity, provider generation, and content checksum."""

    object_id: str
    generation: str
    sha256: str

    def __post_init__(self) -> None:
        if (not isinstance(self.object_id, str) or not self.object_id
                or not isinstance(self.generation, str) or not self.generation
                or not isinstance(self.sha256, str) or len(self.sha256) != 64
                or any(char not in "0123456789abcdef" for char in self.sha256)):
            raise ValueError("Artifact reference is invalid")


@dataclass(frozen=True)
class ManifestEntry:
    """One engine-relative path mapped to an immutable object generation."""

    path: str
    artifact: ArtifactRef


@dataclass(frozen=True)
class ProjectManifest:
    """Immutable sorted mapping from project paths to verified artifact objects."""

    entries: Mapping[str, ManifestEntry]
    version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", MappingProxyType(dict(self.entries)))


@dataclass(frozen=True)
class ProjectRevision:
    """Immutable project state linked to its parent and complete artifact manifest."""

    revision_id: str
    parent_revision_id: str | None
    manifest: ArtifactRef
    project_hash: str
    fence: int


@dataclass(frozen=True)
class WriteFence:
    """Exclusive owner token with a monotonically increasing project fence."""

    project_id: str
    owner_id: str
    value: int


class PersistenceConflict(RuntimeError):
    """Expected ownership or revision precondition failed without pointer change."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class ArtifactStore(Protocol):
    """Immutable artifact storage. Reads address exact generations and stream to disk."""

    def put_file(self, source: Path) -> ArtifactRef:
        """Stream a local file immutably and return its identity and checksum."""
        ...

    def copy_to(self, artifact: ArtifactRef, destination: Path) -> None:
        """Stream the exact generation to a file or fail; never read a newer object."""
        ...


class RevisionStore(Protocol):
    """Atomic project ownership, immutable revisions, and current-pointer store."""

    def current(self, project_id: str) -> ProjectRevision | None:
        ...

    def acquire(self, project_id: str, owner_id: str) -> WriteFence:
        ...

    def release(self, fence: WriteFence) -> None:
        ...

    def recover(self, fence: WriteFence, worker_stopped: bool) -> None:
        ...

    def commit(self, expected_revision_id: str | None, fence: WriteFence,
               revision: ProjectRevision) -> None:
        """Atomically add revision and move pointer iff owner, fence, and parent match."""
        ...

    def get_revision(self, project_id: str, revision_id: str) -> ProjectRevision:
        ...


class InMemoryArtifactStore:
    """Content-addressed test adapter; each checksum has an immutable generation."""

    def __init__(self):
        self._objects: dict[tuple[str, str], bytes] = {}
        self._lock = threading.RLock()

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._objects)

    def put(self, content: bytes) -> ArtifactRef:
        data = bytes(content)
        checksum = hashlib.sha256(data).hexdigest()
        artifact = ArtifactRef(object_id="sha256:" + checksum, generation="1", sha256=checksum)
        key = (artifact.object_id, artifact.generation)
        with self._lock:
            existing = self._objects.setdefault(key, data)
            if existing != data:
                raise ValueError("Immutable artifact identity collision")
        return artifact

    def put_file(self, source: Path) -> ArtifactRef:
        return self.put(Path(source).read_bytes())

    def get(self, artifact: ArtifactRef) -> bytes:
        with self._lock:
            try:
                data = self._objects[(artifact.object_id, artifact.generation)]
            except KeyError:
                raise FileNotFoundError("Artifact generation is missing") from None
        if hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise ValueError("Artifact checksum mismatch")
        return data

    def copy_to(self, artifact: ArtifactRef, destination: Path) -> None:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.get(artifact))


class InMemoryRevisionStore:
    """Thread-safe test adapter for exclusive ownership and conditional commits."""

    def __init__(self):
        self._current: dict[str, str] = {}
        self._revisions: dict[str, dict[str, ProjectRevision]] = {}
        self._owners: dict[str, WriteFence] = {}
        self._last_fence: dict[str, int] = {}
        self._lock = threading.RLock()

    def current(self, project_id: str) -> ProjectRevision | None:
        with self._lock:
            revision_id = self._current.get(project_id)
            if revision_id is None:
                return None
            return self._revisions[project_id][revision_id]

    def acquire(self, project_id: str, owner_id: str) -> WriteFence:
        if not project_id or not owner_id:
            raise ValueError("Project and owner IDs are required")
        with self._lock:
            if project_id in self._owners:
                raise PersistenceConflict("writer_conflict", "Another writer owns this project.")
            value = self._last_fence.get(project_id, 0) + 1
            self._last_fence[project_id] = value
            fence = WriteFence(project_id=project_id, owner_id=owner_id, value=value)
            self._owners[project_id] = fence
            return fence

    def release(self, fence: WriteFence) -> None:
        with self._lock:
            if self._owners.get(fence.project_id) != fence:
                raise PersistenceConflict("stale_fence", "Writer ownership changed before release.")
            del self._owners[fence.project_id]

    def recover(self, fence: WriteFence, worker_stopped: bool) -> None:
        if worker_stopped is not True:
            raise PersistenceConflict("writer_conflict", "Ownership remains until the worker is confirmed stopped.")
        self.release(fence)

    def commit(self, expected_revision_id: str | None, fence: WriteFence,
               revision: ProjectRevision) -> None:
        with self._lock:
            if self._owners.get(fence.project_id) != fence or revision.fence != fence.value:
                raise PersistenceConflict("stale_fence", "Writer fence is no longer current.")
            current_id = self._current.get(fence.project_id)
            if current_id != expected_revision_id or revision.parent_revision_id != expected_revision_id:
                raise PersistenceConflict("revision_conflict", "Project revision changed before commit.")
            revisions = self._revisions.setdefault(fence.project_id, {})
            if revision.revision_id in revisions:
                raise PersistenceConflict("revision_conflict", "Revision identity already exists.")
            revisions[revision.revision_id] = revision
            self._current[fence.project_id] = revision.revision_id

    def get_revision(self, project_id: str, revision_id: str) -> ProjectRevision:
        with self._lock:
            try:
                return self._revisions[project_id][revision_id]
            except KeyError:
                raise FileNotFoundError("Project revision is missing") from None


class ProjectPersistence:
    """Coordinate immutable artifacts, manifests, fenced revisions, and restore."""

    def __init__(self, artifacts: ArtifactStore, revisions: RevisionStore):
        self._artifacts = artifacts
        self._revisions = revisions

    def acquire(self, project_id: str, owner_id: str) -> ProjectWriter:
        """Acquire exclusive project ownership; an interrupted owner stays fenced."""
        fence = self._revisions.acquire(project_id, owner_id)
        return ProjectWriter(self._artifacts, self._revisions, fence)

    def current(self, project_id: str) -> ProjectRevision | None:
        return self._revisions.current(project_id)

    def recover(self, project_id: str, owner_id: str, fence: int, worker_stopped: bool) -> None:
        """Release an interrupted owner only after its execution is confirmed stopped."""
        self._revisions.recover(WriteFence(project_id, owner_id, fence), worker_stopped)

    def read_manifest(self, artifact: ArtifactRef) -> ProjectManifest:
        return _read_manifest(self._artifacts, artifact)


def _checksum_file(path: Path) -> str:
    checksum = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            checksum.update(chunk)
    return checksum.hexdigest()


def _copy_verified(artifacts: ArtifactStore, artifact: ArtifactRef, destination: Path) -> None:
    artifacts.copy_to(artifact, destination)
    if _checksum_file(destination) != artifact.sha256:
        raise ValueError("Artifact checksum mismatch")


def _read_verified_bytes(artifacts: ArtifactStore, artifact: ArtifactRef) -> bytes:
    with tempfile.TemporaryDirectory(prefix="manga-artifact-read-") as temporary:
        path = Path(temporary) / "manifest.json"
        _copy_verified(artifacts, artifact, path)
        return path.read_bytes()


def _validate_relative_path(path: str) -> None:
    relative = PurePosixPath(path)
    if (not path or relative.as_posix() != path or relative.is_absolute()
            or ".." in relative.parts or "\\" in path or ":" in path):
        raise ValueError("Unsafe project manifest path")


def _read_manifest(artifacts: ArtifactStore, artifact: ArtifactRef) -> ProjectManifest:
    payload = _read_verified_bytes(artifacts, artifact)
    try:
        value = json.loads(payload)
        if not isinstance(value, dict) or value.get("version") != 1:
            raise ValueError("Unsupported project manifest version")
        raw_entries = value.get("entries")
        if not isinstance(raw_entries, dict):
            raise TypeError("Project manifest entries must be an object")
        entries = {}
        for path, raw in raw_entries.items():
            _validate_relative_path(path)
            reference = ArtifactRef(**raw)
            entries[path] = ManifestEntry(path=path, artifact=reference)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("Project manifest is invalid") from None
    if "project.json" not in entries:
        raise ValueError("Project manifest has no project state")
    if list(entries) != sorted(entries):
        raise ValueError("Project manifest entries are not canonical")
    for path in entries:
        parts = PurePosixPath(path).parts
        if any("/".join(parts[:index]) in entries for index in range(1, len(parts))):
            raise ValueError("Project manifest contains a file/directory collision")
    return ProjectManifest(entries=entries)


def _manifest_bytes(entries: dict[str, ManifestEntry]) -> bytes:
    value = {"version": 1, "entries": {
        path: {
            "object_id": entry.artifact.object_id,
            "generation": entry.artifact.generation,
            "sha256": entry.artifact.sha256,
        }
        for path, entry in sorted(entries.items())
    }}
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _copy_overlays(root: Path, overlays: Mapping[str, str | Path] | None) -> None:
    for relative, source_value in (overlays or {}).items():
        _validate_relative_path(relative)
        if relative == "project.json":
            raise ValueError("Project state must be committed through the revision interface")
        source = Path(source_value)
        if source.is_symlink() or not source.exists():
            raise ValueError("Workspace overlay source is missing or unsafe")
        if source.is_dir():
            if any(path.is_symlink() for path in source.rglob("*")):
                raise ValueError("Workspace overlays cannot contain symbolic links")
            destination = root.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination, dirs_exist_ok=True)
        elif source.is_file():
            destination = root.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        else:
            raise ValueError("Workspace overlay source must be a file or directory")


class ProjectWriter:
    """Writer scoped to one exclusive owner/fence; independent of a worker process."""

    def __init__(self, artifacts: ArtifactStore, revisions: RevisionStore, fence: WriteFence):
        self._artifacts = artifacts
        self._revisions = revisions
        self._fence = fence
        self._closed = False
        self._materialization_pending = False

    @property
    def fence(self) -> int:
        return self._fence.value

    @property
    def owner_id(self) -> str:
        return self._fence.owner_id

    @property
    def materialization_pending(self) -> bool:
        """Whether the last committed revision still needs a local workspace refresh."""
        return self._materialization_pending

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()

    def release(self) -> None:
        if not self._closed:
            self._revisions.release(self._fence)
            self._closed = True

    def load(self, root: str | Path) -> ProjectRevision | None:
        """Restore the current manifest; seed a first revision from an existing local project."""
        self._ensure_open()
        root = Path(root)
        revision = self._revisions.current(self._fence.project_id)
        if revision is None:
            project_path = root / "project.json"
            if not project_path.is_file():
                return None
            load_project(root)
            return self.commit(root, read_json(project_path), expected_revision_id=None)
        self._restore(root, revision)
        return revision

    def commit(self, root: str | Path, project: dict, expected_revision_id: str | None,
               workspace_overlays: Mapping[str, str | Path] | None = None) -> ProjectRevision:
        """Verify every staged object, then conditionally promote one complete manifest."""
        self._ensure_open()
        if self._materialization_pending:
            raise PersistenceConflict(
                "workspace_refresh_required",
                "Reload the accepted revision before committing another change.",
            )
        if not isinstance(project, dict):
            raise TypeError("Project state must be an object")
        if project.get("version") == 1:
            ProjectV1.model_validate(project)
        else:
            Project.model_validate(project)
        root = Path(root)
        if root.is_symlink() or (root.exists() and not root.is_dir()):
            raise ValueError("Project workspace must be a directory")
        current = self._revisions.current(self._fence.project_id)
        if (current.revision_id if current else None) != expected_revision_id:
            raise PersistenceConflict("revision_conflict", "Project revision changed before commit.")

        root.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="manga-project-revision-", dir=root.parent) as revision_temporary:
            staged = Path(revision_temporary) / "workspace"
            staged.mkdir()
            if root.exists():
                for path in root.rglob("*"):
                    relative = path.relative_to(root)
                    if path.is_symlink():
                        raise ValueError("Project workspaces cannot contain symbolic links")
                    if path.is_dir():
                        continue
                    if path.name.endswith(".tmp"):
                        continue
                    destination = staged / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, destination)
            _copy_overlays(staged, workspace_overlays)
            write_json(staged / "project.json", project)

            entries: dict[str, ManifestEntry] = {}
            for path in sorted(item for item in staged.rglob("*") if item.is_file()):
                relative = path.relative_to(staged).as_posix()
                _validate_relative_path(relative)
                artifact = self._artifacts.put_file(path)
                if _checksum_file(path) != artifact.sha256:
                    raise ValueError("Staged artifact checksum mismatch")
                with tempfile.TemporaryDirectory(prefix="manga-artifact-verify-") as verify_temporary:
                    _copy_verified(self._artifacts, artifact, Path(verify_temporary) / "artifact")
                entries[relative] = ManifestEntry(path=relative, artifact=artifact)

            manifest_payload = _manifest_bytes(entries)
            manifest_path = Path(revision_temporary) / "manifest.json"
            manifest_path.write_bytes(manifest_payload)
            manifest_ref = self._artifacts.put_file(manifest_path)
            if _checksum_file(manifest_path) != manifest_ref.sha256:
                raise ValueError("Staged manifest checksum mismatch")
            with tempfile.TemporaryDirectory(prefix="manga-manifest-verify-") as verify_temporary:
                _copy_verified(self._artifacts, manifest_ref, Path(verify_temporary) / "manifest.json")
            revision = ProjectRevision(
                revision_id=uuid.uuid4().hex,
                parent_revision_id=expected_revision_id,
                manifest=manifest_ref,
                project_hash=digest(project),
                fence=self._fence.value,
            )
            self._revisions.commit(expected_revision_id, self._fence, revision)
            try:
                self._replace_workspace(root, staged)
                self._materialization_pending = False
            except OSError:
                # The durable pointer is already current. Keep the accepted result
                # and let the next load rebuild this disposable local view.
                self._materialization_pending = True
        return revision

    def _restore(self, root: Path, revision: ProjectRevision) -> None:
        manifest = _read_manifest(self._artifacts, revision.manifest)
        root.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="manga-project-restore-", dir=root.parent) as temporary:
            staged = Path(temporary) / "workspace"
            staged.mkdir()
            for relative, entry in manifest.entries.items():
                destination = staged.joinpath(*PurePosixPath(relative).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                _copy_verified(self._artifacts, entry.artifact, destination)
            if digest(read_json(staged / "project.json")) != revision.project_hash:
                raise ValueError("Project state checksum does not match its revision")
            load_project(staged)
            self._replace_workspace(root, staged)
            self._materialization_pending = False

    @staticmethod
    def _replace_workspace(root: Path, staged: Path) -> None:
        if root.is_symlink():
            raise ValueError("Project workspaces cannot be symbolic links")
        if root.exists() and not root.is_dir():
            raise ValueError("Project workspace must be a directory")
        backup = root.with_name(root.name + ".previous-" + uuid.uuid4().hex)
        moved_previous = False
        if root.exists():
            root.replace(backup)
            moved_previous = True
        try:
            staged.replace(root)
        except Exception:
            if moved_previous and backup.exists() and not root.exists():
                backup.replace(root)
            raise
        if moved_previous:
            shutil.rmtree(backup)

    def _ensure_open(self) -> None:
        if self._closed:
            raise PersistenceConflict("stale_fence", "Project writer has been released.")
