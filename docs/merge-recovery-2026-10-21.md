# Merge recovery notes

Repair completed after explicit user approval on 21 October 2026. The server page
gate and API import are restored; incoming operation recovery now lives in the
authenticated client workspace. All 25 web tests, typecheck, and production build
passed. See `CONTEXT.md` for exact commands and limits. The notes below record
the original pre-resolution state.

Recorded 21 October 2026 before resolving conflicts on `dev-test-1`.
The user requested preservation notes before potentially accepting incoming.
Implementation and merge resolution have not been performed.

## Recoverable sources

- Current branch HEAD: `b786f32249bc2412a0fac10eab7c6df1ec429da4`.
- Incoming main (MERGE_HEAD): `cb467f1f9c4dff14a162f5760f4961c2b16ac2c9`.
- Conflicted paths: `web/app/page.tsx` and `web/app/api/workflow/route.ts`.

Use `git show <commit>:<path>` to retrieve either committed version after
accepting incoming. These references preserve committed sources, not any later
manual conflict-resolution edits.

## Required integration

`web/app/page.tsx` in HEAD is a server component. It uses `requireAdmin`,
redirects unauthenticated users to `/login?next=%2F`, redirects other denied users
to `/browse`, and renders `StudioWorkspace`. Preserve this gate and the
`nodejs` runtime and dynamic rendering configuration.

Incoming main retains the studio UI in `page.tsx` and adds durable-operation
and idempotency behavior. Integrate those client changes into
`web/app/studio-workspace.tsx`, preserving its existing Firebase/auth integration.
Simply accepting incoming for the whole page removes the server gate; keeping
only HEAD misses the incoming client behavior. Inspect the complete source diff
before integration.

`web/app/api/workflow/route.ts` has an import conflict between `requireAdmin`
and `createHash` from `node:crypto`. Both imports are needed. Preserve the
POST authorization check alongside incoming enqueue, dispatch, operation-status,
and idempotency behavior. At inspection, the combined working copy already
contained the POST authorization check outside the import conflict.

## Verification and next action

Only Git status/diff and targeted source inspection were performed. No tests ran.
Read `web/AGENTS.md` and the manga workflow skill before implementation, inspect
the full combined changes, then run applicable package checks and affected Python
checks. Verify authorization and operation retry/reconnection behavior together.
Obtain prompt approval for substantial integration under
`docs/agents/prompt-approval.md`, unless the user explicitly bypasses rewriting.
