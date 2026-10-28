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

## 2026-10-28 — Compact studio account controls
- Objective/approval: User explicitly requested avatar-only account UI on `/` and one row with Saved projects and New chapter.
- Changes: apps/web/app/globals.css scopes avatar-only presentation and nonwrapping controls to the studio header. On narrow screens, the brand can occupy a separate row while all three controls stay together. Existing accessible account label and dropdown remain intact; browse styling is unchanged.
- Checks: git diff --check PASS. No live browser verification. Prior full-suite uv version and Turbopack build blockers remain recorded above.
- Next action: Report UI adjustment and typecheck result.
- Final validation: npm run typecheck PASS (exit 0).

## 2026-10-28 — Admin request dashboard and Studio navigation
- Objective/approval: User approved the rewritten dashboard implementation scope with “Do this”. Follow-up explicitly requires retaining the navbar and table on /admin/requests even with no data.
- Implemented: Server-guarded /admin/requests and GET/PATCH /api/admin/requests use the existing boolean admin claim and configured Firestore manga_requests collection. GET lists all owners or one selected request. PATCH requires an explicit bearer token, validates status transitions, compares current status in a transaction, and records the verified actor/time. Reader-owned API behavior is unchanged.
- UI: Shared Requests / Studio / View reader navigation; admin account-menu dashboard link; admin sign-in return path; status filters, request notes, requester account IDs, refresh and status actions. Navbar and table headings remain visible for empty, loading, filtered-empty and error states. Status actions track progress only; no synthesis or publication occurs.
- Studio: Saved projects moved from the header into Continue working. Existing project recovery and draft-leave checks remain. Open in Studio carries a request ID and loads reference details without replacing a saved project. Frontend-only root redirect and processing restrictions remain intact.
- Changed paths: apps/web/app/admin/requests/page.tsx; apps/web/app/api/admin/requests/route.ts; apps/web/features/requests/admin-requests-page.tsx and admin-request-types.ts; apps/web/features/identity/admin-nav.tsx, account-nav.tsx and auth-form.tsx; apps/web/features/studio/studio-workspace.tsx and studio-request-context.tsx; apps/web/app/globals.css; apps/web/tests/admin-requests.test.cjs. Existing CSS and checkpoint edits preserved.
- Validation uses pinned local Node 22.22.3/npm 10.9.8 and uv 0.11.16. npm run typecheck PASS; git diff --check PASS. Web suite passed 44/44 after empty-state coverage; final run also adds admin-login return-path coverage (result below).
- npm run check: check:repo and lint PASS. Initial Python execution hit sandbox temp-folder permission errors. Retry with TEMP/TMP under .cache/admin-temp progressed through tests but reported failures in worker-process recovery and repository-checker regression, and an error in pipeline checkpoint recovery; it did not finish reporting and was interrupted. Optional skips: no external saved sample; no local HTTP test server. No worker/engine changes made.
- npm run build FAIL: Turbopack CSS worker exits before connection; reproduced outside sandbox. npm run build --workspace @manga/web -- --webpack also FAIL (compiler exits without detailed diagnostic). These match the previously recorded build environment limitation; production build is not verified.
- npm run test:http BLOCKED during disposable uv sync: DNS failure downloading hatchling from PyPI, before server startup. No HTTP harness success claimed.
- Browser: verified anonymous /admin/requests redirects to /login?next=%2Fadmin%2Frequests. Authenticated visual QA remains incomplete: native browser control lacked input geometry and the isolated sample-layout preview was unreachable from the in-app browser. Preview server stopped. No live request writes, paid generation, deployment, commit or push.
- Next action: Report implementation and validation limits. Complete authenticated visual/production HTTP verification once build/network environment is available.
- Final web validation: npm run test:web PASS, 45/45 tests, including admin sign-in return paths and empty-table/navbar regression coverage.

## 2026-10-28 — Compact request table follow-up
- Approval/objective: User requested a simpler /admin/requests table: compact rows, plain status, reader-note column, requester names, icon actions/tooltips, and Generate opening Studio. Continued the approved dashboard scope.
- Changes: admin-requests-page.tsx now renders six columns, inline manga/chapter, requesterName, a separate compact reader note, plain status text, and SVG icon actions. request-action.tsx provides accessible labels and hover/focus tooltips with Escape dismissal. globals.css scopes compact spacing and icon styles to the admin table; empty/navbar behavior remains.
- Names: Admin GET resolves Firebase Authentication display names by UID in deduplicated batches of up to 100. Existing requests need no migration. Deleted accounts, unnamed accounts, and lookup failures have explicit name fallbacks; emails are not returned. Updated admin-request-types.ts and route tests.
- Generate: Opens /?request=<id>&create=1. Studio starts at chapter creation instead of restoring an unrelated saved project, retaining saved project storage and prioritizing recovery of unfinished operations. Request title/chapter/note appear in the Studio reference. Requests have no manga-page attachments or approved script, so uploading pages and cast/script approval remain necessary before synthesis. No automatic paid generation or publication was performed.
- Validation: npm run test:web PASS 48/48; npm run typecheck PASS; npm run check:repo PASS with pinned tooling, UV_CACHE_DIR and PYTHONUTF8=1; git diff --check PASS. Tests include requester name resolution, deduplication/batching, lookup failure, six-column empty states, icon labels/tooltips, and Generate preserving unrelated saved projects.
- Visual QA: Rendered the actual dashboard components with synthetic names/requests in an isolated local read-only preview. Verified desktop row heights about 49px at 1280px; mobile 390px keeps page width bounded and table horizontally scrollable. Verified keyboard focus exposes the Approve tooltip. This is sample-data visual QA, not live Firebase verification. Temporary viewport reset and preview tab closed.
- Remaining verification limits: npm run build still fails in Turbopack's CSS subprocess (exit before connection); npm run test:http still fails during disposable uv sync due to PyPI DNS/dependency-download failure. No deployment or live Firebase mutation.
- Next action: Report compact table completion and Generate prerequisite. Resume production build/HTTP checks once environment blockers are resolved.

## 2026-10-28 — Merge Studio request, project picker, and reading-space heading
- Objective/approval: User explicitly requested merging the three screenshot areas on the Studio root (including request-selected /?request=… entry), preserving YOUR READING SPACE and A voice for every character. Continued the approved UI follow-up.
- Changes: studio-workspace.tsx now has one studio-generation-panel containing the heading/progress, request context, explicit Project for audio (loaded snapshot title or new-chapter state), and saved-project selector. studio-request-context.tsx renders inline request title/status and labeled Remarks instead of a separate card. Preserved the user's removal of the longer instructional paragraph. globals.css adds scoped responsive panel styles and removes separate continue-card styling. Existing project loading, generation, auth, and draft protections unchanged; /request submission form unchanged.
- Verification: npm run typecheck PASS. Extended the existing Generate UI test to verify heading, request, remarks, active-project text and selector share one panel, and the old separate card is absent. Web test result recorded below. No new build/HTTP run for this presentation-only follow-up; earlier environment blockers remain.
- git diff --check reports trailing whitespace in the user's concurrently edited admin-requests-page.tsx lines 79–80; left those unrelated edits intact. No whitespace errors reported in this follow-up's Studio files.
- Next action: Report merged panel and validation. No live provider calls, paid generation, deployment, or publication.

## 2026-10-28 — Resolve admin request loading error
- User reported “Could not load requests. Please retry.” Read-only live diagnostics established that all six Firestore requests use status submitted; the admin endpoint previously rejected that status and returned 500 for the entire queue. The current user-edited POST /api/requests writes submitted. One existing record has an empty requester UID.
- Fix: normalizeRequestStatus in admin-request-types.ts maps trimmed/case-normalized submitted to pending. Admin GET and transaction expected-status comparison use the same normalization, so submitted requests load and can be approved/rejected without migration. Existing invalid-UID filtering retains Name unavailable for the ownerless record. No production auth bypass or database writes.
- Live read-only verification: 6 requests, all 6 pass the dashboard row contract after normalization; 2 distinct valid Firebase profiles found, both have display names; zero records modified. This verifies configured database/profile access and data compatibility, not authenticated browser end-to-end actions.
- Tests: added submitted-status listing/review and blank-UID coverage. Updated POST expectation to the user's current submitted status and removed obsolete filter interactions from the dashboard test because the user commented out filters. Preserved user UI/source edits.
- Studio merge follow-up: merged panel implementation is complete and its Generate test passes. Initial full web run had one unrelated failure from removed dashboard filters; test now reflects current UI.
- npm run typecheck PASS. Final web suite result recorded below. Prior production build/HTTP environment blockers remain; no new deployment or generation.
- Next action: User refreshes the dashboard to load the six existing requests.
- Final validation: npm run test:web PASS, 49/49 tests, including the merged Studio panel and submitted-request compatibility.

## 2026-10-28 — Confirm rejection
- Objective/approval: User requested confirmation before rejecting an admin request; directly authorized UI follow-up.
- Changes: admin-requests-page.tsx opens an accessible native dialog naming the manga/chapter, with Keep request and Reject request actions, default focus on Keep request, Escape cancellation, and focus restoration. Reject PATCH occurs only after confirmation. While saving, actions are disabled and a ref prevents duplicate submissions. Failed writes remain in the dialog with the server error; losing authorization dismisses the dialog. Reuses existing request dialog styling.
- Preserved concurrent user change from pending to submitted. Updated request-action.tsx reopen icon key and test fixtures/expectations to the current submitted contract; no user source edits reverted.
- Validation: npm run test:web PASS 49/49, including opening/cancel/Escape with zero writes, failure retaining the dialog, and confirmed rejection updating exactly once. npm run typecheck PASS. No live request was rejected. No new build/HTTP run for this UI follow-up; existing recorded environment blockers remain.
- Changed paths: apps/web/features/requests/admin-requests-page.tsx; apps/web/features/requests/request-action.tsx; apps/web/tests/admin-requests.test.cjs; CONTEXT.md.
- Next action: Report completed rejection confirmation.

## 2026-10-28 — Simplify Studio project panel
- Objective/approval: User requested removing the introductory heading from the screenshot panel; left side should contain only manga title, status and remarks, with right-side content chosen for project selection.
- Changes: Removed YOUR READING SPACE, A voice for every character, intro description, standalone new-chapter badge and divider. Request manga/chapter is now the h1 with status and remarks beneath. Right side groups current Project for audio and saved-project selector. Without request context, shows loaded project title/progress or New chapter/Awaiting manga pages; empty remarks are explicit. Responsive stacking retained; loading/draft/generation behavior unchanged.
- Paths: apps/web/features/studio/studio-workspace.tsx; studio-request-context.tsx; apps/web/app/globals.css; apps/web/tests/auth-drafts.test.cjs.
- Validation: npm run test:web PASS 49/49; npm run typecheck PASS. Existing Generate test verifies title and right-side project grouping. No live provider calls or new build/HTTP verification for this presentation-only edit; prior recorded environment limitations remain.
- Next action: Report simplified panel complete.

## 2026-10-28 — Navbar interaction styling
- Objective/approval: User requested richer hover/click styling instead of plain rounded rectangles.
- Changed apps/web/app/globals.css only: admin navigation now uses animated sage underlines, a persistent thicker active-page line, subtle hover tint/lift, pressed tint/offset, visible keyboard outline, and reduced-motion overrides. Preserved current Home / Requests / Studio labels, destinations and draft-navigation guards.
- Verification: Rendered actual dashboard/navigation with synthetic data in a local preview; inspected active Requests underline and keyboard focus. Browser computed styles confirmed 3px expanded active underline and collapsed inactive underlines. No JS or route behavior changed; no new tests/build required for this CSS-only change. Preview tab closed and server stopped.
- Next action: Report updated interactions.

## 2026-10-28 — PR description for dev-test-1 into main
- Objective/authorization: User requested inspecting branch changes and drafting a PR description; no PR creation, commit, push or merge requested.
- Evidence: Refreshed origin/main and origin/dev-test-1. Local and remote refs match: main ede54cd, dev-test-1 bdfead4. Compared merge-base diff: 22 files, 1,340 insertions, 296 deletions. Clean working tree before this checkpoint.
- Scope for description: authenticated Firestore request submission/user-owned listing; admin-only shared dashboard and transactional status updates; requester display names; rejection confirmation and icon actions; Studio request/new-chapter handoff and project-selection panel; admin/account navigation; named Firestore database configuration and regression tests. Historical commit titles for auth/idempotency do not add corresponding changes in the final merge-base diff.
- Validation: Fresh npm run test:web and npm run typecheck results recorded in .cache/pr-description-tests.log and .cache/pr-description-types.log. Prior full acceptance/build/HTTP blockers remain documented; no new full-suite success claimed.
- Material limitations for description: browser-local requests are not migrated automatically; reader deletion is not wired to Firestore (legacy localStorage code and commented dialog actions remain); Generate opens Studio preparation and does not bypass uploads/cast/script approval or start paid generation.
- Next action: Deliver copy-ready PR title/body. No GitHub PR created.

## 2026-10-28 — Fix getUsers TS2339 in disposable HTTP build
- Objective/approval: User requested fixing getUsers missing from getAdminAuth return type in app/api/admin/requests/route.ts.
- Root cause: tests/verify_local_http.py replaces the Firebase module in its disposable checkout. Its inferred authentication object included token/session verification and cookie creation but omitted the getUsers method used by the admin requests endpoint. Production getAdminAuth already returns Firebase Admin Auth with getUsers.
- Fix: Added a getUsers method typed with SDK UserIdentifier[] and Promise<GetUsersResult> to the disposable fixture; it throws to prevent live profile lookup. No production casts, SDK changes, credentials, or auth bypass.
- Regression: apps/web/tests/http-fixture-types.test.cjs extracts the actual Python-embedded fixture, substitutes it in-memory through a TypeScript compiler host, and typechecks the real admin requests route. Also checks that fixture getUsers rejects live lookup.
- Checks: npm run test:web PASS 50/50; npm run typecheck PASS; uv run --locked ruff check tests/verify_local_http.py PASS; scoped git diff --check PASS. Full npm run test:http attempted, result in .cache/getusers-http.log; prior network/Windows harness blockers remain separate from the fixed TypeScript contract.
- Next action: Report fixture fix and verification; user reruns CI/HTTP build.
