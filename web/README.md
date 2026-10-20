# Manga Reader audio workspace

The UI is adapted from `character-analysis-web`: same paper/ink/sage palette,
header, image viewer, zoom controls, split reader layout and character crops.
The earlier Windows speech prototype has been replaced with the reviewed
`manga_tts` workflow on `dev-test-1`.

## Start locally

1. Install the Python dependencies described in `../docs/AUDIO_WORKFLOW.md`.
2. Select a Python 3.11+ environment with the audio dependencies installed. From
   this directory run `npm ci`, then start Next with that interpreter explicitly:

   ```bash
   PYTHON_EXECUTABLE=/absolute/path/to/environment/bin/python npm run dev
   ```
3. Open http://127.0.0.1:3000. For a production build, run `npm run build` and
   `npm start` instead.

For production startup, use the same explicit interpreter with `npm start`.
`PYTHON_EXECUTABLE` takes precedence over the repository's `.venv` Python and the
final `python` fallback. A host with only `python3` must select a compatible
interpreter explicitly; installing Node dependencies does not install Python
dependencies. Both the workflow worker and legacy extraction route use this
selection order.
Set `GEMINI_API_KEY` in the server environment before starting Next.js for new
planning or audio. Keys are never entered in the browser or sent to it. MagiV3
extraction needs its model dependencies and weights; first loading may download
the pinned model. Restoring/reviewing existing output requires neither Magi nor
new provider calls.

## Workflow

- **Upload:** choose ordered images, a chapter-analysis ZIP, or a saved project ZIP.
  Image sequence can be rearranged before extraction. Optional cast ZIP imports
  named references. Uploads are limited to 128 MB total; images to 10 files/10 MB each.
- **Cast:** create a character directly from a detected panel crop (choose a name
  and voice; no ZIP or API key needed), or import references. Creation saves and
  assigns the selected appearance immediately; save pending edits first. Use the
  new character in other appearance dropdowns, reject false detections, edit
  Gemini voices/pronunciation/acting, and explicitly approve the cast.
- **AI proposal:** generate a proposal, inspect/edit its JSON, and explicitly load
  it. Loading clears approvals. Existing saved proposals are accessible without a key.
- **Source & order:** correct text, include/exclude sources, move them, assign
  scenes and groups. Show/highlight sources against page evidence. Applying rebuilds
  dialogue turns, so finish this before final script edits.
- **Script approval:** edit exact wording/delivery, insert narration linked to
  evidence, set intentional silence, and approve each scene independently.
- **Audio & export:** select approved scenes, inspect requests, render/reuse takes,
  audition them, choose a take or regenerate one segment, export compiled MP3/WAV,
  and download manifests/timeline/script or a resumable project ZIP.

Use **Select all** or individual scene checkboxes to choose the compilation. After
rendering the selected scenes, **Compile selected scenes to MP3** combines their
chosen takes in chapter order into one file. **Download compiled MP3** saves it.
The audio dependencies include an MP3 encoder; a system FFmpeg is also supported.

Changes remain local to the form until Apply. Leaving a dirty section asks before
discarding edits. Server mutations compare the project fingerprint, rejecting stale
edits from other tabs. Failed operations preserve drafts; Reload saved state recovers
completed segments after an interrupted render. Export files are explicitly labeled
as the last export, which may predate later edits.

## Storage and execution

Projects live in `results/web/projects/<id>/`; jobs, staged uploads and downloads
live in sibling directories. Browser storage contains only the active project/job
IDs and pending idempotency intents with request fingerprints for enqueue recovery;
it does not store scripts or credentials. It keeps multiple pending keys until their
operations are found, so a different request cannot overwrite a key after a lost
enqueue response. Saved-project selection works after refresh.
Successful uploads are removed after import; uploads for interrupted work remain
until the operation finishes.

Next routes persist operations in `results/web/operations.sqlite3` before returning
IDs. SQLite coordinates one MAGI slot and one pipeline slot across local processes;
only one operation may own a project at a time. The browser polls persisted progress
and reconnects after refresh. Duplicate submission with the same key and same request
returns the same operation; a changed request with that key conflicts. Existing JSON
job files remain readable for legacy polling. Upload bytes and existing project
visual evidence are fingerprinted at enqueue and rechecked before worker execution.

Workers use the same workspace lock as the CLI and checkpoint audio per segment.
They heartbeat every 15 seconds under a 60-second lease, with a 30-minute attempt
limit. The operation store owns at most three attempts; a durable worker makes one
provider request per attempt. Expired leases trigger local process identity checks;
expiration alone does not release capacity. If a provider result is uncertain, the
slot remains reserved until an operator resolves it. Use the operation ID shown in
the error with the configured Python interpreter:

```bash
"$PYTHON_EXECUTABLE" web_workflow.py reconcile <operation-id> fail
"$PYTHON_EXECUTABLE" web_workflow.py reconcile <operation-id> retry
```

Retry may repeat provider billing and counts toward the three-attempt ceiling. The
command verifies the recorded process where possible. If the process identity cannot
be read, first confirm it stopped, then add `--worker-stopped`. The
SQLite database must remain on local storage and cannot coordinate multiple hosts.
This is a **local-only application**, bound to loopback with origin checks. It has no
user authentication, hosted queue, or multi-user isolation. Do not expose it to a
network or deploy these routes as serverless functions.

## Checks

`npm test`, `npm run typecheck`, and `npm run build` validate the frontend. From
the repository root, run
`/absolute/path/to/environment/bin/python -m unittest discover -s tests -v`
to check backend and worker contracts.
The web-worker tests cover stale edits, sanitized validation failures, restore,
inspection, rendering with an injected renderer, export, bundle creation, durable
enqueue, stage claims, leases and fences. A process test kills a real operation worker
after its first segment is saved, explicitly resolves the uncertain attempt, and
verifies restart reuse without regenerating that segment. It uses temporary projects
and synthetic audio.
Live visual/browser checks and provider quality evaluation remain separate checks.

For a disposable production HTTP check, first install `web/node_modules`, then
run from the repository root:

```bash
/absolute/path/to/environment/bin/python tests/verify_local_http.py
```

This copies runtime source and Node dependencies into a temporary directory,
builds and starts the studio with an explicit interpreter, runs the HTTP test,
checks the existing reader routes, and separately builds/starts frontend-only
mode to check its redirect and processing guards. It clears the Gemini key for
its children, stops the servers, and removes the temporary runtime. Repository
results and supplied samples remain untouched. Allow approximately 400 MB for the
dependency copy, plus build output. Network access is not required after dependencies
are installed; loopback binding and child processes must be permitted.

The runner's `--dev` option verifies development transport separately; adding
`--webpack` selects an explicit diagnostic fallback. Neither establishes a passing
production build. If a restricted build fails on internal port binding, repeat
with the required process permissions and a fresh build cache before changing
runtime configuration. See `../docs/alignment-status.md` for exact S0 evidence.

For the optional HTTP integration check, start the production server and set
`MANGA_WEB_TEST_URL=http://127.0.0.1:3001` (adjust the port). Run
`python -m unittest discover -s tests -p test_web_http.py -v` from the repository
root. It creates a labeled `web_integration_test` project with synthetic audio,
and exercises upload, jobs, export, byte-range playback and downloads without
browser automation or Gemini calls.

## Source layout and checks

`app/` contains the studio page and API routes, `components/` contains the review
workspaces and loading UI, `lib/` contains shared logic, and `tests/` contains
the frontend regression tests. Run `npm test`, `npm run typecheck`, and
`npm run build` from this directory.

The catalog at `/browse`, manga details at `/manga/[id]`, reader at
`/read/[mangaId]/[chapterId]`, and request form at `/request` use the sample catalog
in `app/data/manga.ts`. The audio studio remains at `/`.
