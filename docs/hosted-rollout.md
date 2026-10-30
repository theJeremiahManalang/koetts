# Hosted rollout preparation and rollback

This runbook prepares evidence for a later hosted rollout. It does not authorize
cloud changes, assert that resources exist, or claim that deployment or acceptance
has succeeded. Phase 4 budget reservations, alerts, production pause controls,
quota visibility, and reference-aware seven-day cleanup remain pending until
their implementation and acceptance evidence are reviewed.

## Offline preparation

Use the existing Firebase project `koetts-9bf7f`, Firestore database
`koetts-default`, and region `us-east4`. A clean cloud dataset is required, but
no dataset, artifact bucket, or artifact namespace has been provisioned by this
preparation. Confirm their exact names through the authorized provisioning task;
do not infer a name from local configuration. Capture actual prior web and API
serving revisions and immutable prior `magi` and `pipeline` job image digests.
For a service or job that preflight confirms is absent, record `ABSENT` and its
first-creation rollback procedure. Never copy example revisions from old runbooks
without reconfirming current serving state.

Before creating a record:

1. Review current source and acceptance results. Check `git status` and use the
   intended candidate checkout; the record captures its current `HEAD` and dirty
   state, including status entries.
2. Capture the target project, database, region, clean dataset, bucket, and
   canonical artifact namespace. These are operator assertions; the offline tool
   does not inspect Google Cloud or validate resource existence.
3. Capture rollback targets from live preflight evidence. The web and API values
   must identify actual prior serving revisions. Job values must be immutable
   image digests. `ABSENT` means preflight confirmed no prior resource exists.
4. Choose evidence paths for preflight configuration, access/IAM review,
   offline acceptance, rollout verification, cost/budget controls, cleanup safety,
   and rollback verification. Keep credentials and tokens out of these files.
5. Ensure the output parent directory already exists and is outside results,
   application data, caches, dependencies, and credential directories. The tool
   creates a JSON file only if the output path does not already exist.

Run `uv run python tools/hosted_rollout_record.py --help` to inspect the offline
CLI arguments. Supply every target and rollback value explicitly, repeat
`--evidence-path` for each evidence file, and choose a new `--output` path. The
tool records the candidate SHA, clean/dirty state, supplied values, UTC record
time, and a `pending` verification status. It performs local Git reads and one
exclusive file create; it makes no network or cloud calls. A dirty candidate is
recorded as dirty, not rejected. Review and preserve the exact record with the
rollout evidence.

## Rollout gate and live verification

No live rollout command is specified here. Follow the separately authorized,
service-specific canonical procedure after approval for the exact target and
scope. Before acting, refresh web/API/job serving state, IAM, Firestore rules,
bucket state, billing controls, and the operator-supplied rollback targets.
Confirm the captured candidate matches the source intended for that rollout.
Keep frontend-only mode and production pause controls in force until all
separately required hosted acceptance evidence passes.

Verify and record actual deployed image digests/revisions, configuration, narrow
IAM bindings, readiness and denial cases, restart recovery, session revocation,
authenticated playback, measured workload limits and costs, budget reservations
and alerts, pause behavior, and reference-aware cleanup. File paths in the
preparation record are evidence locations, not proof that those checks ran or
passed. Keep login and published playback available when production is paused.

## Compatibility and rollback

Keep persisted Firestore records and GCS objects readable by the prior serving
web/API/jobs revisions for the full rollback window. Prefer additive fields and
backward-compatible readers and writers. Before any schema or serialization
change, demonstrate that the previous revision can read and recover state written
by the candidate. If that property is unproven, stop before promotion; do not
depend on rollback across an incompatible write.

For rollback, first pause new production admission and dispatch while preserving
login and published playback. Then restore traffic/images and task-owned IAM or
configuration using the captured target-specific procedure. Verify restored
service behavior and record the resulting state. Keep Firestore and GCS durable
data, accepted artifacts, reference records, and evidence intact. Never reset,
truncate, recreate, or delete the production dataset or bucket as a rollback
shortcut. For a first-created service/job marked `ABSENT`, remove only the
candidate resource and task-added grants after verifying containment; preserve
pre-existing identities and all durable data.

Rollback completion requires evidence that production is paused, previous
software is serving (or a new resource is contained), login and published
playback remain available, durable state remains present and readable, and
task-owned access changes are reconciled. A successful command alone does not
establish rollback acceptance.
