# Web agent guide

Root `AGENTS.md` owns task gates. `app/` is the Next.js route boundary. `features/` owns studio, identity, library/reader, and requests; feature code imports no route adapter. Demo fixtures live with their feature. `lib/` owns Python transport only.

For worker snapshots, polling, expected-state rejection, or review mutations, read `../worker/AGENTS.md` and `../../packages/engine/AGENTS.md`. Preserve drafts on failed mutations and stale-state rejection. Server routes verify identity before private assets or processing; read `../../docs/FIREBASE_AUTH.md` for identity changes.

For hosted frontend-only mode, read `../../docs/APP_HOSTING.md`. Preserve root redirect and processing guards. Keep credentials server-side and demo/browser-local request behavior explicit.

Use root npm scripts. Imports/routes require tests, typecheck, and build; transport/auth/runtime changes also require `npm run test:http`. Resolve Next.js's installed docs through the root dependency tree after npm hoisting.

<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
