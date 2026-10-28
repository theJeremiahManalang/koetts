"""Image loading and output helpers. No model download happens in this file."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def image_paths(source):
    source = Path(source)
    if source.is_dir():
        paths = sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS)
    elif source.is_file() and source.suffix.lower() in EXTENSIONS:
        paths = [source]
    else:
        raise ValueError(f"Not an image file or directory: {source}")
    if not paths:
        raise ValueError(f"No supported images in {source}")
    return paths


def load_image(path):
    # Materialize RGB pixels before closing the file. Fix EXIF rotation so
    # coordinates and the saved overlays use the same visible orientation.
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def read_captions(path, paths):
    mapping = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(mapping, dict):
        raise ValueError("Caption JSON must map image filenames to strings")
    captions = []
    for image_path in paths:
        value = mapping.get(image_path.name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing nonempty caption for {image_path.name}")
        if "{" in value or "}" in value:
            raise ValueError("Remove literal braces from captions; the upstream processor uses str.format")
        captions.append(value)
    return captions


def json_default(value):
    # Accommodate tensors/NumPy arrays without changing ordinary Python data.
    if hasattr(value, "detach"):
        return value.detach().cpu().tolist()
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False, default=json_default), encoding="utf-8")


def save_overlay(image, prediction, task, path):
    # Draw on a copy: never alter the user's input image.
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    regions = []
    if task == "detections":
        for category, color in [("panels", "lime"), ("texts", "blue"), ("characters", "red"), ("tails", "orange")]:
            regions.extend((box, f"{category} {i}", color) for i, box in enumerate(prediction.get(category, [])))
    elif task == "ocr":
        # Numeric labels point to ocr_texts in JSON; this also avoids relying on
        # a locally installed font for Japanese or other non-Latin characters.
        regions.extend((box, f"OCR {i}", "blue") for i, box in enumerate(prediction.get("bboxes", [])))
    elif task == "grounding":
        for i, boxes in enumerate(prediction.get("bboxes", [])):
            regions.extend((box, f"phrase {i}", "red") for box in boxes)
    for box, label, color in regions:
        x1, y1, x2, y2 = map(float, box)
        if x2 < x1 or y2 < y1:
            continue  # A malformed prediction should not stop other overlays.
        draw.rectangle((x1, y1, x2, y2), outline=color, width=3)
        draw.text((x1, max(0, y1 - 12)), label, fill=color, stroke_width=1, stroke_fill="white")
    canvas.save(path)
