# Hosted rollout preparation and rollback

This runbook prepares evidence for a later hosted rollout. It does not authorize
cloud changes, assert that resources exist, or claim that deployment or acceptance
has succeeded. Phase 4 budget reservations, alert configuration, production pause controls,
quota visibility, and reference-aware seven-day cleanup passed offline review and
acceptance. Deployed behavior and actual billing delivery remain unverified.

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

### Offline prior-reader acceptance

Run `uv run python -m unittest tests.integration.test_cloud_rollback -v` with
`FIRESTORE_EMULATOR_HOST` pointing to a loopback emulator. This test archives the
fixed prior reader source at `fef5b8add2e22dd98e45283aa7ddbd600a5f3609` without
checking it out over the candidate tree. It seeds candidate project/export and
approved shared review/publication records, a durable operation checkpoint and
budget reservation/debit, pauses the ledger, then injects an uncertain
exact-generation GC delete. The prior HTTP API must read the project snapshot,
catalog and exact published bytes while its service permission map denies
enqueue and coordination. Full hosted/shared Firestore document trees, the held
maintenance barrier, GC run log, and published object generation/bytes must stay
unchanged. The candidate reader must then recover the original deletion chain.

This is offline compatibility evidence only. It uses loopback Firestore, a
frozen fake GCS bucket, and injected service/user verifiers; it does not validate
Firebase identity, Next.js session handling, deployed IAM, Cloud Run execution
status, or live storage behavior. A prior reader can serve snapshots and
published audio but does not understand the candidate GC promotion epoch,
maintenance recovery records, or budget ledger. It cannot safely recover GC,
resume production, or change provider controls. For a real rollback, pause
production dispatch and GC scheduling, confirm workers and collector executions
are stopped, and resolve any held GC barrier with a compatible candidate
revision before serving the prior API. Keep production paused until a compatible
revision with the required GC and provider controls is restored and verified.


### Read-only preflight — 2026-10-30

Cloud Run list/describe queries against `koetts-9bf7f`, `us-east4` returned:

- App Hosting service `koetts` serves 100% traffic from
  `koetts-build-2026-10-21-002`; older tagged revisions also exist.
- Private API `koetts-s3-api` already exists and serves revision
  `koetts-s3-api-00001-gl5`. Its resolved image is
  `us-east4-docker.pkg.dev/koetts-9bf7f/firebaseapphosting-images/koetts-s3-api@sha256:bd5cf2fac59d9733ee408d847eb80b6795ab9c40b7840534b06163d336a43cc2`.
- The regional Cloud Run jobs list is empty.

These observations are timestamped preparation, not immutable rollout targets;
refresh them before deployment. The user selected `koetts-proto-api` as the replacement service name. The
infrastructure default now uses that name. The existing `koetts-s3-api` remains
the live frontend authentication target until a verified cutover; it is not
adopted into Terraform or deleted by this configuration. Refresh preflight for
both names before deployment and preserve the existing API until its callers
have moved successfully.

The Docker command resolves to a Windows Docker Desktop shim but cannot contact
an engine from this WSL distribution. Local container builds are therefore not
currently available. An authorized build must use a working local engine or an
explicitly approved remote build path with its costs included in the test cap.
No builds, deployments, paid inference, IAM changes, or secret reads occurred in
this preflight. Ordinary CLI credential/log-cache access required sandbox
escalation; the read-only cloud queries succeeded.


### Preferred API name and retirement scope — 2026-10-31

The replacement service name is `koetts-proto-api`. This is a service replacement,
not an in-place rename. A read-only check confirms that live `koetts` still uses
`S3_API_URL=https://koetts-s3-api-gu5jb64hpq-uk.a.run.app` and frontend-only mode.
The existing API uses verification mode, the recorded immutable image above,
1 CPU / 512 MiB, maximum one instance, and the existing dedicated runtime identity.
Its service invocation policy grants the App Hosting runtime identity access.

The reviewable cutover scope is:

1. Capture the old service configuration, invocation policy, image and frontend
   revision as rollback evidence, excluding credentials from committed records.
2. Create private `koetts-proto-api`, configure its actual canonical audience and
   intended runtime identity, and validate readiness plus credential-denial cases.
3. Update the frontend URL through a reviewed App Hosting rollout. Preserve
   frontend-only guards for an authentication-only replacement; full production
   activation still requires the hosted phase 5 acceptance gates.
4. Verify frontend authentication diagnostics and confirm no active caller targets
   the old service before deleting it. Retain the old runtime identity and image
   unless separately proven unused; service retirement does not authorize deleting
   shared identities, artifacts, Firestore data, or buckets.
5. Recheck that the old service is absent, the replacement is private and healthy,
   and the frontend uses the replacement. Record serving revisions and checks.

Do not rewrite the checked-in frontend URL to an unverified endpoint ahead of
this sequence. The user's service-name request selects the replacement name;
full hosted deployment, paid inference, and provider tests remain separately
controlled. No cloud mutation has been performed for this preference change.
