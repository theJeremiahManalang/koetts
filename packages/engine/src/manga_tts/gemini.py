"""Gemini stage implementation; public workflow commands live in PipelineRouter."""
from __future__ import annotations

import io
import logging
import re
import time
import wave
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from .config import DEFAULT_MAX_RETRIES, DEFAULT_RENDER_RPM, PipelineConfig

T = TypeVar("T")
LOGGER = logging.getLogger("manga_tts")
LOGGER.addHandler(logging.NullHandler())


def create_client(config: PipelineConfig) -> Any:
    """Create an Agent Platform client lazily, authenticating with Application Default Credentials."""
    if not config.project:
        raise ValueError("Configure GOOGLE_CLOUD_PROJECT or inject a client_factory")
    from google import genai
    from google.genai import types
    return genai.Client(enterprise=True, project=config.project, location=config.location,
                        http_options=types.HttpOptions(timeout=config.timeout_ms,
                            retry_options=types.HttpRetryOptions(attempts=1)))



def retry_api(operation: Callable[[], T], *, name: str, max_attempts: int = DEFAULT_MAX_RETRIES) -> T:
    """Run an injected API operation with bounded transient retries; return its result.

    Retries only 429/500/502/503/504, TimeoutError and ConnectionError with bounded
    backoff. All other failures propagate immediately. Each attempt may incur cost.
    Logs operation/attempt/outcome/status only, never exception text or payloads.
    Does not change models, create competing takes, persist state, or catch parsing errors.
    """
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    for attempt in range(1, max_attempts + 1):
        LOGGER.info("api_attempt", extra={"operation": name, "attempt": attempt, "outcome": "started"})
        try:
            result = operation()
        except Exception as exc:
            raw_code = str(getattr(exc, "code", ""))
            code = raw_code if raw_code in {"400", "401", "403", "404", "429", "500", "502", "503", "504"} else "other"
            transient = code in {"429", "500", "502", "503", "504"} or isinstance(exc, (TimeoutError, ConnectionError))
            retry = transient and attempt < max_attempts
            LOGGER.warning("api_failure", extra={"operation": name, "attempt": attempt,
                "outcome": "retry" if retry else "failed", "status_code": code})
            if not retry:
                raise
            time.sleep(min(30, 2 ** (attempt - 1) * 2))
        else:
            LOGGER.info("api_success", extra={"operation": name, "attempt": attempt, "outcome": "success"})
            return result
    raise RuntimeError("Retry loop exhausted without an outcome")


def error_summary(exc: Exception, secrets: Iterable[str] = ()) -> str:
    """Return a bounded diagnostic for exc, redacting explicit secrets and key patterns.

    Adds hints for common SDK status codes; does not log, persist or mutate inputs."""
    message = str(exc)
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[REDACTED]")
    message = re.sub(r"(?i)(?:AIza[\w-]+|AQ\.[\w.-]+|sk-[\w-]+)", "[REDACTED]", message)
    message = re.sub(r"(?i)Bearer\s+[^\s\"'}]+", "Bearer [REDACTED]", message)
    message = re.sub(r"(?i)((?:api[_-]?key|key|authorization)\s*[=:]\s*)[^\s&,\"'}]+", r"\1[REDACTED]", message)
    code = getattr(exc, "code", None)
    hint = {"400": "Check the model and structured-output schema.", "401": "Check Application Default Credentials.",
            "403": "Check API/project access.", "404": "Check that this model is available to your account.",
            "429": "Quota/rate limit reached; wait or check your project quota."}.get(str(code), "")
    return f"{type(exc).__name__}: {message[:1000]} {hint}".strip()


class GeminiRenderer:
    """Callable adapter from compiled speech requests to Gemini WAV bytes; no project persistence."""
    def __init__(self, client: Any, model: str, rpm: int = DEFAULT_RENDER_RPM, max_retries: int = DEFAULT_MAX_RETRIES) -> None:
        """Configure an injected client, model, request RPM and maximum total attempts.

        No requests occur here. Raises ValueError for invalid rate/attempt limits."""
        if type(rpm) is not int or not 1 <= rpm <= 60 or type(max_retries) is not int or max_retries < 1:
            raise ValueError("Invalid rate/retry settings")
        self.client, self.model, self.interval = client, model, 60 / rpm
        self.max_retries, self.last_call = max_retries, None

    def __call__(self, request: dict[str, Any]) -> bytes:
        """Send reviewed speech through Gemini 3.8 TTS and return its complete WAV bytes.

        May incur cost and sleep for pacing/backoff. Retries transient status/network errors
        up to max_retries total attempts; permanent errors propagate immediately. Raises
        ValueError for missing or invalid WAV audio; SDK errors propagate."""
        from .tts import validate_speech_request
        validate_speech_request(request)
        parts = []
        for item in request["input"][0]["content"]:
            metadata = item["annotations"][0]
            speech_metadata = {"style": metadata["style"]}
            if "speaker" in metadata:
                speech_metadata["speaker"] = metadata["speaker"]
            parts.append({"text": item["text"], "speech_metadata": speech_metadata})
        voices = request["generation_config"]["speech_config"]
        if isinstance(voices, list):
            speech_config = {"voice_config": {"voice": voices[0]["voice"]}}
        else:
            speech_config = {"multi_speaker_voice_config": {"speaker_voice_configs": [
                {"speaker": item["speaker"], "voice_config": {"voice": item["voice"]}}
                for item in voices["speakers"]
            ]}}
        contents = [{"role": "user", "parts": parts}]
        config = {"response_modalities": ["AUDIO"], "speech_config": speech_config}
        def send():
            if self.last_call is not None:
                time.sleep(max(0, self.interval - (time.monotonic() - self.last_call)))
            self.last_call = time.monotonic()
            return self.client.models.generate_content(model=self.model, contents=contents, config=config)
        response = retry_api(send, name="synthesis", max_attempts=self.max_retries)
        candidates = getattr(response, "candidates", None) or []
        content = getattr(candidates[0], "content", None) if candidates else None
        audio = next((getattr(part, "inline_data", None) for part in (getattr(content, "parts", None) or [])
                      if getattr(getattr(part, "inline_data", None), "data", None)), None)
        data = getattr(audio, "data", None)
        if not isinstance(data, bytes) or not data:
            LOGGER.warning("synthesis_response_invalid", extra={"operation": "synthesis", "outcome": "missing_audio"})
            raise ValueError("Gemini returned no audio WAV")
        try:
            with wave.open(io.BytesIO(data), "rb") as wav:
                valid_header = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getcomptype()) == (24000, 1, 2, "NONE")
                frames = wav.getnframes()
                pcm = wav.readframes(frames)
                if not valid_header or frames <= 0 or len(pcm) != frames * 2:
                    raise ValueError
        except (wave.Error, EOFError, ValueError):
            LOGGER.warning("synthesis_response_invalid", extra={"operation": "synthesis", "outcome": "invalid_wav"})
            raise ValueError("Gemini returned an invalid mono 24 kHz 16-bit PCM WAV") from None
        return data
