"""Hosted routes independently authenticate callers before touching cloud services."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

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
        self.backend.list_projects.return_value = {"projects": [], "has_api_key": False}
        self.backend.operation_by_key.return_value = {"id": "original-operation"}
        self.config = BoundaryConfig("demo-hosted", "https://private.example", {
            "web": frozenset({"snapshot", "asset", "enqueue", "poll", "shared", "upload"}),
        }, "cloud")

    def app(self, mode="cloud"):
        config = BoundaryConfig(self.config.project_id, self.config.audience, self.config.permissions, mode)
        def service(token):
            if token != "service":
                raise ValueError("forged service")
            return {"sub": "web", "iss": "https://accounts.google.com", "aud": config.audience}
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
