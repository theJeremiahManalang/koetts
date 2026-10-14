"""Lazy model selection; model-specific dependencies load only when selected."""
from pathlib import Path

MODEL_NAMES = ("magi", "comic-text-detector")


def validate_options(model, task, captions=None):
    if model not in MODEL_NAMES:
        raise ValueError(f"Unknown model: {model}")
    if task not in {"all", "detect", "ocr", "ground"}:
        raise ValueError(f"Unknown task: {task}")
    if model == "comic-text-detector" and (task not in {"all", "detect"} or captions is not None):
        raise ValueError("comic-text-detector supports detection only; use --task detect without --captions")
    if task == "ground" and captions is None:
        raise ValueError("--task ground requires --captions")
    if captions is not None and task not in {"all", "ground"}:
        raise ValueError("--captions is used only by all or ground")


def create_runner(model, device="auto", ctd_repo=None, ctd_weights=None):
    if model == "magi":
        from magi import Magi
        return Magi(device)
    if model == "comic-text-detector":
        from comic_text_detector import ComicTextDetector
        return ComicTextDetector(device, ctd_repo or Path("vendor/comic-text-detector"),
                                 ctd_weights or Path("weights/comictextdetector.pt.onnx"))
    raise ValueError(f"Unknown model: {model}")
