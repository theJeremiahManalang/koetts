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
