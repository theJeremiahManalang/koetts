# Documentation guide

Runtime source, workspace manifests and lockfiles establish implemented behavior.
Plans describe intended work; acceptance records distinguish offline checks from
live verification. Start with the page matching your task.

## Directory layout

- `adr/`: accepted architectural decisions.
- `agents/`: scoped agent workflows and instruction-writing guidance.
- `archive/`: preserved historical evidence and obsolete rollout procedures.
- `plans/`: implementation scope and acceptance requirements.
- `resources/`: hosted operational references.
- `research/`: investigations, source notes and unresolved options.

Essential agent-facing contracts remain at this directory's root:
[ARCHITECTURE.md](ARCHITECTURE.md), [TARGET_DESIGN.md](TARGET_DESIGN.md) and
[STATUS.md](STATUS.md). Developer setup, workflow guides and GCP diagrams live in
the repository's separate [resources directory](../resources/README.md).

## Run and use the application

| Task | Guide |
| --- | --- |
| Install tooling, configure ADC and run locally | [Developer setup](../resources/DEVELOPMENT.md) |
| Configure Firebase sign-in and trusted admins | [Authentication](../resources/FIREBASE_AUTH.md) |
| Review cast/sources/scripts, render, export and recover | [Audio workflow](../resources/AUDIO_WORKFLOW.md) |
| Install optional extraction models and select CPU/CUDA | [Models](../resources/MODELS.md) |
| Understand domain terms | [Glossary](../GLOSSARY.md) |

## Prepare and operate the hosted product

Read [current implementation status](STATUS.md) before treating a hosted
feature as deployed. The [Mermaid diagrams](../resources/GCP_ARCHITECTURE.md) show
initial and final regional placement.

| Task | Guide |
| --- | --- |
| Review accepted scope, limits and phase 5 authorization | [Hosted plan](plans/hosted-service-plan.md) |
| Configure Terraform inputs, identities, resources and secrets | [Hosted infrastructure](resources/hosted-infrastructure.md) |
| Configure or migrate the frontend | [Firebase App Hosting](../resources/APP_HOSTING.md) |
| Prepare rollout evidence, replace the API, migrate frontend and roll back | [Hosted rollout](resources/hosted-rollout.md) |
| Configure allowances, pause production and reconcile spending | [Cost controls](resources/hosted-cost-controls.md) |
| Collect orphan artifacts and recover interrupted cleanup | [Artifact collection](resources/hosted-artifact-collection.md) |
| Evaluate free-tier assumptions | [Dated assessment](research/hosted-free-tier-review.md), [official-source notes](research/hosted-free-tier-sources.md) |

## Understand and change the system

| Task | Guide |
| --- | --- |
| Find entrypoints and workspace ownership | [Root README](../README.md) |
| Understand implemented boundaries | [Architecture](ARCHITECTURE.md) |
| Review accepted product/persistence contracts | [Target design](TARGET_DESIGN.md) |
| Understand durable cloud-job rationale | [ADR 0001](adr/0001-hosted-execution.md) |
| Follow contribution and code-review conventions | [Contributing](../CONTRIBUTING.md) |
| Understand earlier S0–S5 scope definitions | [Architecture alignment plan](plans/architecture-alignment-plan.md), [scope assignment prompt](plans/architecture-alignment-prompt.md) |
| Evaluate optional ADK/managed-agent adoption | [Gemini agent research](research/gemini-agent-gcp-research.md) |

## Historical evidence and agent instructions

[Archive](archive/README.md) preserves earlier acceptance, reviews and rationale.
The [S3 verification runbook](archive/S3_DEPLOYMENT.md) describes the earlier authentication-only
service; it is not the production deployment procedure. Historical commands and
cloud observations require fresh verification before reuse.

[Root agent guide](../AGENTS.md) routes scoped instructions.
[Prompt approval](agents/prompt-approval.md) owns substantial-task approval;
[writing guidance](agents/writing.md) owns harness conventions;
[issue workflow](agents/issue-tracker.md) owns tracker actions.
`CONTEXT.md` is the active task handoff, not an onboarding guide or a permanent
chronological acceptance log.
