"""GCS-backed immutable artifacts and disposable shared-audio cache."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path

from manga_tts.persistence import ArtifactRef


_CHECKSUM = re.compile(r"[a-f0-9]{64}\Z")
_GENERATION = re.compile(r"[1-9][0-9]*\Z")


def _checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _namespace(value: str) -> str:
    if (not isinstance(value, str) or not value or value.startswith("/") or value.endswith("/")
            or "\\" in value or any(part in {"", ".", ".."} for part in value.split("/"))
            or any(not re.fullmatch(r"[A-Za-z0-9._-]+", part) for part in value.split("/"))):
        raise ValueError("Invalid artifact namespace")
    return value


def _validate_ref(ref: ArtifactRef) -> None:
    if not isinstance(ref, ArtifactRef) or not _GENERATION.fullmatch(ref.generation) or not _CHECKSUM.fullmatch(ref.sha256):
        raise ValueError("Invalid artifact reference")


def _precondition_failed(error: Exception) -> bool:
    return getattr(error, "code", None) == 412 or getattr(error, "status_code", None) == 412


class GCSArtifactStore:
    """Content addressed GCS objects, always read and returned by exact generation.

    The bucket is an injected google-cloud-storage Bucket, keeping the SDK optional
    for local users and making provider behavior straightforward to fake in tests.
    """

    def __init__(self, bucket, namespace: str):
        _namespace(namespace)
        if not isinstance(getattr(bucket, "name", None), str) or not bucket.name:
            raise ValueError("A named GCS bucket is required")
        self.bucket = bucket
        self.namespace = namespace

    @property
    def bucket_name(self) -> str:
        return self.bucket.name

    @property
    def artifact_store_id(self) -> str:
        identity = hashlib.sha256((self.bucket_name + "\0" + self.namespace).encode()).hexdigest()
        return "gcs-v1:" + identity

    def _object_name(self, checksum: str) -> str:
        if not _CHECKSUM.fullmatch(checksum):
            raise ValueError("Invalid artifact checksum")
        return f"{self.namespace}/{checksum}"

    def validate_ref(self, artifact: ArtifactRef) -> str:
        """Validate exact-generation identity within this configured namespace."""
        _validate_ref(artifact)
        expected = self._object_name(artifact.sha256)
        if artifact.object_id != expected:
            raise ValueError("Artifact reference is outside this namespace or has an invalid identity")
        return expected

    @staticmethod
    def _download(blob, destination: Path) -> None:
        # GCS accepts a filename and writes directly. The caller always supplies a
        # private temporary path and publishes it only after checksum verification.
        blob.download_to_filename(str(destination))

    def _verify_remote(self, blob, checksum: str, directory: Path) -> str:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, prefix=".gcs-verify-", delete=False) as out:
                temporary = Path(out.name)
            self._download(blob, temporary)
            actual = _checksum(temporary)
            if actual != checksum:
                raise ValueError("Stored artifact checksum mismatch")
            generation = getattr(blob, "generation", None)
            generation = str(generation) if generation is not None else ""
            if not _GENERATION.fullmatch(generation):
                raise ValueError("GCS did not return a valid artifact generation")
            return generation
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def put_file(self, source: Path) -> ArtifactRef:
        """Stage a frozen copy, then create the content object once or verify it."""
        source = Path(source)
        temporary = None
        staging_dir = Path(tempfile.gettempdir())
        digest = hashlib.sha256()
        try:
            with source.open("rb") as incoming, tempfile.NamedTemporaryFile(prefix="manga-gcs-stage-", delete=False) as staged:
                temporary = Path(staged.name)
                while chunk := incoming.read(1024 * 1024):
                    digest.update(chunk)
                    staged.write(chunk)
                staged.flush()
                os.fsync(staged.fileno())
            checksum = digest.hexdigest()
            name = self._object_name(checksum)
            blob = self.bucket.blob(name)
            try:
                blob.upload_from_filename(str(temporary), if_generation_match=0)
                generation = getattr(blob, "generation", None)
                generation = str(generation) if generation is not None else ""
                if not _GENERATION.fullmatch(generation):
                    raise ValueError("GCS upload did not return an artifact generation")
                # Verify stored bytes against the staged checksum before exposing ref.
                exact_blob = self.bucket.blob(name, generation=int(generation))
                actual_generation = self._verify_remote(exact_blob, checksum, staging_dir)
                if actual_generation != generation:
                    raise ValueError("GCS returned a different artifact generation")
                return ArtifactRef(object_id=name, generation=generation, sha256=checksum)
            except Exception as error:
                if not _precondition_failed(error):
                    raise
            # Another writer created the content address. Reload only to discover
            # its generation, then verify that exact generation's bytes.
            existing = self.bucket.blob(name)
            existing.reload()
            generation = getattr(existing, "generation", None)
            generation = str(generation) if generation is not None else ""
            if not _GENERATION.fullmatch(generation):
                raise ValueError("Existing GCS artifact has no valid generation")
            exact_blob = self.bucket.blob(name, generation=int(generation))
            actual_generation = self._verify_remote(exact_blob, checksum, staging_dir)
            if actual_generation != generation:
                raise ValueError("GCS returned a different artifact generation")
            return ArtifactRef(object_id=name, generation=generation, sha256=checksum)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def copy_to(self, artifact: ArtifactRef, destination: Path) -> None:
        """Download the exact generation and atomically replace destination on success."""
        name = self.validate_ref(artifact)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.name}.", delete=False) as out:
                temporary = Path(out.name)
            blob = self.bucket.blob(name, generation=int(artifact.generation))
            self._download(blob, temporary)
            if _checksum(temporary) != artifact.sha256:
                raise ValueError("Artifact checksum mismatch")
            os.replace(temporary, destination)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


class GCSSharedArtifacts:
    """Durable checksum references backed by Firestore and a scratch file cache.

    ``references`` must provide ``get(checksum)`` and ``put(ArtifactRef)``. Cache
    files are never treated as durable: every returned file is checksum verified.
    """

    def __init__(self, artifacts: GCSArtifactStore, references, cache_root: Path):
        if not isinstance(artifacts, GCSArtifactStore):
            raise ValueError("A GCS artifact store is required")
        if not callable(getattr(references, "get", None)) or not callable(getattr(references, "put", None)):
            raise ValueError("Durable artifact references must provide get and put")
        self.artifacts = artifacts
        self.references = references
        self.cache_root = Path(cache_root) / hashlib.sha256(artifacts.artifact_store_id.encode()).hexdigest()

    def _reference(self, checksum: str):
        try:
            return self.references.get(checksum)
        except FileNotFoundError:
            return None

    def store(self, source: Path) -> str:
        artifact = self.artifacts.put_file(Path(source))
        stored = self._reference(artifact.sha256)
        if stored is None:
            self.references.put(artifact)
            stored = self._reference(artifact.sha256)
        if stored != artifact:
            raise ValueError("Durable artifact reference conflicts with stored content")
        return artifact.sha256

    def verified(self, checksum: str) -> Path:
        if not isinstance(checksum, str) or not _CHECKSUM.fullmatch(checksum):
            raise ValueError("Invalid artifact checksum")
        artifact = self._reference(checksum)
        if artifact is None:
            raise ValueError("Artifact reference is unavailable")
        self.artifacts.validate_ref(artifact)
        if artifact.sha256 != checksum:
            raise ValueError("Durable artifact reference checksum mismatch")
        self.cache_root.mkdir(parents=True, exist_ok=True)
        target = self.cache_root / checksum
        if target.exists() or target.is_symlink():
            if not target.is_symlink() and target.is_file() and _checksum(target) == checksum:
                return target
            if target.is_dir() and not target.is_symlink():
                raise ValueError("Artifact cache path is not a file")
        self.artifacts.copy_to(artifact, target)
        if _checksum(target) != checksum:
            target.unlink(missing_ok=True)
            raise ValueError("Artifact checksum mismatch")
        return target
