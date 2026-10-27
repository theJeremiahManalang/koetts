# Active task: S4 shared requests and publication

The user approved the S4 plan and requested implementation on
`feat/shared-managed-request`. Decisions: deduplicate by normalized title, chapter,
and the default audio configuration; reader statuses are pending, approved, and
published. Agreed TDD seams: shared service, authenticated HTTP, and fake-backed
end-to-end flow.

Work so far: added a local SQLite request-store foundation and a focused behavior
test. The store is not connected to routes or UI, and is not an authorization
boundary. `docs/alignment-status.md` records S4 as in progress. Publication was not
implemented: it must bind trusted studio revision, settings, and export artifacts.

Checks: focused Python test and Ruff passed; `npm run typecheck` passed. `npm test` passed; Python skipped the external sample and HTTP server tests, and all 33 web tests passed. An initial sandboxed uv run
failed to download hatchling because DNS was unavailable; escalated uv restored the
pinned build dependencies.

Next: complete request API and UI integration, trusted export review, atomic
publication, authenticated reader playback, end-to-end tests, scope evidence, and
required review. Preserve existing project state; no live publication or paid calls.

Review against `ede54cd946143fa6f9c2a1fc847aacff6520b479` found that SQLite
connections were not closed; fixed with explicit closing and reran the focused test
and Ruff successfully. The spec review confirmed all missing S4 integrations above.
`UV_CACHE_DIR=/tmp/manga-s4-uv-cache npm run check:repo` passed; without that
cache override the sandbox could not write the default uv cache. `git diff --check`
passed. Production HTTP and full `npm run check` have not been run for this partial
work. No S4 acceptance criterion is claimed complete.

Follow-up: added transactional approval attribution and an admin work-list service
method. Focused shared-request tests (two tests) and Ruff pass. These methods are
still not exposed to users; the API and remaining S4 work above remain outstanding.

The user approved the four-phase S4 plan and automatic continuation. Phase 1 now
passes: individual notes, exclusive project link identity, and a worker boundary
that validates and locks existing studio projects. See `docs/alignment-status.md`
for exact checks, skipped tests, initial build failure and independent review.
Phase 2 is next: trusted immutable export review and atomic publication; then
phase 3 authenticated APIs and audio delivery and phase 4 UI and acceptance.
