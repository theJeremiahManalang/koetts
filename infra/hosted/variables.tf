variable "project_id" {
  description = "Existing Firebase/GCP project ID. This configuration does not create a project."
  type        = string
  default     = "koetts-9bf7f"
}

variable "project_number" {
  description = "Numeric project number, used for the Pub/Sub service agent and billing project filter."
  type        = string
  default     = "907898221016"
  validation {
    condition     = can(regex("^[0-9]+$", var.project_number))
    error_message = "project_number must be a numeric Google Cloud project number."
  }
}

variable "region" {
  description = "Region for new Cloud Run and Scheduler resources."
  type        = string
  default     = "us-east4"
}

variable "firestore_database_id" {
  description = "Existing named Firestore database ID. The database is referenced as runtime configuration only."
  type        = string
  default     = "koetts-default"
  validation {
    condition     = var.firestore_database_id != "(default)" && length(trimspace(var.firestore_database_id)) > 0
    error_message = "Use the existing named Firestore database; do not select the default database."
  }
}

variable "cloud_dataset" {
  description = "New, clean Firestore collection namespace for hosted state. Choose explicitly after preflight."
  type        = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{1,100}$", var.cloud_dataset))
    error_message = "cloud_dataset must be a valid explicit dataset identifier."
  }
}

variable "artifact_bucket_location" {
  description = "Location for the new artifact bucket, independent of the service region. us-east1 is eligible for Cloud Storage Always Free usage allowances."
  type        = string
  default     = "us-east1"
}

variable "artifact_bucket_name" {
  description = "New globally unique private bucket name. Existing buckets are not adopted."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,220}[a-z0-9]$", var.artifact_bucket_name))
    error_message = "artifact_bucket_name must be a valid explicit GCS bucket name."
  }
}

variable "artifact_namespace" {
  description = "New canonical object prefix; choose explicitly and keep stable for this dataset."
  type        = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$", var.artifact_namespace))
    error_message = "artifact_namespace must be an explicit slash-separated identifier."
  }
}

variable "api_image" {
  description = "Immutable API image reference, ending in @sha256:<64 hex digits>."
  type        = string
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.api_image))
    error_message = "api_image must use an immutable SHA-256 image digest."
  }
}

variable "magi_image" {
  description = "Immutable CPU inference job image reference, ending in @sha256:<64 hex digits>."
  type        = string
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.magi_image))
    error_message = "magi_image must use an immutable SHA-256 image digest."
  }
}

variable "pipeline_image" {
  description = "Immutable pipeline job image reference, ending in @sha256:<64 hex digits>."
  type        = string
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.pipeline_image))
    error_message = "pipeline_image must use an immutable SHA-256 image digest."
  }
}

variable "api_service_name" {
  description = "New private Cloud Run API service name."
  type        = string
  default     = "koetts-api"
}

variable "magi_job_name" {
  description = "New CPU inference Cloud Run Job name."
  type        = string
  default     = "koetts-magi"
}

variable "pipeline_job_name" {
  description = "New light processing Cloud Run Job name."
  type        = string
  default     = "koetts-pipeline"
}

variable "gc_job_name" {
  description = "New reference-aware artifact collection Cloud Run Job name."
  type        = string
  default     = "koetts-artifact-gc"
}

variable "canonical_api_url" {
  description = "Explicit canonical Cloud Run API base URL from preflight; verify against the deployed service URL before enabling callers."
  type        = string
  validation {
    condition     = can(regex("^https://[^/]+$", var.canonical_api_url))
    error_message = "canonical_api_url must be an HTTPS origin without a path or trailing slash."
  }
}

variable "frontend_service_account_email" {
  description = "Existing App Hosting runtime service account email, looked up but never managed here."
  type        = string
  default     = "firebase-app-hosting-compute@koetts-9bf7f.iam.gserviceaccount.com"
}

variable "billing_account_id" {
  description = "Existing Cloud Billing account in AAAAAA-BBBBBB-CCCCCC form."
  type        = string
  validation {
    condition     = can(regex("^[A-F0-9]{6}(-[A-F0-9]{6}){2}$", var.billing_account_id))
    error_message = "billing_account_id must be an explicit billing account ID."
  }
}

variable "budget_name" {
  description = "New Cloud Billing budget display name and stable notification budget ID."
  type        = string
  default     = "koetts-hosted-pilot-usd20"
}

variable "billing_topic_name" {
  description = "New Pub/Sub topic for Cloud Billing notifications."
  type        = string
  default     = "koetts-hosted-billing"
}

variable "billing_subscription_name" {
  description = "New authenticated push subscription name."
  type        = string
  default     = "koetts-hosted-billing-push"
}

variable "audio_signing_secret_version" {
  description = "Explicit numeric Secret Manager version containing the API's 32-byte audio signing key. Never put its value in Terraform."
  type        = string
  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.audio_signing_secret_version))
    error_message = "Set an explicit numeric version for the audio signing secret."
  }
}

variable "provider_secret_version" {
  description = "Explicit numeric Secret Manager version containing the provider key, exposed only to the pipeline job."
  type        = string
  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.provider_secret_version))
    error_message = "Set an explicit numeric version for the pipeline provider secret."
  }
}

variable "enable_gcs_soft_delete" {
  description = "Opt in to seven-day GCS soft delete. Adds retained storage cost; reference-aware collection remains authoritative."
  type        = bool
  default     = false
}
