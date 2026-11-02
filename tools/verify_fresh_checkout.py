"""Exercise documented frozen onboarding in a disposable copy without secrets or results."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile


def ignore_checkout_artifacts(directory, names):
    patterns = (
        "node_modules", ".next", "__pycache__", ".pytest_cache", ".mypy_cache",
        ".ruff_cache", ".cache", ".turbo", ".terraform", ".venv", "venv",
        "model-cache", "*.pyc", "*.tsbuildinfo", "next-env.d.ts", ".env", ".env.*",
        "*.tfstate", "*.tfstate.*", "*.tfvars", "*.tfvars.json",
        "application_default_credentials.json", "service-account*.json",
    )
    return {
        name for name in names
        if name != ".env.example" and any(Path(name).match(pattern) for pattern in patterns)
    }


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="manga-onboarding-") as directory:
        checkout = Path(directory)
        for name in ("package.json", "package-lock.json", "pyproject.toml", "uv.lock", ".nvmrc", ".npmrc", ".python-version", "firebase.json", "README.md", "AGENTS.md", "CONTRIBUTING.md", "GLOSSARY.md", "CONTEXT.md"):
            shutil.copy2(root / name, checkout / name)
        for name in ("apps", "packages", "tests", "tools", "docs", "images", "resources", "infra"):
            shutil.copytree(root / name, checkout / name, ignore=ignore_checkout_artifacts)
        env = {**os.environ, "GEMINI_API_KEY": "", "GOOGLE_CLOUD_PROJECT": "", "NEXT_TELEMETRY_DISABLED": "1"}
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
