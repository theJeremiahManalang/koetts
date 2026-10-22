# Vision model setup

`packages/vision` owns model identity, image loading, lazy inference, and artifact generation. The reviewed checkpoint and existing model dependency versions are preserved. See [developer setup](development.md) for the lightweight environment.

## Select an accelerator

```bash
uv sync --frozen --extra vision-cpu
# Alternative on a compatible Linux/Windows CUDA 12.4 host:
uv sync --frozen --extra vision-cuda
```

CPU and CUDA extras are mutually exclusive. Their explicit indexes prevent an accidental accelerator choice. The Python 3.11 lock includes both dependency graphs; normal development does not install either. CUDA requires compatible hardware/drivers and is unavailable on macOS. Dependency resolution does not establish hardware performance or inference quality.

The adapter pins model and processor to the same reviewed revision and uses `trust_remote_code=True`. First inference downloads weights and upstream code to the Hugging Face cache. Preserve model caches and inspect the current [model card and usage terms](https://huggingface.co/ragavsachdeva/magiv3) before deployment.

## Inference

```bash
uv run manga-vision --help
uv run --extra vision-cpu manga-vision --input images/page1.jpg --task all
uv run --extra vision-cpu manga-vision --input images/page1.jpg --task ocr
```

When running inference through uv, include the chosen extra so synchronization retains it. Alternatively use the installed `.venv/bin/manga-vision` directly after syncing the extra.

Grounding requires `--captions /path/to/captions.json`: a JSON object mapping exact image filenames to factual captions. Supply one caption for every input image. Literal braces are rejected because upstream prompt formatting interprets them. `all` performs detection/OCR and includes grounding only when captions are supplied.

Folder input is nonrecursive, sorted by filename; use zero-padded names. EXIF orientation is applied before inference. PDF and CBZ input must be exported to images. Task overlays and JSON metadata go to a separate `results/magi/<UTC timestamp>` directory per invocation; `--output` changes the root.

Predictions are evidence, not human decisions. Review OCR, reading order, and identities before approved production. Synthetic tests verify plumbing without weights; live model accuracy and provider voice quality require separate authorized checks.

For import failures, restore the locked environment. For CUDA failures, check driver and hardware compatibility. For memory failures, process one image at a time; cropping changes coordinates and removes page-wide relationships. Retain TLS verification when troubleshooting downloads.
