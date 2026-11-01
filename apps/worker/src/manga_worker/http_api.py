"""Private S3 API. Hosted verification mode cannot access production workspaces."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import tempfile
import time
from pathlib import Path
import threading

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from manga_worker.http_auth import BoundaryConfig, CredentialBoundary
from manga_tts.schemas import WorkflowError
from manga_tts.operations import OperationConflict
from manga_tts.shared_requests import IntakeQuotaExceeded
from manga_worker.cloud_budget import CloudBudgetExceeded

PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
MAX_OPERATION_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON number")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON number")
    return number


async def _operation_request(request: Request):
    keys = request.headers.getlist("idempotency-key")
    if (len(keys) != 1 or not keys[0].strip() or len(keys[0]) > 200
            or any(ord(character) < 32 or ord(character) == 127 for character in keys[0])):
        raise HTTPException(400, "Idempotency-Key required (maximum 200 characters)")
    return keys[0], await _json_request(request)


async def _body_bytes(request: Request, limit: int):
    lengths = request.headers.getlist("content-length")
    if len(lengths) > 1 or (lengths and (not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 20)):
        raise HTTPException(400, "Invalid Content-Length")
    declared = int(lengths[0]) if lengths else None
    if declared is not None and declared > limit:
        raise HTTPException(413, "Operation request too large")
    try:
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > limit:
                raise HTTPException(413, "Operation request too large")
            body.extend(chunk)
        if declared is not None and declared != len(body):
            raise ValueError("Incomplete body")
        return body
    except (ValueError, ClientDisconnect):
        raise HTTPException(400, "Invalid request body") from None


async def _json_request(request: Request, limit=MAX_OPERATION_BYTES):
    content_types = request.headers.getlist("content-type")
    if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "Expected application/json")
    try:
        body = await _body_bytes(request, limit)
        payload = await run_in_threadpool(json.loads, body, object_pairs_hook=_unique_object,
                                          parse_constant=_reject_constant, parse_float=_finite_float)
        if not isinstance(payload, dict):
            raise TypeError("Invalid request")
    except (ValueError, TypeError, RecursionError, ClientDisconnect):
        raise HTTPException(400, "Invalid operation request") from None
    return payload


def create_app(
    config=None, *, service_verifier=None, user_verifier=None, workflow=None, coordinator=None, hosted=None,
    billing_config=None,
):
    config = config or BoundaryConfig.from_environment()
    boundary = CredentialBoundary(config, service_verifier, user_verifier)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    coordinator_instance = coordinator
    hosted_instance = hosted
    hosted_lock = threading.Lock()

    @app.middleware("http")
    async def private_response_headers(request, call_next):
        response = await call_next(request)
        response.headers.update(PRIVATE_HEADERS)
        return response

    def application():
        if config.mode != "local":
            raise HTTPException(503, "Hosted processing unavailable")
        if workflow is not None:
            return workflow
        from manga_worker import workflow as web_workflow

        return web_workflow

    def cloud_application():
        nonlocal hosted_instance
        if config.mode != "cloud":
            raise HTTPException(503, "Hosted processing unavailable")
        with hosted_lock:
            if hosted_instance is None:
                from .cloud import CloudSettings
                from .cloud_application import CloudApplication

                settings = CloudSettings.from_environment()
                if settings.project != config.project_id:
                    raise HTTPException(503, "Hosted project configuration mismatch")
                hosted_instance = CloudApplication(settings, cache_root=Path(tempfile.gettempdir()) / "manga-api-cache")
            return hosted_instance

    def workflow_application():
        return cloud_application() if config.mode == "cloud" else application()

    @app.exception_handler(WorkflowError)
    async def workflow_failure(request, exc):
        status = (
            409 if "conflict" in exc.detail.code or "stale" in exc.detail.code else 400
        )
        return JSONResponse(
            status_code=status, content={"error": exc.detail.model_dump()}
        )

    @app.exception_handler(Exception)
    async def safe_failure(request, exc):
        return JSONResponse(
            status_code=500, content={"error": "Workflow request failed"}, headers=PRIVATE_HEADERS,
        )

    @app.exception_handler(OperationConflict)
    async def operation_conflict(request, exc):
        return JSONResponse(status_code=409, content={"error": {"code": exc.code, "message": "Operation conflict; reload before retrying."}})

    @app.exception_handler(IntakeQuotaExceeded)
    async def intake_limit(request, exc):
        return JSONResponse(status_code=429, content={"error": {"code": exc.code, "message": str(exc)}})

    @app.exception_handler(CloudBudgetExceeded)
    async def production_paused(request, exc):
        return JSONResponse(status_code=429, content={"error": {
            "code": "production_paused", "message": "Hosted production is paused. Contact an administrator.",
        }})

    @app.exception_handler(ValueError)
    async def invalid_request(request, exc):
        return JSONResponse(status_code=400, content={"error": "Invalid workflow request"})

    @app.exception_handler(FileNotFoundError)
    async def missing_resource(request, exc):
        return JSONResponse(status_code=404, content={"error": "Resource not found"})

    @app.get("/ready")
    def ready(request: Request):
        boundary.authorize(request, "readiness", user=False)
        return {"ready": True, "mode": config.mode}

    @app.get("/identity")
    def identity(request: Request):
        return {
            "principal": boundary.authorize(request, "identity"),
            "mode": config.mode,
        }

    @app.post("/internal/coordinator")
    def coordinate(request: Request):
        nonlocal coordinator_instance
        boundary.authorize(request, "coordinate", user=False)
        if config.mode != "cloud":
            raise HTTPException(503, "Hosted coordination unavailable")
        if coordinator_instance is None:
            from .cloud_coordinator import coordinator_from_environment

            coordinator_instance = coordinator_from_environment(expected_project=config.project_id)
        return coordinator_instance.tick()

    @app.post("/internal/operation-events")
    async def operation_event(request: Request):
        boundary.authorize(request, "operation-event", user=False)
        if config.mode != "cloud":
            raise HTTPException(503, "Hosted event dispatch unavailable")
        if request.headers.get("ce-type") != "google.cloud.firestore.document.v1.created":
            raise HTTPException(400, "Unsupported operation event")
        database = os.environ.get("FIRESTORE_DATABASE_ID", "")
        expected_source = f"//firestore.googleapis.com/projects/{config.project_id}/databases/{database}"
        if not database or request.headers.get("ce-source") != expected_source:
            raise HTTPException(400, "Invalid operation event source")
        match = re.fullmatch(
            r"documents/hosted_workflow_v1/[A-Za-z0-9_-]{1,100}/dispatch_signals/([a-f0-9]{32})",
            request.headers.get("ce-subject", ""),
        )
        if not match:
            raise HTTPException(400, "Invalid dispatch signal reference")
        await _body_bytes(request, limit=64 * 1024)
        nonlocal coordinator_instance
        if coordinator_instance is None:
            from .cloud_coordinator import coordinator_from_environment

            coordinator_instance = coordinator_from_environment(expected_project=config.project_id)
        try:
            return coordinator_instance.dispatch_signal(match.group(1))
        except CloudBudgetExceeded:
            return {"dispatched": 0, "deferred": 1, "uncertain": 0}
        except FileNotFoundError:
            return {"dispatched": 0, "deferred": 0, "uncertain": 0}

    @app.get("/production/status")
    def production_status(request: Request):
        boundary.authorize(request, "production-status")
        return cloud_application().production_status()

    @app.post("/internal/billing-report")
    async def billing_report(request: Request):
        boundary.authorize(request, "budget-report", user=False)
        if config.mode != "cloud":
            raise HTTPException(503, "Hosted billing reports unavailable")
        from .cloud_billing import BillingNotificationConfig, parse_billing_notification

        notification_config = billing_config or BillingNotificationConfig.from_environment()
        if not notification_config.subscription.startswith(f"projects/{config.project_id}/subscriptions/"):
            raise HTTPException(503, "Hosted billing subscription configuration mismatch")
        envelope = await _json_request(request, limit=32_000)
        interval, cost, event_id = parse_billing_notification(envelope, notification_config)
        await run_in_threadpool(cloud_application().budget.observe_report, interval, cost, event_id)
        return {"accepted": True}

    @app.post("/production/pause")
    async def production_pause(request: Request):
        actor = await run_in_threadpool(boundary.authorize, request, "production-control")
        payload = await _json_request(request, limit=4096)
        if set(payload) != {"paused", "reason"} or not isinstance(payload["paused"], bool):
            raise HTTPException(400, "Expected paused and reason")
        operator = json.dumps([actor["project_id"], actor["uid"]], separators=(",", ":"))
        await run_in_threadpool(cloud_application().budget.set_paused, operator, payload["reason"],
                                paused=payload["paused"])
        return cloud_application().production_status()

    @app.get("/projects")
    def list_projects(request: Request):
        boundary.authorize(request, "snapshot")
        return cloud_application().list_projects()

    @app.get("/projects/{project_id}")
    def snapshot(project_id: str, request: Request):
        boundary.authorize(request, "snapshot")
        if config.mode == "cloud":
            return cloud_application().snapshot(project_id)
        backend = application()
        try:
            project_id = backend.identifier(project_id)
        except ValueError:
            raise HTTPException(400, "Invalid project identifier") from None
        from manga_tts import PipelineConfig, PipelineRouter

        if not (backend.ROOT / "projects" / project_id / "project.json").is_file():
            raise HTTPException(404, "Project not found")
        from manga_tts.cli import workspace_lock

        with workspace_lock(backend.ROOT / "projects" / project_id):
            router = PipelineRouter(
                PipelineConfig.from_environment(backend.ROOT / "projects" / project_id)
            )
            router.load_project()
            return backend.snapshot(router)

    @app.get("/projects/{project_id}/assets/{asset_path:path}")
    def asset(project_id: str, asset_path: str, request: Request):
        boundary.authorize(request, "asset")
        if config.mode == "cloud":
            path = cloud_application().asset_path(project_id, asset_path)
            return FileResponse(path, headers=PRIVATE_HEADERS)
        raise HTTPException(503, "Asset delivery unavailable")

    @app.put("/uploads/{upload_token}/{name:path}")
    async def upload(upload_token: str, name: str, request: Request):
        actor = await run_in_threadpool(boundary.authorize, request, "upload")
        backend = await run_in_threadpool(cloud_application)
        types = request.headers.getlist("content-type")
        if len(types) != 1 or types[0].lower() != "application/octet-stream":
            raise HTTPException(415, "Expected application/octet-stream")
        body = await _body_bytes(request, MAX_UPLOAD_BYTES)
        if not body:
            raise HTTPException(400, "Empty upload")
        def persist():
            with tempfile.TemporaryDirectory(prefix="manga-api-upload-") as directory:
                source = Path(directory) / "upload"
                source.write_bytes(body)
                return backend.upload(upload_token, name, source, actor)
        return await run_in_threadpool(persist)

    @app.post("/shared")
    async def shared(request: Request):
        # Verify both credentials before reading any private request data. The
        # action-specific second check applies the stronger admin requirement.
        actor = await run_in_threadpool(boundary.authorize, request, "shared", admin=False)
        backend = await run_in_threadpool(cloud_application)
        payload = await _json_request(request, 16 * 1024)
        reader_actions = {"submit", "requests", "delete", "catalog", "published"}
        admin_actions = {"work", "approve", "link", "prepare", "review", "publish"}
        action = payload.get("action")
        if action not in reader_actions | admin_actions:
            raise HTTPException(400, "Invalid shared action")
        if action in admin_actions:
            actor = await run_in_threadpool(boundary.authorize, request, "shared", admin=True)
        return await run_in_threadpool(backend.shared, payload, actor)

    @app.get("/shared/published/{work_id}")
    def published_audio(work_id: str, request: Request, publication_id: str | None = None):
        boundary.authorize(request, "shared", admin=False)
        return FileResponse(cloud_application().published_path(work_id, publication_id), media_type="audio/wav", headers=PRIVATE_HEADERS)

    @app.get("/shared/candidates/{candidate_id}")
    def candidate_audio(candidate_id: str, request: Request):
        boundary.authorize(request, "shared")
        return FileResponse(cloud_application().candidate_path(candidate_id), media_type="audio/wav", headers=PRIVATE_HEADERS)

    @app.post("/operations", status_code=202)
    async def enqueue(request: Request):
        actor = await run_in_threadpool(boundary.authorize, request, "enqueue")
        backend = await run_in_threadpool(workflow_application)
        key, payload = await _operation_request(request)
        payload["actor"] = actor
        # No worker is started here: durable queue ownership remains separate.
        try:
            def persist():
                return backend.enqueue_operation(payload, key).public()

            return await run_in_threadpool(persist)
        except (ValueError, RuntimeError) as exc:
            from manga_tts.schemas import WorkflowError

            if isinstance(exc, (WorkflowError, CloudBudgetExceeded)):
                raise
            from manga_tts.operations import OperationConflict

            if isinstance(exc, OperationConflict):
                raise
            raise HTTPException(400, "Invalid operation request") from None

    @app.get("/operations/by-key")
    def operation_by_key(request: Request, key: str):
        boundary.authorize(request, "poll")
        result = cloud_application().operation_by_key(key)
        if result is None:
            raise HTTPException(404, "Operation not found")
        return result

    @app.get("/operations/{operation_id}")
    def status(operation_id: str, request: Request):
        boundary.authorize(request, "poll")
        backend = workflow_application()
        try:
            result = backend.operation_status(operation_id)
        except ValueError:
            raise HTTPException(400, "Invalid operation identifier") from None
        if result is None:
            raise HTTPException(404, "Operation not found")
        return result

    @app.get("/operations/{operation_id}/events")
    async def operation_events(operation_id: str, request: Request):
        await run_in_threadpool(boundary.authorize, request, "poll")
        backend = await run_in_threadpool(workflow_application)
        loop = asyncio.get_running_loop()
        updates: asyncio.Queue = asyncio.Queue(maxsize=1)

        def publish(value, update_time):
            def enqueue():
                if updates.full():
                    try:
                        updates.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                updates.put_nowait((value, update_time))
            loop.call_soon_threadsafe(enqueue)

        try:
            initial, version, watcher = await run_in_threadpool(backend.watch_operation, operation_id, publish)
        except FileNotFoundError:
            raise HTTPException(404, "Operation not found") from None
        except ValueError:
            raise HTTPException(400, "Invalid operation identifier") from None

        async def stream():
            last_version = version
            last_authorized = time.monotonic()
            expires = last_authorized + 300
            try:
                while time.monotonic() < expires:
                    try:
                        await run_in_threadpool(boundary.authorize, request, "poll")
                    except HTTPException:
                        yield "event: auth-expired\ndata: {}\n\n"
                        return
                    last_authorized = time.monotonic()
                    payload = json.dumps(initial, separators=(",", ":"), allow_nan=False)
                    yield f"id: {version.isoformat()}\nevent: operation\ndata: {payload}\n\n"
                    if initial["status"] in {"complete", "failed", "reconciliation_required"}:
                        return
                    break
                while time.monotonic() < expires:
                    try:
                        value, update_time = await asyncio.wait_for(updates.get(), timeout=15)
                    except asyncio.TimeoutError:
                        if time.monotonic() - last_authorized >= 30:
                            try:
                                await run_in_threadpool(boundary.authorize, request, "poll")
                            except HTTPException:
                                yield "event: auth-expired\ndata: {}\n\n"
                                return
                            last_authorized = time.monotonic()
                        yield ": keepalive\n\n"
                        continue
                    if value is None or update_time is None:
                        yield "event: stream-error\ndata: {}\n\n"
                        return
                    if update_time <= last_version:
                        continue
                    try:
                        await run_in_threadpool(boundary.authorize, request, "poll")
                    except HTTPException:
                        yield "event: auth-expired\ndata: {}\n\n"
                        return
                    last_authorized = time.monotonic()
                    last_version = update_time
                    payload = json.dumps(value, separators=(",", ":"), allow_nan=False)
                    yield f"id: {update_time.isoformat()}\nevent: operation\ndata: {payload}\n\n"
                    if value["status"] in {"complete", "failed", "reconciliation_required"}:
                        return
                yield "event: reconnect\ndata: {}\n\n"
            finally:
                watcher.unsubscribe()

        return StreamingResponse(
            stream(), media_type="text/event-stream",
            headers={**PRIVATE_HEADERS, "X-Accel-Buffering": "no", "Connection": "keep-alive"},
        )

    return app
