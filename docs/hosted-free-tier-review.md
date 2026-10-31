# Hosted Terraform free-tier assessment

Reviewed on 2026-10-31 against `infra/hosted/main.tf`, `variables.tf`, current
official pricing, and one read-only Firestore metadata query. The requested API
service default is now `koetts-api`. No resources were applied, services retired,
container builds started, or inference/provider calls made.

## Conclusion

The configuration is suitable for a small paid pilot with free allowances; it is
not constrained to free-tier usage. The artifact bucket now defaults to `us-central1` independently of the service
region, following the user's placement decision. Neither job count nor retained
artifact size is capped monthly.
The existing web frontend and older API also consume resources outside this
Terraform configuration. Current billing-account usage and remaining allowances
were not measured, so a zero-dollar bill cannot be established.

## Cloud Run compute

`us-central1` has Tier 1 pricing. Monthly request-based allowances are 180,000
vCPU-seconds, 360,000 GiB-seconds and two million requests. Jobs have 240,000
vCPU-seconds and 450,000 GiB-seconds; usage is aggregated by billing account.
Jobs incur at least one billed minute. [Cloud Run pricing](https://cloud.google.com/run/pricing).

The following arithmetic uses configured resource allocations for an illustrative
30-minute billed task. It is not a measured execution or monthly entitlement.
Startup, other runs and existing workloads need additional allowance.

| Resource | Configuration | vCPU-seconds / 30 minutes | GiB-seconds / 30 minutes |
| --- | --- | ---: | ---: |
| API | 1 CPU, 512 MiB; min 0, max 1; request-based | Usage-dependent | Usage-dependent |
| Magi | 4 CPU, 8 GiB; one task, retries 0 | 7,200 | 14,400 |
| Pipeline | 2 CPU, 4 GiB; one task, retries 0 | 3,600 | 7,200 |
| Collector | 1 CPU, 512 MiB; one task, retries 0 | 1,800 | 900 |

Thirty-two full-length Magi attempts alone use 460,800 GiB-seconds, exceeding
the job memory allowance. A daily collector running for all 30 minutes uses
55,800 vCPU-seconds and 27,900 GiB-seconds in a 31-day month. Application retries
are separate paid attempts despite zero platform retries. Five distinct chapters
per month is not a cap on operations, replacements, stages or retries.

Both Scheduler triggers start paused. If enabled, the coordinator invokes the API
44,640 times in a 31-day month, in addition to user traffic. Scale-to-zero and one
instance reduce idle cost and concurrency; they do not limit cumulative runtime.
Coordinator Firestore queries, worker heartbeats, artifact scans and publication
reads also count toward their respective usage allowances.

## Storage and other services

The bucket uses STANDARD storage in `var.artifact_bucket_location`, default
`us-central1`. This is an eligible location for the 5 GB-month storage allowance,
subject to shared usage and other pricing conditions. Services and jobs also default to
`us-central1`, eliminating the planned bucket-to-worker region mismatch. The
frontend initially remains in `us-east4`; its API traffic can incur cross-region
network charges until migration. Eligible placement alone does not guarantee
free delivery.
[Cloud Storage pricing](https://cloud.google.com/storage/pricing).

This changes only new bucket configuration. No existing bucket was relocated or
created. The earlier `us-east4` storage exclusion is resolved for the default new
artifact bucket, while compute, operation, storage-volume and transfer limits
still need measured usage evidence.

See [ancillary service source review](hosted-free-tier-sources.md) for Firestore,
Scheduler, Pub/Sub retention, Secret Manager, build/image storage and App Hosting.
Firestore metadata currently reports `freeTier: true` for `koetts-default` in
`nam5`; this reports database eligibility, not remaining free reads or storage. Firebase
documentation corroborates first-database eligibility regardless of ID, while a
Google Cloud pricing paragraph disagrees; the source review records this discrepancy.

## Budget controls and next decisions

The Terraform USD 20 budget sends alerts at USD 10, 15 and 20. It configures no
native spend-cap enforcement. The application conservatively pauses new production
at USD 15 reported cost plus retained reservations; it does not stop playback,
builds, storage, existing executions or every cloud service. Alert-only budgets
are not automatic spending ceilings. [Budget documentation](https://docs.cloud.google.com/billing/docs/how-to/budgets).

Before making a free-tier claim, confirm the selected bucket location,
measure representative CPU job duration and retained bytes, inspect existing
billing-account consumption, and set conservative operation caps from that evidence.
Keep schedules paused until the separately authorized rollout passes. Do not lower
Magi CPU/memory blindly: CPU quality and performance remain launch gates.


Google now also documents service-specific native spend-cap budgets, including
Cloud Run, but these are not present in this Terraform. Such a cap can pause new
requests across the project's Cloud Run service, affect reader availability, and
still allow latency-related overage and in-flight work. Adding one requires a
separate availability decision rather than silently replacing the application's
production-only pause. [Native spend-cap documentation](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps).
