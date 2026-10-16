# Character analysis implementation walkthrough

## Branch and reused setup

`character-analysis-web` was created from `main`. At implementation time, `main`
had the Python starter but no tracked web UI. The existing `web/` UI and package
setup were copied from `development-web`, then adapted. No changes were made to
`main`, the user-pasted notebook, `magi.py`, `config.py`, `files.py`, or `run.py`.

The reader retains the existing paper/sage palette, header, two-column layout,
image zoom, responsive cards, buttons, and toast notifications. Sample story,
narration-detail controls, and sound-effect placeholders were removed because
this proof of concept deals with actual dialogue and character voices.

## Connected flow

Upload images and choose direction → `/api/extract` → `web_analyze.analyze()` →
existing `Magi.predict(task="all")` → detection + OCR →
`normalize_page()` → editable dialogue and character crops → persistent character
registry + voice assignments → `scriptFor()` → `/api/audio` →
`validate_script()` → per-line synthesis → combined WAV.

Detection and OCR are separate predictions. Reading order and spatial matching
are separate concerns: preserve the OCR sequence for RTL while matching each OCR
box to a detection text box to obtain its speaker association. LTR uses a spatial
fallback. Neither matching nor ordering is represented as guaranteed correct.

## Files and functions

### `character_analysis.py` — replacement for the normalization responsibilities in notebook cell 4

- `box(value)` validates finite, nondegenerate four-coordinate boxes. Malformed
  model data fails explicitly instead of silently producing a broken script.
- `overlap(a, b)` computes intersection over union. Unlike the notebook's
  `compute_iou_and_containment()`, it compares independent OCR and detection
  regions, rather than assigning an inner box to a containing panel.
- `spatial_order(boxes)` provides the LTR fallback: group vertically overlapping
  regions into rows and order each row left to right. Row grouping uses a fixed
  anchor to limit tall-region chaining. It remains a heuristic.
- `normalize_page(detection, ocr, image, page_id, direction)` performs the core
  conversion. It reads `ocr_texts` and `bboxes`, verifies their lengths, creates
  character appearance IDs, preserves page cluster labels, and makes padded
  thumbnail crops as embedded PNGs. It matches text by IoU (minimum 0.25 and a
  0.10 lead over the second candidate), attaches direct speaker associations,
  and keeps weak matches and multiple speakers unresolved. Multiple OCR
  fragments may match the same detection. Detected regions with no confident
  OCR match remain excluded, blank review entries. RTL leaves the OCR list in
  its returned order; LTR groups lines by panel and uses spatial ordering inside
  each group. Unassigned LTR regions follow assigned panels for manual review.

Connections to the notebook: replaces OCR string extraction, ID assignment,
character crops, essential flags, and direct association conversion. Removes
unconditional `sort_panels_manga()` / weighted `intra_panel_key` sorting for RTL
and unsupported character-to-tail reconstruction. Crop padding remains 5%, as
in the supplied notebook. Page cluster IDs are scoped to a page; they are never
assumed to identify the same person across images.

### `web_analyze.py` — notebook cells 2, 6 and the JSON part of cell 7

- `analyze(manifest_path)` reads the API's ordered upload manifest; validates image
  formats and pixel limits; fixes EXIF orientation; converts to RGB; loads the
  existing `Magi` wrapper once per uncached request; runs detection and OCR for
  each image; and calls `normalize_page()`.
- `CACHE_VERSION` marks the preprocessing/analysis cache contract. The SHA-256
  key contains RGB pixel content, image dimensions, model ID, pinned revision,
  and cache version. Changing images cannot accidentally reuse page-number
  caches. Direction is intentionally outside the raw cache: normalization can
  be rerun in either direction without repeating model inference.
- The `__main__` block sends model logs to stderr and emits only JSON on stdout,
  allowing Next.js to parse the result reliably.

Raw model results are retained in `.cache/analysis`. Temporary writes are renamed
only after successful serialization. The original notebook's synthetic-page
fallback and ZIP packaging are not in the upload flow. Unlike its forced
RGB→grayscale→RGB preprocessing, this branch retains the existing repository's
EXIF-corrected RGB setup. Both crops and model coordinates use that same image.

### `web/lib/python.ts` — shared local Python execution

- `root` resolves the repository above the web working directory.
- `python(script, args)` chooses `PYTHON_EXECUTABLE`, the local `.venv`, or Python
  on PATH. It executes a fixed script with separate arguments, hides Windows
  console windows, sets UTF-8, and bounds runtime/output. Routes do not construct
  shell commands from uploaded filenames or dialogue text.

### `web/app/api/extract/route.ts` — upload boundary

- `POST(request)` accepts an ordered list of images and RTL/LTR direction. It
  validates number, MIME type, file size and combined size, writes temporary
  files with server-generated names, invokes `web_analyze.py`, and returns JSON.
  It limits analysis to one request per Node process and cleans up temporary
  originals in `finally`, including on failure.

This replaces the old OCR-only endpoint while retaining its local-process model.
It corresponds to notebook ingestion plus the inference loop, not model loading
in the browser. Pillow independently verifies actual image content.

### `web/lib/analysis.ts` — web data contract and audio handoff

- `Character`: stable UUID, editable name, selected installed voice.
- `Appearance`: page-specific detection ID, box, page cluster/group, crop, and
  user-assigned persistent character ID.
- `Line`: recognized/edited text, source page, detection match, candidate speaker
  appearances, selected appearance, inclusion and review warning.
- `Page` / `Analysis`: ordered image results and model provenance.
- `scriptFor(...)` resolves appearance → persistent character → voice for every
  line, assigns consecutive chapter sequence numbers, records source filenames,
  and strips crop data from the audio-facing JSON. Off-panel speakers use an
  explicitly selected character without requiring a visible appearance.
- `playbackErrors(script, voices)` checks included lines for nonempty text,
  resolved characters and currently available voices. Unresolved lines can be
  excluded or corrected. These client checks supplement server validation.

This is the layer absent from the notebook: the chapter analysis becomes a
voice-ready script while retaining source and appearance references.

### `web/app/page.tsx` — reused reader UI and review controls

- `Home()` owns uploaded images, analysis, editable lines, appearances, registry,
  selected direction, errors, generated audio and loading state.
- Effects load voices and the saved registry, persist registry changes, and
  create/release image and audio object URLs.
- `invalidateAudio()` pauses and removes stale audio after edits.
- `resetAnalysis()` clears analysis and audio when input/order/direction changes.
- `selectFiles()` checks upload limits, naturally sorts filenames, and resets
  dependent state. Uploading alone does not run inference.
- `movePage()` changes image sequence before analysis.
- `extract()` submits uploads/direction and stores normalized results.
- `addCharacter()` creates a persistent UUID; `updateCharacter()` changes name
  or voice while keeping that UUID.
- `assignAppearance()` links a crop to a persistent character. The optional
  whole-cluster action assigns all appearances in that model-suggested page
  cluster. Individual assignments can split an incorrectly grouped cluster.
- `updateLine()` edits text, inclusion, appearance or explicit off-panel identity.
- `addLine()` adds manually transcribed dialogue for the selected page, even if
  the model missed every region. Its box is the page extent, not a claimed model
  detection; the user positions it using the order buttons.
- `moveLine()` changes chapter playback order without changing stable line IDs.
- `download()` exports JSON; `copyJson()` copies the same reviewed script.
- `parseRegistry()` validates imported/stored character records and duplicate IDs.
- `importRegistry()` merges registry records by stable ID. This allows identities
  and voices to move between browsers without guessing cross-page recognition.
- `generateAudio()` validates the reviewed script and requests either all included
  lines or a single selected line. It creates an audio player/download URL from
  the returned WAV and shows failures instead of substituting another voice.

The browser persists the character registry, not uploaded images or active page
edits. Download JSON to retain a reviewed script. Character crops and explicit
unknown-speaker controls take the place of notebook-only diagnostic inspection.

### `web/app/api/voices/route.ts`

- `GET()` calls the Python speech bridge to list enabled Windows voices. Failure
  returns an explicit unavailable state. No browser-dependent voice identifier is
  passed to a different synthesis engine.

### `web/app/api/audio/route.ts`

- `POST(request)` bounds script size, serializes audio jobs per Node process,
  creates temporary script/output paths, calls `web_audio.py`, and serves an
  uncached WAV response. Cleanup runs on both success and failure.

### `web_audio.py` — new audio stage after notebook cell 7

- `speech(args)` executes the fixed PowerShell helper, captures output, hides the
  child window, and limits each speech invocation to two minutes. Windows is
  required by this adapter. The process-scoped execution policy does not change
  system settings.
- `voices()` parses the installed, enabled voice names.
- `validate_script(script, available)` checks record counts, duplicate references,
  line IDs and sequence, included text lengths, selected voice availability,
  identity/voice consistency, and appearance/identity agreement. Unknown speakers
  cannot silently receive an arbitrary voice. Excluded lines need not be voiced.
- `generate(script, output)` validates, synthesizes changed lines, and reuses WAVs
  keyed by text, voice, rate and engine/format version. It validates audio format
  and joins clips in line sequence with 300 ms pauses. Changing one line does not
  resynthesize unchanged clips. Output is mono, 16-bit PCM at 22,050 Hz.
- The `__main__` block either lists voices or generates a supplied reviewed script.

### `speech.ps1`

This helper has two modes rather than named functions. Without `RequestPath`, it
lists enabled installed voices. With a JSON request, it selects the requested
voice and rate, writes a WAV, speaks the text as text (not executable code/SSML),
and disposes the synthesizer. The synthesis engine is Windows `System.Speech`.
It does not implement voice cloning or ingest custom voice samples.

### Reused web support files

- `web/app/globals.css`: original reader styles plus character forms, crops,
  dialogue editors, page ordering, and responsive audio controls using the same
  visual tokens.
- `web/app/layout.tsx`: unchanged shared `RootLayout()` and page metadata.
- `web/package.json` / `package-lock.json`: reused Next.js, React, Tailwind, Sonner
  and TypeScript dependencies; no new speech service dependency.
- `web/postcss.config.mjs`: reused Tailwind PostCSS setup.
- `web/tsconfig.json` / `next-env.d.ts`: reused TypeScript/framework setup.
- `web/AGENTS.md`: retained framework guidance; local Next.js docs were consulted.
- `web/README.md`: current startup instructions, workflow, limits and cache notes.
- `.gitignore`: excludes node modules/build output, local model weights/vendor
  checkout, and retains existing cache exclusions.

### Existing Python files reused without changes

- `config.py`: the model ID and fixed upstream revision replace the notebook's
  unpinned model repository reference.
- `magi.py`: `Magi.__init__()` handles processor/model loading and CPU/CUDA dtype;
  `Magi.predict()` dispatches detection and OCR under inference mode. This reuses
  the notebook's intended loading/inference responsibilities without copying its
  broad exception-based OCR signature fallback.
- `files.py`: `json_default()` converts tensor/array model values for raw caching,
  corresponding to the notebook's `to_serializable()`.
- `run.py`, `example.py` and original file/overlay helpers continue to work as
  before. They are not part of the new web request path.

## Verification

The new `tests/test_character_analysis.py` contains nine tests:

- Geometry-based OCR matching despite reversed list positions, RTL preservation,
  essential flags, and embedded crop generation.
- LTR panel ordering and dialogue ordering within a panel.
- Multiple candidate speakers remain unresolved.
- Missing OCR remains reviewable and cluster IDs are page-scoped.
- Invalid OCR lengths fail explicitly.
- Raw inference cache survives direction changes but not changed image pixels.
- Invalid text, voice, character, appearance or sequence blocks synthesis.
- Explicit off-panel speakers work and excluded blank lines are ignored.
- Per-line cache reuse and chapter audio length including pauses.

Together with the existing two tests, all 11 pass. TypeScript and production build
checks pass. Real Windows synthesis with Microsoft David Desktop and Microsoft
Zira Desktop produced a WAV. A headless Edge check exercised registry persistence,
upload/review with a clearly labeled model-output fixture, missing-identity blocking,
real audio generation through the API, stale-audio invalidation, mobile layout,
and invalid upload rejection. Desktop/mobile screenshots were visually inspected.
These fixture tests validate application behavior, not model recognition accuracy.

A real offline CPU run of the cached pinned Magi model on `images/page1.jpg`
completed successfully: 3 panels, 2 character appearances and 9 OCR lines. Three
lines had a single linked appearance; six were retained for speaker review. This
checks the actual model response contract and image-to-script path, not general
accuracy. The sample contains recognition errors that the text editor can correct.
The existing Python environment is PyTorch 2.5.1 CPU; CUDA was unavailable.

The final browser check also used the real cached model output through the upload
API: two appearance controls and nine editable lines rendered successfully. With
explicit test identity assignments (not claims about the manga characters), the
real audio endpoint generated the nine-line WAV. Adding a blank manual line
correctly blocked full-script audio until corrected or excluded. Multi-image
cache tests confirm repeated images retain distinct page IDs while reusing raw
inference. The final production build and all 11 tests pass.
