"""Repository checks reject forbidden package imports and broken documentation."""
import json
import tempfile
import unittest
from pathlib import Path

from tools.check_repo import check


class RepositoryChecks(unittest.TestCase):
    def test_architecture_and_pointer_regressions_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({"workspaces": ["apps/web"]}))
            (root / "package-lock.json").write_text("{}")
            (root / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["apps/worker", "packages/engine", "packages/vision"]\n')
            source = root / "packages/engine/src/manga_tts"
            source.mkdir(parents=True)
            (source / "bad.py").write_text("from manga_worker import workflow\n")
            (root / "AGENTS.md").write_text("Read `missing.md`.\n[Missing](missing.md)\n")
            errors = check(root)
            self.assertTrue(any("forbidden dependency" in error for error in errors))
            self.assertTrue(any("broken instruction pointer" in error for error in errors))
            self.assertTrue(any("broken link" in error for error in errors))
            (source / "bad.py").write_text("from manga_vision import files\n")
            (root / "missing.md").write_text("# Present\n")
            self.assertEqual(check(root), [])
            identity = root / "apps/web/features/identity"
            studio = root / "apps/web/features/studio"
            identity.mkdir(parents=True)
            studio.mkdir(parents=True)
            (studio / "internal.ts").write_text("export const value = 1;\n")
            (identity / "bad.ts").write_text('import { value } from "../studio/internal";\n')
            self.assertTrue(any("forbidden feature dependency" in error for error in check(root)))
            (identity / "bad.ts").write_text("export const value = 1;\n")
            self.assertEqual(check(root), [])
