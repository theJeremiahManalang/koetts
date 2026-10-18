"""Gemini stage implementation; public workflow commands live in PipelineRouter."""
from __future__ import annotations
import base64
import logging
import re
import time
from typing import Any, Callable, Iterable, TypeVar
from .config import DEFAULT_MAX_RETRIES, DEFAULT_RENDER_RPM, PipelineConfig
T = TypeVar("T")
LOGGER = logging.getLogger("manga_tts")
LOGGER.addHandler(logging.NullHandler())


def create_client(config: PipelineConfig) -> Any:
    """Create a provider client lazily from runtime-only credentials; no generation call.

    Raises ValueError without a key. The SDK is optional until this function is used.
    """
    if not config.api_key or not config.api_key.get_secret_value():
        raise ValueError("Configure GEMINI_API_KEY or inject a client_factory")
    from google import genai
    return genai.Client(api_key=config.api_key.get_secret_value(), http_options={"timeout": config.timeout_ms})



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
    hint = {"400": "Check the model and structured-output schema.", "401": "Check the API key.",
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
        """Send request through client.interactions.create and return decoded audio bytes.

        May incur cost and sleep for pacing/backoff. Retries transient status/network errors
        up to max_retries total attempts; permanent errors propagate immediately. Raises
        ValueError for missing audio; decoding/SDK errors propagate. WAV validation is the caller responsibility."""
        from .tts import validate_speech_request
        validate_speech_request(request)
        def send():
            if self.last_call is not None:
                time.sleep(max(0, self.interval - (time.monotonic() - self.last_call)))
            self.last_call = time.monotonic()
            return self.client.interactions.create(model=self.model, **request)
        response = retry_api(send, name="synthesis", max_attempts=self.max_retries)
        audio = getattr(response, "output_audio", None)
        if not audio or not getattr(audio, "data", None):
            LOGGER.warning("synthesis_response_invalid", extra={"operation": "synthesis", "outcome": "missing_audio"})
            raise ValueError("Gemini returned no audio")
        return base64.b64decode(audio.data, validate=True)
