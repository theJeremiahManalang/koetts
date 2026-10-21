"""Subprocess harness for durable-operation recovery with synthetic audio only."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

from test_audio_pipeline import wav_bytes

import web_workflow
from manga_tts import PipelineRouter, resolution


def main() -> None:
    root, operation_id, fence, mode = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4]
    web_workflow.ROOT = root
    calls = 0

    def render(request):
        nonlocal calls
        calls += 1
        with (root / "render-calls.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(request) + "\n")
        if mode == "interrupt" and calls == 2:
            (root / "second-segment-started").touch()
            while True:
                time.sleep(.05)
        return wav_bytes()

    def router(config, **options):
        return PipelineRouter(
            config,
            client_factory=lambda: object(),
            renderer_factory=lambda _client, _model: render,
            **options,
        )

    if mode.startswith("plan"):
        def propose(project, _root, _client, **options):
            options["before_provider"]()
            (root / "planning-called").touch()
            data = {"appearances": [], "sources": [], "scenes": []}
            project["proposal"] = {"cache_key": "offline", "evidence": "fixture", "data": data}
            return data

        patch.object(resolution, "propose_plan", propose).start()

    if mode in {"between-checkpoints", "before-notification", "failed-notification", "plan-checkpoint"}:
        original_perform = web_workflow.perform

        def pause_after_checkpoint(engine, request, progress, **options):
            def report(message, **details):
                if mode == "failed-notification" and details.get("status") == "saved":
                    (root / "first-segment-saved").touch()
                    raise RuntimeError("Progress transport failed after persistence")
                if mode != "before-notification" or details.get("status") != "saved":
                    progress(message, **details)
                if details.get("status") == "saved" or (
                    mode == "plan-checkpoint" and details.get("stage") == "planning" and details.get("status") == "complete"
                ):
                    (root / "first-segment-saved").touch()
                    while True:
                        time.sleep(.05)

            return original_perform(engine, request, report, **options)

        patch.object(web_workflow, "perform", pause_after_checkpoint).start()

    with patch.object(web_workflow, "PipelineRouter", router):
        web_workflow.run_operation(operation_id, fence)


if __name__ == "__main__":
    main()
