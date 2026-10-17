"""Explicit local workflow commands. Paid work occurs only in plan and render."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile

from . import PipelineConfig, PipelineRouter
from . import schemas
from .storage import digest, read_json


@contextmanager
def workspace_lock(workspace):
    """Exclude competing CLI writers. A crash leaves a lock requiring human inspection."""
    workspace = Path(workspace).resolve()
    workspace.parent.mkdir(parents=True, exist_ok=True)
    lock = workspace.parent / (workspace.name + ".lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("Workspace is locked. Check for an active process before removing its sibling .lock file.") from None
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


@contextmanager
def input_bundle(path):
    """Accept the supplied ZIP layout or its unpacked directory, without modifying it."""
    if path is None:
        yield None
        return
    path = Path(path)
    if not path.is_dir():
        yield path
        return
    with tempfile.TemporaryDirectory() as td:
        bundle = Path(td) / "input.zip"
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(path.rglob("*")):
                if item.is_symlink():
                    raise ValueError("Input directory cannot contain symbolic links")
                if item.is_file():
                    archive.write(item, item.relative_to(path).as_posix())
        yield bundle


def write_new(path, value):
    """Do not overwrite a review draft or another existing file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)


def review_document(project, stage, scene_id=None):
    """Editable commands with a base-state fingerprint, not an editable project dump."""
    data = schemas.dump(project)
    if stage == "cast":
        command = {"cast": [{"speaker_id": sid, **{k: c.get(k, "") for k in ("name", "voice", "pronunciation", "acting_notes")}}
                            for sid, c in data["cast"].items()],
                   "appearances": [{k: a[k] for k in schemas.AppearanceEdit.model_fields} for a in data["appearances"]], "approve": False}
    elif stage == "sources":
        command = {"sources": [{k: s[k] for k in schemas.SourceEdit.model_fields} for s in data["sources"]]}
    else:
        scene = next((s for s in data["scenes"] if s["scene_id"] == scene_id), None)
        if scene is None:
            raise ValueError("Choose a known --scene for script review")
        command = {"scene_id": scene_id, "title": scene["title"], "context": scene["context"],
                   "turns": [{k: t[k] for k in schemas.TurnEdit.model_fields} for t in scene["turns"]], "approve": False}
    return {"stage": stage, "base_revision": digest(data), "command": command}


def apply_review(router, document, approve=False):
    if document.get("base_revision") != digest(schemas.dump(router.project)):
        raise ValueError("Review is stale; export a fresh review document before applying edits")
    stage = document.get("stage")
    types = {"cast": (schemas.CastReview, router.apply_cast_review),
             "sources": (schemas.SourceReview, router.apply_source_review),
             "script": (schemas.SceneReview, router.apply_scene_review)}
    if stage not in types:
        raise ValueError("Unknown review stage")
    command = dict(document["command"])
    if stage != "sources":
        # Approval must be a deliberate command-line action, not a model-authored flag.
        command["approve"] = approve
    elif approve:
        raise ValueError("Source edits are applied, then approved through script review")
    contract, action = types[stage]
    return action(contract.model_validate(command))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    extract = sub.add_parser("extract", help="MagiV3 images to chapter ZIP; no Gemini calls")
    inputs = extract.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--images", nargs="+", type=Path, help="Explicit page/panel sequence")
    inputs.add_argument("--input", type=Path, help="One image or folder (natural filename order)")
    extract.add_argument("--output", required=True, type=Path)
    extract.add_argument("--chapter-id", default="chapter_001")
    extract.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    extract.add_argument("--order", choices=["model", "rtl", "ltr"], default="model")
    for action in ("create", "restore", "status", "import-cast", "plan", "load-proposal", "review", "apply", "inspect", "render", "select-take", "export", "bundle", "settings", "narrate"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--workspace", required=True, type=Path)
        if action == "create":
            cmd.add_argument("--chapter", required=True, type=Path)
            cmd.add_argument("--cast", type=Path)
            cmd.add_argument("--originals", type=Path)
        if action == "restore":
            cmd.add_argument("--bundle", required=True, type=Path)
        if action == "import-cast":
            cmd.add_argument("--cast", required=True, type=Path)
        if action in ("plan", "review", "bundle", "inspect"):
            cmd.add_argument("--output", required=True, type=Path)
        if action == "review":
            cmd.add_argument("--stage", required=True, choices=["cast", "sources", "script"])
            cmd.add_argument("--scene")
        if action in ("apply", "load-proposal", "settings", "narrate"):
            cmd.add_argument("--file", required=True, type=Path)
        if action == "apply":
            cmd.add_argument("--approve", action="store_true")
        if action == "plan":
            cmd.add_argument("--model")
        if action in ("inspect", "render", "export"):
            cmd.add_argument("--scenes", required=True, nargs="+")
        if action == "render":
            cmd.add_argument("--regenerate", nargs="*", default=[])
        if action == "export":
            cmd.add_argument("--mp3", action="store_true")
        if action == "select-take":
            cmd.add_argument("--segment", required=True)
            cmd.add_argument("--take", required=True)
    return p


def execute(args):
    if args.action == "extract":
        from .extraction import extract_chapter
        if args.images:
            paths = args.images
        else:
            import re
            from files import image_paths
            paths = image_paths(args.input)
            paths.sort(key=lambda p: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)])
        print(extract_chapter(paths, args.output, chapter_id=args.chapter_id, device=args.device, order=args.order, progress=print))
        return
    with workspace_lock(args.workspace):
        router = PipelineRouter(PipelineConfig.from_environment(args.workspace))
        if args.action == "create":
            with input_bundle(args.chapter) as chapter, input_bundle(args.cast) as cast, input_bundle(args.originals) as originals:
                router.create_project(chapter, cast, originals)
        elif args.action == "restore":
            router.restore_project(args.bundle)
        else:
            router.load_project()
            if args.action == "import-cast":
                with input_bundle(args.cast) as cast:
                    router.import_cast(cast)
            elif args.action == "plan":
                if args.output.exists():
                    raise FileExistsError("Proposal output already exists; choose a new path")
                write_new(args.output, schemas.dump(router.generate_proposal(args.model, progress=lambda e: print(e.message))))
            elif args.action == "load-proposal":
                router.apply_proposal(schemas.Proposal.model_validate(read_json(args.file)))
            elif args.action == "review":
                write_new(args.output, review_document(router.project, args.stage, args.scene))
            elif args.action == "apply":
                apply_review(router, read_json(args.file), args.approve)
            elif args.action == "settings":
                router.update_settings(schemas.SettingsUpdate.model_validate(read_json(args.file)))
            elif args.action == "narrate":
                router.insert_narration(schemas.NarrationInsert.model_validate(read_json(args.file)))
            elif args.action == "inspect":
                write_new(args.output, [schemas.dump(s) for s in router.inspect_segments(schemas.RenderSelection(scene_ids=args.scenes))])
            elif args.action == "render":
                router.render_selected(schemas.RenderCommand(scene_ids=args.scenes, regenerate=args.regenerate), progress=lambda e: print(e.message))
            elif args.action == "select-take":
                router.select_take(schemas.TakeSelection(segment_id=args.segment, take_id=args.take))
            elif args.action == "export":
                print(router.export_audio(schemas.RenderSelection(scene_ids=args.scenes), args.mp3).wav_path)
            elif args.action == "bundle":
                if args.output.exists():
                    raise FileExistsError("Bundle output already exists; choose a new path")
                print(router.bundle_project(args.output))
        project = router.project
        print(json.dumps({"chapter": project.chapter_id, "sources": len(project.sources),
                          "appearances": len(project.appearances), "scenes": [s.scene_id for s in project.scenes],
                          "approved_scenes": list(project.approvals), "takes": sum(map(len, project.takes.values()))}, indent=2))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        execute(args)
    except schemas.WorkflowError as exc:
        print(json.dumps(schemas.dump(exc.detail)), file=sys.stderr)
        return 1
    except schemas.ValidationError as exc:
        print("Invalid fields: " + ", ".join(".".join(map(str, e["loc"])) for e in exc.errors(include_input=False, include_context=False)), file=sys.stderr)
        return 1
    except ImportError:
        print("Missing dependency. Install requirements-audio.txt, and requirements.txt for MagiV3 extraction.", file=sys.stderr)
        return 1
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0
