# Character analysis web proof of concept

The branch `character-analysis-web` starts from `main` and reuses the existing
reader UI from `development-web` (there was no web UI on `main`). The existing
Python model wrapper and pinned model configuration are unchanged.

## Run

Install the Python environment from the root README, then run:

```powershell
cd web
npm ci
npm run dev
```

Open http://127.0.0.1:3000. The server automatically uses the repository `.venv`.
Set `PYTHON_EXECUTABLE` in `web/.env.local` to use another Python environment.
Audio synthesis uses installed **Windows desktop speech voices** via
`System.Speech`; no API key or extra speech package is required. The speech child
process uses a process-scoped execution policy; it does not change the machine's
PowerShell policy. Image analysis also runs on other supported Python platforms,
but this initial audio adapter requires Windows.

## Workflow

1. Upload one or up to ten PNG/JPEG/WebP images (10 MB each, 50 MB total,
   25 megapixels per image). Initial page order uses natural filename sorting;
   arrow buttons let you adjust it before analysis.
2. Choose RTL or LTR and analyze. RTL preserves the model's OCR sequence. LTR
   applies a spatial panel/line fallback. Both can be corrected manually.
3. Add named characters and choose installed voices. Assign character crops to
   these persistent IDs. Apply an assignment to a suggested page cluster only
   when appropriate; individual assignments can correct a bad cluster.
4. Review text, inclusion, speaker appearances, off-panel identities, and line
   order. Unresolved identities are explicit and block audio for included lines.
5. Download/copy dialogue JSON; generate one line or all included lines; play or
   download the resulting WAV. Editing text, identities, voices or order removes
   stale audio from the UI. Unchanged audio clips are reused on the next request.

Character names, stable IDs and voice choices persist in browser local storage.
Export/import the character registry to carry it to another browser. Page edits
and appearance assignments remain in the active page; download the dialogue JSON
before leaving. Clearing images does not clear your character registry.

## Implementation and limits

Read [CHARACTER_ANALYSIS_WALKTHROUGH.md](../CHARACTER_ANALYSIS_WALKTHROUGH.md)
for every file/function and its relationship to the supplied notebook.

The server runs one analysis and one audio request at a time per Node process.
A fresh model process is used for each uncached analysis request, with one model
load shared across that request's images. The process timeout is 30 minutes;
CPU-only inference can be slow. Uploaded originals are temporary and removed
following the request. Raw detection/OCR caches remain in `.cache/analysis`, and
per-line audio remains in `.cache/audio`. Character crops are small embedded PNGs.

This is a local proof of concept, without login, a distributed job queue, automatic
cross-page recognition, voice cloning, translation, narration generation, or cloud
hosting. Keep the provided loopback-only server binding. LTR ordering and spatial
matching are heuristics; review complex layouts. The model's essential flag is a
suggestion, not a guaranteed dialogue-versus-SFX classification.

## Checks

```powershell
# From repository root:
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
# From web:
npm run typecheck
npm run build
```

See the walkthrough for verification evidence and its limits.
