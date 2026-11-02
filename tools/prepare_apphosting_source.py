#!/usr/bin/env python3
"""Create a sanitized, flat App Hosting source tree with a projected npm lockfile."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_WORKSPACE = "apps/web"
EXPECTED_LINK = "node_modules/@manga/web"

EXCLUDED_DIRS = {
    ".aws",
    ".cache",
    ".codex",
    ".git",
    ".next",
    ".terraform",
    ".venv",
    ".agents",
    "__pycache__",
    "infra",
    "node_modules",
    "results",
    "vendor",
    "weights",
}
EXCLUDED_FILES = {".firebaserc", "package-lock.json"}
SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}


class PreparationError(Exception):
    """Raised when source cannot be staged without guessing."""


def fail(message: str) -> None:
    raise PreparationError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read valid JSON from {path}: {exc}")
    if not isinstance(result, dict):
        fail(f"expected a JSON object in {path}")
    return result


def has_workspace_protocol(value: Any) -> bool:
    if isinstance(value, dict):
        return any(has_workspace_protocol(item) for item in value.values())
    if isinstance(value, list):
        return any(has_workspace_protocol(item) for item in value)
    return isinstance(value, str) and value.startswith("workspace:")


def projected_lock(root_lock: dict[str, Any], web_manifest: dict[str, Any]) -> dict[str, Any]:
    packages = root_lock.get("packages")
    if not isinstance(packages, dict):
        fail("root package-lock.json has no packages object")
    root_entry = packages.get("")
    app_entry = packages.get(EXPECTED_WORKSPACE)
    if not isinstance(root_entry, dict) or not isinstance(app_entry, dict):
        fail("lockfile must contain root and apps/web package entries")

    workspaces = root_entry.get("workspaces")
    if workspaces != [EXPECTED_WORKSPACE]:
        fail(f"unexpected root lock workspaces: {workspaces!r}")
    manifest_workspaces = load_json(ROOT / "package.json").get("workspaces")
    if manifest_workspaces != [EXPECTED_WORKSPACE]:
        fail(f"unexpected root package.json workspaces: {manifest_workspaces!r}")
    if web_manifest.get("name") != app_entry.get("name"):
        fail("apps/web manifest name does not match its root lockfile entry")
    if app_entry.get("name") != "@manga/web":
        fail(f"unexpected apps/web package name: {app_entry.get('name')!r}")

    app_workspace_entries = [
        key for key in packages if key.startswith("apps/") and key != EXPECTED_WORKSPACE
    ]
    if app_workspace_entries:
        fail(f"unexpected nested or additional workspace lock entries: {app_workspace_entries}")
    app_nested_entries = [key for key in packages if key.startswith(f"{EXPECTED_WORKSPACE}/")]
    if app_nested_entries:
        fail(f"nested lock entries under apps/web cannot be projected: {app_nested_entries}")

    links = {key: value for key, value in packages.items() if isinstance(value, dict) and value.get("link")}
    if links != {EXPECTED_LINK: {"resolved": EXPECTED_WORKSPACE, "link": True}}:
        fail(f"unexpected workspace or package links in lockfile: {links!r}")
    if has_workspace_protocol(app_entry) or has_workspace_protocol(web_manifest):
        fail("apps/web uses a workspace: dependency that cannot be projected safely")
    if app_entry.get("dependencies", {}) != web_manifest.get("dependencies", {}):
        fail("apps/web dependency declarations differ between manifest and root lockfile")
    if app_entry.get("devDependencies", {}) != web_manifest.get("devDependencies", {}):
        fail("apps/web devDependency declarations differ between manifest and root lockfile")

    projected = json.loads(json.dumps(root_lock))
    projected_packages = projected["packages"]
    projected_packages[""] = projected_packages.pop(EXPECTED_WORKSPACE)
    del projected_packages[EXPECTED_LINK]
    projected["name"] = app_entry["name"]
    if "version" in app_entry:
        projected["version"] = app_entry["version"]

    # Keep every installed package record byte-for-byte equivalent as JSON data.
    original_installed = {
        key: value for key, value in packages.items() if key.startswith("node_modules/") and key != EXPECTED_LINK
    }
    output_installed = {
        key: value for key, value in projected_packages.items() if key.startswith("node_modules/")
    }
    if original_installed != output_installed:
        fail("projected lockfile changed a node_modules package record")
    return projected


def excluded(relative: Path) -> bool:
    parts = relative.parts
    name = relative.name
    lower = name.lower()
    if any(part in EXCLUDED_DIRS for part in parts):
        return True
    if name in EXCLUDED_FILES:
        return True
    if lower == ".env" or lower.startswith(".env."):
        return True
    if lower.endswith(tuple(SENSITIVE_SUFFIXES)):
        return True
    if "credential" in lower or "service-account" in lower or "service_account" in lower:
        return True
    if lower.endswith((".tfstate", ".tfstate.backup", ".tfvars", ".tfvars.json")):
        return True
    if lower.endswith((".pyc", ".tsbuildinfo")):
        return True
    if lower.startswith("firebase-debug") and lower.endswith(".log"):
        return True
    return False


def copy_app_source(source: Path, target: Path) -> tuple[int, list[str]]:
    copied = 0
    omitted: list[str] = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if excluded(relative):
            omitted.append(relative.as_posix())
            continue
        if path.is_symlink():
            fail(f"refusing to stage symlink: {relative}")
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            copied += 1
    return copied, omitted


def prepare(output: Path) -> tuple[int, list[str]]:
    source = ROOT / EXPECTED_WORKSPACE
    if not source.is_dir():
        fail(f"missing web workspace: {source}")
    output = output.expanduser().resolve()
    if output.exists():
        fail(f"output already exists; choose a new directory: {output}")
    if output == ROOT or ROOT in output.parents:
        fail("output must be outside the repository to avoid recursive source staging")

    web_manifest = load_json(source / "package.json")
    lock = projected_lock(load_json(ROOT / "package-lock.json"), web_manifest)
    root_manifest = load_json(ROOT / "package.json")
    deployment_manifest = json.loads(json.dumps(web_manifest))
    # npm only honors overrides at its installation root. Preserve root policy
    # when a buildpack treats the app directory as a standalone installation.
    for key in ("overrides", "packageManager"):
        if key in root_manifest:
            if key in web_manifest and web_manifest[key] != root_manifest[key]:
                fail(f"conflicting root and app {key} cannot be projected safely")
            deployment_manifest[key] = root_manifest[key]

    config = load_json(ROOT / "firebase.json")
    existing_apphosting = config.get("apphosting", [])
    selected = [
        item for item in existing_apphosting
        if isinstance(item, dict) and item.get("rootDir") == EXPECTED_WORKSPACE
    ]
    if len(selected) != 1:
        fail("firebase.json must contain exactly one App Hosting target rooted at apps/web")
    flat_apphosting = json.loads(json.dumps(selected[0]))
    flat_apphosting["rootDir"] = "."

    output.mkdir(parents=True)
    try:
        copied, omitted = copy_app_source(source, output)
        (output / "package.json").write_text(
            json.dumps(deployment_manifest, indent=2) + "\n", encoding="utf-8"
        )
        (output / "package-lock.json").write_text(
            json.dumps(lock, indent=2) + "\n", encoding="utf-8"
        )
        (output / "firebase.json").write_text(
            json.dumps({"apphosting": [flat_apphosting]}, indent=2) + "\n", encoding="utf-8"
        )
        for name in (".nvmrc", ".npmrc"):
            source_file = ROOT / name
            if source_file.is_file():
                shutil.copy2(source_file, output / name)
        append_standalone_flag(output / "apphosting.yaml")
        validate_staged_tree(output)
        return copied, omitted
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def append_standalone_flag(path: Path) -> None:
    if not path.is_file():
        fail("apps/web/apphosting.yaml is required for the flat App Hosting source")
    lines = path.read_text(encoding="utf-8").splitlines()
    flag_lines = [line.strip() for line in lines if "MANGA_STANDALONE_WEB" in line]
    if flag_lines:
        fail("MANGA_STANDALONE_WEB must be generated in staging, not declared in source apphosting.yaml")
    stanza = [
        "  - variable: MANGA_STANDALONE_WEB",
        '    value: "1"',
        "    availability: [BUILD, RUNTIME]",
    ]
    path.write_text("\n".join([*lines, *stanza, ""]), encoding="utf-8")


def validate_staged_tree(output: Path) -> None:
    forbidden_dirs = EXCLUDED_DIRS | {".env"}
    for path in output.rglob("*"):
        relative = path.relative_to(output)
        if path.is_symlink():
            fail(f"staged tree contains symlink: {relative}")
        if any(part in forbidden_dirs for part in relative.parts):
            fail(f"staged tree contains excluded path: {relative}")
        if relative.as_posix() not in {"package-lock.json", "apps/web/package-lock.json"} and excluded(relative):
            fail(f"staged tree contains excluded file: {relative}")
    if (output / "apps").exists():
        fail("flat staged tree must not contain the apps/ workspace directory")
    if not (output / "package-lock.json").is_file():
        fail("flat staged tree is missing package-lock.json")
    config = load_json(output / "firebase.json")
    apphosting = config.get("apphosting", [])
    if set(config) != {"apphosting"} or len(apphosting) != 1 or apphosting[0].get("rootDir") != ".":
        fail("staged firebase.json must contain only the existing apphosting target with rootDir '.'")
    yaml_lines = (output / "apphosting.yaml").read_text(encoding="utf-8").splitlines()
    if not any(line.strip() == "- variable: MANGA_STANDALONE_WEB" for line in yaml_lines):
        fail("staged apphosting.yaml is missing MANGA_STANDALONE_WEB")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="new staging directory to create")
    args = parser.parse_args()
    try:
        copied, omitted = prepare(args.output)
    except (PreparationError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Prepared App Hosting source at {args.output.expanduser().resolve()}")
    print(f"Copied {copied} app files; omitted {len(omitted)} excluded paths.")
    print("Projected lock: flat package-lock.json from root workspace package-lock.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
