# Active task: documentation consolidation

## Objective and approval

The user requested: “Update my docs to the current context and organize it.”
This is an authorized follow-up to hosted implementation and the approved GCP
Gemini migration. Update documentation and navigation without changing runtime,
cloud resources, costs or approval requirements. Preserve historical evidence.

The broader hosted-service goal remains incomplete on `feat/hosted-service`, based
on main `0bdacc5cd0092cf33d53afb4d12f6b64b5ba16bb`. Implementation, substantial
commits and independent Standards/Spec review were authorized. Deployment, paid
model/CPU tests, human cast/script/audio approvals and real publication retain
separate gates. No phase 5 deployment or paid inference occurred in this task.

## Current authoritative context

- Existing project: `koetts-9bf7f`; named Firestore: `koetts-default`, `nam5`.
- New API: `koetts-api`. New API/jobs/Scheduler/artifact storage target
  `us-central1`. Existing frontend `koetts` remains `us-east4` initially; its later
  migration to `us-central1` is part of the expected end state.
- Existing `koetts-s3-api` is the earlier verification service. Its replacement
  and retirement require verified caller cutover. Historical live observations
  are recorded in the rollout guide and need refreshing before execution.
- Gemini SDK is locked to 2.33.0. Planning and synthesis use ADC and explicit
  `GOOGLE_CLOUD_PROJECT`, with `GOOGLE_CLOUD_LOCATION=us`. Only the pipeline identity
  has inference permission. No API-key fallback or provider-key secret injection.
- Reviewed text/style/voice requests map to Gemini 3.8 `generate_content`; unary
  output is validated complete mono 24 kHz 16-bit PCM WAV. No live model-quality,
  account-access or cost claim follows from offline wire fixtures.
- Quotas, approvals, exact-generation artifacts, operation fences, durable provider
  uncertainty and budget reservations remain authoritative. ADK is research only.
- The infrastructure target is USD 10/month with a desired USD 20 ceiling, not a
  guarantee. Project-filtered budget reporting includes GCP model spend; the
  separate provider ledger is an application allowance, not transferred API credit.
  Production pause preserves login and published playback.

## Implementation and verification before this cleanup

Hosted phases 0–4 passed offline reviews. Phase 4 final fixes include `364c4a6`
and `8703d04`. Gemini migration `d9eb6f1`, review fixes `821c02e`, and evidence
`40182c8` passed both review follow-ups. Those fixes restored pipeline execution
identity, shared WAV validation and replaced stale API-key guidance.

Recorded migration checks: repository/Ruff/Python suite, 90 web tests and typecheck
passed; 104 loopback Firestore tests and production-webpack HTTP studio/frontend-only
checks passed; Terraform fmt/schema validation passed; Mermaid blocks parsed.
Default Turbopack failed under process/port restrictions, so the complete default
`npm run check` is not claimed green. Optional/live tests are distinct from passes.
Temporary evidence paths: `/tmp/gcp-gemini-check.log`,
`/tmp/gcp-gemini-firestore.log`, `/tmp/gcp-gemini-http.log`. They may not survive
runtime replacement. Pinned tooling: Node 22.22.3, npm 10.9.8, uv 0.11.16,
Python 3.11.15. No heavy inference dependencies or model downloads are required.

## Documentation work in progress

Root owns README/navigation, architecture, status/archive and this handoff.
A bounded worker owns hosted operational/plan/free-tier documents and diagrams;
another owns developer/auth/frontend/audio and agent-research documents.
Workers preserve each other's edits. No further delegation is allowed for them.

The previous long alignment log is preserved in
`docs/archive/alignment-status-through-2026-10-31.md`; the active
`docs/alignment-status.md` now summarizes current acceptance and remaining gates.
The S3 runbook remains at its original path for stable pointers, clearly marked
historical. Current production rollout belongs to `docs/hosted-rollout.md`.
Only the AGENTS.md hosting pointer changes: frontend setup routes to App Hosting,
and new cloud resources/cutover routes to the current infrastructure/rollout guides.
No skill, approval policy or runtime configuration changes.

## Completion and next action

Collect both documentation workers, audit cross-file consistency, run repository
and Markdown/Mermaid checks, commit the consolidation, then obtain independent
Standards/Spec review and fix findings. Record exact results here before handoff.
Do not claim that documentation cleanup refreshes live cloud state or reruns
previous acceptance suites. Next implementation gate remains bounded phase 5
cloud/test authorization with incremental infrastructure/build and model spending
allowances, plus real rollout targets, IAM/model access and billing attribution.

## Documentation validation

Repository checks passed during consolidation. A local-target scan checked 165
Markdown links with no missing targets; all three Mermaid diagrams parsed with
the temporary Mermaid 11.12.2 validator. These are documentation checks, not fresh
application acceptance or live cloud verification.

Navigation walkthroughs (text inspection, not model evaluations): substantial new
work still routes to prompt approval; quick questions reach the relevant guide;
approved follow-ups reuse existing scope; material scope changes retain renewed
approval; explicit bypass remains defined by the unchanged approval guide. Hosting
now reaches the current deployment runbooks, with historical S3 evidence still
discoverable from the documentation index. No approval rule was relaxed.
