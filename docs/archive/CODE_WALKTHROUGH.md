> Historical walkthrough of the original OCR proof of concept. For the current studio workflow, see [AUDIO_WORKFLOW.md](../../resources/AUDIO_WORKFLOW.md).

# Manga text: file guide and request walkthrough

This guide describes the original OCR proof of concept, not the current studio. Start with the numbered flow,
then use the file guide to find the code you want to change.

## 1. The complete path

```text
Browser: web/app/page.tsx
  Choose image -> store File in React state -> show local preview
  Click MAGI -> extract() -> POST /api/extract
    |
Next.js server: web/app/api/extract/route.ts
  POST() -> validate request -> save temporary image -> launch Python
    |
Python process: web_extract.py
  extract_text(path) -> decode image -> create_runner("magi")
    |
runners.py
  create_runner() -> Magi(device="auto")
    |
magi.py + config.py
  Load processor and model -> predict(..., "ocr") -> predict_ocr(...)
    |
web_extract.py
  Keep ocr_texts -> print {"texts": [...]}
    |
Next.js API
  Parse Python output -> return {"texts": [...]} -> clean up temporary file
    |
Browser: web/app/page.tsx
  setTexts(result.texts) -> format {"output": [...]} -> display -> Copy JSON
```

There are three execution locations: the browser, the Node.js server running
Next.js, and a Python child process started by that server. During local
development, all three run on your computer. The browser does not run Python.

## 2. Step by step: from opening the page to copying the result

### Step 1: Start the web server

Run these commands from the project root:

```powershell
cd web
npm run dev
```

`web/package.json` maps `dev` to `next dev --hostname 127.0.0.1`.
Open `http://127.0.0.1:3000`.

Next.js uses its folder conventions to connect the files:

- `app/layout.tsx` supplies the outer HTML document and loads `globals.css`.
- `app/page.tsx` supplies the home page at `/`.
- `app/api/extract/route.ts` handles requests to `/api/extract`.

There is no handwritten routing file connecting these paths. Next.js discovers
them from their names and locations.

### Step 2: Select an image in the browser

**File:** `web/app/page.tsx` — the file input's `onChange` handler.

```tsx
const selected = event.target.files?.[0] ?? null;
setFile(selected);
```

The browser provides a `File` object containing the selected file's name, type,
size, and access to its bytes. The handler first clears previous results and
messages. It rejects files over `10 * 1024 * 1024` bytes and MIME types other than
PNG, JPEG, or WebP, then stores the selection in React state.

**At this point, the image has not been sent to the server and the model has not
run.** The original file on your computer is unchanged.

### Step 3: Show a local preview

**File:** `web/app/page.tsx` — `useEffect(..., [file])`.

```tsx
const url = URL.createObjectURL(file);
setPreview(url);
return () => URL.revokeObjectURL(url);
```

React runs this effect when the selected file changes. The browser creates a
temporary `blob:` URL, and `<img src={preview}>` displays it. This is a local
browser reference, not a server upload URL. The cleanup releases that reference
when the selection changes or the component is removed.

### Step 4: Click the MAGI button

**File:** `web/app/page.tsx` — `onClick={extract}` calls `extract()`.

The button is disabled when no valid file is selected or extraction is already
running. `extract()` checks those conditions again, sets `busy` to `true`, clears
old output, and creates the request:

```tsx
const body = new FormData();
body.append("image", file);
body.append("model", "magi");
const response = await fetch("/api/extract", { method: "POST", body });
```

`FormData` packages two fields: `image` contains the image bytes and `model`
contains the string `magi`. The browser supplies the multipart request format.
The relative URL sends this to the same server serving the web page.

The model choice is currently fixed to MAGI by this button. There is no separate
model-selection screen or automatic extraction on upload.

### Step 5: The API receives and validates the request

**File:** `web/app/api/extract/route.ts` — `POST(request)`.

```ts
const data = await request.formData();
const file = data.get("image");
```

The API does the following before starting Python:

1. Returns HTTP `429` if its current server process is already handling an extraction.
2. Returns HTTP `413` if the declared request size exceeds 11 MiB. This allows
   room for form data around the 10 MiB image limit.
3. Sets the process's busy flag.
4. Parses the submitted form.
5. Requires `model` to equal `magi`.
6. Requires a nonempty `File`, an allowed MIME type, and at most 10 MiB of image data.

Invalid model or image fields return HTTP `400`. Browser validation is repeated
on the server because requests can also be sent without using the page.

The busy flag is stored on `globalThis`. It protects this Node.js process; it is
not a shared queue across multiple server instances. The Content-Length check is
an early check of the declared length, not a streaming upload limiter.

### Step 6: Save the image temporarily on the server

**File:** `web/app/api/extract/route.ts` — `mkdtemp()` and `writeFile()`.

```ts
directory = await mkdtemp(path.join(tmpdir(), "manga-ocr-"));
const input = path.join(directory, "panel");
await writeFile(input, Buffer.from(await file.arrayBuffer()));
```

The uploaded image goes into the operating system's temporary directory on the
machine running Next.js. An illustrative Windows path is:

```text
<OS temporary directory>\manga-ocr-ABC123\panel
```

The suffix is generated for each request. `panel` is a file with no extension;
Python identifies its actual image format from its contents. The uploaded
filename is not used to construct the server path.

This web flow does not save the upload under `images/`, `web/public/`, or
`results/`. It does not insert it into a database.

### Step 7: Next.js launches the Python bridge

**File:** `web/app/api/extract/route.ts` — `execute(...)`.

The server calculates the repository root as the parent of its working directory.
This is why the documented commands run Next.js from `web/`.

It chooses Python in this order:

1. `PYTHON_EXECUTABLE`, if configured in the server environment.
2. The repository's `.venv/Scripts/python.exe` on Windows, or `.venv/bin/python` elsewhere.
3. `python` from the system's executable search path.

It then runs the equivalent of:

```text
<python executable> <repository root>/web_extract.py <temporary image path>
```

`execute` is `execFile` wrapped by `promisify`, so the route can `await` the child
process. Arguments are passed as an array, not assembled into a shell command.
The settings allow 15 minutes, limit captured output to 4 MiB, set UTF-8 Python
output, and hide the child window on Windows.

The web API calls `web_extract.py` directly. It does **not** call `run.py`.

### Step 8: Python opens and prepares the image

**File:** `web_extract.py` — the main block and `extract_text(path)`.

`sys.argv[1]` contains the temporary image path passed by Node.js.

```python
with Image.open(path) as source:
    # Format and pixel-count validation happens here.
    image = ImageOps.exif_transpose(source).convert("RGB")
```

Pillow decodes the actual image, checks that its format is PNG, JPEG, or WebP,
and rejects images above 25 million pixels. EXIF rotation is applied, then the
image becomes RGB pixel data. This is the object passed to the model.

### Step 9: Choose and load MAGI

**Files:** `web_extract.py` → `runners.py` → `magi.py` → `config.py`.

```python
runner = create_runner("magi")
```

`runners.create_runner()` recognizes `magi`, imports `Magi`, and returns
`Magi(device="auto")`. This calls `Magi.__init__()`.

The constructor:

- Imports PyTorch and the Transformers loading classes.
- Selects CUDA if PyTorch reports it available; otherwise selects CPU.
- Uses float16 on CUDA and float32 on CPU.
- Reads `MODEL_ID` and `MODEL_REVISION` from `config.py`.
- Loads the processor and pretrained model for `ragavsachdeva/magiv3` at the
  pinned revision.
- Moves the model to the selected device and enables evaluation mode.

Model assets can download from Hugging Face and be reused from its local cache.
The application's image inference happens in the local Python process; this
code does not send the panel to a hosted inference API.

Each web extraction starts a fresh Python process and reloads the model into
memory. Cached files avoid downloading the entire model again, but do not keep
the loaded model alive between requests.

### Step 10: Run text recognition

**File:** `web_extract.py`, calling `magi.py` — `Magi.predict()`.

```python
prediction = runner.predict([image], "ocr")["ocr"][0]
```

`[image]` is a one-image batch. The task string `ocr` means text recognition.
Inside `Magi.predict()`, the matching branch executes:

```python
result["ocr"] = self.model.predict_ocr(images, self.processor)
```

`predict_ocr()` belongs to the downloaded model implementation. Our `magi.py`
wrapper invokes it; it does not implement the neural network itself. Inference
runs under `torch.inference_mode()`, without training the model.

The wrapper returns a dictionary containing the OCR batch. `['ocr'][0]` selects
the first image's prediction. That prediction contains `ocr_texts` and may also
contain coordinates; the web bridge only takes `ocr_texts`.

### Step 11: Python returns just the text through stdout

**File:** `web_extract.py` — end of `extract_text()` and the main block.

```python
texts = prediction["ocr_texts"]
return {"texts": [text for text in texts if text.strip()]}
```

The bridge checks that this is a list of strings and removes empty or
whitespace-only entries. It preserves the content and order of retained strings;
it does not translate, summarize, trim each retained string, or reorder dialogue.

The main block serializes the dictionary:

```python
print(json.dumps(result, ensure_ascii=False))
```

This writes JSON to the child process's **stdout**, which Node.js captures. It
does not create a JSON file. `ensure_ascii=False` preserves readable Unicode.
During extraction, ordinary Python print output is redirected to **stderr** so
model-loading messages do not become part of the JSON protocol.

Example Python stdout:

```json
{"texts": ["Hello!", "Where are we?"]}
```

### Step 12: The server responds and cleans up

**File:** `web/app/api/extract/route.ts` — after `await execute(...)`.

```ts
const result = JSON.parse(stdout);
return Response.json({ texts: result.texts });
```

Between those statements, the route checks that `result.texts` is an array of
strings. A successful response has HTTP `200` and this shape:

```json
{"texts": ["Hello!", "Where are we?"]}
```

The `finally` block attempts to remove the temporary directory and its image
whether processing succeeds or fails, then resets the busy flag. The user's
original image is not deleted. A process crash can prevent normal cleanup.

### Step 13: Display the copyable JSON in the browser

**File:** `web/app/page.tsx` — continuation of `extract()` and rendering.

```tsx
const result = await response.json();
setTexts(result.texts);
```

Updating React state causes the component to render again. It formats the result:

```tsx
const outputJson = texts === null ? "" : JSON.stringify({ output: texts }, null, 2);
```

The `<pre><code>` elements display:

```json
{
  "output": [
    "Hello!",
    "Where are we?"
  ]
}
```

**The internal API key is `texts`; the displayed and copied key is `output`.**
This conversion happens entirely in `page.tsx`. `JSON.stringify` adds indentation
and correctly escapes quotation marks, newlines, and other special characters.
Valid JSON has no trailing comma or final semicolon.

`texts === null` means no result is available yet. `texts === []` means extraction
completed with no retained text: the UI shows a message and `{"output": []}`.
The `finally` block in `extract()` sets `busy` back to `false`.

### Step 14: Copy JSON

**File:** `web/app/page.tsx` — `copyOutput()`.

```tsx
await navigator.clipboard.writeText(outputJson);
```

This copies the same formatted JSON displayed on screen to the clipboard. No
server request or model execution occurs. If clipboard access fails, the UI asks
the user to select and copy the displayed JSON manually.

## 3. What each project file does

Paths below are relative to the repository root. Dependency packages, downloaded
model source, and generated build files are described by folder rather than
listing every third-party file.

### Web application files

- **`web/app/page.tsx`**: Interactive page. Owns file selection, preview, loading
  state, request submission, errors, JSON formatting, and clipboard copying.
  `"use client"` enables client-side React hooks and browser APIs. State names:
  `file` is the selection, `preview` is its local URL, `busy` tracks extraction,
  `error` stores failure messages, `texts` stores the returned strings, and
  `copyStatus` stores clipboard feedback.
- **`web/app/api/extract/route.ts`**: Server endpoint. Receives the upload,
  validates it, creates the temporary file, runs Python, validates the returned
  JSON, responds, and cleans up. `runtime = "nodejs"` allows filesystem and
  child-process operations.
- **`web/app/layout.tsx`**: Shared HTML/body wrapper, page title and description,
  and global stylesheet import. Its `children` slot contains the page.
- **`web/app/globals.css`**: Imports Tailwind and defines base colors, font,
  outline spacing, and button cursor behavior. It does not process images.
- **`web/postcss.config.mjs`**: Enables the Tailwind PostCSS plugin for CSS builds.
- **`web/package.json`**: Lists JavaScript dependencies and commands: `dev` starts
  development mode, `build` compiles production output, `start` serves that output,
  and `typecheck` checks TypeScript without generating JavaScript.
- **`web/package-lock.json`**: Records the exact resolved npm dependency versions.
- **`web/tsconfig.json`**: TypeScript compiler settings, including strict checking,
  React JSX support, Next.js integration, and included source/type files.
- **`web/next-env.d.ts`**: Next.js type declarations used by TypeScript. Normally
  managed by Next.js rather than edited for application features.
- **`web/README.md`**: Web setup instructions, runtime limits, and validation notes.

### Python files used by the web request

- **`web_extract.py`**: Small command-line bridge between Node.js and the model.
  Accepts one image path and writes one JSON result to stdout.
- **`runners.py`**: Shared model factory. `create_runner()` constructs the selected
  adapter with lazy imports. `validate_options()` validates CLI model/task/caption
  combinations; the web bridge does not call that validation function.
- **`magi.py`**: Loads MAGI and dispatches detection, OCR, or grounding tasks.
  The web uses only its OCR branch.
- **`config.py`**: Shared MAGI model ID and pinned revision used during loading.
- **`requirements.txt`**: Python dependencies for MAGI and image handling. These
  are installed during setup, not reinstalled for each request.

### Other Python entry points and helpers

- **`run.py`**: Separate terminal application. `main()` parses command arguments,
  validates options, selects a runner, processes image files, and writes JSON and
  annotated images into timestamped model-specific result folders. It loads the
  runner once for that CLI invocation. It is not in the web request path.
- **`files.py`**: Helpers used by the CLI and example. `image_paths()` discovers
  input files, `load_image()` applies rotation and RGB conversion,
  `read_captions()` validates caption mappings, `json_default()` converts array or
  tensor values, `write_json()` saves JSON, and `save_overlay()` draws predicted
  regions on copies of images. The web bridge does its own image loading and does
  not call these helpers.
- **`example.py`**: Standalone Python usage example. Loads the sample image,
  supplies a caption, runs MAGI tasks, and writes `example-results.json`.
- **`captions.example.json`**: Example filename-to-caption mapping for CLI
  grounding. It is not an OCR result or a web upload configuration.

### Tests, documentation, and sample data

- **`tests/test_web_extract.py`**: Tests the bridge's text-only output, empty
  prediction behavior, and rejection of invalid images before model loading.
  Model calls are mocked, so these tests do not download or run real weights.
- **`tests/test_runners.py`**: Tests MAGI option validation, metadata, overlays, and preservation of repeated CLI runs.
- **`tests/test_project.py`**: Tests shared image/caption/output helpers and MAGI
  dispatch/validation without real model weights.
- **`README.md`**: Overall setup, model usage, CLI examples, and a link to web setup.
- **`VALIDATION.md`**: Records prior verification and its limits.
- **`TEXT_EXTRACTION_RESEARCH.md`**: Background research about OCR and reading order;
  it is not executable application code.
- **`images/README.md`**: Instructions for supplying sample images.
- **`images/page1.jpg`**: Sample image used for local checks and the Python example.
  Web uploads do not automatically replace it.
- **`.gitignore`**: Keeps environments, dependencies, caches, downloaded weights,
  results, and local web environment files out of normal Git tracking.
- **`CODE_WALKTHROUGH.md`**: This guide; it has no runtime role.

### Generated or local folders

- **`.venv/`**: Python interpreter and installed Python packages.
- **`web/node_modules/`**: Installed Next.js, React, Tailwind, and other npm packages.
- **`web/.next/`**: Generated Next.js development/build output.
- **`web/*.tsbuildinfo`**: TypeScript incremental-check cache, when generated.
- **`__pycache__/`**: Python bytecode cache.
- **`results/`**: CLI outputs. The web path does not write results here.
- **`web/.env.local`**, if created: Local server settings such as
  `PYTHON_EXECUTABLE`. The Python path is a server setting, not a browser setting.
- **Hugging Face cache**: Stores downloaded MAGI assets; its location depends on
  the Python environment's cache configuration.
- **OS temporary directory**: Holds the web request's image until cleanup.

## 4. Where to look when something goes wrong

- **Image does not become selectable:** `page.tsx`, file input validation.
- **Button stays disabled:** `page.tsx`, `file` and `busy` state.
- **HTTP 400:** `route.ts`, submitted model/image validation.
- **HTTP 413:** `route.ts`, declared request-size check.
- **HTTP 429:** `route.ts`, another request holds the process's busy flag.
- **HTTP 500:** Check the server terminal's `OCR failed:` message. Possible causes
  include image decoding, missing Python packages, model loading, inference,
  timeout, or malformed Python output. The browser gets a general error message.
- **Wrong or missing recognized text:** The OCR prediction comes from
  `magi.py` calling the upstream `predict_ocr()` method. The UI only formats it.
- **Unexpected displayed JSON key:** `page.tsx` creates the `output` key; the
  API and bridge use `texts` internally.
- **Copy fails:** `page.tsx`, `copyOutput()` and browser clipboard access.

## 5. Which file to edit for common changes

- Change the page appearance or displayed JSON: `web/app/page.tsx` and
  `web/app/globals.css`.
- Change upload limits: browser validation in `page.tsx`, server validation in
  `route.ts`, and pixel-count validation in `web_extract.py` as appropriate.
- Change the API response field: update both `route.ts` and the `result.texts`
  reader in `page.tsx`. If the Python protocol also changes, update
  `web_extract.py` and the route's Python-result validation together.
- Add another OCR model: add a runner, then extend the bridge, API allowlist,
  and UI model selection. Adding a button alone does not add model support.
- Keep models loaded between requests: replace the fresh-process-per-request
  arrangement with a persistent inference service or worker.
- Save extraction history: add explicit storage; the current flow keeps results
  in browser state and deletes the temporary uploaded image after processing.
