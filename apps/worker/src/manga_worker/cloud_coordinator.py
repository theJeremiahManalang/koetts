"""Private scheduled dispatch and confirmed-stop project recovery."""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from manga_tts.storage import read_json

from .cloud import CloudSettings, cloud_stores
from .cloud_budget import CloudBudgetLedger
from .cloud_jobs import CloudJobDispatcher, CloudRunJobs
from .cloud_operations import FirestoreOperationStore


def project_recovery(stores, operations):
    """Return a callback used only after the dispatcher confirms execution stopped."""
    def recover(operation, claim):
        expected_owner = f"hosted-{operation.operation_id}-{claim.fence}"
        owner = stores.revisions.active_owner(operation.project_id)
        if owner is not None:
            if owner.owner_id != expected_owner:
                return False
            stores.revisions.recover(owner, worker_stopped=True)
        # Verify the accepted manifest before retrying. A lost progress event must
        # not prevent explicit retry from reusing already accepted segment audio.
        with tempfile.TemporaryDirectory(prefix="manga-cloud-recover-") as directory:
            with stores.persistence.acquire(operation.project_id, "reconcile-" + uuid.uuid4().hex) as writer:
                workspace = Path(directory) / "project"
                current = writer.load(workspace)
                if current is not None:
                    checkpoint = dict(operation.checkpoint or {})
                    checkpoint.update(project_hash=current.project_hash, revision_id=current.revision_id,
                                      operation_id=operation.operation_id, recovered=True)
                    baseline = checkpoint.get("provider_base_revision_id")
                    if (operation.payload.get("action") == "plan" and baseline
                            and baseline != current.revision_id and read_json(workspace / "project.json").get("proposal")):
                        checkpoint["planning_complete"] = True
                    operations.reconcile_checkpoint(claim, checkpoint)
        return True
    return recover


def coordinator_from_environment(*, expected_project: str):
    """Construct explicit cloud services; never start a local worker or inference client."""
    from google.cloud import firestore

    settings = CloudSettings.from_environment()
    if settings.project != expected_project:
        raise ValueError("Cloud storage project must match the authenticated API project")
    client = firestore.Client(project=settings.project, database=settings.database)
    stores = cloud_stores(settings, Path(tempfile.gettempdir()) / "manga-cloud-coordinator", firestore_client=client)
    budget = CloudBudgetLedger(client, settings.dataset, stores.artifacts.artifact_store_id)
    operations = FirestoreOperationStore(client, settings.dataset, stores.artifacts.artifact_store_id, budget=budget)
    jobs = CloudRunJobs(settings.project, os.environ.get("MANGA_CLOUD_REGION", "us-east4"), {
        "magi": os.environ.get("MANGA_MAGI_JOB", ""),
        "pipeline": os.environ.get("MANGA_PIPELINE_JOB", ""),
    })
    return CloudJobDispatcher(operations, jobs, recover_project=project_recovery(stores, operations))
