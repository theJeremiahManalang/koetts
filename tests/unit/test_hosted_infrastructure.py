"""Static checks for the offline hosted Terraform configuration."""
from pathlib import Path
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infra" / "hosted"
MAIN = (INFRA / "main.tf").read_text(encoding="utf-8")
VARIABLES = (INFRA / "variables.tf").read_text(encoding="utf-8")
RULES = (INFRA / "firestore.rules").read_text(encoding="utf-8")
TF_IGNORE = (INFRA / ".gitignore").read_text(encoding="utf-8")


class HostedInfrastructureTests(unittest.TestCase):
    def test_existing_database_and_app_hosting_backend_are_not_managed(self):
        self.assertNotRegex(MAIN, r'resource\s+"google_firestore_database"')
        self.assertNotRegex(MAIN, r'resource\s+"google_firebase_app_hosting_backend"')
        self.assertRegex(MAIN, r'FIRESTORE_DATABASE_ID\s*=\s*var\.firestore_database_id')
        self.assertIn('resource.type == \\"firestore.googleapis.com/Database\\"', MAIN)
        self.assertIn('databases/${var.firestore_database_id}', MAIN)
        self.assertIn('default     = "koetts-default"', VARIABLES)
        self.assertNotIn("koetts-default", MAIN)

    def test_new_bucket_is_private_and_has_no_age_deletion(self):
        self.assertIn('uniform_bucket_level_access = true', MAIN)
        self.assertIn('public_access_prevention    = "enforced"', MAIN)
        self.assertIn('force_destroy               = false', MAIN)
        self.assertIn('retention_duration_seconds = var.enable_gcs_soft_delete ? 604800 : 0', MAIN)
        self.assertNotRegex(MAIN, r'(?i)age\s*=\s*[0-9]+')
        self.assertNotIn('allUsers', MAIN)

    def test_jobs_are_bounded_cpu_only_and_gemini_uses_adc_only_on_pipeline(self):
        for job in ("magi", "pipeline"):
            section = MAIN.split(f'resource "google_cloud_run_v2_job" "{job}"', 1)[1]
            section = section.split("\nresource ", 1)[0]
            self.assertRegex(section, r"task_count\s*=\s*1")
            self.assertRegex(section, r"parallelism\s*=\s*1")
            self.assertRegex(section, r'max_retries\s*=\s*0')
            self.assertRegex(section, r'timeout\s*=\s*"1800s"')
            self.assertNotIn("nvidia.com/gpu", section)
        api = MAIN.split('resource "google_cloud_run_v2_service" "api"', 1)[1]
        api = api.split('\nresource "google_cloud_run_v2_service_iam_member"', 1)[0]
        self.assertNotIn("audio_signing.secret_id", api)
        self.assertIn('resource "google_secret_manager_secret_iam_member" "frontend_audio_signing"', MAIN)
        pipeline = MAIN.split('resource "google_cloud_run_v2_job" "pipeline"', 1)[1]
        pipeline = pipeline.split('\nresource "google_cloud_scheduler_job"', 1)[0]
        self.assertNotIn("GEMINI_API_KEY", MAIN)
        self.assertNotIn("provider.secret_id", MAIN)
        self.assertIn('GOOGLE_CLOUD_PROJECT     = var.project_id', MAIN)
        self.assertIn('GOOGLE_CLOUD_LOCATION    = var.inference_location', MAIN)
        self.assertIn('default     = "us"', VARIABLES)
        self.assertIn('"aiplatform.googleapis.com"', MAIN)
        inference_role = MAIN.split('resource "google_project_iam_custom_role" "gemini_inference"', 1)[1]
        inference_role = inference_role.split('\nresource ', 1)[0]
        self.assertIn('permissions = ["aiplatform.endpoints.predict"]', inference_role)
        inference_binding = MAIN.split('resource "google_project_iam_member" "pipeline_gemini_inference"', 1)[1]
        inference_binding = inference_binding.split('\nresource ', 1)[0]
        self.assertIn('google_service_account.pipeline.email', inference_binding)
        self.assertNotIn('google_service_account.api.email', inference_binding)
        self.assertNotIn('google_service_account.magi.email', inference_binding)
        self.assertIn('google_project_iam_member.pipeline_gemini_inference', pipeline)
        self.assertNotIn('provider_secret_version', VARIABLES)
        self.assertNotIn('google_secret_manager_secret" "provider', MAIN)

    def test_reference_aware_collector_has_maintenance_permissions_and_namespace_scope(self):
        gc_role = MAIN.split('resource "google_project_iam_custom_role" "firestore_gc"', 1)[1]
        gc_role = gc_role.split('\nresource ', 1)[0]
        for permission in ('"datastore.entities.create"', '"datastore.entities.update"',
                           '"datastore.entities.delete"'):
            self.assertIn(permission, gc_role)
        gc_storage_role = MAIN.split('resource "google_project_iam_custom_role" "artifact_gc"', 1)[1]
        gc_storage_role = gc_storage_role.split('\nresource ', 1)[0]
        self.assertIn('"storage.objects.get"', gc_storage_role)
        self.assertIn('"storage.objects.list"', gc_storage_role)
        self.assertIn('"storage.objects.delete"', gc_storage_role)
        self.assertNotIn('"storage.objects.create"', gc_storage_role)
        self.assertIn('name   = "${var.artifact_namespace}/"', MAIN)
        self.assertIn('resource "google_storage_managed_folder_iam_member" "artifact_gc"', MAIN)
        self.assertNotIn('resource "google_storage_bucket_iam_member" "artifact_gc"', MAIN)
        runtime_role = MAIN.split('resource "google_project_iam_custom_role" "artifact_runtime"', 1)[1]
        runtime_role = runtime_role.split('\nresource ', 1)[0]
        self.assertIn('"storage.objects.create"', runtime_role)
        self.assertIn('"storage.objects.get"', runtime_role)
        self.assertIn('"storage.objects.list"', runtime_role)
        self.assertNotIn('"storage.objects.delete"', runtime_role)
        self.assertNotIn('"storage.objects.update"', runtime_role)

    def test_gc_job_is_pipeline_cpu_daily_paused_and_invoked_with_oauth(self):
        gc = MAIN.split('resource "google_cloud_run_v2_job" "gc"', 1)[1]
        gc = gc.split('\nresource ', 1)[0]
        self.assertRegex(gc, r'image\s*=\s*var\.pipeline_image')
        self.assertRegex(gc, r'command\s*=\s*\["python",\s*"-m",\s*"manga_worker\.cloud_gc"\]')
        self.assertIn('limits = { cpu = "1", memory = "512Mi" }', gc)
        self.assertIn('name  = "MANGA_GC_JOB"', gc)
        self.assertRegex(gc, r'timeout\s*=\s*"1800s"')
        self.assertRegex(gc, r'max_retries\s*=\s*0')
        self.assertNotIn('GEMINI_API_KEY', gc)
        self.assertNotIn('audio_signing', gc)
        self.assertIn('schedule         = "0 3 * * *"', MAIN)
        self.assertIn('paused           = true', MAIN)
        scheduler = MAIN.split('resource "google_cloud_scheduler_job" "artifact_gc"', 1)[1]
        scheduler = scheduler.split('\nresource ', 1)[0]
        self.assertIn('oauth_token {', scheduler)
        self.assertNotIn('oidc_token {', scheduler)
        self.assertIn('scope                 = "https://www.googleapis.com/auth/cloud-platform"', scheduler)
        self.assertIn('google_cloud_run_v2_job_iam_member" "gc_scheduler_invoker"', MAIN)
        self.assertIn('google_cloud_run_v2_job_iam_member" "gc_execution_reader"', MAIN)
        self.assertIn('role     = "roles/run.invoker"', MAIN)
        reader_role = MAIN.split('resource "google_project_iam_custom_role" "gc_execution_reader"', 1)[1]
        reader_role = reader_role.split('\nresource ', 1)[0]
        self.assertIn('"run.executions.get"', reader_role)
        self.assertNotIn('run.jobs.runWithOverrides', reader_role)

    def test_frontend_admin_permissions_and_operator_cli_iam_are_present(self):
        frontend = MAIN.split('data.google_service_account.frontend.unique_id) = [', 1)[1].split(']', 1)[0]
        self.assertIn('"production-status"', frontend)
        self.assertIn('"production-control"', frontend)
        self.assertIn('resource "google_project_iam_member" "operator_firestore"', MAIN)
        self.assertIn('resource "google_cloud_run_v2_job_iam_member" "operator_gc_recovery"', MAIN)
        self.assertIn('resource "google_project_iam_member" "operator_gc_recovery_operation"', MAIN)
        self.assertIn('"run.jobs.runWithOverrides"', MAIN)
        coordinator = MAIN.split('resource "google_project_iam_custom_role" "coordinator"', 1)[1]
        coordinator = coordinator.split('\nresource ', 1)[0]
        self.assertIn('"run.executions.list"', coordinator)
        self.assertIn('"run.executions.cancel"', coordinator)
        self.assertNotIn('"run.jobs.list"', coordinator)
        self.assertIn('"run.operations.get"', MAIN)
        self.assertIn('resource "google_cloud_run_v2_job_iam_member" "coordinator_magi"', MAIN)
        self.assertIn('resource "google_cloud_run_v2_job_iam_member" "coordinator_pipeline"', MAIN)

    def test_identities_invocation_and_scheduler_start_closed(self):
        for account in ("api", "magi", "pipeline", "scheduler", "gc_scheduler", "pubsub_push", "gc", "operator"):
            self.assertIn(f'resource "google_service_account" "{account}"', MAIN)
        self.assertNotIn('member = "allUsers"', MAIN)
        self.assertIn('schedule    = "* * * * *"', MAIN)
        self.assertIn("paused      = true", MAIN)
        self.assertIn('run.jobs.runWithOverrides', MAIN)
        self.assertIn('"coordinate"', MAIN)
        self.assertIn('"budget-report"', MAIN)
        self.assertIn("data.google_service_account.frontend.unique_id", MAIN)

    def test_budget_is_project_filtered_and_alerts_at_target_thresholds(self):
        self.assertIn('units         = "20"', MAIN)
        self.assertIn('projects = ["projects/${var.project_number}"]', MAIN)
        for threshold in ("0.5", "0.75", "1.0"):
            self.assertIn(f"threshold_percent = {threshold}", MAIN)
        self.assertIn("google_pubsub_subscription.billing.name", MAIN)
        self.assertIn("google_billing_budget.hosted.name", MAIN)

    def test_browser_rules_deny_every_document_operation(self):
        self.assertRegex(RULES, r"allow read, write: if false;")
        configuration = json.loads((INFRA / "firebase.rules.json").read_text())
        self.assertEqual(configuration, {"firestore": [{"database": "koetts-default", "rules": "firestore.rules"}]})

    def test_local_state_and_variable_files_are_ignored(self):
        for pattern in (".terraform/", "*.tfstate", "*.tfvars", "*.tfvars.json"):
            self.assertIn(pattern, TF_IGNORE)


if __name__ == "__main__":
    unittest.main()
