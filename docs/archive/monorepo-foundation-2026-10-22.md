# Monorepo foundation acceptance — 22 October 2026

## Approval and scope

The user explicitly requested implementation of the approved “Small-team monorepo foundation” plan. Preferences were `apps/` plus `packages/`, uv for Python, npm for Node, and preservation of intentional product demos. Work includes tooling, package/app boundaries, cleanup, developer docs, harness, CI, and local verification. It authorizes no deployment, publication, model-weight download, or paid provider calls.

## Delivered boundaries

- `apps/web` is the npm workspace. Routes delegate to studio, identity, library/reader, and requests features. Catalog and sample request fixtures remain explicit demo data. Browser-local requests and inactive reader audio are not represented as shared production services.
- `apps/worker` owns the `manga_worker` workflow, OCR, HTTP, and credential adapters. `packages/engine` preserves `manga_tts`; `packages/vision` preserves `manga_vision`. Dependency direction is worker to engine/vision, engine to vision, with no application import from reusable packages. Web feature dependencies and route separation are checked.
- Root uv metadata/lock and root npm metadata/lock are authoritative. Python 3.11.15, Node 22.22.3, npm 10.9.8, and uv 0.11.16 define the tested environment. Default Python installs exclude PyTorch; optional CPU/CUDA 12.4 selections retain original model-stack pins and use explicit indexes.
- Installed module/console entrypoints replace root scripts. `MANGA_DATA_ROOT` selects an absolute state directory shared between web and worker. Checkout defaults preserve `results/web`; non-editable installed workers use the documented user-data fallback outside a checkout.
- Removed legacy import shims, root starter examples, handwritten requirement manifests, nested npm lockfile, generic shared skills/templates, and generated Next type files from source ownership. Next type generation runs before typechecking on fresh checkouts.
- Updated developer/contribution/architecture/workflow/hosting guidance and scoped instructions. Historical source hyperlinks follow moved files; literal historical paths and prior acceptance evidence remain historical.
- CI installs from root locks and runs boundaries/docs, lint, tests, typecheck/build, disposable HTTP checks, and disposable fresh-onboarding checks. Container configuration installs the locked non-editable worker/API subset. No cloud rollout was attempted.

The previous uncommitted cleanup was preserved and incorporated. No commits were created. Supplied samples, saved results, model caches, credentials, and existing local environment settings were preserved.

## Dependency compatibility decisions

Enforcing Node 22 exposed that the previous Firebase 13 client dependency pulled Node-24-only packages. The client is now pinned to Firebase 12.10.0; the existing Admin SDK remains. Auth draft/session, authorization, and HTTP fixture checks pass against that dependency tree.

The fresh dependency audit exposed an older gRPC transitive resolution. Root override `@grpc/grpc-js=1.14.6` replaces it without changing Firebase public APIs. The resulting frozen npm install reports zero audit findings. This is an installation audit result, not a full security assessment.

## Acceptance results

| Check | Result |
| --- | --- |
| `uv lock`, `uv sync --frozen` | Passed; default Python environment has no Torch module |
| `npm ci` | Passed with declared Node/npm engine constraints and one root lockfile |
| `npm run check` | Passed: boundaries/docs, Ruff, Python/web tests, Next type generation, TypeScript, production build |
| Python suite | 105 tests; 103 passed, 2 optional skips |
| Web suite | 33 tests passed |
| `npm run test:http` | Passed disposable studio and frontend-only production builds/servers, including one HTTP integration test |
| `uv run --locked python tools/verify_fresh_checkout.py` | Passed clean-copy frozen installs, repository checks, Python/web tests, lightweight environment assertion, and external-directory module entrypoints |
| `uv sync --frozen --extra vision-cpu --dry-run` | Passed; selects Torch 2.5.1+cpu and torchvision 0.20.1+cpu |
| `uv sync --frozen --extra vision-cuda --dry-run` | Passed; selects Torch 2.5.1+cu124 and torchvision 0.20.1+cu124 |
| Both vision extras together, dry run | Rejected as expected by declared conflicts |
| Non-editable API subset in `/tmp/manga-worker-package-check` | Passed frozen install with `--package manga-worker --extra api --no-dev --no-editable`; installed entrypoints run outside checkout and import the API from site-packages without Torch |
| `git diff --check` | Passed |

The full suite skips external-project compatibility when `MANGA_TTS_SAMPLE_PROJECT` is absent and standalone HTTP integration when `MANGA_WEB_TEST_URL` is absent. The disposable HTTP runner separately executes that integration test against its own server. External saved-project fixture compatibility remains unverified; synthetic saved-project/recovery regressions pass.

The initial fresh-copy check correctly exposed generated Next type references before generation and the handoff file missing from the copy. The checker now excludes generated type declarations from source import validation, the typecheck command generates types, and the copy includes its referenced handoff. Final onboarding passes. Initial SDK engine and transitive audit failures are resolved above.

No live inference, accelerator installation/execution, Gemini quality evaluation, browser visual audit, GitHub-hosted CI execution, Docker image build, or cloud rollout was performed. Container packaging was checked through the equivalent non-editable workspace subset installation; actual image/runtime hosting remains unverified. CPU/CUDA checks establish reproducible resolution, not hardware compatibility or model accuracy.

## Harness walkthrough and reading cost

Static walkthroughs, not model evaluations:

- Substantial task reaches the prompt-approval guide; this task's explicit implementation request supplies approval.
- Quick questions use the direct-answer branch.
- Approved follow-ups retain authorization; material scope changes require renewed approval.
- Explicit bypass requests remain valid.
- Web, worker, engine, and vision pointers reach their scoped instructions; worker/engine invariants remain shared without application-to-engine import reversal.
- Hosting points to service-specific project guides. Reusable personal skills remain outside the repository.
- Root checker validates Markdown links and agent pointers, including archived navigation. Tests prove forbidden engine imports and missing pointers/links are rejected.

Whitespace-word and UTF-8 byte counts versus the original `HEAD` before both cleanup passes:

| Reading unit | Before words / bytes | After words / bytes |
| --- | --- | --- |
| Root guide | 433 / 3708 | 278 / 2318 |
| Web guide, including generated Next block | 204 / 1496 | 218 / 1698 |
| Workflow skill versus scoped engine guide | 449 / 3687 | 236 / 1908 |

Worker-specific instructions are disclosed separately at the application boundary. These counts measure text, not tokenizer usage or context-window fit. Completion evidence belongs here; `CONTEXT.md` is only the active task checkpoint.
