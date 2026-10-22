# Validation record

## Audio integration on dev-test-1 (2026-10-17)

### Frontend integration

- Adapted the `character-analysis-web` UI and its original styles/layout. Windows
  speech routes were replaced with reviewed Manga-TTS worker/job and asset routes.
- Next.js production build and TypeScript checks pass.
- Six new worker tests pass: snapshots/approvals/evidence, inspect-render-export-bundle,
  stale edits, safe validation errors, restore/cleanup, and identifier validation.
- The optional HTTP integration check passes against the production Next server:
  multipart ZIP upload, asynchronous restore, snapshot, inspect, cached render,
  export, bundle download, WAV byte ranges, missing mutation header rejection and
  path traversal rejection. Uses synthetic input/audio; no model/provider requests.
- Browser visual verification was attempted but automatic approval review blocked
  opening the local app because its usage limit was reached. No alternative browser
  automation was used. Responsive styling is implemented but not visually verified.
- Local HTTP checks require network access outside this environment's sandbox.

### Backend integration

- Imported the supplied loose `manga_tts` package; added chapter extraction and a
  CLI without copying the sample manga/profile/audio assets into the repository.
- Offline integration tests exercise real file storage, review contracts, approval
  gates, speaker segmentation, silence/narration, take validation, targeted regeneration,
  partial-render resume, WAV assembly, archive safeguards and restore.
- Final test run: 17 tests passed, including the optional supplied-project test.
- The supplied version-2 four-scene/six-take project was checked in temporary copies.
  Reusing takes never created an API client. Export reproduced its 92.23-second
  chapter WAV byte-for-byte, including after bundle/restore.
- CLI help and Python compilation checked. Test runtime: local Python 3.11 with
  Pydantic 2.14.1 and Pillow. The sandbox's default temporary directory blocked atomic
  renames; tests ran with TEMP/TMP directed to the repository's ignored .cache/test-tmp.
- No new paid Gemini requests were made. Live provider compatibility, acting quality,
  actual Magi inference/accuracy and ffmpeg MP3 conversion were not verified in this
  integration pass. The available PyTorch runtime is CPU-only.
- The optional external-sample test is skipped when MANGA_TTS_SAMPLE_PROJECT is unset.

## Original main-branch starter

Prepared on 2026-10-07.

Passed:

- All project Python files compile.
- Command-line help runs without loading the model.
- Two local tests pass: image/caption/output handling and task dispatch/input validation. The dispatch test uses a fake model.
- Each directly pinned dependency release exists on PyPI; metadata permits Python 3.11. This is not a full dependency-resolution or installation test.
- Method signatures, imported dependencies, RGB image support, result structures, and the checkpoint's recorded Transformers version were checked in upstream source at revision `49c73a225122d53adbaa26d53868be81a57706e2`.

Not verified:

- Full dependency installation in Python 3.11.
- Checkpoint download, real model loading, or inference on CPU/GPU.
- Numerical accuracy, processing time, or minimum RAM/VRAM.

Local checks ran using the app's bundled Python 3.12 and Pillow. That environment does not contain PyTorch or Transformers. No real model results are included or implied. Use the README setup and one image to validate the complete pipeline on your machine.

## Current web-app cleanup (2026-10-17)

- Removed the eight unused Colab/Jupyter presentation modules. Web and CLI review
  continue through the same backend; original supplied files remain outside this repo.
- Removed 78 unused selectors inherited from the previous frontend and unused imports.
- Retained all runtime modules, CLI commands, tests, dependency manifests/lockfile,
  project instructions, original starter files, and user data.
- After cleanup: 24 tests passed, including byte-identical sample WAV reproduction;
  one optional live-server HTTP test was skipped. Production build and TypeScript
  checks passed. Browser visual verification remains unavailable due to the earlier
  tool approval usage limit; no new live model/provider calls were made.
## Codebase cleanup verification — 2026-10-18

- Moved supporting guides into `docs/`, shared studio UI into `web/components/`,
  and frontend regression tests into `web/tests/`; updated imports and setup links.
- Removed the disconnected fictional catalog, placeholder reader, browser-local
  request form, their mock data, and 477 lines of associated styles.
- Retained all model adapters, CLI/API entry points, saved results, model assets,
  dependencies, and assistant configuration.
- Python suite: 48 tests, 46 passed and 2 skipped (external sample and opt-in HTTP).
- Separately ran the opt-in HTTP integration against a production server: passed
  upload/restore, audio reuse, export, and download checks using synthetic audio.
- Frontend regression tests: 8 passed. TypeScript check and production build passed.
- Opened the production studio in a browser and inspected its initial page and styling.
- Windows sandbox restrictions affected temporary-file operations, subprocess mocks,
  and build path resolution; verification passed outside the sandbox.
- Live Magi inference and Gemini generation were not rerun; no model/provider code changed.

Run commands from the repository root, or from `web/` for npm commands.

## Optional detector removal — 2026-10-18

Removed the unused alternate detector, its CLI flags and dependency list,
downloaded source and checkpoint, and obsolete setup documentation. MAGI remains
the extraction backend; existing MAGI CLI arguments and result paths are preserved.
Updated runner tests retain validation and repeated-output coverage.
Python regression suite: 45 tests, 43 passed and 2 optional tests skipped.

## Browse restoration — 2026-10-18

Restored the original browse, manga details, reader, request form, sample catalog,
and their complete styles from Git at the user's request. This supersedes the
earlier cleanup note about removing those pages. Component organization and the
optional detector removal remain in place.
