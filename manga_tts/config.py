"""Runtime configuration and protocol constants. Importing never reads secrets or creates clients."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from .schemas import Settings

PathLike = str | os.PathLike[str]
TEXT_POLICY_VERSION = 1
CACHE_REVISION = 2  # Package upgrade deliberately retires v1 planning/audio cache entries.
VERSION = 2
SAMPLE_RATE = 24000
UNKNOWN = "UNKNOWN"
NARRATOR = "NARRATOR"
VOICES = ["Kore", "Puck", "Aoede", "Leda", "Zephyr", "Charon", "Fenrir", "Orus", "Algenib", "Despina"]
DELIVERIES = ["speech", "thought", "shout", "whisper", "narration"]
DEFAULT_PROJECT_SETTINGS = {
    "planning_model": "gemini-3.8-flash", "tts_model": "gemini-3.8-flash-tts",
    "max_chars": 1200, "scene_pause": .65, "segment_pause": .12,
}
DEFAULT_RENDER_RPM = 9
DEFAULT_MAX_RETRIES = 5
DEFAULT_CLIENT_TIMEOUT_MS = 180000
MAX_ARCHIVE_BYTES = 1_000_000_000
MIN_OCR_IOU = .5
MAX_SILENCE_SEC = 30

class PipelineConfig(BaseModel):
    """Runtime-only options. Saved settings win; defaults apply only to new projects.

    Credentials never enter model dumps/repr, persisted projects or log records.
    Construction performs no environment lookup, filesystem writes or provider calls.
    """
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False, revalidate_instances="always")
    workspace: Path
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    defaults: Settings = Field(default_factory=lambda: Settings.model_validate(DEFAULT_PROJECT_SETTINGS))
    rpm: int = Field(default=DEFAULT_RENDER_RPM, ge=1, le=60)
    max_attempts: int = Field(default=DEFAULT_MAX_RETRIES, ge=1)
    timeout_ms: int = Field(default=DEFAULT_CLIENT_TIMEOUT_MS, ge=1)

    @field_validator("workspace", mode="before")
    @classmethod
    def path_input(cls, value: Any) -> Any:
        """Accept a path string as an explicit convenience; other fields remain strict."""
        return Path(value) if isinstance(value, str) else value

    @classmethod
    def from_environment(cls, workspace: PathLike, **options: Any) -> PipelineConfig:
        """Explicitly read GEMINI_API_KEY; no dotenv loading, I/O or API calls."""
        key = os.environ.get("GEMINI_API_KEY", "")
        return cls(workspace=Path(workspace), api_key=SecretStr(key) if key else None, **options)
