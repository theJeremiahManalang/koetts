"""Pure normalization: preserve MAGI order, reconcile OCR, expose reviewable speakers."""
import base64
import io
import math


def box(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("Expected a four-coordinate bounding box")
    result = [float(v) for v in value]
    if not all(math.isfinite(v) for v in result) or result[2] <= result[0] or result[3] <= result[1]:
        raise ValueError("Invalid bounding box")
    return result


def overlap(a, b):
    """Intersection over union for two independently predicted text regions."""
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2]-a[0]) * (a[3]-a[1]) + (b[2]-b[0]) * (b[3]-b[1]) - intersection
    return intersection / union if union else 0


def spatial_order(boxes):
    """LTR fallback: top-to-bottom rows, left-to-right within a row."""
    rows = []
    for index in sorted(range(len(boxes)), key=lambda i: boxes[i][1]):
        current = boxes[index]
        for row in rows:
            anchor = boxes[row[0]]
            shared = max(0, min(current[3], anchor[3]) - max(current[1], anchor[1]))
            if shared / min(current[3]-current[1], anchor[3]-anchor[1]) >= 0.5:
                row.append(index)
                break
        else:
            rows.append([index])
    return [i for row in rows for i in sorted(row, key=lambda i: boxes[i][0])]


def normalize_page(detection, ocr, image, page_id, direction):
    if direction not in {"rtl", "ltr"}:
        raise ValueError("Select rtl or ltr")
    panels = [box(b) for b in detection.get("panels", [])]
    regions = [box(b) for b in detection.get("texts", [])]
    chars = [box(b) for b in detection.get("characters", [])]
    words, locations = ocr.get("ocr_texts"), ocr.get("bboxes")
    if not isinstance(words, list) or not isinstance(locations, list) or len(words) != len(locations) or any(not isinstance(t, str) for t in words):
        raise ValueError("OCR must contain parallel ocr_texts and bboxes lists")
    locations = [box(b) for b in locations]
    clusters = detection.get("character_cluster_labels", [])
    essential = detection.get("is_essential_text", [])
    associations = detection.get("text_character_associations", [])
    appearances = []
    for i, bounds in enumerate(chars):
        x1, y1, x2, y2 = bounds
        dx, dy = (x2-x1)*.05, (y2-y1)*.05
        crop_box = (max(0, int(x1-dx)), max(0, int(y1-dy)), min(image.width, int(x2+dx)), min(image.height, int(y2+dy)))
        crop_data = ""
        if crop_box[2] > crop_box[0] and crop_box[3] > crop_box[1]:
            crop = image.crop(crop_box)
            crop.thumbnail((180, 180))
            output = io.BytesIO()
            crop.save(output, format="PNG")
            crop_data = "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()
        cluster = clusters[i] if i < len(clusters) else None
        appearances.append({"id": f"{page_id}_chr_{i+1}", "bbox": bounds, "cluster": cluster,
                            "group_id": f"{page_id}_cluster_{cluster}" if cluster is not None else f"{page_id}_appearance_{i}",
                            "crop": crop_data, "character_id": None})

    # Match each OCR region by location. Ambiguous/weak matches remain unresolved;
    # multiple OCR fragments may legitimately belong to one detection region.
    lines = []
    matched = set()
    for i, (text, bounds) in enumerate(zip(words, locations)):
        scores = sorted(((overlap(bounds, b), j) for j, b in enumerate(regions)), reverse=True)
        match = scores[0][1] if scores and scores[0][0] >= .25 and (len(scores) == 1 or scores[0][0] - scores[1][0] >= .1) else None
        if match is not None:
            matched.add(match)
        candidates = sorted({pair[1] for pair in associations if isinstance(pair, (list, tuple)) and len(pair) == 2 and pair[0] == match and isinstance(pair[1], int) and 0 <= pair[1] < len(chars)})
        lines.append({"id": f"{page_id}_text_{i+1}", "page_id": page_id, "text": text.strip(), "bbox": bounds,
                      "detection_index": match, "speaker_candidates": [appearances[c]["id"] for c in candidates],
                      "appearance_id": appearances[candidates[0]]["id"] if len(candidates) == 1 else None,
                      "included": bool(essential[match]) if match is not None and match < len(essential) else True,
                      "warning": "Review text-region match" if match is None else "Review speaker" if len(candidates) != 1 else ""})
    # Keep detected regions missed by OCR visible for manual transcription.
    for i, bounds in enumerate(regions):
        if i not in matched:
            lines.append({"id": f"{page_id}_missing_{i}", "page_id": page_id, "text": "", "bbox": bounds,
                          "detection_index": i, "speaker_candidates": [], "appearance_id": None,
                          "included": False, "warning": "No confident OCR match; review for missing or duplicate text"})
    if direction == "ltr":
        panel_order = spatial_order(panels)
        groups = {p: [] for p in panel_order}
        groups[None] = []
        for line in lines:
            b = line["bbox"]
            cx, cy = (b[0]+b[2])/2, (b[1]+b[3])/2
            parent = next((p for p in panel_order if panels[p][0] <= cx <= panels[p][2] and panels[p][1] <= cy <= panels[p][3]), None)
            groups[parent].append(line)
        lines = [group[i] for group in groups.values() for i in spatial_order([line["bbox"] for line in group])]
    for i, line in enumerate(lines, 1):
        line["sequence"] = i
    return {"id": page_id, "width": image.width, "height": image.height, "panels": panels,
            "appearances": appearances, "lines": lines}
