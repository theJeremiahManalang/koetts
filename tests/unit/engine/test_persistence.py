"""Durable revision contract tests using local in-memory adapters."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tests.unit.engine import test_audio_pipeline as fixtures

from manga_tts import PipelineConfig, PipelineRouter, schemas
from manga_tts.persistence import (
    InMemoryArtifactStore,
    InMemoryRevisionStore,
    PersistenceConflict,
    ProjectPersistence,
    ProjectRevision,
)
from manga_tts.schemas import WorkflowError
from manga_tts.storage import read_json, write_json


def require_revision(revision: ProjectRevision | None) -> ProjectRevision:
    if revision is None:
        raise AssertionError("Expected a current project revision")
    return revision


class BarrierArtifactStore(InMemoryArtifactStore):
    """Let two commits finish artifact staging before either pointer CAS."""

    def __init__(self):
        super().__init__()
        self.barrier: threading.Barrier | None = None
        self.local = threading.local()

    def put(self, content: bytes):
        if self.barrier is not None and not getattr(self.local, "waited", False):
            self.local.waited = True
            self.barrier.wait(timeout=5)
        return super().put(content)


class FailingRevisionStore(InMemoryRevisionStore):
    def __init__(self):
        super().__init__()
        self.fail_next_commit = False

    def commit(self, *args, **kwargs):
        if self.fail_next_commit:
            self.fail_next_commit = False
            raise OSError("simulated pointer-store failure")
        return super().commit(*args, **kwargs)


class FailingReadArtifactStore(InMemoryArtifactStore):
    def __init__(self):
        super().__init__()
        self.fail_copy_at: int | None = None
        self.copy_count = 0

    def copy_to(self, artifact, destination):
        self.copy_count += 1
        if self.copy_count == self.fail_copy_at:
            raise OSError("simulated artifact read failure")
        return super().copy_to(artifact, destination)


class CorruptingArtifactStore(InMemoryArtifactStore):
    def __init__(self):
        super().__init__()
        self.corrupt_reads = False

    def copy_to(self, artifact, destination):
        super().copy_to(artifact, destination)
        if self.corrupt_reads:
            Path(destination).write_bytes(b"corrupted artifact")


class ProjectPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        fixture = fixtures.PipelineTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = Path(self.temp.name) / "project"
        shutil.copytree(fixture.router.root, self.root)
        (self.root / "input/page.png").write_bytes(b"page-one")
        self.state = schemas.dump(fixture.router.project)
        self.state["title"] = "First"
        write_json(self.root / "project.json", self.state)
        self.artifacts = InMemoryArtifactStore()
        self.revisions = InMemoryRevisionStore()
        self.persistence = ProjectPersistence(self.artifacts, self.revisions)

    def test_commit_writes_verified_manifest_and_load_restores_current_revision(self):
        writer = self.persistence.acquire("chapter", "worker-1")
        first = writer.commit(self.root, self.state, expected_revision_id=None)
        self.assertEqual(first.parent_revision_id, None)

        manifest = self.persistence.read_manifest(first.manifest)
        page = manifest.entries["input/page.png"]
        self.assertEqual(page.artifact.sha256, hashlib.sha256(b"page-one").hexdigest())
        self.assertEqual(self.artifacts.get(page.artifact), b"page-one")

        changed = {**self.state, "title": "Second"}
        second = writer.commit(self.root, changed, expected_revision_id=first.revision_id)
        self.assertEqual(second.parent_revision_id, first.revision_id)
        self.assertEqual(second.project_hash, hashlib.sha256(
            json.dumps(changed, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest())
        writer.release()

        restored_root = Path(self.temp.name) / "restored"
        reader = self.persistence.acquire("chapter", "reader-1")
        loaded = require_revision(reader.load(restored_root))
        self.assertEqual(loaded.revision_id, second.revision_id)
        self.assertEqual(read_json(restored_root / "project.json")["title"], "Second")
        self.assertEqual((restored_root / "input/page.png").read_bytes(), b"page-one")
        reader.release()

    def test_competing_commits_have_one_winner_and_stale_pointer_stays_unchanged(self):
        seed = self.persistence.acquire("chapter", "seed")
        seed.commit(self.root, self.state, expected_revision_id=None)
        require_revision(self.persistence.current("chapter"))
        seed.release()

        artifacts = BarrierArtifactStore()
        revisions = InMemoryRevisionStore()
        persistence = ProjectPersistence(artifacts, revisions)
        # Seed the second store before racing the two candidate revisions.
        writer = persistence.acquire("chapter", "worker-2")
        base = writer.commit(self.root, self.state, expected_revision_id=None)
        artifacts.barrier = threading.Barrier(2)
        outcomes = []
        def commit(title):
            state = {**self.state, "title": title}
            try:
                outcomes.append(writer.commit(self.root, state, expected_revision_id=base.revision_id))
            except PersistenceConflict as exc:
                outcomes.append(exc)
        threads = [threading.Thread(target=commit, args=(title,)) for title in ("A", "B")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sum(not isinstance(value, Exception) for value in outcomes), 1)
        conflicts = [value for value in outcomes if isinstance(value, PersistenceConflict)]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].code, "revision_conflict")
        winners = [value for value in outcomes if isinstance(value, ProjectRevision)]
        current = require_revision(persistence.current("chapter"))
        self.assertEqual(len(winners), 1)
        self.assertEqual(current.revision_id, winners[0].revision_id)
        writer.release()

    def test_uploaded_artifacts_do_not_promote_when_pointer_commit_fails(self):
        revisions = FailingRevisionStore()
        persistence = ProjectPersistence(self.artifacts, revisions)
        writer = persistence.acquire("chapter", "worker-1")
        first = writer.commit(self.root, self.state, expected_revision_id=None)
        old_project = (self.root / "project.json").read_bytes()
        artifact_count = self.artifacts.count
        revisions.fail_next_commit = True

        with self.assertRaisesRegex(OSError, "pointer-store failure"):
            writer.commit(self.root, {**self.state, "title": "Uncommitted"},
                          expected_revision_id=first.revision_id)

        self.assertEqual(require_revision(persistence.current("chapter")).revision_id, first.revision_id)
        self.assertEqual((self.root / "project.json").read_bytes(), old_project)
        self.assertGreater(self.artifacts.count, artifact_count)
        writer.release()

    def test_artifact_verification_failure_keeps_prior_revision_current(self):
        artifacts = CorruptingArtifactStore()
        persistence = ProjectPersistence(artifacts, InMemoryRevisionStore())
        writer = persistence.acquire("chapter", "worker-1")
        first = writer.commit(self.root, self.state, expected_revision_id=None)
        old_project = (self.root / "project.json").read_bytes()
        artifacts.corrupt_reads = True

        with self.assertRaisesRegex(ValueError, "Artifact checksum mismatch"):
            writer.commit(self.root, {**self.state, "title": "Corrupt"},
                          expected_revision_id=first.revision_id)

        self.assertEqual(require_revision(persistence.current("chapter")).revision_id, first.revision_id)
        self.assertEqual((self.root / "project.json").read_bytes(), old_project)
        writer.release()

    def test_workspace_overlay_waits_for_pointer_commit(self):
        revisions = FailingRevisionStore()
        persistence = ProjectPersistence(self.artifacts, revisions)
        (self.root / "references").mkdir(exist_ok=True)
        (self.root / "references/old.png").write_bytes(b"old reference")
        writer = persistence.acquire("chapter", "worker-1")
        first = writer.commit(self.root, self.state, expected_revision_id=None)
        overlay = Path(self.temp.name) / "overlay"
        overlay.mkdir()
        (overlay / "new.png").write_bytes(b"new reference")
        revisions.fail_next_commit = True

        with self.assertRaisesRegex(OSError, "pointer-store failure"):
            writer.commit(self.root, self.state, first.revision_id,
                          workspace_overlays={"references": overlay})

        self.assertEqual(require_revision(persistence.current("chapter")).revision_id, first.revision_id)
        self.assertEqual((self.root / "references/old.png").read_bytes(), b"old reference")
        self.assertFalse((self.root / "references/new.png").exists())
        writer.release()

    def test_failed_restore_keeps_existing_workspace_intact(self):
        artifacts = FailingReadArtifactStore()
        persistence = ProjectPersistence(artifacts, InMemoryRevisionStore())
        writer = persistence.acquire("chapter", "worker-1")
        writer.commit(self.root, self.state, expected_revision_id=None)
        writer.release()

        old_project = b"old local view"
        old_page = b"old local asset"
        (self.root / "project.json").write_bytes(old_project)
        (self.root / "input/page.png").write_bytes(old_page)
        artifacts.copy_count = 0
        artifacts.fail_copy_at = 3  # Manifest, first entry, then the second entry.
        reader = persistence.acquire("chapter", "reader-1")
        with self.assertRaisesRegex(OSError, "artifact read failure"):
            reader.load(self.root)
        self.assertEqual((self.root / "project.json").read_bytes(), old_project)
        self.assertEqual((self.root / "input/page.png").read_bytes(), old_page)
        reader.release()

    def test_writer_ownership_blocks_edits_and_stale_fence_cannot_commit_after_recovery(self):
        first = self.persistence.acquire("chapter", "worker-1")
        fence = first.fence
        with self.assertRaises(PersistenceConflict) as blocked:
            self.persistence.acquire("chapter", "admin-edit")
        self.assertEqual(blocked.exception.code, "writer_conflict")
        with self.assertRaises(PersistenceConflict):
            self.persistence.recover("chapter", "worker-1", fence, worker_stopped=False)

        self.persistence.recover("chapter", "worker-1", fence, worker_stopped=True)
        second = self.persistence.acquire("chapter", "admin-edit")
        self.assertGreater(second.fence, fence)
        with self.assertRaises(PersistenceConflict) as stale:
            first.commit(self.root, {**self.state, "title": "Stale"}, expected_revision_id=None)
        self.assertEqual(stale.exception.code, "stale_fence")
        second.release()


class PipelinePersistenceTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.PipelineTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.approve()
        self.fixture = fixture
        self.root = fixture.root / "persisted-project"
        shutil.copytree(fixture.router.root, self.root)

    def make_store(self, revisions=None):
        artifacts = InMemoryArtifactStore()
        revisions = revisions or InMemoryRevisionStore()
        return ProjectPersistence(artifacts, revisions), artifacts, revisions

    def test_router_checkpoint_survives_new_writer_and_reuses_accepted_audio(self):
        persistence, _, _ = self.make_store()
        writer = persistence.acquire("chapter", "worker-1")
        writer.load(self.root)
        calls = []
        router = PipelineRouter(
            PipelineConfig(workspace=self.root),
            client_factory=lambda: object(),
            renderer_factory=lambda client, model: lambda request: calls.append(request) or fixtures.wav_bytes(),
            persistence=writer,
        )
        router.load_project()
        router.render_selected(schemas.RenderCommand(scene_ids=["scene_001"]))
        accepted = require_revision(persistence.current("chapter"))
        take = next(iter(router.project.takes.values()))[0]
        audio_path = self.root / take.path
        audio_hash = hashlib.sha256(audio_path.read_bytes()).hexdigest()
        self.assertEqual(audio_hash, take.audio_sha256)
        self.assertEqual(len(calls), 2)
        writer.release()

        next_writer = persistence.acquire("chapter", "worker-2")
        resumed = PipelineRouter(
            PipelineConfig(workspace=self.root),
            client_factory=lambda: self.fail("Provider client must stay lazy"),
            renderer_factory=lambda client, model: self.fail("Accepted audio must be reused"),
            persistence=next_writer,
        )
        loaded = resumed.load_project()
        self.assertEqual(require_revision(persistence.current("chapter")).revision_id, accepted.revision_id)
        self.assertEqual(sum(map(len, loaded.takes.values())), 2)
        resumed.render_selected(schemas.RenderCommand(scene_ids=["scene_001"]))
        self.assertEqual(hashlib.sha256(audio_path.read_bytes()).hexdigest(), audio_hash)
        next_writer.release()

    def test_checkpoint_failure_does_not_acknowledge_or_promote_audio(self):
        revisions = FailingRevisionStore()
        persistence, _, _ = self.make_store(revisions)
        writer = persistence.acquire("chapter", "worker-1")
        writer.load(self.root)
        router = PipelineRouter(
            PipelineConfig(workspace=self.root),
            client_factory=lambda: object(),
            renderer_factory=lambda client, model: lambda request: fixtures.wav_bytes(),
            persistence=writer,
        )
        router.load_project()
        current = require_revision(persistence.current("chapter"))
        project_bytes = (self.root / "project.json").read_bytes()
        revisions.fail_next_commit = True

        with self.assertRaises(WorkflowError):
            router.render_selected(schemas.RenderCommand(scene_ids=["scene_001"]))

        self.assertEqual(require_revision(persistence.current("chapter")).revision_id, current.revision_id)
        self.assertEqual((self.root / "project.json").read_bytes(), project_bytes)
        writer.release()
        recovered = persistence.acquire("chapter", "worker-2")
        recovered.load(self.root)
        self.assertEqual(sum(map(len, read_json(self.root / "project.json")["takes"].values())), 0)
        recovered.release()

    def test_failed_cast_import_does_not_overwrite_current_workspace_assets(self):
        revisions = FailingRevisionStore()
        persistence, _, _ = self.make_store(revisions)
        writer = persistence.acquire("chapter", "worker-1")
        router = PipelineRouter(PipelineConfig(workspace=self.root), persistence=writer)
        router.load_project()
        current = require_revision(persistence.current("chapter"))
        cast_manifest = {"characters": [{"speaker_id": "D", "name": "D", "is_generic": True}]}
        pack = Path(self.fixture.root) / "replacement-cast.zip"
        with zipfile.ZipFile(pack, "w") as archive:
            archive.writestr("cast.json", json.dumps(cast_manifest))
            archive.writestr("new-reference.bin", b"replacement asset")
        old_manifest = (self.root / "references/cast.json").read_bytes()
        revisions.fail_next_commit = True

        with self.assertRaises(WorkflowError):
            router.import_cast(pack)

        self.assertEqual(require_revision(persistence.current("chapter")).revision_id, current.revision_id)
        self.assertEqual((self.root / "references/cast.json").read_bytes(), old_manifest)
        self.assertFalse((self.root / "references/new-reference.bin").exists())
        writer.release()

    def test_router_reports_stale_fence_as_typed_conflict(self):
        persistence, _, _ = self.make_store()
        stale_writer = persistence.acquire("chapter", "worker-1")
        stale_writer.load(self.root)
        stale_router = PipelineRouter(PipelineConfig(workspace=self.root), persistence=stale_writer)
        stale_router.load_project()
        fence = stale_writer.fence
        persistence.recover("chapter", "worker-1", fence, worker_stopped=True)

        current_writer = persistence.acquire("chapter", "worker-2")
        current_router = PipelineRouter(PipelineConfig(workspace=self.root), persistence=current_writer)
        current_router.load_project()
        before = require_revision(persistence.current("chapter"))
        with self.assertRaises(WorkflowError) as conflict:
            stale_router.update_metadata({"title": "Stale worker"})
        self.assertEqual(conflict.exception.detail.code, "stale_fence")
        self.assertEqual(require_revision(persistence.current("chapter")).revision_id, before.revision_id)
        current_writer.release()

    def test_transport_metadata_advances_the_same_revision_pointer(self):
        persistence, _, _ = self.make_store()
        writer = persistence.acquire("chapter", "worker-1")
        router = PipelineRouter(PipelineConfig(workspace=self.root), persistence=writer)
        router.load_project()
        before = require_revision(persistence.current("chapter"))

        updated = router.update_metadata({"title": "Durable title"})

        current = require_revision(persistence.current("chapter"))
        self.assertNotEqual(current.revision_id, before.revision_id)
        self.assertEqual(current.parent_revision_id, before.revision_id)
        self.assertEqual(current.project_hash, hashlib.sha256(
            json.dumps(schemas.dump(updated), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest())
        writer.release()

    def test_post_commit_materialization_failure_is_reported_as_accepted_checkpoint(self):
        persistence, _, _ = self.make_store()
        writer = persistence.acquire("chapter", "worker-1")
        router = PipelineRouter(PipelineConfig(workspace=self.root), persistence=writer)
        router.load_project()
        before = require_revision(persistence.current("chapter"))

        with (
            patch("manga_tts.persistence.ProjectWriter._replace_workspace",
                  side_effect=OSError("local volume unavailable")),
            self.assertRaises(WorkflowError) as result,
        ):
            router.update_metadata({"title": "Accepted revision"})

        self.assertEqual(result.exception.detail.code, "checkpoint_materialization_pending")
        current = require_revision(persistence.current("chapter"))
        self.assertNotEqual(current.revision_id, before.revision_id)
        self.assertEqual(current.parent_revision_id, before.revision_id)
        self.assertTrue(writer.materialization_pending)
        with self.assertRaises(PersistenceConflict) as blocked:
            writer.commit(self.root, schemas.dump(router.project), current.revision_id)
        self.assertEqual(blocked.exception.code, "workspace_refresh_required")
        self.assertEqual(require_revision(persistence.current("chapter")).revision_id, current.revision_id)
        restored = require_revision(writer.load(self.root))
        self.assertEqual(restored.revision_id, current.revision_id)
        self.assertEqual(read_json(self.root / "project.json")["title"], "Accepted revision")
        writer.release()


if __name__ == "__main__":
    unittest.main()
