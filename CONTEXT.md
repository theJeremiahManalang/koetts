# Active task: preserve /browse while migrating styling to Tailwind

## Objective and approval

On 2026-11-04 the user approved implementation with "Implement this now", following the read-only assessment and recommendation to migrate /browse to Tailwind while preserving its UI. This is the approved follow-up scope. No redesign, backend changes, deployment, paid generation, or request-flow integration is authorized by this task.

## Decisions and changed paths

- apps/web/features/library/browse-page.tsx: move layout, sizing, typography, colors, responsive rules, and interaction-state styles into Tailwind utilities. Keep existing state, event handlers, DOM structure, and browse-* hooks.
- apps/web/features/library/manga-shelf.tsx: migrate shelf/control styling without changing scrolling or keyboard behavior.
- apps/web/features/library/request-preview-modal.tsx: migrate dialog/bottom-sheet styling without changing draft, validation, focus, or submission-preview behavior.
- apps/web/features/library/browse.css: retain only scoped theme variables, unlayered global/account compatibility overrides, focus/disabled rules, and WebKit scrollbar hiding.
- docs/browse-ui-preview.md: document styling ownership and exact-value/breakpoint preservation.
- No dependency, Tailwind configuration, global stylesheet, fixture, authentication, or other route changes.
- Exact pixel values and inclusive media conditions preserve 700px/1100px/1600px behavior. Targeted important utilities override existing unlayered globals. Contextual cover/player styles remain descendant utilities where required.

## Validation

Tools: repository-cached Node 22.22.3/npm 10.9.8 and uv 0.11.16, with PYTHONUTF8=1. UV_CACHE_DIR points to .cache/uv. Test temporary data stays under .cache/browse-tailwind/test-temp.

- Chromium visual comparison: 53/53 screenshots byte-identical to the original commit 79515d3, with zero measured computed-style differences. 35 cases cover home/details/modal/guest/empty at 390, 700, 701, 1100, 1101, 1440, and 1600px. 18 additional cases cover hover, keyboard focus, selected genre, account dropdown, touch, and reduced motion at 390, 1100, and 1440px.
- Repeated all 53 cases using the emitted production CSS files referenced by the built /browse HTML: zero computed-style differences and 53/53 byte-identical screenshots against the original baselines.
- These are isolated renders of the actual components with fixture authentication/state and compiled Tailwind CSS, not live-provider authentication or backend claims. Desktop catalog and mobile modal screenshots visually inspected.
- npm run check:repo: passed.
- npm run lint: passed.
- npm run test:web: 58 tests, 57 passed, 1 failed. Browse interaction coverage passed. Unchanged published-audio.test.cjs fails Windows symlink creation with EPERM.
- npm run typecheck: passed.
- npm run build: passed outside the Windows sandbox; existing broad tracing warnings in apps/web/lib/python.ts remain. The sandboxed Turbopack build stalled and was stopped.
- npm run check: stopped in Python tests: 143 run, 117 passed, 17 skipped, 2 failures, 7 errors. Six errors are shared-request/shared-service SQLite cleanup locks (WinError 32); one is a symlink privilege error (WinError 1314). Failures: worker child-PID assertion and repository instruction-pointer assertion. These paths are unchanged by this UI refactor. Full details: .cache/browse-tailwind/check-final.log.
- Earlier attempts encountered the default shell's uv 0.11.26 mismatch, missing cached build dependencies, Windows cp1252 decoding, and sandbox temporary-directory permissions. Pinned tooling, UTF-8, and an unsandboxed run resolved those setup issues; the distinct test failures above remain.
- git diff --check: passed.
- No test:http run: no transport, auth, packaging, or runtime behavior changed. No live-provider testing, paid generation, or deployment performed.

## Outcome and next action

Implementation and visual verification are complete. Browse CSS declarations decreased from 600 to 33; component utilities own the migrated styles. Ready for user review. The unrelated full-suite failures are recorded above and are not part of the approved styling scope. No further implementation or deployment is pending for this task.

Visual harness, screenshots, and logs are disposable artifacts under .cache/browse-tailwind; original saved results, credentials, and existing caches were preserved.
