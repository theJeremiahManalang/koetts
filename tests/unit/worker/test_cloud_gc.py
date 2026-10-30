"""Small, in-memory checks for collector input validation and reference walking."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from manga_tts.persistence import ArtifactRef
from manga_worker.cloud_gc import ArtifactCollection, ReferenceAwareCollector


class CloudGcUnitTests(unittest.TestCase):
    def test_execution_identity_requires_cloud_run_execution_resource(self):
        for valid in (
            "projects/demo-project/locations/us-central1/jobs/gc-job/executions/run-1",
        ):
            self.assertEqual(ArtifactCollection._execution(valid), valid)

        for invalid in (None, "", "projects/demo/jobs/gc", "projects/demo/locations/US/jobs/gc/executions/run"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                ArtifactCollection._execution(invalid)

    def test_reference_walker_finds_refs_nested_in_operation_payload(self):
        collector = object.__new__(ReferenceAwareCollector)
        ref = ArtifactRef("pilot/audio/" + "a" * 64, "7", "a" * 64)
        collector.stores = SimpleNamespace(artifacts=SimpleNamespace(validate_ref=lambda item: None))

        found = list(collector._references({
            "payload": {"uploads": [{"object_id": ref.object_id, "generation": ref.generation,
                                      "sha256": ref.sha256}]},
            "unrelated": "value",
        }))

        self.assertEqual(found, [ref])

    def test_collector_rejects_naive_clock_before_acquiring_barrier(self):
        collector = ReferenceAwareCollector(SimpleNamespace(), SimpleNamespace(),
                                            clock=lambda: datetime(2026, 1, 1))
        with self.assertRaisesRegex(ValueError, "aware clock"):
            collector.collect("projects/demo/locations/us-central1/jobs/gc/executions/run")


if __name__ == "__main__":
    unittest.main()
