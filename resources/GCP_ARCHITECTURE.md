# GCP architecture — phase 5 hosted infrastructure

This is the intended deployment topology, not evidence that phase 5 is deployed.
It reflects the latest placement decisions: new API, jobs, Scheduler and artifact
storage in `us-central1`; existing frontend in `us-east4` initially, followed by
its planned migration to `us-central1`. The existing Firestore database remains
in `nam5`. Live rollout and paid validation still require separate authorization.

## Application and data paths

Solid connections show intended application calls or data access. The API is
private: the browser reaches it through the Next.js server, using independent
service and Firebase user credentials. Project-scoped managed services appear
outside the regional boxes because this diagram does not assign them a regional
location. Resource names without a fixed value are selected during preflight.

```mermaid
flowchart TB
    user["Reader or admin browser"]
    provider["Gemini inference: us endpoint<br/>Gen AI SDK enterprise mode + ADC<br/>Pipeline identity only"]

    subgraph project["Firebase / GCP project: koetts-9bf7f"]
        auth["Firebase Authentication<br/>Google sign-in and user verification"]
        secrets["Secret Manager<br/>Frontend audio signing key"]

        subgraph east["us-east4: existing frontend initially"]
            web["Firebase App Hosting: koetts<br/>Next.js server<br/>1 CPU / 512 MiB; min 0, max 2"]
        end

        subgraph central["us-central1: new hosted backend"]
            api["Private Cloud Run service: koetts-api<br/>HTTP API and coordinator<br/>1 CPU / 512 MiB; min 0, max 1"]
            dispatch["Cloud Scheduler: hosted-coordinator<br/>Every minute; initially paused"]
            magi["Cloud Run Job: koetts-magi<br/>CPU extraction / OCR<br/>4 CPU / 8 GiB"]
            pipeline["Cloud Run Job: koetts-pipeline<br/>Planning, synthesis and export<br/>2 CPU / 4 GiB"]
            gcSchedule["Cloud Scheduler: hosted-artifact-gc<br/>Daily 03:00 UTC; initially paused"]
            gc["Cloud Run Job: koetts-artifact-gc<br/>Reference-aware collection<br/>1 CPU / 512 MiB"]
            bucket[("Private GCS artifact bucket<br/>Dedicated managed-folder namespace<br/>Exact generations and SHA-256")]
        end

        subgraph database["nam5: existing database"]
            firestore[("Firestore: koetts-default<br/>Clean hosted and shared namespaces<br/>Revisions, operations, quotas, budget and GC state")]
        end
    end

    user -->|"HTTPS, uploads, catalog and audio ranges"| web
    user -->|"Google sign-in"| auth
    web -->|"Session and user verification"| auth
    web -->|"Service ID token plus user credential"| api
    api -->|"Revocation and user verification"| auth
    secrets -->|"Signing key: frontend only"| web
    dispatch -->|"OIDC: private coordinator endpoint"| api
    api -->|"Dispatch and reconcile"| magi
    api -->|"Dispatch and reconcile"| pipeline
    api -->|"Metadata and transactions"| firestore
    magi -->|"Claims, heartbeats and checkpoints"| firestore
    pipeline -->|"Claims, heartbeats and checkpoints"| firestore
    api -->|"Create and read exact artifacts"| bucket
    magi -->|"Read sources; create artifacts"| bucket
    pipeline -->|"Read and create artifacts"| bucket
    pipeline -->|"ADC identity; budget-authorized calls"| provider
    gcSchedule -->|"OAuth: run only collector job"| gc
    gc -->|"Reference roots and maintenance barrier"| firestore
    gc -->|"Delete only eligible unreferenced generations"| bucket

    classDef existing fill:#e8f0fe,stroke:#3367d6,color:#172b4d;
    classDef planned fill:#e6f4ea,stroke:#188038,color:#173b24;
    class web,auth,firestore existing;
    class api,dispatch,magi,pipeline,gcSchedule,gc,bucket,secrets planned;
```

Blue nodes are existing services; green nodes are planned resources. Their arrows
describe the complete hosted path after acceptance, not the frontend's current
frontend-only mode. App Hosting includes its managed edge/CDN infrastructure,
which is collapsed into the frontend node for readability.

Published audio travels from private GCS through the API and the same-origin
frontend response to the browser. Every audio and range request checks the session
and publication. There is no public bucket or shareable GCS signed download URL.
Browser Firestore access is denied; backend SDK access uses IAM. Application
quotas, ownership and admin checks still apply inside the API.

Each job has one task, parallelism one, zero platform retries and a 30-minute
attempt timeout. The application allows at most three attempts and one global
slot per production stage. An uncertain provider outcome holds capacity until
reconciled; it does not trigger a blind paid retry. The collector removes only
unreferenced temporary artifacts older than seven days, preserving accepted and
referenced artifacts.

## Billing and operational controls

This diagram expands the API and Firestore roles shown above. Billing notification
delivery is asynchronous. The budget is project-filtered and alert-only; the
application's production pause preserves identity and published playback.

```mermaid
flowchart LR
    billing["Cloud Billing<br/>Project-filtered USD 20 budget includes Gemini<br/>Alerts at USD 10 / 15 / 20"]
    topic["Pub/Sub topic<br/>koetts-hosted-billing"]
    push["Authenticated push subscription<br/>koetts-hosted-billing-push"]
    api["koetts-api<br/>Billing report validation<br/>Production admission and claims"]
    ledger[("Firestore budget ledger<br/>Reports, reservations, provider debits<br/>Pause, settlement and audit records")]
    admin["Verified admin<br/>Frontend pause / resume controls"]
    operator["Developer operator CLI<br/>Explicit allowance configuration<br/>Settlement and reconciliation"]
    production["New extraction and generation<br/>Allowed only after budget admission"]
    reads["Login and published playback<br/>Remain available during production pause"]

    billing -->|"Budget reports"| topic
    topic --> push
    push -->|"Verified OIDC identity"| api
    api <-->|"Atomic budget checks and reports"| ledger
    admin -->|"Verified service and admin credentials"| api
    operator -->|"Audited developer actions"| ledger
    api -->|"Reject when paused or allowance exhausted"| production
    api -->|"Pause does not gate published reads"| reads
```

New production pauses at USD 15 reported project cost plus conservative retained
reservations, or earlier when an admission would exhaust allowance. The project
budget includes Gemini; the separate application provider allowance controls
admission and does not change billing attribution. These controls do not guarantee
a monthly bill ceiling:
builds, retained storage, playback and existing executions can continue charging.

## Staged frontend migration

The final target includes a frontend in `us-central1`. Keeping the current frontend
initially avoids combining backend acceptance with the frontend region cutover.
The existing `koetts-s3-api` remains the authentication verification target until
the new API is accepted and callers move; it is not a component of the final
production topology.

```mermaid
flowchart LR
    current["Current live state<br/>Frontend: us-east4<br/>Verification API: koetts-s3-api, us-east4"]
    initial["Phase 5 initial target<br/>Frontend: us-east4<br/>koetts-api, jobs and GCS: us-central1"]
    gate["Frontend migration gate<br/>New regional App Hosting backend<br/>Verify identity, origin, sign-in,<br/>audio playback and rollback"]
    final["Expected final target<br/>Frontend, koetts-api, jobs and GCS: us-central1<br/>Firestore remains nam5"]

    current -->|"Deploy and verify backend; update frontend API setting"| initial
    initial -->|"Prepare regional frontend replacement"| gate
    gate -->|"Cut over only after acceptance"| final
```

The initial frontend-to-API path crosses regions. Co-locating API/jobs and GCS
removes the intended bucket-to-worker region mismatch; it does not make every
service or transfer free. The later frontend backend may have a different generated
website URL and runtime identity. Capture actual values and verify Firebase
authorized domains, public origin, session behavior, API invocation and secret
access before redirecting users. Preserve the old frontend until rollback is
proven. No current website URL is changed by these diagrams.

## Configuration and ownership map

| Component | Configuration or source of truth |
| --- | --- |
| New regional compute and Scheduler | `infra/hosted/variables.tf`: `region = "us-central1"` |
| New artifact storage | `artifact_bucket_location = "us-central1"`; explicit bucket name and namespace required |
| API name and identity audience | `api_service_name = "koetts-api"`; `canonical_api_url` must match actual deployed URL |
| Dedicated workload identities and IAM | `infra/hosted/main.tf`; runtime GCS create/read versus collector read/delete grants |
| Existing frontend | `apps/web/apphosting.yaml`, `firebase.json` and deployed App Hosting backend; outside Terraform management |
| Existing Firestore | `firestore_database_id = "koetts-default"`; Terraform does not create or relocate the database |
| Gemini identity and signing secret | Pipeline uses Gen AI SDK enterprise mode and ADC with inference IAM; frontend signing value/version remains a separate operator input |
| Immutable container images | Explicit `api_image`, `magi_image`, `pipeline_image` digests; image builds and registry setup are outside this Terraform |

IAM limits Firestore workload access to the named database, not individual
collections. Application ownership, namespace bindings, fencing and admin checks
provide the finer boundaries. The frontend identity, production workers,
coordinator caller, billing push caller, collector caller, collector and operator
have distinct permissions; the diagram groups these identities into their workloads.

See [infrastructure configuration](../docs/resources/hosted-infrastructure.md),
[hosted plan](../docs/plans/hosted-service-plan.md), [rollout and migration](../docs/resources/hosted-rollout.md),
[cost controls](../docs/resources/hosted-cost-controls.md), and [free-tier assessment](../docs/research/hosted-free-tier-review.md).
