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
from urllib.parse import urlencode, urlparse

import test_audio_pipeline as fixtures

from manga_tts.schemas import RenderCommand


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

        def request(route, data=None, headers=None):
            req = urllib.request.Request(base + route, data=data, headers=headers or {})
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
        with request("/api/workflow", body, {"Content-Type": "multipart/form-data; boundary=" + boundary, "X-Manga-Workflow": "1", "Origin": base}) as response:
            self.assertEqual(response.status, 202)
            job = json.load(response)
        poll(job)
        project_id = job["project"]
        with request("/api/workflow?project=" + project_id) as response:
            state = json.load(response)
        self.assertTrue(state["cast_approved"])
        self.assertEqual(state["project"]["chapter_id"], "web_integration_test")
        mutation_headers = {"Content-Type": "application/json", "X-Manga-Workflow": "1", "Origin": base}
        payload = {"project": project_id, "revision": state["revision"],
                   "action": "rename", "command": {"title": "HTTP revision check"}}
        with request("/api/workflow", json.dumps(payload).encode(), mutation_headers) as response:
            poll(json.load(response))
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
            with request("/api/workflow", payload, {"Content-Type": "application/json", "X-Manga-Workflow": "1", "Origin": base}) as response:
                poll(json.load(response))
        route = "/api/asset?" + urlencode({"project": project_id, "path": "exports/chapter_narration.wav"})
        with request(route, headers={"Range": "bytes=0-43"}) as response:
            self.assertEqual(response.status, 206)
            header = response.read()
            self.assertEqual(len(header), 44)
            self.assertEqual(header[:4], b"RIFF")
        with request("/api/asset?" + urlencode({"project": project_id, "path": "bundle.zip", "download": "1"})) as response:
            self.assertEqual(response.read(2), b"PK")
        with self.assertRaises(urllib.error.HTTPError) as context:
            request("/api/workflow", b"{}", {"Content-Type": "application/json"})
        self.assertEqual(context.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as context:
            request("/api/asset?" + urlencode({"project": project_id, "path": "../../config.py"}))
        self.assertEqual(context.exception.code, 404)
