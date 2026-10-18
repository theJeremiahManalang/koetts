"""Tts stage implementation; public workflow commands live in PipelineRouter."""
from __future__ import annotations
import array
import hashlib
import math
import shutil
from pathlib import Path
import subprocess
from typing import Any, Iterable, Callable
import uuid
import wave
from .config import SAMPLE_RATE, NARRATOR, MAX_SILENCE_SEC, TEXT_POLICY_VERSION, CACHE_REVISION, PathLike
from .schemas import SpeechRequest, Renderer, validate_contract
from .cleaner import require_reviewed_text
from .storage import asset, digest, write_json, save_project
from .script import validate_scene, scene_signature
from .gemini import LOGGER



def validate_speech_request(request: dict[str, Any]) -> None:
    """Validate exact Gemini payload shape, speaker limits and reviewed text; no API calls.

    Rejects malformed content, configuration and unsafe encoding with ValueError.
    Does not rewrite text or substitute voices; approval checks belong to compile_segments.
    """
    validate_contract(request, SpeechRequest, "speech request")
    if request["response_format"] != {"type": "audio"} or len(request["input"]) != 1:
        raise ValueError("Speech request must contain one user input and request audio")
    block = request["input"][0]
    if block["type"] != "user_input" or not block["content"]:
        raise ValueError("Speech request has no user text")
    config = request["generation_config"]["speech_config"]
    if isinstance(config, list):
        if len(config) != 1 or not config[0]["voice"]:
            raise ValueError("Single-speaker request requires one voice")
        speakers = None
    else:
        speakers = [item["speaker"] for item in config["speakers"]]
        if len(speakers) != 2 or len(set(speakers)) != 2 or any(not item["voice"] for item in config["speakers"]):
            raise ValueError("Multi-speaker request requires two distinct speakers and voices")
    used = set()
    for item in block["content"]:
        if item["type"] != "text" or not item["text"].strip() or len(item["annotations"]) != 1:
            raise ValueError("Speech content requires nonempty text and one speech annotation")
        require_reviewed_text(item["text"], "Spoken text")
        meta = item["annotations"][0]
        if meta["type"] != "speech_metadata":
            raise ValueError("Unsupported speech annotation")
        require_reviewed_text(meta["style"], "Speech metadata")
        if speakers is None and "speaker" in meta or speakers is not None and meta.get("speaker") not in speakers:
            raise ValueError("Speech annotation does not match configured speakers")
        if speakers is not None:
            used.add(meta["speaker"])
    if speakers is not None and used != set(speakers):
        raise ValueError("Configured speakers must both occur in speech content")


def compile_segments(p: dict[str, Any], scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Return ordered, signed synthesis/silence segments for an approved scene in p.

    Enforces current approvals, at most two speakers per request, separate narrator
    passages and max_chars. Excluded turns never enter requests. Raises ValueError for
    stale approval, invalid settings or oversized turns. No mutation, I/O or API calls."""
    validate_scene(p, scene)
    if p["approvals"].get(scene["scene_id"]) != scene_signature(p, scene):
        raise ValueError("Scene changed or is unapproved; review and approve it before rendering")
    segments: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    speakers: set[str] = set()
    chars = 0
    limit = p["settings"]["max_chars"]
    if not isinstance(limit, int) or limit < 100:
        raise ValueError("max_chars must be an integer >= 100")
    def flush():
        nonlocal current, speakers, chars
        if current:
            segments.append({"turns": current, "silence_sec": 0.0})
        current, speakers, chars = [], set(), 0
    for t in scene["turns"]:
        if not t["include"]:
            continue
        if len(t["text"]) > limit:
            raise ValueError("Turn exceeds segment character limit; split it during source review or raise max_chars")
        sid = t["speaker_id"]
        if t.get("silence_sec", 0):
            flush()
            if t["text"].strip():
                segments.append({"turns": [t], "silence_sec": 0.0})
            segments.append({"turns": [dict(t, text="")], "silence_sec": float(t["silence_sec"])})
            continue
        if current and (len(speakers | {sid}) > 2 or chars + len(t["text"]) > limit
                        or sid == NARRATOR or NARRATOR in speakers):
            flush()
        current.append(t)
        speakers.add(sid)
        chars += len(t["text"])
    flush()
    for i, seg in enumerate(segments):
        seg["segment_id"] = f"{scene['scene_id']}_{i+1:03d}"
        seg["scene_id"] = scene["scene_id"]
        seg["source_ids"] = [sid for t in seg["turns"] for sid in t["source_ids"]]
        seg["request"] = None if seg["silence_sec"] else build_request(p, scene, seg["turns"])
        seg["signature"] = digest({"cache_revision": CACHE_REVISION, "text_policy": TEXT_POLICY_VERSION, "request": seg["request"], "silence": seg["silence_sec"],
                                    "model": p["settings"]["tts_model"], "sample_rate": SAMPLE_RATE})
    return segments


def build_request(p: dict[str, Any], scene: dict[str, Any], turns: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a Gemini speech payload for included turns from one compiled segment.

    Uses exact turn text and cast/scene acting metadata from p; never normalizes it.
    Validates the payload, raising ValueError for malformed configuration/encoding.
    Caller must validate approvals and inclusion through compile_segments. No API
    calls or mutation."""
    if not turns or any(not t["include"] for t in turns):
        raise ValueError("Speech requests require included turns")
    speakers = list(dict.fromkeys(t["speaker_id"] for t in turns))
    content = []
    for t in turns:
        c = p["cast"][t["speaker_id"]]
        style = "; ".join(x for x in [c.get("acting_notes", ""), scene["context"], f"{c['name']}; {t['delivery']}; {t['emotion']}",
                                      t["style"], t["pacing"], c.get("pronunciation", "")] if x)
        meta = {"type": "speech_metadata", "style": style}
        if len(speakers) > 1:
            meta["speaker"] = t["speaker_id"]
        content.append({"type": "text", "text": t["text"], "annotations": [meta]})
    config = ([{"voice": p["cast"][speakers[0]]["voice"]}] if len(speakers) == 1 else
              {"speakers": [{"speaker": s, "voice": p["cast"][s]["voice"]} for s in speakers]})
    request = {"input": [{"type": "user_input", "content": content}], "response_format": {"type": "audio"},
            "generation_config": {"speech_config": config}}
    validate_speech_request(request)
    return request


def wav_info(path: PathLike) -> tuple[dict[str, Any], bytes]:
    """Read path and return (metadata, PCM bytes) for mono 24 kHz 16-bit PCM WAV.

    Metadata includes frame count, duration and clipping. Raises ValueError for
    unexpected format; wave/IO errors propagate. No project mutation."""
    with wave.open(str(path), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getcomptype()) != (SAMPLE_RATE, 1, 2, "NONE"):
            raise ValueError("Expected mono 24 kHz 16-bit PCM WAV")
        frames = wav.getnframes()
        pcm = wav.readframes(frames)
    if frames <= 0 or len(pcm) != frames * 2:
        raise ValueError("Empty or truncated WAV")
    values = array.array("h")
    values.frombytes(pcm)
    import sys
    if sys.byteorder != "little":
        values.byteswap()
    peak = max(abs(x) for x in values) / 32768
    return {"frames": frames, "duration_sec": frames / SAMPLE_RATE, "peak": peak,
            "clipped_samples": sum(abs(x) >= 32767 for x in values)}, pcm


def write_wav(path: PathLike, pcm: bytes) -> None:
    """Write raw signed 16-bit mono PCM bytes to path at SAMPLE_RATE.

    Creates parent directories and replaces the WAV; returns None. I/O errors propagate."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)


def selection_key(segment: dict[str, Any]) -> str:
    # Equal requests may share cached audio, but choosing a new take is local to one segment.
    """Return a segment-local take-selection key combining segment ID and request signature."""
    return segment["segment_id"] + ":" + segment["signature"]


def render_scene(p: dict[str, Any], root: PathLike, scene: dict[str, Any], renderer: Renderer, regenerate: Iterable[str] = (),
                 checkpoint: Callable[[dict[str, Any]], Any] | None = None,
                 progress: Callable[[str, str], None] | None = None) -> list[dict[str, Any]]:
    """Render or reuse approved scene segments, returning the compiled segment list.

    renderer(request) must return WAV bytes and may make paid calls. regenerate is an
    iterable of segment IDs that explicitly bypass reuse. Valid cached takes are
    checksum/format verified; silence is generated locally. Mutates p takes/selections,
    writes WAVs and saves after each successful segment, retaining progress on failure.
    Approval, regeneration, renderer and I/O errors propagate; no competing takes are automatic."""
    persist = checkpoint or (lambda data: save_project(data, root))
    report = progress or (lambda status, segment_id: None)
    segments = compile_segments(p, scene)
    regenerate = set(regenerate)
    if not regenerate <= {s["segment_id"] for s in segments}:
        raise ValueError("Unknown regeneration segment ID")
    for seg in segments:
        LOGGER.info("segment_started", extra={"operation": "render", "scene_id": scene["scene_id"],
            "segment_id": seg["segment_id"], "outcome": "started"})
        sig = seg["signature"]
        key = selection_key(seg)
        selected = p["selected_takes"].get(key)
        available = p["takes"].get(sig, [])
        take = (next((t for t in available if t["take_id"] == selected), None) if selected
                else available[-1] if available else None)
        if take and seg["segment_id"] not in regenerate:
            path = asset(root, take["path"])
            reusable = False
            try:
                wav_info(path)
                reusable = hashlib.sha256(path.read_bytes()).hexdigest() == take["audio_sha256"]
            except (OSError, ValueError, wave.Error):
                pass
            if reusable:
                p["selected_takes"][key] = take["take_id"]
                # A checkpoint failure must surface; it is not corrupt audio and
                # must never trigger a replacement paid synthesis call.
                persist(p)
                report("reused", seg["segment_id"])
                LOGGER.info("segment_reused", extra={"operation": "render", "scene_id": scene["scene_id"],
                    "segment_id": seg["segment_id"], "outcome": "reused"})
                continue
        take_id = uuid.uuid4().hex[:12]
        rel = f"takes/{sig}/{take_id}.wav"
        path = asset(root, rel)
        if seg["silence_sec"]:
            write_wav(path, b"\0\0" * round(SAMPLE_RATE * seg["silence_sec"]))
        else:
            try:
                data = renderer(seg["request"])
            except Exception:
                LOGGER.error("segment_failed", extra={"operation": "render", "scene_id": scene["scene_id"],
                    "segment_id": seg["segment_id"], "outcome": "failed"})
                raise
            temp = path.with_suffix(".tmp.wav")
            temp.parent.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(data)
            try:
                wav_info(temp)
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
        info, _ = wav_info(path)
        p["takes"].setdefault(sig, []).append({"take_id": take_id, "path": rel, **info,
            "audio_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        p["selected_takes"][key] = take_id
        persist(p)  # Resume safely after every successful segment.
        report("saved", seg["segment_id"])
        LOGGER.info("segment_saved", extra={"operation": "render", "scene_id": scene["scene_id"],
            "segment_id": seg["segment_id"], "outcome": "saved"})
    return segments


def export_audio(p: dict[str, Any], root: PathLike, scene_ids: list[str], mp3: bool = False) -> Path:
    """Assemble selected current takes for scene_ids into chapter audio under root/exports.

    Returns the WAV Path; writes script, cast, manifest and scene/segment timeline JSON.
    Selection follows project scene order, with configured pauses; matching export files
    are overwritten. Requires current approvals and intact selected audio. No synthesis.
    Raises ValueError for invalid selection/missing or changed takes. mp3=True additionally
    runs ffmpeg; failure can leave valid WAV/JSON outputs. I/O/subprocess errors propagate."""
    if not scene_ids or len(scene_ids) != len(set(scene_ids)):
        raise ValueError("Choose at least one scene, without duplicates")
    encoder = None
    if mp3:
        encoder = shutil.which("ffmpeg")
        if not encoder:
            try:
                from imageio_ffmpeg import get_ffmpeg_exe
                encoder = get_ffmpeg_exe()
            except (ImportError, RuntimeError):
                raise ValueError("MP3 encoder unavailable; install requirements-audio.txt") from None
    known = {s["scene_id"] for s in p["scenes"]}
    if not set(scene_ids) <= known:
        raise ValueError("Unknown scene selection")
    for key in ("scene_pause", "segment_pause"):
        value = p["settings"][key]
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= MAX_SILENCE_SEC:
            raise ValueError("Export pauses must be between 0 and 30 seconds")
    pcm_parts: list[bytes] = []
    timeline: list[dict[str, Any]] = []
    cursor = 0
    exported: list[dict[str, Any]] = []
    for scene in p["scenes"]:
        if scene["scene_id"] not in scene_ids:
            continue
        segments = compile_segments(p, scene)
        if not segments:
            continue
        if exported:
            silence = round(SAMPLE_RATE * p["settings"]["scene_pause"])
            pcm_parts.append(b"\0\0" * silence)
            cursor += silence
        scene_start = cursor
        for i, seg in enumerate(segments):
            sig = seg["signature"]
            take = next((t for t in p["takes"].get(sig, []) if t["take_id"] == p["selected_takes"].get(selection_key(seg))), None)
            if take is None:
                raise ValueError(f"Missing current audio for {seg['segment_id']}; render it first")
            path = asset(root, take["path"])
            if hashlib.sha256(path.read_bytes()).hexdigest() != take["audio_sha256"]:
                raise ValueError("Take changed on disk; regenerate it")
            info, pcm = wav_info(path)
            # Intentional silence is already an explicit segment; don't pad it twice.
            if i and not seg["silence_sec"] and not segments[i-1]["silence_sec"]:
                gap = round(SAMPLE_RATE * p["settings"]["segment_pause"])
                pcm_parts.append(b"\0\0" * gap)
                cursor += gap
            start = cursor
            pcm_parts.append(pcm)
            cursor += info["frames"]
            timeline.append({"segment_id": seg["segment_id"], "scene_id": scene["scene_id"],
                "source_ids": seg["source_ids"], "turn_ids": [t["turn_id"] for t in seg["turns"]],
                "start_sec": start / SAMPLE_RATE, "end_sec": cursor / SAMPLE_RATE,
                "signature": sig, "take": take})
        exported.append({"scene_id": scene["scene_id"], "start_sec": scene_start / SAMPLE_RATE, "end_sec": cursor / SAMPLE_RATE})
    if not pcm_parts:
        raise ValueError("Selection contains no included audio")
    out = Path(root) / "exports"
    out.mkdir(parents=True, exist_ok=True)
    wav = out / "chapter_narration.wav"
    write_wav(wav, b"".join(pcm_parts))
    write_json(out / "timeline.json", {"sample_rate": SAMPLE_RATE, "timestamp_granularity": "segment",
        "total_duration_sec": cursor / SAMPLE_RATE, "scenes": exported, "segments": timeline})
    write_json(out / "cast.json", p["cast"])
    write_json(out / "approved_script.json", [s for s in p["scenes"] if s["scene_id"] in scene_ids])
    write_json(out / "render_manifest.json", {"chapter_id": p["chapter_id"], "settings": p["settings"], "segments": timeline})
    if mp3:
        temporary = out / "chapter_narration.pending.mp3"
        try:
            subprocess.run([encoder, "-y", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "192k", str(temporary)], check=True, capture_output=True)
            temporary.replace(out / "chapter_narration.mp3")
        finally:
            temporary.unlink(missing_ok=True)
    else:
        (out / "chapter_narration.mp3").unlink(missing_ok=True)
    return wav
