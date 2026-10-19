"""JSON-only bridge for the local Next.js proof of concept."""
import contextlib
import json
import sys


def extract_text(path):
    from PIL import Image, ImageOps

    from runners import create_runner

    with Image.open(path) as source:
        if source.format not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError("Only PNG, JPEG and WebP are supported")
        if source.width * source.height > 25_000_000:
            raise ValueError("Image must be at most 25 megapixels")
        image = ImageOps.exif_transpose(source).convert("RGB")
    runner = create_runner("magi")
    prediction = runner.predict([image], "ocr")["ocr"][0]
    texts = prediction["ocr_texts"]
    if not isinstance(texts, list) or any(not isinstance(text, str) for text in texts):
        raise ValueError("Unexpected OCR text response")
    return {"texts": [text for text in texts if text.strip()]}


if __name__ == "__main__":
    # Model loading logs must not corrupt the JSON protocol on stdout.
    with contextlib.redirect_stdout(sys.stderr):
        result = extract_text(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False))
