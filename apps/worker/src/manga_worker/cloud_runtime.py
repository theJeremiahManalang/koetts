"""Finite Cloud Run worker entrypoint for one fenced hosted operation."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import tempfile
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from manga_tts import PipelineRouter, schemas
from manga_tts.operations import OperationClaim, OperationConflict
from manga_tts.persistence import ArtifactRef
from manga_tts.storage import digest, read_json

from .cloud import CloudSettings, cloud_stores
from .workflow import operation_pipeline_config, perform, verify_operation_sources


_SAFE_UPLOAD_NAME = re.compile(r"[A-Za-z0-9._/-]{1,240}\Z")


class CloudRuntime:
    """Run one persisted operation in private scratch with cloud-backed durability."""

    def __init__(
        self,
        store,
        persistence,
        artifacts,
        root: Path,
        *,
        router_factory: Callable[..., Any] | None = None,
        perform_operation: Callable[..., dict] = perform,
        extractor: Callable[[Path], Any] | None = None,
        source_verifier: Callable[..., None] = verify_operation_sources,
        stop_process: Callable[[], None] | None = None,
    ):
        self.store = store
        self.persistence = persistence
        self.artifacts = artifacts
        self.root = Path(root)
        self.router_factory = router_factory or self._router
        self.perform_operation = perform_operation
        self.extractor = extractor or self._extract_text
        self.source_verifier = source_verifier
        self.stop_process = stop_process or self._terminate

    @staticmethod
    def _extract_text(image: Path):
        """Load the optional OCR stack only when a hosted OCR job runs."""
        from .extract import extract_text

        return extract_text(image)

    @staticmethod
    def _terminate() -> None:
        os.kill(os.getpid(), signal.SIGTERM)

    @staticmethod
    def _router(workspace: Path, writer, request: dict):
        approval_context = None
        actor = request.get("actor")
        if actor is not None:
            approval_context = schemas.ApprovalContext(
                actor=schemas.ApprovalActor.model_validate(actor),
                operation_id=request["operation_id"],
                reviewed_revision=request.get("revision") or "new-project",
            )
        return PipelineRouter(
            operation_pipeline_config(workspace),
            persistence=writer,
            approval_context=approval_context,
        )

    @staticmethod
    def _safe_upload_path(name: str) -> PurePosixPath:
        if (not isinstance(name, str) or not _SAFE_UPLOAD_NAME.fullmatch(name)
                or "\\" in name or name.startswith("/") or ":" in name):
            raise ValueError("Hosted upload manifest contains an invalid filename")
        path = PurePosixPath(name)
        if path.as_posix() != name or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("Hosted upload manifest contains an invalid filename")
        return path

    def _materialize_uploads(self, operation, request: dict, attempt_root: Path) -> None:
        uploads = operation.payload.get("cloud_uploads", {})
        if not isinstance(uploads, dict):
            raise ValueError("Hosted upload manifest is invalid")
        token = request.get("upload_token") or operation.operation_id
        if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("Hosted upload identity is invalid")
        upload_root = attempt_root / "uploads" / token
        upload_root.mkdir(parents=True, exist_ok=True)
        for name, raw_ref in uploads.items():
            relative = self._safe_upload_path(name)
            if not isinstance(raw_ref, dict):
                raise ValueError("Hosted upload reference is invalid")
            ref = ArtifactRef(**raw_ref)
            destination = upload_root.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.artifacts.copy_to(ref, destination)
            if destination.is_symlink() or not destination.is_file():
                raise ValueError("Hosted upload materialization failed")

    @staticmethod
    def _restore_project(operation, writer, workspace: Path):
        revision = writer.load(workspace)
        pinned = operation.payload.get("project_revision_id")
        checkpoint = operation.checkpoint or {}
        if pinned is not None and (not isinstance(pinned, str) or not pinned):
            raise ValueError("Pinned hosted project revision is invalid")
        if revision is None:
            if pinned is not None or checkpoint.get("project_hash"):
                raise ValueError("Pinned hosted project revision is unavailable")
        elif revision.revision_id != pinned:
            # A retry may use a later accepted checkpoint only when its
            # exact project hash still matches the durable operation record.
            if (not checkpoint.get("project_hash")
                    or checkpoint["project_hash"] != revision.project_hash
                    or (checkpoint.get("revision_id") is not None
                        and checkpoint["revision_id"] != revision.revision_id)):
                raise ValueError("Hosted project changed from the pinned starting revision")
        return revision

    def run(self, claim: OperationClaim, execution_name: str) -> bool:
        """Register and execute exactly one Cloud Run execution for a claim."""
        operation = self.store.get(claim.operation_id)
        if operation.fence != claim.fence or operation.status != "running":
            raise OperationConflict("stale_fence", "Operation fence is no longer current.")
        if (operation.operation_id != claim.operation_id
                or not re.fullmatch(r"[a-f0-9]{32}", operation.operation_id)
                or not re.fullmatch(r"[a-f0-9]{32}", operation.project_id)):
            raise OperationConflict("invalid_identity", "Hosted operation identity is invalid.")
        try:
            operation = self.store.register_execution(claim, execution_name)
        except OperationConflict as exc:
            if exc.code == "duplicate_worker":
                return False
            raise

        attempt_root = self.root / "attempts" / operation.operation_id / str(claim.fence)
        attempt_root.mkdir(parents=True, exist_ok=False)
        workspace = attempt_root / "projects" / operation.project_id
        request = dict(operation.payload)
        ocr = request.get("action") == "ocr"
        if ocr and operation.stage != "magi":
            self._finish_failure(claim, "Hosted OCR operation stage is invalid.", "invalid_payload")
            shutil.rmtree(attempt_root, ignore_errors=True)
            return True
        if not ocr:
            workspace.mkdir(parents=True)
        if request.get("project") not in (None, operation.project_id):
            self._finish_failure(claim, "Hosted request project does not match its operation.", "invalid_payload")
            shutil.rmtree(attempt_root, ignore_errors=True)
            return True
        request["project"] = operation.project_id
        request["operation_id"] = operation.operation_id
        request["job"] = request.get("upload_token") or operation.operation_id

        stop_heartbeat = threading.Event()
        fence_lost = threading.Event()

        def heartbeat_loop() -> None:
            deadline = time.monotonic() + self.store.policy.attempt_timeout_seconds
            interval = self.store.policy.heartbeat_seconds
            while not stop_heartbeat.wait(min(interval, max(0.0, deadline - time.monotonic()))):
                if time.monotonic() >= deadline:
                    try:
                        self.store.heartbeat(claim, progress={"message": "Attempt timed out; awaiting safe reconciliation."})
                    except Exception:
                        pass
                    self.stop_process()
                    return
                try:
                    self.store.heartbeat(claim)
                except Exception:
                    fence_lost.set()
                    self.stop_process()
                    return

        thread = threading.Thread(target=heartbeat_loop, name=f"cloud-op-{operation.operation_id[:8]}-lease", daemon=True)
        thread.start()
        writer = None
        writer_release_failed = False
        failure: tuple[str, str, bool] | None = None
        try:
            self._materialize_uploads(operation, request, attempt_root)
            if ocr:
                self.source_verifier(operation, request, root=attempt_root)
                token = request.get("upload_token")
                if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{32}", token):
                    raise OperationConflict("invalid_payload", "Hosted OCR upload identity is invalid.")
                image = attempt_root / "uploads" / token / "panel.png"
                if image.is_symlink() or not image.is_file():
                    raise OperationConflict("invalid_payload", "Hosted OCR image is unavailable.")
                try:
                    response = self.extractor(image)
                except Exception as exc:
                    raise OperationConflict("ocr_failed", "Hosted OCR failed.") from exc
                if (not isinstance(response, dict) or not isinstance(response.get("texts"), list)
                        or any(not isinstance(value, str) for value in response["texts"])):
                    raise OperationConflict("invalid_ocr_response", "OCR returned an invalid response.")
                if fence_lost.is_set():
                    raise OperationConflict("stale_fence", "Worker fence is no longer current.")
                stop_heartbeat.set()
                self.store.complete(claim, {"texts": response["texts"]})
                return True

            owner_id = f"hosted-{operation.operation_id}-{claim.fence}"
            writer = self.persistence.acquire(operation.project_id, owner_id)
            revision = self._restore_project(operation, writer, workspace)
            request["project_revision_id"] = revision.revision_id if revision is not None else None
            self.source_verifier(operation, request, root=attempt_root)

            def before_provider() -> None:
                if fence_lost.is_set():
                    raise OperationConflict("stale_fence", "Worker fence is no longer current.")
                current = self.persistence.current(operation.project_id)
                checkpoint = dict(self.store.get(operation.operation_id).checkpoint or {})
                checkpoint["provider_base_revision_id"] = current.revision_id if current else None
                self.store.heartbeat(claim, checkpoint=checkpoint)
                self.store.mark_provider_call_pending(claim)

            def progress(message: str, **details: Any) -> None:
                if fence_lost.is_set():
                    raise OperationConflict("stale_fence", "Worker fence is no longer current.")
                checkpoint = None
                planning_complete = details.get("stage") == "planning" and details.get("status") == "complete"
                accepted_segment = details.get("status") in {"saved", "reused"} and details.get("segment_id")
                provider_saved = details.get("status") == "saved" or planning_complete
                if planning_complete or accepted_segment:
                    local_project = workspace / "project.json"
                    if local_project.is_file():
                        current = self.persistence.current(operation.project_id)
                        project_hash = digest(read_json(local_project))
                        if current is not None and current.project_hash == project_hash:
                            checkpoint = dict(self.store.get(operation.operation_id).checkpoint or {})
                            checkpoint.update({
                                "operation_id": operation.operation_id,
                                "project_hash": project_hash,
                                "revision_id": current.revision_id,
                            })
                            if details.get("segment_id"):
                                checkpoint["segment_id"] = details["segment_id"]
                            if planning_complete:
                                checkpoint["planning_complete"] = True
                self.store.heartbeat(
                    claim,
                    progress={"message": message, **details},
                    checkpoint=checkpoint,
                    provider_result_checkpointed=bool(provider_saved and checkpoint is not None),
                )

            router = self.router_factory(workspace, writer, request)
            result = self.perform_operation(
                router,
                request,
                progress,
                operation=operation,
                before_provider=before_provider,
                store=self.store,
                root=attempt_root,
            )
            # Bundle output sits outside the project manifest; publish it as an
            # immutable artifact before the operation result references it.
            bundle = attempt_root / "downloads" / f"{operation.project_id}.zip"
            if bundle.is_file():
                result = dict(result)
                result["bundle_artifact"] = vars(self.artifacts.put_file(bundle))
            current = self.persistence.current(operation.project_id)
            if current is not None:
                result = dict(result)
                result["project_revision_id"] = current.revision_id
                result["project_hash"] = current.project_hash
            try:
                writer.release()
            except Exception:
                writer_release_failed = True
                raise
            writer = None
            # Successful completion invalidates the claim. Stop lease renewal
            # first so a concurrent heartbeat cannot terminate a completed job.
            stop_heartbeat.set()
            self.store.complete(claim, result)
            return True
        except schemas.WorkflowError as exc:
            failure = (exc.detail.message, exc.detail.code, exc.detail.retryable)
        except OperationConflict as exc:
            failure = (str(exc), exc.code, False)
        except (ValueError, FileNotFoundError) as exc:
            failure = (str(exc), "invalid_operation", False)
        except Exception:  # Provider and SDK text may include credentials or source content.
            failure = ("Operation failed. Completed durable work is retained.", "worker_failed", False)
        finally:
            if writer is not None and not writer_release_failed:
                try:
                    writer.release()
                except Exception:
                    writer_release_failed = True
            stop_heartbeat.set()
            thread.join(timeout=max(1.0, self.store.policy.heartbeat_seconds + 0.5))
            if writer_release_failed:
                try:
                    self.store.mark_uncertain(claim, "Project writer release could not be confirmed; reconcile after execution stops.")
                except OperationConflict:
                    pass
            elif failure is not None:
                self._finish_failure(claim, failure[0], failure[1], retryable=failure[2])
            shutil.rmtree(attempt_root, ignore_errors=True)
        return True

    def _finish_failure(self, claim, message: str, code: str, *, retryable: bool = False) -> None:
        try:
            self.store.fail(claim, message[:400], code, retryable=retryable)
        except OperationConflict:
            pass


def _execution_identity() -> tuple[str, str, str]:
    """Build canonical resource identity from explicit Cloud Run location values."""
    project = os.environ.get("CLOUD_RUN_PROJECT", "")
    location = os.environ.get("CLOUD_RUN_LOCATION", "")
    job = os.environ.get("CLOUD_RUN_JOB", "")
    execution = os.environ.get("CLOUD_RUN_EXECUTION", "")
    if not all((project, location, job, execution)):
        raise RuntimeError("Cloud Run project, location, job and execution identity are required")
    if any("/" in part for part in (project, location, job, execution)):
        raise RuntimeError("Cloud Run execution identity is invalid")
    return f"projects/{project}/locations/{location}/jobs/{job}/executions/{execution}", project, location


def main() -> int:
    """Container entrypoint; cloud execution has no SQLite or local fallback."""
    operation_id = os.environ.get("MANGA_OPERATION_ID", "")
    fence_text = os.environ.get("MANGA_OPERATION_FENCE", "")
    if not re.fullmatch(r"[a-f0-9]{32}", operation_id) or not fence_text.isdecimal() or int(fence_text) < 1:
        raise RuntimeError("Cloud Run operation identity is required")
    execution_name, project, _ = _execution_identity()
    from google.cloud import firestore, storage

    settings = CloudSettings.from_environment()
    if settings.project != project:
        raise RuntimeError("Cloud Run project does not match configured hosted storage")
    firestore_client = firestore.Client(project=settings.project, database=settings.database)
    storage_client = storage.Client(project=settings.project)
    stores = cloud_stores(
        settings,
        Path(tempfile.gettempdir()) / "manga-shared-cache",
        firestore_client=firestore_client,
        storage_client=storage_client,
    )
    from .cloud_operations import FirestoreOperationStore

    store = FirestoreOperationStore(firestore_client, settings.dataset, stores.artifacts.artifact_store_id)
    root = Path(os.environ.get("MANGA_DATA_ROOT", "/tmp/manga-cloud-runtime"))
    runtime = CloudRuntime(store, stores.persistence, stores.artifacts, root)
    runtime.run(OperationClaim(operation_id, int(fence_text)), execution_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
