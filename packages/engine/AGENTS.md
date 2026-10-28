# Production engine guide

This package owns reviewed state, planning/synthesis, takes, export, local revision persistence, and durable operation coordination. Preserve the `manga_tts` namespace. Import vision utilities; import no worker/web application code. CLI and application adapters submit decisions through the same router.

## Invariants

- Evidence retains recovered text, image coordinates, explicit order, and source identity. Human decisions remain distinguishable from evidence.
- Review cast, then sources, then exact scripts. Applying sources rebuilds dialogue. Loading proposals does not approve them. Changes invalidate affected approvals.
- Expected-state fingerprints reject stale writes. Reload rather than rewriting fingerprints to force acceptance.
- CLI and workers share writer ownership. Confirm the recorded process stopped before recovering its lock; lease expiry alone proves no such fact.
- Render preflights selection and checkpoints successful segments. Preserve eligible take reuse, selected-take validation, and resume behavior. Inspection/export require no synthesis client.
- Restore validates in staging before publishing to an empty workspace. Export replaces fixed filenames without claiming transactional publication.
- Local files and SQLite coordinate one host. Preserve the distinction from distributed durability and reader publication.

Read `../../docs/AUDIO_WORKFLOW.md` for domain semantics/recovery and `../../docs/architecture.md` for seams. Commands/models live in `src/manga_tts/schemas.py`; router owns validated commits. Storage and operation tests bind their recovery contracts.

Run affected engine tests; shared schema/router/storage changes require the full Python suite. Use injected renderers and synthetic predictions. Run worker integration checks when changing application contracts. Report optional skips and separate live-provider limitations.
