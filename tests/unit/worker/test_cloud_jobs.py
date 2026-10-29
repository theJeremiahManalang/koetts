from __future__ import annotations

from dataclasses import replace
import unittest
from manga_tts.operations import Operation, OperationClaim

from manga_worker.cloud_jobs import CloudJobDispatcher, CloudJobError, CloudJobOutcomeUnknown, CloudRunJobs


PROJECT, REGION = "manga-prod", "us-east4"
JOB = f"projects/{PROJECT}/locations/{REGION}/jobs/magi-job"
EXEC = JOB + "/executions/run-1"


class Response:
    def __init__(self, value, status_code=200):
        self.value = value
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.value


class Session:
    def __init__(self, *, post=None, get=None):
        self.posts = []
        self.gets = []
        self.post_values = list(post or [])
        self.get_values = list(get or [])

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.post_values.pop(0)

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return self.get_values.pop(0)


def jobs(session, **kwargs):
    return CloudRunJobs(
        PROJECT,
        REGION,
        {"magi": "magi-job", "pipeline": "pipeline-job"},
        session=session,
        sleep=lambda _: None,
        **kwargs,
    )


class CloudRunJobsTests(unittest.TestCase):
    def test_start_overrides_single_task_timeout_and_polls_lro_response(self):
        session = Session(
            post=[Response({"name": "projects/manga-prod/locations/us-east4/operations/op-1"})],
            get=[Response({"done": True, "response": {"name": EXEC}})],
        )
        claim = OperationClaim("opid-1", 4)

        self.assertEqual(jobs(session).start(claim, "magi"), EXEC)
        url, request = session.posts[0]
        self.assertTrue(url.endswith("/jobs/magi-job:run"))
        overrides = request["json"]["overrides"]
        self.assertEqual((overrides["taskCount"], overrides["timeout"]), (1, "1800s"))
        self.assertEqual(
            overrides["containerOverrides"][0]["env"],
            [
                {"name": "MANGA_OPERATION_ID", "value": "opid-1"},
                {"name": "MANGA_OPERATION_FENCE", "value": "4"},
            ],
        )
        self.assertTrue(session.gets[0][0].endswith("/operations/op-1"))

    def test_pending_lro_is_unknown_and_start_not_repeated(self):
        session = Session(
            post=[Response({"name": "projects/manga-prod/locations/us-east4/operations/op-1"})],
            get=[Response({"done": False}), Response({"done": False})],
        )
        with self.assertRaises(CloudJobOutcomeUnknown):
            jobs(session, poll_attempts=2).start(OperationClaim("op", 1), "magi")
        self.assertEqual(len(session.posts), 1)

    def test_run_job_execution_metadata_is_returned_without_waiting_for_completion(self):
        session = Session(
            post=[
                Response(
                    {
                        "name": "projects/manga-prod/locations/us-east4/operations/op-1",
                        "metadata": {"@type": "type.googleapis.com/google.cloud.run.v2.Execution", "name": EXEC},
                        "done": False,
                    }
                )
            ]
        )
        self.assertEqual(jobs(session).start(OperationClaim("op", 1), "magi"), EXEC)
        self.assertEqual(session.gets, [])

    def test_execution_metadata_returned_from_pending_operation_poll(self):
        session = Session(
            post=[Response({"name": "projects/manga-prod/locations/us-east4/operations/op-1", "done": False})],
            get=[
                Response(
                    {
                        "name": "projects/manga-prod/locations/us-east4/operations/op-1",
                        "metadata": {"@type": "type.googleapis.com/google.cloud.run.v2.Execution", "name": EXEC},
                        "done": False,
                    }
                )
            ],
        )
        self.assertEqual(jobs(session, poll_attempts=2).start(OperationClaim("op", 1), "magi"), EXEC)
        self.assertEqual(len(session.gets), 1)

    def test_status_classifies_from_execution_state(self):
        cases = [
            (
                {"completionTime": "now", "conditions": [{"type": "Completed", "state": "CONDITION_SUCCEEDED"}]},
                "succeeded",
            ),
            ({"completionTime": "now", "conditions": [{"type": "Completed", "state": "CONDITION_FAILED"}]}, "failed"),
            ({"completionTime": "now", "cancelledCount": 1}, "cancelled"),
            (
                {
                    "conditions": [
                        {
                            "type": "Completed",
                            "state": "CONDITION_RECONCILING",
                            "executionReason": "EXECUTION_CANCELLED",
                        }
                    ]
                },
                "active",
            ),
            ({"conditions": [{"type": "Completed", "state": "CONDITION_FAILED"}]}, "active"),
            ({"completionTime": "now", "conditions": []}, "unknown"),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                self.assertEqual(jobs(Session(get=[Response(body)])).status(EXEC), expected)

    def test_status_rejects_foreign_execution(self):
        with self.assertRaises(ValueError):
            jobs(Session()).status("projects/other/locations/us-east4/jobs/magi-job/executions/run")

    def test_find_executions_matches_exact_operation_and_fence_and_paginates(self):
        matching = {
            "name": EXEC,
            "template": {
                "containers": [
                    {
                        "env": [
                            {"name": "MANGA_OPERATION_ID", "value": "op-1"},
                            {"name": "MANGA_OPERATION_FENCE", "value": "9"},
                        ]
                    }
                ]
            },
        }
        wrong_fence = {
            "name": JOB + "/executions/run-2",
            "template": {
                "containers": [
                    {
                        "env": [
                            {"name": "MANGA_OPERATION_ID", "value": "op-1"},
                            {"name": "MANGA_OPERATION_FENCE", "value": "8"},
                        ]
                    }
                ]
            },
        }
        session = Session(
            get=[Response({"executions": [wrong_fence], "nextPageToken": "next"}), Response({"executions": [matching]})]
        )
        self.assertEqual(jobs(session).find_executions(OperationClaim("op-1", 9), "magi"), [EXEC])
        self.assertEqual(session.gets[1][1]["params"]["pageToken"], "next")

    def test_find_executions_fails_closed_when_pagination_incomplete(self):
        session = Session(get=[Response({"executions": [], "nextPageToken": "more"})])
        with self.assertRaisesRegex(CloudJobError, "absence is unproven"):
            jobs(session, max_pages=1).find_executions(OperationClaim("op", 1), "magi")

    def test_find_executions_does_not_assume_unpublished_nested_template_shape(self):
        execution = {
            "name": EXEC,
            "template": {
                "template": {
                    "containers": [
                        {
                            "env": [
                                {"name": "MANGA_OPERATION_ID", "value": "op"},
                                {"name": "MANGA_OPERATION_FENCE", "value": "1"},
                            ]
                        }
                    ]
                }
            },
        }
        session = Session(get=[Response({"executions": [execution]})])
        self.assertEqual(jobs(session).find_executions(OperationClaim("op", 1), "magi"), [])


def operation(status="running", attempt=1, fence=1):
    return Operation(
        operation_id="op",
        idempotency_key="idem",
        request_fingerprint="fingerprint",
        project_id="project",
        stage="magi",
        payload={},
        revision=None,
        source_fingerprint="source",
        configuration_fingerprint="config",
        status=status,
        attempt_count=attempt,
        fence=fence,
        lease_expires_at=0,
        worker_pid=None,
        worker_created_at=None,
        provider_outcome_pending=False,
        progress={},
        checkpoint=None,
        result=None,
        failure_code=None,
        message="working",
        created_at=0,
        updated_at=0,
        attempt_started_at=0,
    )


class Store:
    def __init__(self, *, dispatch_operation=None):
        self.op = dispatch_operation or operation()
        self.dispatch_state = "pending"
        self.execution = None
        self.worker_registered = False
        self.pending_provider = False
        self.calls = []
        self.candidates = []
        self.timeout_candidates = []
        self.recovered_unsubmitted = 0

    def claim_next(self):
        self.calls.append("claim")
        return None

    def begin_dispatch(self, claim):
        self.calls.append("begin")
        if self.op.status != "running" or self.dispatch_state != "pending":
            return False
        self.dispatch_state = "submitting"
        return True

    def get(self, _):
        return replace(self.op, provider_outcome_pending=self.pending_provider)

    def attempt(self, _):
        return {
            "dispatch_state": self.dispatch_state,
            "execution_name": self.execution,
            "worker_registered": self.worker_registered,
        }

    def record_execution(self, _, name):
        self.calls.append("record")
        self.execution = name
        self.dispatch_state = "started"

    def mark_uncertain(self, _, message):
        self.calls.append("uncertain")
        self.op = replace(self.op, status="reconciliation_required", message=message)

    def confirm_execution_stopped(self, _, name):
        self.calls.append("stopped:" + name)

    def worker_stopped(self, _):
        self.calls.append("worker_stopped")

    def hold_live_worker(self, _):
        self.calls.append("hold")

    def expired(self):
        return self.candidates

    def timed_out(self):
        return self.timeout_candidates

    def reconciliation_required(self):
        return [self.op] if self.op.status == "reconciliation_required" else []

    def recover_unsubmitted(self, _):
        self.recovered_unsubmitted += 1


class FakeJobs:
    def __init__(self, *, start_error=False, state="active", found=None, states=None):
        self.start_error = start_error
        self.state = state
        self.states = list(states or [])
        self.found = found or []
        self.starts = 0
        self.cancelled = 0
        self.find_calls = 0

    def start(self, claim, stage):
        self.starts += 1
        if self.start_error:
            raise TimeoutError("response lost")
        return EXEC

    def find_executions(self, claim, stage):
        self.find_calls += 1
        return self.found

    def status(self, name):
        return self.states.pop(0) if self.states else self.state

    def cancel(self, name):
        self.cancelled += 1


class CloudJobDispatcherTests(unittest.TestCase):
    def test_dispatch_intent_cas_prevents_duplicate_start_after_uncertain_response(self):
        store = Store()
        pending_claims = [OperationClaim("op", 1)]

        def claim_next():
            return pending_claims.pop(0) if pending_claims else None

        store.claim_next = claim_next
        fake = FakeJobs(start_error=True)
        dispatcher = CloudJobDispatcher(store, fake)
        dispatcher.tick()
        dispatcher.tick()
        self.assertEqual(fake.starts, 1)
        self.assertEqual(store.calls.count("begin"), 1)
        self.assertIn("uncertain", store.calls)

    def test_claim_left_pending_before_dispatch_is_started_once_on_next_tick(self):
        store = Store()
        store.candidates = [store.op]
        fake = FakeJobs()
        dispatcher = CloudJobDispatcher(store, fake)
        dispatcher.tick()
        dispatcher.tick()
        self.assertEqual(fake.starts, 1)
        self.assertEqual(store.dispatch_state, "started")

    def test_timed_out_unsubmitted_claim_uses_atomic_recovery_without_cloud_calls(self):
        store = Store()
        store.timeout_candidates = [store.op]
        fake = FakeJobs()
        CloudJobDispatcher(store, fake).tick()
        self.assertEqual(store.recovered_unsubmitted, 1)
        self.assertEqual(fake.starts, 0)
        self.assertEqual(fake.find_calls, 0)

    def test_timed_out_submitting_claim_is_reconciled_not_lease_released(self):
        store = Store()
        store.dispatch_state = "submitting"
        store.timeout_candidates = [store.op]
        fake = FakeJobs(found=[])
        CloudJobDispatcher(store, fake).tick()
        self.assertEqual(store.recovered_unsubmitted, 0)
        self.assertEqual(fake.starts, 0)
        self.assertEqual(fake.find_calls, 1)
        self.assertNotIn("hold", store.calls)

    def test_stale_start_error_after_completion_does_not_mark_uncertain(self):
        store = Store()
        pending_claims = [OperationClaim("op", 1)]

        def claim_next():
            return pending_claims.pop(0) if pending_claims else None

        store.claim_next = claim_next

        class CompletedJobs(FakeJobs):
            def start(self, claim, stage):
                store.op = replace(store.op, status="complete")
                raise TimeoutError("late response")

        counts = CloudJobDispatcher(store, CompletedJobs()).tick()
        self.assertEqual(counts["uncertain"], 0)
        self.assertEqual(store.op.status, "complete")
        self.assertNotIn("uncertain", store.calls)

    def test_reconcile_active_execution_keeps_slot_and_renews_lease(self):
        store = Store()
        store.execution = EXEC
        store.candidates = [store.op]
        dispatcher = CloudJobDispatcher(store, FakeJobs(state="active"))
        dispatcher.tick()
        self.assertIn("hold", store.calls)
        self.assertNotIn("worker_stopped", store.calls)

    def test_reconcile_terminal_provider_uncertainty_confirms_stop_but_keeps_slot(self):
        store = Store()
        store.execution = EXEC
        store.pending_provider = True
        store.candidates = [store.op]
        dispatcher = CloudJobDispatcher(store, FakeJobs(state="succeeded"))
        dispatcher.tick()
        self.assertIn(f"stopped:{EXEC}", store.calls)
        self.assertIn("worker_stopped", store.calls)

    def test_terminal_path_recovers_project_before_releasing_slot(self):
        store = Store()
        store.execution = EXEC
        store.candidates = [store.op]
        order = []
        store.worker_stopped = lambda _: order.append("worker_stopped")
        dispatcher = CloudJobDispatcher(
            store,
            FakeJobs(state="failed"),
            recover_project=lambda operation, claim: order.append("recover_project") or True,
        )
        dispatcher.tick()
        self.assertEqual(order, ["recover_project", "worker_stopped"])

    def test_failed_project_recovery_keeps_slot_uncertain(self):
        store = Store()
        store.execution = EXEC
        store.candidates = [store.op]
        dispatcher = CloudJobDispatcher(
            store,
            FakeJobs(state="failed"),
            recover_project=lambda operation, claim: False,
        )
        dispatcher.tick()
        self.assertIn("uncertain", store.calls)
        self.assertNotIn("worker_stopped", store.calls)

    def test_reconcile_unknown_execution_marks_uncertain(self):
        store = Store()
        store.execution = EXEC
        store.candidates = [store.op]
        dispatcher = CloudJobDispatcher(store, FakeJobs(state="unknown"))
        dispatcher.tick()
        self.assertIn("uncertain", store.calls)
        self.assertNotIn("worker_stopped", store.calls)

    def test_reconcile_dispatch_without_unique_execution_marks_uncertain(self):
        store = Store()
        store.dispatch_state = "submitting"
        store.candidates = [store.op]
        dispatcher = CloudJobDispatcher(store, FakeJobs(found=[]))
        dispatcher.tick()
        self.assertIn("uncertain", store.calls)

    def test_uncertain_operations_are_reconciled_again_without_re_marking(self):
        store = Store(dispatch_operation=operation(status="reconciliation_required"))
        store.dispatch_state = "submitting"
        store.execution = EXEC
        dispatcher = CloudJobDispatcher(store, FakeJobs(state="active"))
        dispatcher.tick()
        self.assertIn("hold", store.calls)
        self.assertNotIn("uncertain", store.calls)

    def test_uncertain_dispatch_without_execution_stays_reserved(self):
        store = Store(dispatch_operation=operation(status="reconciliation_required"))
        store.dispatch_state = "submitting"
        dispatcher = CloudJobDispatcher(store, FakeJobs(found=[]))
        dispatcher.tick()
        self.assertNotIn("uncertain", store.calls)
        self.assertNotIn("worker_stopped", store.calls)

    def test_timeout_cancels_then_rechecks_before_releasing_worker(self):
        store = Store()
        store.execution = EXEC
        store.candidates = [store.op]
        store.timeout_candidates = [store.op]
        fake = FakeJobs(states=["active", "failed"])
        CloudJobDispatcher(store, fake).tick()
        self.assertEqual(fake.cancelled, 1)
        self.assertIn(f"stopped:{EXEC}", store.calls)
        self.assertIn("worker_stopped", store.calls)


if __name__ == "__main__":
    unittest.main()
