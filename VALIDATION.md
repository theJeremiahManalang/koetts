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
