# Hosted GCP and Firebase free-tier source notes

Official pricing documentation checked 2026-10-31. These are pricing allowances,
not proof of this project's live billing configuration, current usage, or a zero
bill. Google can change offers; recheck the linked product pages before a rollout
or cost estimate.

## Allowances and applicability

| Service | Official no-cost allowance and conditions | Relevance to this Terraform scope |
| --- | --- | --- |
| **Firestore Standard** | One free database per project, with 1 GiB stored data, 50,000 document reads/day, 20,000 writes/day, 20,000 deletes/day, and 10 GiB/month outbound transfer. The daily quotas reset around midnight Pacific. The pricing page says named (non-default) databases require billing and **do not qualify** for this free quota. [Firestore pricing](https://cloud.google.com/firestore/pricing) | `firestore_database_id` defaults to `koetts-default`; variables require a named database rather than `(default)`. However, a task-owner read-only `gcloud firestore databases list --project=koetts-9bf7f --format=json(name,locationId,type,freeTier)` observation on 2026-10-31 reported only this database (`nam5`, `FIRESTORE_NATIVE`) and `freeTier=true`. The [Firebase billing guide](https://firebase.google.com/docs/firestore/pricing#free-quota) says the first database qualifies regardless of ID, consistent with that live field but contrary to the Google Cloud pricing paragraph. This is a documentation discrepancy, not evidence that a database migration is required. The observation did not check remaining usage or charges. |
| **Secret Manager** | Monthly, aggregated across projects by billing account: 6 active secret versions, 10,000 access operations, and 3 rotation notifications free. Enabled **and disabled** versions count as active; destroyed versions do not. Management operations are free. [Secret Manager pricing](https://cloud.google.com/secret-manager/pricing) | Terraform now defines one audio-signing secret container and access binding, but no secret-version resources. Gemini uses pipeline service identity rather than a provider-key secret. The runtime variables require explicit version IDs, so version payload creation is a separate step. A signing-key version fits within the six-version allowance only if other projects' use on that billing account leaves room. |
| **Cloud Scheduler** | Three jobs per month free per billing account; additional jobs cost $0.10 per job per 31 days. A paused job still counts. Billing is by job, not executions. [Cloud Scheduler pricing](https://cloud.google.com/scheduler/pricing) | Terraform defines two paused jobs (`hosted-artifact-gc`, `hosted-coordinator`). They count as two jobs even while paused; they fit under the allowance only if the same billing account has at most one other billable Scheduler job. |
| **Pub/Sub** | Basic Message Delivery throughput is free for the first 10 GiB each calendar month per billing account. This is throughput, not message storage. Topic retention, acknowledged-message retention, and certain old unacknowledged backlogs incur storage charges at the published storage rate; cross-zone/region data transfer may also apply. [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing) | Terraform sets both topic retention and subscription retention to 604800 seconds (7 days). Topic retention can incur storage charges for retained published messages; the 10 GiB throughput allowance does not waive them. Subscription storage charges can also apply for unacknowledged messages older than one day, except while already retained by the topic. Actual charges depend on volume and location. |
| **Artifact Registry** | 0.5 GiB-month storage free per billing account; usage across projects attached to that account shares the limit. [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing) | This file enables the API but defines no repository. The allowance is relevant only if another workflow creates/uses a repository; it is not a per-repository allowance. |
| **Cloud Build** | 2,500 build-minutes/month per billing account, only for `e2-standard-2` builds in the default pool. The allowance is promotional and Google says it may change. [Cloud Build pricing](https://cloud.google.com/build/pricing), [Google Cloud Free Tier limits](https://docs.cloud.google.com/free/docs/free-cloud-features) | This file defines no Cloud Build resource or build execution. Do not count private-pool builds or other machine types as covered by these free minutes. |
| **Firebase App Hosting** | Requires the Blaze pay-as-you-go plan. Its published no-cost limits include 10 GiB/month outgoing bandwidth; Artifact Registry 0.5 GB storage; Cloud Run 180,000 vCPU-seconds, 360,000 GiB-seconds, and 2 million requests; Cloud Build 2,500 build-minutes; Cloud Logging 50 GiB/month and 30-day log retention; and Secret Manager 6 active versions, 10,000 access operations, 3 rotations. The no-cost amounts are aggregated across projects by billing account and reset monthly. App Hosting's Cloud Storage allowance (5 GB-months, 5,000 Class A and 50,000 Class B operations, 100 GB North America transfer to eligible destinations) applies only when deploying local source/archive and only to App Hosting backends in `us-central1`. [App Hosting costs](https://firebase.google.com/docs/app-hosting/costs) | The repository has an existing frontend outside this Terraform file; that alone does not establish an App Hosting backend or deployment. These allowances apply only if the frontend actually uses App Hosting on Blaze. Terraform now defaults new API/jobs and artifact storage to `us-central1`. The existing frontend stays in `us-east4` until a separate migration; the Terraform region does not move it or qualify its source/archive storage for the App Hosting-specific allowance. App Hosting usage over allowances can bill. |

## Cross-cutting billing caveats

- Google Cloud Free Tier requires an active, good-standing Cloud Billing account;
  negotiated pricing/custom rate cards can affect eligibility. Most listed GCP
  allowances are shared across projects on the same billing account, so this
  project's remaining allowance cannot be inferred from its Terraform alone.
  [Free Tier eligibility and limits](https://docs.cloud.google.com/free/docs/free-cloud-features)
- A free allowance is not a project spending cap. Usage above limits is billed
  on a paid billing account. Firebase Blaze enables pay-as-you-go billing;
  budget alerts notify and do not themselves cap charges. [Firebase billing
  plans](https://firebase.google.com/docs/projects/billing/firebase-pricing-plans)
- App Hosting specifically requires Blaze, even where usage remains inside its
  published no-cost allowances. Having a Firebase frontend in the repository
  does not prove App Hosting is the deployed host. [App Hosting costs](https://firebase.google.com/docs/app-hosting/costs)
- Terraform evidence above describes configured resources only. It cannot prove
  which billing account is linked, whether resources already exist outside this
  file, total account-level usage, actual service traffic, or realized charges.

## Evidence inspected

- `infra/hosted/variables.tf`: named Firestore database default `koetts-default`;
  Terraform rejects `(default)`.
- Task-owner read-only Firestore database list on 2026-10-31: only
  `koetts-default` in `nam5`, `FIRESTORE_NATIVE`, with `freeTier=true`.
  Remaining usage was not checked. Firebase documentation agrees that the first
  database qualifies regardless of ID; the Google Cloud pricing paragraph differs.
  No source establishes remaining no-cost capacity.
- `infra/hosted/main.tf`: one Secret Manager container and no secret-version
  resource; two Cloud Scheduler jobs with `paused = true`; Pub/Sub topic and
  subscription each set to 604800-second retention; Artifact Registry API
  enabled, with no repository or Cloud Build resource in this file.
- Frontend hosting configuration is outside this Terraform scope. Apart from
  the database-list observation above, this research did not inspect live cloud
  resources or query billing/usage.
