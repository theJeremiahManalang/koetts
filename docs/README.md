# Documentation guide

Runtime source, workspace manifests and lockfiles establish implemented behavior.
Plans describe intended work; acceptance records distinguish offline checks from
live verification. Start with the page matching your task.

## Run and use the application

| Task | Guide |
| --- | --- |
| Install tooling, configure ADC and run locally | [Developer setup](development.md) |
| Configure Firebase sign-in and trusted admins | [Authentication](FIREBASE_AUTH.md) |
| Review cast/sources/scripts, render, export and recover | [Audio workflow](AUDIO_WORKFLOW.md) |
| Install optional extraction models and select CPU/CUDA | [Models](MODELS.md) |
| Understand domain terms | [Glossary](../GLOSSARY.md) |

## Prepare and operate the hosted product

Read [current implementation status](alignment-status.md) before treating a hosted
feature as deployed. The [Mermaid diagrams](hosted-infrastructure-diagram.md) show
initial and final regional placement.

| Task | Guide |
| --- | --- |
| Review accepted scope, limits and phase 5 authorization | [Hosted plan](hosted-service-plan.md) |
| Configure Terraform inputs, identities, resources and secrets | [Hosted infrastructure](hosted-infrastructure.md) |
| Configure or migrate the frontend | [Firebase App Hosting](APP_HOSTING.md) |
| Prepare rollout evidence, replace the API, migrate frontend and roll back | [Hosted rollout](hosted-rollout.md) |
| Configure allowances, pause production and reconcile spending | [Cost controls](hosted-cost-controls.md) |
| Collect orphan artifacts and recover interrupted cleanup | [Artifact collection](hosted-artifact-collection.md) |
| Evaluate free-tier assumptions | [Dated assessment](hosted-free-tier-review.md), [official-source notes](hosted-free-tier-sources.md) |

## Understand and change the system

| Task | Guide |
| --- | --- |
| Find entrypoints and workspace ownership | [Root README](../README.md) |
| Understand implemented boundaries | [Architecture](architecture.md) |
| Review accepted product/persistence contracts | [Target design](target-design.md) |
| Understand durable cloud-job rationale | [ADR 0001](adr/0001-hosted-execution.md) |
| Follow contribution and code-review conventions | [Contributing](../CONTRIBUTING.md) |
| Understand earlier S0–S5 scope definitions | [Architecture alignment plan](architecture-alignment-plan.md), [scope assignment prompt](architecture-alignment-prompt.md) |
| Evaluate optional ADK/managed-agent adoption | [Gemini agent research](gemini-agent-gcp-research.md) |

## Historical evidence and agent instructions

[Archive](archive/README.md) preserves earlier acceptance, reviews and rationale.
The [S3 verification runbook](S3_DEPLOYMENT.md) describes the earlier authentication-only
service; it is not the production deployment procedure. Historical commands and
cloud observations require fresh verification before reuse.

[Root agent guide](../AGENTS.md) routes scoped instructions.
[Prompt approval](agents/prompt-approval.md) owns substantial-task approval;
[writing guidance](agents/writing.md) owns harness conventions;
[issue workflow](agents/issue-tracker.md) owns tracker actions.
`CONTEXT.md` is the active task handoff, not an onboarding guide or a permanent
chronological acceptance log.
