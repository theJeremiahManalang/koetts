# Validation record

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

## Reusable runner validation (2026-10-09)

Branch: `development`. Checked with the project's Python 3.11.9 virtual environment.

Passed:

- Eight tests, including both original tests and six new runner tests.
- Shared CLI integration with deterministic substitute models: correct model folders,
  metadata, overlays, and preservation of results across repeated invocations.
- CTD adapter tests: RGB-to-BGR conversion, block normalization, empty detections,
  mask writing, unsupported-task rejection before loading, missing-source messages,
  ONNX CPU selection even when CUDA is available, checkpoint fingerprint metadata,
  and rejection of explicit CUDA for upstream ONNX.
- Python compilation, CLI help, and `git diff --check`.
- `pip check` reports no broken requirements in the currently installed environment.
  This does not mean the new CTD requirements were successfully installed.
- Downloaded the upstream CTD source at
  `440b978563c71b758e31aaa315d100faba1efa2f` and the official
  `comictextdetector.pt.onnx` release asset into ignored local folders.

Blocked / not verified:

- CTD dependency installation failed twice because connections to
  `files.pythonhosted.org` were reset while downloading OpenCV, with the normal
  resolver and an alternate download route. The existing environment lacks OpenCV.
- Real CTD inference therefore remains unverified; finish installing
  `requirements-ctd.txt` when package downloads work and run the README command.
- MAGI loading/inference was not rerun in this change. Its prediction methods were
  preserved and exercised with a substitute model in the existing test.
- No accuracy comparison, GPU test, OCR benchmark, or verified reading-order result
  is claimed. The new tests validate integration, not neural-model quality.

The checked-in code does not include model weights or copied upstream implementation.
The source and weights downloaded here live under ignored `vendor/` and `weights/`.
