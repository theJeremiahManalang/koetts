"""Cleaner stage implementation; public workflow commands live in PipelineRouter."""
from __future__ import annotations
import copy
import unicodedata
from typing import Any
_PUNCTUATION = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "--",
    "\u2026": "...", "\u00a0": " ", "\u202f": " ", "\ufeff": "", "\u200b": "",
})


def normalize_text(text: str) -> str:
    """Return an idempotent, speech-safe punctuation/encoding proposal; never mutate inputs.

    Repairs reversible UTF-8 bytes misdecoded as CP1252/Latin-1 (including repeated
    corruption), then converts smart punctuation to ASCII, normalizes line endings,
    and removes surrogates/unsupported controls. Valid Unicode, tabs, newlines and
    vocal tags survive. U+FFFD survives deliberately: lost bytes cannot be recovered.
    Ambiguous byte-like character sequences need human review. No files or API calls.
    Callers must present changes before approval, never silently clean approved speech.
    Raises TypeError for non-string input.
    """
    if not isinstance(text, str):
        raise TypeError("Text must be a string")
    def byte(char: str) -> int | None:
        for encoding in ("cp1252", "latin-1"):
            try:
                return char.encode(encoding)[0]
            except UnicodeEncodeError:
                continue
        return None
    # Each successful repair shortens the string, so iteration reaches a fixed point.
    while True:
        result, index = [], 0
        while index < len(text):
            first = byte(text[index])
            size = (2 if first is not None and 0xC2 <= first <= 0xDF else
                    3 if first is not None and 0xE0 <= first <= 0xEF else
                    4 if first is not None and 0xF0 <= first <= 0xF4 else 0)
            if size and index + size <= len(text):
                values = [byte(c) for c in text[index:index + size]]
                if all(v is not None and 0x80 <= v <= 0xBF for v in values[1:]):
                    try:
                        result.append(bytes(value for value in values if value is not None).decode("utf-8"))
                        index += size
                        continue
                    except UnicodeDecodeError:
                        pass
            result.append(text[index])
            index += 1
        repaired = "".join(result)
        if repaired != text:
            text = repaired
            continue
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n").translate(_PUNCTUATION)
        cleaned = "".join(c for c in cleaned if unicodedata.category(c) not in {"Cs", "Cc"} or c in "\n\t")
        if cleaned == text:
            return cleaned
        # Removed controls can expose another reversible byte sequence. Reach a
        # fixed point across BOTH repair and cleanup, without recursive calls.
        text = cleaned


def require_reviewed_text(text: str, label: str = "text") -> None:
    """Reject unrecoverable or unnormalized render text without altering it or logging content.

    Raises ValueError requiring correction/exclusion or review of normalize_text output.
    Use before approval and again at the speech boundary; no mutation/I/O.
    """
    if "\ufffd" in text:
        raise ValueError(f"{label}: unrecoverable replacement character; correct or exclude before rendering")
    if normalize_text(text) != text:
        raise ValueError(f"{label}: review suggested text repairs and apply them before approval")


def normalize_planning_data(value: Any) -> Any:
    """Return a cleaned JSON copy for visual planning; leave project/source evidence intact.

    Unknown replacement characters remain visible to the image-assisted planner.
    The resulting proposal still needs human review. Dict keys, IDs and filesystem
    paths are not rewritten, so planning still refers to the original source assets.
    """
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        return [normalize_planning_data(item) for item in value]
    if isinstance(value, dict):
        return {key: copy.deepcopy(item) if key.endswith(("_id", "_ids", "_path", "_filename"))
                or key in {"references", "path", "filename", "voice", "planning_model", "tts_model"}
                else normalize_planning_data(item) for key, item in value.items()}
    return value
