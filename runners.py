"""Lazy model selection; model-specific dependencies load only when selected."""

MODEL_NAMES = ("magi",)


def validate_options(model, task, captions=None):
    if model not in MODEL_NAMES:
        raise ValueError(f"Unknown model: {model}")
    if task not in {"all", "detect", "ocr", "ground"}:
        raise ValueError(f"Unknown task: {task}")
    if task == "ground" and captions is None:
        raise ValueError("--task ground requires --captions")
    if captions is not None and task not in {"all", "ground"}:
        raise ValueError("--captions is used only by all or ground")


def create_runner(model, device="auto"):
    if model == "magi":
        from magi import Magi
        return Magi(device)
    raise ValueError(f"Unknown model: {model}")
