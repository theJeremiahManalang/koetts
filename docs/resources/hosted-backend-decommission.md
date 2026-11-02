# Hosted backend decommission guide

This is a future teardown procedure. It has not been run. Finish hosted manual
acceptance first. It removes backend compute and identities while retaining the
Firebase App Hosting frontend and the stored project/audio data.

## Keep

- Firebase project `koetts-9bf7f`, App Hosting backend `koetts` in `us-east4`,
  Firebase Auth users/admin claims, and the Firebase App Hosting runtime identity.
- Firestore database `koetts-default` in `nam5`, including project/revision
  records and the metadata needed to find retained project/audio objects.
- Bucket `koetts-9bf7f-hosted-artifacts-us-central1` and only the generated
  project/audio objects plus transitive references needed to reopen them.
  Inventory exact object generations first. Remove unrelated uploads only through
  reference-aware cleanup after checking retained project references; do not
  remove objects by age or prefix alone.
- The Cloud Billing budget and email notifications. Keep
  `hosted-audio-signing-key` while retained audio still uses its signed playback
  path. Keep private Terraform state and inputs for recovery.

The application budget ledger and operation history are not generated media.
Keep them until hosted operations and billing are reconciled; never delete or
reinitialize them to release reservations.

## Order of work

1. After manual testing ends, set `MANGA_MAINTENANCE_MODE` and
   `MANGA_FRONTEND_ONLY` to `"1"` in `apps/web/apphosting.yaml`. Prepare and
   deploy the Firebase frontend using [App Hosting instructions](../../resources/APP_HOSTING.md).
   Verify the public URL displays **Hosted studio is offline** before stopping
   backend services. This change affects the frontend only; it does not stop
   Cloud Run jobs. Deploy from the prepared source after reviewing its staged
   config:

   ```bash
   python tools/prepare_apphosting_source.py --output /tmp/koetts-apphosting-decommission
   (
     cd /tmp/koetts-apphosting-decommission
     firebase deploy --only apphosting:koetts --project koetts-9bf7f
   )
   ```
2. Keep the ledger active and the coordinator running while already accepted
   queued/running work drains. Confirm there are no running Cloud Run executions
   and no queued or running operations. Resolve uncertain operations only after
   execution absence or termination is proven. If one cannot be safely resolved,
   preserve its record/reservation and stop here. Once the queue is clear, pause
   production with the audited operator CLI. Set the explicit cloud configuration
   in the same shell before running the CLI:

   ```bash
   export FIREBASE_PROJECT_ID=koetts-9bf7f
   export FIRESTORE_DATABASE_ID=koetts-default
   export MANGA_CLOUD_DATASET=hosted_pilot_20261101
   export MANGA_ARTIFACT_BUCKET=koetts-9bf7f-hosted-artifacts-us-central1
   export MANGA_ARTIFACT_NAMESPACE=hosted/pilot_20261101
   uv run --locked python -m manga_worker.cloud_operator pause \
     --actor YOUR_GOOGLE_ACCOUNT \
     --reason "Hosted backend decommission" \
     --evidence YOUR_DECOMMISSION_RECORD \
     --execute
   ```

3. With the ledger paused, pause both schedulers, then remove the Eventarc trigger
   after the coordinator has drained accepted dispatch signals:

   ```bash
   gcloud scheduler jobs pause hosted-coordinator --location=us-central1 --project=koetts-9bf7f
   gcloud scheduler jobs pause hosted-artifact-gc --location=us-central1 --project=koetts-9bf7f
   gcloud eventarc triggers delete hosted-operation-dispatch --location=nam5 --project=koetts-9bf7f
   ```

4. Preserve the Cloud Billing budget and its default email recipients. The
   current budget also publishes notifications to `koetts-hosted-billing`, whose
   push subscription targets the API. In Cloud Billing, remove that Pub/Sub
   destination only after verifying email notifications remain enabled. Then
   delete `koetts-hosted-billing-push` and `koetts-hosted-billing`; verify a later
   budget alert still reaches the billing recipients.
5. Retire only these backend compute resources after the drain checks pass:

   | Resource | Name |
   | --- | --- |
   | Cloud Run service | `koetts-api` in `us-central1` |
   | Legacy Cloud Run service | `koetts-s3-api` in `us-east4`, after confirming no remaining client depends on it |
   | Cloud Run jobs | `koetts-magi`, `koetts-pipeline`, `koetts-artifact-gc` in `us-central1` |
   | Cloud Scheduler jobs | `hosted-coordinator`, `hosted-artifact-gc` in `us-central1` |
   | Eventarc trigger | `hosted-operation-dispatch` in `nam5` |
   | Artifact Registry repository | `koetts-hosted` in `us-central1`, after confirming no other consumer needs its images |

   Cloud Run deletion protection is enabled on the service and jobs. First set
   `deletion_protection = false` on the API, Magi, pipeline, and GC resource blocks
   in `infra/hosted/main.tf`. Apply a fresh plan containing only those four
   protection updates; do not combine that change with deletion. Then remove the
   listed compute resources one at a time and verify each result:

   ```bash
   gcloud run services delete koetts-api --region=us-central1 --project=koetts-9bf7f
   gcloud run services delete koetts-s3-api --region=us-east4 --project=koetts-9bf7f
   gcloud run jobs delete koetts-magi --region=us-central1 --project=koetts-9bf7f
   gcloud run jobs delete koetts-pipeline --region=us-central1 --project=koetts-9bf7f
   gcloud run jobs delete koetts-artifact-gc --region=us-central1 --project=koetts-9bf7f
   gcloud scheduler jobs delete hosted-coordinator --location=us-central1 --project=koetts-9bf7f
   gcloud scheduler jobs delete hosted-artifact-gc --location=us-central1 --project=koetts-9bf7f
   gcloud artifacts repositories delete koetts-hosted --location=us-central1 --project=koetts-9bf7f
   ```

   Remove only the hosted API/job/scheduler service accounts, their
   `hosted*` custom IAM roles and bindings, and the API/job grants on the artifact
   managed folder and named Firestore database. The task-owned accounts are
   `hosted-api-runtime`, `hosted-magi-job`, `hosted-pipeline-job`,
   `hosted-scheduler`, `hosted-gc-scheduler`, `hosted-billing-push`,
   `hosted-operation-events`, `hosted-operator`, and `hosted-artifact-gc`. The
   custom roles are `hostedFirestoreRuntime`, `hostedFirestoreGc`,
   `hostedFirestoreOperator`, `hostedArtifactRuntime`, `hostedArtifactGc`,
   `hostedFirebaseUserReader`, `hostedGeminiInference`, `hostedJobCoordinator`,
   `hostedCoordinatorOperationReader`, `hostedGcRecoveryJob`,
   `hostedGcRecoveryOperationReader`, and `hostedGcExecutionReader`. Remove their
   bindings before deleting each identity or role. Do not remove the Firebase App
   Hosting identity, its Secret Manager access, the billing budget, Firestore
   database, artifact bucket, or project-wide Firebase/Firestore/Storage APIs.
   The legacy service uses `koetts-s3-api@koetts-9bf7f.iam.gserviceaccount.com`;
   remove it only after verifying that no remaining resource uses that identity.
   Its revision currently has 100% configured traffic, which does not prove actual
   request volume. Review Cloud Logging and client configuration before retiring it.
6. Review cleanup evidence and preserve the private Terraform state. The
   `infra/hosted` root also manages the retained bucket, Secret Manager secret,
   budget, Firestore indexes, and Firebase-related grants. **Do not run a broad
   `terraform destroy`.** Use a fresh saved, targeted plan and inspect every
   deletion; stop if it includes the bucket/folder, database data, secret,
   budget, App Hosting backend, or Firebase Auth. Record the exact plan and apply
   output in the private decommission record. Do not apply this active-hosting
   configuration again while decommissioned; it will recreate backend resources.

## Verify retained state

- Firebase App Hosting backend `koetts` still serves the maintenance page and
  Firebase Auth remains available.
- The named Firestore database and artifact bucket still exist. Verify retained
  project records and exact project/audio object generations against the saved
  inventory; do not use a bucket-wide delete or recreate operation.
- Both Cloud Run services and all jobs, both schedulers, the Eventarc trigger, and
  the backend-only billing push subscription are absent. Billing email alerts still
  reach their recipients.
- Production stays paused. Keep the saved Terraform plan/apply output, budget
  status, operation ledger, object inventory, and rollback targets together.

To restore processing later, redeploy from a fresh reviewed Terraform plan,
verify the private API and job permissions, return the frontend flags to `"0"`,
and run the hosted acceptance checklist before resuming production or schedules.
