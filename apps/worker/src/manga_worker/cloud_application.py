"""Hosted application boundary over Firestore revisions, jobs, and GCS artifacts."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from manga_tts import PipelineRouter, schemas
from manga_tts.operations import Operation
from manga_tts.persistence import ArtifactRef
from manga_tts.shared_requests import ReaderIntakePolicy, SharedRequests
from manga_tts.storage import digest, read_json

from .cloud import CloudSettings, cloud_stores
from .cloud_admission import CloudChapterAdmission
from .cloud_budget import CloudBudgetLedger
from .cloud_operations import FirestoreOperationStore
from .workflow import WORKFLOW_ACTIONS, operation_pipeline_config

_MAX_UPLOAD = 10 * 1024 * 1024
_MAX_PAGES = 40
_MAX_UPLOAD_FILES = 42
_MAX_IMAGE_PIXELS = 25_000_000
_SAFE_NAME = re.compile(r"[A-Za-z0-9._/-]{1,240}\Z")
_OPERATION_FIELDS = {
    "action", "project", "revision", "actor", "upload_token", "images", "source_hashes",
    "cloud_uploads", "project_revision_id", "mode", "direction", "mp3", "command", "work_id",
}


class CloudApplication:
    """Per-request hosted service. Scratch contains verified cache data only."""

    def __init__(self, settings: CloudSettings, *, firestore_client=None, storage_client=None,
                 cache_root: Path, admission_clock=None):
        self.settings = settings
        self.root = Path(cache_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.stores = cloud_stores(settings, self.root / "artifacts", firestore_client=firestore_client,
                                   storage_client=storage_client)
        self.budget = CloudBudgetLedger(
            self.stores.revisions.client, settings.dataset, self.stores.artifacts.artifact_store_id
        )
        self.operations = FirestoreOperationStore(
            self.stores.revisions.client, settings.dataset, self.stores.artifacts.artifact_store_id,
            budget=self.budget,
        )
        self.shared_requests = SharedRequests(
            self.root / "shared-unused.sqlite3", metadata=self.stores.shared_metadata,
            artifacts=self.stores.shared_artifacts, intake_policy=ReaderIntakePolicy(),
        )
        self.admission = CloudChapterAdmission(
            self.stores.revisions.client, settings.dataset, self.stores.artifacts.artifact_store_id,
            clock=admission_clock,
        )
        self.client = self.stores.revisions.client
        self.uploads = self.client.collection("hosted_workflow_v1").document(settings.dataset).collection("uploads")

    @staticmethod
    def identifier(value):
        from .workflow import identifier
        return identifier(value)

    def production_status(self):
        return {"budget": self.budget.status(), "chapter_quota": self.admission.status(),
                "reader_limits": {"pending": self.shared_requests.intake_policy.max_pending,
                                  "new_per_utc_day": self.shared_requests.intake_policy.max_new_per_utc_day},
                "artifact_collection": self.stores.revisions.artifact_maintenance_status()}

    @staticmethod
    def _actor(actor: dict, project: str) -> dict:
        if (not isinstance(actor, dict) or set(actor) != {"kind", "uid", "project_id"}
                or actor.get("kind") != "firebase" or actor.get("project_id") != project
                or not isinstance(actor.get("uid"), str) or not actor["uid"]
                or len(actor["uid"]) > 256 or any(ord(c) < 32 for c in actor["uid"])):
            raise ValueError("Invalid verified hosted actor")
        return {"kind": "firebase", "uid": actor["uid"], "project_id": project}

    @staticmethod
    def _safe_name(name: str) -> PurePosixPath:
        if (not isinstance(name, str) or not _SAFE_NAME.fullmatch(name) or "\\" in name
                or name.startswith("/") or ":" in name):
            raise ValueError("Invalid upload filename")
        path = PurePosixPath(name)
        if path.as_posix() != name or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("Invalid upload filename")
        return path

    def _cache_dir(self, *parts: str) -> Path:
        current = self.root
        for part in parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Hosted cache path is unsafe")
            current.mkdir(exist_ok=True)
        return current

    def _cache_entry(self, workspace: Path, relative: str, entry) -> Path:
        path = self._safe_name(relative)
        target = workspace.joinpath(*path.parts)
        cursor = workspace
        if workspace.is_symlink():
            raise ValueError("Hosted cache workspace is unsafe")
        for part in path.parts[:-1]:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError("Hosted cache path is unsafe")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not target.is_symlink() and target.is_file():
            with target.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() == entry.artifact.sha256:
                    return target
        self.stores.artifacts.copy_to(entry.artifact, target)
        if target.is_symlink() or not target.is_file():
            raise ValueError("Hosted artifact materialization failed")
        return target

    @staticmethod
    def _upload_name(name: str) -> None:
        if name in {"chapter.zip", "cast.zip", "panel.png"}:
            return
        match = re.fullmatch(r"(0|[1-9][0-9]?)\.png", name) if isinstance(name, str) else None
        if match and int(match.group(1)) < _MAX_PAGES:
            return
        raise ValueError("Invalid hosted upload filename")

    @staticmethod
    def _validate_image(path: Path) -> None:
        from PIL import Image, UnidentifiedImageError

        try:
            with Image.open(path) as image:
                if image.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("Upload must contain a supported image")
                width, height = image.size
                if (not isinstance(width, int) or not isinstance(height, int) or width < 1 or height < 1
                        or width * height > _MAX_IMAGE_PIXELS):
                    raise ValueError("Image dimensions exceed the 25-megapixel limit")
                image.verify()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("Upload is not a valid image") from exc

    def _manifest_ref(self, token: str, actor: dict):
        snap = self.uploads.document(token).get()
        value = snap.to_dict() if snap.exists else None
        if not isinstance(value, dict) or value.get("owner_uid") != actor["uid"] or value.get("project_id") != actor["project_id"]:
            raise ValueError("Upload token is unavailable to this actor")
        files = value.get("files")
        if not isinstance(files, dict) or len(files) > _MAX_UPLOAD_FILES:
            raise ValueError("Upload manifest is invalid")
        for name in files:
            self._upload_name(name)
        return value

    def upload(self, upload_token: str, name: str, source: Path, actor: dict) -> dict:
        token = self.identifier(upload_token)
        self._safe_name(name)
        self._upload_name(name)
        actor = self._actor(actor, self.settings.project)
        source = Path(source)
        if source.is_symlink() or not source.is_file() or source.stat().st_size > _MAX_UPLOAD:
            raise ValueError("Upload must be a regular file no larger than 10 MiB")
        # Bound bytes actually staged, including files changed after stat().
        with tempfile.TemporaryDirectory(prefix="hosted-upload-") as td:
            staged = Path(td) / "upload"
            total = 0
            with source.open("rb") as src, staged.open("wb") as out:
                while chunk := src.read(64 * 1024):
                    total += len(chunk)
                    if total > _MAX_UPLOAD:
                        raise ValueError("Upload must be no larger than 10 MiB")
                    out.write(chunk)
            if total == 0:
                raise ValueError("Upload cannot be empty")
            if name.endswith(".png"):
                self._validate_image(staged)
            epoch = self.stores.revisions.artifact_epoch()
            ref = self.stores.artifacts.put_file(staged)
        doc = self.uploads.document(token)
        from google.cloud import firestore

        self.stores.revisions.ensure_binding()

        @firestore.transactional
        def commit(tx):
            bound = self.stores.revisions._binding(tx)
            if not bound:
                raise ValueError("Hosted dataset namespace binding is missing")
            self.stores.revisions._assert_artifact_epoch(tx, epoch)
            snap = doc.get(transaction=tx)
            prior = snap.to_dict() if snap.exists else {"owner_uid": actor["uid"], "project_id": actor["project_id"], "files": {}}
            if prior.get("owner_uid") != actor["uid"] or prior.get("project_id") != actor["project_id"]:
                raise ValueError("Upload token belongs to another actor")
            files = dict(prior.get("files", {}))
            existing = files.get(name)
            encoded = vars(ref)
            if existing is not None and existing != encoded:
                raise ValueError("Upload filename is immutable")
            if existing is None and len(files) >= _MAX_UPLOAD_FILES:
                raise ValueError("An upload token cannot contain more than 42 files")
            files[name] = encoded
            tx.set(doc, {"owner_uid": actor["uid"], "project_id": actor["project_id"], "files": files,
                         "updated_at": time.time()})
        commit(self.client.transaction())
        return {"name": name, "sha256": ref.sha256, "size": total}

    def _read_project_manifest(self, revision):
        manifest = self.stores.persistence.read_manifest(revision.manifest)
        for entry in manifest.entries.values():
            self.stores.artifacts.validate_ref(entry.artifact)
        return manifest

    def _read_project(self, project_id: str, *, revision_id: str | None = None, materialize: bool = True,
                      manifest=None):
        project_id = self.identifier(project_id)
        revision = (self.stores.persistence.current(project_id) if revision_id is None
                    else self.stores.revisions.get_revision(project_id, revision_id))
        if revision is None:
            raise FileNotFoundError("Project not found")
        manifest = manifest or self._read_project_manifest(revision)
        project_entry = manifest.entries.get("project.json")
        if project_entry is None:
            raise ValueError("Hosted project manifest has no project state")
        workspace = self._cache_dir("projects", project_id, revision.revision_id)
        entries = manifest.entries.items() if materialize else (("project.json", project_entry),)
        for relative, entry in entries:
            self._cache_entry(workspace, relative, entry)
        data = read_json(workspace / "project.json")
        if not isinstance(data, dict) or digest(data) != revision.project_hash:
            raise ValueError("Hosted project revision checksum mismatch")
        if len(data.get("chapter", {}).get("pages", [])) > _MAX_PAGES:
            raise ValueError("Hosted projects are limited to 40 pages")
        return revision, workspace, data

    def list_projects(self) -> dict:
        projects = []
        collection = self.stores.revisions.root.collection("projects")
        for snapshot in collection.limit(200).stream():
            try:
                revision = self.stores.persistence.current(snapshot.id)
                if revision is None:
                    continue
                manifest = self.stores.persistence.read_manifest(revision.manifest)
                item = manifest.entries.get("project.json")
                if item is None:
                    continue
                with tempfile.TemporaryDirectory(prefix="hosted-list-") as td:
                    target = Path(td) / "project.json"
                    self.stores.artifacts.copy_to(item.artifact, target)
                    data = read_json(target)
                if not isinstance(data, dict) or digest(data) != revision.project_hash:
                    raise ValueError("Hosted project revision checksum mismatch")
                projects.append({"id": snapshot.id, "name": data.get("title") or "Untitled project",
                                 "scenes": len(data.get("scenes", []))})
            except (ValueError, FileNotFoundError):
                continue
        return {"projects": projects, "has_api_key": bool(os.environ.get("GEMINI_API_KEY"))}

    def snapshot(self, project_id: str) -> dict:
        revision = self.stores.persistence.current(self.identifier(project_id))
        if revision is None:
            raise FileNotFoundError("Project not found")
        manifest = self._read_project_manifest(revision)
        _, workspace, _ = self._read_project(project_id, revision_id=revision.revision_id, manifest=manifest,
                                             materialize=False)
        router = PipelineRouter(operation_pipeline_config(workspace))
        router.load_project()
        return self._snapshot(router, manifest)

    @staticmethod
    def _snapshot(router, manifest=None):
        from .workflow import snapshot
        return snapshot(router, manifest)

    def _verified_uploads(self, payload: dict, actor: dict):
        token = payload.get("upload_token")
        if token is None:
            return {}, [], None
        token = self.identifier(token)
        manifest = self._manifest_ref(token, actor)
        files = manifest.get("files", {})
        action = payload.get("action")
        if action == "create" and payload.get("mode") == "images":
            names = [name for name in files if re.fullmatch(r"(?:0|[1-9][0-9]?)\.png", name)
                     and int(name[:-4]) < _MAX_PAGES]
            names.sort(key=lambda name: int(name[:-4]))
            if not names or len(names) > _MAX_PAGES or names != [f"{index}.png" for index in range(len(names))]:
                raise ValueError("Image upload order is invalid")
            payload["images"] = names
        elif action == "ocr":
            names = ["panel.png"]
        elif action == "create":
            names = ["chapter.zip"]
        elif action == "cast-import":
            names = ["cast.zip"]
        else:
            raise ValueError("This action does not accept uploaded files")
        if "cast.zip" in files and action == "create":
            names = [*names, "cast.zip"]
        refs = {}
        hashes = []
        for name in names:
            self._safe_name(name)
            raw = files.get(name)
            if raw is None:
                raise ValueError("Required upload is missing")
            ref = ArtifactRef(**raw)
            self.stores.artifacts.validate_ref(ref)
            refs[name] = raw
            hashes.append(ref.sha256)
        return refs, hashes, token

    def _validate_archive_pages(self, action: str, request: dict, refs: dict) -> int | None:
        if action != "create" or request.get("mode") not in {"chapter", "restore"}:
            return None
        name = "chapter.zip" if request["mode"] == "chapter" else "project.zip"
        # Restore callers historically upload their bundle as chapter.zip.
        if name not in refs and "chapter.zip" in refs:
            name = "chapter.zip"
        with tempfile.TemporaryDirectory(prefix="hosted-archive-check-") as td:
            archive_path = Path(td) / "upload.zip"
            self.stores.artifacts.copy_to(ArtifactRef(**refs[name]), archive_path)
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    metadata_name = "project.json" if request["mode"] == "restore" else "chapter_analysis.json"
                    matches = [entry for entry in archive.infolist() if entry.filename == metadata_name]
                    if len(matches) != 1:
                        raise ValueError("Archive metadata is missing or duplicated")
                    info = matches[0]
                    if info.file_size > 5 * 1024 * 1024:
                        raise ValueError("Chapter metadata is too large")
                    metadata_bytes = archive.read(info)
                metadata = json.loads(metadata_bytes)
                if request["mode"] == "restore":
                    from manga_tts.storage import load_project
                    project_root = Path(td) / "restore"
                    project_root.mkdir()
                    (project_root / "project.json").write_bytes(metadata_bytes)
                    loaded = load_project(project_root)
                    page_count = len(loaded.get("chapter", {}).get("pages", []))
                else:
                    from manga_tts.schemas import ChapterInput, validate_contract
                    validate_contract(metadata, ChapterInput, "chapter")
                    page_count = len(metadata["pages"])
            except (KeyError, OSError, zipfile.BadZipFile, json.JSONDecodeError, AttributeError, TypeError) as exc:
                raise ValueError("Chapter archive metadata is invalid") from exc
            if not isinstance(page_count, int) or isinstance(page_count, bool) or not 1 <= page_count <= _MAX_PAGES:
                raise ValueError("Hosted projects are limited to 40 pages")
            return page_count

    def _work_admission(self, request: dict, key: str, page_count: int):
        work_id = request.get("work_id")
        if not isinstance(work_id, str) or not re.fullmatch(r"[a-f0-9]{32}", work_id):
            raise ValueError("Approved shared chapter work is required before hosted project creation")
        reservation = self.admission.prepare(work_id, key, page_count)
        root = self.client.collection("shared_workflow_v1").document(self.settings.dataset)
        work_ref = root.collection("chapter_work").document(work_id)
        approval_ref = root.collection("work_approvals").document(work_id)

        def admit(transaction):
            # Recheck trusted shared metadata in the operation transaction before
            # the reservation callback stages any ledger writes.
            shared_snapshot = root.get(transaction=transaction)
            shared = shared_snapshot.to_dict() if shared_snapshot.exists else None
            if (not isinstance(shared, dict)
                    or shared.get("schema_version") != 1
                    or isinstance(shared.get("schema_version"), bool)
                    or shared.get("artifact_store_id") != self.stores.artifacts.artifact_store_id):
                raise ValueError("Shared chapter work belongs to a different schema or artifact store")
            work_snapshot = work_ref.get(transaction=transaction)
            approval_snapshot = approval_ref.get(transaction=transaction)
            work = work_snapshot.to_dict() if work_snapshot.exists else None
            approval = approval_snapshot.to_dict() if approval_snapshot.exists else None
            if (not isinstance(work, dict) or work.get("id") != work_id
                    or work.get("status") not in {"approved", "published"}
                    or not isinstance(approval, dict) or approval.get("work_id") != work_id
                    or not isinstance(approval.get("actor"), str) or not approval["actor"]
                    or not isinstance(approval.get("created_at"), str) or not approval["created_at"]):
                raise ValueError("Approved shared chapter work is required before hosted project creation")
            reservation(transaction)

        return admit

    def enqueue_operation(self, payload: dict, key: str) -> Operation:
        if not isinstance(payload, dict) or set(payload) - _OPERATION_FIELDS:
            raise ValueError("Invalid operation request")
        request = dict(payload)
        request.pop("project_revision_id", None)
        request.pop("cloud_uploads", None)
        request.pop("source_hashes", None)
        request.pop("actor", None)
        action = request.get("action")
        if action not in WORKFLOW_ACTIONS and action != "ocr":
            raise ValueError("Unknown workflow action")
        project = self.identifier(request.get("project"))
        actor = self._actor(payload.get("actor"), self.settings.project)
        artifact_epoch = self.stores.revisions.artifact_epoch()
        refs, hashes, token = self._verified_uploads(request, actor)
        archive_page_count = self._validate_archive_pages(action, request, refs)
        request.update({"actor": actor, "upload_token": token, "cloud_uploads": refs, "source_hashes": hashes})

        # Fingerprint original user intent before consulting the mutable project pointer.
        # A lost response can then recover the same operation after it advances state.
        semantic = {k: v for k, v in request.items()
                    if k not in {"upload_token", "cloud_uploads", "source_hashes", "project_revision_id"}}
        if action == "create":
            semantic.pop("project", None)
            semantic.pop("revision", None)
        semantic["trusted_uploads"] = [{"name": name, "sha256": ref["sha256"]} for name, ref in refs.items()]
        request_fingerprint = digest(semantic)
        try:
            existing = self.operations.get_by_key(key)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                from manga_tts.operations import OperationConflict
                raise OperationConflict("idempotency_conflict", "This idempotency key already belongs to a different request.")
            return existing

        current = self.stores.persistence.current(project)
        if action == "create":
            if current is not None:
                raise ValueError("New project identity is already in use")
            pinned = None
            request.pop("revision", None)
        elif action == "ocr":
            pinned = current.revision_id if current is not None else None
            if current is not None:
                self._require_revision(request.get("revision"), current.project_hash)
        else:
            if current is None:
                raise FileNotFoundError("Project not found")
            pinned = current.revision_id
            self._require_revision(request.get("revision"), current.project_hash)
        request["project_revision_id"] = pinned
        admission = None
        if action == "create":
            if request.get("mode") == "images":
                page_count = len(request.get("images", []))
            else:
                page_count = archive_page_count
            if page_count is None:
                raise ValueError("Hosted chapter page count could not be verified")
            admission = self._work_admission(request, key, page_count)
        source_fingerprint = self._source_fingerprint(request, refs, hashes, current)
        configuration = {k: request[k] for k in ("mode", "direction", "mp3") if k in request}
        command = request.get("command")
        if isinstance(command, dict) and "settings" in command:
            configuration["settings"] = command["settings"]
        stage = "magi" if (action == "create" and request.get("mode") == "images") or action == "ocr" else "pipeline"
        return self.operations.enqueue(idempotency_key=key, payload=request, project_id=project, stage=stage,
                                       revision=request.get("revision"), source_fingerprint=source_fingerprint,
                                       configuration_fingerprint=digest(configuration), request_fingerprint=request_fingerprint,
                                       admission=admission, artifact_epoch=artifact_epoch)

    @staticmethod
    def _require_revision(expected: str | None, current: str) -> None:
        if expected != current:
            raise schemas.WorkflowError(schemas.Failure(
                code="revision_conflict", stage="persistence",
                message="This project changed in another session. Reload before applying your edits.",
            ))

    def _source_fingerprint(self, request: dict, refs: dict, hashes: list[str], current) -> str:
        if request.get("action") == "ocr":
            return digest({"uploads": hashes, "project_evidence": []})
        from .workflow import operation_source_fingerprint
        root = self.root / "source-fingerprint-metadata"
        token = request.get("upload_token")
        checksums = {}
        if token:
            for name, raw_ref in refs.items():
                self._safe_name(name)
                reference = ArtifactRef(**raw_ref)
                self.stores.artifacts.validate_ref(reference)
                checksums[f"uploads/{token}/{name}"] = reference.sha256

        project_data = None
        if current is not None and request.get("action") != "create":
            manifest = self._read_project_manifest(current)
            _, _, project_data = self._read_project(request["project"], revision_id=current.revision_id,
                                                     materialize=False, manifest=manifest)
            project_prefix = f"projects/{request['project']}/"
            checksums.update({project_prefix + path: entry.artifact.sha256
                              for path, entry in manifest.entries.items()})

        fingerprint_request = dict(request, source_hashes=hashes)
        return operation_source_fingerprint(fingerprint_request, root=root,
                                            source_checksums=checksums, project_data=project_data)

    def operation_status(self, operation_id: str) -> dict | None:
        try:
            return self.operations.get(self.identifier(operation_id)).public()
        except FileNotFoundError:
            return None

    def operation_by_key(self, key: str) -> dict | None:
        try:
            return self.operations.get_by_key(key).public()
        except FileNotFoundError:
            return None

    def shared(self, payload: dict, actor: dict):
        if not isinstance(payload, dict):
            raise ValueError("Invalid shared request")
        actor = self._actor(actor, self.settings.project)
        request = dict(payload)
        reader = json.dumps([actor["project_id"], actor["uid"]], separators=(",", ":"), ensure_ascii=False)
        action = request.get("action")
        request["reader"] = reader
        request["actor"] = reader
        if action == "link":
            project_id = self.identifier(request.get("project_id"))
            revision = self.stores.persistence.current(project_id)
            if revision is None:
                raise FileNotFoundError("Project not found")
            if "revision" in request:
                self._require_revision(request.get("revision"), revision.project_hash)
            self._read_project(project_id, revision_id=revision.revision_id, materialize=False)
            shared = self._guarded_shared_requests(project_id, revision.revision_id)
            return shared.link_project(self.identifier(request["work_id"]), project_id, reader)
        if action in {"prepare", "review", "publish"}:
            work_id = request.get("work_id")
            link = self.shared_requests.get_link(self.identifier(work_id))
            if not link:
                raise ValueError("Work has no linked studio project")
            visible_revision = self.stores.persistence.current(link["project_id"])
            if visible_revision is None:
                raise FileNotFoundError("Project not found")
            self._require_revision(request.get("revision"), visible_revision.project_hash)
            manifest = self._read_project_manifest(visible_revision)
            revision, workspace, _ = self._read_project(
                link["project_id"], revision_id=visible_revision.revision_id,
                manifest=manifest, materialize=False,
            )
            from .workflow import EXPORT_REVIEW_FILES

            for name in (*EXPORT_REVIEW_FILES, "chapter_narration.mp3"):
                relative = f"exports/{name}"
                entry = manifest.entries.get(relative)
                if entry is not None:
                    self._cache_entry(workspace, relative, entry)
            self._require_revision(request.get("revision"), revision.project_hash)
            shared = self._guarded_shared_requests(link["project_id"], revision.revision_id)
            return self._shared_export(action, request, workspace, link, reader, shared)
        from .shared_actions import metadata_action
        return metadata_action(self.shared_requests, request)

    def _guarded_shared_requests(self, project_id: str, revision_id: str):
        from .shared_firestore import FirestoreSharedMetadata, SharedProjectRevisionGuard

        revisions = self.stores.revisions
        guard = SharedProjectRevisionGuard(
            revisions._project(project_id), revision_id,
            binding_document=revisions.root,
            artifact_store_id=self.stores.artifacts.artifact_store_id,
            project_id=project_id,
        )
        metadata = FirestoreSharedMetadata(
            self.client, self.settings.dataset, self.stores.artifacts.artifact_store_id,
            project_guard=guard,
        )
        return SharedRequests(
            self.root / "shared-unused.sqlite3", metadata=metadata,
            artifacts=self.stores.shared_artifacts, intake_policy=self.shared_requests.intake_policy,
            clock=self.shared_requests.clock,
        )

    def _shared_export(self, action, request, workspace, link, actor, shared_requests):
        from .workflow import _export_snapshot
        snapshot = _export_snapshot(workspace, request["revision"], work_id=request["work_id"], link=link)
        if action == "prepare": return shared_requests.prepare_audio_review(snapshot, actor=actor)
        if action == "review": return shared_requests.approve_audio_review(snapshot, candidate_id=self.identifier(request["candidate_id"]), actor=actor)
        expected_publication = request.get("expected_publication")
        if expected_publication is not None:
            expected_publication = self.identifier(expected_publication)
        return shared_requests.publish_review(snapshot, review_id=self.identifier(request["review_id"]), actor=actor,
                                          expected_publication=expected_publication)

    def asset_path(self, project_id: str, relative: str) -> Path:
        self.identifier(project_id)
        if relative == "bundle.zip":
            current = self.stores.persistence.current(project_id)
            if current is None:
                raise FileNotFoundError("Project not found")
            for snapshot in self.operations.root.collection("operations").where("project_id", "==", project_id).limit(100).stream():
                operation = self.operations.get(snapshot.id)
                result = operation.result or {}
                if (operation.status == "complete" and operation.payload.get("action") == "bundle"
                        and result.get("project_revision_id") == current.revision_id
                        and isinstance(result.get("bundle_artifact"), dict)):
                    ref = ArtifactRef(**result["bundle_artifact"])
                    target = self._cache_dir("bundles", project_id, current.revision_id) / "bundle.zip"
                    if not target.is_file() or target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != ref.sha256:
                        self.stores.artifacts.copy_to(ref, target)
                    return target
            raise FileNotFoundError("Current project bundle is unavailable")
        path = self._safe_name(relative)
        if path.parts[0] not in {"input", "originals", "references", "takes", "exports"}:
            raise ValueError("Asset path is not readable")
        revision = self.stores.persistence.current(project_id)
        if revision is None:
            raise FileNotFoundError("Asset not found")
        manifest = self.stores.persistence.read_manifest(revision.manifest)
        entry = manifest.entries.get(path.as_posix())
        if entry is None:
            raise FileNotFoundError("Asset not found")
        workspace = self._cache_dir("projects", project_id, revision.revision_id)
        return self._cache_entry(workspace, path.as_posix(), entry)

    def published_path(self, work_id: str, publication_id: str | None = None) -> Path:
        publication = self.shared_requests.publication(self.identifier(work_id))
        if not publication or (publication_id and publication["id"] != self.identifier(publication_id)):
            raise FileNotFoundError("Publication not found")
        return self.shared_requests.published_artifact(work_id, "chapter_narration.wav", publication["id"])

    def candidate_path(self, candidate_id: str) -> Path:
        return self.shared_requests.candidate_artifact(self.identifier(candidate_id), "chapter_narration.wav")
