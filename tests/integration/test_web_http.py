"""Opt-in local HTTP integration; leaves a labeled test project in results/web.

Set MANGA_WEB_TEST_URL=http://127.0.0.1:3001 with the Next server running.
Exercises API transport only, not browser rendering or visual correctness.
"""
import json
import os
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlencode, urlparse

from tests.unit.engine import test_audio_pipeline as fixtures

from manga_tts.cli import review_document
from manga_tts.schemas import Project, RenderCommand


@unittest.skipUnless(os.environ.get("MANGA_WEB_TEST_URL"), "No local web test server configured")
class WebHTTPTests(unittest.TestCase):
    def test_upload_restore_render_reuse_export_and_download(self):
        base = os.environ["MANGA_WEB_TEST_URL"].rstrip("/")
        self.assertIn(urlparse(base).hostname, {"127.0.0.1", "localhost"})
        fixture = fixtures.PipelineTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.approve()
        fixture.router.render_selected(RenderCommand(scene_ids=["scene_001"]))
        project = fixture.router._data()
        project["chapter_id"] = "web_integration_test"
        fixture.router._commit(project)
        bundle = fixture.router.bundle_project(fixture.root / "http-input.zip")

        def request(route, data=None, headers=None, method=None):
            request_headers = dict(headers or {})
            token = os.environ.get("MANGA_WEB_TEST_TOKEN")
            if token:
                request_headers.setdefault("Authorization", "Bearer " + token)
            req = urllib.request.Request(base + route, data=data, headers=request_headers, method=method)
            return urllib.request.urlopen(req, timeout=45)

        def poll(job, expected="complete"):
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                with request("/api/workflow?job=" + job["id"]) as response:
                    result = json.load(response)
                if result["status"] in ("complete", "failed"):
                    self.assertEqual(result["status"], expected, result.get("message"))
                    return result
                time.sleep(.25)
            self.fail("Worker did not finish in 60 seconds")

        boundary = uuid.uuid4().hex
        body = b""
        for key, value in [("action", "create"), ("mode", "restore")]:
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="chapter"; filename="project.zip"\r\nContent-Type: application/zip\r\n\r\n'.encode() + bundle.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
        with request("/api/workflow", body, {"Content-Type": "multipart/form-data; boundary=" + boundary, "X-Manga-Workflow": "1", "Idempotency-Key": uuid.uuid4().hex, "Origin": base}) as response:
            self.assertEqual(response.status, 202)
            job = json.load(response)
        poll(job)
        project_id = job["project"]
        with request("/api/workflow?project=" + project_id) as response:
            state = json.load(response)
        self.assertTrue(state["cast_approved"])
        self.assertEqual(state["project"]["chapter_id"], "web_integration_test")
        mutation_headers = {"Content-Type": "application/json", "X-Manga-Workflow": "1", "Idempotency-Key": uuid.uuid4().hex, "Origin": base}
        payload = {"project": project_id, "revision": state["revision"],
                   "action": "rename", "command": {"title": "HTTP revision check"}}
        idempotency_key = uuid.uuid4().hex
        keyed_headers = {**mutation_headers, "Idempotency-Key": idempotency_key}
        with request("/api/workflow", json.dumps(payload).encode(), keyed_headers) as response:
            first_rename = json.load(response)
            poll(first_rename)
        with request("/api/workflow", json.dumps(payload).encode(), keyed_headers) as response:
            duplicate = json.load(response)
        self.assertEqual(duplicate["id"], first_rename["id"])
        with request("/api/workflow?key=" + idempotency_key) as response:
            self.assertEqual(json.load(response)["id"], first_rename["id"])
        changed_payload = json.loads(json.dumps(payload))
        changed_payload["command"]["title"] = "Different request under same key"
        with self.assertRaises(urllib.error.HTTPError) as context:
            request("/api/workflow", json.dumps(changed_payload).encode(), keyed_headers)
        self.assertEqual(context.exception.code, 409)
        with request("/api/workflow?project=" + project_id) as response:
            current = json.load(response)
        self.assertNotEqual(current["revision"], state["revision"])
        payload["command"]["title"] = "Rejected stale HTTP edit"
        with request("/api/workflow", json.dumps(payload).encode(), mutation_headers) as response:
            failed = poll(json.load(response), expected="failed")
        self.assertIn("changed in another session", failed["message"])
        with request("/api/workflow?project=" + project_id) as response:
            self.assertEqual(json.load(response), current)
        for action in ("inspect", "render", "export", "bundle"):
            with request("/api/workflow?project=" + project_id) as response:
                revision = json.load(response)["revision"]
            command = {"scene_ids": ["scene_001"]} if action != "bundle" else {}
            payload = json.dumps({"project": project_id, "revision": revision, "action": action, "command": command}).encode()
            with request("/api/workflow", payload, {"Content-Type": "application/json", "X-Manga-Workflow": "1", "Idempotency-Key": uuid.uuid4().hex, "Origin": base}) as response:
                poll(json.load(response))
        route = "/api/asset?" + urlencode({"project": project_id, "path": "exports/chapter_narration.wav"})
        with request(route, headers={"Range": "bytes=0-43"}) as response:
            self.assertEqual(response.status, 206)
            header = response.read()
            self.assertEqual(len(header), 44)
            self.assertEqual(header[:4], b"RIFF")
        with request("/api/asset?" + urlencode({"project": project_id, "path": "bundle.zip", "download": "1"})) as response:
            self.assertEqual(response.read(2), b"PK")

        reader_headers = {"Authorization": "Bearer fixture-reader", "Content-Type": "application/json", "Origin": base}
        other_headers = {**reader_headers, "Authorization": "Bearer fixture-reader-two"}
        shared_body = {"title": "HTTP Manga", "chapter": "01", "notes": "first reader note", "reader": "forged"}
        with self.assertRaises(urllib.error.HTTPError) as denied:
            request("/api/shared/requests", json.dumps(shared_body).encode(), {**reader_headers, "Origin": "https://attacker.invalid"})
        self.assertEqual(denied.exception.code, 403)
        with request("/api/shared/requests", json.dumps(shared_body).encode(), reader_headers) as response:
            first_request = json.load(response)["request"]
        self.assertFalse(first_request["duplicate"])
        with request("/api/shared/requests", json.dumps(shared_body).encode(), reader_headers) as response:
            self.assertTrue(json.load(response)["request"]["duplicate"])
        shared_body.update(title="  http  manga ", chapter="1", notes="second reader note")
        with request("/api/shared/requests", json.dumps(shared_body).encode(), other_headers) as response:
            second_request = json.load(response)["request"]
        self.assertEqual(first_request["work_id"], second_request["work_id"])
        with request("/api/shared/requests", headers=reader_headers) as response:
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertEqual([item["id"] for item in json.load(response)["requests"]], [first_request["id"]])
        with self.assertRaises(urllib.error.HTTPError) as denied:
            request("/api/shared/admin", headers=reader_headers)
        self.assertEqual(denied.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as denied:
            request("/api/shared/requests", json.dumps({"id": second_request["id"]}).encode(), reader_headers, "DELETE")
        self.assertEqual(denied.exception.code, 404)
        admin_headers = {"Content-Type": "application/json", "Origin": base}

        def admin_action(action, **fields):
            payload = {"action": action, "work_id": first_request["work_id"], "actor": "forged", **fields}
            with request("/api/shared/admin", json.dumps(payload).encode(), admin_headers) as response:
                return json.load(response)["result"]

        admin_action("approve")
        admin_action("link", project_id=project_id)
        with request("/api/shared/admin") as response:
            self.assertIn("no-store", response.headers["Cache-Control"])
            work = json.load(response)["work"]
        selected = next(item for item in work if item["id"] == first_request["work_id"])
        self.assertEqual({item["notes"] for item in selected["requests"]}, {"first reader note", "second reader note"})
        self.assertIn("fixture-admin", selected["approved_by"])
        with request("/api/workflow?project=" + project_id) as response:
            snapshot = json.load(response)
        script_review = review_document(Project.model_validate(snapshot["project"]), "script", "scene_001")["command"]
        script_review["approve"] = True
        payload = {"project": project_id, "revision": snapshot["revision"], "action": "script", "command": script_review}
        with request("/api/workflow", json.dumps(payload).encode(), {**mutation_headers, "Idempotency-Key": uuid.uuid4().hex}) as response:
            poll(json.load(response))
        for action in ("render", "export"):
            with request("/api/workflow?project=" + project_id) as response:
                revision = json.load(response)["revision"]
            payload = {"project": project_id, "revision": revision, "action": action, "command": {"scene_ids": ["scene_001"]}}
            with request("/api/workflow", json.dumps(payload).encode(), {**mutation_headers, "Idempotency-Key": uuid.uuid4().hex}) as response:
                poll(json.load(response))
        with request("/api/workflow?project=" + project_id) as response:
            revision = json.load(response)["revision"]
        candidate = admin_action("prepare", revision=revision)
        candidate_url = "/api/shared/candidate?" + urlencode({"id": candidate["id"]})
        with self.assertRaises(urllib.error.HTTPError) as denied:
            request(candidate_url, headers=reader_headers)
        self.assertEqual(denied.exception.code, 403)
        with request(candidate_url, headers={"Range": "bytes=0-3"}) as response:
            self.assertEqual(response.read(), b"RIFF")
        review = admin_action("review", revision=revision, candidate_id=candidate["id"])
        with request("/api/shared/admin") as response:
            recovered = next(item for item in json.load(response)["work"] if item["id"] == first_request["work_id"])
        self.assertEqual(recovered["candidate"]["id"], candidate["id"])
        self.assertEqual(recovered["review"]["id"], review["id"])
        published = admin_action("publish", revision=revision, review_id=review["id"], expected_publication=None)
        with request("/api/shared/catalog", headers=reader_headers) as response:
            self.assertTrue(any(item["publication_id"] == published["id"] for item in json.load(response)["chapters"]))
        with request("/api/shared/requests", headers=reader_headers) as response:
            self.assertEqual(json.load(response)["requests"][0]["status"], "published")
        with request("/api/shared/playback?" + urlencode({"work": first_request["work_id"]}), headers=reader_headers) as response:
            audio_url = json.load(response)["url"]
        with self.assertRaises(urllib.error.HTTPError) as denied:
            request(audio_url, headers={"Authorization": ""})
        self.assertEqual(denied.exception.code, 401)
        with self.assertRaises(urllib.error.HTTPError) as denied:
            request(audio_url + "x", headers=reader_headers)
        self.assertEqual(denied.exception.code, 403)
        with request(audio_url, headers={"Cookie": "koetts-session=fixture-reader", "Range": "bytes=0-43", "Authorization": ""}) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read()[:4], b"RIFF")
        with self.assertRaises(urllib.error.HTTPError) as denied:
            request(audio_url, headers=other_headers)
        self.assertEqual(denied.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as context:
            request("/api/workflow", b"{}", {"Content-Type": "application/json"})
        self.assertEqual(context.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as context:
            request("/api/workflow", b"{}", {"Content-Type": "application/json", "X-Manga-Workflow": "1"})
        self.assertEqual(context.exception.code, 400)
        self.assertIn("Idempotency-Key", context.exception.read().decode())
        legacy_id = uuid.uuid4().hex
        legacy_path = Path(__file__).resolve().parents[2] / "results" / "web" / "jobs" / f"{legacy_id}.json"
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text(json.dumps({"id": legacy_id, "project": project_id, "status": "complete", "message": "Legacy"}))
        self.addCleanup(lambda: legacy_path.unlink(missing_ok=True))
        with request(f"/api/workflow?job={legacy_id}") as response:
            self.assertEqual(json.load(response)["message"], "Legacy")
        with self.assertRaises(urllib.error.HTTPError) as context:
            request("/api/asset?" + urlencode({"project": project_id, "path": "../../config.py"}))
        self.assertEqual(context.exception.code, 404)
