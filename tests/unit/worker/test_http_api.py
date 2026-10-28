"""S3 HTTP credential boundaries, with injected external identity verifiers."""

import unittest

import httpx

from manga_worker.http_api import create_app
from manga_worker.http_auth import BoundaryConfig


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

        from tests.unit.engine import test_audio_pipeline as fixtures

        from manga_worker import workflow as web_workflow

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


class HttpHardeningTests(unittest.IsolatedAsyncioTestCase):
    headers = {"Authorization": "Bearer service", "X-KoeTTS-User-Token": "user", "Idempotency-Key": "intent"}

    def app(self, backend=None, *, service_verifier=None, user_verifier=None):
        return create_app(
            BoundaryConfig("test-project", "https://api", {
                "svc": frozenset({"readiness", "identity", "enqueue", "poll", "snapshot"})
            }, mode="local"),
            service_verifier=service_verifier or (lambda token: {
                "sub": "svc", "iss": "https://accounts.google.com", "aud": "https://api",
            }),
            user_verifier=user_verifier or (lambda token, session: {
                "sub": "admin", "iss": "https://securetoken.google.com/test-project",
                "aud": "test-project", "admin": True,
            }),
            workflow=backend,
        )

    async def test_blocking_verification_and_storage_do_not_occupy_event_loop(self):
        import asyncio
        import threading

        loop_thread = threading.get_ident()
        verifier_threads = []
        started, release = threading.Event(), threading.Event()

        def service(token):
            verifier_threads.append(threading.get_ident())
            return {"sub": "svc", "iss": "https://accounts.google.com", "aud": "https://api"}

        def user(token, session):
            verifier_threads.append(threading.get_ident())
            return {"sub": "admin", "iss": "https://securetoken.google.com/test-project", "aud": "test-project", "admin": True}

        class Backend:
            def operation_status(self, operation_id):
                started.set()
                release.wait(2)
                return {"id": operation_id}

        app = self.app(Backend(), service_verifier=service, user_verifier=user)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            self.assertEqual((await client.get("/identity", headers=self.headers)).status_code, 200)
            self.assertTrue(all(thread != loop_thread for thread in verifier_threads))
            blocked = asyncio.create_task(client.get("/operations/blocked", headers=self.headers))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                self.assertFalse(blocked.done())
                response = await asyncio.wait_for(client.get("/ready", headers=self.headers), timeout=1)
                self.assertEqual(response.status_code, 200)
            finally:
                release.set()
                await blocked

    async def test_private_responses_are_not_cacheable_and_errors_are_sanitized(self):
        class Backend:
            def operation_status(self, operation_id):
                raise RuntimeError("private database path and credential")

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app(Backend()), raise_app_exceptions=False), base_url="http://test") as client:
            for route, headers, expected in [
                ("/identity", self.headers, 200), ("/identity", {}, 401),
                ("/operations/unknown", self.headers, 500),
            ]:
                response = await client.get(route, headers=headers)
                self.assertEqual(response.status_code, expected)
                self.assertIn("no-store", response.headers.get("cache-control", ""))
                self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
                self.assertNotIn("private database", response.text)
                self.assertNotIn("credential", response.text if expected == 500 else "")

    async def test_enqueue_rejects_ambiguous_or_non_json_inputs_before_persistence(self):
        class Backend:
            def __init__(self):
                self.payloads = []

            def enqueue_operation(self, payload, key):
                self.payloads.append(payload)
                raise AssertionError("Invalid input reached persistence")

        backend = Backend()
        valid_headers = {**self.headers, "Content-Type": "application/json"}
        cases = [
            (self.headers, b"{}", 415),
            ({**valid_headers, "Content-Type": "text/plain"}, b"{}", 415),
            (valid_headers, b"{", 400),
            (valid_headers, b'{"action":"rename","action":"render"}', 400),
            (valid_headers, b'{"value":NaN}', 400),
            (valid_headers, b'{"value":Infinity}', 400),
            (valid_headers, b'{"value":1e999}', 400),
            (valid_headers, b"[" * 1500 + b"0" + b"]" * 1500, 400),
            ({**valid_headers, "Idempotency-Key": "   "}, b"{}", 400),
            ([*valid_headers.items(), ("Idempotency-Key", "second")], b"{}", 400),
            ({**valid_headers, "Content-Length": "-1"}, b"{}", 400),
            ({**valid_headers, "Content-Length": "3"}, b"{}", 400),
            ([*valid_headers.items(), ("Content-Length", "2"), ("Content-Length", "3")], b"{}", 400),
        ]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app(backend), raise_app_exceptions=False), base_url="http://test") as client:
            for headers, body, expected in cases:
                with self.subTest(headers=headers, body=body[:80]):
                    response = await client.post("/operations", headers=headers, content=body)
                    self.assertEqual(response.status_code, expected)
        self.assertEqual(backend.payloads, [])

    async def test_enqueue_limits_declared_and_streamed_body_size(self):
        limit = 5 * 1024 * 1024
        consumed = False

        async def declared_body():
            nonlocal consumed
            consumed = True
            yield b"{}"

        async def streamed_body():
            yield b" " * limit
            yield b"x"

        class Backend:
            def enqueue_operation(self, payload, key):
                raise AssertionError("Oversized body reached persistence")

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app(Backend())), base_url="http://test") as client:
            headers = {**self.headers, "Content-Type": "application/json"}
            response = await client.post("/operations", headers={**headers, "Content-Length": str(limit + 1)}, content=declared_body())
            self.assertEqual(response.status_code, 413)
            self.assertFalse(consumed)
            response = await client.post("/operations", headers=headers, content=streamed_body())
            self.assertEqual(response.status_code, 413)

    async def test_malformed_credentials_are_rejected_before_external_verifiers(self):
        service_calls, user_calls = [], []

        def service(token):
            service_calls.append(token)
            return {"sub": "svc", "iss": "https://accounts.google.com", "aud": "https://api"}

        def user(token, session):
            user_calls.append(token)
            return {"sub": "admin", "iss": "https://securetoken.google.com/test-project", "aud": "test-project", "admin": True}

        app = self.app(service_verifier=service, user_verifier=user)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for authorization in ("Bearer ", "Bearer two tokens", "Bearer " + "x" * 16385):
                response = await client.get("/identity", headers={**self.headers, "Authorization": authorization})
                self.assertEqual(response.status_code, 401)
            duplicate = [*self.headers.items(), ("Authorization", "Bearer second")]
            self.assertEqual((await client.get("/identity", headers=duplicate)).status_code, 401)
            self.assertEqual(service_calls, [])
            for token in (" ", "two tokens", "x" * 16385):
                response = await client.get("/identity", headers={**self.headers, "X-KoeTTS-User-Token": token})
                self.assertEqual(response.status_code, 401)
            self.assertEqual(user_calls, [])
            response = await client.get("/identity", headers={**self.headers, "Authorization": "bearer service"})
            self.assertEqual(response.status_code, 200)

    async def test_invalid_direct_configuration_fails_before_serving(self):
        for project, audience in (("", "https://api"), ("test-project", ""), (" ", "https://api")):
            with self.subTest(project=project, audience=audience), self.assertRaises(ValueError):
                create_app(BoundaryConfig(project, audience, {}))
