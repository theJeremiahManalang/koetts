"""Private S3 API. Hosted verification mode cannot access production workspaces."""

from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from manga_worker.http_auth import BoundaryConfig, CredentialBoundary
from manga_tts.schemas import WorkflowError

PRIVATE_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


def create_app(
    config=None, *, service_verifier=None, user_verifier=None, workflow=None
):
    config = config or BoundaryConfig.from_environment()
    boundary = CredentialBoundary(config, service_verifier, user_verifier)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

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
        key = request.headers.get("idempotency-key", "")
        if not key or len(key) > 200:
            raise HTTPException(
                400, "Idempotency-Key required (maximum 200 characters)"
            )
        try:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 5 * 1024 * 1024:
                    raise HTTPException(413, "Operation request too large")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise TypeError("Invalid request")
        except (ValueError, TypeError):
            raise HTTPException(400, "Invalid operation request") from None
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
