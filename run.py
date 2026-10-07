"""Run inference on an image or folder; use python run.py --help."""

import argparse
from pathlib import Path
from datetime import datetime, timezone
from config import MODEL_ID, MODEL_REVISION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Image file or folder (nonrecursive)")
    parser.add_argument("--task", choices=["all", "detect", "ocr", "ground"], default="all")
    parser.add_argument("--captions", type=Path, help="JSON mapping image filenames to captions")
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    # Validate filenames/captions before spending time loading the model.
    from files import image_paths, read_captions, load_image, write_json, save_overlay
    from magi import Magi
    try:
        paths = image_paths(args.input)
        if args.task == "ground" and not args.captions:
            parser.error("--task ground requires --captions")
        if args.captions and args.task not in {"all", "ground"}:
            parser.error("--captions is used only by all or ground")
        captions = read_captions(args.captions, paths) if args.captions else None
    except (ValueError, OSError) as exc:
        parser.error(str(exc))

    runner = Magi(args.device)
    # A separate run folder preserves results from earlier invocations.
    output = args.output / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    # Load the model only once, but process one image at a time to limit memory.
    for index, path in enumerate(paths):
        print(f"[{index + 1}/{len(paths)}] {path.name}")
        image = load_image(path)
        batch = runner.predict([image], args.task, [captions[index]] if captions else None)
        predictions = {task: values[0] for task, values in batch.items()}
        # Include the full filename and index to avoid PNG/JPG stem collisions.
        prefix = f"{index:04d}_{path.name}"
        write_json(output / f"{prefix}.json", {
            "model": MODEL_ID, "revision": MODEL_REVISION,
            "source": str(path.resolve()), "image_size": list(image.size),
            "device": runner.device, "caption": captions[index] if captions else None,
            "predictions": predictions,
        })
        for task, prediction in predictions.items():
            save_overlay(image, prediction, task, output / f"{prefix}.{task}.png")
    print(f"Results saved to {output.resolve()}")


if __name__ == "__main__":
    main()
