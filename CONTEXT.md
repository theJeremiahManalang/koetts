# Task checkpoint

Updated 20 October 2026. Completed S2, durable local operations and recoverable
local workers, on `feat/architecture-alignment` from starting commit `a5e59a2`.

- **Approval:** user approved the S2 prompt and implementation plan. Scope excludes
  cloud storage/deployment, live or paid generation, publication, and new Node
  dependencies.
- **Decisions:** `docs/target-design.md` records same-host SQLite/WAL scheduling,
  one local slot per MAGI/pipeline stage, per-project exclusivity, idempotency,
  three store-owned attempts, one provider request per worker attempt, 30-minute
  timeout, 15-second heartbeat, 60-second lease, process-identity recovery, and
  operator reconciliation for uncertain provider outcomes. Upload bytes and
  relevant existing visual evidence are fingerprinted at enqueue and verified before
  worker execution. The browser retains multiple pending idempotency keys until the
  corresponding operation is found. `GLOSSARY.md` records the lifecycle terms.
- **Implementation:** `manga_tts/operations.py` owns persistence, claims, fences,
  retries, leases, checkpoints, process reconciliation, and operator resolution.
  `web_workflow.py` dispatches finite workers with operation ID/fence and loads
  trusted parameters from SQLite. Provider callbacks and project locks preserve
  existing engine behavior. The Next workflow route requires `Idempotency-Key`,
  supports lookup by key, and falls back to old JSON job files for polling. The UI
  stops polling and explains `reconciliation_required`. `requirements-audio.txt`
  adds bounded `psutil` for local PID/create-time verification.
- **Changed source/tests:** `manga_tts/operations.py`, `manga_tts/cli.py`,
  `manga_tts/resolution.py`, `manga_tts/router.py`, `manga_tts/tts.py`,
  `web_workflow.py`, `web/lib/workflow.ts`, `web/app/api/workflow/route.ts`,
  `web/app/page.tsx`, `web/lib/types.ts`, `web/lib/idempotency.ts`,
  `requirements-audio.txt`,
  `tests/test_operations.py`, `tests/test_operation_worker_process.py`,
  `tests/operation_worker_process.py`, `tests/test_web_workflow.py`,
  `tests/test_web_http.py`, and `web/tests/idempotency.test.cjs`.
- **Changed docs:** `docs/target-design.md`, `docs/architecture.md`,
  `docs/AUDIO_WORKFLOW.md`, `docs/alignment-status.md`, `web/README.md`,
  `GLOSSARY.md`, and this checkpoint.
- **Review fixes already applied:** extract the shared SQLite claim transition,
  remove the unused store protocol, pass `OperationClaim` through worker state
  transitions, clear provider uncertainty after durable result checkpoint, resume
  safe stopped work automatically, and make the operation store the sole retry
  authority. Later review fixes consolidated the action registry and status types,
  fixed multipart idempotency-key recovery after conflicts/lost responses, and
  rejected changed upload or planning evidence before worker execution. Initial and
  final review reports found no hard code standard breach or remaining
  judgement-call smells. The Spec review found no remaining requirements gaps.
  Findings for checkpoint resume, multipart and lost-response key recovery, source
  image/crop/upload fingerprints, and changed-path inventory were fixed and rechecked.
- **Checks passed:** focused Python suites `test_operations`, `test_web_workflow`,
  and `test_operation_worker_process` (35 tests), plus `test_worker_process` (one
  test); final full Python discovery (80 tests: 78 passed, two expected skips);
  scoped Ruff and import sorting; scoped Pyright (zero diagnostics); `npm test` (10
  passed); `npm run typecheck`; `npm run build` (Next.js 16.4.0);
  `tests/verify_local_http.py` (studio HTTP integration and frontend-only guards);
  and `git diff --check a5e59a2...HEAD`.
- **Limits:** no Firestore, Cloud Run, live model/provider call, paid generation, or
  publication work ran. SQLite/WAL is local-host only; tests do not claim power-loss
  durability. `/tmp/manga-s2-venv` and `/tmp/manga-s2-pyrightconfig.json` are
  temporary verification setup; no runtime dependency beyond `psutil` was added.
- **Next action:** hand off S2 as complete. S3 is the next eligible scope in the
  alignment plan. No push was requested.
