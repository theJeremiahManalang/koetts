# Manga panels to reviewed audio

The Python CLI and local Next.js studio share a per-project single-writer engine.
Start with [developer setup](development.md). Firebase identity protects studio access;
local SQLite and filesystem workers coordinate production on one host. Hosted shared
processing remains migration work.

## Environment

Follow [developer setup](development.md). The root uv workspace installs review/audio and worker dependencies; optional vision extras add extraction dependencies. MP3 export uses the bundled imageio-ffmpeg encoder or system ffmpeg. Configure `GEMINI_API_KEY` only in the server environment for planning/synthesis. Live provider compatibility remains a separate check.

The web studio persists operations in `results/web/operations.sqlite3` before
returning an operation ID. This local SQLite scheduler allows one MAGI operation and
one pipeline operation at a time on the same host, and serializes work per project.
It is not a distributed queue and the database must stay on local storage. A worker
lease uses a 15-second heartbeat and 60-second expiry, with a 30-minute attempt
limit. Uncertain provider outcomes keep their stage slot until explicit local
reconciliation. Retrying an uncertain operation may repeat provider billing and
counts toward the three-attempt ceiling.

The following examples use `uv run python` from the repository root. Generated projects and drafts
in these examples are under the already ignored `results/` directory.

## 1. Extract images in the intended sequence

```powershell
uv run manga-tts extract --images page1.png page2.png page3.png --output results/chapter.zip --device cuda
```

You can upload individual panels or complete pages. The explicit file sequence is
preserved. Alternatively, `--input images` uses natural filename order (page2
before page10). Images are EXIF-oriented and stored as RGB PNG evidence; coordinates
refer to those images. Originals are never modified.

Default `--order model` preserves MagiV3's predicted RTL panel/text order.
`--order rtl` proposes whitespace-based horizontal bands and right-to-left columns;
`--order ltr` reverses column traversal. These are editable proposals, not guarantees
for overlapping, diagonal, inset, or artistic layouts. AI planning and human source
review can correct order across panel and page boundaries.

The chapter ZIP contains `chapter_analysis.json`, page images, character crops,
annotated previews, raw predictions, source image hashes and extraction diagnostics.
OCR is matched geometrically, never by detection array index. Multiple contained
OCR lines can populate one detected bubble. Unmatched/ambiguous OCR is retained as
separate reviewable text; unresolved detection text stays blank. In model-order
mode unmatched OCR is appended and explicitly flagged for order review. Resolve
duplicates or missing words before approval. Model essential-text flags remain
evidence and determine initial inclusion; review excluded text as well.

IDs are persistent within the imported project. A fresh extraction is a new import;
automatic reconciliation of human edits across extraction reruns is not implemented.

## 2. Create the review project and import cast references

```powershell
uv run manga-tts create --workspace results/chapter-project --chapter results/chapter.zip --cast cast_references
```

`--chapter`, `--cast`, and optional `--originals` accept ZIPs or unpacked folders.
This supports the exact sample folders supplied for this project. Creation requires
an empty workspace. A cast folder has `cast.json` at its root, with entries such as:

```json
{"characters":[{"speaker_id":"ALICE","name":"Alice","references":["alice.png"],"voice":"Kore","pronunciation":"Alice","acting_notes":"Warm, natural delivery"}]}
```

Named characters need reference images. Optional `profile_path` points to a UTF-8
profile in the same bundle. A generic cast entry may use `is_generic: true` without
an image; it represents a shared voice, not a single character identity. `UNKNOWN`
means unresolved; `NARRATOR` is separate and is never an attribution fallback.
To import cast later: `uv run manga-tts import-cast --workspace results/chapter-project --cast cast_references`.

## 3. Generate and explicitly load an AI proposal

```powershell
uv run manga-tts plan --workspace results/chapter-project --output results/proposal.json
uv run manga-tts load-proposal --workspace results/chapter-project --file results/proposal.json
```

Planning uses pages, crops, references and OCR to propose identities, dialogue order,
scene boundaries, acting and optional visible-evidence narration. Generate saves a
proposal; loading applies it but does not approve it. Review the JSON before loading.
It is also possible to skip planning and edit the cast/sources manually.

## 4. Review cast, then source order, then exact script

```powershell
uv run manga-tts review --workspace results/chapter-project --stage cast --output results/cast-review.json
```

Edit the generated `command` fields: assign each appearance to a speaker or reject
false detections, and choose voices. Then explicitly approve:

```powershell
uv run manga-tts apply --workspace results/chapter-project --file results/cast-review.json --approve
uv run manga-tts review --workspace results/chapter-project --stage sources --output results/sources-review.json
```

Edit the sources against the page evidence: text, inclusion, speaker, unique order,
scene/group IDs, and delivery. Only consecutive compatible bubbles may share a
turn group. Apply sources before final script edits: rebuilding source groups replaces
dialogue-turn wording. Original recovered text remains immutable evidence.

```powershell
uv run manga-tts apply --workspace results/chapter-project --file results/sources-review.json
uv run manga-tts status --workspace results/chapter-project
uv run manga-tts review --workspace results/chapter-project --stage script --scene scene_001 --output results/scene-001-review.json
uv run manga-tts apply --workspace results/chapter-project --file results/scene-001-review.json --approve
```

Review the script file before the final command. Repeat the last two commands for
each scene listed by `status`. Omitting `--approve` saves an unapproved draft.
Unresolved included speakers, empty speech, invalid grouping, unsupported tags and
stale approvals block rendering. No automatic blanket approval is performed.

Review documents contain a base-state fingerprint. Any intervening applied change
requires a fresh document; do not edit the fingerprint to bypass the check. Export
and apply one review at a time. Existing draft/proposal output files are not overwritten.

Use the web interface for visual review, crop-based character creation without a
cast ZIP, and audio audition. CLI and web commands share a workspace lock; direct
router callers remain responsible for single-writer ownership. The web scheduler
checks operation-owned process identity before releasing a stale lock or stage slot;
do not remove operation locks manually. If a provider outcome remains uncertain,
resolve it with the configured Python interpreter:

```powershell
uv run manga-worker reconcile OPERATION_ID fail
uv run manga-worker reconcile OPERATION_ID retry
```

Choose `retry` only after accepting possible duplicate provider billing. Standalone
CLI locks still require confirming the recorded process has stopped before manual
removal. If the web worker's process identity cannot be read, confirm it has stopped
and append `--worker-stopped` to the reconciliation command.

## 5. Inspect, render, audition and export

```powershell
uv run manga-tts inspect --workspace results/chapter-project --scenes scene_001 scene_002 --output results/requests.json
uv run manga-tts render --workspace results/chapter-project --scenes scene_001 scene_002
uv run manga-tts export --workspace results/chapter-project --scenes scene_001 scene_002
uv run manga-tts bundle --workspace results/chapter-project --output results/reviewed-project.zip
```

Use the actual scene IDs from `status`. Inspection requires approvals and makes no
provider call. Rendering preflights the whole selection, splits requests at two
speakers and the character budget, separates narration, generates silence locally,
validates mono 24 kHz 16-bit PCM WAVs, and checkpoints each successful segment.
Intact current takes are reused. An API timeout can still incur a charge before a
response is lost; retries cannot guarantee exactly-once billing. The web queue marks
an uncertain provider outcome for explicit reconciliation instead of automatic retry.

Listen using the web audio panel or the WAV files. Regenerate only selected
segments with `render ... --regenerate scene_001_001`. Previous takes remain. Select
a retained take with `select-take --workspace ... --segment scene_001_001 --take TAKE_ID`.
Take IDs and paths are stored in `project.json` and the exported manifest.

Export never synthesizes missing audio. It writes:

- `exports/chapter_narration.wav` (optional MP3 with `--mp3`).
- `exports/approved_script.json` and `exports/cast.json`.
- `exports/timeline.json` with frame-derived scene/segment timestamps.
- `exports/render_manifest.json` with source/turn IDs, settings and selected take checksums.

Export follows scene order, not argument order. Fixed export filenames are replaced;
save a bundle outside the workspace before replacing a deliverable you need to keep.
MP3 conversion failure may leave valid WAV/JSON output. Export itself is not a
multi-file transaction. A separate admin review and atomic publication step snapshots
the exact export and preserves the previous published audio on replacement failure.
The bundle contains applied state/assets, not unapplied drafts.

## Publish reviewed audio locally

Readers submit chapter requests through `/request` and see their own requests at
`/requests`. At `/admin/requests`, an admin approves shared chapter work and attaches
an existing studio project. Use the linked studio to supply authorized source images
and complete the cast, source, script, render and export steps above.

Prepare the export for audition, listen to the immutable candidate, and record an
explicit audio review. Publish that reviewed export with the separate publication
button. Changes to the project, export or project link require a fresh review.
Replacement work and failed publication leave the previous published audio available.
Readers browse published chapters at `/browse`; Listen opens authenticated playback
with automatically refreshed links and byte-range seeking. Studio source images are
not delivered to readers.

Shared requests, decisions and publication pointers are local to the same host.
Preserve the complete configured data root, including `shared.sqlite3` and
`shared-artifacts`, when backing up or moving it. Hosted shared storage is S5 work;
frontend-only hosting keeps this local service disabled.

## Recovery and advanced edits

```powershell
uv run manga-tts restore --workspace results/restored --bundle results/reviewed-project.zip
uv run manga-tts export --workspace results/restored --scenes scene_001 scene_002
```

Restore stages and validates the bundle before publishing to an empty workspace.
Existing version-2 approvals and eligible takes are retained; version-1 projects
require reapproval and new current requests. Neither restore nor export needs an API
key when the necessary takes already exist.

`settings --file settings-command.json` accepts a `SettingsUpdate` object:
`{"settings":{"planning_model":"gemini-3.8-flash","tts_model":"gemini-3.8-flash-tts","max_chars":1200,"scene_pause":0.65,"segment_pause":0.12}}`.
It clears scene approvals. `narrate --file narration-command.json` accepts
`{"scene_id":"scene_001","position":0,"text":"A new morning.","evidence_source_ids":["page_001:p001_txt_01"]}`.
Review and approve narration against the referenced visual evidence.

## Validation and limits

Run `npm run test:python`. Tests use synthetic images/predictions
and valid synthetic PCM, exercising the real import/review/render/export/restore
code. They cover geometry, RTL fallback, stale drafts, approval rollback, three-speaker
segmentation, exclusions, silence, narration, targeted regeneration, corrupt takes,
interrupted rendering, archive traversal and CLI writer exclusion.

Set `MANGA_TTS_SAMPLE_PROJECT` to an unpacked supplied project to enable the optional
compatibility test. It works on temporary copies and asserts byte-identical WAV export,
cache reuse without a client, and bundle restore. Original sample files are untouched.

This implementation has not established live Magi OCR accuracy or Gemini acting
quality. It does not translate non-English manga, align words/bubbles to audio,
automatically reconcile extraction reruns, or provide multi-user/cloud job scheduling.
Those are separate extensions. The initial product remains upload/import, review,
approve, generate, audition and export.
