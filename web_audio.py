"""Validated Windows speech bridge with per-line WAV caching and chapter assembly."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

ROOT = Path(__file__).parent


def speech(args):
    if sys.platform != "win32":
        raise RuntimeError("This proof of concept uses installed Windows voices")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "speech.ps1"), *args],
                            check=True, capture_output=True, encoding="utf-8-sig", timeout=120,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    return result.stdout


def voices():
    result = json.loads(speech([]))
    return result if isinstance(result, list) else [result]


def validate_script(script, available):
    characters = script.get("characters", [])
    appearances = script.get("appearances", [])
    lines = script.get("lines", [])
    if not isinstance(characters, list) or not isinstance(appearances, list) or not isinstance(lines, list) or not 1 <= len(lines) <= 500:
        raise ValueError("Provide 1-500 dialogue lines and character references")
    registry = {c["id"]: c for c in characters}
    refs = {a["id"]: a for a in appearances}
    if len(registry) != len(characters) or len(refs) != len(appearances):
        raise ValueError("Duplicate character or appearance IDs")
    selected = []
    ids = set()
    for index, line in enumerate(lines, 1):
        if line.get("sequence") != index or line.get("id") in ids or not isinstance(line.get("id"), str):
            raise ValueError("Invalid dialogue ID or sequence")
        ids.add(line["id"])
        if not line.get("included"):
            continue
        text = line.get("text")
        character = registry.get(line.get("character_id"))
        appearance = refs.get(line.get("appearance_id"))
        if not isinstance(text, str) or not text.strip() or len(text) > 5000:
            raise ValueError(f"Line {index}: enter 1-5000 characters of dialogue")
        if not character or character.get("voice") not in available or line.get("voice") != character["voice"]:
            raise ValueError(f"Line {index}: select an available voice for its character")
        if line.get("appearance_id") and (not appearance or appearance.get("character_id") != character["id"]):
            raise ValueError(f"Line {index}: appearance and character do not agree")
        selected.append(line)
    if not selected or sum(len(line["text"]) for line in selected) > 50000:
        raise ValueError("Select dialogue totaling 1-50,000 characters")
    return selected


def generate(script, output):
    lines = validate_script(script, voices())
    cache = ROOT / ".cache" / "audio"
    cache.mkdir(parents=True, exist_ok=True)
    clips = []
    for line in lines:
        settings = {"text": line["text"].strip(), "voice": line["voice"], "rate": 0, "engine": "windows-speech-pcm22050-v1"}
        key = hashlib.sha256(json.dumps(settings, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        clip = cache / f"{key}.wav"
        if not clip.exists():
            with tempfile.TemporaryDirectory(prefix="manga-speech-") as directory:
                temporary = Path(directory) / "line.wav"
                request = Path(directory) / "request.json"
                request.write_text(json.dumps({**settings, "output": str(temporary)}, ensure_ascii=False), encoding="utf-8")
                speech([str(request)])
                with wave.open(str(temporary), "rb") as audio:
                    if audio.getnframes() == 0:
                        raise ValueError("Speech engine returned empty audio")
                clip.write_bytes(temporary.read_bytes())
        clips.append(clip)
    with wave.open(str(output), "wb") as chapter:
        chapter.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
        for index, clip in enumerate(clips):
            with wave.open(str(clip), "rb") as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 22050):
                    raise ValueError("Unexpected speech audio format")
                chapter.writeframes(audio.readframes(audio.getnframes()))
            if index < len(clips)-1:
                chapter.writeframes(b"\0\0" * int(22050 * .3))


if __name__ == "__main__":
    if sys.argv[1] == "voices":
        print(json.dumps({"voices": voices()}))
    else:
        generate(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")), Path(sys.argv[2]))
