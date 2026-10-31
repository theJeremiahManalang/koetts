locals {
  enabled_services = toset([
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudbilling.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "identitytoolkit.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
  ])

  service_permissions = {
    (data.google_service_account.frontend.unique_id) = ["identity", "readiness", "snapshot", "asset", "upload", "shared", "enqueue", "poll", "production-status", "production-control"]
    (google_service_account.scheduler.unique_id)     = ["coordinate"]
    (google_service_account.pubsub_push.unique_id)   = ["budget-report"]
    (google_service_account.operator.unique_id)      = ["identity", "readiness", "production-status", "production-control"]
  }

  common_cloud_env = {
    FIREBASE_PROJECT_ID      = var.project_id
    FIRESTORE_DATABASE_ID    = var.firestore_database_id
    MANGA_CLOUD_DATASET      = var.cloud_dataset
    MANGA_ARTIFACT_BUCKET    = google_storage_bucket.artifacts.name
    MANGA_ARTIFACT_NAMESPACE = var.artifact_namespace
    MANGA_CLOUD_REGION       = var.region
    MANGA_MAGI_JOB           = var.magi_job_name
    MANGA_PIPELINE_JOB       = var.pipeline_job_name
    MANGA_SHARED_BACKEND     = "cloud"
    MANGA_DATA_ROOT          = "/tmp/manga-cloud-runtime"
  }
}

resource "google_project_service" "enabled" {
  for_each           = local.enabled_services
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

data "google_service_account" "frontend" {
  project    = var.project_id
  account_id = split("@", var.frontend_service_account_email)[0]
}

resource "google_service_account" "api" {
  project      = var.project_id
  account_id   = "hosted-api-runtime"
  display_name = "Hosted API runtime"
}

resource "google_service_account" "magi" {
  project      = var.project_id
  account_id   = "hosted-magi-job"
  display_name = "Hosted CPU inference job"
}

resource "google_service_account" "pipeline" {
  project      = var.project_id
  account_id   = "hosted-pipeline-job"
  display_name = "Hosted pipeline job"
}

resource "google_service_account" "scheduler" {
  project      = var.project_id
  account_id   = "hosted-scheduler"
  display_name = "Hosted coordinator scheduler caller"
}

resource "google_service_account" "gc_scheduler" {
  project      = var.project_id
  account_id   = "hosted-gc-scheduler"
  display_name = "Hosted artifact collection scheduler caller"
}

resource "google_service_account" "pubsub_push" {
  project      = var.project_id
  account_id   = "hosted-billing-push"
  display_name = "Hosted billing notification push caller"
}

resource "google_service_account" "operator" {
  project      = var.project_id
  account_id   = "hosted-operator"
  display_name = "Hosted production operator caller"
}

resource "google_service_account" "gc" {
  project      = var.project_id
  account_id   = "hosted-artifact-gc"
  display_name = "Hosted reference-aware artifact collector"
}

resource "google_project_iam_custom_role" "firestore_runtime" {
  project     = var.project_id
  role_id     = "hostedFirestoreRuntime"
  title       = "Hosted Firestore runtime data access"
  description = "Document operations required by hosted services; no database administration."
  permissions = [
    "datastore.databases.get",
    "datastore.entities.create",
    "datastore.entities.delete",
    "datastore.entities.get",
    "datastore.entities.list",
    "datastore.entities.update",
  ]
}

resource "google_project_iam_custom_role" "firestore_gc" {
  project     = var.project_id
  role_id     = "hostedFirestoreGc"
  title       = "Hosted Firestore artifact collection"
  description = "Read references and maintain fenced GC runs, collection barriers, and stale upload metadata. Firestore IAM cannot scope these permissions to collections."
  permissions = [
    "datastore.databases.get",
    "datastore.entities.create",
    "datastore.entities.delete",
    "datastore.entities.get",
    "datastore.entities.list",
    "datastore.entities.update",
  ]
}

resource "google_project_iam_custom_role" "firestore_operator" {
  project     = var.project_id
  role_id     = "hostedFirestoreOperator"
  title       = "Hosted Firestore budget operator"
  description = "Read and update hosted operation and budget ledgers for the audited operator CLI."
  permissions = [
    "datastore.databases.get",
    "datastore.entities.create",
    "datastore.entities.delete",
    "datastore.entities.get",
    "datastore.entities.list",
    "datastore.entities.update",
  ]
}

resource "google_project_iam_custom_role" "artifact_runtime" {
  project     = var.project_id
  role_id     = "hostedArtifactRuntime"
  title       = "Hosted artifact object runtime"
  description = "Create and read objects under the dedicated artifact managed folder."
  permissions = [
    "storage.objects.create",
    "storage.objects.get",
    "storage.objects.list",
  ]
}

resource "google_project_iam_custom_role" "artifact_gc" {
  project     = var.project_id
  role_id     = "hostedArtifactGc"
  title       = "Hosted reference-aware artifact collection"
  description = "List, read, and delete objects after application reference checks."
  permissions = [
    "storage.objects.delete",
    "storage.objects.get",
    "storage.objects.list",
  ]
}

resource "google_project_iam_custom_role" "firebase_user_reader" {
  project     = var.project_id
  role_id     = "hostedFirebaseUserReader"
  title       = "Hosted Firebase user verification"
  description = "Read Firebase Auth users for revoked-token validation only."
  permissions = ["firebaseauth.users.get"]
}

resource "google_project_iam_custom_role" "coordinator" {
  project     = var.project_id
  role_id     = "hostedJobCoordinator"
  title       = "Hosted Cloud Run job coordinator"
  description = "Run configured jobs with operation/fence overrides and reconcile executions; bound separately to each configured job."
  permissions = [
    "run.executions.cancel",
    "run.executions.get",
    "run.executions.list",
    "run.jobs.get",
    "run.jobs.runWithOverrides",
  ]
}

resource "google_project_iam_custom_role" "coordinator_operation_reader" {
  project     = var.project_id
  role_id     = "hostedCoordinatorOperationReader"
  title       = "Hosted coordinator operation reader"
  description = "Poll Cloud Run long-running job-start operations."
  permissions = ["run.operations.get"]
}

resource "google_project_iam_custom_role" "gc_recovery_job" {
  project     = var.project_id
  role_id     = "hostedGcRecoveryJob"
  title       = "Hosted GC recovery job operator"
  description = "Start only the GC job with an explicit recovery owner and inspect its executions. Bind at the GC job resource."
  permissions = [
    "run.executions.get",
    "run.jobs.get",
    "run.jobs.runWithOverrides",
  ]
}

resource "google_project_iam_custom_role" "gc_recovery_operation_reader" {
  project     = var.project_id
  role_id     = "hostedGcRecoveryOperationReader"
  title       = "Hosted GC recovery operation reader"
  description = "Read Cloud Run long-running job-start operations while confirming GC recovery execution identity."
  permissions = ["run.operations.get"]
}

resource "google_project_iam_custom_role" "gc_execution_reader" {
  project     = var.project_id
  role_id     = "hostedGcExecutionReader"
  title       = "Hosted artifact collector execution reader"
  description = "Read executions of the configured GC job so recovery can prove the prior collector stopped."
  permissions = ["run.executions.get"]
}

resource "google_project_iam_member" "runtime_firestore" {
  for_each = {
    api      = google_service_account.api.email
    magi     = google_service_account.magi.email
    pipeline = google_service_account.pipeline.email
  }
  project = var.project_id
  role    = google_project_iam_custom_role.firestore_runtime.name
  member  = "serviceAccount:${each.value}"
  condition {
    title       = "hosted_named_database_only"
    description = "Limit runtime document access to the existing named Firestore database."
    expression  = "resource.type == \"firestore.googleapis.com/Database\" && resource.name == \"projects/${var.project_id}/databases/${var.firestore_database_id}\""
  }
}

resource "google_project_iam_member" "api_firebase_auth" {
  project = var.project_id
  role    = google_project_iam_custom_role.firebase_user_reader.name
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "coordinator_operations" {
  project = var.project_id
  role    = google_project_iam_custom_role.coordinator_operation_reader.name
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "gc_firestore" {
  project = var.project_id
  role    = google_project_iam_custom_role.firestore_gc.name
  member  = "serviceAccount:${google_service_account.gc.email}"
  condition {
    title       = "hosted_named_database_only"
    description = "Limit reference reads to the existing named Firestore database."
    expression  = "resource.type == \"firestore.googleapis.com/Database\" && resource.name == \"projects/${var.project_id}/databases/${var.firestore_database_id}\""
  }
}

resource "google_project_iam_member" "operator_firestore" {
  project = var.project_id
  role    = google_project_iam_custom_role.firestore_operator.name
  member  = "serviceAccount:${google_service_account.operator.email}"
  condition {
    title       = "hosted_named_database_only"
    description = "Limit operator ledger writes to the existing named Firestore database."
    expression  = "resource.type == \"firestore.googleapis.com/Database\" && resource.name == \"projects/${var.project_id}/databases/${var.firestore_database_id}\""
  }
}

resource "google_storage_bucket" "artifacts" {
  project                     = var.project_id
  name                        = var.artifact_bucket_name
  location                    = var.artifact_bucket_location
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  deletion_policy             = "PREVENT"

  soft_delete_policy {
    retention_duration_seconds = var.enable_gcs_soft_delete ? 604800 : 0
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.enabled]
}

resource "google_storage_managed_folder" "artifacts" {
  bucket = google_storage_bucket.artifacts.name
  name   = "${var.artifact_namespace}/"
}

resource "google_storage_managed_folder_iam_member" "artifact_runtime" {
  for_each = {
    api      = google_service_account.api.email
    magi     = google_service_account.magi.email
    pipeline = google_service_account.pipeline.email
  }
  bucket         = google_storage_managed_folder.artifacts.bucket
  managed_folder = google_storage_managed_folder.artifacts.name
  role           = google_project_iam_custom_role.artifact_runtime.name
  member         = "serviceAccount:${each.value}"
}

resource "google_storage_managed_folder_iam_member" "artifact_gc" {
  bucket         = google_storage_managed_folder.artifacts.bucket
  managed_folder = google_storage_managed_folder.artifacts.name
  role           = google_project_iam_custom_role.artifact_gc.name
  member         = "serviceAccount:${google_service_account.gc.email}"
}

resource "google_secret_manager_secret" "audio_signing" {
  project   = var.project_id
  secret_id = "hosted-audio-signing-key"
  replication {
    auto {}
  }
  deletion_protection = true
  depends_on          = [google_project_service.enabled]
}

resource "google_secret_manager_secret" "provider" {
  project   = var.project_id
  secret_id = "hosted-provider-key"
  replication {
    auto {}
  }
  deletion_protection = true
  depends_on          = [google_project_service.enabled]
}

resource "google_secret_manager_secret_iam_member" "frontend_audio_signing" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.audio_signing.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_service_account.frontend.email}"
}

resource "google_secret_manager_secret_iam_member" "pipeline_provider" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.provider.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_cloud_run_v2_service" "api" {
  project             = var.project_id
  name                = var.api_service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true

  template {
    service_account                  = google_service_account.api.email
    timeout                          = "300s"
    max_instance_request_concurrency = 40
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
    containers {
      image = var.api_image
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }
      env {
        name  = "S3_API_MODE"
        value = "cloud"
      }
      env {
        name  = "S3_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "S3_SERVICE_AUDIENCE"
        value = var.canonical_api_url
      }
      env {
        name  = "S3_SERVICE_PERMISSIONS"
        value = jsonencode(local.service_permissions)
      }
      dynamic "env" {
        for_each = local.common_cloud_env
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name  = "MANGA_BILLING_ACCOUNT_ID"
        value = var.billing_account_id
      }
      env {
        name  = "MANGA_BILLING_BUDGET_ID"
        value = element(split("/", google_billing_budget.hosted.name), 3)
      }
      env {
        name  = "MANGA_BILLING_SUBSCRIPTION"
        value = "projects/${var.project_id}/subscriptions/${google_pubsub_subscription.billing.name}"
      }
    }
  }

  depends_on = [
    google_project_service.enabled,
    google_project_iam_member.runtime_firestore,
    google_project_iam_member.api_firebase_auth,
    google_storage_managed_folder_iam_member.artifact_runtime,
    google_cloud_run_v2_job_iam_member.coordinator_magi,
    google_cloud_run_v2_job_iam_member.coordinator_pipeline,
    google_project_iam_member.coordinator_operations,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "frontend_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_service_account.frontend.email}"
}

resource "google_cloud_run_v2_service_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_run_v2_service_iam_member" "billing_push_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_push.email}"
}

resource "google_cloud_run_v2_service_iam_member" "operator_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.operator.email}"
}

resource "google_cloud_run_v2_job" "magi" {
  project             = var.project_id
  name                = var.magi_job_name
  location            = var.region
  deletion_protection = true
  template {
    task_count  = 1
    parallelism = 1
    template {
      max_retries     = 0
      timeout         = "1800s"
      service_account = google_service_account.magi.email
      containers {
        image = var.magi_image
        resources {
          limits = { cpu = "4", memory = "8Gi" }
        }
        dynamic "env" {
          for_each = local.common_cloud_env
          content {
            name  = env.key
            value = env.value
          }
        }
        env {
          name  = "CLOUD_RUN_PROJECT"
          value = var.project_id
        }
        env {
          name  = "CLOUD_RUN_LOCATION"
          value = var.region
        }
      }
    }
  }
  depends_on = [
    google_project_service.enabled,
    google_project_iam_member.runtime_firestore,
    google_storage_managed_folder_iam_member.artifact_runtime,
  ]
}

resource "google_cloud_run_v2_job_iam_member" "coordinator_magi" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.magi.name
  role     = google_project_iam_custom_role.coordinator.name
  member   = "serviceAccount:${google_service_account.api.email}"
}

resource "google_cloud_run_v2_job" "pipeline" {
  project             = var.project_id
  name                = var.pipeline_job_name
  location            = var.region
  deletion_protection = true
  template {
    task_count  = 1
    parallelism = 1
    template {
      max_retries     = 0
      timeout         = "1800s"
      service_account = google_service_account.pipeline.email
      containers {
        image = var.pipeline_image
        resources {
          limits = { cpu = "2", memory = "4Gi" }
        }
        dynamic "env" {
          for_each = local.common_cloud_env
          content {
            name  = env.key
            value = env.value
          }
        }
        env {
          name  = "CLOUD_RUN_PROJECT"
          value = var.project_id
        }
        env {
          name  = "CLOUD_RUN_LOCATION"
          value = var.region
        }
        env {
          name = "GEMINI_API_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.provider.secret_id
              version = var.provider_secret_version
            }
          }
        }
      }
    }
  }
  depends_on = [
    google_project_service.enabled,
    google_project_iam_member.runtime_firestore,
    google_storage_managed_folder_iam_member.artifact_runtime,
    google_secret_manager_secret_iam_member.pipeline_provider,
  ]
}

resource "google_cloud_run_v2_job_iam_member" "coordinator_pipeline" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.pipeline.name
  role     = google_project_iam_custom_role.coordinator.name
  member   = "serviceAccount:${google_service_account.api.email}"
}

resource "google_cloud_run_v2_job" "gc" {
  project             = var.project_id
  name                = var.gc_job_name
  location            = var.region
  deletion_protection = true
  template {
    task_count  = 1
    parallelism = 1
    template {
      max_retries     = 0
      timeout         = "1800s"
      service_account = google_service_account.gc.email
      containers {
        image   = var.pipeline_image
        command = ["python", "-m", "manga_worker.cloud_gc"]
        resources {
          limits = { cpu = "1", memory = "512Mi" }
        }
        dynamic "env" {
          for_each = local.common_cloud_env
          content {
            name  = env.key
            value = env.value
          }
        }
        env {
          name  = "CLOUD_RUN_PROJECT"
          value = var.project_id
        }
        env {
          name  = "CLOUD_RUN_LOCATION"
          value = var.region
        }
        env {
          name  = "MANGA_GC_JOB"
          value = var.gc_job_name
        }
      }
    }
  }
  depends_on = [
    google_project_service.enabled,
    google_project_iam_member.gc_firestore,
    google_storage_managed_folder_iam_member.artifact_gc,
  ]
}

resource "google_cloud_run_v2_job_iam_member" "gc_execution_reader" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.gc.name
  role     = google_project_iam_custom_role.gc_execution_reader.name
  member   = "serviceAccount:${google_service_account.gc.email}"
}

resource "google_cloud_run_v2_job_iam_member" "gc_scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.gc.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.gc_scheduler.email}"
}

resource "google_cloud_run_v2_job_iam_member" "operator_gc_recovery" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.gc.name
  role     = google_project_iam_custom_role.gc_recovery_job.name
  member   = "serviceAccount:${google_service_account.operator.email}"
}

resource "google_project_iam_member" "operator_gc_recovery_operation" {
  project = var.project_id
  role    = google_project_iam_custom_role.gc_recovery_operation_reader.name
  member  = "serviceAccount:${google_service_account.operator.email}"
}

resource "google_cloud_scheduler_job" "artifact_gc" {
  project          = var.project_id
  name             = "hosted-artifact-gc"
  region           = var.region
  description      = "Daily reference-aware seven-day orphan artifact collection."
  schedule         = "0 3 * * *"
  time_zone        = "Etc/UTC"
  paused           = true
  attempt_deadline = "320s"
  retry_config {
    retry_count = 0
  }
  http_target {
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${var.gc_job_name}:run"
    http_method = "POST"
    oauth_token {
      service_account_email = google_service_account.gc_scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
  depends_on = [google_cloud_run_v2_job_iam_member.gc_scheduler_invoker]
}

resource "google_cloud_scheduler_job" "coordinator" {
  project     = var.project_id
  name        = "hosted-coordinator"
  region      = var.region
  description = "One-minute hosted operation dispatch and reconciliation."
  schedule    = "* * * * *"
  time_zone   = "Etc/UTC"
  paused      = true
  http_target {
    uri         = "${var.canonical_api_url}/internal/coordinator"
    http_method = "POST"
    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = var.canonical_api_url
    }
  }
  depends_on = [google_cloud_run_v2_service_iam_member.scheduler_invoker]
}

resource "google_project_service_identity" "pubsub" {
  provider   = google-beta
  project    = var.project_id
  service    = "pubsub.googleapis.com"
  depends_on = [google_project_service.enabled]
}

resource "google_service_account_iam_member" "pubsub_token_creator" {
  service_account_id = google_service_account.pubsub_push.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = google_project_service_identity.pubsub.member
}

resource "google_pubsub_topic" "billing" {
  project                    = var.project_id
  name                       = var.billing_topic_name
  message_retention_duration = "604800s"
  depends_on                 = [google_project_service.enabled]
}

resource "google_pubsub_subscription" "billing" {
  project                    = var.project_id
  name                       = var.billing_subscription_name
  topic                      = google_pubsub_topic.billing.id
  ack_deadline_seconds       = 60
  message_retention_duration = "604800s"
  expiration_policy {
    ttl = "2678400s"
  }
  push_config {
    push_endpoint = "${var.canonical_api_url}/internal/billing-report"
    oidc_token {
      service_account_email = google_service_account.pubsub_push.email
      audience              = var.canonical_api_url
    }
  }
  depends_on = [
    google_service_account_iam_member.pubsub_token_creator,
  ]
}

resource "google_billing_budget" "hosted" {
  billing_account = var.billing_account_id
  display_name    = var.budget_name
  amount {
    specified_amount {
      currency_code = "USD"
      units         = "20"
    }
  }
  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.75
  }
  threshold_rules {
    threshold_percent = 1.0
  }
  all_updates_rule {
    pubsub_topic                   = google_pubsub_topic.billing.id
    schema_version                 = "1.0"
    disable_default_iam_recipients = false
  }
  budget_filter {
    projects = ["projects/${var.project_number}"]
  }
}

