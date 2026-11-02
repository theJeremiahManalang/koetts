"""Cloud selection must never turn incomplete remote configuration into local state."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from manga_worker.cloud import CloudSettings, CloudStores
from manga_worker.shared import SharedService


class CloudSettingsTests(unittest.TestCase):
    def test_explicit_configuration_and_canonical_namespace(self):
        environment = dict(FIREBASE_PROJECT_ID="demo-hosted", FIRESTORE_DATABASE_ID="named",
                           MANGA_CLOUD_DATASET="pilot", MANGA_ARTIFACT_BUCKET="demo-artifacts",
                           MANGA_ARTIFACT_NAMESPACE="pilot/artifacts")
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(CloudSettings.from_environment().namespace, "pilot/artifacts")
        for key in environment:
            with self.subTest(key=key), patch.dict(os.environ, {**environment, key: ""}, clear=True):
                with self.assertRaises(ValueError):
                    CloudSettings.from_environment()
        for namespace in ("/pilot", "pilot/", "pilot//objects", "../objects", "pilot/../objects", " pilot"):
            with self.subTest(namespace=namespace), patch.dict(os.environ, {
                    **environment, "MANGA_ARTIFACT_NAMESPACE": namespace}, clear=True):
                with self.assertRaises(ValueError):
                    CloudSettings.from_environment()

    def test_cloud_selection_uses_remote_metadata_and_artifacts(self):
        metadata, artifacts = Mock(), Mock()
        stores = CloudStores(Mock(), metadata, artifacts, Mock(), Mock())
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
                "MANGA_SHARED_BACKEND": "cloud"}, clear=True):
            root = Path(temporary)
            with patch("manga_worker.cloud.CloudSettings.from_environment") as settings:
                with patch("manga_worker.cloud.cloud_stores", return_value=stores) as build:
                    service = SharedService(root)
                    self.assertIs(service.store.metadata, metadata)
                    self.assertIs(service.store.artifacts, artifacts)
                    build.assert_called_once_with(settings.return_value, root / "shared-cache")
            self.assertEqual(list(root.iterdir()), [])

    def test_cloud_failure_never_creates_sqlite_or_local_artifact_identity(self):
        for failure in (ValueError("Missing configuration"), OSError("Unavailable")):
            with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
                    "MANGA_SHARED_BACKEND": "cloud"}, clear=True):
                root = Path(temporary)
                with patch("manga_worker.cloud.CloudSettings.from_environment", side_effect=failure):
                    with self.assertRaises(type(failure)):
                        SharedService(root)
                self.assertEqual(list(root.iterdir()), [])
