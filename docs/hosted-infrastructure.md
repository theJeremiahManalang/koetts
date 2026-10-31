# Hosted infrastructure configuration

`infra/hosted` describes new GCP resources for the hosted pilot. It is offline
configuration only: no `terraform apply`, `gcloud`, Firebase deployment, paid call,
or live IAM check was run for this change. It deliberately does not create or manage
the existing project `koetts-9bf7f`, App Hosting backend `koetts`, or named Firestore
database `koetts-default`.

See the [phase 5 Mermaid diagrams](hosted-infrastructure-diagram.md) for regional
placement, application/data paths, cost controls and staged frontend migration.

## Boundaries and inputs

Cloud Run and Scheduler default to `us-central1`. The artifact bucket has a separate
`artifact_bucket_location` input, default `us-central1` as selected by the user. This
qualifies for storage free allowances subject to usage limits. Storage and
processing share a region. The frontend stays in `us-east4` initially, so its API
traffic can incur cross-region charges until the planned migration to `us-central1`.
Terraform does not manage or move that App Hosting backend.

The configuration references the existing named Firestore database as a runtime
setting and creates a clean collection dataset inside it. Choose `cloud_dataset`, a
new globally unique artifact bucket, and a stable `artifact_namespace` explicitly
after authorized live preflight. The configuration has no Firestore database
resource and does not import or migrate local state. Firestore IAM is project policy
with a resource-name condition for the exact configured database; collection
dataset scoping is not claimed or encoded as an IAM capability. Google documents
resource-name IAM conditions for individual databases, including that the Cloud
console does not honor those conditions for its own database views. Validate the
condition against the live Firestore Native database before rollout.

The new API, `magi` and `pipeline` jobs use immutable image digests. The private API
has zero minimum, maximum one instance, one CPU, 512 MiB, and authenticated Cloud
Run invocation. The two finite CPU jobs each use one task, one concurrent task, zero
platform retries, and a 30-minute per-attempt timeout. The `magi` job has a 4 CPU /
8 GiB ceiling; `pipeline` has 2 CPU / 4 GiB. Neither job requests a GPU. These
configured caps do not establish measured throughput or a monthly spending limit.
The Scheduler starts paused and must stay paused until the rollout gates pass.

The configuration creates separate API, inference-job, pipeline-job, scheduler,
Pub/Sub push, GC scheduler, artifact collector, and operator service accounts.
Runtime artifact grants use a Cloud Storage managed folder at the exact artifact
namespace path; API and processing jobs get only object create/get/list there, and
the collector gets only object get/list/delete there. Runtime
Firestore document access uses a narrow custom role conditioned on the named
database. The GC role includes document create/update/delete for fenced
`maintenance`, `gc_runs`, and stale `uploads` records, as well as reads for all
live references. Firestore IAM cannot restrict those operations to collections,
so IAM scope is the named database and the collector enforces the collection-level
contract in code. API Firebase Auth access is limited to the user lookup permission
used for revoked-token checks. The API coordinator gets a custom Cloud Run role
with run-with-overrides and execution inspection/list/cancel permissions, bound
separately to the `magi` and `pipeline` jobs. A separate one-permission project
role allows polling the Cloud Run long-running operation returned by job start. No
Owner or Editor grant exists. Cloud Run service invoker grants name only the
frontend, coordinator Scheduler, Pub/Sub push, and operator identities; the
artifact-GC Scheduler has invocation only on its single job. No public invoker is
configured.

The collector uses the immutable pipeline CPU image, one task, one concurrent task,
zero platform retries, a 30-minute timeout, and 1 CPU / 512 MiB. It has no provider
key, signing key, or GPU. Its daily 03:00 UTC Cloud Scheduler trigger starts paused
and calls the Cloud Run Jobs API with an OAuth access token. Its dedicated caller
can invoke only the GC job and cannot set task overrides. Recovery is a separate
operator action: the operator may start only that GC job with
`MANGA_GC_RECOVER_OWNER`, inspect its execution, and read the start operation. The
GC identity can inspect executions for that GC job to verify the previous run
stopped before replaying exact-generation deletions; it cannot start jobs or set
overrides. The daily scheduler does not set recovery overrides.

The developer budget CLI writes Firestore ledger and operation state using a
dedicated operator data role conditioned on the named database. It does not use
the operator service token or invoke provider/model services. The operator API
service subject has production status/control permissions, while those routes still
require a verified Firebase administrator. The frontend subject has the same
status/control actions for future admin UI use, with the same Firebase check.

`S3_SERVICE_PERMISSIONS` is generated using each service account's numeric subject:
the frontend caller receives the current hosted transport actions, Scheduler gets
`coordinate`, Pub/Sub gets `budget-report`, and the operator gets identity,
readiness, production-status, and production-control actions. API pause mutations
still require a verified Firebase administrator in addition to the service token. The existing
App Hosting runtime identity can read the audio signing secret used by the Next.js
server. The API does not receive this key. The existing backend must
still reference `MANGA_AUDIO_SIGNING_KEY` as a runtime-only App Hosting secret at
the pinned numeric version; this configuration does not manage that backend or
edit its `apphosting.yaml`. The reviewed web configuration change will have this
shape, with the numeric version supplied from approved Secret Manager setup:

```yaml
- variable: MANGA_AUDIO_SIGNING_KEY
  secret: hosted-audio-signing-key@VERSION
  availability:
    - RUNTIME
```

The provider key is exposed only to the pipeline job;
it is absent from the API, browser, and `magi` job. Terraform creates secret
containers and IAM bindings, but no secret versions or secret values. Add values
through an approved Secret Manager procedure and provide explicit numeric version
inputs. Never put secret bytes in a `.tfvars` file or Terraform state.

The GCS bucket enforces uniform bucket-level access and public access prevention,
cannot be destroyed by this configuration, and has no age-based lifecycle rule.
Seven-day reference-aware collection belongs to the application GC process; bucket
age deletion could remove referenced artifacts. Optional seven-day GCS soft delete
is off by default because it retains deleted bytes and adds storage cost. Turning it
on is an explicit cost decision, not a replacement for reference-aware collection.

## Billing and rollout gates

The USD 20 budget filters to this project and sends configured notifications at
50%, 75%, and 100%, matching USD 10, 15, and 20. Its notification topic and
authenticated Pub/Sub push subscription target the private API. The API receives
the generated budget ID, billing account ID, and exact subscription resource name.
Budget notifications are delayed estimates and are not a hard spend cap. The
operating target remains USD 10/month and USD 20 is a desired infrastructure
ceiling, not a guarantee. Existing traffic and other services can continue to accrue
cost while production is paused.

Before rollout, verify the real API URL equals `canonical_api_url`; the same
operator-supplied URL is used for service-token validation and Scheduler/Pub/Sub
OIDC audiences to avoid an API URL dependency cycle. Verify Pub/Sub push token
audience/subject and the numeric subjects in `S3_SERVICE_PERMISSIONS`. Confirm the
Cloud Billing notification topic publisher permission and actual notification
payload identity against a test delivery. Google documents budget notifications as
at-least-once, possibly out of order, and delayed; ingestion is idempotent, but live
delivery remains unverified here.

Pub/Sub's service agent is explicitly generated with the locked `google-beta`
provider before its narrowly scoped push-token grant. Computing its email alone
does not prove that a newly enabled project's service agent exists. This is the
only beta resource used; see the provider's [service identity documentation](https://registry.terraform.io/providers/hashicorp/google-beta/latest/docs/resources/project_service_identity).

Inspect the existing Firestore Security Rules before changing them. The checked-in
[`infra/hosted/firestore.rules`](../infra/hosted/firestore.rules) is deny-all browser
rules text, but this Terraform configuration does not deploy Firestore rules. The
separate [`firebase.rules.json`](../infra/hosted/firebase.rules.json) configuration
targets only `koetts-default`, without Auth, App Hosting or another database. If
preflight finds the named database permits browser access, deploy these rules only
to that database through the separately authorized Firebase procedure, using the
explicit config and `firestore:koetts-default` deploy selector. Capture existing
rules and their rollback target first. The [Firebase rules deployment guide](https://firebase.google.com/docs/rules/manage-deploy)
documents named-database selectors. No rules deployment ran during offline work.
Do not replace rules for another database. Server-side Google client libraries use
IAM and bypass Firestore Security Rules, so browser deny rules do not replace the
service-account IAM checks.

## Offline validation and later execution

From the repository root, focused static checks are:

```bash
uv run python -m unittest tests.unit.test_hosted_infrastructure
```

When Terraform is installed, initialize without a remote backend and validate the
configuration:

```bash
terraform -chdir=infra/hosted init -backend=false
terraform -chdir=infra/hosted validate
terraform -chdir=infra/hosted fmt -check -recursive
```

These commands validate syntax/provider schemas only. For this configuration,
HashiCorp Terraform 1.17.1 was downloaded from the official release host and its
archive checksum verified. Backend-disabled initialization, `fmt -check`, and
`validate` passed. No plan or apply ran. No `.tfvars` or backend state is checked
in; preserve `.terraform.lock.hcl` with the configuration.
Before any live plan/apply, review state boundaries, verify all explicit inputs,
confirm existing services/database/rules/IAM and billing account, and obtain
separate authorization for the exact cloud changes. Keep App Hosting frontend-only
mode on and Scheduler paused until the hosted service acceptance gates and rollback
evidence pass. Follow [`hosted rollout preparation`](hosted-rollout.md); do not
infer live IAM, billing, URL, database, or secret-version readiness from this file.

Primary references:

- [Google Cloud Terraform provider](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [Terraform Cloud Run v2 job IAM member](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_v2_job_iam)
- [Cloud Run IAM permissions](https://docs.cloud.google.com/run/docs/reference/iam/permissions)
- [Cloud Run jobs.run authorization](https://docs.cloud.google.com/run/docs/reference/rest/v2/projects.locations.jobs/run)
- [Firestore Native server IAM](https://docs.cloud.google.com/firestore/native/docs/security/iam)
- [Per-database IAM conditions](https://docs.cloud.google.com/datastore/docs/manage-databases#configure_per-database_access_permissions)
- [IAM resource type/name condition attributes](https://docs.cloud.google.com/iam/docs/conditions-attribute-reference)
- [Authenticated Pub/Sub push](https://docs.cloud.google.com/pubsub/docs/authenticate-push-subscriptions)
- [Cloud Storage managed-folder IAM](https://docs.cloud.google.com/storage/docs/access-control/using-iam-for-managed-folders)
- [Programmatic Cloud Billing notifications](https://docs.cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications)
- [Firestore Security Rules and server client behavior](https://firebase.google.com/docs/firestore/security/rules-conditions)
- [App Hosting Secret Manager references](https://firebase.google.com/docs/app-hosting/configure)


## Free-tier assessment

The API service default is `koetts-api`. The existing verification API remains
`koetts-s3-api` until an authorized, verified cutover. The Terraform configuration
is not restricted to no-cost usage: the new artifact bucket defaults to eligible
`us-central1`, but execution/storage volumes have no cumulative free-tier cap.
The initial frontend-to-API path crosses regions until frontend migration. See the dated [free-tier review](hosted-free-tier-review.md)
and [official-source notes](hosted-free-tier-sources.md) before estimating costs.
