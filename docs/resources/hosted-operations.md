# Hosted operations

Operational entry point for the hosted GCP backend. This guide documents
configuration and safe operator procedures; it is not evidence of current live
resource state or authorization to change cloud resources. Read [current status](../STATUS.md)
and the [hosted plan](../plans/hosted-service-plan.md), then use the linked
runbooks for detailed deployment, acceptance, cost controls, or decommission.

## Configuration sources

| Concern | Source of truth |
| --- | --- |
| Terraform resource graph and runtime environment | [`infra/hosted/main.tf`](../../infra/hosted/main.tf) |
| Input names, defaults, and validation | [`infra/hosted/variables.tf`](../../infra/hosted/variables.tf) |
| Provider versions and checksums | [`infra/hosted/versions.tf`](../../infra/hosted/versions.tf), `.terraform.lock.hcl` |
| Project-specific Terraform values | `infra/hosted/phase5.auto.tfvars.json` (private, ignored) |
| Terraform's local resource identity | `infra/hosted/terraform.tfstate` and backups (private, ignored) |
| Frontend runtime/build settings | [`apps/web/apphosting.yaml`](../../apps/web/apphosting.yaml) |
| Operator CLI project, database, dataset, bucket, and namespace | Explicit environment variables; see [cost controls](hosted-cost-controls.md) and [manual deployment](manual-production-deployment.md) |
| Provider allowance and per-stage admission limits | Firestore application ledger, written through audited `manga_worker.cloud_operator`; never Terraform billing budget |

Do not print, commit, or share tfvars, state, saved plans, signing-secret bytes,
tokens, or raw logs. Terraform auto-loads `phase5.auto.tfvars.json` from
`infra/hosted`; commands below use that existing private file. Keep its stable
dataset, bucket, namespace, identities, billing IDs, secret version, and immutable
image digests unless a separately reviewed change requires otherwise. The
frontend configuration names the API URL and secret version reference; it does
not contain signing-secret bytes.

`coordinator_paused` defaults to `true`. A private tfvars override may set it to
`false`; inspect that value privately before planning. This controls the
reconciliation scheduler only. The artifact-GC scheduler has its own paused
setting. A successful apply can preserve an intentional enabled scheduler.

The Terraform Cloud Billing budget is USD 20 for the whole GCP project, with
50%, 75%, and 100% notifications. It includes Gemini and other project charges;
notifications can be delayed and are not a hard spend cap. The separate
Firestore runtime ledger controls provider allowance, per-stage/per-call
allowances, and call count at application admission. Those controls also are not
a hard GCP spend cap. See [cost controls](hosted-cost-controls.md) for audited
ledger changes and billing reconciliation.

## Provisioning sequence

For a new backend, complete these gates in order. Terraform does not bootstrap
missing product prerequisites or infer their identifiers:

1. Confirm the existing GCP/Firebase project is linked to the intended billing
   account. Confirm the named Firestore database and deny-browser rules, Firebase
   App Hosting backend, and its runtime service account already exist. Terraform
   references these resources; it does not create or migrate them.
2. Create or verify the dedicated Artifact Registry repository required by the
   image build. Terraform does not manage that repository. Use the repository and
   region names approved for this project.
3. Securely create `infra/hosted/phase5.auto.tfvars.json` from authorized project
   values if it is missing. Set required dataset, bucket, namespace, billing
   account, API URL, secret-version input, and immutable image references. Keep
   the private state if this environment has existing resources. If state or
   inputs are missing, stop and recover the correct files; do not silently start
   a new state against deployed resources.
4. Run the approved signing-secret procedure. Terraform manages the secret
   container and frontend access binding, not secret bytes or versions. Do not
   invent a version number; confirm the intended version exists before deploying
   a frontend that references it.
5. Build API, pipeline, and Magi images and record immutable digests. Use
   [manual deployment](manual-production-deployment.md) for the exact Cloud Build
   invocation and digest checks. Enter the digests in private tfvars.
6. Run the plan workflow below. For first provisioning, expect new backend
   identities, roles, bindings, bucket/folder, budget notifications, indexes,
   API, jobs, trigger, and paused schedulers. Verify the plan leaves existing
   project data, Firestore database, App Hosting backend, and signing-secret
   values intact. Stop if actions differ from intended scope.
7. Apply only the saved and explicitly authorized plan. Verify indexes and
   service/job readiness, then prepare and deploy the frontend through the
   sanitized App Hosting flow in the manual deployment guide. Complete paused
   acceptance before any activation. Keep schedulers paused unless each has a
   separate explicit decision.

## Resource boundary

Terraform references the existing GCP/Firebase project, named Firestore database,
App Hosting runtime service account, and billing account. It does not create a
project or the Firebase App Hosting backend. It enables required project APIs,
looks up the existing frontend service account, and manages backend service
accounts/roles/bindings, private Cloud Run API and jobs, Eventarc/Scheduler and
Pub/Sub delivery, Firestore indexes, artifact bucket/folder, signing-secret
container and access, and the project-filtered billing budget. Terraform manages
the secret container and runtime version reference; operators own secret bytes
and version creation. The Firebase frontend is deployed separately through
Firebase App Hosting.

The existing Firestore database `koetts-default` is referenced, never created or
deleted by this root. Hosted documents use an explicit `cloud_dataset` collection
namespace in that database. The artifact bucket and namespace are explicit inputs
and must be new, dedicated resources for initial provisioning; do not adopt an
existing bucket or reset project data. Region defaults are Cloud Run and bucket
`us-central1`, Firestore/Eventarc source `nam5`, and Vertex AI `us`.

## Plan and apply

Run from repository root. First verify active account/project, exact authorized
scope, paused/queue/execution state, and available local state backup. For initial
provisioning, also verify the existing named database, frontend identity, billing
account, secret version, unique bucket name, dataset namespace, API URL, and
immutable image digests. Do not proceed if the correct state or inputs are
missing. These commands create local evidence only until a human explicitly
applies the reviewed plan.

```bash
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
umask 077
deployment_dir="$PWD/results/hosted-terraform-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p results
mkdir -m 700 "$deployment_dir"
if [ -f infra/hosted/terraform.tfstate ]; then
  cp infra/hosted/terraform.tfstate "$deployment_dir/terraform.tfstate.before"
fi
cp infra/hosted/phase5.auto.tfvars.json "$deployment_dir/phase5.auto.tfvars.json.before"
git rev-parse HEAD > "$deployment_dir/commit.txt"
git status --short > "$deployment_dir/git-status.txt"
terraform -chdir=infra/hosted init -lockfile=readonly
terraform -chdir=infra/hosted fmt -check
terraform -chdir=infra/hosted validate
plan_file="$deployment_dir/hosted.tfplan"
terraform -chdir=infra/hosted plan -out="$plan_file"
terraform -chdir=infra/hosted show -no-color "$plan_file" > "$deployment_dir/hosted-plan.txt"
cat "$deployment_dir/hosted-plan.txt"
```

The saved plan path is absolute and its parent is created with mode `0700`; files
inherit private mode from `umask 077`. Protect this evidence directory. Review
every action and the JSON plan when needed. Stop if the plan unexpectedly adds,
replaces, or deletes data, bucket/folder, secret, billing, IAM, frontend-related,
or other shared resources. Confirm only intended changes, deletion protection,
private invoker, event source/destination, image digests, index readiness, and
scheduler states. Record reviewer and exact plan path. A saved plan can be stale
after any source, input, state, or live-resource change; discard it and generate
a fresh plan after such a change.

Only after explicit authorization for this exact reviewed plan, apply the saved
plan and keep the output private:

```bash
terraform -chdir=infra/hosted apply "$plan_file" 2>&1 | tee "$deployment_dir/apply.log"
```

Terraform can make cloud changes during `apply`. A successful command proves
Terraform execution, not application acceptance. Capture actual outputs and
verify ready revisions, immutable serving image digests, URL/audience, private
access, indexes, schedules, ledger status, and preserved data separately. Follow
[manual deployment](manual-production-deployment.md) for build, frontend rollout,
paused acceptance, human activation, and evidence requirements.

## Modify existing deployment

For code changes, build immutable API/pipeline/Magi image digests using the
approved build allowance. Update only intended image fields in the private tfvars;
verify them against successful Cloud Build metadata. For configuration changes,
edit the intended private input or checked-in Terraform source, preserve stable
data identities, then repeat the saved-plan review above. Frontend changes use
the sanitized App Hosting source preparation and deploy flow in
[manual deployment](manual-production-deployment.md); wrap `cd` and deploy in a
subshell so the operator's shell returns to the repo root. Do not change runtime
allowance or scheduler state as a side effect of image updates. Do not deploy
frontend flags that enable processing until paused acceptance and explicit
activation gates are satisfied.

After apply, capture read-only service/job/frontend metadata and a narrow log
window. Compare serving revisions with the plan and build record. If apply or
delivery fails, preserve ledger and records, pause through approved operational
controls when safe, and follow the recovery steps in the [deployment runbook](manual-production-deployment.md).
Do not retry uncertain paid work automatically.

## Decommission

Decommission has its own drain, maintenance, retention, and resource-specific
deletion sequence. Never use broad `terraform destroy`; this Terraform root also
manages resources that must remain, including bucket/data references, the secret
container, billing, and indexes. Keep the frontend, Auth, named Firestore database,
retained project/audio objects and references, necessary signing version, billing
alerts, and private Terraform state. Use the [backend decommission guide](hosted-backend-decommission.md)
only after acceptance and billing/operation reconciliation. It requires a fresh
reviewed targeted plan and explicit resource list. This guide does not assert
that any current hosted service is deployed or decommissioned.

## Related runbooks

Start each manual campaign with private copies of both shared checklists:

```bash
mkdir -p manual-testing
test_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
cp docs/resources/admin-processing-acceptance-checklist.md \
  "manual-testing/admin-processing-$test_stamp.md"
cp docs/resources/production-deployment-checklist.md \
  "manual-testing/production-deployment-$test_stamp.md"
```

The root `manual-testing/` directory is gitignored. Gitignore prevents future
staging; it does not erase earlier Git history.

- [Infrastructure reference](hosted-infrastructure.md): architecture, inputs, IAM, storage, and Terraform details.
- [Manual deployment](manual-production-deployment.md) and [deployment checklist](production-deployment-checklist.md): build, saved plan, rollout, recovery, and evidence.
- [Manual acceptance](hosted-manual-validation.md), [admin checklist](admin-processing-acceptance-checklist.md), and [phase 5 review](phase-5-manual-acceptance-review.md): human test steps and evidence.
- [Cost controls](hosted-cost-controls.md): pause/resume, allowance configuration, billing, and reconciliation.
- [Artifact collection](hosted-artifact-collection.md): reference-aware cleanup and recovery.
- [Backend decommission](hosted-backend-decommission.md): future compute retirement while preserving product data.
