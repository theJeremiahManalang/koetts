# Project agent guide

## Working context

Preserve the Next.js reader/demo and local Python audiobook studio. Runtime source
and configuration establish behavior; architecture plans describe future work.

Use caveman chat; professional prose in files, comments, commits, and external messages.
For library documentation, resolve and query Context7 first; fall back to official docs.

Keep agent docs under `docs/`, except `AGENTS.md`, `CONTEXT.md`, and skills under
`.agents/skills/`. Read `docs/README.md` for authority.

## Prompt approval

Before substantial new implementation, architecture, or investigation, read
`docs/agents/prompt-approval.md`: ground and present a rewritten prompt, then wait
for explicit approval before execution. Read-only preparation is allowed. Answer
quick questions directly; continue approved follow-ups. Material scope changes
require renewed approval. Honor explicit requests to skip rewriting.

## Conditional context

- **Web changes:** read `web/AGENTS.md`; use `web/package.json` for available checks.
- **Extraction, review, audio, or worker changes:** read
  `.agents/skills/manga-workflow/SKILL.md` before editing the pipeline or its adapters.
- **Model setup or real inference:** read `docs/MODELS.md`.
- **Cloud hosting:** read `docs/APP_HOSTING.md` and `web/apphosting.yaml`.
  App Hosting runs the demo with `MANGA_FRONTEND_ONLY=1`, without local processing.
  For authorized deployment, use the provider skill. For Cloud Run operations, read
  `.agents/skills/cloud-run-basics/SKILL.md`.
- **Architecture migration:** read `docs/target-design.md`, including unresolved decisions,
  then the assigned scope in `docs/architecture-alignment-plan.md`.
  `docs/current-app-baseline.md` is historical evidence, not fresh verification.
- **Past validation:** consult `docs/VALIDATION.md` only when historical results help
  diagnosis. Report checks from this task separately.

Complete the assigned scope's acceptance checks, then report.
Human approval remains explicit for cast/script decisions and publication. Paid
generation and cloud deployment require task authorization; existing authorization
remains valid. Ordinary reversible implementation and offline checks proceed within scope.

## State and verification

Preserve `results/`, model caches, and supplied samples. Check recovery/compatibility
on temporary copies. Inspect imports before deleting duplicates: the studio uses
`web/components/`; older copies exist.

Choose an available project Python interpreter explicitly; `python` may be absent.
Configure `PYTHON_EXECUTABLE` for the web worker.
Run affected Python checks with `<interpreter> -m unittest discover -s tests -v`;
run affected web checks from `web/` using its package scripts. Distinguish failures,
optional skips, missing dependencies, and unverified live-provider behavior.

## Task handoff

Before handoff or compaction, update `CONTEXT.md`: objective, scope/approval status,
decisions, changed paths, exact checks/results, blockers, next action. Include source
paths; exclude credentials/private uploads. Read only when resuming its task; verify
against request, tree, and source. Checkpoints record state, not authority. For alignment
scopes, link durable acceptance evidence in `docs/alignment-status.md` rather than duplicating it.

## Conditional guides

- **Agent-document changes:** use `.agents/skills/writing-for-agents/SKILL.md`.
- **Issue/spec work:** use GitHub Issues through `gh`; read `docs/agents/issue-tracker.md`.
- **Triage labels:** read `docs/agents/triage-labels.md` for canonical roles.
- **Domain terms or decisions:** read `docs/agents/domain.md` and root `GLOSSARY.md`;
  consult relevant ADRs when present.
