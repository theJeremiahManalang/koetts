"""Cast propagation preserves reviewed wording and never guesses missing links."""
import copy
import unittest

from manga_tts import schemas, script
import test_audio_pipeline as fixtures


class CastSpeakerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PipelineTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.project = schemas.dump(self.fixture.router.project)
        self.appearance = self.project["appearances"][0]
        self.appearance["speaker_id"] = "A"
        self.linked = next(s for s in self.project["sources"] if s["magi_links"])
        self.turn = next(t for t in self.project["scenes"][0]["turns"] if self.linked["source_id"] in t["source_ids"])

    def test_clear_links_fill_sources_and_turns_without_rebuilding(self):
        self.turn["text"] = "Keep this manually edited wording"
        self.turn["emotion"] = "surprised"
        script.sync_cast_speakers(self.project)
        self.assertEqual(self.linked["speaker_id"], "A")
        self.assertEqual(self.turn["speaker_id"], "A")
        self.assertEqual(self.turn["text"], "Keep this manually edited wording")
        self.assertEqual(self.turn["emotion"], "surprised")
        self.assertTrue(all(s["speaker_id"] == "UNKNOWN" for s in self.project["sources"] if not s["magi_links"]))

    def test_saving_cast_persists_the_dialogue_handoff(self):
        from manga_tts.cli import review_document
        from manga_tts.storage import save_project, read_json
        self.turn["text"] = "Retain the edited script"
        save_project(self.project, self.fixture.router.root)
        self.fixture.router.load_project()
        command = review_document(self.fixture.router.project, "cast")["command"]
        command["approve"] = True
        self.fixture.router.apply_cast_review(schemas.CastReview.model_validate(command))
        saved = read_json(self.fixture.router.root / "project.json")
        source = next(s for s in saved["sources"] if s["source_id"] == self.linked["source_id"])
        turn = next(t for t in saved["scenes"][0]["turns"] if self.linked["source_id"] in t["source_ids"])
        self.assertEqual(source["speaker_id"], "A")
        self.assertEqual(turn["speaker_id"], "A")
        self.assertEqual(turn["text"], "Retain the edited script")

    def test_reassignment_updates_automatic_speakers_but_keeps_manual_choices(self):
        script.sync_cast_speakers(self.project)
        self.appearance["speaker_id"] = "B"
        script.sync_cast_speakers(self.project)
        self.assertEqual(self.linked["speaker_id"], "B")
        self.assertEqual(self.turn["speaker_id"], "B")
        self.turn.update(speaker_id="C", speaker_origin="manual")
        self.appearance["speaker_id"] = "A"
        script.sync_cast_speakers(self.project)
        self.assertEqual(self.linked["speaker_id"], "A")
        self.assertEqual(self.turn["speaker_id"], "C")
        self.linked.update(speaker_id="UNKNOWN", speaker_origin="manual")
        script.sync_cast_speakers(self.project)
        self.assertEqual(self.linked["speaker_id"], "UNKNOWN")

    def test_rejected_and_conflicting_links_remain_unresolved(self):
        script.sync_cast_speakers(self.project)
        self.appearance["rejected"] = True
        script.sync_cast_speakers(self.project)
        self.assertEqual(self.linked["speaker_id"], "UNKNOWN")
        self.assertEqual(self.turn["speaker_id"], "UNKNOWN")
        self.appearance["rejected"] = False
        other = {**copy.deepcopy(self.appearance), "char_id": "other", "speaker_id": "B"}
        self.project["appearances"].append(other)
        self.linked["magi_links"].append({"char_id": "other"})
        script.sync_cast_speakers(self.project)
        self.assertEqual(self.linked["speaker_id"], "UNKNOWN")

    def test_legacy_known_speakers_are_preserved(self):
        self.linked["speaker_id"] = "B"
        self.turn["speaker_id"] = "C"
        script.sync_cast_speakers(self.project)
        self.assertEqual(self.linked["speaker_id"], "B")
        self.assertEqual(self.turn["speaker_id"], "C")

    def test_batch_sync_happens_after_all_legacy_scene_edits(self):
        # Emulate two scenes submitted by a client still showing UNKNOWN speakers.
        first = self.project["scenes"][0]
        self.project["scenes"].append({"scene_id": "second", "title": "Second", "context": "", "turns": []})
        second_source = next(s for s in self.project["sources"] if s != self.linked)
        second_source["scene_id"] = "second"
        second_source["magi_links"] = copy.deepcopy(self.linked["magi_links"])
        script.rebuild_turns(self.project)
        script.approve_cast(self.project)
        # Reset to the old persisted state before the fix, preserving approved Cast.
        for source in self.project["sources"]:
            source["speaker_id"] = "UNKNOWN"
            source.pop("speaker_origin", None)
            source.pop("cast_speaker_id", None)
        for scene in self.project["scenes"]:
            for turn in scene["turns"]:
                turn["speaker_id"] = "UNKNOWN"
                turn.pop("speaker_origin", None)
                turn.pop("cast_speaker_id", None)
        from manga_tts.storage import save_project
        save_project(self.project, self.fixture.router.root)
        self.fixture.router.load_project()
        fields = tuple(k for k in schemas.TurnEdit.model_fields if k != "speaker_origin")
        command = {"scenes": [{"scene_id": s["scene_id"], "title": s["title"], "context": s["context"], "turns": [{k: t[k] for k in fields} for t in s["turns"]], "approve": False} for s in self.project["scenes"]]}
        result = schemas.dump(self.fixture.router.apply_scene_reviews(schemas.SceneBatchReview.model_validate(command)))
        for scene in result["scenes"]:
            for turn in scene["turns"]:
                if second_source["source_id"] in turn["source_ids"] or self.linked["source_id"] in turn["source_ids"]:
                    self.assertEqual(turn["speaker_id"], "A")


if __name__ == "__main__":
    unittest.main()
