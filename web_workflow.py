"""Local Next.js bridge for reviewed Manga-TTS jobs. Never trusts client paths."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

from manga_tts import PipelineConfig, PipelineRouter, schemas
from manga_tts.cli import workspace_lock
from manga_tts.config import VOICES
from manga_tts.extraction import extract_chapter
from manga_tts.script import cast_signature, scene_signature
from manga_tts.storage import asset, digest, read_json, write_json

ROOT = Path(__file__).resolve().parent / "results" / "web"


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("Invalid project or job identifier")
    return value


def snapshot(router):
    data = schemas.dump(router.project)
    pages = []
    for page in data["chapter"]["pages"]:
        candidates = [f"originals/{page.get('image_filename', '')}", f"input/{page.get('image_filename', '')}",
                      f"input/previews/page_{page['page_index']:03d}_annotated.jpg"]
        image = next((p for p in candidates if asset(router.root, p).is_file()), None)
        pages.append({**page, "preview_path": image})
    exports = [p.name for p in (router.root / "exports").glob("*") if p.is_file() and p.suffix in {".wav", ".mp3", ".json"}]
    return {"project": data, "revision": digest(data), "pages": pages, "voices": VOICES,
            "cast_approved": data["cast_approval"] == cast_signature(data),
            "approved_scenes": [s["scene_id"] for s in data["scenes"] if data["approvals"].get(s["scene_id"]) == scene_signature(data, s)],
            "exports": exports, "has_api_key": bool(os.environ.get("GEMINI_API_KEY"))}


def perform(router, request, progress):
    action = request["action"]
    upload = ROOT / "uploads" / identifier(request["job"])
    if action == "create":
        mode = request.get("mode")
        if mode == "restore":
            router.restore_project(upload / "chapter.zip")
        else:
            chapter = upload / "chapter.zip"
            if mode == "images":
                images = [asset(upload, name) for name in request["images"]]
                extract_chapter(images, chapter, device="auto", order="model" if request.get("direction") == "rtl" else "ltr", progress=progress)
            elif mode != "chapter":
                raise ValueError("Choose images, chapter input or project restore")
            cast = upload / "cast.zip"
            router.create_project(chapter, cast if cast.exists() else None)
        return {}
    router.load_project()
    if request.get("revision") != digest(schemas.dump(router.project)):
        raise ValueError("This project changed in another session. Reload before applying your edits.")
    command = request.get("command", {})
    if action == "cast-import":
        router.import_cast(upload / "cast.zip")
    elif action == "cast-create":
        router.create_cast_member(schemas.CastCreate.model_validate(command))
    elif action == "plan":
        router.generate_proposal(progress=lambda e: progress(e.message))
    elif action == "proposal":
        router.apply_proposal(schemas.Proposal.model_validate(command))
    elif action in {"cast", "sources", "script", "settings", "narration", "take"}:
        types = {"cast": (schemas.CastReview, router.apply_cast_review),
                 "sources": (schemas.SourceReview, router.apply_source_review),
                 "script": (schemas.SceneReview, router.apply_scene_review),
                 "settings": (schemas.SettingsUpdate, router.update_settings),
                 "narration": (schemas.NarrationInsert, router.insert_narration),
                 "take": (schemas.TakeSelection, router.select_take)}
        contract, method = types[action]
        method(contract.model_validate(command))
    elif action == "inspect":
        return {"segments": [schemas.dump(s) for s in router.inspect_segments(schemas.RenderSelection.model_validate(command))]}
    elif action == "render":
        result = router.render_selected(schemas.RenderCommand.model_validate(command), progress=lambda e: progress(e.message))
        return {"segments": [schemas.dump(s) for s in result.segments]}
    elif action == "export":
        router.export_audio(schemas.RenderSelection.model_validate(command), mp3=request.get("mp3") is True)
    elif action == "bundle":
        router.bundle_project(ROOT / "downloads" / (request["project"] + ".zip"))
    else:
        raise ValueError("Unknown workflow action")
    return {}


def run_job(job):
    job = identifier(job)
    status_path = ROOT / "jobs" / (job + ".json")
    request = read_json(ROOT / "jobs" / (job + ".request.json"))
    project = identifier(request["project"])
    request["job"] = job
    def update(message, status="running", **extra):
        write_json(status_path, {"id": job, "project": project, "status": status, "message": message, **extra})
    try:
        update("Preparing workspace…")
        with workspace_lock(ROOT / "projects" / project):
            router = PipelineRouter(PipelineConfig.from_environment(ROOT / "projects" / project))
            result = perform(router, request, update)
        update("Ready for review.", "complete", result=result)
    except schemas.WorkflowError as exc:
        update(exc.detail.message, "failed")
    except schemas.ValidationError as exc:
        fields = [".".join(map(str, e["loc"])) for e in exc.errors(include_input=False, include_context=False)]
        update("Invalid review fields: " + ", ".join(fields), "failed")
    except (ValueError, FileNotFoundError) as exc:
        # Only local workflow errors; provider errors are sanitized by the router.
        update(str(exc)[:400], "failed")
    except Exception:
        update("Operation failed. Check dependencies and workspace access. Completed audio is retained.", "failed")
    finally:
        # Uploaded staging files are not needed once imported. Use only the fixed job directory.
        import shutil
        staging = ROOT / "uploads" / job
        if staging.exists():
            shutil.rmtree(staging)


def main():
    action, value = sys.argv[1:3]
    if action == "job":
        run_job(value)
    elif action == "snapshot":
        with workspace_lock(ROOT / "projects" / identifier(value)):
            router = PipelineRouter(PipelineConfig.from_environment(ROOT / "projects" / value))
            router.load_project()
            print(json.dumps(snapshot(router), ensure_ascii=False))
    else:
        raise ValueError("Unknown bridge command")


if __name__ == "__main__":
    main()
