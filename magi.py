"""Small, reusable wrapper around the three upstream prediction methods."""

from config import MODEL_ID, MODEL_REVISION


class Magi:
    def __init__(self, device="auto"):
        # Lazy imports let --help and input validation work before ML setup.
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be auto, cpu, or cuda")
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable. Check your NVIDIA driver and PyTorch build, or use --device cpu.")

        self.device = device
        # Half precision saves GPU memory. CPU uses float32 for compatibility.
        dtype = torch.float16 if device == "cuda" else torch.float32
        print(f"Loading {MODEL_ID} on {device}; first run downloads model files.")
        common = dict(revision=MODEL_REVISION, trust_remote_code=True)
        self.processor = AutoProcessor.from_pretrained(MODEL_ID, **common)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=dtype,
            # Eager attention avoids requiring the optional flash-attn package.
            attn_implementation="eager",
            use_safetensors=True,
            **common,
        ).to(device).eval()
        # eval() disables training behavior such as dropout; it does not train.
        self.torch = torch

    def predict(self, images, task="all", captions=None):
        if task not in {"all", "detect", "ocr", "ground"}:
            raise ValueError("Unknown task")
        if not images:
            raise ValueError("Supply at least one image")
        if task == "ground" and captions is None:
            raise ValueError("Grounding requires captions")
        if captions is not None:
            if len(captions) != len(images) or any(not isinstance(c, str) or not c.strip() for c in captions):
                raise ValueError("Provide one nonempty caption per image")
            # Upstream uses str.format on prompts. Literal braces would be
            # treated as formatting fields even though no boxes were supplied.
            if any("{" in c or "}" in c for c in captions):
                raise ValueError("Captions cannot contain literal { or } with this processor")

        result = {}
        # Inference does not need gradients, which are used to update weights.
        with self.torch.inference_mode():
            if task in {"all", "detect"}:
                result["detections"] = self.model.predict_detections_and_associations(images, self.processor)
            if task in {"all", "ocr"}:
                result["ocr"] = self.model.predict_ocr(images, self.processor)
            if task == "ground" or (task == "all" and captions is not None):
                result["grounding"] = self.model.predict_character_grounding(images, captions, self.processor)
        return result
