"""Production controls require both service permission and verified admin identity."""
import unittest
from unittest.mock import Mock

import httpx

from manga_worker.http_api import create_app
from manga_worker.http_auth import BoundaryConfig


class ProductionControlTests(unittest.IsolatedAsyncioTestCase):
    def app(self, permissions=None):
        self.hosted = Mock()
        self.hosted.budget.status.return_value = {"paused": True}
        return create_app(
            BoundaryConfig("demo-controls", "https://api", {
                "service": frozenset(permissions if permissions is not None else
                                     {"production-status", "production-control", "identity"}),
            }, mode="cloud"),
            service_verifier=lambda token: {
                "sub": "service", "iss": "https://accounts.google.com", "aud": "https://api",
            },
            user_verifier=lambda token, session: {
                "sub": "verified-user", "iss": "https://securetoken.google.com/demo-controls",
                "aud": "demo-controls", "admin": token == "admin",
            }, hosted=self.hosted,
        )

    async def test_status_denies_missing_user_and_reader_before_backend(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app()), base_url="http://test") as client:
            for credential, expected in ((None, 401), ("reader", 403), ("admin", 200)):
                headers = {"Authorization": "Bearer service"}
                if credential:
                    headers["X-KoeTTS-User-Token"] = credential
                response = await client.get("/production/status", headers=headers)
                self.assertEqual(response.status_code, expected)
            self.hosted.budget.status.assert_called_once_with()

    async def test_pause_records_verified_actor_and_identity_remains_available(self):
        headers = {"Authorization": "Bearer service", "X-KoeTTS-User-Token": "admin"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app()), base_url="http://test") as client:
            response = await client.post("/production/pause", headers=headers,
                                         json={"paused": True, "reason": "operator pause"})
            self.assertEqual(response.status_code, 200)
            self.hosted.budget.set_paused.assert_called_once_with(
                '["demo-controls","verified-user"]', "operator pause", paused=True,
            )
            self.assertEqual((await client.get("/identity", headers=headers)).status_code, 200)

    async def test_service_permission_and_exact_control_fields_required(self):
        headers = {"Authorization": "Bearer service", "X-KoeTTS-User-Token": "admin"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app(set())), base_url="http://test") as client:
            self.assertEqual((await client.post("/production/pause", headers=headers,
                                               json={"paused": True, "reason": "pause"})).status_code, 403)
            self.hosted.budget.set_paused.assert_not_called()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app()), base_url="http://test") as client:
            self.assertEqual((await client.post("/production/pause", headers=headers, json={
                "paused": True, "reason": "pause", "actor": "forged",
            })).status_code, 400)
            self.hosted.budget.set_paused.assert_not_called()
