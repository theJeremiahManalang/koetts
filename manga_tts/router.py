"""Synchronous application interface: typed commands, owned state and durable checkpoints.

One router owns one workspace. Public snapshots are detached; callers never edit live
state. This is not a concurrent writer, HTTP server or background job scheduler.
"""
from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Mapping
from functools import wraps
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

from pydantic import ValidationError

from . import resolution, script, storage, tts
from .config import VERSION, PathLike, PipelineConfig
from .gemini import LOGGER, GeminiRenderer, create_client
from .persistence import PersistenceConflict, ProjectWriter, _copy_overlays
from .schemas import (
    CastCreate,
    CastMember,
    CastReview,
    ExportResult,
    Failure,
    MigrationReport,
    NarrationInsert,
    ProgressCallback,
    ProgressEvent,
    Project,
    Proposal,
    RenderCommand,
    Renderer,
    RenderResult,
    RenderSelection,
    SceneBatchReview,
    SceneReview,
    Segment,
    SettingsUpdate,
    SourceReview,
    TakeSelection,
    WorkflowError,
    dump,
)

P = ParamSpec("P")
R = TypeVar("R")


def operation(stage: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Expose safe errors at the app seam without logging rejected values or tracebacks."""
    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        @wraps(function)
        def run(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return function(*args, **kwargs)
            except WorkflowError:
                raise
            except PersistenceConflict as exc:
                raise WorkflowError(Failure(code=exc.code, stage="persistence", message=str(exc))) from None
            except Exception as exc:
                fields: list[str] = []
                code, message, retryable = "operation_failed", f"The {stage} operation failed. Check inputs, approvals and workspace files.", False
                if isinstance(exc, ValidationError):
                    fields = [".".join(map(str, error["loc"])) for error in exc.errors(include_input=False, include_context=False)]
                    code, message = "invalid_command", "Invalid fields: " + ", ".join(fields)
                elif isinstance(exc, ImportError):
                    code, message = "missing_dependency", "Install requirements-audio.txt for provider calls."
                elif isinstance(exc, (TimeoutError, ConnectionError)):
                    code, message, retryable = "provider_unavailable", "Gemini could not complete the request. Completed work is retained; retry explicitly.", True
                elif str(getattr(exc, "code", "")) in {"400", "401", "403", "404", "429", "500", "502", "503", "504"}:
                    status = str(exc.code)  # type: ignore[attr-defined]
                    code, message = "provider_" + status, "Gemini returned status " + status + ". Check access, model availability, quota or request configuration."
                    retryable = status in {"429", "500", "502", "503", "504"}
                elif isinstance(exc, ValueError):
                    code = "review_required"
                    # Only fixed, actionable messages cross the seam. Never forward
                    # arbitrary provider text or Pydantic's rejected input repr.
                    text = str(exc)
                    explanations = {
                        "replacement character": "Lost text remains. Correct it from the page image or exclude it before approval.",
                        "text repairs": "Review and apply the suggested text repairs before approval.",
                        "Approve the current cast": "Approve the current cast before approving or rendering scenes.",
                        "unapproved": "The scene is changed or unapproved. Review and approve it before rendering.",
                        "Resolve or reject": "Resolve or reject every appearance before approving the cast.",
                        "Resolve or exclude": "Resolve or exclude every included speaker before approval.",
                        "Punctuation-only": "Approve a vocalization, intentional silence or exclusion for punctuation-only speech.",
                        "Use supported momentary vocal tags": "Unsupported vocal tag. Use <gasp>, <breath>, <sigh>, <laugh>, <cough>, or <short pause>. Put action directions in Acting direction.",
                        "Excluded source is in an included turn": "A spoken turn uses an excluded source. Uncheck Include for that turn, or include its source in Source & reading order before approving.",
                        "Scene turns must cover source bubbles": "The script no longer matches the reviewed sources. Apply Source & reading order again, then review the rebuilt script.",
                        "neither speech nor intentional silence": "An included turn is empty. Enter spoken wording, set intentional silence, or uncheck Include before approving.",
                        "existing project": "Choose a new workspace for restoration; an existing project cannot be replaced.",
                        "Project exists": "Resume the existing project or choose a new workspace.",
                        "No visual evidence": "Page images or annotated previews are missing from this workspace.",
                        "no proposal text": "Gemini returned no proposal text. Inspect planning_cache response diagnostics.",
                        "invalid proposal JSON": "Gemini returned invalid JSON. Inspect planning_cache response diagnostics.",
                        "Proposal validation failed": "The proposal is invalid. Inspect planning_cache response diagnostics.",
                        "Visual evidence changed": "Visual evidence changed. Generate a fresh proposal before applying it.",
                        "Missing current audio": "Current audio is missing. Render the selected approved scenes before export.",
                        "MP3 encoder unavailable": "MP3 export needs the audio dependencies. Install requirements-audio.txt, then export again.",
                        "No active project": "Create, load or restore a project before this operation.",
                        "Configure GEMINI_API_KEY": "Configure GEMINI_API_KEY in the environment or Colab Secrets, or inject a configured client.",
                    }
                    message = next((safe for key, safe in explanations.items() if key in text), message)
                LOGGER.warning("workflow_failed", extra={"stage": stage, "outcome": "failed", "failure_code": code})
                raise WorkflowError(Failure(code=code, stage=stage, message=message, retryable=retryable, fields=fields)) from None
        return run
    return decorate


class PipelineRouter:
    """Own one validated project and coordinate synchronous workflow commands.

    client_factory() returns a configured provider client; renderer_factory(client,
    model) returns a raw request-to-WAV callable. Both are lazy. Successful commands
    autosave; failed edit/approval validation leaves applied state unchanged. Rendering
    publishes one durable segment at a time, deliberately retaining partial progress.
    """

    def __init__(self, config: PipelineConfig, client_factory: Callable[[], Any] | None = None,
                 renderer_factory: Callable[[Any, str], Renderer] | None = None, *,
                 persistence: ProjectWriter | None = None) -> None:
        """Retain configuration/adapters without I/O, clients, panels or paid calls."""
        self._config = PipelineConfig.model_validate(config).model_copy(deep=True)
        self._client_factory, self._renderer_factory = client_factory, renderer_factory
        self._persistence = persistence
        self._persistence_revision_id: str | None = None
        self._client: Any = None
        self._renderer: Renderer | None = None
        self._project: Project | None = None
        self._listeners: list[Callable[[int], None]] = []
        self._revision = 0
        self._migration: MigrationReport | None = None

    @property
    def root(self) -> Path:
        """Workspace path, without creating directories."""
        return self._config.workspace

    @property
    def revision(self) -> int:
        """Runtime revision, incremented after each durable state publication."""
        return self._revision

    @property
    def project(self) -> Project:
        """Return a deep detached snapshot; modifications cannot alter live state."""
        if self._project is None:
            raise WorkflowError(Failure(code="no_project", stage="project", message="Create, load or restore a project first."))
        return self._project.model_copy(deep=True)

    @property
    def migration(self) -> MigrationReport | None:
        """Detached one-time migration summary for the current load/restore operation."""
        return self._migration.model_copy(deep=True) if self._migration else None

    def subscribe(self, listener: Callable[[int], None]) -> Callable[[], None]:
        """Subscribe to revisions; return an unsubscribe callback. Never exposes state."""
        self._listeners.append(listener)
        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)
        return unsubscribe

    def _notify(self) -> None:
        self._revision += 1
        for callback in list(self._listeners):
            try:
                callback(self._revision)
            except Exception:
                # A presentation failure must not roll back an already saved command.
                LOGGER.warning("observer_failed", extra={"stage": "notification", "outcome": "failed"})

    def _data(self) -> dict[str, Any]:
        if self._persistence is not None and self._persistence.materialization_pending:
            revision = self._persistence.load(self.root)
            self._persistence_revision_id = revision.revision_id if revision is not None else None
            self._project = Project.model_validate(storage.load_project(self.root))
        return dump(self.project)

    def _commit(self, candidate: dict[str, Any],
                workspace_overlays: Mapping[str, str | Path] | None = None) -> Project:
        model = Project.model_validate(candidate)
        if self._persistence is None:
            _copy_overlays(self.root, workspace_overlays)
            storage.save_project(dump(model), self.root)
        else:
            revision = self._persistence.commit(
                self.root, dump(model), self._persistence_revision_id, workspace_overlays
            )
            self._persistence_revision_id = revision.revision_id
        self._project = model
        self._notify()
        if self._persistence is not None and self._persistence.materialization_pending:
            raise WorkflowError(Failure(
                code="checkpoint_materialization_pending", stage="persistence",
                message="The durable revision was accepted, but the local workspace could not refresh. Reload before continuing.",
            ))
        return self.project

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._client_factory() if self._client_factory else create_client(self._config)
        return self._client

    def _get_renderer(self) -> Renderer:
        if self._renderer is None:
            client, model = self._get_client(), self.project.settings.tts_model
            self._renderer = (self._renderer_factory(client, model) if self._renderer_factory else
                              GeminiRenderer(client, model, rpm=self._config.rpm, max_retries=self._config.max_attempts))
        return self._renderer

    def _event(self, callback: ProgressCallback | None, stage: str, status: str, message: str,
               scene_id: str | None = None, segment_id: str | None = None) -> None:
        if callback:
            callback(ProgressEvent(stage=stage, status=status, message=message, scene_id=scene_id, segment_id=segment_id))

    @operation("create")
    def create_project(self, chapter_zip: PathLike, references_zip: PathLike | None = None,
                       originals_zip: PathLike | None = None) -> Project:
        """Extract/recover a new chapter and autosave it; no API calls. Existing projects are refused."""
        candidate = storage.new_project(chapter_zip, self.root, references_zip, originals_zip, persist=False)
        candidate["settings"] = dump(self._config.defaults)
        self._migration, self._renderer = None, None
        return self._commit(candidate)

    @operation("metadata")
    def update_metadata(self, metadata: dict[str, Any]) -> Project:
        """Commit transport-owned project metadata through the normal persistence seam."""
        allowed = {"title", "source_review_signature", "proposal_applied_signature",
                   "web_export_signature", "web_export_scenes"}
        if not isinstance(metadata, dict) or not set(metadata) <= allowed:
            raise ValueError("Unsupported project metadata fields")
        candidate = self._data()
        candidate.update(metadata)
        return self._commit(candidate)

    @operation("load")
    def load_project(self) -> Project:
        """Load saved settings/history without rewriting v2 files; save a v1 migration once. No API calls."""
        if self._persistence is not None:
            revision = self._persistence.load(self.root)
            self._persistence_revision_id = revision.revision_id if revision is not None else None
        old_version = storage.read_json(self.root / "project.json").get("version")
        candidate = storage.load_project(self.root)
        if old_version == 1:
            result = self._commit(candidate)
        else:
            self._project = Project.model_validate(candidate)
            self._notify()
            result = self.project
        self._renderer = None
        self._migration = (MigrationReport(from_version=1, to_version=VERSION,
            message="Upgraded to v2. Review cast and scenes again; historical cache/takes/exports are retained but not reused.")
            if old_version == 1 else None)
        return result

    @operation("restore")
    def restore_project(self, bundle: PathLike) -> Project:
        """Restore into a new workspace and migrate if needed; never modify the supplied ZIP or call Gemini."""
        storage.restore_project(bundle, self.root)
        return self.load_project()

    @operation("cast")
    def import_cast(self, references_zip: PathLike) -> Project:
        """Validate reference assets in staging, merge them and save an unapproved cast; no API calls."""
        candidate = self._data()
        # Invalid packs cannot overwrite existing references. A successful import
        # still replaces matching assets, as documented for reference imports.
        with tempfile.TemporaryDirectory() as td:
            staged = Path(td)
            if (self.root / "references").exists():
                shutil.copytree(self.root / "references", staged / "references")
            storage.import_cast(candidate, staged, references_zip)
            Project.model_validate(candidate)
            candidate["approvals"] = {}
            return self._commit(candidate, {"references": staged / "references"})

    @operation("cast")
    def create_cast_member(self, command: CastCreate) -> Project:
        """Create a character from a selected crop without a ZIP or provider call."""
        command = CastCreate.model_validate(command)
        candidate = self._data()
        appearance = next((a for a in candidate["appearances"] if a["char_id"] == command.char_id), None)
        if appearance is None:
            raise ValueError("Choose an existing appearance")
        name, voice = command.name.strip(), command.voice.strip()
        if not name or not voice:
            raise ValueError("Cast names and voices cannot be empty")
        if any(c["name"].casefold() == name.casefold() for c in candidate["cast"].values()):
            raise ValueError("This character name already exists; assign its existing entry instead")
        reference = "input/" + appearance["crop_path"]
        if not storage.asset(self.root, reference).is_file():
            raise ValueError("The selected appearance has no reference image")
        index = 1
        while f"CHARACTER_{index:03d}" in candidate["cast"]:
            index += 1
        speaker_id = f"CHARACTER_{index:03d}"
        candidate["cast"][speaker_id] = dump(CastMember(name=name, voice=voice, pronunciation="", references=[reference]))
        appearance.update(speaker_id=speaker_id, rejected=False)
        candidate.update(cast_approval=None, approvals={})
        script.sync_cast_speakers(candidate)
        return self._commit(candidate)

    @operation("cast")
    def apply_cast_review(self, command: CastReview) -> Project:
        """Apply a complete cast/gallery command, optionally approve atomically, then autosave."""
        command = CastReview.model_validate(command)
        candidate = script.review_cast(self._data(), dump(command))
        for entry in command.new_characters:
            if not storage.asset(self.root, candidate["cast"][entry.speaker_id]["references"][0]).is_file():
                raise ValueError("The selected appearance has no reference image")
        return self._commit(candidate)

    @operation("cast")
    def approve_cast(self) -> Project:
        """Validate current appearance resolution and approve the current cast; autosave, no API calls."""
        candidate = self._data()
        script.approve_cast(candidate)
        return self._commit(candidate)

    @operation("planning")
    def generate_proposal(self, planning_model: str | None = None, progress: ProgressCallback | None = None) -> Proposal:
        """Explicit paid-capable visual planning; cache first, leave script unapproved/unmodified, autosave proposal."""
        candidate = self._data()
        if len(candidate["cast"]) < 2:
            raise ValueError("Import the named cast first")
        if planning_model is not None:
            candidate["settings"]["planning_model"] = planning_model.strip()
        Project.model_validate(candidate)
        result = resolution.propose_plan(candidate, self.root, None,
            progress=lambda message: self._event(progress, "planning", "running", message),
            max_attempts=self._config.max_attempts, client_factory=self._get_client)
        self._commit(candidate)
        self._event(progress, "planning", "complete", "Proposal ready for human review.")
        return Proposal.model_validate(result)

    @operation("proposal")
    def apply_proposal(self, proposal: Proposal) -> Project:
        """Load an edited saved proposal after checking visual evidence; clear approvals and autosave."""
        proposal = Proposal.model_validate(proposal)
        candidate = self._data()
        saved = candidate.get("proposal")
        if not saved:
            raise ValueError("Generate a proposal first")
        if saved["evidence"] != resolution.evidence_signature(candidate, self.root):
            raise ValueError("Visual evidence changed")
        script.apply_proposal(candidate, dump(proposal))
        return self._commit(candidate)

    @operation("sources")
    def apply_source_review(self, command: SourceReview) -> Project:
        """Validate complete source edits/order/grouping, rebuild turns and autosave; clear scene approvals."""
        command = SourceReview.model_validate(command)
        return self._commit(script.review_sources(self._data(), dump(command)))

    @operation("script")
    def sync_cast_speakers(self) -> Project:
        """Backfill clear speaker links in an existing project; never rewrite dialogue."""
        candidate = self._data()
        script.sync_cast_speakers(candidate)
        return self._commit(candidate)

    @operation("script")
    def apply_scene_review(self, command: SceneReview) -> Project:
        """Apply exact transcript edits and optional approval atomically; source evidence stays unchanged."""
        command = SceneReview.model_validate(command)
        return self._commit(script.review_scene(self._data(), dump(command)))

    @operation("script")
    def apply_scene_reviews(self, command: SceneBatchReview) -> Project:
        """Validate all scene edits before publishing any of them."""
        command = SceneBatchReview.model_validate(command)
        ids = [scene.scene_id for scene in command.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("Review each scene only once in a save")
        candidate = self._data()
        for scene in command.scenes:
            edit = dump(scene)
            edit["approve"] = False
            candidate = script.review_scene(candidate, edit, sync_speakers=False)
        script.sync_cast_speakers(candidate)
        for review in command.scenes:
            if review.approve:
                scene = next(s for s in candidate["scenes"] if s["scene_id"] == review.scene_id)
                script.approve_scene(candidate, scene)
        return self._commit(candidate)

    @operation("narration")
    def insert_narration(self, command: NarrationInsert) -> Project:
        """Insert visible-evidence narration and clear that scene approval; autosave, no paid calls."""
        command = NarrationInsert.model_validate(command)
        return self._commit(script.add_narration(self._data(), dump(command)))

    @operation("settings")
    def update_settings(self, command: SettingsUpdate) -> Project:
        """Explicitly replace saved settings and clear scene approvals; never override them during restore."""
        command = SettingsUpdate.model_validate(command)
        candidate = self._data()
        candidate["settings"] = dump(command.settings)
        candidate["approvals"] = {}
        result = self._commit(candidate)
        self._renderer = None
        return result

    @operation("selection")
    def set_render_selection(self, command: RenderSelection) -> Project:
        """Save unique known scene IDs; empty selection is allowed, without approval/rendering."""
        command = RenderSelection.model_validate(command)
        candidate = self._data()
        self._selected(candidate, command.scene_ids, allow_empty=True)
        candidate["render_selection"] = command.scene_ids
        return self._commit(candidate)

    @staticmethod
    def _selected(data: dict[str, Any], ids: list[str], allow_empty: bool = False) -> list[dict[str, Any]]:
        known = {scene["scene_id"] for scene in data["scenes"]}
        if (not ids and not allow_empty) or len(ids) != len(set(ids)) or not set(ids) <= known:
            raise ValueError("Choose unique known scenes")
        return [scene for scene in data["scenes"] if scene["scene_id"] in ids]

    @operation("inspection")
    def inspect_segments(self, selection: RenderSelection) -> list[Segment]:
        """Compile approved selected scenes into detached typed requests; no client creation or API calls."""
        selection = RenderSelection.model_validate(selection)
        candidate = self._data()
        return [Segment.model_validate(segment) for scene in self._selected(candidate, selection.scene_ids)
                for segment in tts.compile_segments(candidate, scene)]

    @operation("render")
    def render_selected(self, command: RenderCommand, progress: ProgressCallback | None = None) -> RenderResult:
        """Explicit paid-capable synthesis with whole-selection preflight and per-segment durable resume."""
        command = RenderCommand.model_validate(command)
        candidate = self._data()
        scenes = self._selected(candidate, command.scene_ids)
        planned = [seg for scene in scenes for seg in tts.compile_segments(candidate, scene)]
        if not set(command.regenerate) <= {seg["segment_id"] for seg in planned}:
            raise ValueError("Regenerate IDs must belong to selected scenes")
        def render(request: dict[str, Any]) -> bytes:
            # Even client creation is deferred until a missing non-silence segment.
            return self._get_renderer()(request)
        for scene in scenes:
            own_ids = {seg["segment_id"] for seg in planned if seg["scene_id"] == scene["scene_id"]}
            def report(status: str, segment_id: str) -> None:
                self._event(progress, "render", status, "Segment " + status, scene["scene_id"], segment_id)
            tts.render_scene(candidate, self.root, scene, render,
                regenerate=[sid for sid in command.regenerate if sid in own_ids], checkpoint=self._commit,
                progress=report)
        self._event(progress, "render", "complete", "Selected audio is ready for audition.")
        return RenderResult(project=self.project, segments=[Segment.model_validate(seg) for seg in planned])

    @operation("take")
    def select_take(self, command: TakeSelection) -> Project:
        """Validate a current segment/take checksum and select it for export; autosave, no synthesis."""
        command = TakeSelection.model_validate(command)
        candidate = self._data()
        segments = [seg for scene in candidate["scenes"]
                    if candidate["approvals"].get(scene["scene_id"]) == script.scene_signature(candidate, scene)
                    for seg in tts.compile_segments(candidate, scene)]
        segment = next((seg for seg in segments if seg["segment_id"] == command.segment_id), None)
        if segment is None:
            raise ValueError("Unknown or unapproved segment")
        take = next((take for take in candidate["takes"].get(segment["signature"], []) if take["take_id"] == command.take_id), None)
        if take is None:
            raise ValueError("Take does not belong to the current request")
        import hashlib
        path = storage.asset(self.root, take["path"])
        tts.wav_info(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != take["audio_sha256"]:
            raise ValueError("Take changed on disk")
        candidate["selected_takes"][tts.selection_key(segment)] = command.take_id
        return self._commit(candidate)

    @operation("export")
    def export_audio(self, selection: RenderSelection, mp3: bool = False) -> ExportResult:
        """Assemble current chosen takes and overwrite fixed export files; never synthesize missing speech."""
        selection = RenderSelection.model_validate(selection)
        wav = tts.export_audio(self._data(), self.root, selection.scene_ids, mp3)
        return ExportResult(wav_path=str(wav), export_directory=str(wav.parent))

    @operation("bundle")
    def bundle_project(self, destination: PathLike | None = None) -> Path:
        """Write a resumable bundle of applied state/assets/history/exports, excluding runtime credentials/drafts."""
        path = Path(destination) if destination else self.root.parent / (self.root.name + "_project.zip")
        return storage.bundle_project(self._data(), self.root, path)
