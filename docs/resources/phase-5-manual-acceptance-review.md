# Phase 5 manual acceptance review

## Finding

The checklist reports that hosted Studio was opened directly, an image was
uploaded, and Create appeared enabled without an approved work selection. Hosted
production remained paused, and the user confirmed the paused notification; no job
started. This is evidence of a UI gating defect, not evidence of an admission or
production bypass.

`StudioRequestContext` read `window.location.search` inside an effect whose
dependencies omitted the current work query. When Next.js reused the Studio client
component during navigation from a selected request to direct Studio, its prior
approved `hostedWorkState` could remain set. The Create button gated only on whether
that state was non-null, not whether its work ID still matched the current URL.
Submission code and `prepareHostedUpload` compare/validate the URL work reference,
and the cloud application transactionally checks approved work and its approval
record before enqueue. Thus stale UI state could enable a button that would still
be rejected before upload or by the server.

The local checklist finding was a mistaken expectation. The hosted plan requires
approved work for hosted project creation and explicitly retains standalone local
creation. The real local usability gap was that Studio did not label an unselected
local project as standalone. Local Google sign-in was later reported resolved.

## Changes

- Drive request lookup from Next's current search parameters; clear prior work and
  eligibility as the query changes, and ignore responses after selection changes.
- Gate hosted Create on verified work whose ID matches the current URL.
- Show the selected work's title and approval status, a hosted empty-state action,
  or a standalone-local label when starting a local project.
- Correct the checklist's local expectation, resolved sign-in result, hosted upload
  observation, and pass/fail totals. Keep the hosted direct-entry failure recorded
  until the user retests the fix.

## Evidence and remaining acceptance

The manual record identifies revision `b411be03a2cd2842f3e597d25008df6aaed422eb`,
Opera GX, and local URL `127.0.0.0:3000`. Its date `01-02-2026` and timezone are
ambiguous and were left as supplied. The checklist contains no hosted frontend
revision or exact UTC test window, so no matching log capture is claimed here.

Focused mounted-Studio navigation, upload, context, and draft tests passed (19); TypeScript typecheck and production
build passed. The full web suite passed 89 of 90 tests under Node `v24.18.0`/npm `11.16.0`;
the remaining multipart stream test failed with `ReadableStream is already closed`.
This checkout requires Node `22.22.3` and npm `10.x`; that runtime is unavailable
in this shell. The failure is outside the changed files and needs rerun with the
pinned runtime. The HTTP acceptance setup also stopped before execution because DNS
could not resolve the Python package host while downloading `h11`.

A mounted Studio regression changes and removes the work query, delays verification,
and checks the actual Create button state. The hosted page was not interactively
retested after this change because no Browser
plugin or Playwright package is available in this environment. Keep production and
schedulers paused. User retest of direct hosted entry, local standalone labeling,
and current-work navigation is still required. CPU/Gemini generation, authenticated
playback, session revocation, recovery, rollback, and final cost review remain
unaccepted.
