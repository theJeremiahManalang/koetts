"""Scheduled coordination requires its own service permission and explicit cloud mode."""
import unittest
from unittest.mock import Mock, patch

import httpx

from manga_worker.http_api import create_app
from manga_worker.http_auth import BoundaryConfig


class CoordinatorBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_storage_project_must_match_authenticated_service_project(self):
        from manga_worker.cloud_coordinator import coordinator_from_environment

        with patch("manga_worker.cloud_coordinator.CloudSettings.from_environment", return_value=Mock(project="other")):
            with patch("google.cloud.firestore.Client", side_effect=AssertionError("Must reject before ADC")):
                with self.assertRaises(ValueError):
                    coordinator_from_environment(expected_project="demo-hosted")

    async def request(self, mode, permissions, *, authorization="Bearer scheduler"):
        coordinator = Mock()
        coordinator.tick.return_value = {"dispatched": 1, "reconciled": 0, "uncertain": 0}
        config = BoundaryConfig("demo-hosted", "https://private.example", {"scheduler": frozenset(permissions)}, mode)
        app = create_app(config, coordinator=coordinator, service_verifier=lambda _: {
            "sub": "scheduler", "iss": "https://accounts.google.com", "aud": config.audience,
        }, user_verifier=Mock(side_effect=AssertionError("Scheduler never impersonates a user")))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://private.example") as client:
            response = await client.post("/internal/coordinator", headers={"Authorization": authorization})
        return coordinator, response

    async def test_only_cloud_scheduler_permission_can_coordinate_without_user_credentials(self):
        coordinator, response = await self.request("cloud", {"coordinate"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["dispatched"], 1)
        coordinator.tick.assert_called_once_with()
        self.assertEqual(response.headers["cache-control"], "private, no-store")

    async def test_web_service_without_coordinate_permission_cannot_dispatch(self):
        coordinator, response = await self.request("cloud", {"identity", "readiness"})
        self.assertEqual(response.status_code, 403)
        coordinator.tick.assert_not_called()

    async def test_verification_and_local_modes_never_construct_or_run_cloud_coordinator(self):
        with patch("manga_worker.cloud_coordinator.coordinator_from_environment", side_effect=AssertionError("Cloud access")):
            for mode in ("verification", "local"):
                coordinator, response = await self.request(mode, {"coordinate"})
                self.assertEqual(response.status_code, 503)
                coordinator.tick.assert_not_called()

    async def test_anonymous_scheduler_request_cannot_dispatch(self):
        coordinator, response = await self.request("cloud", {"coordinate"}, authorization="")
        self.assertEqual(response.status_code, 401)
        coordinator.tick.assert_not_called()
