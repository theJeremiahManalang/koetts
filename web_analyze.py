"""Local web bridge. Raw inference cache is independent of editable reading order."""
import contextlib
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps
from character_analysis import normalize_page
from config import MODEL_ID, MODEL_REVISION
from files import json_default

CACHE_VERSION = "analysis-rgb-v1"


def analyze(manifest_path):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    direction = manifest["direction"]
    if direction not in {"rtl", "ltr"}:
        raise ValueError("Invalid reading direction")
    cache_dir = Path(__file__).parent / ".cache" / "analysis"
    cache_dir.mkdir(parents=True, exist_ok=True)
    runner = None
    pages = []
    for index, entry in enumerate(manifest["images"], 1):
        with Image.open(entry["path"]) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"} or source.width * source.height > 25_000_000:
                raise ValueError("Use PNG, JPEG or WebP images of at most 25 megapixels")
            image = ImageOps.exif_transpose(source).convert("RGB")
        digest = hashlib.sha256(image.tobytes() + str(image.size).encode() + f"{MODEL_ID}:{MODEL_REVISION}:{CACHE_VERSION}".encode()).hexdigest()
        cache_file = cache_dir / f"{digest}.json"
        if cache_file.exists():
            raw = json.loads(cache_file.read_text(encoding="utf-8"))
        else:
            if runner is None:
                from magi import Magi
                runner = Magi()
            predictions = runner.predict([image], "all")
            raw = json.loads(json.dumps({"detections": predictions["detections"][0], "ocr": predictions["ocr"][0]}, default=json_default))
            temporary = cache_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            temporary.replace(cache_file)
        page = normalize_page(raw["detections"], raw["ocr"], image, f"page_{index:03d}", direction)
        page.update({"filename": entry["name"], "image_hash": digest})
        pages.append(page)
    return {"schema_version": "1.0.0", "reading_direction": direction, "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION, "pages": pages}


if __name__ == "__main__":
    with contextlib.redirect_stdout(sys.stderr):
        result = analyze(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False))
