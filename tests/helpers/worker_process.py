"""Subprocess harness for real worker execution with offline audio only."""
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

from tests.unit.engine.test_audio_pipeline import wav_bytes

from manga_worker import workflow as web_workflow
from manga_tts import PipelineRouter


def main():
    root, job, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    web_workflow.ROOT = root
    calls = 0

    def render(request):
        nonlocal calls
        calls += 1
        with (root / "render-calls.jsonl").open("a") as stream:
            stream.write(json.dumps(request) + "\n")
        if mode == "interrupt" and calls == 2:
            (root / "second-segment-started").touch()
            # The parent kills this process after verifying the first checkpoint.
            while True:
                time.sleep(.05)
        return wav_bytes()

    def router(config):
        return PipelineRouter(config, client_factory=lambda: object(),
                              renderer_factory=lambda client, model: render)

    with patch.object(web_workflow, "PipelineRouter", router):
        web_workflow.run_job(job)


if __name__ == "__main__":
    main()
