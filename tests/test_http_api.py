"""S3 HTTP credential boundaries, with injected external identity verifiers."""

import unittest

import httpx

from manga_tts.http_api import create_app
from manga_tts.http_auth import BoundaryConfig


class HttpBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_required_even_for_readiness(self):
        app = create_app(
            BoundaryConfig(
                "test-project", "https://api", {"svc": frozenset({"readiness"})}
            ),
            service_verifier=lambda token: {
                "sub": "svc",
                "iss": "https://accounts.google.com",
                "aud": "https://api",
            },
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            self.assertEqual((await client.get("/ready")).status_code, 401)
            self.assertEqual(
                (
                    await client.get(
                        "/ready", headers={"Authorization": "Bearer valid"}
                    )
                ).status_code,
                200,
            )

    async def test_verified_admin_identity_and_hosted_data_refusal(self):
        actions = frozenset({"identity", "snapshot", "enqueue", "poll", "asset"})

        def service(token):
            return {
                "sub": "svc",
                "iss": "https://accounts.google.com",
                "aud": "https://api",
            }

        def user(token, session):
            return {
                "sub": "admin-user",
                "iss": (
                    "https://session.firebase.google.com/"
                    if session
                    else "https://securetoken.google.com/"
                )
                + "test-project",
                "aud": "test-project",
                "admin": True,
            }

        class UnavailableBackend:
            def __getattr__(self, name):
                raise AssertionError(
                    "Verification must never access a workspace or provider"
                )

        app = create_app(
            BoundaryConfig("test-project", "https://api", {"svc": actions}),
            service_verifier=service,
            user_verifier=user,
            workflow=UnavailableBackend(),
        )
        headers = {"Authorization": "Bearer service", "X-KoeTTS-User-Token": "user"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            identity = await client.get("/identity", headers=headers)
            self.assertEqual(
                identity.json(),
                {
                    "principal": {
                        "kind": "firebase",
                        "uid": "admin-user",
                        "project_id": "test-project",
                    },
                    "mode": "verification",
                },
            )
            for method, path in [
                ("GET", "/projects/project"),
                ("GET", "/projects/project/assets/example.wav"),
                ("GET", "/operations/job"),
                ("POST", "/operations"),
            ]:
                self.assertEqual(
                    (await client.request(method, path, headers=headers)).status_code,
                    503,
                )
            session = {
                "Authorization": "Bearer service",
                "X-KoeTTS-Session-Cookie": "cookie",
            }
            self.assertEqual(
                (await client.get("/identity", headers=session)).status_code, 200
            )

    async def test_untrusted_or_ambiguous_credentials_are_denied(self):
        config = BoundaryConfig(
            "test-project", "https://api", {"svc": frozenset({"identity"})}
        )
        valid_service = {
            "sub": "svc",
            "iss": "https://accounts.google.com",
            "aud": "https://api",
        }
        valid_user = {
            "sub": "admin",
            "iss": "https://securetoken.google.com/test-project",
            "aud": "test-project",
            "admin": True,
        }
        for changes, expected in [
            ({"aud": "other"}, 401),
            ({"iss": "forged"}, 401),
            ({"sub": "other"}, 403),
        ]:
            app = create_app(
                config,
                service_verifier=lambda token, changes=changes: {
                    **valid_service,
                    **changes,
                },
                user_verifier=lambda token, session: valid_user,
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                self.assertEqual(
                    (
                        await client.get(
                            "/identity",
                            headers={
                                "Authorization": "Bearer x",
                                "X-KoeTTS-User-Token": "x",
                            },
                        )
                    ).status_code,
                    expected,
                )
        for changes, expected in [
            ({"admin": False}, 403),
            ({"admin": "true"}, 403),
            ({"aud": "other"}, 401),
            ({"iss": "forged"}, 401),
            ({"sub": ""}, 401),
        ]:
            app = create_app(
                config,
                service_verifier=lambda token: valid_service,
                user_verifier=lambda token, session, changes=changes: {
                    **valid_user,
                    **changes,
                },
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                self.assertEqual(
                    (
                        await client.get(
                            "/identity",
                            headers={
                                "Authorization": "Bearer x",
                                "X-KoeTTS-User-Token": "x",
                            },
                        )
                    ).status_code,
                    expected,
                )
        app = create_app(
            config,
            service_verifier=lambda token: valid_service,
            user_verifier=lambda token, session: valid_user,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for extra in [
                {},
                {"X-KoeTTS-User-Token": "x", "X-KoeTTS-Session-Cookie": "x"},
                {"X-KoeTTS-UID": "admin", "X-KoeTTS-Role": "admin"},
            ]:
                self.assertEqual(
                    (
                        await client.get(
                            "/identity", headers={"Authorization": "Bearer x", **extra}
                        )
                    ).status_code,
                    401,
                )

    async def test_revocation_or_verifier_failure_never_leaks_secrets(self):
        def revoked(token, session):
            raise ValueError("private credential detail")

        app = create_app(
            BoundaryConfig(
                "test-project", "https://api", {"svc": frozenset({"identity"})}
            ),
            service_verifier=lambda token: {
                "sub": "svc",
                "iss": "https://accounts.google.com",
                "aud": "https://api",
            },
            user_verifier=revoked,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/identity",
                headers={"Authorization": "Bearer x", "X-KoeTTS-User-Token": "x"},
            )
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("private", response.text)

    async def test_local_queue_overwrites_actor_and_preserves_conflicts(self):
        from manga_tts.operations import OperationConflict
        from manga_tts.schemas import Failure, WorkflowError

        class Backend:
            def enqueue_operation(self, payload, key):
                if key == "conflict":
                    raise OperationConflict("conflict", "private path")
                if key == "stale":
                    raise WorkflowError(
                        Failure(
                            code="stale_revision",
                            stage="review",
                            message="Refresh project",
                        )
                    )
                self.payload = payload

                class Operation:
                    def public(self):
                        return {"operation_id": "durable-op"}

                return Operation()

            def operation_status(self, operation_id):
                return (
                    {"operation_id": operation_id}
                    if operation_id == "durable-op"
                    else None
                )

        backend = Backend()
        app = create_app(
            BoundaryConfig(
                "test-project",
                "https://api",
                {"svc": frozenset({"enqueue", "poll"})},
                mode="local",
            ),
            service_verifier=lambda token: {
                "sub": "svc",
                "iss": "https://accounts.google.com",
                "aud": "https://api",
            },
            user_verifier=lambda token, session: {
                "sub": "admin",
                "iss": "https://securetoken.google.com/test-project",
                "aud": "test-project",
                "admin": True,
            },
            workflow=backend,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            headers = {
                "Authorization": "Bearer x",
                "X-KoeTTS-User-Token": "x",
                "Idempotency-Key": "new",
            }
            response = await client.post(
                "/operations",
                headers=headers,
                json={"actor": {"uid": "forged"}, "action": "approve_cast"},
            )
            self.assertEqual(response.status_code, 202)
            self.assertEqual(
                backend.payload["actor"],
                {"kind": "firebase", "uid": "admin", "project_id": "test-project"},
            )
            for key in ["conflict", "stale"]:
                response = await client.post(
                    "/operations", headers={**headers, "Idempotency-Key": key}, json={}
                )
                self.assertEqual(response.status_code, 409)
                self.assertNotIn("private path", response.text)
            self.assertEqual(
                (
                    await client.get("/operations/durable-op", headers=headers)
                ).status_code,
                200,
            )
            self.assertEqual(
                (await client.get("/operations/missing", headers=headers)).status_code,
                404,
            )

    async def test_real_local_snapshot_and_durable_idempotency(self):
        import shutil
        from unittest.mock import patch

        import test_audio_pipeline as fixtures

        import web_workflow

        fixture = fixtures.PipelineTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.approve()
        root = fixture.root / "web-api"
        project_id = "a" * 32
        workspace = root / "projects" / project_id
        shutil.copytree(fixture.router.root, workspace)
        app = create_app(
            BoundaryConfig(
                "test-project",
                "https://api",
                {"svc": frozenset({"snapshot", "enqueue", "poll"})},
                mode="local",
            ),
            service_verifier=lambda token: {
                "sub": "svc",
                "iss": "https://accounts.google.com",
                "aud": "https://api",
            },
            user_verifier=lambda token, session: {
                "sub": "admin",
                "iss": "https://securetoken.google.com/test-project",
                "aud": "test-project",
                "admin": True,
            },
        )
        headers = {
            "Authorization": "Bearer x",
            "X-KoeTTS-User-Token": "x",
            "Idempotency-Key": "real-intent",
        }
        with patch.object(web_workflow, "ROOT", root):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                snapshot = await client.get("/projects/" + project_id, headers=headers)
                self.assertEqual(snapshot.status_code, 200)
                revision = snapshot.json()["revision"]
                payload = {
                    "project": project_id,
                    "action": "rename",
                    "revision": revision,
                    "command": {"title": "New title"},
                }
                first = await client.post("/operations", headers=headers, json=payload)
                self.assertEqual(first.status_code, 202)
                second = await client.post("/operations", headers=headers, json=payload)
                self.assertEqual(first.json()["id"], second.json()["id"])
                conflict = await client.post(
                    "/operations",
                    headers=headers,
                    json={**payload, "command": {"title": "Different"}},
                )
                self.assertEqual(conflict.status_code, 409)
                operation_id = first.json()["id"]
                poll = await client.get("/operations/" + operation_id, headers=headers)
                self.assertEqual(poll.status_code, 200)
                self.assertEqual(poll.json()["status"], "queued")
                claim = web_workflow.claim_next_operation()
                assert claim is not None
                web_workflow.run_operation(claim.operation_id, claim.fence)
                stale = await client.post(
                    "/operations",
                    headers={**headers, "Idempotency-Key": "stale-intent"},
                    json=payload,
                )
                self.assertEqual(stale.status_code, 202)
                stale_claim = web_workflow.claim_next_operation()
                assert stale_claim is not None
                web_workflow.run_operation(stale_claim.operation_id, stale_claim.fence)
                stale_status = await client.get(
                    "/operations/" + stale.json()["id"], headers=headers
                )
                self.assertEqual(stale_status.json()["status"], "failed")
                self.assertEqual(
                    stale_status.json()["failure_code"], "revision_conflict"
                )

    async def test_asset_requires_both_identities_and_asset_permission(self):
        for permission, user, expected in [
            ({"asset"}, None, 401),
            ({"snapshot"}, "admin", 403),
            ({"asset"}, "reader", 403),
            ({"asset"}, "admin", 503),
        ]:
            app = create_app(
                BoundaryConfig(
                    "test-project", "https://api", {"svc": frozenset(permission)}
                ),
                service_verifier=lambda token: {
                    "sub": "svc",
                    "iss": "https://accounts.google.com",
                    "aud": "https://api",
                },
                user_verifier=lambda token, session: {
                    "sub": "user",
                    "iss": "https://securetoken.google.com/test-project",
                    "aud": "test-project",
                    "admin": token == "admin",
                },
            )
            headers = {"Authorization": "Bearer service"}
            if user:
                headers["X-KoeTTS-User-Token"] = user
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/projects/project/assets/example.wav", headers=headers
                )
                self.assertEqual(response.status_code, expected)
