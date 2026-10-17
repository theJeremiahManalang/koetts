"""Adapter for dmMaze/comic-text-detector's upstream inference interface."""
import hashlib
import importlib
from pathlib import Path
import subprocess
import sys


class ComicTextDetector:
    model_id = "dmMaze/comic-text-detector"

    def __init__(self, device="auto", repo=Path("vendor/comic-text-detector"),
                 weights=Path("weights/comictextdetector.pt.onnx")):
        repo, weights = Path(repo).resolve(), Path(weights).resolve()
        if not (repo / "inference.py").is_file():
            raise ValueError(f"Comic Text Detector source missing at {repo}. See README model setup or use --ctd-repo.")
        if not weights.is_file():
            raise ValueError(f"Comic Text Detector weights missing at {weights}. See README or use --ctd-weights.")
        if weights.suffix.lower() not in {".pt", ".onnx"}:
            raise ValueError("Comic Text Detector weights must be .pt or .onnx")
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be auto, cpu, or cuda")
        import torch
        onnx = weights.suffix.lower() == ".onnx"
        if onnx and device == "cuda":
            raise ValueError("Upstream ONNX uses OpenCV CPU inference. Use --device cpu or .pt weights for CUDA.")
        if onnx:
            self.device = "cpu"
        elif device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; use --device cpu or install a compatible PyTorch build.")
        # Upstream uses absolute imports (basemodel, models, utils). Keep its
        # root available for the lifetime of this one-model CLI process.
        for name in ("inference", "basemodel", "models", "utils"):
            existing = sys.modules.get(name)
            if existing is not None:
                origin = getattr(existing, "__file__", None)
                if origin is None or not Path(origin).resolve().is_relative_to(repo):
                    raise RuntimeError(f"Upstream import conflict: {name}; run this model in a fresh Python process.")
        sys.path.insert(0, str(repo))
        try:
            detector = importlib.import_module("inference").TextDetector
        except ImportError as exc:
            raise RuntimeError("Cannot import Comic Text Detector. Install requirements-ctd.txt; see README.") from exc
        print(f"Loading {self.model_id} on {self.device}")
        self.detector = detector(model_path=str(weights), input_size=1024, device=self.device, act="leaky")
        try:
            revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                               text=True, stderr=subprocess.DEVNULL).strip()
            dirty = bool(subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True).strip())
        except (OSError, subprocess.CalledProcessError):
            revision, dirty = None, None
        self.revision = revision
        with weights.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        self.metadata = {"weights": str(weights), "weights_sha256": digest,
                         "source_directory": str(repo), "source_dirty": dirty,
                         "backend": "opencv" if onnx else "torch", "input_size": 1024}
        self.masks = []

    def predict(self, images, task="all", captions=None):
        if task not in {"all", "detect"} or captions is not None:
            raise ValueError("Comic Text Detector supports detection only, without captions")
        if not images:
            raise ValueError("Supply at least one image")
        import numpy as np
        predictions = []
        self.masks = []
        for image in images:
            # Pillow RGB -> OpenCV BGR, matching upstream imread input.
            pixels = np.asarray(image.convert("RGB"))[:, :, ::-1].copy()
            mask, refined, blocks = self.detector(pixels)
            predictions.append({"texts": [list(block.xyxy) for block in blocks],
                                "text_blocks": [block.to_dict() for block in blocks]})
            self.masks.append((mask, refined))
        return {"detections": predictions}

    def save_artifacts(self, output, prefix):
        from PIL import Image
        # The shared CLI deliberately processes one page per predict call.
        names = {}
        for label, pixels in zip(("mask", "mask-refined"), self.masks[0]):
            name = f"{prefix}.{label}.png"
            Image.fromarray(pixels).save(Path(output) / name)
            names[label] = name
        return names
