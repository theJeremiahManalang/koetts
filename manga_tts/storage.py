"""Storage stage implementation; public workflow commands live in PipelineRouter."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .config import (
    DEFAULT_PROJECT_SETTINGS,
    MAX_ARCHIVE_BYTES,
    MIN_OCR_IOU,
    NARRATOR,
    UNKNOWN,
    VERSION,
    VOICES,
    PathLike,
)
from .schemas import CastManifest, ChapterInput, Project, ProjectV1, validate_contract


def digest(value: Any) -> str:
    """Return a stable SHA-256 hex digest of a JSON-serializable value; no mutation or I/O."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8", errors="backslashreplace")).hexdigest()


def read_json(path: PathLike) -> Any:
    """Read strict UTF-8 JSON, accepting an optional leading UTF-8 BOM.

    Returns decoded data without normalization or mutation. Malformed JSON, invalid
    UTF-8 bytes and filesystem errors propagate; callers validate domain contracts.
    No encoding guessing, writes or API calls.
    """
    return json.loads(Path(path).read_text(encoding="utf-8").removeprefix("\ufeff"))


def write_json(path: PathLike, value: Any) -> None:
    """Atomically replace path with UTF-8 JSON for value, creating parent directories.

    Escapes unpaired surrogates to preserve raw evidence in valid UTF-8 JSON; it
    does not approve/clean spoken text. Returns None. Serialization and filesystem
    errors propagate; no API calls."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    # JSON escapes preserve invalid source-code-point evidence while the FILE
    # itself remains strictly valid UTF-8. Render text must still pass review.
    serialized = json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8", errors="backslashreplace").decode("utf-8")
    temp.write_text(serialized, encoding="utf-8")
    temp.replace(path)


def asset(root: PathLike, relative: str) -> Path:
    """Resolve relative archive/project asset paths beneath root.

    Returns a Path; raises ValueError for absolute paths, traversal or workspace escapes.
    Does not create files."""
    rel = PurePosixPath(str(relative).replace("\\", "/"))
    if rel.is_absolute() or ".." in rel.parts or ":" in str(rel):
        raise ValueError(f"Unsafe asset path: {relative}")
    path = (Path(root) / str(rel)).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError("Asset escapes workspace")
    return path


def extract_zip(path: PathLike, target: PathLike) -> None:
    """Extract path ZIP into target after checking size, paths and symlinks.

    Returns None. Existing matching files are overwritten; failures may leave extracted
    files. Raises ValueError for unsafe entries or excessive size; ZIP/I/O errors propagate."""
    target = Path(target)
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 10000:
            raise ValueError("Archive has too many entries")
        if sum(e.file_size for e in entries) > MAX_ARCHIVE_BYTES:
            raise ValueError("Archive exceeds 1 GB uncompressed")
        seen = set()
        for entry in entries:
            canonical = str(asset(target, entry.filename)).casefold()
            if canonical in seen:
                raise ValueError("Archive contains duplicate paths")
            seen.add(canonical)
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Archive symlinks are unsupported")
        total = 0
        for entry in entries:
            dest = asset(target, entry.filename)
            if entry.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, dest.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_ARCHIVE_BYTES:
                            raise ValueError("Archive exceeds 1 GB uncompressed")
                        output.write(chunk)


def iou(a: list[float], b: list[float]) -> float:
    """Return intersection-over-union for two [left, top, right, bottom] boxes; no mutation."""
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    aa = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    bb = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    return inter / max(aa + bb - inter, 1e-8)


def ocr_pairs(raw: dict[str, Any]) -> list[tuple[str, list[float]]]:
    """Return (text, bbox) pairs from supported raw OCR layouts.

    Malformed or mismatched arrays return an empty list; raw is not modified."""
    ocr = raw.get("ocr", {})
    if isinstance(ocr, dict):
        texts = ocr.get("ocr_texts") or ocr.get("transcriptions") or ocr.get("texts") or []
        boxes = ocr.get("bboxes") or ocr.get("ocr_regions") or ocr.get("boxes")
    elif isinstance(ocr, list) and ocr and isinstance(ocr[0], dict):
        texts = [x.get("text", x.get("ocr", "")) for x in ocr]
        boxes = [x.get("bbox", x.get("box")) for x in ocr]
    elif isinstance(ocr, list):
        texts, boxes = ocr, None
    else:
        texts, boxes = [], None
    if boxes is None:
        boxes = raw.get("detections", {}).get("texts", [])
    if len(texts) != len(boxes) or any(not isinstance(b, list) or len(b) != 4 for b in boxes):
        return []
    return [(str(t).strip(), b) for t, b in zip(texts, boxes)]


def recover_ocr(chapter: dict[str, Any], raw_pages: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copied chapter with blank OCR recovered from raw_pages by box IoU.

    Matches are one-to-one; existing text and essential labels are preserved. No I/O."""
    result = copy.deepcopy(chapter)
    for page in result["pages"]:
        pairs = ocr_pairs(raw_pages.get(page["page_id"], {}))
        edges = sorted(((iou(t["bbox"], box), ti, oi)
                        for ti, t in enumerate(page["texts"])
                        for oi, (_, box) in enumerate(pairs)), reverse=True)
        used_t, used_o = set(), set()
        for score, ti, oi in edges:
            if score < MIN_OCR_IOU or ti in used_t or oi in used_o:
                continue
            used_t.add(ti)
            used_o.add(oi)
            text = page["texts"][ti]
            # New image adapters already reconciled OCR, including deliberate
            # ambiguous blanks. Retrying here could duplicate their unmatched OCR.
            if "ocr_indices" not in text and not text.get("ocr_text", "").strip():
                text["ocr_text"] = pairs[oi][0]
                text["ocr_recovery"] = {"method": "bbox_iou", "iou": round(score, 4)}
    return result


def new_project(chapter_zip: PathLike, root: PathLike, references_zip: PathLike | None = None, originals_zip: PathLike | None = None,
                *, persist: bool = True) -> dict[str, Any]:
    """Create and return a project from chapter_zip in root; save project.json.

    Optionally extract references_zip and originals_zip. Recovers OCR, initializes
    unresolved speakers and rebuilds turns without API calls. persist=False lets the
    router apply validated runtime defaults before its single durable commit. Raises ValueError if
    project.json exists or archives/cast are invalid; malformed input and I/O errors
    propagate. Failure may leave extracted assets; choose a fresh root for retry."""
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Project exists or workspace is nonempty. Choose a new workspace.")
    extract_zip(chapter_zip, root / "input")
    chapter = read_json(root / "input/chapter_analysis.json")
    validate_contract(chapter, ChapterInput, "chapter")
    page_ids, source_ids = set(), set()
    for page in chapter["pages"]:
        if page["page_id"] in page_ids:
            raise ValueError("Duplicate page ID")
        page_ids.add(page["page_id"])
        for item in page["texts"]:
            bubble_key = (page["page_id"], item["text_id"])
            if bubble_key in source_ids or len(item["bbox"]) != 4:
                raise ValueError("Duplicate source ID or invalid bubble bounding box")
            source_ids.add(bubble_key)
    raw = {}
    for page in chapter["pages"]:
        path = root / "input/raw_predictions" / f"page_{page['page_index']:03d}_raw.json"
        raw[page["page_id"]] = read_json(path) if path.exists() else {}
        validate_contract(raw[page["page_id"]], dict[str, Any], "raw prediction")
    chapter = recover_ocr(chapter, raw)
    if originals_zip:
        extract_zip(originals_zip, root / "originals")
    p = {"version": VERSION, "chapter_id": chapter["chapter_id"], "chapter": chapter,
         "cast": {NARRATOR: {"name": "Narrator", "voice": "Charon", "pronunciation": "", "references": []}},
         "appearances": [], "sources": [], "scenes": [], "takes": {}, "selected_takes": {},
         "approvals": {}, "proposal": None, "cast_approval": None,
         "settings": copy.deepcopy(DEFAULT_PROJECT_SETTINGS)}
    for page in sorted(chapter["pages"], key=lambda x: x["page_index"]):
        scene_id = f"scene_{page['page_index']:03d}"
        p["scenes"].append({"scene_id": scene_id, "title": page["page_id"], "context": "", "turns": []})
        for ch in page["characters"]:
            p["appearances"].append({**ch, "page_id": page["page_id"], "speaker_id": UNKNOWN,
                                     "rejected": False, "reason": "Unreviewed appearance"})
        links = page.get("associations", {}).get("text_to_character", [])
        for t in sorted(page["texts"], key=lambda x: x["reading_order"]):
            sid = f"{page['page_id']}:{t['text_id']}"
            p["sources"].append({"source_id": sid, "page_id": page["page_id"], "panel_id": t.get("panel_id"),
                                 "bbox": t["bbox"], "original_text": t["ocr_text"], "text": t["ocr_text"],
                                 "upstream_essential": t.get("is_essential", True),
                                 "include": t.get("is_essential", True), "speaker_id": UNKNOWN,
                                 "scene_id": scene_id, "order": len(p["sources"]), "turn_group": sid,
                                 "delivery": "speech", "emotion": "neutral", "style": "", "pacing": "unhurried; allow short reactions to land",
                                 "reaction": None, "reason": "Needs review",
                                 "magi_links": [x for x in links if x["text_id"] == t["text_id"]]})
    if references_zip:
        import_cast(p, root, references_zip)
    from .script import rebuild_turns
    rebuild_turns(p)
    validate_contract(p, Project, "project")
    if persist:
        save_project(p, root)
    return p


def import_cast(p: dict[str, Any], root: PathLike, references_zip: PathLike) -> None:
    """Merge characters from references_zip into project p and invalidate cast approval.

    Extracts assets under root/references; reads cast.json and optional profiles.
    Generic characters may omit images. Returns None; raises ValueError for invalid
    IDs or missing references. Extraction may overwrite assets even if validation fails.
    Does not save project.json; callers must save after a successful import."""
    extract_zip(references_zip, Path(root) / "references")
    manifest = read_json(Path(root) / "references/cast.json")
    validate_contract(manifest, CastManifest, "cast manifest")
    cast = copy.deepcopy(p["cast"])
    seen = set()
    for c in manifest["characters"]:
        sid = c["speaker_id"]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", sid) or sid in (UNKNOWN, NARRATOR) or sid in seen:
            raise ValueError(f"Invalid/reserved character ID: {sid}")
        seen.add(sid)
        refs = c.get("references", [])
        is_generic = c.get("is_generic", False)
        if not isinstance(is_generic, bool):
            raise ValueError("is_generic must be a boolean")
        if not refs and not is_generic:
            raise ValueError(f"{sid} needs at least one reference image")
        for ref in refs:
            if not asset(Path(root) / "references", ref).is_file():
                raise ValueError(f"Missing reference: {ref}")
        used_voices = {profile["voice"] for key, profile in cast.items() if key != sid}
        default_voice = cast.get(sid, {}).get("voice") or next((v for v in VOICES if v not in used_voices), "Kore")
        profile_path = c.get("profile_path", "")
        profile_markdown = (asset(Path(root) / "references", profile_path).read_text(encoding="utf-8")
                            if profile_path else "")
        cast[sid] = {"name": c["name"], "voice": c.get("voice") or default_voice,
                     "pronunciation": c.get("pronunciation", ""),
                     "references": [f"references/{r}" for r in refs],
                     "role": c.get("role", "supporting"), "is_generic": is_generic,
                     "description": c.get("description", ""), "personality": c.get("personality", ""),
                     "acting_notes": c.get("acting_notes", ""), "profile_markdown": profile_markdown,
                     "profile_path": f"references/{profile_path}" if profile_path else ""}
    p["cast"] = cast
    p["cast_approval"] = None


def save_project(p: dict[str, Any], root: PathLike) -> None:
    """Atomically write applied project p to root/project.json; return None.

    Widget drafts and runtime credentials are not part of p. I/O errors propagate."""
    write_json(Path(root) / "project.json", p)


def load_project(root: PathLike) -> dict[str, Any]:
    """Read and return root/project.json without migration, mutation or API calls.

    Raises ValueError for an unsupported version; JSON and filesystem errors propagate."""
    p = read_json(Path(root) / "project.json")
    if not isinstance(p, dict):
        raise ValueError("project: expected object")
    if p.get("version") == 1:
        validate_contract(p, ProjectV1, "legacy project")
        p.update(version=VERSION, cast_approval=None, approvals={}, selected_takes={}, proposal=None)
    if p.get("version") != VERSION:
        raise ValueError("Unsupported project version")
    validate_contract(p, Project, "project")
    return p


def bundle_project(p: dict[str, Any], root: PathLike, destination: PathLike) -> Path:
    """Save p and return destination Path after writing a resumable project ZIP.

    Includes applied state, source/reference assets, planning cache, takes and exports.
    Excludes widget drafts and runtime client/credentials. Existing destination is
    overwritten atomically; creates the destination parent. Destination must be
    outside the workspace. ZIP/I/O errors propagate; no API calls."""
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if destination.is_relative_to(root):
        raise ValueError("Save project bundles outside the workspace")
    save_project(p, root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as td:
        staged = Path(td) / "bundle.zip"
        with zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED) as z:
            for folder in ("input", "references", "originals", "planning_cache", "takes", "exports"):
                for path in sorted((root / folder).rglob("*")):
                    if path.is_symlink() or not path.resolve().is_relative_to(root):
                        raise ValueError("Project assets must stay inside the workspace")
                    if path.is_file() and ".tmp" not in path.suffixes:
                        z.write(path, path.relative_to(root).as_posix())
            z.write(root / "project.json", "project.json")
        staged.replace(destination)
    return destination


def restore_project(bundle: PathLike, root: PathLike) -> dict[str, Any]:
    """Extract bundle into root and return its version-checked saved project.

    Requires an absent or empty root. Extracts and validates in a sibling staging
    directory before publication. No API calls; invalid archives leave root intact."""
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise ValueError("Restore into a new workspace to avoid replacing an existing project")
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root.parent) as td:
        staged = Path(td) / "project"
        extract_zip(bundle, staged)
        project = load_project(staged)
        if root.exists():
            root.rmdir()  # Only the checked empty directory, never recursive deletion.
        staged.replace(root)
    return project
