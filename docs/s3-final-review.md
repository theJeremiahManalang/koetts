# Final S3 code review

Reviewed 22 October 2026 after explicit user approval. The fixed baseline is
`7d897263f6be605d6bfd052826b0df2f13f0083b`; the reviewed S3 head is
`d3af8726147aa84b1b5fd1d1ad2018d33da5a1e3`. Commands were
`git diff 7d89726...d3af872` and `git log 7d89726..d3af872 --oneline`.
The review covers S3 and its approved authentication-only deployment boundary,
not S4/S5. Existing unrelated checkpoint edits were preserved outside commits.

Independent Standards and Spec reviewers inspected the complete change. Confirmed
findings were reproduced before correction, fixed independently, then reviewed
again. Existing commits were not rewritten or split retrospectively.

## Standards

No actionable documented-standard violations or baseline heuristic smells were
reported. The review used root/web agent guides, the manga workflow skill,
`AUDIO_WORKFLOW.md` and the hosting guide. Follow-up review of both fixes found
no introduced standards issues. Static review findings and fresh test execution
are distinguished below.

## Spec

Two confirmed findings were corrected:

1. **P1 — Same-user token renewal stops active operation polling.** The S3 plan
   requires preserving the studio during renewal and restoring protected actions
   after reauthentication. `api()` rejected reads during verification; `watch()`
   treated that as failure and exited. Because the workspace now stays mounted,
   initialization did not restart polling. Callers also discarded the recovery
   intent after nonterminal returns. A rendered-component regression failed with
   `reauthentication must resume the existing operation without reload`.
   Commit `434c81e` changes only the studio and its regression test: read/poll
   requests wait through same-account verification; mutations never replay
   automatically; stale accounts abort; recovery records clear only after terminal
   acknowledgment. Uncertain outcomes retain their idempotency lookup key.
2. **P2 — Scene ID `cast` receives a cast audit identity.** The S3 plan requires
   recording the actual approval subject and fingerprint. Ordinary source review
   accepts nonblank scene IDs, including `cast`; the audit helper inferred kind
   from that literal ID and recorded the cast fingerprint. A real source-review
   to scene-approval regression failed with `'cast' != 'scene'`. Commit `4161dfa`
   changes only the router and audit regression test, passing explicit subject
   kind/ID pairs for cast, single-scene and batch-scene approval. Prior audit
   history and project data were not rewritten.

Independent Spec follow-up found both findings resolved and no introduced gap.
These findings supersede the earlier absence-of-findings claim for these paths.

## Verification

Commands ran from the repository root unless a different working directory is
specified. Python 3.11.15 was selected explicitly in a fresh temporary environment
because the historical environment no longer existed. Its dependencies came from
`requirements-audio.txt`, `requirements-api.txt` and test/static-check tooling.

| Command or check | Observed result |
| --- | --- |
| `/tmp/manga-final-review-venv/bin/python -m unittest discover -s tests -v` | 101 run; 99 passed; two expected skips: external sample and externally managed HTTP server |
| Focused approval-audit discovery | Eight passed, including source regrouping into scene `cast` and single/batch approval |
| `npm test` in `web/` | 33 passed, including active operation renewal/failure/recovery |
| Focused polling regression after strengthening uncertain-outcome observation | Passed; explicitly observes reconciliation before asserting retained recovery intent |
| `npm run typecheck` and `npm run build` in `web/` | Passed |
| Scoped Ruff on router and audit test | Passed |
| Scoped Pyright on router and audit test | Zero errors/warnings with explicit temporary Python 3.11 environment/import paths |
| Native Chromium, `node /tmp/s3-browser/final-review-polling.cjs` | Passed: pending/failed verification pauses requests, reauthentication resumes polling, reconciliation retains intent, zero page errors |
| Whitespace checks for each bounded commit | Passed |

The Browser plugin was unavailable; regular Playwright used installed Chromium.
The temporary browser harness bundled actual studio/auth components and mocked
external Firebase, navigation and child review UI. No live user credentials or
provider calls were used. The durable regression is
`web/tests/auth-drafts.test.cjs`. An initial test-cleanup failure from asynchronous
activity outliving its synthetic window was corrected by draining the owned timer
before teardown; the final focused and full web runs pass.

No cloud deployment, role change, paid inference or publication ran during this
review. The fixes are local commits; deployed S3 verification revisions retain
their earlier validated source. Both corrected paths concern local project
processing, which remains disabled in hosted mode. Previous live acceptance is
recorded separately in `alignment-status.md`; no new live validation is claimed.

Final totals: Standards zero findings; Spec two fixed, highest priority P1 polling;
zero remaining actionable findings in the reviewed scope.
