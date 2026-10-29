"""Explicit cloud storage construction; disposable local paths never own cloud state."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from manga_tts.persistence import ArtifactStore, ProjectPersistence, RevisionStore


@dataclass(frozen=True)
class CloudSettings:
    project: str
    database: str
    dataset: str
    bucket: str
    namespace: str

    def __post_init__(self):
        for value in (self.project, self.dataset):
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
                raise ValueError("Explicit cloud project, database and dataset required")
        if not isinstance(self.database, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}|\(default\)", self.database):
            raise ValueError("Explicit cloud database required")
        if not isinstance(self.bucket, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,220}[a-z0-9]", self.bucket):
            raise ValueError("Invalid cloud artifact bucket")
        if not isinstance(self.namespace, str) or not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", self.namespace):
            raise ValueError("Explicit canonical cloud artifact namespace required")

    @classmethod
    def from_environment(cls):
        return cls(*(os.environ.get(key, "") for key in (
            "FIREBASE_PROJECT_ID", "FIRESTORE_DATABASE_ID", "MANGA_CLOUD_DATASET",
            "MANGA_ARTIFACT_BUCKET", "MANGA_ARTIFACT_NAMESPACE",
        )))


@dataclass(frozen=True)
class CloudStores:
    persistence: ProjectPersistence
    shared_metadata: object
    shared_artifacts: object
    artifacts: ArtifactStore
    revisions: RevisionStore


def cloud_stores(settings: CloudSettings, cache_root: Path, *, firestore_client=None, storage_client=None):
    """Use attached ADC only when clients are not injected. Never select local fallback."""
    from .cloud_artifacts import GCSArtifactStore, GCSSharedArtifacts
    from .cloud_revisions import FirestoreArtifactReferences, FirestoreRevisionStore
    from .shared_firestore import FirestoreSharedMetadata

    if firestore_client is None:
        from google.cloud import firestore

        firestore_client = firestore.Client(project=settings.project, database=settings.database)
    if storage_client is None:
        from google.cloud import storage

        storage_client = storage.Client(project=settings.project)
    artifacts = GCSArtifactStore(storage_client.bucket(settings.bucket), settings.namespace)
    identity = artifacts.artifact_store_id
    revisions = FirestoreRevisionStore(firestore_client, settings.dataset, identity)
    references = FirestoreArtifactReferences(firestore_client, settings.dataset, identity)
    return CloudStores(
        persistence=ProjectPersistence(artifacts, revisions),
        shared_metadata=FirestoreSharedMetadata(firestore_client, settings.dataset, identity),
        shared_artifacts=GCSSharedArtifacts(artifacts, references, cache_root),
        artifacts=artifacts,
        revisions=revisions,
    )
