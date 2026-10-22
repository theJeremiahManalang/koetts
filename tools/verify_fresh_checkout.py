"""Exercise documented frozen onboarding in a disposable copy without secrets or results."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="manga-onboarding-") as directory:
        checkout = Path(directory)
        for name in ("package.json", "package-lock.json", "pyproject.toml", "uv.lock", ".nvmrc", ".npmrc", ".python-version", "README.md", "AGENTS.md", "CONTRIBUTING.md", "GLOSSARY.md", "CONTEXT.md"):
            shutil.copy2(root / name, checkout / name)
        for name in ("apps", "packages", "tests", "tools", "docs", "images"):
            shutil.copytree(root / name, checkout / name, ignore=shutil.ignore_patterns(
                "node_modules", ".next", "__pycache__", "*.tsbuildinfo", "next-env.d.ts", ".env", ".env.local"))
        env = {**os.environ, "GEMINI_API_KEY": "", "NEXT_TELEMETRY_DISABLED": "1"}
        for name in ("PYTHON_EXECUTABLE", "MANGA_DATA_ROOT", "MANGA_REPO_ROOT", "MANGA_TTS_SAMPLE_PROJECT", "MANGA_WEB_TEST_URL", "VIRTUAL_ENV"):
            env.pop(name, None)
        for command in (["uv", "sync", "--frozen"], ["npm", "ci"], ["npm", "run", "check:repo"], ["npm", "test"]):
            subprocess.run(command, cwd=checkout, env=env, check=True, timeout=300)
        interpreter = checkout / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(interpreter), "-c", "import importlib.util; assert importlib.util.find_spec('torch') is None"],
                       cwd=directory, env=env, check=True)
        with tempfile.TemporaryDirectory(prefix="manga-cli-cwd-") as external:
            for module in ("manga_tts", "manga_vision", "manga_worker.workflow", "manga_worker.extract"):
                subprocess.run([str(interpreter), "-m", module, "--help"], cwd=external, env=env, check=True, timeout=30)
        print("Fresh-checkout frozen installs, tests, lightweight environment, and external-directory entrypoints passed.")


if __name__ == "__main__":
    main()
