# Production deployment and acceptance checklist

Use with [manual deployment](manual-production-deployment.md). An unchecked item is
pending; a successful command is not proof of user-flow acceptance. No deployment is recorded as completed by this template. Limited teardown
completed on 2026-11-02; evidence is private under
`results/compute-teardown-20261102/`. Generate a fresh refreshing plan before redeployment.

## Campaign record

- Operator / reviewer:
- Candidate commit / dirty source manifest:
- UTC start / end:
- Private evidence directory:
- Approved build/infrastructure allowance / remaining estimate:
- Manual Gemini allowance / measured stage and call caps:
- Prior API/frontend revisions and job digests:
- Final API/frontend revisions and job digests:
- Build IDs / App Hosting rollout ID:
- Teardown decision / exact reviewed resource list and plan (or unnecessary):
- Teardown readiness / execution evidence: completed 2026-11-02; private evidence directory above.

For each item, replace `Actual: pending` with observations and a pass/fail decision;
use evidence paths or IDs without secrets or tokens.

## Preparation and protected state

- [x] Expected: pinned Node22/npm10/uv and full local checks pass.
  Actual: pending. Evidence:
- [x] Expected: state, backups and private tfvars secured; correct existing dataset,
  bucket/namespace, identities, billing IDs and signing versions retained.
  Actual: pending. Evidence:
- [x] Expected: refreshed live baseline and rollback targets captured; active
  executions positively identified; production/provider ledger and schedules paused.
  Actual: pending. Evidence:
- [x] Expected: limited teardown, if selected, removes only `koetts-api`, jobs
  `koetts-magi`, `koetts-pipeline`, `koetts-artifact-gc`, and schedulers
  `hosted-coordinator`, `hosted-artifact-gc`; preserves frontend `koetts` and old API `koetts-s3-api`; preserves all durable data, secrets, identities and budget resources.
  Actual: pending. Evidence:

## Build, plan and deployment

- [x] Expected: backend build succeeds from candidate; API/magi/pipeline immutable
  digests recorded and assigned to correct private Terraform inputs.
  Actual: pending. Evidence:
- [x] Expected: exact saved plan reviewed; data/secret/identity/budget resources
  preserved; deletion protection changes individually reviewed if required.
  Actual: pending. Evidence:
- [x] Expected: Firestore and Eventarc source `nam5`; API/jobs/bucket `us-central1`;
  existing frontend `us-east4`.
  Actual: pending. Evidence:
- [x] Expected: applied saved plan matches reviewed candidate; ready API/job images
  match digests; no public invoker; actual URL/audience match; event filter is scoped.
  Actual: pending. Evidence:
- [x] Expected: sanitized App Hosting stage targets existing `koetts` backend;
  deployed frontend URL, secret reference, cloud mode, revision and traffic verified.
  Actual: pending. Evidence:

## Paused acceptance before activation

- [x] Expected: browse/login accessible; anonymous private API rejected; non-admin
  processing rejected before work; admin diagnostic access succeeds.
  Actual: pending. Evidence:
- [x] Expected: admin create returns explicit paused notification; no execution
  starts; provider allowance/calls disabled; recovery and GC schedules paused.
  Actual: pending. Evidence:
- [x] Expected: browser Firestore access denied; private API IAM/signing references
  remain narrow and correct; billing notifications and combined controls retained.
  Actual: pending. Evidence:

## Human activation and manual processing

- [x] Expected: human approves activation with measured stage/call caps and allowance;
  operator records audited configuration/resume, with separate scheduler decision.
  Actual: pending. Evidence:
- [ ] Expected: user manually uploads approved sample and creates one operation;
  request returns accepted durable operation identity before processing completes.
  Actual: pending. UTC / operation ID / evidence:
- [ ] Expected: Eventarc dispatch starts bounded job; SSE delivers progress and
  terminal state without recurring `/api/workflow?job=` requests.
  Actual: pending. Evidence:
- [ ] Expected: disconnect/reload reconnects saved operation; no duplicate enqueue,
  execution or paid retry; terminal result survives reload.
  Actual: pending. Evidence:
- [ ] Expected: sign-out/account change closes browser stream; revoked admin access
  closes server stream within 30 seconds; failed mutation preserves editable drafts.
  Actual: pending. Evidence:
- [ ] Expected: user manually runs optional authorized planning, then reviews cast,
  sources and exact script before short synthesis; measured quality/time/memory/cost
  recorded.
  Actual: pending. UTC / operation IDs / evidence:
- [ ] Expected: authenticated playback and byte ranges work; publication occurs only
  after approval of the exact export and required human audio review.
  Actual: pending. Export ID / approval / evidence:
- [ ] Expected: uncertain worker/provider outcome is reconciled without automatic
  paid retry; restart/rollback recovery preserves durable records and artifacts.
  Actual: pending. Evidence:

## Capture and acceptance decision

- [ ] Expected: narrow UTC log capture stored in new private results directory;
  user observations correlated with operation IDs and deployed revisions.
  Actual: pending. `--since` / `--until` / output path:
- [ ] Expected: agent completes read-only post-deploy configuration/log review;
  every failure and pending acceptance item reported explicitly.
  Actual: pending. Report path:
- [ ] Expected: campaign ends with agreed production/scheduler pause; active
  executions accounted for; delayed billing follow-up assigned.
  Actual: pending. Evidence:
- Final decision: pending / accepted / rejected.
- Outstanding defects and owner:
- Billing reconciliation owner/date:
