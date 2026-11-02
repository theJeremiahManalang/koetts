# Test and CI audit

The user approved audit and remediation on 2026-11-02, against baseline
`7e9e908`. Inventory includes `.github/workflows/ci.yml`, 55 Python files under
`tests/` (including helpers), and 25 web test files. No tracked `__tests__/`,
`e2e/`, `spec/`, or `specs/` directories were found. Findings below describe
source evidence, not measured GitHub runner performance.

## CI/CD bottlenecks

- The original single job serialized all acceptance after `npm run check`.
  A fast repository/lint/typecheck prerequisite now gates five parallel suites:
  Python, web, production HTTP, Firestore, and fresh-checkout acceptance.
  The final `check` job retains the existing branch-protection check name.
- npm and uv caching already existed and were retained. The pinned Firestore
  emulator jar is now cached and checksum-verified on every use.
- PR concurrency cancels outdated runs; main pushes are not automatically cancelled.
- Failed jobs upload uniquely named logs with seven-day retention. Emulator output
  can now persist outside its temporary directory through `--log-file`.
- A service container was evaluated and deliberately omitted. The existing pinned,
  checksum-verified emulator process already owns readiness and cleanup. Adding
  a container duplicates that lifecycle or changes emulator provenance without
  improving these contracts. No production database is required by CI.
- Suites are split by responsibility; test-count sharding and coverage tooling
  were not added without evidence of a remaining bottleneck. No browser E2E
  runner exists, so browser traces are not claimed.

## Hall of Shame and contract gaps

## Web test audit

Scope: all 25 `apps/web/tests/*.test.cjs` files. No skipped or commented-out tests were found. Existing route loaders exercise actual route adapters with injected private/provider boundaries; transpiling TypeScript source is test loading, not itself an implementation assertion. Mounted UI tests restore DOM globals and unmount roots after each case.

### Hall of Shame findings and remediation

- `auth-drafts.test.cjs`: fixed 25/30/50/1100 ms waits and elapsed-time reconnect loops made authorization, navigation and polling checks dependent on wall time. Replaced them with Node test mock timers and an explicit deferred work-verification response. The test now chooses exactly when server verification completes and advances the application's documented polling/reconnect clock.
- `auth-drafts.test.cjs`: deleted the source-regex SSE test. Mounted hosted-stream test already asserts reconnection, no polling, no duplicate submission, and terminal saved-job cleanup.
- `admin-auth.test.cjs`: deleted regex matching exact handler formatting. Added parameterized HTTP401/403 route execution tests covering workflow GET/POST, assets, SSE and upload. Added matching extraction tests. Denied cases supply malformed/missing payloads to demonstrate rejection precedes parsing and backend calls.
- `hosted-work-context.test.cjs`: removed redundant source-string assertions about component spelling, dependency arrays and query implementation. Mounted navigation/eligibility tests cover those contracts; retained actual failed-verification alert/eligibility assertions. Removed unnecessary zero-time timer flush.
- `hosted-upload.test.cjs`: removed tautological self-equality assertion. Retained exact expected UUID32 mapping.

### Added contract coverage

`hosted-workflow.test.cjs` now verifies absent/malformed/uppercase/overlong SSE identifiers reject before backend access, local execution rejects hosted streams, typed backend error status/body survives the route, and browser cancellation reaches the private transport request signal. Combined with the new authorization table and extraction authorization cases, this adds six meaningful parameterized tests.

### Verification

Pinned Node22.22.3: all 25 web test files passed (exit0). Six directly affected files also executed individually: 44 tests passed, zero failures or skips. Artifacts: `/tmp/web-final.log` and `/tmp/{admin-auth,auth-drafts,hosted-extract,hosted-upload,hosted-work-context,hosted-workflow}-verified.log`. Full run 8.89s versus initial11.93s is directional evidence only, not a benchmark. No runtime files, cloud resources, or provider calls changed. Final integrated checks are recorded below.

## Python test audit

Inventory: 55 Python files under tests/, 343 test methods; full discovery executes 347 tests including inherited cases. Unit suites cover engine, vision and worker; integration suites use isolated temporary filesystem state or explicit loopback emulators. No additional Python __tests__, e2e or spec suites found in tracked inventory.

Hall of Shame fixes:
- tests/unit/worker/test_http_api.py cold-start contention test used 30 ms sleep to encourage a race. Replaced with observed lock acquisition and a threading.Event barrier, proving initialization overlaps a competing attempt without timing luck.
- tests/integration/test_cloud_operations.py listener test polled an unprotected callback list every 10 ms. Replaced with threading.Condition notifications and state predicates. Extended actual Firestore contract through queued, progress and terminal result delivery.
- Removed a dead Mock.return_value overridden by side_effect in the webhook test.

Priority missing contracts added:
- SSE service/user authentication denies access before watch registration (401/403), and missing operation returns 404 with private cache policy.
- Invalid listener update emits stream-error control event and unsubscribes instead of claiming success.

Retained intentionally:
- Emulator/sample/server skipUnless prerequisites; these prevent live-provider access. CI should explicitly provide loopback emulator, not remove safety skips.
- Bounded subprocess/file marker polling and server readiness loops assert observable state and detect early exit; sleeps there are polling intervals, not unconditional success assumptions.
- Four apparent assertion-free process tests delegate to a shared helper containing detailed checkpoint/hash/retry assertions. They cover distinct fault boundaries and are not dead tests.
- Static Terraform tests assert deployment contracts; broad replacement with actual cloud provisioning exceeds offline scope.

Verification: full Python unittest discovery 347 tests, 97 prerequisite skips, pass in 28.603s; focused API/auth contracts 25 tests pass in 3.432s after deterministic contention refactor; Ruff passes on all three changed files. Final integrated discovery also includes the contention refactor. Sandbox HTTP execution hung and was terminated; approved escalated synthetic tests passed. No cloud/model calls.

## Regression exposed by emulator execution

The first real local emulator run executed 108 tests and found one recovery
failure: `FirestoreOperationStore.repair_dispatch_signals` returned a bare bool
from its transaction callback, although `_run` requires `(result, binding_exists)`.
Both return branches now preserve the namespace binding. The existing integration
case covers signal repair and rate limiting, so no duplicate regression was added.

## Review and acceptance

Independent Standards review of CI/tools/web changes and Spec review of test
changes found no remaining findings. Follow-up review and final verification
results are recorded in `CONTEXT.md`. Source assertions retained for static
Terraform contracts are offline safeguards, not proof of live provisioning.
Optional sample/provider acceptance remains separate from synthetic suite results.

Final integrated verification used Node 22.22.3/npm 10.9.8 and pinned uv:
`npm run check` passed (347 Python tests, 97 prerequisite skips, 104 web tests,
lint, typecheck, build); `npm run test:http` passed; the complete Firestore
emulator suite passed all 108 tests after the recovery fix. Initial emulator
failure is retained in `/tmp/manga-audit-firestore.log`; final evidence is in
`/tmp/manga-audit-firestore-final.log` and `/tmp/manga-audit-final-check.log`.
GitHub-hosted workflow execution was not performed. No deployment, production
resume, or paid generation occurred.
Fresh-checkout frozen installation, tests, lightweight dependency checks and
external-directory entrypoint verification also passed.
