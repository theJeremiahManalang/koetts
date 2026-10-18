# Project documentation

## Authority and reading paths

Runtime source and configuration establish implemented behavior. The following
files hold different kinds of context; a future design is not runtime evidence.

| Need | Authoritative document |
| --- | --- |
| Current architecture and code seams | [architecture.md](architecture.md) |
| Accepted release scope, target architecture, unresolved decisions | [target-design.md](target-design.md) |
| Implementation scopes and acceptance checks | [architecture-alignment-plan.md](architecture-alignment-plan.md) |
| Assign one implementation scope | [architecture-alignment-prompt.md](architecture-alignment-prompt.md) |
| Local setup | [web guide](../web/README.md), [models](MODELS.md) |
| Review, synthesis, export, recovery | [audio workflow](AUDIO_WORKFLOW.md) |
| Existing frontend hosting configuration | [App Hosting](APP_HOSTING.md) |
| Historical checks and inspection | [validation history](VALIDATION.md), [baseline](current-app-baseline.md) |
| Extraction research | [research notes](TEXT_EXTRACTION_RESEARCH.md) |

[AGENTS.md](../AGENTS.md) routes agents to conditional context. Project skills live
under `.agents/skills/`; they contain reusable procedures, not roadmap status.
[CONTEXT.md](../CONTEXT.md) records the active assignment and handoff only.
Migration acceptance evidence belongs in `alignment-status.md` when S0 begins;
that report does not exist yet. Avoid treating its absence as a completed S0.

## Historical material

[archive/](archive/) preserves the original OCR walkthrough and imported architecture
handoff/prompts. Consult it only to recover unique rationale or historical intent.
The active target design supersedes old claims that cloud policy was agreed.
