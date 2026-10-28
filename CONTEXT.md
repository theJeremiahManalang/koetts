# Active task handoff

## Objective and approval

Finish post-merge folder cleanup on dev-test-1 while preserving Firestore requests and local configuration. On 2026-10-28 the user explicitly authorized implementation after the comparison and ordered cleanup recommendations. No deployment, live Firestore writes, commit, or push requested.

## Decisions and changed paths

- Keep apps/web and root npm dependencies. Removed obsolete root web and cache-only root manga_tts after verifying resolved target paths.
- Copied web/.env.local to apps/web/.env.local; verified equal SHA-256 hashes before deleting the old file. The new file remains ignored. All existing Firebase settings and database selection are preserved.
- Retained user edits in apps/web/features/requests/request-page.tsx, requests-page.tsx, apps/web/apphosting.yaml, and the new apps/web/app/api/requests/route.ts. GET/POST retain authenticated ownership, manga_requests, numeric chapters and server timestamps. Notes validation now matches the 2,000-character form limit.
- Backed up old API route and nested lockfile under ignored .cache/merge-cleanup-backup. Removed obsolete tracked web/next-env.d.ts; Next generates it in the active app.
- apps/web/.env.example: document required FIRESTORE_DATABASE_ID without a default database.
- apps/web/tests/requests-route.test.cjs: four mocked tests cover denied identity, verified ownership, input validation, numeric chapter/server timestamps, user-scoped reads, and private/no-store caching.
- tests/verify_local_http.py: add a typed fail-closed Firestore export to the disposable identity fixture; it never calls live Firestore.
- Downloaded Node 22.22.3 (npm 10.9.8) and uv 0.11.16 under ignored .cache/tooling. Global tools unchanged. Frozen uv sync recreated local .venv with Python 3.11.15 and default locked dependencies.

## Exact checks and results

Validation prepended .cache/tooling/node-v22.22.3-win-x64 and .cache/tooling/uv/bin to PATH. Set PYTHONUTF8=1, UV_CACHE_DIR to repository .cache/uv, and NEXT_TELEMETRY_DISABLED=1.

- uv sync --frozen: passed with pinned uv 0.11.16.
- npm run check: repository check and lint passed; stopped at Python test failures. 105 tests ran: 2 failures, 3 errors, 2 optional skips.
- Three Python errors: Windows short/long temp path mismatch in worker source fingerprinting. Failures: worker PID assertion mismatch; repository checker regression test did not detect forbidden feature dependency. Worker/engine production code unchanged.
- Optional skips: external saved sample not supplied; local web test server not configured.
- npm run test:web: all 37 tests passed, including four new request-route tests.
- npm run typecheck: passed, including Next route type generation.
- npm run build: passed; includes /api/requests, /request, /requests.
- npm run test:http: failed before server startup with FileNotFoundError [WinError 2] launching bare npm via Python subprocess on Windows. Run began before the fixture export update; updated fixture has been linted but not end-to-end validated by this blocked harness.
- uv run --locked ruff check tests/verify_local_http.py: passed after fixture update.
- git diff --check: passed.
- git check-ignore confirms local env and tool cache remain ignored.
- No live Firebase authentication, reads/writes, or paid generation tested.

## Next action and blockers

Review/commit cleanup, including the untracked relocated API route and new test. Resolve existing Windows test/harness portability failures separately before claiming the full acceptance suite passes. Run root development commands with the project-local tools on PATH. Saved results, images, weights, vendor files, and model caches were preserved.

## 2026-10-28 — Studio account menu
- Objective/approval: User requested the same user/logout controls on `/` as `/browse`; small UI follow-up directly authorized.
- Decision: Reuse the existing AccountNav in the studio header, including name/avatar, requests/admin links, sign-out pending/error handling. Allow header actions to wrap.
- Changed paths: apps/web/features/studio/studio-workspace.tsx; apps/web/app/globals.css; CONTEXT.md (appended checkpoint, preserving prior work).
- Checks: npm run test:web PASS (37/37); npm run typecheck PASS. npm run check BLOCKED at check:repo because installed uv 0.11.26 differs from pinned 0.11.16. npm run build FAILED twice (sandbox and elevated) with Turbopack CSS subprocess exiting before connection. No live browser/provider verification performed; no authentication contracts changed.
- Blockers/next action: UI implementation complete; production build verification needs Turbopack subprocess issue resolved. Unrelated existing changes preserved.

## 2026-10-28 — Request pages syntax check
- Objective/approval: User requested syntax inspection of requests-page.tsx and request-page.tsx.
- Result: Both inspected; npm run typecheck PASS (exit 0), no syntax or TypeScript errors. No source edits.
- Observations: Request delete dialog actions are commented out; old delete implementation still uses localStorage while listing uses API. Request form resets notes twice. These are behavior/cleanup issues, not syntax errors.
- Changed paths: CONTEXT.md only for this check. Blockers: none. Next action: report findings.
