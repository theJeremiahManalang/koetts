"""Private S3 API. Hosted verification mode cannot access production workspaces."""

from __future__ import annotations

import json
import math

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from manga_worker.http_auth import BoundaryConfig, CredentialBoundary
from manga_tts.schemas import WorkflowError

PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
MAX_OPERATION_BYTES = 5 * 1024 * 1024


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
    content_types = request.headers.getlist("content-type")
    if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "Expected application/json")
    lengths = request.headers.getlist("content-length")
    if len(lengths) > 1 or (lengths and (not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 20)):
        raise HTTPException(400, "Invalid Content-Length")
    declared = int(lengths[0]) if lengths else None
    if declared is not None and declared > MAX_OPERATION_BYTES:
        raise HTTPException(413, "Operation request too large")
    try:
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > MAX_OPERATION_BYTES:
                raise HTTPException(413, "Operation request too large")
            body.extend(chunk)
        if declared is not None and declared != len(body):
            raise ValueError("Incomplete body")
        payload = await run_in_threadpool(json.loads, body, object_pairs_hook=_unique_object,
                                          parse_constant=_reject_constant, parse_float=_finite_float)
        if not isinstance(payload, dict):
            raise TypeError("Invalid request")
    except (ValueError, TypeError, RecursionError, ClientDisconnect):
        raise HTTPException(400, "Invalid operation request") from None
    return keys[0], payload


def create_app(
    config=None, *, service_verifier=None, user_verifier=None, workflow=None, coordinator=None
):
    config = config or BoundaryConfig.from_environment()
    boundary = CredentialBoundary(config, service_verifier, user_verifier)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    coordinator_instance = coordinator

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

    @app.get("/projects/{project_id}")
    def snapshot(project_id: str, request: Request):
        boundary.authorize(request, "snapshot")
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
        raise HTTPException(503, "Asset delivery unavailable")

    @app.post("/operations", status_code=202)
    async def enqueue(request: Request):
        actor = await run_in_threadpool(boundary.authorize, request, "enqueue")
        backend = await run_in_threadpool(application)
        key, payload = await _operation_request(request)
        payload["actor"] = actor
        # No worker is started here: durable queue ownership remains separate.
        try:
            def persist():
                return backend.enqueue_operation(payload, key).public()

            return await run_in_threadpool(persist)
        except (ValueError, RuntimeError) as exc:
            from manga_tts.schemas import WorkflowError

            if isinstance(exc, WorkflowError):
                raise
            from manga_tts.operations import OperationConflict

            if isinstance(exc, OperationConflict):
                raise HTTPException(409, "Operation conflict") from None
            raise HTTPException(400, "Invalid operation request") from None

    @app.get("/operations/{operation_id}")
    def status(operation_id: str, request: Request):
        boundary.authorize(request, "poll")
        backend = application()
        try:
            result = backend.operation_status(operation_id)
        except ValueError:
            raise HTTPException(400, "Invalid operation identifier") from None
        if result is None:
            raise HTTPException(404, "Operation not found")
        return result

    return app
