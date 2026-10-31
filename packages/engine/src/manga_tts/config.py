"""Runtime configuration and protocol constants. Importing never reads secrets or creates clients."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .schemas import Settings

PathLike = str | os.PathLike[str]
TEXT_POLICY_VERSION = 1
CACHE_REVISION = 2  # Project/review cache revision; provider changes use dedicated cache identities.
PLANNING_BACKEND_VERSION = 2
SPEECH_BACKEND_VERSION = 2
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


def provider_configured() -> bool:
    """Return whether an explicit Google Cloud project is configured; never inspect ADC."""
    return bool(os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip())

class PipelineConfig(BaseModel):
    """Runtime-only options. Saved settings win; defaults apply only to new projects.

    Credentials never enter model dumps/repr, persisted projects or log records.
    Construction performs no environment lookup, filesystem writes or provider calls.
    """
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False, revalidate_instances="always")
    workspace: Path
    project: str | None = Field(default=None, min_length=1)
    location: str = Field(default="us", min_length=1)
    defaults: Settings = Field(default_factory=lambda: Settings.model_validate(DEFAULT_PROJECT_SETTINGS))
    rpm: int = Field(default=DEFAULT_RENDER_RPM, ge=1, le=60)
    max_attempts: int = Field(default=DEFAULT_MAX_RETRIES, ge=1)
    timeout_ms: int = Field(default=DEFAULT_CLIENT_TIMEOUT_MS, ge=1)

    @property
    def provider_configured(self) -> bool:
        """Whether this config names a project, without checking credentials or initializing a client."""
        return bool(self.project)

    @field_validator("workspace", mode="before")
    @classmethod
    def path_input(cls, value: Any) -> Any:
        """Accept a path string as an explicit convenience; other fields remain strict."""
        return Path(value) if isinstance(value, str) else value

    @classmethod
    def from_environment(cls, workspace: PathLike, **options: Any) -> PipelineConfig:
        """Read explicit Agent Platform project/location; no ADC lookup or API calls."""
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip() or None
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us")
        options.setdefault("project", project)
        options.setdefault("location", location)
        return cls(workspace=Path(workspace), **options)
