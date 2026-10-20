# Manga audiobook studio

Extract dialogue from manga images, review character assignments and scripts,
generate character voices, and export chapter audio. The local Next.js studio
uses the Python `manga_tts` backend. Cast and script approval are required before
speech generation.

## Start locally

1. Set up Python and the extraction models using [the model setup guide](docs/MODELS.md).
2. Install the audio dependencies with `.\.venv\Scripts\python.exe -m pip install -r requirements-audio.txt`.
3. Follow [the web setup guide](web/README.md): run `npm ci` and `npm run dev` inside `web/`, then open http://127.0.0.1:3000.

Set `GEMINI_API_KEY` in the server environment for new planning and speech
generation. Reviewing existing projects does not require provider calls.
See [the audio workflow guide](docs/AUDIO_WORKFLOW.md) for CLI commands and recovery.
Run all commands from the repository root unless a guide says otherwise.

## Project structure

- `manga_tts/`: extraction, cast resolution, script review, speech generation, and project storage.
- `web/app/`: studio, browse catalog, manga details, reader, request form, loading route, and backend API routes.
- `web/components/`: cast, source, script, image-order, and loading components.
- `web/lib/`: shared types, review logic, and Python worker integration.
- `tests/` and `web/tests/`: Python integration tests and frontend regression tests.
- `docs/`: model setup, audio workflow, research, historical walkthrough, and validation notes.
- `images/`: sample image and input guidance.
- Root Python modules: shared model adapters and the supported `run.py`, `web_extract.py`, and `web_workflow.py` entry points. `example.py` and `captions.example.json` demonstrate model use.

Local `results/`, `.cache/`, `.venv/`, and web build/dependency folders are ignored
by Git. Results may contain saved projects and audio; keep these when cleaning
generated files. MAGI downloads its model assets to the Hugging Face cache.
See the [documentation index](docs/README.md) for current architecture and the accepted
shared reader/admin target. `AGENTS.md` routes assistants to task-specific context;
project skills remain under `.agents/skills/`.

## Verify changes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd web
npm test
npm run typecheck
npm run build
```

Python tests use synthetic predictions and audio without provider calls. Some
tests require an explicitly configured local HTTP server or external sample data;
their skip messages explain the required setup. Real model and provider checks
are described in [the validation notes](docs/VALIDATION.md).
