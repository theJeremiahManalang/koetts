# Active task: documentation directory organization

## Objective and approval

The user requested root `resources/` for developer project guides and the GCP
architecture diagram, and `docs/` with adr/agents/archive/plans/resources/research
plus uppercase essential harness documents and README.md. This supersedes the
interrupted request for a root research directory. No root research directory
was created.
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

## Documentation changes

Updated README/navigation, architecture, active status/archive and this handoff.
Two bounded workers completed hosted operational/plan/free-tier and developer/
auth/frontend/audio/research updates within separate file ownership.

The previous long alignment log is preserved in
`docs/archive/alignment-status-through-2026-10-31.md`; the active
`docs/STATUS.md` now summarizes current acceptance and remaining gates.
The S3 runbook is now `docs/archive/S3_DEPLOYMENT.md`, clearly historical. Current
production rollout is `docs/resources/hosted-rollout.md`. Root and scoped AGENTS
migration, vision, hosting, engine and web pointers now target the moved canonical
files. Their triggers and approval policies are unchanged; runtime configuration
is unchanged.

## Completion and next action

Directory reorganization is committed in `7f1ca7d`. Spec review reports no findings.
Standards review found stale handoff claims about the old S3 path and which agent
pointers changed; both statements are corrected. The archive index's former inline
path references now link to current uppercase harness documents. Final checks
cover all canonical moves, Markdown links, the repository-checker regression and
Mermaid parsing. No application or live cloud tests are needed for this path-only
change; the original application acceptance remains recorded above.

Next implementation gate remains bounded phase 5 cloud/test authorization with
incremental infrastructure/build and model spending allowances, actual rollout
targets, IAM/model access and billing attribution. Documentation cleanup does not
refresh live cloud state, authorize spending, or complete the broader hosted goal.

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


Reading-size evidence uses reproducible whitespace-word counts (`len(text.split())`)
from `git show 40182c8:PATH` versus the updated file, not token estimates or model
evaluations. AGENTS.md: 278 to 286 words. Frontend hosting path APP_HOSTING.md:
662 to 762 words. Prior private-service pointer S3_DEPLOYMENT.md: 1,177 words;
replacement infrastructure/rollout references: 1,768 and 1,573 words (3,341
combined). The larger disclosed path covers the full hosted stack rather than
only verification. CONTEXT.md reduced from 2,012 to 708 words before this review
record; active alignment status from 8,705 to 566 words. Documentation index grew
from 216 to 381 words to provide task-based routing.

Review of 40182c8...997e1b3 found missing reading-size evidence and an unintended
rewrite of the accepted infrastructure spending target as total-project spending.
The measurements above address the first. Restored the original infrastructure
USD 10 target/desired USD 20 ceiling and separate provider allowance, explicitly
recording project-wide billing aggregation as an unresolved implementation gap.
No new spending policy or authorization was inferred from cleanup. The archived
alignment record was mechanically compared with its prior content: all original
text remains, with only the wrapper and normalized relative links changed.


## Requested directory layout

Moved developer setup, audio workflow, models, Firebase auth, App Hosting and GCP
Mermaid diagrams into root resources/, with its own README. Moved operational
references into docs/resources/, implementation plans into docs/plans/, research
notes into docs/research/, and the historical S3 runbook into docs/archive/.
Kept ADRs, agent instructions and historical archives in their existing folders.
Renamed essential docs-root contracts to ARCHITECTURE.md, TARGET_DESIGN.md and
STATUS.md. All old files have one canonical destination; no duplicate compatibility
copies or runtime changes were added. Rebased Markdown links and scoped AGENTS
pointers throughout the repository, including links inside archived evidence;
historical prose/source paths remain historical where appropriate.

Navigation walkthroughs: substantial new work still reaches the unchanged approval
guide; quick questions can start in root resources or docs indexes; approved
follow-ups retain authorization; material scope changes retain the same gate;
explicit bypass remains in the unchanged approval guide. Hosting, engine, vision
and web pointers now resolve to their moved canonical documents. These are text
walkthroughs, not model evaluations. Reading-cost measurement uses whitespace
words; document relocation changes path spelling rather than domain-rule content.
Reading-size evidence and independent review outcomes are recorded below.

Validation before review: 20 source/destination moves verified with no
old active file left; 203 local Markdown targets resolve. Repository checker
and its unit regression pass; three Mermaid diagrams parse. AGENTS.md remains
286 whitespace words before/after; docs/README.md grows from 381 to 452 words
for explicit directory routing. No token estimate or model evaluation is claimed.


Directory-review outcome: Spec found no gaps; Standards stale-handoff finding
corrected. Earlier consolidation-review notes above describe the prior task's
accepted-policy fix, not a new policy change during this reorganization. Root
resources contains developer documentation and GCP diagrams; docs/research holds
research notes. The interrupted root research/ request was superseded before
filesystem mutation. No root research/ directory was created.
