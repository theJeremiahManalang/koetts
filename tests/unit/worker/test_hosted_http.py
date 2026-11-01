"""Hosted routes independently authenticate callers before touching cloud services."""
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from datetime import UTC, datetime

import httpx

from manga_tts.shared_requests import IntakeQuotaExceeded
from manga_worker.http_api import create_app
from manga_worker.http_auth import BoundaryConfig


class HostedHTTPTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.audio = Path(self.temporary.name) / "audio.wav"
        self.audio.write_bytes(b"0123456789")
        self.backend = Mock()
        self.backend.published_path.return_value = self.audio
        self.backend.candidate_path.return_value = self.audio
        self.backend.asset_path.return_value = self.audio
        self.backend.shared.return_value = {"id": "safe-result"}
        self.backend.list_projects.return_value = {"projects": [], "provider_configured": False}
        self.backend.operation_by_key.return_value = {"id": "original-operation"}
        self.config = BoundaryConfig("demo-hosted", "https://private.example", {
            "web": frozenset({"snapshot", "asset", "enqueue", "poll", "shared", "upload"}),
            "events": frozenset({"operation-event"}),
        }, "cloud")

    def app(self, mode="cloud"):
        config = BoundaryConfig(self.config.project_id, self.config.audience, self.config.permissions, mode)
        def service(token):
            if token not in {"service", "event-service"}:
                raise ValueError("forged service")
            return {"sub": "events" if token == "event-service" else "web", "iss": "https://accounts.google.com", "aud": config.audience}
        def user(token, session):
            if token == "revoked":
                raise ValueError("revoked")
            return {"sub": token, "admin": token == "admin", "aud": config.project_id,
                    "iss": ("https://session.firebase.google.com/" if session else "https://securetoken.google.com/") + config.project_id}
        return create_app(config, hosted=self.backend, service_verifier=service, user_verifier=user)

    @staticmethod
    def headers(user="reader"):
        return {"Authorization": "Bearer service", "X-Koetts-User-Token": user}

    async def test_reader_actions_and_admin_actions_recheck_role_and_actor(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(self.app()), base_url="https://private.example") as client:
            response = await client.post("/shared", headers=self.headers(), json={
                "action": "submit", "reader": "forged", "actor": "forged", "title": "Manga", "chapter": "1", "notes": "note",
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.backend.shared.call_args.args[1], {"kind": "firebase", "uid": "reader", "project_id": "demo-hosted"})
            self.backend.shared.reset_mock()
            for action in ("work", "approve", "link", "prepare", "review", "publish"):
                denied = await client.post("/shared", headers=self.headers(), json={"action": action})
                self.assertEqual(denied.status_code, 403)
            self.backend.shared.assert_not_called()
            admin = await client.post("/shared", headers=self.headers("admin"), json={"action": "work"})
            self.assertEqual(admin.status_code, 200)

    async def test_operation_event_requires_eventarc_identity_and_exact_firestore_signal(self):
        headers = {
            "Authorization": "Bearer event-service",
            "ce-type": "google.cloud.firestore.document.v1.created",
            "ce-source": "//firestore.googleapis.com/projects/demo-hosted/databases/koetts-default",
            "ce-subject": "documents/hosted_workflow_v1/dataset/dispatch_signals/" + "a" * 32,
        }
        event_thread = threading.get_ident()
        dispatch_threads = []
        auth_threads = []
        coordinator = Mock()
        coordinator.dispatch_signal.side_effect = lambda *_: (dispatch_threads.append(threading.get_ident()) or {"dispatched": 1, "deferred": 0, "uncertain": 0})
        coordinator.dispatch_signal.return_value = {"dispatched": 1, "deferred": 0, "uncertain": 0}
        config = BoundaryConfig(self.config.project_id, self.config.audience, self.config.permissions, "cloud")
        def service(token):
            auth_threads.append(threading.get_ident())
            subject = "events" if token == "event-service" else "web"
            return {"sub": subject, "iss": "https://accounts.google.com", "aud": config.audience}
        with patch.dict("os.environ", {"FIRESTORE_DATABASE_ID": "koetts-default"}):
            app = create_app(config, service_verifier=service, user_verifier=lambda *_: {}, coordinator=coordinator)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://private.example") as client:
                accepted = await client.post("/internal/operation-events", headers=headers, json={"ignored": True})
                self.assertEqual(accepted.status_code, 200)
                self.assertEqual(accepted.json()["dispatched"], 1)
                self.assertNotEqual(dispatch_threads, [])
                self.assertTrue(all(thread != event_thread for thread in dispatch_threads))
                self.assertTrue(auth_threads)
                self.assertTrue(all(thread != event_thread for thread in auth_threads))
                self.assertEqual(coordinator.dispatch_signal.call_args.args[0], "a" * 32)
                for mutation in (
                    {"ce-source": "//firestore.googleapis.com/projects/other/databases/koetts-default"},
                    {"ce-subject": "documents/hosted_workflow_v1/other/operations/" + "a" * 32},
                    {"ce-type": "google.cloud.firestore.document.v1.updated"},
                ):
                    rejected = await client.post("/internal/operation-events", headers={**headers, **mutation}, json={})
                    self.assertEqual(rejected.status_code, 400)
                denied = await client.post("/internal/operation-events", headers={**headers, "Authorization": "Bearer service"}, json={})
                self.assertEqual(denied.status_code, 403)

    async def test_operation_status_stream_sends_current_and_terminal_state(self):
        watcher = Mock()
        initial = {"id": "a" * 32, "project": "b" * 32, "status": "running", "message": "Working"}
        terminal = {**initial, "status": "complete", "message": "Ready"}
        def watch_operation(operation_id, callback):
            if operation_id != initial["id"]:
                raise ValueError("Invalid operation identifier")
            callback(terminal, datetime(2026, 11, 2, 0, 0, 1, tzinfo=UTC))
            return initial, datetime(2026, 11, 2, 0, 0, 0, tzinfo=UTC), watcher
        self.backend.watch_operation.side_effect = watch_operation
        async def inline(function, *args, **kwargs):
            return function(*args, **kwargs)
        with patch("manga_worker.http_api.run_in_threadpool", new=inline):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(self.app()), base_url="https://private.example") as client:
                response = await client.get(f"/operations/{initial['id']}/events", headers=self.headers("admin"))
                invalid = await client.get("/operations/not-an-id/events", headers=self.headers("admin"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/event-stream")
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertIn('"status":"running"', response.text)
        self.assertIn('"status":"complete"', response.text)
        watcher.unsubscribe.assert_called_once_with()
        self.assertEqual(invalid.status_code, 400)

    async def test_operation_stream_closes_when_admin_is_revoked_midstream(self):
        watcher = Mock()
        initial = {"id": "a" * 32, "project": "b" * 32, "status": "running", "message": "Working"}
        terminal = {**initial, "status": "complete", "message": "Ready"}
        def watch_operation(_, callback):
            callback(terminal, datetime(2026, 11, 2, 0, 0, 1, tzinfo=UTC))
            return initial, datetime(2026, 11, 2, 0, 0, 0, tzinfo=UTC), watcher
        self.backend.watch_operation.side_effect = watch_operation
        checks = 0
        def verify_user(*_):
            nonlocal checks
            checks += 1
            if checks >= 3:
                raise ValueError("revoked")
            return {"sub": "admin", "admin": True, "aud": "demo-hosted",
                    "iss": "https://securetoken.google.com/demo-hosted"}
        config = BoundaryConfig(self.config.project_id, self.config.audience, self.config.permissions, "cloud")
        def verify_service(_):
            return {"sub": "web", "iss": "https://accounts.google.com", "aud": config.audience}
        app = create_app(config, hosted=self.backend, service_verifier=verify_service, user_verifier=verify_user)
        async def inline(function, *args, **kwargs):
            return function(*args, **kwargs)
        with patch("manga_worker.http_api.run_in_threadpool", new=inline):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://private.example") as client:
                response = await client.get(f"/operations/{initial['id']}/events", headers=self.headers("admin"))
        self.assertIn('"status":"running"', response.text)
        self.assertIn("event: auth-expired", response.text)
        self.assertNotIn('"status":"complete"', response.text)
        watcher.unsubscribe.assert_called_once_with()

    async def test_published_ranges_require_fresh_valid_reader_credentials(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(self.app()), base_url="https://private.example") as client:
            response = await client.get("/shared/published/work?publication_id=publication", headers={**self.headers(), "Range": "bytes=2-5"})
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.content, b"2345")
            self.assertEqual(response.headers["content-range"], "bytes 2-5/10")
            self.assertEqual(response.headers["cache-control"], "private, no-store")
            self.backend.published_path.reset_mock()
            for headers in ({}, self.headers("revoked"), {**self.headers(), "Authorization": "Bearer forged"}):
                rejected = await client.get("/shared/published/work", headers=headers)
                self.assertEqual(rejected.status_code, 401)
            self.backend.published_path.assert_not_called()
            self.assertEqual((await client.get("/shared/candidates/candidate", headers=self.headers())).status_code, 403)
            self.backend.candidate_path.assert_not_called()

    async def test_upload_is_bounded_before_persistence_and_pins_verified_actor(self):
        self.backend.upload.return_value = {"sha256": "a" * 64}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(self.app()), base_url="https://private.example") as client:
            response = await client.put("/uploads/token/0.png", headers={**self.headers("admin"), "Content-Type": "application/octet-stream"}, content=b"synthetic image")
            self.assertEqual(response.status_code, 200)
            args = self.backend.upload.call_args.args
            self.assertEqual(args[0:2], ("token", "0.png"))
            self.assertEqual(args[3]["uid"], "admin")
            self.backend.upload.reset_mock()
            too_big = await client.put("/uploads/token/0.png", headers={**self.headers("admin"), "Content-Type": "application/octet-stream", "Content-Length": str(11 * 1024 * 1024)}, content=b"small")
            self.assertEqual(too_big.status_code, 413)
            self.assertEqual((await client.put("/uploads/token/0.png", headers=self.headers(), content=b"bytes")).status_code, 403)
            self.backend.upload.assert_not_called()

    async def test_intake_limit_is_typed_and_backend_is_unavailable_in_verification_mode(self):
        self.backend.shared.side_effect = IntakeQuotaExceeded("daily_limit", "Daily reader request limit reached")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(self.app()), base_url="https://private.example") as client:
            response = await client.post("/shared", headers=self.headers(), json={"action": "submit"})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.json()["error"]["code"], "daily_limit")
        self.backend.shared.reset_mock()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(self.app("verification")), base_url="https://private.example") as client:
            response = await client.post("/shared", headers=self.headers(), json={"action": "submit"})
            self.assertEqual(response.status_code, 503)
            self.backend.shared.assert_not_called()

    async def test_enqueue_overwrites_actor_and_key_lookup_precedes_id_route(self):
        self.backend.enqueue_operation.return_value = Mock(public=lambda: {"id": "safe-operation"})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(self.app()), base_url="https://private.example") as client:
            response = await client.post("/operations", headers={**self.headers("admin"), "Idempotency-Key": "intent"}, json={"action": "rename", "actor": {"uid": "forged"}})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(self.backend.enqueue_operation.call_args.args[0]["actor"]["uid"], "admin")
            lookup = await client.get("/operations/by-key?key=intent", headers=self.headers("admin"))
            self.assertEqual(lookup.json()["id"], "original-operation")
            self.backend.operation_status.assert_not_called()
