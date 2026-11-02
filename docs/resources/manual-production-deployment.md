# Manual production deployment

This is a procedure for the human deployment operator. It does not record an
executed deployment or authorize production activation. Use the accompanying
[deployment checklist](production-deployment-checklist.md) to record expected and
actual results. The agent performs read-only post-deployment review after the
operator supplies the UTC window and evidence paths.

## Scope and preserved resources

Use project `koetts-9bf7f`. The frontend `koetts` stays in `us-east4`; private API
`koetts-api`, CPU jobs, schedulers and artifact bucket stay in `us-central1`.
Existing Firestore `koetts-default` and its Eventarc source location are `nam5`.
The Eventarc destination region remains `us-central1`.

The approved removal list is exactly `koetts-api`, jobs `koetts-magi`,
`koetts-pipeline`, `koetts-artifact-gc`, and schedulers `hosted-coordinator` and
`hosted-artifact-gc`. Preserve frontend `koetts` and old API `koetts-s3-api`.
Limited teardown completed on 2026-11-02 using approved CLI execution, after
verifying the paused ledger, zero provider allowance and no listed executions.
All six approved resources were deleted. Private metadata and Terraform input
backups are in `results/compute-teardown-20261102/`. Postchecks verified empty
central services/jobs/schedulers lists and preserved frontend, legacy API,
database, bucket, secret, identities, billing budget/topic/subscription and paused
ledger. Full data contents were not audited.

Terraform state remains unchanged. Generate a fresh normal plan with refresh to
recreate missing resources and their resource-scoped bindings. Do not apply a
saved plan from before teardown. No build, deployment or Terraform apply occurred.

Preserve Firestore,
GCS objects/buckets, Artifact Registry images, identities, IAM needed by preserved
services, signing secrets and versions, billing budget/notifications, and the
budget ledger. Do not run a broad `terraform destroy`, reset data, remove state,
or rotate signing material as part of deployment. Existing API/job deletion
protection must not be disabled without a reviewed resource-specific change.
Reusing existing resources for an update is preferable when teardown is unnecessary.

`infra/hosted/terraform.tfstate`, backups and ignored
`infra/hosted/phase5.auto.tfvars.json` are authoritative local deployment inputs;
there is no configured remote state backend. Securely back them up before any
mutation and retain them after teardown. Never publish state, plans, tfvars, tokens,
raw private logs or secret bytes. Do not recreate preserved resources because a
state file or credential is unavailable; recover the correct inputs first.

## 1. Prepare the candidate and baseline

1. Use the exact reviewed candidate commit. Record `git rev-parse HEAD` and
   `git status --short`; preserve a source manifest for any deliberate dirty build.
2. Select Node through `.nvmrc` (`22.22.3`), npm `10.9.8`, uv `0.11.16` and Python
   3.11. Run `npm ci`, `uv sync --frozen`, `npm run check`, `npm run test:http`
   and `npm run test:firestore`; record failures and optional sample skips.
3. Verify the active Google account/project, ADC and required permissions in the
   operator's terminal. Refresh live service revisions, job image digests, active
   executions, scheduler states, Firestore location, bucket namespace, signing
   secret version references, budget ledger and private API IAM. Record UTC times.
4. Confirm production is paused, provider calls disabled and both schedulers
   paused. Wait for positively confirmed terminal executions before any teardown.
   A lease expiry alone is insufficient. Preserve old revisions/digests as rollback
   targets; do not delete a service merely because it appears unused.
5. Inspect existing tfvars without printing credentials. Keep `cloud_dataset`,
   `artifact_bucket_name`, `artifact_namespace`, frontend identity, billing IDs and
   `audio_signing_secret_version` unchanged. Verify `region=us-central1`,
   `artifact_bucket_location=us-central1`, `firestore_database_location=nam5`.

## 2. Build backend images

Cloud Build incurs infrastructure/build spend. Use the authorized allowance and
choose a unique immutable tag. From the repository root, replacing `UNIQUE_TAG`:

```bash
gcloud builds submit --project=koetts-9bf7f --config=cloudbuild.hosted.yaml --substitutions=_REGION=us-central1,_REPOSITORY=koetts-hosted,_TAG=UNIQUE_TAG .
```

Record build ID/status, candidate manifest and pushed digests for `koetts-api`,
`koetts-pipeline` and `koetts-magi`. Set `api_image`, `pipeline_image` and
`magi_image` in the existing private tfvars to the corresponding full
`us-central1-docker.pkg.dev/...@sha256:...` references. Do not use mutable tags in
Terraform. The GC job uses `pipeline_image`; verify its digest matches the pipeline digest
in the plan.

A successful build does not update Terraform inputs automatically. Before applying,
compare all three private image references against that build's `results.images`:

```bash
gcloud builds describe BUILD_ID --project=koetts-9bf7f --format='json(status,results.images)'
```

Eventarc uses the full `/internal/operation-events` destination URL as its signed
token audience. The API must verify that audience for event dispatch while keeping
other actions restricted to the base API audience. A successful Cloud Run IAM
invocation can still receive an application-level 401 if these differ.

Every planned API/job digest must match the selected successful build. Reusing an
older digest can deploy an API without the frontend's progress-stream route or
operation dispatch signals, even when uploads and enqueue requests succeed. After
apply, compare the serving API and all job digests with the same build record.

## 3. Review and apply the exact infrastructure plan

Run these commands from the repository root. The plan file lives under ignored
`results/`, and the commands create its parent first. A saved plan can contain
sensitive configuration, so keep the directory private.

```bash
umask 077
mkdir -p results/deployment-plans
chmod 700 results/deployment-plans
plan_file="$PWD/results/deployment-plans/koetts-hosted.tfplan"
terraform -chdir=infra/hosted init -lockfile=readonly
terraform -chdir=infra/hosted fmt -check
terraform -chdir=infra/hosted validate
terraform -chdir=infra/hosted plan -out="$plan_file"
terraform -chdir=infra/hosted show -no-color "$plan_file"
```

Review every resource action. An ordinary update must preserve existing data,
identities, secrets and budget resources. Verify the Eventarc trigger uses `nam5`,
sets event data content type to `application/protobuf` for direct Firestore events,
its document filter selects the existing dataset's `dispatch_signals`, and its
private API destination is `us-central1`. Confirm API invoker IAM remains narrow,
both queued-operation indexes exist, job retries are zero, and schedules remain
paused. New Eventarc/IAM/index/TTL
resources require review of this concrete plan before apply.

If the user elects the approved limited teardown, prepare a separate explicit
resource list and reviewed plan first. Account for API/job deletion protection,
active executions, frontend outage and Eventarc/billing destinations. Reconcile
Terraform with actual resource removals using refreshed state before the replacement
plan. Retain state and let Terraform detect removals; do not use `terraform state rm`
as a deletion shortcut. Do not use
this deployment plan as a teardown plan or remove shared dependencies by association.

After the exact plan passes review, the human operator applies that saved plan:

```bash
plan_file="$PWD/results/deployment-plans/koetts-hosted.tfplan"
terraform -chdir=infra/hosted apply "$plan_file"
```

Record outputs privately and verify actual ready revisions and digests. The
canonical API URL and OIDC audience must match the actual service URL. If the URL
changes after recreation, update `canonical_api_url` through a second reviewed
plan, verify service audiences and billing push configuration, then update the
frontend source setting. Keep secret-version references intact; never export bytes. While the API is down,
its production controls, admin diagnostics and billing-push endpoint are unavailable.
Preserved billing notifications may retry; verify backlog delivery and ledger state
after restoration. Do not initialize or reset the existing ledger to clear errors.

## 4. Deploy the existing east-region frontend

Confirm `apps/web/apphosting.yaml` references the verified API URL and existing
signing-secret version, with the intended cloud admin mode. Use the sanitized
app-only source preparation helper; do not deploy the raw monorepo checkout.
Replace `UNIQUE` with a new staging suffix:

```bash
uv run --locked python tools/prepare_apphosting_source.py --output /tmp/koetts-apphosting-stagev2
cd /tmp/koetts-apphosting-stagev2
firebase deploy --only apphosting:koetts --project koetts-9bf7f --non-interactive
```

Record build ID, rollout status, ready revision and traffic allocation. Verify the
frontend remains in `us-east4`. Current expected URL is
`https://koetts--koetts-9bf7f.us-east4.hosted.app`; confirm it from live deployment
metadata. Regional frontend migration is a separate operation.

## 5. Verify paused behavior, then let the user test

Before activation, verify public browse/login, anonymous private API denial,
non-admin processing denial, admin diagnostic access, and the explicit
“Hosted production is paused” denial for new production. Confirm no job starts.
Verify Firestore browser access remains denied and no public API invoker was added.

Production activation is a separate explicit human action. Configure measured
stage/call caps and provider allowance before resuming; do not reuse blocked setup
caps. See [cost controls](hosted-cost-controls.md). Run from the repository root;
otherwise `uv run --locked` cannot find the workspace lockfile and warns that
`--locked` has no effect. The operator CLI does not infer cloud settings from
Terraform or the active gcloud project. Supply all five settings explicitly:

```bash
cd /home/ssuish/projects/manga-to-audio-book-project
FIREBASE_PROJECT_ID=koetts-9bf7f \
FIRESTORE_DATABASE_ID=koetts-default \
MANGA_CLOUD_DATASET=hosted_pilot_20261101 \
MANGA_ARTIFACT_BUCKET=koetts-9bf7f-hosted-artifacts-us-central1 \
MANGA_ARTIFACT_NAMESPACE=hosted/pilot_20261101 \
GOOGLE_CLOUD_PROJECT=koetts-9bf7f \
uv run --locked python -m manga_worker.cloud_operator status --execute
```

`status --execute` only reads the production ledger. It still needs Application
Default Credentials (ADC). If ADC is not configured on this machine, run
`gcloud auth application-default login` and set its quota project with
`gcloud auth application-default set-quota-project koetts-9bf7f`. CLI sign-in
alone does not provide ADC to Python client libraries.

Configure caps only after a representative hosted run establishes maximum CPU
cost per stage, maximum provider cost per operation/call, and call count. Values
use integer USD micro-units (`1 USD = 1,000,000`). Each stage needs
`infrastructure_micro`, `provider_micro`, `provider_call_micro`, and
`max_provider_calls`. Keep `magi` provider fields zero. Keep `pipeline` provider
fields zero until enabling the manually approved Gemini test. Stage caps from the
initial setup are hold values, not measurements; do not reuse them.

Use the interactive tool to collect USD values, write a private JSON cap file,
and print the default no-write plan:

```bash
uv run --locked python tools/manage_hosted_budget.py \
  --actor YOUR_GOOGLE_ACCOUNT \
  --reason "Enable measured hosted manual acceptance" \
  --evidence YOUR_ACCEPTANCE_RECORD
```

Review the plan and generated file path. Add `--execute` only after reviewing the
caps and plan. To reuse the reviewed file without re-entering values, pass
`--provider-allowance-usd 5 --stage-caps PATH --actor ... --reason ... --evidence ...`.
The tool changes ledger configuration only; it does not resume production or run
jobs. The lower-level `cloud_operator configure` command remains available.

First review the proposed ledger configuration without `--execute`:

```bash
uv run --locked python -m manga_worker.cloud_operator configure \
  --provider-allowance-micro 5000000 \
  --stage-caps results/hosted-stage-caps.json \
  --actor YOUR_GOOGLE_ACCOUNT \
  --reason "Enable measured hosted manual acceptance" \
  --evidence YOUR_ACCEPTANCE_RECORD
```

`5,000,000` is the user's previously approved USD 5 Gemini allowance. Edit
`results/hosted-stage-caps.json` with measured stage limits first. The pipeline
provider operation cap times its call count must fit the provider allowance. Check
the printed plan, then rerun the same command with `--execute` to write the ledger
configuration. Run `status --execute` again; confirm the allowance and caps, and
confirm the ledger remains paused.

Before resuming, verify the Eventarc trigger exists and targets the current API.
Inspect queued operations and ensure every queued item is an intentional test;
resuming emits dispatch signals and can start queued jobs immediately. Review the
resume plan without `--execute`:

```bash
uv run --locked python -m manga_worker.cloud_operator resume \
  --actor YOUR_GOOGLE_ACCOUNT \
  --reason "Run approved hosted manual acceptance" \
  --evidence YOUR_ACCEPTANCE_RECORD
```

If the plan is correct and the queue is clear except for the intended test, rerun
with `--execute`. Verify `/production/status` reports unpaused before submitting
one test. The user initiates and observes all paid Gemini calls. Pause again after
the test using `cloud_operator pause` with the same audit fields and `--execute`.
Keep recovery and GC schedulers paused unless their separate acceptance requires
them; normal dispatch is Eventarc driven. A Cloud Billing alert budget is not a
hard spending cap, and billing reports may be delayed, so retain the application
limits and monitor GCP charges during the test.

The user performs admin extraction and optional authorized AI planning manually,
then reviews cast, sources and exact scripts before short synthesis. Follow the
[audio workflow](../../resources/AUDIO_WORKFLOW.md); loading a proposal does not
approve it. The agent must not initiate paid calls. Record operation IDs, UTC start/end,
expected/actual behavior, retries and any error. Verify SSE status, disconnect/reload
recovery without duplicate enqueue, session revocation, draft retention and published
playback. Publication still requires approval of the exact reviewed export.

## 6. Capture logs and request read-only review

After the user provides the real test window, replace the sample timestamps and
choose a new output directory (the helper rejects an existing output directory):

```bash
uv run --locked python tools/capture_hosted_logs.py --project koetts-9bf7f --region us-central1 --since 2026-11-02T00:00:00Z --until 2026-11-02T00:15:00Z --output results/manual-production-UNIQUE
```

This captures private API, `koetts-magi`, `koetts-pipeline`, `koetts-artifact-gc`
and the `koetts` frontend in `us-east4`. It writes private `logs.json` and
`summary.json`. It does not capture Eventarc/Scheduler delivery configuration or
prove final billing/model cost; collect their metadata separately when relevant.

The agent reviews live configuration read-only, verifies revisions/digests, private
IAM, budgets/pauses and selected logs against the completed checklist, then reports
pass/fail/pending evidence. Do not declare production acceptance from a successful
build alone. At campaign end explicitly pause new production and scheduling as
agreed, inspect all existing executions, and retain delayed billing follow-up.

## Recovery

Pause admission and scheduling first. Restore the captured compatible API/frontend
revisions or immutable job images through reviewed commands/plans. Verify published
playback, login and durable state. Never reset Firestore/GCS or recreate signing
secrets to obtain a clean deployment. Unknown provider outcomes require explicit
reconciliation before retry; do not resubmit paid work automatically.

## API-only Eventarc audience fix

Run the following blocks from the repository root in the same Bash terminal.
These commands build and deploy the reviewed local API source. They preserve job
image references and create private backups. The existing queued extraction may
start when Eventarc retries after deployment; do not submit another upload.

### Build and update the private API digest

```bash
set -euo pipefail
cd /home/ssuish/projects/manga-to-audio-book-project
umask 077
deployment_dir="$PWD/results/eventarc-api-fix-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 700 "$deployment_dir"
cp infra/hosted/phase5.auto.tfvars.json "$deployment_dir/tfvars-before.json"
cp infra/hosted/terraform.tfstate "$deployment_dir/terraform.tfstate-before"
git rev-parse HEAD > "$deployment_dir/commit.txt"
git diff --binary HEAD > "$deployment_dir/source.patch"
api_tag="eventarc-fix-$(date -u +%Y%m%dT%H%M%SZ)"
api_image="us-central1-docker.pkg.dev/koetts-9bf7f/koetts-hosted/koetts-api:$api_tag"
build_id="$(gcloud builds submit --project=koetts-9bf7f --suppress-logs   --config=cloudbuild.s3.yaml --substitutions="_IMAGE=$api_image"   --format='value(id)' .)"
gcloud builds describe "$build_id" --project=koetts-9bf7f   --format=json > "$deployment_dir/build.json"
.venv/bin/python - "$deployment_dir/build.json" "$api_image" <<'PYTHON'
import json
import os
from pathlib import Path
import re
import sys

build = json.loads(Path(sys.argv[1]).read_text())
if build.get("status") != "SUCCESS":
    raise SystemExit("Build did not succeed; Terraform inputs unchanged.")
images = [image for image in build["results"]["images"] if image["name"] == sys.argv[2]]
if len(images) != 1 or not re.fullmatch(r"sha256:[a-f0-9]{64}", images[0]["digest"]):
    raise SystemExit("Expected exactly one API image digest; Terraform inputs unchanged.")
path = Path("infra/hosted/phase5.auto.tfvars.json")
settings = json.loads(path.read_text())
settings["api_image"] = sys.argv[2].rsplit(":", 1)[0] + "@" + images[0]["digest"]
temporary = path.with_suffix(".json.tmp")
with temporary.open("x", encoding="utf-8") as output:
    os.chmod(temporary, 0o600)
    output.write(json.dumps(settings, indent=2) + "\n")
os.replace(temporary, path)
print("API image:", settings["api_image"])
PYTHON
```

### Generate and review a fresh plan

```bash
terraform -chdir=infra/hosted fmt -check
terraform -chdir=infra/hosted validate
terraform -chdir=infra/hosted plan -out="$deployment_dir/api-fix.tfplan"
terraform -chdir=infra/hosted show -no-color "$deployment_dir/api-fix.tfplan"   > "$deployment_dir/plan.txt"
cat "$deployment_dir/plan.txt"
```

Expect one in-place API image update and zero additions or deletions. Investigate
other actions before proceeding. This fresh plan replaces the earlier stale-image
plan; do not reuse that already-applied plan.

### Apply the reviewed plan and inspect delivery

```bash
terraform -chdir=infra/hosted apply "$deployment_dir/api-fix.tfplan"
gcloud run services describe koetts-api --project=koetts-9bf7f   --region=us-central1   --format='json(status.latestReadyRevisionName,status.traffic,spec.template.spec.containers[0].image)'
gcloud logging read   'resource.type="cloud_run_revision" AND resource.labels.service_name="koetts-api" AND httpRequest.requestUrl:"/internal/operation-events"'   --project=koetts-9bf7f --freshness=10m --limit=10   --format='table(timestamp,httpRequest.status)'
gcloud run jobs executions list --project=koetts-9bf7f   --region=us-central1 --job=koetts-magi --limit=3
printf 'Deployment evidence: %s\n' "$deployment_dir"
```

Compare the serving digest with the API image printed in the first block. Inspect
new delivery timestamps: old 401 records remain in the log window. A successful
event response alone does not prove extraction completion. Provide the evidence
directory and observed result for agent log review. These commands do not invoke
Gemini, change budget caps, or resume schedulers.
