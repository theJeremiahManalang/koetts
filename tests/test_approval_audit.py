"""Approval audit is committed with reviewed state, without provider calls."""
import unittest
from unittest.mock import patch

import test_audio_pipeline
import test_persistence

from manga_tts import PipelineConfig, PipelineRouter, schemas
from manga_tts.cli import apply_review, review_document
from manga_tts.persistence import InMemoryArtifactStore, ProjectPersistence


class ApprovalAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_audio_pipeline.PipelineTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.router = self.fixture.router

    def test_local_approval_records_identity_and_subjects(self):
        self.fixture.approve()
        records = self.router.project.approval_audit
        self.assertEqual([r.subject_id for r in records], ['cast', 'scene_001'])
        self.assertTrue(all(r.actor.kind == 'local' for r in records))
        self.assertEqual(records[-1].fingerprint, self.router.project.approvals['scene_001'])
        self.assertTrue(all(r.operation_id and r.reviewed_revision and r.timestamp for r in records))

    def test_verified_actor_retries_do_not_duplicate_audit(self):
        self.fixture.approve()
        context = schemas.ApprovalContext(actor=schemas.ApprovalActor(
            kind='firebase', uid='admin-uid', project_id='test-project'),
            operation_id='op-1', reviewed_revision='reviewed-1')
        router = PipelineRouter(self.router._config, approval_context=context)
        router.load_project()
        router.approve_cast()
        router.approve_cast()
        records = [r for r in router.project.approval_audit if r.operation_id == 'op-1']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].actor.uid, 'admin-uid')
        self.assertEqual(records[0].reviewed_revision, 'reviewed-1')

    def test_failed_save_publishes_neither_approval_nor_audit(self):
        before = schemas.dump(self.router.project)
        command = review_document(self.router.project, 'cast')
        for appearance in command['command']['appearances']:
            appearance['speaker_id'] = 'A'
        with (
            patch('manga_tts.storage.save_project', side_effect=OSError('disk failed')),
            self.assertRaises(schemas.WorkflowError),
        ):
            apply_review(self.router, command, approve=True)
        self.assertEqual(schemas.dump(self.router.project), before)

    def test_pointer_failure_retains_old_revision_and_history(self):
        revisions = test_persistence.FailingRevisionStore()
        persistence = ProjectPersistence(InMemoryArtifactStore(), revisions)
        writer = persistence.acquire("audit-project", "audit-writer")
        self.addCleanup(writer.release)
        router = PipelineRouter(self.router._config, persistence=writer)
        router.load_project()
        before = schemas.dump(router.project)
        pointer = revisions.current("audit-project")
        command = review_document(router.project, "cast")
        for appearance in command["command"]["appearances"]:
            appearance["speaker_id"] = "A"
        revisions.fail_next_commit = True
        with self.assertRaises(schemas.WorkflowError):
            apply_review(router, command, approve=True)
        self.assertEqual(revisions.current("audit-project"), pointer)
        self.assertEqual(schemas.dump(router.project), before)
        reloaded = PipelineRouter(self.router._config, persistence=writer)
        self.assertEqual(schemas.dump(reloaded.load_project()), before)

    def test_history_survives_bundle_restore_and_draft_save(self):
        self.fixture.approve()
        before = self.router.project.approval_audit
        draft = review_document(self.router.project, "script", "scene_001")
        apply_review(self.router, draft)
        self.assertEqual(self.router.project.approval_audit, before)
        bundle = self.router.bundle_project()
        restored = PipelineRouter(PipelineConfig(workspace=self.fixture.root / "audit-restored"))
        restored.restore_project(bundle)
        self.assertEqual(restored.project.approval_audit, before)

    def test_metadata_cannot_replace_audit_or_actor(self):
        self.fixture.approve()
        before = schemas.dump(self.router.project)
        for metadata in ({"approval_audit": []}, {"actor": {"kind": "firebase", "uid": "forged"}}):
            with self.assertRaises(schemas.WorkflowError):
                self.router.update_metadata(metadata)
        self.assertEqual(schemas.dump(self.router.project), before)

    def test_old_project_has_empty_history_without_changing_serialization(self):
        data = schemas.dump(self.router.project)
        data.pop('approval_audit', None)
        old = schemas.Project.model_validate(data)
        self.assertEqual(old.approval_audit, [])
        self.assertNotIn('approval_audit', schemas.dump(old))
