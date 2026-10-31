# Repository agent guide

Start with `README.md` for entrypoints and `docs/README.md` for authority. Workspace manifests and runtime source establish behavior; migration plans describe future work.

## Task routing

- **Substantial new work:** read `docs/agents/prompt-approval.md`. Continue approved follow-ups; explicit bypasses remain valid. Renew approval for material scope changes.
- **Web:** read `apps/web/AGENTS.md` before changing routes, features, or web tooling.
- **Workers or HTTP:** read `apps/worker/AGENTS.md` before changing transport, execution, or identity boundaries.
- **Engine:** read `packages/engine/AGENTS.md` before changing review, audio, persistence, or operation contracts.
- **Vision:** read `packages/vision/AGENTS.md`; read `docs/MODELS.md` before dependency changes or real inference.
- **Harness:** read `docs/agents/writing.md` before editing instructions or their context pointers.
- **Migration:** read `docs/target-design.md`, then the assigned scope in `docs/architecture-alignment-plan.md`; record scope evidence in `docs/alignment-status.md`.
- **Hosting:** read `docs/APP_HOSTING.md` for the frontend; read `docs/hosted-infrastructure.md` and `docs/hosted-rollout.md` for new cloud resources, cutover, or recovery.
- **Domain decisions:** use `GLOSSARY.md`; inspect relevant ADRs when present.
- **Issues:** read `docs/agents/issue-tracker.md`; use `gh` within the user's authorized tracker scope.

## Workspace and completion

Use pinned uv/npm tooling from the root. Package dependencies flow worker to engine/vision, engine to vision; vision imports no app package. Keep heavy inference optional. `npm run check:repo` enforces ownership and pointers; `npm run check` runs the normal acceptance suite. Use `npm run test:http` for transport, packaging, auth, or runtime changes. Record failures and optional skips separately from live-provider claims.

Preserve saved results, supplied samples, model caches, credentials, and unrelated edits. Test recovery on temporary copies. Human cast/script decisions and publication require explicit approval. Paid generation and deployment require task authorization; existing authorization persists.

Before handoff, update `CONTEXT.md` with objective, approval, decisions, changed paths, exact checks/results, blockers, and next action. Read that checkpoint only when resuming its task; verify against source.
