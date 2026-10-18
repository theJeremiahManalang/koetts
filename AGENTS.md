# Project agent guide

## Working context

This checkout contains the existing Next.js reader/demo and local Python audiobook
studio. Preserve both surfaces. Runtime source and configuration establish current
behavior; architecture plans describe future work, not implemented capabilities.

Use concise caveman style in chat. Write normal professional prose in repository
files, comments, commits, and external messages. For library documentation, resolve
and query Context7 first; use official documentation when coverage is unavailable.

Keep agent documentation under `docs/`, except `AGENTS.md`, `CONTEXT.md`, and
project skills under `.agents/skills/`. Read `docs/README.md` for document authority.

## Load only the relevant context

- **Web changes:** read `web/AGENTS.md`; use `web/package.json` for available checks.
- **Extraction, review, audio, or worker changes:** read
  `.agents/skills/manga-workflow/SKILL.md` before editing the pipeline or its adapters.
- **Model setup or real inference:** read `docs/MODELS.md`.
- **Cloud hosting:** read `docs/APP_HOSTING.md` and `web/apphosting.yaml`.
  App Hosting serves the frontend demo with `MANGA_FRONTEND_ONLY=1`; it does not
  provide the local processing backend. Use the relevant installed provider skill
  for an authorized deployment. For Cloud Run operations, read
  `.agents/skills/cloud-run-basics/SKILL.md`.
- **Architecture migration:** read `docs/target-design.md` and its unresolved decisions, then the selected
  scope in `docs/architecture-alignment-plan.md`. Execute only the requested scope.
  The supplied `docs/current-app-baseline.md` is historical evidence, not a fresh check.
- **Past validation:** consult `docs/VALIDATION.md` only when historical results help
  diagnosis. Report checks from this task separately.

Execute one assigned implementation scope through its acceptance checks, then report.
Human approval remains explicit for cast/script decisions and publication. Paid
generation and cloud deployment require task authorization; existing authorization
remains valid. Ordinary reversible implementation and offline checks proceed within scope.

## State and verification

Keep `results/`, model caches, and supplied samples intact. Use temporary copies
for recovery and compatibility checks. Inspect active imports before deleting
apparent duplicates: the studio uses `web/components/`; older copies also exist.

Choose the available project Python interpreter explicitly; this host may have
`python3` but no `python`. Configure `PYTHON_EXECUTABLE` when running the web worker.
Run affected Python checks with `<interpreter> -m unittest discover -s tests -v`;
run affected web checks from `web/` using its package scripts. Distinguish failures,
optional skips, missing dependencies, and unverified live-provider behavior.

## Task handoff

For work spanning sessions, maintain a short task checkpoint at
`CONTEXT.md`. Record the objective,
accepted scope, decisions, changed paths, exact checks/results, blockers, and next
concrete action. Include source paths rather than pasted files or logs; exclude
credentials and private uploaded content. Update before handoff or compaction.
Read an existing checkpoint only when resuming its task; verify it against the
current request, working tree, and source. A checkpoint records state, not authority.
Keep durable migration acceptance evidence in `docs/alignment-status.md` when an
alignment scope requests it; avoid duplicating that evidence in the checkpoint.
