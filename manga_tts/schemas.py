"""Strict Pydantic data contracts and JSON serialization helpers.

Saved/vendor models preserve extra evidence. Commands forbid extra fields. These
models validate shape; script services enforce cross-record and approval rules.
"""
from __future__ import annotations
from typing import Any, Callable, Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

JSONData = dict[str, Any]
class Contract(BaseModel):
    """Strict JSON contract preserving upstream and legacy evidence fields."""
    model_config = ConfigDict(strict=True, extra="allow", allow_inf_nan=False, revalidate_instances="always")

class Settings(Contract):
    """Persisted user settings; operational retry limits are configured separately."""
    planning_model: str = Field(min_length=1)
    tts_model: str = Field(min_length=1)
    max_chars: int = Field(ge=100)
    scene_pause: float = Field(ge=0, le=30)
    segment_pause: float = Field(ge=0, le=30)


class Reaction(Contract):
    """Human-reviewed vocal event or intentional silence replacing a source utterance."""
    text: str
    silence_sec: float


class CastMember(Contract):
    """One reusable speaker profile; reference paths are relative to the workspace."""
    name: str
    voice: str
    pronunciation: str
    references: list[str]
    role: str = ""
    is_generic: bool = False
    description: str = ""
    personality: str = ""
    acting_notes: str = ""
    profile_markdown: str = ""
    profile_path: str = ""


class Source(Contract):
    """Stable bubble identity, immutable OCR evidence, and editable reviewed wording/order."""
    source_id: str
    page_id: str
    panel_id: str | None
    bbox: list[float]
    original_text: str
    text: str
    upstream_essential: bool
    include: bool
    speaker_id: str
    scene_id: str
    order: int
    turn_group: str
    delivery: str
    emotion: str
    style: str
    pacing: str
    reaction: Reaction | None
    reason: str = ""
    magi_links: list[dict[str, Any]] = Field(default_factory=list)


class ChapterText(Contract):
    """Minimum upstream bubble contract; extra Magi evidence fields are preserved."""
    text_id: str
    bbox: list[float]
    reading_order: int
    ocr_text: str
    panel_id: str | None = None
    is_essential: bool = False


class ChapterPage(Contract):
    """Minimum input page; previews/originals and vendor evidence stay in the ZIP."""
    page_id: str
    page_index: int
    texts: list[ChapterText]
    characters: list[dict[str, Any]]


class ChapterInput(Contract):
    """chapter_analysis.json entry point inside the source ZIP."""
    chapter_id: str
    pages: list[ChapterPage]


class CastInput(Contract):
    """One imported cast.json entry; named speakers require reference images."""
    speaker_id: str
    name: str
    references: list[str] = Field(default_factory=list)
    voice: str | None = None
    pronunciation: str = ""
    profile_path: str = ""
    role: str = ""
    is_generic: bool = False
    description: str = ""
    personality: str = ""
    acting_notes: str = ""


class CastManifest(Contract):
    """Named reference ZIP manifest, located at the ZIP root."""
    characters: list[CastInput]


class Appearance(Contract):
    """Detected visual appearance; Magi fields remain evidence, not cast identity."""
    char_id: str
    page_id: str
    crop_path: str
    speaker_id: str
    rejected: bool
    reason: str
    bbox: list[float] = Field(default_factory=list)


class Turn(Contract):
    """Authoritative render transcript; excluded turns never enter speech requests."""
    turn_id: str
    kind: str
    speaker_id: str
    source_ids: list[str]
    text: str
    include: bool
    delivery: str
    emotion: str
    style: str
    pacing: str
    silence_sec: float
    evidence_source_ids: list[str] = Field(default_factory=list)
    anchor_source_id: str | None = None


class Scene(Contract):
    """Ordered turns with shared visual/acting context; may cross page boundaries."""
    scene_id: str
    title: str
    context: str
    turns: list[Turn]


class ProposedAppearance(Contract):
    """Proposed identity decision; loaded only by explicit review action."""
    char_id: str
    speaker_id: str
    rejected: bool
    reason: str


class ProposedSource(Contract):
    """Proposal wording and acting; source inclusion is deliberately not AI-controlled."""
    source_id: str
    text: str
    speaker_id: str
    scene_id: str
    turn_group: str
    delivery: str
    emotion: str
    style: str
    pacing: str
    reason: str
    reaction_text: str


class ProposedScene(Contract):
    """Proposed scene boundary and visible-evidence narration."""
    scene_id: str
    title: str
    context: str
    narration: str
    evidence_source_ids: list[str]


class Proposal(Contract):
    """Complete ordered proposal; validated against PLAN_SCHEMA before application."""
    appearances: list[ProposedAppearance]
    sources: list[ProposedSource]
    scenes: list[ProposedScene]


class SpeechMetadata(Contract):
    """Sustained acting instructions attached to exact, approved spoken text."""
    type: str
    style: str
    speaker: str = ""


class SpeechText(Contract):
    """One speaker turn in a Gemini interaction."""
    type: str
    text: str
    annotations: list[SpeechMetadata]


class UserInput(Contract):
    """Gemini interaction input block."""
    type: str
    content: list[SpeechText]


class Voice(Contract):
    """Single-speaker voice configuration."""
    voice: str


class SpeakerVoice(Voice):
    """Named voice for a two-speaker interaction."""
    speaker: str


class MultiVoice(Contract):
    """Two named speaker configurations."""
    speakers: list[SpeakerVoice]


class GenerationConfig(Contract):
    """Gemini speech generation configuration."""
    speech_config: list[Voice] | MultiVoice


class AudioFormat(Contract):
    """Requested response modality."""
    type: str


class SpeechRequest(Contract):
    """Exact SDK payload, excluding the separately configured model."""
    input: list[UserInput]
    response_format: AudioFormat
    generation_config: GenerationConfig


class AudioInfo(Contract):
    """Validated mono PCM WAV metadata."""
    frames: int
    duration_sec: float
    peak: float
    clipped_samples: int


class Take(AudioInfo):
    """Retained WAV and checksum; indexed by complete segment request signature."""
    take_id: str
    path: str
    audio_sha256: str


class Segment(Contract):
    """Compiled synthesis unit, or local intentional silence with request=None."""
    segment_id: str
    scene_id: str
    source_ids: list[str]
    turns: list[Turn]
    silence_sec: float
    request: SpeechRequest | None
    signature: str


class TimelineSegment(Contract):
    """Export timing at segment granularity; not bubble-level forced alignment."""
    segment_id: str
    scene_id: str
    source_ids: list[str]
    turn_ids: list[str]
    start_sec: float
    end_sec: float
    signature: str
    take: Take


class ExportManifest(Contract):
    """render_manifest.json contract."""
    chapter_id: str
    settings: Settings
    segments: list[TimelineSegment]


class SavedProposal(Contract):
    """Planning cache provenance plus the unapproved proposal."""
    cache_key: str
    evidence: str
    data: Proposal


class ProjectFields(Contract):
    """Persisted project.json contract; validated by Pydantic at workflow seams.

    chapter retains the upstream Magi JSON, including vendor-specific evidence fields.
    No credentials, clients, or unapplied widget drafts belong in this object.
    """
    version: int
    chapter_id: str
    title: str = Field(default="", max_length=120)
    source_review_signature: str | None = None
    page_order: list[str] = Field(default_factory=list)
    panel_order: dict[str, list[str]] = Field(default_factory=dict)
    proposal_applied_signature: str | None = None
    web_export_signature: str | None = None
    web_export_scenes: list[str] = Field(default_factory=list)
    chapter: dict[str, Any]
    settings: Settings
    sources: list[Source]
    cast: dict[str, CastMember]
    appearances: list[Appearance]
    scenes: list[Scene]
    takes: dict[str, list[Take]]
    selected_takes: dict[str, str]
    approvals: dict[str, str]
    cast_approval: str | None
    proposal: SavedProposal | None
    render_selection: list[str] = Field(default_factory=list)

class Project(ProjectFields):
    """Current version-2 persisted project and detached router snapshot."""
    version: Literal[2]


class ProjectV1(ProjectFields):
    """Validation contract used solely to migrate legacy bundles."""
    version: Literal[1]

class Renderer(Protocol):
    """Injectable raw Gemini-payload to WAV adapter; may incur cost."""
    def __call__(self, request: JSONData) -> bytes:
        """Return mono 24 kHz 16-bit PCM WAV bytes or raise a provider error."""
        ...

class Command(BaseModel):
    """Strict app/UI command; unknown fields are rejected."""
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False, revalidate_instances="always")

class CastCreate(Command):
    """Create a named character using an existing detected crop as reference."""
    char_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=120)
    voice: str = Field(min_length=1, max_length=120)


class CastEdit(Command):
    """Editable profile fields; identity IDs and references are not rewritten."""
    speaker_id: str
    name: str = Field(min_length=1)
    voice: str = Field(min_length=1)
    pronunciation: str
    acting_notes: str

class AppearanceEdit(Command):
    """Reviewed detection decision."""
    char_id: str
    speaker_id: str
    rejected: bool

class CastReferenceCreate(Command):
    """New draft character anchored to an existing detected appearance."""
    speaker_id: str = Field(pattern=r"^CHARACTER_[A-Za-z0-9_]+$", max_length=120)
    char_id: str = Field(min_length=1)


class CastReview(Command):
    """Complete cast/gallery review, optionally approved atomically."""
    cast: list[CastEdit]
    appearances: list[AppearanceEdit]
    new_characters: list[CastReferenceCreate] = Field(default_factory=list)
    approve: bool = False

class SourceEdit(Command):
    """Editable source fields, excluding immutable OCR and upstream labels."""
    source_id: str
    speaker_origin: Literal["manual"] | None = None
    include: bool
    speaker_id: str
    order: int
    scene_id: str = Field(min_length=1)
    turn_group: str = Field(min_length=1)
    text: str
    delivery: str
    emotion: str
    style: str
    pacing: str
    reaction: Reaction | None

class SourceReview(Command):
    """Complete source ordering/edit transaction; rebuilds dialogue turns."""
    sources: list[SourceEdit]
    page_order: list[str] | None = None
    panel_order: dict[str, list[str]] | None = None

class TurnEdit(Command):
    """Editable final transcript/acting fields; source evidence links stay immutable."""
    turn_id: str
    speaker_origin: Literal["manual"] | None = None
    include: bool
    speaker_id: str
    text: str
    delivery: str
    emotion: str
    style: str
    pacing: str
    silence_sec: float = Field(ge=0, le=30)

class SceneReview(Command):
    """Complete scene edit and optional approval in one transaction."""
    scene_id: str
    title: str
    context: str
    turns: list[TurnEdit]
    approve: bool = False


class SceneBatchReview(Command):
    """Save multiple scene drafts and explicit approvals as one transaction."""
    scenes: list[SceneReview] = Field(min_length=1)

class NarrationInsert(Command):
    """Visible-evidence narration at a reviewed turn boundary."""
    scene_id: str
    position: int = Field(ge=0)
    text: str = Field(min_length=1)
    evidence_source_ids: list[str] = Field(min_length=1)

class SettingsUpdate(Command):
    """Explicit settings replacement; invalidates scene approvals."""
    settings: Settings

class RenderSelection(Command):
    """Persist scene selection without approving or rendering it."""
    scene_ids: list[str]

class RenderCommand(RenderSelection):
    """Explicit synthesis request; regenerate only listed selected segment IDs."""
    regenerate: list[str] = Field(default_factory=list)

class TakeSelection(Command):
    """Choose an intact retained take for a current segment signature."""
    segment_id: str
    take_id: str

class ProgressEvent(Contract):
    """Payload-free progress suitable for Colab or a future app worker."""
    stage: str
    status: str
    message: str
    scene_id: str | None = None
    segment_id: str | None = None

ProgressCallback = Callable[[ProgressEvent], None]

class MigrationReport(Contract):
    """One-time schema upgrade; historical artifacts remain on disk."""
    from_version: int
    to_version: int
    message: str

class RenderResult(Contract):
    """Selected compiled segments and detached post-operation project."""
    project: Project
    segments: list[Segment]

class ExportResult(Contract):
    """Filesystem outputs; no synthesis occurs during export."""
    wav_path: str
    export_directory: str

class Failure(Contract):
    """Safe machine-readable workflow error; no rejected values or secrets."""
    code: str
    stage: str
    message: str
    retryable: bool = False
    fields: list[str] = Field(default_factory=list)

class WorkflowError(ValueError):
    """Public workflow failure exposing a safe structured detail model."""
    def __init__(self, detail: Failure) -> None:
        self.detail = detail
        super().__init__(detail.message)


def dump(value: BaseModel) -> JSONData:
    """Return detached Python JSON data, preserving absent optional fields and evidence."""
    return value.model_dump(mode="python", exclude_unset=True)


def validate_contract(value: Any, contract: Any, label: str = "input") -> None:
    """Validate without mutation; report locations only, never rejected values/context."""
    try:
        TypeAdapter(contract).validate_python(value, strict=True)
    except ValidationError as exc:
        locations = [label + "." + ".".join(map(str, error["loc"])) for error in exc.errors(include_input=False, include_context=False)]
        raise ValueError("Invalid fields: " + ", ".join(locations)) from None
