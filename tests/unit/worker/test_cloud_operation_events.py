"""Firestore listener contracts without remote services."""
from datetime import UTC, datetime
import unittest
from unittest.mock import Mock, patch

from manga_worker.cloud_operations import FirestoreOperationStore


class OperationEventsTests(unittest.TestCase):
    def test_transaction_result_and_sdk_snapshot_lists(self):
        store = object.__new__(FirestoreOperationStore)
        store.client = Mock()
        ref = Mock()
        snapshot = Mock(update_time=datetime(2026, 11, 2, tzinfo=UTC))
        ref.get.return_value = snapshot
        operation = Mock()
        operation.public.return_value = {"status": "running"}
        callback = Mock()
        with patch.object(store, "_operation_ref", return_value=ref), \
             patch.object(store, "_binding", return_value=True), \
             patch.object(store, "_operation", return_value=operation), \
             patch("google.cloud.firestore.transactional", side_effect=lambda function: function):
            initial, version, watcher = store.watch_public("a" * 32, callback)
            self.assertEqual(initial, {"status": "running"})
            self.assertEqual(version, snapshot.update_time)
            self.assertIs(watcher, ref.on_snapshot.return_value)
            changed = ref.on_snapshot.call_args.args[0]
            changed([snapshot], [], snapshot.update_time)
            callback.assert_called_once_with(initial, version)
            callback.reset_mock()
            changed([], [], snapshot.update_time)
            callback.assert_called_once_with(None, None)
