"""Finite Cloud Run Jobs dispatch and execution reconciliation.

This adapter deliberately treats an ambiguous jobs.run outcome as uncertain. The
durable operation store, not Cloud Run or Scheduler retries, owns retry policy.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Literal
from urllib.parse import quote

from manga_tts.operations import Operation, OperationClaim

CloudExecutionStatus = Literal["active", "succeeded", "failed", "cancelled", "unknown"]


class CloudJobError(RuntimeError):
    """Cloud Run returned invalid or incomplete evidence for a job operation."""


class CloudJobOutcomeUnknown(CloudJobError):
    """A start may have been accepted, but no execution identity was confirmed."""


class CloudRunJobs:
    """Small Cloud Run v2 REST adapter with injectable AuthorizedSession-like client."""

    def __init__(
        self,
        project: str,
        region: str,
        jobs: Mapping[str, str],
        *,
        session=None,
        poll_attempts: int = 5,
        poll_interval: float = 1.0,
        page_size: int = 100,
        max_pages: int = 10,
        sleep=time.sleep,
    ):
        if not project or not region or set(jobs) != {"magi", "pipeline"}:
            raise ValueError("Explicit project, region, and magi/pipeline Cloud Run Jobs are required")
        if any(not isinstance(name, str) or not name or "/" in name for name in jobs.values()):
            raise ValueError("Cloud Run job names must be explicit resource identifiers")
        if poll_attempts < 1 or page_size < 1 or max_pages < 1 or poll_interval < 0:
            raise ValueError("Cloud Run polling and pagination bounds must be positive")
        self.project = project
        self.region = region
        self.jobs = dict(jobs)
        self._session = session
        self.poll_attempts = poll_attempts
        self.poll_interval = poll_interval
        self.page_size = page_size
        self.max_pages = max_pages
        self._sleep = sleep

    @property
    def _base(self) -> str:
        return f"https://run.googleapis.com/v2/projects/{quote(self.project, safe='')}/locations/{quote(self.region, safe='')}"

    def _http(self):
        if self._session is None:
            try:
                import google.auth
                from google.auth.transport.requests import AuthorizedSession
            except ImportError as exc:  # pragma: no cover - dependency present only in hosted extra
                raise RuntimeError("Install the worker api extra to use Cloud Run Jobs") from exc
            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            self._session = AuthorizedSession(credentials)
        return self._session

    @staticmethod
    def _json(response) -> dict:
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise CloudJobError("Cloud Run returned a malformed JSON object")
        return value

    def _execution_name(self, value: dict) -> str | None:
        """Read only a full execution resource name belonging to this configured job."""
        expected_job = f"projects/{self.project}/locations/{self.region}/jobs/"
        candidate = value.get("name")
        if isinstance(candidate, str) and candidate.startswith(expected_job) and "/executions/" in candidate:
            if candidate.split("/executions/", 1)[0] in {
                f"projects/{self.project}/locations/{self.region}/jobs/{name}" for name in self.jobs.values()
            }:
                return candidate
        metadata = value.get("metadata")
        if isinstance(metadata, dict):
            # jobs.run metadata is google.cloud.run.v2.Execution, not a
            # wrapper whose field must be named "execution".
            found = metadata.get("name")
            if isinstance(found, str) and self._execution_name({"name": found}):
                return found
            for key in ("execution", "executionName"):
                found = metadata.get(key)
                if isinstance(found, str) and self._execution_name({"name": found}):
                    return found
                if isinstance(found, dict) and isinstance(found.get("name"), str):
                    if self._execution_name({"name": found["name"]}):
                        return found["name"]
        response = value.get("response")
        if isinstance(response, dict):
            found = self._execution_name(response)
            if found:
                return found
        return None

    def _request_execution_name(self, operation: dict) -> str | None:
        name = operation.get("name")
        prefix = f"projects/{self.project}/locations/{self.region}/operations/"
        if not isinstance(name, str) or not name.startswith(prefix) or not name[len(prefix) :]:
            direct = self._execution_name(operation)
            if direct:
                return direct
            raise CloudJobOutcomeUnknown("Cloud Run start response has no valid operation resource name")
        url = f"{self._base}/operations/{quote(name[len(prefix) :], safe='')}"
        current = operation
        for index in range(self.poll_attempts):
            if current.get("done") is True and current.get("error"):
                raise CloudJobError("Cloud Run rejected the job execution")
            execution = self._execution_name(current)
            if execution:
                return execution
            if current.get("done") is True:
                raise CloudJobOutcomeUnknown("Cloud Run operation completed without an execution resource name")
            if index + 1 < self.poll_attempts:
                if self.poll_interval:
                    self._sleep(self.poll_interval)
                current = self._json(self._http().get(url, timeout=15))
        raise CloudJobOutcomeUnknown("Cloud Run start operation is still pending; reconcile before retrying")

    def start(self, claim: OperationClaim, stage: str) -> str:
        if stage not in self.jobs:
            raise ValueError("Unsupported Cloud Run operation stage")
        job = self._job_resource(stage)
        url = f"{self._base}/jobs/{quote(self.jobs[stage], safe='')}:run"
        body = {
            "overrides": {
                "taskCount": 1,
                "timeout": "1800s",
                "containerOverrides": [
                    {
                        "env": [
                            {"name": "MANGA_OPERATION_ID", "value": claim.operation_id},
                            {"name": "MANGA_OPERATION_FENCE", "value": str(claim.fence)},
                        ]
                    }
                ],
            }
        }
        operation = self._json(self._http().post(url, json=body, timeout=30))
        execution = self._request_execution_name(operation)
        if not execution.startswith(job + "/executions/"):
            raise CloudJobOutcomeUnknown("Cloud Run returned an execution for the wrong configured job")
        return execution

    def _job_resource(self, stage: str) -> str:
        return f"projects/{self.project}/locations/{self.region}/jobs/{self.jobs[stage]}"

    def _validate_execution(self, execution_name: str) -> str:
        if not isinstance(execution_name, str):
            raise ValueError("Execution resource name is required")
        for job_name in self.jobs.values():
            prefix = f"projects/{self.project}/locations/{self.region}/jobs/{job_name}/executions/"
            suffix = execution_name[len(prefix) :] if execution_name.startswith(prefix) else ""
            if suffix and "/" not in suffix:
                return execution_name
        raise ValueError("Execution does not belong to a configured Cloud Run Job")

    def status(self, execution_name: str) -> CloudExecutionStatus:
        execution_name = self._validate_execution(execution_name)
        response = self._http().get(f"https://run.googleapis.com/v2/{execution_name}", timeout=15)
        if getattr(response, "status_code", None) == 404:
            return "unknown"
        value = self._json(response)
        completion = value.get("completionTime")
        conditions = value.get("conditions")
        if not isinstance(conditions, list):
            conditions = []
        completed = next((c for c in conditions if isinstance(c, dict) and c.get("type") == "Completed"), None)
        if completion:
            reason = completed.get("executionReason", completed.get("reason")) if completed else None
            if value.get("cancelledCount", 0) > 0 or reason in {"EXECUTION_CANCELLED", "CANCELLED"}:
                return "cancelled"
            if completed and completed.get("state") == "CONDITION_SUCCEEDED":
                return "succeeded"
            if completed and completed.get("state") == "CONDITION_FAILED":
                return "failed"
            if value.get("failedCount", 0) > 0:
                return "failed"
            if value.get("succeededCount", 0) == value.get("taskCount") == 1:
                return "succeeded"
            return "unknown"
        if value.get("reconciling") is True or not completion:
            return "active"
        return "unknown"

    def cancel(self, execution_name: str) -> None:
        execution_name = self._validate_execution(execution_name)
        self._json(self._http().post(f"https://run.googleapis.com/v2/{execution_name}:cancel", json={}, timeout=15))

    @staticmethod
    def _env(execution: dict) -> dict[str, str]:
        template = execution.get("template")
        if not isinstance(template, dict):
            return {}
        containers = template.get("containers")
        if not isinstance(containers, list):
            return {}
        result = {}
        for container in containers:
            if not isinstance(container, dict) or not isinstance(container.get("env"), list):
                continue
            for item in container["env"]:
                if isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("value"), str):
                    result[item["name"]] = item["value"]
        return result

    def find_executions(self, claim: OperationClaim, stage: str) -> list[str]:
        if stage not in self.jobs:
            raise ValueError("Unsupported Cloud Run operation stage")
        url = f"{self._base}/jobs/{quote(self.jobs[stage], safe='')}/executions"
        token = None
        matches = []
        for page in range(self.max_pages):
            params = {"pageSize": self.page_size}
            if token:
                params["pageToken"] = token
            value = self._json(self._http().get(url, params=params, timeout=15))
            executions = value.get("executions")
            if not isinstance(executions, list):
                raise CloudJobError("Cloud Run execution list response is incomplete")
            for execution in executions:
                if not isinstance(execution, dict):
                    continue
                env = self._env(execution)
                name = execution.get("name")
                if (
                    env.get("MANGA_OPERATION_ID") == claim.operation_id
                    and env.get("MANGA_OPERATION_FENCE") == str(claim.fence)
                    and isinstance(name, str)
                ):
                    matches.append(self._validate_execution(name))
            token = value.get("nextPageToken")
            if not token:
                return matches
            if not isinstance(token, str):
                raise CloudJobError("Cloud Run returned an invalid page token")
        raise CloudJobError("Cloud Run execution listing exceeded the page bound; absence is unproven")


class CloudJobDispatcher:
    """Dispatch queued claims once and reconcile only from durable store intent."""

    def __init__(self, store, jobs: CloudRunJobs, *, recover_project=None):
        self.store = store
        self.jobs = jobs
        self.recover_project = recover_project

    def tick(self) -> dict[str, int]:
        counts = {"dispatched": 0, "reconciled": 0, "uncertain": 0}
        claim = self.store.claim_next()
        if claim is not None:
            try:
                self._dispatch(claim)
                counts["dispatched"] += 1
            except Exception as exc:
                if self._uncertain(claim, f"Cloud Run dispatch outcome needs reconciliation: {type(exc).__name__}."):
                    counts["uncertain"] += 1
        timed_out_operations = self.store.timed_out()
        timed_out = {op.operation_id for op in timed_out_operations}
        uncertain = getattr(self.store, "reconciliation_required", lambda: [])()
        candidates = {op.operation_id: op for op in (*self.store.expired(), *timed_out_operations, *uncertain)}
        for operation in candidates.values():
            claim = OperationClaim(operation.operation_id, operation.fence)
            try:
                if self._reconcile(claim, operation, operation.operation_id in timed_out):
                    counts["reconciled"] += 1
            except Exception as exc:
                if self._uncertain(claim, f"Cloud Run execution outcome needs reconciliation: {type(exc).__name__}."):
                    counts["uncertain"] += 1
        return counts

    def _dispatch(self, claim: OperationClaim) -> None:
        if not self.store.begin_dispatch(claim):
            return
        operation = self.store.get(claim.operation_id)
        try:
            name = self.jobs.start(claim, operation.stage)
        except Exception:
            # start() may have reached Cloud Run. Never invoke it twice for this claim.
            raise
        self.store.record_execution(claim, name)

    def _uncertain(self, claim: OperationClaim, message: str) -> bool:
        try:
            current = self.store.get(claim.operation_id)
            if current.fence == claim.fence and current.status == "running":
                self.store.mark_uncertain(claim, message)
                return True
        except Exception:
            # Preserve the original failure. Store outages also must not trigger a retry.
            pass
        return False

    def _reconcile(self, claim: OperationClaim, operation: Operation, timed_out: bool) -> bool:
        attempt = self.store.attempt(claim)
        name = attempt.get("execution_name")
        if not name:
            unsubmitted = attempt.get("dispatch_state") == "pending" and not attempt.get("worker_registered")
            if timed_out and unsubmitted:
                recover_unsubmitted = getattr(self.store, "recover_unsubmitted", None)
                if callable(recover_unsubmitted):
                    recover_unsubmitted(claim)
                else:
                    self._uncertain(claim, "Expired unsubmitted Cloud Run intent cannot be safely recovered.")
                return True
            if not timed_out and operation.status == "running" and unsubmitted:
                # The durable CAS has not begun, so jobs.run is proven not to have
                # been invoked. Claim submitting before making the one safe call.
                self._dispatch(claim)
                return True
            names = self.jobs.find_executions(claim, operation.stage)
            if len(names) != 1:
                self._uncertain(claim, "Cloud Run dispatch has no uniquely confirmed execution.")
                return True
            name = names[0]
            self.store.record_execution(claim, name)
        state = self.jobs.status(name)
        if state == "active" and timed_out:
            self.jobs.cancel(name)
            state = self.jobs.status(name)
        if state == "active":
            self.store.hold_live_worker(claim)
            return True
        if state in {"unknown", None}:
            self._uncertain(claim, "Cloud Run execution status is not authoritative.")
            return True
        self.store.confirm_execution_stopped(claim, name)
        current = self.store.get(claim.operation_id)
        if current.status != "complete":
            if self.recover_project is not None and not self.recover_project(current, claim):
                self._uncertain(claim, "Cloud Run stopped, but project ownership recovery was not confirmed.")
                return True
            self.store.worker_stopped(claim)
        return True
