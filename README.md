# Learn MagiV3 by running it

## Character analysis web proof of concept

The `character-analysis-web` branch adds image upload, RTL/LTR reading direction,
editable dialogue, character appearance crops, persistent character IDs, selected
Windows voices, and downloadable WAV audio using the existing Magi wrapper.
See [web/README.md](web/README.md) to run it and
[CHARACTER_ANALYSIS_WALKTHROUGH.md](CHARACTER_ANALYSIS_WALKTHROUGH.md) for the
file/function walkthrough and connection to the supplied notebook.


This is a commented Python starter for `ragavsachdeva/magiv3`. It runs the three methods in the Hugging Face example, saves their results as JSON, and draws boxes on copies of your images. You do not need to train the model.

## 1. What the model does

MagiV3 is a vision-language model for comics. Give it a comic page or panel and choose a task:

- **Detection and association:** locate comic elements and predict relationships between them.
- **OCR:** read text and locate it in the image.
- **Character grounding:** supply a caption describing the image, and locate the characters referenced in that caption.

For example, grounding a caption such as “A girl with glasses talks to a boy wearing a hat” asks the model to locate those people. The caption is your input. This starter does not generate stories, translate dialogue, or provide a general chat interface.

The official model card describes its intended tasks: https://huggingface.co/ragavsachdeva/magiv3

## 2. How your original snippet works

`AutoModelForCausalLM.from_pretrained(...)` looks up the repository's configuration and loads its trained weights and custom class. Despite the generic loader name, this repository maps it to a Florence-2 conditional-generation model. You are using pretrained knowledge, not fitting a new model.

`torch_dtype=torch.float16` stores floating-point model values in half precision. It reduces GPU memory use. The wrapper chooses float32 on CPU because that is a more conservative CPU execution path.

`trust_remote_code=True` allows Python code from the model repository to execute locally. It is necessary for these custom methods. The starter pins a specific commit for both model and processor, so changes to the repository's main branch do not silently change what runs. Pinning makes the source reproducible; it is not a security audit.

`.cuda()` moves the model to an NVIDIA CUDA GPU. It fails without a usable CUDA device. This starter uses `.to(device)` and can select CPU automatically instead. CPU execution is expected to be much slower and has not been benchmarked here.

`.eval()` switches off training behavior such as dropout. It does not itself disable gradients; the wrapper also uses `torch.inference_mode()` to avoid tracking gradients during prediction.

`AutoProcessor` prepares pixels and text in the format the checkpoint learned. You pass a **list of RGB Pillow images**, not a filename string. For grounding, pass a **list of captions of the same length and in the same order**.

Conceptually, the processor converts the input into numbers, the model predicts output tokens from the image and task instruction, and postprocessing turns the output into usable text and regions. Learned relationships can be wrong: inspect overlays before building downstream decisions around predictions.

## 3. Requirements and compatibility

- Use a separate **Python 3.11** environment for these instructions.
- An NVIDIA GPU is the practical path. CPU is available as an unverified fallback.
- The checkpoint weights occupy roughly **1.67 GB** on the Hub. Actual RAM/VRAM use is higher; generation, temporary tensors, Python, and dependencies also consume memory. No minimum VRAM guarantee is made here.
- Allow several GB of disk space and internet access for installation and the first model load. Hugging Face caches downloads for reuse. The weights, processor, tokenizer, and upstream Python files download automatically; they are not bundled in this ZIP.
- The checkpoint configuration records Transformers **4.45.2**, so this starter pins that release. The other pins form a proposed compatible environment, not an end-to-end verified lockfile. Transitive dependencies are not fully locked. Avoid installing this into an unrelated existing environment.
- The supplied PyTorch 2.5.1/CUDA 12.4 option targets GPUs supported by that older build. Newer GPU generations may require a newer PyTorch/torchvision pair; check the official selector and validate model compatibility before changing versions.

References: [checkpoint configuration](https://huggingface.co/ragavsachdeva/magiv3/blob/49c73a225122d53adbaa26d53868be81a57706e2/config.json), [PyTorch installation commands](https://pytorch.org/get-started/previous-versions/).

## 4. Windows setup

Extract the ZIP. Open PowerShell **inside the extracted magiv3-starter folder**, where run.py and requirements.txt are located. Install Python 3.11 first if `py -3.11` is unavailable.

Create an isolated environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

Choose **one** PyTorch installation option.

NVIDIA GPU, with a compatible GPU and driver:

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
```

CPU only:

```powershell
.\.venv\Scripts\python.exe -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
```

Then install the remaining packages and check the environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import torch; print('PyTorch:', torch.__version__); print('CUDA available:', torch.cuda.is_available())"
```

Using the environment's Python directly avoids PowerShell activation-policy issues. There is no need to change your execution policy. No Hugging Face API key is normally needed for this public model.

On Linux, create the environment with `python3.11 -m venv .venv` and replace `.\.venv\Scripts\python.exe` in the commands with `.venv/bin/python`. The same CPU/CUDA wheel indexes apply to supported Linux systems. This project does not configure Apple MPS.

## 5. First run

Put a comic image at `images/page1.png`, then run detection and OCR together:

```powershell
.\.venv\Scripts\python.exe run.py --input images/page1.png --task all
```

`all` runs detection and OCR; it also runs grounding **when captions are supplied**. It does not invent captions. Model loading happens once per invocation; the first invocation downloads the model.

For OCR only:

```powershell
.\.venv\Scripts\python.exe run.py --input images/page1.png --task ocr
```

For detection only:

```powershell
.\.venv\Scripts\python.exe run.py --input images/page1.png --task detect
```

For grounding, edit `captions.example.json`: the key must be the exact image filename, and the value must accurately describe the visible characters. Do not include literal curly braces, because the upstream processor interprets them as formatting fields.

```powershell
.\.venv\Scripts\python.exe run.py --input images/page1.png --task ground --captions captions.example.json
```

To run all three:

```powershell
.\.venv\Scripts\python.exe run.py --input images/page1.png --task all --captions captions.example.json
```

To process a folder, one image at a time:

```powershell
.\.venv\Scripts\python.exe run.py --input images --task all --output results
```

When using captions with a folder, supply an entry for every image filename. Files are sorted by filename, not numeric page order; use page001, page002, etc. Subfolders are not traversed. PDFs and CBZ archives must be converted to image files separately. Animated or multipage image files use the first frame.

Add `--device cuda` to require GPU use and fail clearly if unavailable; add `--device cpu` to explicitly try CPU execution.

## 6. Reading your results

Each invocation creates a new timestamped folder under `results/`. Each image gets one JSON file plus a separate overlay PNG for each task. The JSON records model revision, input path, image dimensions, device, supplied caption, and predictions. Coordinates refer to the RGB image after EXIF rotation, as shown in the overlays.

Boxes use `[x_min, y_min, x_max, y_max]` pixel coordinates. The top-left is `(0, 0)`; x increases rightward and y downward. Coordinates can be fractional.

**Detection:** `panels`, `texts`, `characters`, and `tails` contain boxes. `character_cluster_labels` groups predicted character appearances within the image, not permanent identities across a book. `text_character_associations` contains zero-based `[text_index, character_index]` pairs; `text_tail_associations` links text to tails. `is_essential_text` is a predicted flag per detected text region.

**OCR:** `ocr_texts` and `bboxes` are parallel lists. Overlay label `OCR 0` corresponds to their first entries. These OCR boxes come from a separate prediction and must not be equated with detection text boxes by list index.

**Grounding:** `grounded_caption`, nested `bboxes`, and `indices_of_bboxes_in_caption` preserve the upstream output. A phrase can have multiple boxes. The index pairs mark spans in the returned caption, not character IDs. Overlay labels identify the corresponding phrase group.

The three result formats were checked against the [upstream implementation](https://huggingface.co/ragavsachdeva/magiv3/blob/49c73a225122d53adbaa26d53868be81a57706e2/modeling_florence2.py) and [processor](https://huggingface.co/ragavsachdeva/magiv3/blob/49c73a225122d53adbaa26d53868be81a57706e2/processing_florence2.py).

## 7. Files and suggested reading order

1. `example.py`: minimal use of the wrapper from your own Python code.
2. `config.py`: model ID and pinned revision.
3. `magi.py`: loading, precision, devices, and the three prediction calls, with comments explaining why.
4. `files.py`: input validation, RGB loading, JSON serialization, and drawing boxes.
5. `run.py`: command-line options and processing files with one loaded model.
6. `requirements.txt`: dependency versions, including imports required by upstream code.
7. `captions.example.json`: edit this to describe your image.
8. `tests/test_project.py`: lightweight checks that require Pillow but no model download.
9. `VALIDATION.md`: what was and was not tested during preparation.

To run the lightweight checks after installing dependencies:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 8. Troubleshooting

- **Python command not found:** install Python 3.11 and reopen your terminal. Use the exact environment Python paths above.
- **CUDA unavailable:** the machine may lack a supported NVIDIA GPU, a compatible driver, or the CUDA PyTorch build. Check the CUDA availability command. CPU mode is a fallback, not a speed equivalent.
- **GPU out of memory:** close other GPU applications and process a single page. The starter already uses one image per call. Cropping into panels may improve small-text readability but changes coordinates to the crop and loses page-wide relationships. Upstream resizes images, so shrinking the original file alone does not guarantee lower model memory use.
- **Import or generate errors:** verify you are using the new environment and the pinned Transformers version. Do not install FlashAttention; the starter chooses eager attention.
- **Slow startup:** the first load downloads roughly 1.67 GB of weights plus supporting files. Later loads use the Hugging Face cache, though loading into RAM/VRAM still takes time.
- **Connection/SSL failure:** check network/proxy configuration and certificate trust. Do not disable TLS verification.
- **Missing or incorrect text:** inspect the page quality, try panel crops, and review output manually. No accuracy guarantee is provided for a particular language, lettering style, or page layout. Dense pages can exceed the upstream helper's generation limit.
- **Empty results:** an empty list is a possible prediction. It does not prove that nothing exists in the image.
- **Grounding mismatch:** use a short factual caption describing visible characters; names alone may not provide useful visual clues.

## 9. Model use terms

The model card permits personal, research, noncommercial, and not-for-profit use, and directs other uses to the author for a licensing arrangement. Check the current model card before commercial deployment. This starter does not change the model's terms: https://huggingface.co/ragavsachdeva/magiv3#license-and-citation
