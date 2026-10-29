"""Local Next.js bridge for reviewed Manga-TTS jobs. Never trusts client paths."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import psutil

from manga_tts import PipelineConfig, PipelineRouter, schemas, tts
from manga_tts.cli import recover_operation_lock, workspace_lock
from manga_tts.config import VOICES
from manga_tts.extraction import extract_chapter
from manga_tts.operations import (
    LocalOperationService,
    Operation,
    OperationClaim,
    OperationConflict,
    OperationStage,
    OperationStore,
    ReconciliationAction,
    SQLiteOperationStore,
    process_identity,
)
from manga_tts.resolution import page_image
from manga_tts.script import cast_signature, scene_signature
from manga_tts.shared_requests import ExportSnapshot
from manga_tts.storage import asset, digest, export_signature, read_json, write_json

from .paths import data_root

ROOT = data_root()

@dataclass
class WorkflowExecution:
    router: PipelineRouter
    request: dict[str, Any]
    progress: Callable[..., None]
    upload: Path
    operation: Operation | None
    before_provider: Callable[[], None] | None
    store: OperationStore | None = None
    data_root: Path = ROOT

    @property
    def command(self) -> dict[str, Any]:
        return self.request.get("command", {})


@dataclass(frozen=True)
class WorkflowAction:
    execute: Callable[[WorkflowExecution], dict[str, Any] | None]
    after: Callable[[WorkflowExecution], None] | None = None


def _create_project(context: WorkflowExecution) -> dict[str, Any]:
    mode = context.request.get("mode")
    if mode == "restore":
        context.router.restore_project(context.upload / "chapter.zip")
    else:
        chapter = context.upload / "chapter.zip"
        if mode == "images":
            images = [asset(context.upload, name) for name in context.request["images"]]
            extract_chapter(
                images,
                chapter,
                device="auto",
                order="model" if context.request.get("direction") == "rtl" else "ltr",
                progress=context.progress,
            )
        elif mode != "chapter":
            raise ValueError("Choose images, chapter input or project restore")
        cast = context.upload / "cast.zip"
        context.router.create_project(chapter, cast if cast.exists() else None)
    return {}


def _rename_project(context: WorkflowExecution) -> None:
    title = context.command.get("title")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120 or any(ord(c) < 32 for c in title):
        raise ValueError("Enter a project title between 1 and 120 characters, without control characters.")
    context.router.update_metadata({"title": title.strip()})


def _import_cast(context: WorkflowExecution) -> None:
    context.router.import_cast(context.upload / "cast.zip")


def _create_cast_member(context: WorkflowExecution) -> None:
    context.router.create_cast_member(schemas.CastCreate.model_validate(context.command))


def _plan_proposal(context: WorkflowExecution) -> None:
    context.router.generate_proposal(
        progress=lambda event: _report_progress(context, event),
        before_provider=context.before_provider,
    )


def _apply_proposal(context: WorkflowExecution) -> None:
    context.router.apply_proposal(schemas.Proposal.model_validate(context.command))


def _sync_speakers(context: WorkflowExecution) -> None:
    if context.command.get("scenes"):
        review = schemas.SceneBatchReview.model_validate(context.command)
        review = review.model_copy(
            update={"scenes": [scene.model_copy(update={"approve": False}) for scene in review.scenes]}
        )
        context.router.apply_scene_reviews(review)
    else:
        context.router.sync_cast_speakers()


def _typed_command(contract: Any, method_name: str) -> Callable[[WorkflowExecution], None]:
    def apply(context: WorkflowExecution) -> None:
        method = getattr(context.router, method_name)
        method(contract.model_validate(context.command))

    return apply


def _report_progress(context: WorkflowExecution, event: Any) -> None:
    context.progress(
        event.message,
        stage=event.stage,
        status=event.status,
        scene_id=event.scene_id,
        segment_id=event.segment_id,
    )


def _inspect_segments(context: WorkflowExecution) -> dict[str, Any]:
    return {
        "segments": [
            schemas.dump(segment)
            for segment in context.router.inspect_segments(
                schemas.RenderSelection.model_validate(context.command)
            )
        ]
    }


def _render_segments(context: WorkflowExecution) -> dict[str, Any]:
    command = schemas.RenderCommand.model_validate(context.command)
    if context.operation is not None:
        operation = context.operation
        store = context.store if context.store is not None else operation_store()
        claim = OperationClaim(operation.operation_id, operation.fence)
        checkpoint = dict(operation.checkpoint or {})
        data = schemas.dump(context.router.project)
        if "baseline_take_ids" not in checkpoint:
            # Record pre-existing takes before synthesis. A retry can then identify
            # replacements committed even if the progress notification was lost.
            checkpoint["baseline_take_ids"] = [
                take["take_id"] for group in data["takes"].values() for take in group
            ]
            checkpoint["project_hash"] = digest(data)
            store.heartbeat(claim, checkpoint=checkpoint)
        baseline = set(checkpoint["baseline_take_ids"])
        accepted = {
            key.split(":", 1)[0]
            for key, take_id in data["selected_takes"].items()
            if take_id not in baseline
        }
        command = command.model_copy(update={
            "regenerate": [segment_id for segment_id in command.regenerate if segment_id not in accepted],
        })
    result = context.router.render_selected(
        command,
        progress=lambda event: _report_progress(context, event),
        before_provider=context.before_provider,
    )
    return {"segments": [schemas.dump(segment) for segment in result.segments]}


def _export_audio(context: WorkflowExecution) -> None:
    context.router.export_audio(
        schemas.RenderSelection.model_validate(context.command),
        mp3=context.request.get("mp3") is True,
    )


def _bundle_project(context: WorkflowExecution) -> None:
    context.router.bundle_project(context.data_root / "downloads" / (context.request["project"] + ".zip"))


def _record_source_review(context: WorkflowExecution) -> None:
    data = schemas.dump(context.router.project)
    context.router.update_metadata({"source_review_signature": source_signature(data)})


def _record_proposal_application(context: WorkflowExecution) -> None:
    data = schemas.dump(context.router.project)
    context.router.update_metadata(
        {"proposal_applied_signature": digest(data["proposal"]), "source_review_signature": None}
    )


WORKFLOW_ACTIONS = {
    "create": WorkflowAction(_create_project),
    "rename": WorkflowAction(_rename_project),
    "cast-import": WorkflowAction(_import_cast),
    "cast-create": WorkflowAction(_create_cast_member),
    "plan": WorkflowAction(_plan_proposal),
    "proposal": WorkflowAction(_apply_proposal, _record_proposal_application),
    "cast": WorkflowAction(_typed_command(schemas.CastReview, "apply_cast_review")),
    "sources": WorkflowAction(_typed_command(schemas.SourceReview, "apply_source_review"), _record_source_review),
    "script": WorkflowAction(_typed_command(schemas.SceneReview, "apply_scene_review")),
    "script-batch": WorkflowAction(_typed_command(schemas.SceneBatchReview, "apply_scene_reviews")),
    "sync-speakers": WorkflowAction(_sync_speakers),
    "settings": WorkflowAction(_typed_command(schemas.SettingsUpdate, "update_settings")),
    "narration": WorkflowAction(_typed_command(schemas.NarrationInsert, "insert_narration")),
    "take": WorkflowAction(_typed_command(schemas.TakeSelection, "select_take")),
    "inspect": WorkflowAction(_inspect_segments),
    "render": WorkflowAction(_render_segments),
    "export": WorkflowAction(_export_audio),
    "bundle": WorkflowAction(_bundle_project),
}


def operation_store() -> SQLiteOperationStore:
    return SQLiteOperationStore(ROOT / "operations.sqlite3")


def operation_pipeline_config(workspace: Path) -> PipelineConfig:
    """Leave all retries to the operation store, the single durable retry authority."""
    config = PipelineConfig.from_environment(workspace)
    return config.model_copy(update={"max_attempts": 1})


def _source_file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def operation_source_fingerprint(request: dict[str, Any], *, root: Path | None = None) -> str:
    """Fingerprint staged upload bytes and project visual evidence used by queued work."""
    root = ROOT if root is None else root
    upload_token = request.get("upload_token")
    expected_hashes = request.get("source_hashes", [])
    actual_hashes = []
    if upload_token is not None:
        upload = root / "uploads" / identifier(upload_token)
        action = request.get("action")
        if action == "create" and request.get("mode") == "images":
            names = list(request.get("images", []))
        elif action == "create":
            names = ["chapter.zip"]
        elif action == "cast-import":
            names = ["cast.zip"]
        elif action == "ocr":
            names = ["panel.png"]
        else:
            raise ValueError("Unexpected upload for this workflow action")
        if action == "create" and (upload / "cast.zip").is_file():
            names.append("cast.zip")
        for name in names:
            source = asset(upload, name)
            source_hash = _source_file_hash(source)
            if source_hash is None:
                raise ValueError("A staged source file is missing")
            actual_hashes.append(source_hash)
        if actual_hashes != expected_hashes:
            raise ValueError("Staged source files changed after upload validation")
    elif expected_hashes:
        raise ValueError("Source fingerprints require staged upload files")

    workspace = root / "projects" / identifier(request["project"])
    project_path = workspace / "project.json"
    evidence = []
    action = request.get("action")
    if project_path.is_file() and action in {"plan", "cast", "cast-create"}:
        project = read_json(project_path)
        if action == "plan":
            for page in project.get("chapter", {}).get("pages", []):
                try:
                    source, _ = page_image(project, workspace, page)
                except ValueError:
                    evidence.append({"page_id": page.get("page_id"), "missing": True})
                else:
                    evidence.append(
                        {
                            "page_id": page.get("page_id"),
                            "path": str(source.relative_to(workspace)),
                            "sha256": _source_file_hash(source),
                        }
                    )
            for speaker_id in sorted(project.get("cast", {})):
                for reference in project["cast"][speaker_id].get("references", []):
                    source = asset(workspace, reference)
                    evidence.append(
                        {
                            "speaker_id": speaker_id,
                            "path": reference,
                            "sha256": _source_file_hash(source),
                        }
                    )
            appearance_ids = [item["char_id"] for item in project.get("appearances", [])]
        elif action == "cast-create":
            appearance_ids = [request.get("command", {}).get("char_id")]
        else:
            additions = request.get("command", {}).get("new_characters", [])
            appearance_ids = [item.get("char_id") for item in additions if isinstance(item, dict)]

        for char_id in appearance_ids:
            appearance = next(
                (item for item in project.get("appearances", []) if item.get("char_id") == char_id),
                None,
            )
            if appearance is None:
                evidence.append({"char_id": char_id, "missing": True})
                continue
            relative = "input/" + appearance["crop_path"]
            source = asset(workspace, relative)
            evidence.append(
                {
                    "char_id": char_id,
                    "path": relative,
                    "sha256": _source_file_hash(source),
                }
            )
    return digest({"uploads": actual_hashes, "project_evidence": evidence})


def verify_operation_sources(operation: Operation, request: dict[str, Any], *, root: Path | None = None) -> None:
    try:
        current_fingerprint = operation_source_fingerprint(request, root=root)
    except (OSError, ValueError):
        current_fingerprint = None
    if current_fingerprint != operation.source_fingerprint:
        raise schemas.WorkflowError(
            schemas.Failure(
                code="source_conflict",
                stage="persistence",
                message="Pinned source evidence changed before execution. Enqueue a new operation.",
            )
        )


def enqueue_operation(request: dict, idempotency_key: str) -> Operation:
    """Persist server-owned workflow parameters before returning an operation ID."""
    if not isinstance(request, dict) or request.get("action") not in WORKFLOW_ACTIONS:
        raise ValueError("Unknown workflow action")
    project = identifier(request.get("project"))
    action = request["action"]
    if action == "create":
        if request.get("mode") not in {"images", "chapter", "restore"}:
            raise ValueError("Unknown project creation mode")
    elif request.get("revision") is not None and not isinstance(request["revision"], str):
        raise ValueError("Invalid project revision")
    upload_token = request.get("upload_token")
    if upload_token is not None:
        identifier(upload_token)
    payload = dict(request)
    semantic_payload = {key: value for key, value in payload.items() if key != "upload_token"}
    if action == "create":
        # Project and upload IDs are generated per HTTP attempt; the source bytes and
        # import configuration identify the user intent across a lost response.
        semantic_payload.pop("project", None)
    source_hashes = payload.get("source_hashes", [])
    if not isinstance(source_hashes, list) or any(
        not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
        for value in source_hashes
    ):
        raise ValueError("Invalid source fingerprints")
    stage: OperationStage = "magi" if action == "create" and request.get("mode") == "images" else "pipeline"
    configuration = {
        key: payload.get(key)
        for key in ("mode", "direction", "mp3")
        if key in payload
    }
    command = payload.get("command")
    if isinstance(command, dict) and "settings" in command:
        configuration["settings"] = command["settings"]
    return operation_store().enqueue(
        idempotency_key=idempotency_key,
        payload=payload,
        project_id=project,
        stage=stage,
        revision=payload.get("revision"),
        source_fingerprint=operation_source_fingerprint(payload),
        configuration_fingerprint=digest(configuration),
        request_fingerprint=digest(semantic_payload),
    )


def enqueue_request_file(token: str, idempotency_key: str) -> dict:
    token = identifier(token)
    request_path = ROOT / "requests" / f"{token}.json"
    try:
        operation = enqueue_operation(read_json(request_path), idempotency_key)
    finally:
        request_path.unlink(missing_ok=True)
    return {
        "operation": operation.public(),
        "stored_upload_token": operation.payload.get("upload_token"),
    }


def claim_next_operation() -> OperationClaim | None:
    store = operation_store()
    service = LocalOperationService(store)
    service.reconcile_expired(recover_operation_workspace)
    return store.claim_next()


def recover_operation_workspace(operation: Operation) -> bool:
    """Release a stale project lock only when it names this stopped operation fence."""
    if operation.worker_pid is None or operation.worker_created_at is None:
        return True
    workspace = ROOT / "projects" / operation.project_id
    recovered = recover_operation_lock(
        workspace,
        operation.operation_id,
        operation.fence,
        operation.worker_pid,
        operation.worker_created_at,
    )
    if recovered and operation.payload.get("action") == "render" and (workspace / "project.json").is_file():
        project_hash = digest(read_json(workspace / "project.json"))
        operation_store().record_recovery_checkpoint(
            OperationClaim(operation.operation_id, operation.fence), project_hash
        )
    return recovered


def operation_status(operation_id: str) -> dict | None:
    try:
        return operation_store().get(identifier(operation_id)).public()
    except FileNotFoundError:
        return None


def operation_by_key(idempotency_key: str) -> dict | None:
    try:
        return operation_store().get_by_key(idempotency_key).public()
    except FileNotFoundError:
        return None


def reconcile_operation(
    operation_id: str,
    action: str,
    worker_stopped_confirmed: bool = False,
) -> Operation:
    """Resolve an uncertain operation only after its local worker has stopped."""
    if action not in {"fail", "retry"}:
        raise ValueError("Choose fail or retry")
    resolution = cast(ReconciliationAction, action)
    store = operation_store()
    operation = store.get(identifier(operation_id))
    if operation.status != "reconciliation_required":
        raise OperationConflict("invalid_transition", "Operation does not need reconciliation.")
    if operation.worker_pid is not None and operation.worker_created_at is not None:
        state = process_identity(operation.worker_pid, operation.worker_created_at)
        if state is True:
            raise OperationConflict("worker_active", "Worker is still active; wait before resolving this operation.")
        if state is None and not worker_stopped_confirmed:
            raise OperationConflict("worker_unknown", "Worker identity cannot be confirmed; capacity remains reserved.")
        workspace = ROOT / "projects" / operation.project_id
        if not recover_operation_lock(
            workspace,
            operation.operation_id,
            operation.fence,
            operation.worker_pid,
            operation.worker_created_at,
            worker_stopped_confirmed=worker_stopped_confirmed and state is None,
        ):
            raise OperationConflict("workspace_lock_unverified", "Workspace lock ownership could not be verified safely.")
        if operation.payload.get("action") == "render" and (workspace / "project.json").is_file():
            store.record_recovery_checkpoint(
                OperationClaim(operation.operation_id, operation.fence),
                digest(read_json(workspace / "project.json")),
            )
    return store.resolve_uncertain(operation.operation_id, resolution)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Invalid project or job identifier")
    return value


def link_shared_project(store, work_id, project_id, actor):
    """Link approved work only to an existing, valid local studio project."""
    project_id = identifier(project_id)
    projects = (ROOT / "projects").resolve()
    workspace = projects / project_id
    if workspace.is_symlink() or not (workspace / "project.json").is_file():
        raise ValueError("Studio project not found")
    with workspace_lock(workspace):
        router = PipelineRouter(operation_pipeline_config(workspace))
        router.load_project()
        return store.link_project(work_id, project_id, actor)


def _export_snapshot(workspace, expected_revision, *, work_id, link):
    """Resolve current export metadata and files while the workspace lock is held."""
    router = PipelineRouter(operation_pipeline_config(workspace))
    router.load_project()
    data = schemas.dump(router.project)
    revision = digest(data)
    if revision != expected_revision:
        raise ValueError("Project revision changed; reload before reviewing")
    export_id = data.get("web_export_id")
    if not export_id or not workflow_status(data, workspace)["exported_scenes"]:
        raise ValueError("Current export is unavailable; export the reviewed project first")
    names = ["chapter_narration.wav", "timeline.json", "cast.json", "approved_script.json", "render_manifest.json"]
    if (workspace / "exports" / "chapter_narration.mp3").is_file():
        names.append("chapter_narration.mp3")
    artifacts = {}
    for name in names:
        path = workspace / "exports" / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Export artifact is unavailable")
        artifacts[name] = asset(workspace, f"exports/{name}")
    return ExportSnapshot(work_id=work_id, link_id=link["id"], project_id=link["project_id"],
                          revision=revision, export_id=export_id, settings_hash=digest(data["settings"]),
                          artifacts=artifacts)


@contextmanager
def _locked_shared_export(store, work_id, expected_revision):
    """Hold the project lock through inspection and the caller's store mutation."""
    link = store.get_link(work_id)
    if not link:
        raise ValueError("Work has no linked studio project")
    project_id = identifier(link["project_id"])
    workspace = (ROOT / "projects").resolve() / project_id
    if workspace.is_symlink() or not (workspace / "project.json").is_file():
        raise ValueError("Studio project not found")
    with workspace_lock(workspace):
        yield _export_snapshot(workspace, expected_revision, work_id=work_id, link=link)


def prepare_shared_export(store, work_id, actor, expected_revision):
    """Prepare a current immutable export snapshot for an administrator to inspect."""
    with _locked_shared_export(store, work_id, expected_revision) as snapshot:
        return store.prepare_audio_review(snapshot, actor=actor)


def approve_shared_export(store, work_id, candidate_id, actor, expected_revision):
    """Record a human decision against the prepared, still-current export."""
    with _locked_shared_export(store, work_id, expected_revision) as snapshot:
        return store.approve_audio_review(snapshot, candidate_id=candidate_id, actor=actor)


def publish_shared_export(store, work_id, review_id, actor, expected_revision, expected_publication):
    """Publish only a reviewed export that still matches the locked studio project."""
    with _locked_shared_export(store, work_id, expected_revision) as snapshot:
        return store.publish_review(snapshot, review_id=review_id, actor=actor,
                                    expected_publication=expected_publication)


def source_signature(data):
    return digest({key: data.get(key) for key in ("sources", "page_order", "panel_order")})


def workflow_status(data, root):
    ready = []
    for scene in data["scenes"]:
        try:
            segments = tts.compile_segments(data, scene)
            if not segments:
                continue
            for segment in segments:
                selected = data["selected_takes"].get(tts.selection_key(segment))
                take = next((t for t in data["takes"].get(segment["signature"], []) if t["take_id"] == selected), None)
                if not take or hashlib.sha256(asset(root, take["path"]).read_bytes()).hexdigest() != take["audio_sha256"]:
                    break
            else:
                ready.append(scene["scene_id"])
        except (ValueError, OSError):
            continue
    exported = data.get("web_export_scenes", []) if data.get("web_export_signature") == export_signature(data) and (root / "exports/chapter_narration.wav").is_file() else []
    return {"sources_reviewed": bool(data["sources"]) and data.get("source_review_signature") == source_signature(data),
            "proposal_applied": bool(data["proposal"]) and data.get("proposal_applied_signature") == digest(data["proposal"]),
            "audio_ready_scenes": ready, "exported_scenes": exported}


def snapshot(router):
    data = schemas.dump(router.project)
    pages = []
    for page in data["chapter"]["pages"]:
        candidates = [f"originals/{page.get('image_filename', '')}", f"input/{page.get('image_filename', '')}"]
        original = next((p for p in candidates if asset(router.root, p).is_file()), None)
        annotated = f"input/previews/page_{page['page_index']:03d}_annotated.jpg"
        annotated = annotated if asset(router.root, annotated).is_file() else None
        pages.append({**page, "preview_path": original or annotated,
                      "original_path": original, "annotated_path": annotated})
    exports = [p.name for p in (router.root / "exports").glob("*") if p.is_file() and p.suffix in {".wav", ".mp3", ".json"}]
    order = data.get("page_order") or [p["page_id"] for p in pages]
    pages.sort(key=lambda page: order.index(page["page_id"]) if page["page_id"] in order else len(order))
    for page in pages:
        panel_order = data.get("panel_order", {}).get(page["page_id"])
        if panel_order:
            page["panels"] = sorted(page.get("panels", []), key=lambda panel: panel_order.index(panel["panel_id"]))
    return {"project": data, "revision": digest(data), "pages": pages, "voices": VOICES,
            "cast_approved": data["cast_approval"] == cast_signature(data),
            "approved_scenes": [s["scene_id"] for s in data["scenes"] if data["approvals"].get(s["scene_id"]) == scene_signature(data, s)],
            "workflow_status": workflow_status(data, router.root), "exports": exports, "has_api_key": bool(os.environ.get("GEMINI_API_KEY"))}


def perform(router, request, progress, *, operation: Operation | None = None, before_provider=None,
            store: OperationStore | None = None, root: Path | None = None):
    action = request["action"]
    handler = WORKFLOW_ACTIONS.get(action)
    if handler is None:
        raise ValueError("Unknown workflow action")
    root = ROOT if root is None else root
    upload = root / "uploads" / identifier(request["job"])
    context = WorkflowExecution(router, request, progress, upload, operation, before_provider, store, root)
    if action != "create":
        router.load_project()
        current_revision = digest(schemas.dump(router.project))
        checkpoint_revision = operation.checkpoint.get("project_hash") if operation and operation.checkpoint else None
        is_checkpoint_resume = action in {"render", "plan"} and checkpoint_revision == current_revision
        if request.get("revision") != current_revision and not is_checkpoint_resume:
            raise schemas.WorkflowError(schemas.Failure(
                code="revision_conflict", stage="persistence",
                message="This project changed in another session. Reload before applying your edits.",
            ))
        if (action == "plan" and is_checkpoint_resume and operation and operation.checkpoint
                and operation.checkpoint.get("planning_complete")):
            return {}
    result = handler.execute(context)
    if handler.after is not None:
        handler.after(context)
    return result or {}


def run_job(job):
    job = identifier(job)
    status_path = ROOT / "jobs" / (job + ".json")
    request = read_json(ROOT / "jobs" / (job + ".request.json"))
    project = identifier(request["project"])
    request["job"] = job
    def update(message, status="running", **extra):
        write_json(status_path, {"id": job, "project": project, "status": status, "message": message, **extra})
    def legacy_progress(message, **_details):
        update(message)
    try:
        update("Preparing workspace…")
        with workspace_lock(ROOT / "projects" / project):
            router = PipelineRouter(PipelineConfig.from_environment(ROOT / "projects" / project))
            result = perform(router, request, legacy_progress)
        update("Ready for review.", "complete", result=result)
    except schemas.WorkflowError as exc:
        update(exc.detail.message, "failed", failure_code=exc.detail.code)
    except schemas.ValidationError as exc:
        fields = [".".join(map(str, e["loc"])) for e in exc.errors(include_input=False, include_context=False)]
        update("Invalid review fields: " + ", ".join(fields), "failed")
    except (ValueError, FileNotFoundError) as exc:
        # Only local workflow errors; provider errors are sanitized by the router.
        update(str(exc)[:400], "failed")
    except Exception:  # noqa: BLE001 - persist a safe terminal job result for unknown failures.
        update("Operation failed. Check dependencies and workspace access. Completed audio is retained.", "failed")
    finally:
        # Uploaded staging files are not needed once imported. Use only the fixed job directory.
        import shutil
        staging = ROOT / "uploads" / job
        if staging.exists():
            shutil.rmtree(staging)


def run_operation(operation_id: str, fence: int) -> None:
    """Execute one finite operation using only its persisted parameters and claim fence."""
    operation_id = identifier(operation_id)
    store = operation_store()
    operation = store.get(operation_id)
    claim = OperationClaim(operation_id, fence)
    try:
        process = psutil.Process()
        operation = store.register_worker(claim, process.pid, process.create_time())
    except OperationConflict:
        return

    request = dict(operation.payload)
    request["job"] = request.get("upload_token") or operation.operation_id
    stop_heartbeat = threading.Event()

    def heartbeat_loop() -> None:
        deadline = time.monotonic() + store.policy.attempt_timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                try:
                    store.heartbeat(
                        claim,
                        progress={"message": "Attempt timed out; waiting for safe reconciliation."},
                    )
                except OperationConflict:
                    return
                psutil.Process().terminate()
                return
            if stop_heartbeat.wait(min(store.policy.heartbeat_seconds, remaining)):
                return
            try:
                store.heartbeat(claim)
            except OperationConflict:
                return

    heartbeat = threading.Thread(target=heartbeat_loop, name=f"operation-{operation_id[:8]}-lease", daemon=True)
    heartbeat.start()

    def progress(message: str, **details: Any) -> None:
        checkpoint = None
        planning_complete = details.get("stage") == "planning" and details.get("status") == "complete"
        if planning_complete or details.get("status") in {"saved", "reused"} and details.get("segment_id"):
            project_path = ROOT / "projects" / operation.project_id / "project.json"
            if project_path.is_file():
                checkpoint = {**(store.get(operation_id).checkpoint or {}),
                    "operation_id": operation_id,
                    "project_hash": digest(read_json(project_path)),
                    "segment_id": details["segment_id"],
                }
                if planning_complete:
                    checkpoint["planning_complete"] = True
        provider_result_checkpointed = (
            details.get("status") == "saved"
            or planning_complete
        )
        store.heartbeat(
            claim,
            progress={"message": message, **details},
            checkpoint=checkpoint,
            provider_result_checkpointed=provider_result_checkpointed,
        )

    def before_provider() -> None:
        store.mark_provider_call_pending(claim)

    def fail(message: str, code: str, *, retryable: bool = False) -> None:
        try:
            store.fail(claim, message, code, retryable=retryable)
        except OperationConflict:
            pass

    try:
        progress("Preparing workspace…")
        workspace = ROOT / "projects" / operation.project_id
        with workspace_lock(workspace, operation_id=operation_id, fence=fence):
            verify_operation_sources(operation, request)
            approval_context = None
            if request.get("actor") is not None:
                approval_context = schemas.ApprovalContext(
                    actor=schemas.ApprovalActor.model_validate(request["actor"]),
                    operation_id=operation_id,
                    reviewed_revision=operation.revision or "new-project",
                )
            router = PipelineRouter(operation_pipeline_config(workspace), approval_context=approval_context)
            result = perform(
                router,
                request,
                progress,
                operation=operation,
                before_provider=before_provider,
            )
        store.complete(claim, result)
        upload_token = request.get("upload_token")
        if upload_token:
            shutil.rmtree(ROOT / "uploads" / identifier(upload_token), ignore_errors=True)
    except schemas.WorkflowError as exc:
        fail(exc.detail.message, exc.detail.code, retryable=exc.detail.retryable)
    except schemas.ValidationError as exc:
        fields = [".".join(map(str, error["loc"])) for error in exc.errors(include_input=False, include_context=False)]
        fail("Invalid review fields: " + ", ".join(fields), "invalid_command")
    except (ValueError, FileNotFoundError) as exc:
        fail(str(exc)[:400], "invalid_operation")
    except Exception:  # noqa: BLE001 - persist a safe terminal or uncertain outcome.
        fail(
            "Operation failed. Check dependencies and workspace access. Completed audio is retained.",
            "operation_failed",
        )
    finally:
        stop_heartbeat.set()
        heartbeat.join(timeout=1)


def _spawn_worker(operation_id: str, fence: int) -> None:
    command = [sys.executable, "-m", "manga_worker.workflow", "run", operation_id, str(fence)]
    options: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": ROOT,
        "env": {**os.environ, "MANGA_DATA_ROOT": str(ROOT)},
        "close_fds": True,
    }
    if os.name == "nt":
        options["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    else:
        options["start_new_session"] = True
    subprocess.Popen(command, **options)


def main():
    if len(sys.argv) == 2 and sys.argv[1] in {"--help", "-h"}:
        print("Usage: manga-worker {snapshot,enqueue,claim-next,run,status,lookup-key,reconcile,job} ...")
        return
    if len(sys.argv) < 2:
        raise ValueError("Unknown bridge command")
    action = sys.argv[1]
    if action == "job":
        run_job(sys.argv[2])
    elif action == "snapshot":
        value = sys.argv[2]
        with workspace_lock(ROOT / "projects" / identifier(value)):
            router = PipelineRouter(PipelineConfig.from_environment(ROOT / "projects" / value))
            router.load_project()
            print(json.dumps(snapshot(router), ensure_ascii=False))
    elif action == "enqueue":
        try:
            print(json.dumps(enqueue_request_file(sys.argv[2], sys.argv[3]), ensure_ascii=False))
        except OperationConflict as exc:
            print(json.dumps({"error": str(exc), "code": exc.code}, ensure_ascii=False))
    elif action == "claim-next":
        claim = claim_next_operation()
        print(json.dumps({"id": claim.operation_id, "fence": claim.fence} if claim else None))
    elif action == "run":
        run_operation(identifier(sys.argv[2]), int(sys.argv[3]))
    elif action == "status":
        print(json.dumps(operation_status(sys.argv[2]), ensure_ascii=False))
    elif action == "lookup-key":
        print(json.dumps(operation_by_key(sys.argv[2]), ensure_ascii=False))
    elif action == "reconcile":
        operation_id, resolution = sys.argv[2], sys.argv[3]
        options = sys.argv[4:]
        if any(option != "--worker-stopped" for option in options):
            raise ValueError("Unknown reconciliation option")
        operation = reconcile_operation(
            operation_id,
            resolution,
            worker_stopped_confirmed="--worker-stopped" in options,
        )
        if resolution == "retry":
            claim = operation_store().claim(operation.operation_id)
            if claim is not None:
                _spawn_worker(claim.operation_id, claim.fence)
        print(json.dumps(operation.public(), ensure_ascii=False))
    else:
        raise ValueError("Unknown bridge command")


if __name__ == "__main__":
    try:
        main()
    except OperationConflict as exc:
        print(f"{exc.code}: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from None
