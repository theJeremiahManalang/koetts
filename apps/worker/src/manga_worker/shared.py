"""Local application boundary for shared requests and reviewed publications.

The caller authenticates users before invoking this service. The command protocol
uses standard input so reader notes and verified identity do not appear in argv.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from manga_tts.shared_requests import SharedRequests

from . import workflow
from .paths import data_root
from .shared_actions import METADATA_ACTIONS, metadata_action


class SharedService:
    def __init__(self, root: Path):
        backend = os.environ.get("MANGA_SHARED_BACKEND", "sqlite")
        metadata = None
        artifacts = None
        if backend == "cloud":
            from .cloud import CloudSettings, cloud_stores

            stores = cloud_stores(CloudSettings.from_environment(), root / "shared-cache")
            metadata, artifacts = stores.shared_metadata, stores.shared_artifacts
        elif backend == "firestore":
            from .shared_cutover import FirestoreSettings, bind_firestore
            from .shared_firestore import FirestoreSharedMetadata, artifact_store_identity

            settings = FirestoreSettings.from_environment()
            client = settings.client()
            bind_firestore(root, client, settings)
            metadata = FirestoreSharedMetadata(client, settings.dataset, artifact_store_identity(root))
        elif backend == "sqlite":
            from .shared_cutover import read_binding

            if read_binding(root) is not None:
                raise ValueError("Data root is bound to Firestore; explicit cutover reconciliation required")
        else:
            raise ValueError("Invalid shared metadata backend")
        self.store = SharedRequests(root / "shared.sqlite3", metadata=metadata, artifacts=artifacts)

    def execute(self, request: dict):
        action = request.get("action")
        store = self.store
        if action in METADATA_ACTIONS:
            result = metadata_action(store, request)
            if action == "published":
                result["path"] = str(store.published_artifact(
                    request["work_id"], "chapter_narration.wav", result["publication_id"],
                ))
            return result
        if action == "link":
            return workflow.link_shared_project(store, workflow.identifier(request["work_id"]), request["project_id"], request["actor"])
        if action == "prepare":
            return workflow.prepare_shared_export(store, workflow.identifier(request["work_id"]), request["actor"], request["revision"])
        if action == "review":
            return workflow.approve_shared_export(store, workflow.identifier(request["work_id"]),
                                                   workflow.identifier(request["candidate_id"]), request["actor"], request["revision"])
        if action == "publish":
            prior = request.get("expected_publication")
            if prior is not None:
                workflow.identifier(prior)
            return workflow.publish_shared_export(store, workflow.identifier(request["work_id"]),
                                                  workflow.identifier(request["review_id"]), request["actor"], request["revision"], prior)
        if action == "candidate":
            return {"path": str(store.candidate_artifact(workflow.identifier(request["candidate_id"]), "chapter_narration.wav"))}
        raise ValueError("Unsupported shared action")


def main():
    try:
        raw = sys.stdin.read(65537)
        if len(raw) > 65536:
            raise ValueError("Request too large")
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError("Invalid request")
        result = SharedService(data_root()).execute(request)
        print(json.dumps({"ok": True, "result": result}))
    except Exception:  # noqa: BLE001 - the command boundary never emits private data or tracebacks.
        print(json.dumps({"ok": False, "error": "Request is invalid, unavailable, or has changed."}))


if __name__ == "__main__":
    main()
