# Documentation authority

Runtime source, workspace manifests, and lockfiles establish implemented behavior and dependencies. These documents add conventions and domain rationale; migration plans describe future work.

| Need | Guide |
| --- | --- |
| Entrypoints and ownership | [Root README](../README.md) |
| Setup, commands, environments, troubleshooting | [Developer setup](development.md) |
| Team review and dependency workflow | [Contributing](../CONTRIBUTING.md) |
| Implemented boundaries | [Architecture](architecture.md) |
| Domain terms | [Glossary](../GLOSSARY.md) |
| Extraction and hardware setup | [Models](MODELS.md) |
| Review, synthesis, export, recovery | [Audio workflow](AUDIO_WORKFLOW.md) |
| Login and trusted admin access | [Firebase authentication](FIREBASE_AUTH.md) |
| Frontend hosting | [App Hosting](APP_HOSTING.md) |
| Private HTTP service | [API deployment](S3_DEPLOYMENT.md) |
| Accepted target/open decisions | [Target design](target-design.md) |
| Migration scopes and evidence | [Plan](architecture-alignment-plan.md), [status](alignment-status.md) |

[Root agent guide](../AGENTS.md) routes scoped instructions. [Prompt approval](agents/prompt-approval.md) owns substantial-task approval; [writing guidance](agents/writing.md) owns harness conventions. `CONTEXT.md` records only the active task handoff.

[Archive](archive/README.md) retains unique historical rationale and acceptance evidence. Historical paths and commands describe their original checkout and are not current onboarding instructions.
