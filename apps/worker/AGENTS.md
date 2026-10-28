# Worker application guide

This app owns local workflow/OCR execution and the private HTTP credential boundary. Import engine decisions from `manga_tts`; import image utilities from `manga_vision`. The engine imports no worker modules.

Read `../../packages/engine/AGENTS.md` for production invariants. `src/manga_worker/workflow.py` owns request staging, snapshots, operation dispatch, and recovery. `http_api.py` and `http_auth.py` own service/user credential separation. Verification mode rejects project/asset/operation access before touching workspaces.

Use installed modules or console entrypoints. Data paths come from `MANGA_DATA_ROOT` or the documented checkout/installed default, never caller working directory. Pass the resolved data root to child processes. Preserve JSON-only stdout and sanitized errors.

Run worker unit tests and process/HTTP integration tests. Run `npm run test:http` when changing transport, packaging, paths, auth, or web interaction. A passing fixture identity test does not establish live cloud authorization.
