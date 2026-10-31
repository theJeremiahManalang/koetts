"""Offline tests for Agent Platform Gemini configuration and TTS transport."""
from __future__ import annotations

import io
import base64
import json
import os
import tempfile
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import google.auth
from google.auth.credentials import Credentials
from google import genai
from google.genai import types

from manga_tts.config import PipelineConfig, provider_configured
from manga_tts.gemini import GeminiRenderer, create_client


def wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\x01\x00" * 240)
    return buffer.getvalue()


def request(speakers: int = 1) -> dict:
    turns = [
        {"type": "text", "text": "  Exact reviewed line!  ", "annotations": [{"type": "speech_metadata", "style": "Warm; Alice; speech; bright; pause; pronunciation"}]},
    ]
    speech_config = [{"voice": "Kore"}]
    if speakers == 2:
        turns.append({"type": "text", "text": "Another exact line?", "annotations": [{
            "type": "speech_metadata", "speaker": "B", "style": "Low and calm"}]})
        turns[0]["annotations"][0]["speaker"] = "A"
        speech_config = {"speakers": [{"speaker": "A", "voice": "Kore"}, {"speaker": "B", "voice": "Puck"}]}
    return {"input": [{"type": "user_input", "content": turns}], "response_format": {"type": "audio"},
            "generation_config": {"speech_config": speech_config}}


class GeminiConfigTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_environment_config_reads_project_and_location_only(self):
        os.environ["GEMINI_API_KEY"] = "must-not-be-used"
        config = PipelineConfig.from_environment("workspace")
        self.assertIsNone(config.project)
        self.assertEqual(config.location, "us")
        self.assertFalse(config.provider_configured)
        self.assertFalse(provider_configured())
        os.environ["GOOGLE_CLOUD_PROJECT"] = "approved-project"
        os.environ["GOOGLE_CLOUD_LOCATION"] = "eu"
        config = PipelineConfig.from_environment("workspace")
        self.assertEqual((config.project, config.location), ("approved-project", "eu"))
        self.assertTrue(config.provider_configured)
        self.assertTrue(provider_configured())

    def test_no_api_key_fallback_and_explicit_enterprise_adc_client(self):
        os.environ["GEMINI_API_KEY"] = "ignored-key"
        with patch("google.genai.Client") as client:
            with self.assertRaisesRegex(ValueError, "GOOGLE_CLOUD_PROJECT"):
                create_client(PipelineConfig(workspace=tempfile.gettempdir()))
            client.assert_not_called()

            config = PipelineConfig(workspace=tempfile.gettempdir(), project="gcp-project")
            create_client(config)
            kwargs = client.call_args.kwargs
            self.assertEqual(kwargs["enterprise"], True)
            self.assertEqual((kwargs["project"], kwargs["location"]), ("gcp-project", "us"))
            self.assertEqual(kwargs["http_options"].retry_options.attempts, 1)
            self.assertNotIn("api_key", kwargs)


class GeminiRendererTests(unittest.TestCase):
    def render(self, request_payload):
        data = wav_bytes()
        response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[
            SimpleNamespace(inline_data=SimpleNamespace(data=data))]))])
        client = SimpleNamespace(models=SimpleNamespace(generate_content=patch_callable(response)))
        renderer = GeminiRenderer(client, "gemini-3.8-flash-tts", rpm=60, max_retries=1)
        self.assertEqual(renderer(request_payload), data)
        return client.models.generate_content.call_args.kwargs

    def test_single_speaker_maps_exact_text_style_voice_and_audio_config(self):
        call = self.render(request())
        self.assertEqual(call["model"], "gemini-3.8-flash-tts")
        self.assertEqual(call["contents"], [{"role": "user", "parts": [{
            "text": "  Exact reviewed line!  ", "speech_metadata": {
                "style": "Warm; Alice; speech; bright; pause; pronunciation"}}]}])
        self.assertEqual(call["config"], {"response_modalities": ["AUDIO"], "speech_config": {
            "voice_config": {"voice": "Kore"}}})

    def test_multi_speaker_maps_turn_metadata_and_voice_configs(self):
        call = self.render(request(2))
        self.assertEqual(call["contents"][0]["parts"], [
            {"text": "  Exact reviewed line!  ", "speech_metadata": {
                "speaker": "A", "style": "Warm; Alice; speech; bright; pause; pronunciation"}},
            {"text": "Another exact line?", "speech_metadata": {
                "speaker": "B", "style": "Low and calm"}},
        ])
        self.assertEqual(call["config"]["speech_config"], {"multi_speaker_voice_config": {
            "speaker_voice_configs": [
                {"speaker": "A", "voice_config": {"voice": "Kore"}},
                {"speaker": "B", "voice_config": {"voice": "Puck"}},
            ]}})

    def test_missing_and_invalid_audio_responses_fail_safely(self):
        for response in (SimpleNamespace(candidates=[]), SimpleNamespace(candidates=[SimpleNamespace(
                content=SimpleNamespace(parts=[SimpleNamespace(inline_data=SimpleNamespace(data=b"bad"))]))])):
            client = SimpleNamespace(models=SimpleNamespace(generate_content=patch_callable(response)))
            renderer = GeminiRenderer(client, "gemini-3.8-flash-tts", rpm=60, max_retries=1)
            with self.assertRaisesRegex(ValueError, "WAV"):
                renderer(request())

    def test_sdk_wire_payloads_single_and_multi_speaker(self):
        for speaker_count in (1, 2):
            with self.subTest(speaker_count=speaker_count):
                data = wav_bytes()
                wire_requests = []

                def respond(req: httpx.Request) -> httpx.Response:
                    wire_requests.append(req)
                    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{
                        "inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(data).decode("ascii")}
                    }]}}]})

                fake_credentials = SyntheticCredentials()
                mock_transport = httpx.MockTransport(respond)
                http_client = httpx.Client(transport=mock_transport)
                client = genai.Client(enterprise=True, project="synthetic-project", location="us",
                    credentials=fake_credentials,
                    http_options=types.HttpOptions(httpx_client=http_client,
                        retry_options=types.HttpRetryOptions(attempts=1)))
                try:
                    renderer = GeminiRenderer(client, "gemini-3.8-flash-tts", rpm=60, max_retries=1)
                    self.assertEqual(renderer(request(speaker_count)), data)
                finally:
                    client.close()
                    http_client.close()

                self.assertEqual(len(wire_requests), 1)
                req = wire_requests[0]
                self.assertEqual(req.url.host, "aiplatform.us.rep.googleapis.com")
                self.assertIn("Bearer synthetic-access-token", req.headers["authorization"])
                self.assertTrue(req.url.path.endswith("/publishers/google/models/gemini-3.8-flash-tts:generateContent"))
                body = json.loads(req.content)
                self.assertEqual(body["contents"][0]["role"], "user")
                self.assertEqual(body["contents"][0]["parts"], expected_wire_parts(speaker_count))
                self.assertEqual(body["generationConfig"]["responseModalities"], ["AUDIO"])
                speech_config = body["generationConfig"]["speechConfig"]
                if speaker_count == 1:
                    self.assertEqual(speech_config, {"voiceConfig": {"voice": "Kore"}})
                else:
                    self.assertEqual(speech_config, {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
                        {"speaker": "A", "voiceConfig": {"voice": "Kore"}},
                        {"speaker": "B", "voiceConfig": {"voice": "Puck"}},
                    ]}})

    def test_sdk_environment_api_keys_are_ignored_in_enterprise_mode(self):
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "explicit-project",
                                    "GOOGLE_CLOUD_LOCATION": "us",
                                    "GOOGLE_API_KEY": "ignored-google-key",
                                    "GEMINI_API_KEY": "ignored-gemini-key"}, clear=True), \
                patch("google.auth.default", return_value=(SyntheticCredentials(), "adc-project")) as adc_default:
            client = create_client(PipelineConfig(workspace=tempfile.gettempdir(),
                project="explicit-project", location="us"))
            try:
                self.assertEqual(client._api_client.project, "explicit-project")
                self.assertEqual(client._api_client.location, "us")
                self.assertIsNone(client._api_client.api_key)
                # Credential discovery stays lazy until the provider call.
                adc_default.assert_not_called()
                self.assertEqual(client._api_client._access_token(), "synthetic-access-token")
                adc_default.assert_called_once()
            finally:
                client.close()


def patch_callable(value):
    """Return a tiny callable mock without relying on a live SDK response type."""
    from unittest.mock import Mock
    return Mock(return_value=value)


class SyntheticCredentials(Credentials):
    """Minimal ADC credentials for requests intercepted by httpx.MockTransport."""
    def __init__(self):
        super().__init__()
        self.token = "synthetic-access-token"

    def refresh(self, request):
        self.token = "synthetic-access-token"

    def apply(self, headers, token=None):
        headers["authorization"] = f"Bearer {token or self.token}"

    def __eq__(self, other):
        return self is other


def expected_wire_parts(speakers: int) -> list[dict]:
    first = {"text": "  Exact reviewed line!  ", "speechMetadata": {
        "style": "Warm; Alice; speech; bright; pause; pronunciation"}}
    if speakers == 1:
        return [first]
    first["speechMetadata"]["speaker"] = "A"
    return [first, {"text": "Another exact line?", "speechMetadata": {
        "speaker": "B", "style": "Low and calm"}}]


if __name__ == "__main__":
    unittest.main()
