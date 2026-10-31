output "project_id" {
  value       = var.project_id
  description = "Existing project targeted by these new hosted resources."
}

output "firestore_database_id" {
  value       = var.firestore_database_id
  description = "Runtime-only reference to the existing named Firestore database; Terraform does not manage it."
}

output "cloud_dataset" {
  value       = var.cloud_dataset
  description = "Operator-selected clean hosted collection namespace."
}

output "artifact_bucket" {
  value       = google_storage_bucket.artifacts.name
  description = "New private GCS artifact bucket."
}

output "artifact_bucket_location" {
  value       = google_storage_bucket.artifacts.location
  description = "Artifact bucket location, configured independently of the service region."
}

output "artifact_namespace" {
  value       = var.artifact_namespace
  description = "Canonical artifact object prefix."
}

output "api_service_url" {
  value       = google_cloud_run_v2_service.api.uri
  description = "Actual API URL; compare with canonical_api_url before enabling traffic."
}

output "canonical_api_url" {
  value       = var.canonical_api_url
  description = "Explicit URL used for API service-token validation and OIDC audiences."
}

output "billing_account_id" {
  value       = var.billing_account_id
  description = "Cloud Billing account identifier configured for notification validation."
}

output "billing_budget_id" {
  value       = element(split("/", google_billing_budget.hosted.name), 3)
  description = "Generated budget ID expected in Cloud Billing notification attributes. Verify live payload identity."
}

output "billing_subscription" {
  value       = "projects/${var.project_id}/subscriptions/${google_pubsub_subscription.billing.name}"
  description = "Exact fully qualified Pub/Sub subscription expected by the private API."
}

output "service_account_emails" {
  value = {
    api          = google_service_account.api.email
    magi         = google_service_account.magi.email
    pipeline     = google_service_account.pipeline.email
    scheduler    = google_service_account.scheduler.email
    pubsub       = google_service_account.pubsub_push.email
    gc           = google_service_account.gc.email
    operator     = google_service_account.operator.email
    gc_scheduler = google_service_account.gc_scheduler.email
  }
  description = "Dedicated workload identities created by this configuration."
}

output "gc_job_name" {
  value       = google_cloud_run_v2_job.gc.name
  description = "Reference-aware collection job; its Scheduler is paused until rollout acceptance."
}
