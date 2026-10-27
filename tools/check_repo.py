"""Validate workspace ownership, dependency boundaries, and active document links."""
from __future__ import annotations

import ast
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"node_modules", ".next", ".venv", "__pycache__", ".git", ".cache", ".ruff_cache", ".aws", ".codex"}


def check(root: Path = ROOT) -> list[str]:
    errors = []
    owners = {
        "packages/vision/src": {"manga_vision"},
        "packages/engine/src": {"manga_tts", "manga_vision"},
        "apps/worker/src": {"manga_worker", "manga_tts", "manga_vision"},
    }
    namespaces = {"manga_vision", "manga_tts", "manga_worker"}
    for owner, allowed in owners.items():
        for source in (root / owner).rglob("*.py"):
            tree = ast.parse(source.read_text(), filename=str(source))
            for node in ast.walk(tree):
                module = node.module if isinstance(node, ast.ImportFrom) else None
                imports = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [module] if module else []
                for module in imports:
                    namespace = module.split(".")[0]
                    if namespace in namespaces and namespace not in allowed:
                        errors.append(f"{source.relative_to(root)}:{node.lineno}: forbidden dependency {module}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
                    errors.append(f"{source.relative_to(root)}:{node.lineno}: use static domain imports")
    for source in (root / "apps/web").rglob("*"):
        if any(part in SKIP for part in source.parts) or source.name == "next-env.d.ts" or source.suffix not in {".ts", ".tsx"}:
            continue
        for spec in re.findall(r'(?:from\s+|import\s*)[\'"](\.[^\'\"]+)[\'"]', source.read_text()):
            target = source.parent / spec
            if not any(p.exists() for p in (target, target.with_suffix(".ts"), target.with_suffix(".tsx"))):
                errors.append(f"{source.relative_to(root)}: unresolved import {spec}")
            resolved = target.resolve()
            if "features" in source.parts:
                if "/app/" in str(resolved):
                    errors.append(f"{source.relative_to(root)}: feature imports route adapter {spec}")
                feature_root = root / "apps/web/features"
                allowed = {"identity": {"identity"}, "library": {"library", "identity"},
                           "requests": {"requests", "library", "identity"}, "studio": {"studio", "identity"}}
                owner = source.relative_to(feature_root).parts[0]
                if resolved.is_relative_to(feature_root):
                    imported = resolved.relative_to(feature_root).parts[0]
                    if imported not in allowed.get(owner, {owner}):
                        errors.append(f"{source.relative_to(root)}: forbidden feature dependency {spec}")
    for source in root.rglob("*.md"):
        if any(part in SKIP for part in source.parts):
            continue
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', source.read_text()):
            if ":" in target or target.startswith(("#", "/")):
                continue
            if not (source.parent / target.split("#")[0]).exists():
                errors.append(f"{source.relative_to(root)}: broken link {target}")
        if source.name == "AGENTS.md":
            for pointer in re.findall(r'`([^`]+\.(?:md|toml|json|yaml))`', source.read_text()):
                if "*" in pointer:
                    continue
                if not (source.parent / pointer).exists() and not (root / pointer).exists():
                    errors.append(f"{source.relative_to(root)}: broken instruction pointer {pointer}")
    manifests = [p for p in root.rglob("package-lock.json") if not any(x in SKIP for x in p.parts)]
    if manifests != [root / "package-lock.json"]:
        errors.append("Keep exactly one root npm lockfile")
    package = json.loads((root / "package.json").read_text())
    if package.get("workspaces") != ["apps/web"]:
        errors.append("Unexpected npm workspace membership")
    workspace = tomllib.loads((root / "pyproject.toml").read_text())
    if set(workspace["tool"]["uv"]["workspace"]["members"]) != set(owners_to_members()):
        errors.append("Unexpected uv workspace membership")
    for name in ("config.py", "files.py", "magi.py", "runners.py", "run.py", "web_workflow.py", "web_extract.py", "example.py"):
        if (root / name).exists():
            errors.append(f"Obsolete root entrypoint remains: {name}")
    return errors


def owners_to_members():
    return ("apps/worker", "packages/engine", "packages/vision")


if __name__ == "__main__":
    problems = check()
    print("\n".join(problems) if problems else "Workspace boundaries, imports, pointers, and active documentation links passed.")
    sys.exit(bool(problems))
