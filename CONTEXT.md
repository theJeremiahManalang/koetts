# Task checkpoint

## Active S3 implementation and deployment — 22 October 2026

- **Approval:** User explicitly approved the full S3 implementation/authentication-only deployment plan, requested implementation and commit on the current branch, and subsequently asked to continue. No role promotion, inference, publication, S4 or S5 processing is authorized. Existing checkpoint edits below are preserved.
- **Implementation:** Draft renewal/failure retention with disabled actions; verified server principals pinned into operations; atomic project approval audit; independently authenticated Python HTTP API; verification-only Docker image; repaired disposable authenticated HTTP harness; frontend diagnostic. Sources: `web/components/auth-provider.tsx`, `web/components/require-sign-in.tsx`, `web/lib/require-admin.ts`, workflow route/worker, `manga_tts/router.py`, `manga_tts/schemas.py`, `manga_tts/http_api.py`, `manga_tts/http_auth.py`. Deployment runbook: `docs/S3_DEPLOYMENT.md`.
- **Checks already run in this task:** Python 3.11.15 `/tmp/manga-s3-venv/bin/python -m unittest discover -s tests -v`: 100 run, 98 passed, two expected skips. Web `npm test`: 31 passed; typecheck and production build passed. Repaired `tests/verify_local_http.py` passed studio HTTP workflow and frontend-only checks using a disposable identity SDK fixture. Scoped Ruff and Pyright passed. Independent Standards and Spec reviews each found zero actionable issues. Initial process-fixture and TypeScript-fixture failures were corrected and rechecked. Temporary environment/logs disappeared when execution resumed; prior tool results remain task evidence.
- **Cloud state:** Project `koetts-9bf7f`, region `us-east4`, existing backend `koetts`. API `koetts-s3-api-00001-gl5` is ready, image digest `sha256:bd5cf2fac59d9733ee408d847eb80b6795ab9c40b7840534b06163d336a43cc2`; build `f2bf2888-ed20-4dce-92fc-08e1e8e106f8`. Private URL `https://koetts-s3-api-gu5jb64hpq-uk.a.run.app`. Verification mode, 1 CPU/512 MiB, zero minimum/one maximum instances. Dedicated runtime subject `116829968863372483123`; App Hosting subject `111180949335785966002`. API invokers are those service accounts only. Custom role `koettsS3AuthVerifier` grants runtime `firebaseauth.users.get`; temporary deployment-user OIDC minting grant is scoped to API service account.
- **Discovery:** Named Firestore database `koetts-default` already has explicit deny-all browser rules, unchanged. One existing Firebase admin, no readers discovered; no promotion performed. Actual App Hosting hostname was added to authorized domains preserving prior domains. Google provider already enabled.
- **Live checks:** Private readiness 200; anonymous platform access 403; missing/forged/duplicate Firebase credentials 401; separate wrong-service-audience token 401. Used direct IAM Credentials generateIdToken with user access token only in memory, avoiding broader getAccessToken impersonation grants. No user impersonation/provider calls. Earlier gcloud impersonation command failed because it requires broader access-token permission; direct ID-token method succeeded.
- **Live browser correction:** First frontend rollout `build-2026-10-21-001` succeeded and anonymous route/denial checks passed. Native Chromium then found session DELETE 403 because browser Origin is public but Next URL is internal. Restored traffic to captured `koetts-build-2026-10-18-001`; user observed session failure and diagnostic404 during rollback. Added explicit canonical `MANGA_APP_ORIGIN`, preserving strict Origin/cross-site checks and ignoring forwarded hosts. Red-green proxy test, 32 web tests and production build pass; focused independent reviews clean. Corrected rollout is running, output `/tmp/manga-s3-frontend-rollout2.log`.
- **Native browser:** `node /tmp/s3-browser/run.cjs` passed actual Chromium draft/upload continuity, native inert, reauth/recovery, account switch and sign-out with mocked external identity. Separate live browser confirmed exact canonical Origin headers, Firebase SDK initialization and the hosted-origin bug. No user credentials entered by agent.
- **Corrected rollout:** `koetts-build-2026-10-21-002` serves100% traffic. Live canonical-origin DELETE200 with secure cookie flags, attacker-origin403, missing-origin403, valid-origin missing-token401, anonymous protected APIs401, root307 and public pages200 all pass. Native Chromium confirms login/Browse session clearing200, enabled Google button, no session error and no runtime errors. User successfully signs in but diagnostic403 confirms reader role; preflight admin remains enabled and a reader now exists. User asked to sign in with existing admin (masked identity shared only in chat). Positive admin diagnostic pending; no role promotion. Temporary verifier minting/self-invocation bindings removed; final IAM confirms App Hosting sole invoker and no temporary user binding.
- **Next:** Record user admin diagnostic result, verify cleanup, finish durable evidence and commit task changes. Preserve prior review-only CONTEXT edits unstaged when committing task checkpoint. Previous frontend baseline remains rollback target. No completion claim until live admin acceptance is recorded or explicitly pending.

## Active handoff: 21 October 2026 merge repair

- Objective and approval: user explicitly approved restoring the admin-gated page,
  integrating incoming operation retry/recovery into the authenticated workspace,
  repairing the API import, and running web checks. Starting tree was clean after
  merge commit `60bd75b`.
- Changed: `web/app/page.tsx` restores the server authorization gate and
  frontend-only `/browse` redirect. `web/app/studio-workspace.tsx` incorporates
  incoming idempotency, pending-operation lookup, and reconciliation handling while
  retaining Firebase authorization, the client admin gate, and KoeTTS branding.
  `web/app/api/workflow/route.ts` restores the missing `requireAdmin` import.
- Regression checks: `web/tests/studio-page.test.cjs` covers anonymous/non-admin
  redirects, authorized rendering, and frontend-only short-circuiting.
  `web/tests/workflow-route.test.cjs` mocks authorization for existing enqueue tests
  and verifies GET/POST denial before processing.
- Results from `web/`: `npm.cmd test` passed all 25 tests; `npm.cmd run typecheck`
  passed; `npm.cmd run build` passed. `git diff --check` passed.
  PowerShell blocked the initial `npm` script launcher; using `npm.cmd` succeeded
  without changing execution policy. Build warned about an outside-repository lockfile.
  Generated `web/next-env.d.ts` changes were reverted.
- Limits: no Python source changed; Python tests and live Firebase/browser checks
  were not run. No deployment or paid generation occurred.
- Next action: user review/commit. No implementation blocker remains.
  [Recovery notes](docs/merge-recovery-2026-10-21.md) preserve pre-resolution sources.
  The earlier checkpoint below is historical.

Updated 20 October 2026. S1/S2 review and remediation completed on
`feat/architecture-alignment`, starting from `b7d4ff2`.

- **Objective and approval:** The user approved independent standards/spec reviews,
  fixes, regression checks, documentation, and a commit. The user selected the
  parent of the first S1 commit as the review baseline: `6423d44dd495d79de6eb6073875c98ad374ee8cb`.
  No deployment, paid inference, or publication was authorized or performed.
  The user subsequently authorized pushing this branch and opening a PR to `main`.
- **Scope and decisions:** Preserve the local studio and S1/S2 contracts. Render
  retries retain the original take baseline and reuse replacements already accepted
  by the operation. Planning retries recognize the checkpointed completion hash.
  Ambiguous enqueue failures retain staged inputs. Explicit reconciliation refreshes
  accepted render state only after worker stoppage and workspace ownership checks.
- **Changed source/tests:** `manga_tts/operations.py`, `web_workflow.py`,
  `web/app/api/workflow/route.ts`, `tests/test_operations.py`,
  `tests/test_operation_worker_process.py`, `tests/operation_worker_process.py`,
  and `web/tests/workflow-route.test.cjs`. Includes the stopped-process termination
  race fix and shared fenced failure handling.
- **Evidence:** `docs/alignment-status.md` links `docs/s1-s2-review.md`, which owns
  the initial findings, remediation, acceptance evidence, and limitations.
  Final independent standards and spec reviews report zero remaining findings
  within the reviewed fixes.
- **Checks:** `/tmp/manga-s2-venv/bin/python -m unittest discover -s tests -v`:
  85 tests, 83 passed, two optional skips (external sample and HTTP server).
  Focused operation tests: 12 passed; worker process tests: six passed.
  `npm test`: 12 passed; `npm run typecheck` and `npm run build`: passed in `web/`.
  Scoped Ruff and import ordering passed. Scoped Pyright with
  `/tmp/manga-s2-pyrightconfig.json`: zero diagnostics. Initial Pyright without the
  environment config reported three psutil source warnings; the configured run
  resolves them. `git diff --check` passed.
- **Limits:** Synthetic audio only; no live provider or cloud verification.
  Ambiguous enqueue failures can retain orphan uploads pending a separate cleanup
  policy. No supplied samples, model caches, or results were changed.
- **Blockers:** None within the approved scope.
- **Next action:** Push the branch and open the authorized PR to `main`, including
  S2 and the review fixes. S1 is already on `origin/main`. S3 remains outside scope.
