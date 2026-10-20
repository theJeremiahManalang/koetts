"""Subprocess harness for durable-operation recovery with synthetic audio only."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

from test_audio_pipeline import wav_bytes

import web_workflow
from manga_tts import PipelineRouter


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

    def router(config):
        return PipelineRouter(
            config,
            client_factory=lambda: object(),
            renderer_factory=lambda _client, _model: render,
        )

    if mode == "between-checkpoints":
        original_perform = web_workflow.perform

        def pause_after_checkpoint(engine, request, progress, **options):
            def report(message, **details):
                progress(message, **details)
                if details.get("status") == "saved":
                    (root / "first-segment-saved").touch()
                    while True:
                        time.sleep(.05)

            return original_perform(engine, request, report, **options)

        patch.object(web_workflow, "perform", pause_after_checkpoint).start()

    with patch.object(web_workflow, "PipelineRouter", router):
        web_workflow.run_operation(operation_id, fence)


if __name__ == "__main__":
    main()
