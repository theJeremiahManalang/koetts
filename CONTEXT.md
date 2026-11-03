# Active task: browse UI preview

## Objective and approval

Implement and document the approved dark `/browse` UI with temporary manga data. User approved implementation on 2026-11-03: "Create a docu for this and implement the changes now." Root `/`, admin routes, authentication and published APIs remain unchanged. No audio, paid generation, deployment, or publication authorized or performed.

## Decisions and changed paths

- `apps/web/features/library/browse-page.tsx`: featured banner, shelf, local search/genre filtering, selection panel, chapter metadata selection, disabled player, existing sign-in gate and account navigation.
- `apps/web/features/library/browse.css`: scoped charcoal/teal theme, common plain covers, wide 360px detail panel and narrow full-width details, fixed player clearance.
- `apps/web/features/temp-data/manga.ts`: eight fictional typed manga fixtures, short and long chapter lists.
- `apps/web/tests/shared-ui.test.cjs`: replace live-browse expectation with fixture interaction coverage; other reader/API tests remain.
- `tools/check_repo.py`: narrowly allow library to import temp-data as required by the approved folder location.
- `docs/browse-ui-preview.md`: approved scope, behavior, integration boundary, deferred work.

## Exact checks and outcomes

- `npm run typecheck`: passed.
- `npm run test:web`: 57/58 passed; existing published-audio symlink test fails with Windows EPERM. Retrying `node --test apps/web/tests/published-audio.test.cjs` outside sandbox has the same failure.
- `node --test apps/web/tests/shared-ui.test.cjs`: 11/11 passed after the final focus-restoration adjustment.
- `npm run check`: blocked at its first step by installed uv 0.11.26 versus pinned 0.11.16. Host Node is 24.19.0 versus repository pin 22.22.3. No toolchain pins changed.
- `.venv/Scripts/python.exe -X utf8 tools/check_repo.py`: passed. Without UTF-8 mode the Windows default cp1252 decoder fails on source Unicode.
- `.venv/Scripts/ruff.exe check .`: passed; targeted checker lint passed too.
- `npm run build`: Turbopack CSS worker exits before connection, both inside and outside sandbox.
- `npm run build --workspace @manga/web -- --webpack`: passed outside sandbox (sandbox attempt failed creating .next directories). Build preceded the final focus-effect timing adjustment, which is covered by the passing UI test.
- `.venv/Scripts/python.exe -m unittest discover -s tests -t . -q`: interrupted after repeated temporary-directory permission errors and no completion; not claimed as passed.
- Initial targeted repository-tools unittest failed on sandbox temporary-directory permissions; retry uses workspace-local `.cache/test-temp`.
- `git diff --check`: passed (only CRLF normalization warning).
- Browser: signed-out narrow `/browse` visually inspected. Signed-in desktop/mobile visual QA remains incomplete: browser session has no login and isolated static fixture preview failed to connect. No authentication bypass added to application. Temporary fixture server stopped.
- HTTP/provider tests not run: no transport/auth/runtime implementation changed; no live-provider claims.

## Blockers and next action

UI implementation complete; full acceptance remains limited by local toolchain mismatch, Windows symlink permissions, Turbopack worker failure, and incomplete signed-in visual inspection. Review `/browse` in a signed-in browser at desktop/mobile widths; rerun normal acceptance in the pinned environment. Preserve all existing results and credentials. `.cache/browse-qa` contains ignored disposable static visual fixtures, not product routes.

Targeted retry result: `.venv/Scripts/python.exe -X utf8 -m unittest tests.unit.test_repo_tools -v` with TEMP/TMP set to `.cache/test-temp` ran but failed the existing `broken instruction pointer` assertion at line 23. No related pointer-check logic was changed. This is recorded as a separate unresolved test failure, not a pass.

## Follow-up: horizontal discovery shelves (2026-11-03)

Approval: user approved the shelf plan and desktop wheel behavior with "Implement these changes". Scope remains `/browse`; no audio or admin/root route changes.

Changes: new `apps/web/features/library/manga-shelf.tsx` owns independent scrolling, labelled arrow controls, edge states, keyboard navigation, non-passive vertical-wheel translation, horizontal-gesture/zoom preservation, and reduced-motion behavior. Browse now displays Recently added, ranked Top 10 Mangas, the request banner, then Today's Top Picks for You. Each shelf has 10 manga from explicit `browseShelves` fixture lists. Filtering shows one horizontal results shelf. Updated scoped CSS, temporary data, shared UI tests, and `docs/browse-ui-preview.md`.

Validation: `node --test apps/web/tests/shared-ui.test.cjs` passed 11/11, including row counts, ranks, banner URL, independent wheel movement, both edges, pixel/line/page delta modes, horizontal gestures, modifier keys, touch-pointer exemption, keyboard/buttons, filtering, focus, and no audio requests. `npm run typecheck` passed. `npm run check` still stops at uv 0.11.26 versus pinned 0.11.16.

Visual QA: isolated server-rendered fixture snapshots inspected at 1440x1000 and 390x844; shelves overflow internally with hidden scrollbars and document width stays within viewport. Snapshot uses mock identity and no hydration, so wheel behavior is verified by the DOM interaction test, not this visual check. Temporary public snapshot files removed and browser viewport restored. Existing real authentication is unchanged.

Follow-up completion: `.venv/Scripts/python.exe -X utf8 tools/check_repo.py`, `.venv/Scripts/ruff.exe check .`, and `git diff --check` passed. `npm run build --workspace @manga/web -- --webpack` passed outside sandbox. No HTTP/provider tests run for this UI-only follow-up. Next action: user review of the shelves; standard full acceptance still requires the pinned uv environment. No new implementation blockers.

## Follow-up: smooth motion (2026-11-03)

User authorized smooth scrolling and manga-selection animation, with Framer Motion only if needed. Native smooth scroll now accumulates wheel destinations; reduced-motion preference selects instant scrolling. Keyed detail panels use a 240ms CSS fade/slide entrance, and selected cards lift subtly. No dependency additions or route/admin/audio changes. Changed manga-shelf.tsx, browse-page.tsx, browse.css, shared-ui.test.cjs, and browse-ui-preview.md.

Checks: shared UI tests 11/11 passed, including rapid wheel burst accumulation, smooth behavior, and reduced-motion instant behavior. Typecheck passed. Production webpack build pending. No live visual animation inspection performed in this follow-up; static layout was inspected in the prior shelf task. Existing full-check uv version mismatch remains unchanged.

Motion follow-up completion: production webpack build passed; git diff --check passed. No live animation visual QA claimed. Next action: user review of scrolling feel and detail entrance.

## Follow-up: remove selection motion (2026-11-03)

User requested removal of manga-selection animation due to a scrolling issue. Removed detail fade/slide keyframes and selected-card lift styles from browse.css, and removed the selected-ID key from the aside so switching manga no longer remounts its scroll container. Smooth shelf scrolling is unchanged. Updated browse-ui-preview.md. `node --test apps/web/tests/shared-ui.test.cjs`: 11/11 passed. No live visual check or full build rerun for this small removal. Next action: user verify the reported scrolling behavior with selection animations removed.

## Follow-up: UI-only request modal (2026-11-03)

Authorization: implement modal, retain `/request`, remind user about that pending route decision, and do not connect Firestore. Added library/request-preview-modal.tsx; browse header/banner now open it. Native dialog provides keyboard modality and Escape; body scroll is locked during open, focus restored with preventScroll. Title/chapter/notes validation matches existing bounds. Local preview explicitly says request not submitted. No network submission or persistence, no fake success state. Draft retained across closes but cleared on user change via key. Mobile bottom sheet styling added to browse.css. Existing `/request` page and its backend calls were not modified.

Tests: shared-ui.test.cjs passed 11/11 including both openers, field validation, cancel, focus restoration, draft retention, local preview and no fetch calls. Typecheck/build completion recorded below. No live browser modal/focus-trap QA yet; native dialog modality is not emulated by jsdom. Existing full-check uv mismatch remains.

REMINDER FOR FUTURE REQUEST-FLOW WORK: `/request` remains intentionally available. Remind the user of the pending keep/retire decision; do not remove it or connect the modal to Firestore without authorization. This is documented project follow-up guidance, not a scheduled notification.

Modal completion: npm run typecheck, production webpack build, UTF-8 repository checker, and git diff --check passed. Live browser visual/accessibility verification remains unperformed. Next action: review modal UI; retain `/request` and keep Firestore disconnected from this preview until explicitly approved.
