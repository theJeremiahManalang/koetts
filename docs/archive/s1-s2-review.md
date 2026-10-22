# S1/S2 review and remediation

Reviewed on 20 October 2026. The user approved the review, implementation,
regression checks, and commit on the current branch. The approved baseline is
`6423d44dd495d79de6eb6073875c98ad374ee8cb`, the parent of the first S1 commit
`de36c74`. The reviewed head is `b7d4ff277c90176c69a7d0a4e56663cab54f4943`.
The comparison is `git diff 6423d44...b7d4ff2`; the follow-up reviews inspect the
working patch against that head.

Requirements come from S1/S2 in `architecture-alignment-plan.md` and the accepted
ownership and local scheduling decisions in `target-design.md`. Standards come
from the repository and web agent guides, the manga workflow skill, and
`AUDIO_WORKFLOW.md`. Independent reviewers examined standards and specification
conformance, followed by a second review of the fixes.

## Standards

The initial review found no documented-standard violations and one low-priority
duplication smell: four handlers repeated fenced failure persistence. A shared
local helper in `web_workflow.run_operation` now handles these cases. The final
standards review reports no remaining findings.

## Spec

The initial specification review found three recovery defects. All were fixed:

1. Forced regeneration repeated an accepted replacement after restart. Render
   operations now checkpoint the pre-existing take identities before synthesis.
   Retried operations reuse accepted replacement takes while still replacing old
   takes requested by the original command. Recovery preserves this baseline even
   when persistence succeeds before progress notification.
2. A lost enqueue response deleted uploads that could already belong to a durable
   operation. The workflow route now retains staged inputs after ambiguous enqueue
   failure. Definite idempotency rejection still removes the unused upload, and a
   successful duplicate submission removes its redundant staging directory.
3. A saved planning proposal failed with a revision conflict on retry. Planning
   completion now records its accepted project hash and completion identity. A
   matching retry completes without another planning request or project mutation.

Follow-up review found that explicit reconciliation also needed to refresh the
render checkpoint after a handled progress failure. It now does so after worker
stoppage and workspace ownership checks, with matching operation fence and slot.
The final specification review reports no remaining findings within these fixes.

A further verified timeout defect returned a live identity when a process vanished
during termination. `stop_process` now returns the stopped identity for that race,
allowing safe work to return to the queue.

## Validation

All Python commands use `/tmp/manga-s2-venv/bin/python`. Web commands run in `web/`.

| Check | Result |
| --- | --- |
| `-m unittest discover -s tests -p test_operation_worker_process.py -v` | Six passed: normal and forced restart, lost or failed progress, operator resolution, and planning completion |
| `-m unittest discover -s tests -p test_operations.py -v` | Twelve passed, including the termination race |
| `-m unittest discover -s tests -v` | 85 tests; 83 passed, two optional skips |
| `npm test` | Twelve passed, including ambiguous enqueue and definite rejection |
| `npm run typecheck` | Passed |
| `npm run build` | Passed with Next.js 16.4.0 |
| Scoped Ruff check and import-order check | Passed for the five changed Python files |
| Scoped Pyright with the existing Python 3.11 virtual-environment configuration | Zero errors, warnings, or informationals |
| `git diff --check` | Passed |

The forced-regeneration regression failed before the fix with three renderer calls
instead of two. The termination-race regression failed before the fix because the
stopped process was reported as live. Subprocess tests use synthetic audio, existing
temporary project fixtures, and no provider credentials.

Scoped lint/type checks cover `manga_tts/operations.py`, `web_workflow.py`,
`tests/operation_worker_process.py`, `tests/test_operation_worker_process.py`, and
`tests/test_operations.py`. Commands are `/tmp/manga-s2-venv/bin/ruff check <files>`,
the same command with `--select I`, and `/tmp/manga-s2-venv/bin/pyright -p
/tmp/manga-s2-pyrightconfig.json <files>`. The config selects Python 3.11, basic
checking, the `/tmp/manga-s2-venv` environment, and repository/tests import paths.
An earlier Pyright invocation without this environment configuration reported
three missing-source warnings for `psutil`; the correctly configured run resolves
them without disabling diagnostics.

The optional skips are external sample compatibility and HTTP integration without
a configured local server. Live providers, cloud integration, deployment,
publication, and power-loss durability remain unverified. Ambiguous failed enqueues
may retain unowned uploads; safe orphan cleanup remains a separate retention concern.
