"""MagiV3 images -> portable chapter bundle. Never plans, approves or synthesizes."""
from __future__ import annotations

import hashlib
import json
import math
import tempfile
import zipfile
from pathlib import Path

from .storage import iou, write_json


def boxes(values, width, height):
    result = []
    for value in values:
        if len(value) != 4 or not all(math.isfinite(float(v)) for v in value):
            raise ValueError("Invalid model bounding box")
        x1, y1, x2, y2 = map(float, value)
        box = [max(0., x1), max(0., y1), min(float(width), x2), min(float(height), y2)]
        if box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError("Empty or out-of-image model bounding box")
        result.append(box)
    return result


def layout_order(regions, direction="rtl"):
    """Whitespace-cut layout proposal, preserving vendor order for overlapping layouts.

    Horizontal gutters take precedence; vertical columns traverse right-to-left.
    This is an optional heuristic, never a claim of authoritative reading order.
    """
    def visit(indices):
        if len(indices) < 2:
            return indices
        for axis in (1, 0):
            ordered = sorted(indices, key=lambda i: regions[i][axis])
            end = regions[ordered[0]][axis + 2]
            for at in range(1, len(ordered)):
                if regions[ordered[at]][axis] > end:
                    first, second = ordered[:at], ordered[at:]
                    if axis == 0 and direction == "rtl":
                        first, second = second, first
                    return visit(first) + visit(second)
                end = max(end, regions[ordered[at]][axis + 2])
        return indices
    return visit(list(range(len(regions))))


def _intersection(a, b):
    return max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))


def _panel(box, panels):
    scores = [_intersection(box, p["bbox"]) for p in panels]
    return panels[max(range(len(scores)), key=scores.__getitem__)]["panel_id"] if scores and max(scores) > 0 else None


def reconcile_texts(detections, ocr):
    """Associate by geometry, retaining unmatched OCR and diagnostics for manual review.

    OCR indices are never equated with detection indices. Multiple lines can belong
    to one bubble. Ambiguous matches are retained separately rather than guessed.
    """
    assigned = {i: [] for i in range(len(detections))}
    unmatched, diagnostics = [], []
    for oi, (text, box) in enumerate(ocr):
        area = (box[2]-box[0]) * (box[3]-box[1])
        candidates = [(max(iou(box, target), _intersection(box, target)/area), di)
                      for di, target in enumerate(detections)]
        candidates = sorted((score, di) for score, di in candidates if score >= .5)[::-1]
        if candidates and (len(candidates) == 1 or candidates[0][0]-candidates[1][0] >= .15):
            assigned[candidates[0][1]].append(oi)
        else:
            unmatched.append(oi)
            diagnostics.append({"code": "ambiguous_ocr" if candidates else "unmatched_ocr", "ocr_index": oi})
    for di, indices in assigned.items():
        if not indices:
            diagnostics.append({"code": "missing_ocr", "detection_index": di})
    return assigned, unmatched, diagnostics


def extract_chapter(images, destination, *, chapter_id="chapter_001", runner=None,
                    device="auto", order="model", progress=None):
    """Extract ordered image paths to a new ZIP; originals and raw predictions included.

    Model order is the default Magi RTL proposal. Optional rtl/ltr whitespace order
    is a fallback. Stable import IDs refer to this extraction, not future reruns.
    An injectable runner permits offline integration testing without model weights.
    """
    from config import MODEL_ID, MODEL_REVISION
    from files import json_default, load_image, save_overlay
    paths = [Path(p) for p in images]
    destination = Path(destination)
    if not paths or any(not p.is_file() for p in paths):
        raise ValueError("Supply existing image files in chapter order")
    if len({p.resolve() for p in paths}) != len(paths):
        raise ValueError("Duplicate input image")
    if order not in {"model", "rtl", "ltr"}:
        raise ValueError("Unknown reading order")
    if destination.exists():
        raise FileExistsError("Chapter destination already exists")
    if not chapter_id.strip():
        raise ValueError("Chapter ID cannot be empty")
    if runner is None:
        from magi import Magi
        runner = Magi(device)
    chapter = {"schema_version": "1.0.0", "chapter_id": chapter_id,
               "metadata": {"model_id": MODEL_ID, "model_revision": MODEL_REVISION,
                            "reading_direction": "ltr" if order == "ltr" else "rtl",
                            "order_method": order, "page_count": len(paths), "review_required": True}, "pages": []}
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for number, path in enumerate(paths, 1):
            if progress:
                progress(f"Extracting image {number}/{len(paths)}")
            image = load_image(path)
            raw = json.loads(json.dumps({k: v[0] for k, v in runner.predict([image], "all").items()}, default=json_default))
            det, ocr = raw.get("detections", {}), raw.get("ocr", {})
            width, height = image.size
            panel_boxes = boxes(det.get("panels", []), width, height)
            char_boxes = boxes(det.get("characters", []), width, height)
            text_boxes = boxes(det.get("texts", []), width, height)
            ocr_boxes = boxes(ocr.get("bboxes", []), width, height)
            words = ocr.get("ocr_texts", [])
            if len(words) != len(ocr_boxes) or any(not isinstance(w, str) for w in words):
                raise ValueError("OCR text and geometry are inconsistent")
            prefix, page_id = f"p{number:03d}", f"page_{number:03d}"
            panel_order = list(range(len(panel_boxes))) if order == "model" else layout_order(panel_boxes, order)
            panels = [{"panel_id": f"{prefix}_pan_{i+1:02d}", "bbox": box,
                       "reading_order": panel_order.index(i)+1} for i, box in enumerate(panel_boxes)]
            assigned, unmatched, diagnostics = reconcile_texts(text_boxes, list(zip(words, ocr_boxes)))
            texts = []
            flags = det.get("is_essential_text", [])
            for i, box in enumerate(text_boxes):
                indices = sorted(assigned[i], key=lambda oi: (ocr_boxes[oi][1], ocr_boxes[oi][0]))
                texts.append({"text_id": f"{prefix}_txt_{i+1:02d}", "bbox": box,
                              "ocr_text": "\n".join(words[oi] for oi in indices),
                              "is_essential": bool(flags[i]) if i < len(flags) else True,
                              "panel_id": _panel(box, panels), "ocr_indices": indices,
                              "detection_index": i})
            for oi in unmatched:
                texts.append({"text_id": f"{prefix}_ocr_{oi+1:02d}", "bbox": ocr_boxes[oi],
                              "ocr_text": words[oi], "is_essential": True, "panel_id": _panel(ocr_boxes[oi], panels),
                              "ocr_indices": [oi], "detection_index": None})
            indices = list(range(len(texts)))
            if order != "model":
                indices = []
                for panel_id in [panels[i]["panel_id"] for i in panel_order] + [None]:
                    group = [i for i, t in enumerate(texts) if t["panel_id"] == panel_id]
                    indices.extend(group[i] for i in layout_order([texts[j]["bbox"] for j in group], order))
            for rank, i in enumerate(indices, 1):
                texts[i]["reading_order"] = rank
            if unmatched and order == "model":
                diagnostics.append({"code": "unmatched_ocr_appended_review_order"})
            characters = []
            for i, box in enumerate(char_boxes):
                crop = f"crops/{prefix}_chr_{i+1:02d}.png"
                (root / "crops").mkdir(exist_ok=True)
                image.crop((math.floor(box[0]), math.floor(box[1]), math.ceil(box[2]), math.ceil(box[3]))).save(root / crop)
                labels = det.get("character_cluster_labels", [])
                characters.append({"char_id": f"{prefix}_chr_{i+1:02d}", "bbox": box, "crop_path": crop,
                                   "panel_id": _panel(box, panels), "magi_page_cluster_id": labels[i] if i < len(labels) else None})
            associations = []
            for pair in det.get("text_character_associations", []):
                if len(pair) != 2 or any(type(v) is not int for v in pair) or not (0 <= pair[0] < len(text_boxes) and 0 <= pair[1] < len(characters)):
                    diagnostics.append({"code": "invalid_speaker_association"})
                    continue
                associations.append({"text_id": texts[pair[0]]["text_id"], "char_id": characters[pair[1]]["char_id"], "source": "magi_direct"})
            image.save(root / f"{page_id}.png")
            (root / "previews").mkdir(exist_ok=True)
            save_overlay(image, det, "detections", root / f"previews/{page_id}_annotated.jpg")
            write_json(root / f"raw_predictions/{page_id}_raw.json", raw)
            chapter["pages"].append({"page_id": page_id, "page_index": number, "image_filename": f"{page_id}.png",
                                     "input_name": path.name, "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                     "width": width, "height": height, "panels": panels, "characters": characters,
                                     "texts": texts, "associations": {"text_to_character": associations}, "diagnostics": diagnostics})
        write_json(root / "chapter_analysis.json", chapter)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents accidental replacement of a previous extraction.
        with zipfile.ZipFile(destination, "x", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
    return destination
