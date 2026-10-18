# Web agent guide

Read the repository `AGENTS.md` for task routing and context handoff.

The active studio is `app/page.tsx` with workspaces in `components/`. Catalog,
reader, and request pages use demo data; they are separate from studio projects.
Trace imports before changing similarly named files under `app/` or `lib/`.
`npm test` selects tests in `tests/` through `package.json`.

For API routes, Python transport, polling, or review state, read
`../.agents/skills/manga-workflow/SKILL.md`. Keep shared types and worker snapshots
aligned. Preserve drafts on failed mutations and stale-state rejection.

For frontend-only hosting, retain processing guards in all three API routes and
the root-page redirect. Read `../docs/APP_HOSTING.md` before changing that boundary.
Keep provider credentials on the server.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
