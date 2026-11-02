"""Injected GCS behavior tests; no cloud SDK or network required."""
import hashlib
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path

from manga_tts.persistence import ArtifactRef
from manga_worker.cloud_artifacts import GCSArtifactStore, GCSSharedArtifacts


class PreconditionFailed(Exception):
    code = 412


class FakeBlob:
    def __init__(self, bucket, name, generation=None):
        self.bucket = bucket
        self.name = name
        self._requested_generation = generation
        self.generation = generation

    def upload_from_filename(self, filename, if_generation_match=None):
        if if_generation_match != 0:
            raise AssertionError("uploads must be create only")
        if self.name in self.bucket.objects:
            raise PreconditionFailed()
        generation = str(self.bucket.next_generation)
        self.bucket.next_generation += 1
        self.bucket.objects[self.name] = (generation, Path(filename).read_bytes())
        self.generation = int(generation)

    def reload(self):
        self.generation = int(self.bucket.objects[self.name][0])

    def download_to_filename(self, filename):
        current_generation, content = self.bucket.objects.get(self.name, (None, None))
        if content is None:
            raise FileNotFoundError(self.name)
        if self._requested_generation is not None and str(self._requested_generation) != current_generation:
            raise FileNotFoundError("generation missing")
        Path(filename).write_bytes(content)
        if self.generation is None:
            self.generation = int(current_generation)


class FakeBucket:
    name = "unit-test-bucket"

    def __init__(self):
        self.objects = {}
        self.next_generation = 1
        self.requests = []

    def blob(self, name, generation=None):
        self.requests.append((name, generation))
        return FakeBlob(self, name, generation)


class FakeReferences:
    def __init__(self):
        self.values = {}

    def get(self, checksum):
        if checksum not in self.values:
            raise FileNotFoundError(checksum)
        return self.values[checksum]

    def put(self, ref):
        prior = self.values.setdefault(ref.sha256, ref)
        if prior != ref:
            raise ValueError("reference conflict")


class GCSArtifactStoreTests(unittest.TestCase):
    def setUp(self):
        self.bucket = FakeBucket()
        self.store = GCSArtifactStore(self.bucket, "shared/audio")

    def test_cached_bytes_do_not_bypass_durable_reference_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            references = FakeReferences()
            shared = GCSSharedArtifacts(self.store, references, Path(directory) / "cache")
            source = Path(directory) / "source"
            source.write_bytes(b"audio")
            checksum = shared.store(source)
            self.assertEqual(shared.verified(checksum).read_bytes(), b"audio")
            references.values[checksum] = ArtifactRef("foreign/" + checksum, "1", checksum)
            with self.assertRaises(ValueError):
                shared.verified(checksum)

    def test_create_only_upload_and_content_dedup_verify_existing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.write_bytes(b"chapter audio")
            first = self.store.put_file(source)
            second = GCSArtifactStore(self.bucket, "shared/audio").put_file(source)
            self.assertEqual(first, second)
            self.assertEqual(first.generation, "1")
            self.assertEqual(self.bucket.objects[first.object_id][1], b"chapter audio")
            self.assertEqual(sum(1 for name, generation in self.bucket.requests if generation is None), 3)
            self.assertTrue(all(generation is None or generation == 1 for _, generation in self.bucket.requests))

    def test_existing_object_metadata_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.write_bytes(b"valid")
            good = self.store.put_file(source)
            self.bucket.objects[good.object_id] = (good.generation, b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum"):
                self.store.put_file(source)

    def test_upload_is_staged_before_caller_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.write_bytes(b"frozen")
            reference = self.store.put_file(source)
            source.write_bytes(b"changed")
            self.assertEqual(reference.sha256, hashlib.sha256(b"frozen").hexdigest())
            self.assertEqual(self.bucket.objects[reference.object_id][1], b"frozen")

    def test_copy_uses_exact_generation_and_atomically_preserves_destination_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.write_bytes(b"audio")
            ref = self.store.put_file(source)
            destination = Path(directory) / "result"
            destination.write_bytes(b"old")
            bad = ArtifactRef(ref.object_id, "99", ref.sha256)
            with self.assertRaises(FileNotFoundError):
                self.store.copy_to(bad, destination)
            self.assertEqual(destination.read_bytes(), b"old")
            self.store.copy_to(ref, destination)
            self.assertEqual(destination.read_bytes(), b"audio")
            self.assertIn((ref.object_id, 1), self.bucket.requests)

    def test_copy_checksum_mismatch_preserves_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.write_bytes(b"audio")
            ref = self.store.put_file(source)
            self.bucket.objects[ref.object_id] = (ref.generation, b"corrupt")
            destination = Path(directory) / "result"
            destination.write_bytes(b"old")
            with self.assertRaisesRegex(ValueError, "checksum"):
                self.store.copy_to(ref, destination)
            self.assertEqual(destination.read_bytes(), b"old")

    def test_missing_upload_generation_fails_closed(self):
        class MissingGenerationBlob(FakeBlob):
            def upload_from_filename(self, filename, if_generation_match=None):
                super().upload_from_filename(filename, if_generation_match)
                self.generation = None

        class MissingGenerationBucket(FakeBucket):
            def blob(self, name, generation=None):
                if generation is None:
                    return MissingGenerationBlob(self, name, generation)
                return FakeBlob(self, name, generation)

        with tempfile.TemporaryDirectory() as directory:
            store = GCSArtifactStore(MissingGenerationBucket(), "shared/audio")
            source = Path(directory) / "source"
            source.write_bytes(b"audio")
            with self.assertRaisesRegex(ValueError, "generation"):
                store.put_file(source)

    def test_restart_recovers_durable_reference_and_cache_is_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.write_bytes(b"audio")
            refs = FakeReferences()
            shared = GCSSharedArtifacts(self.store, refs, root / "cache")
            checksum = shared.store(source)
            restarted = GCSSharedArtifacts(GCSArtifactStore(self.bucket, "shared/audio"), refs, root / "cache")
            path = restarted.verified(checksum)
            self.assertEqual(path.read_bytes(), b"audio")
            path.write_bytes(b"tampered")
            self.assertEqual(restarted.verified(checksum).read_bytes(), b"audio")

    def test_shared_reference_conflicts_and_invalid_refs_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.write_bytes(b"audio")
            refs = FakeReferences()
            shared = GCSSharedArtifacts(self.store, refs, root / "cache")
            checksum = shared.store(source)
            actual = refs.values[checksum]
            refs.values[checksum] = ArtifactRef("other/path", actual.generation, checksum)
            with self.assertRaisesRegex(ValueError, "outside this namespace"):
                shared.verified(checksum)
            for bad in (
                ArtifactRef("shared/audio/" + checksum, "0", checksum),
                ArtifactRef("shared/other/" + checksum, "1", checksum),
                SimpleNamespace(object_id="shared/audio/" + checksum, generation="1", sha256="x" * 64),
            ):
                with self.assertRaises(ValueError):
                    self.store.copy_to(bad, root / "destination")
            with self.assertRaises(ValueError):
                GCSArtifactStore(self.bucket, "../escape")

    def test_artifact_store_identity_is_stable_and_namespace_scoped(self):
        self.assertEqual(self.store.artifact_store_id, GCSArtifactStore(self.bucket, "shared/audio").artifact_store_id)
        self.assertNotEqual(self.store.artifact_store_id, GCSArtifactStore(self.bucket, "shared/audio/other").artifact_store_id)


if __name__ == "__main__":
    unittest.main()
