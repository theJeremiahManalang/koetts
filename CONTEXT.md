# Active task handoff

## Objective and approval

Implement the user's explicitly approved small-team uv/npm monorepo plan. Preferences: `apps/` + `packages/`; retain intentional demos. Work is complete; final pointer/lint checks passed. Changes are committed and published in PR #14, incorporating the earlier cleanup. No deployment, publication, paid provider calls, or model-weight downloads were authorized/performed.

## Delivered source boundaries

- `apps/web`: root npm workspace, explicit studio/identity/library/requests features, owned demo fixtures, thin route adapters, installed-module Python transport.
- `apps/worker/src/manga_worker`: workflow/OCR/HTTP/auth application adapters and explicit data-root resolution.
- `packages/engine/src/manga_tts`: reusable production engine with preserved namespace.
- `packages/vision/src/manga_vision`: reusable image/inference utilities and CLI; heavy dependencies are optional.
- Root `pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`, runtime pins, and `.npmrc`: frozen workspace management. Removed requirements manifests, root scripts/aliases/examples, nested lock, generic shared skills/templates.
- `tests/unit`, `tests/integration`, `tests/helpers`: grouped regression ownership; `tools/check_repo.py` enforces package/feature boundaries and docs/harness pointers.
- `.github/workflows/ci.yml`, updated `Dockerfile.s3`, cloud source configuration, `tools/verify_fresh_checkout.py`, and updated disposable HTTP runner.
- Root/developer/contribution/domain/hosting docs and scoped agent guides reflect current boundaries. Historical evidence remains archived.

Default data remains repository `results/web`. An absolute `MANGA_DATA_ROOT` overrides it; non-checkout installed workers use the user-data fallback. Web passes the same root to workers. Existing samples/results/model caches/credentials/environment files were preserved.

## Verification

Durable evidence: [monorepo foundation acceptance](docs/archive/monorepo-foundation-2026-10-22.md).

- `npm run check`: passed with pinned Node 22.22.3/npm 10.9.8 and uv 0.11.16/Python 3.11.15. Includes boundaries/docs, Ruff, 105 Python tests (103 passed, 2 optional skips), 33 web tests, Next type generation, typecheck, production build.
- `npm run test:http`: passed studio and frontend-only production modes and one HTTP integration test in temporary runtimes.
- `uv run --locked python tools/verify_fresh_checkout.py`: passed clean-copy frozen installs, checks/tests, no-Torch assertion, external-directory entrypoints.
- CPU/CUDA extra dry runs select pinned accelerator builds; enabling both fails as expected. No accelerator packages or weights were installed in the developer environment.
- Frozen non-editable worker/API subset installed under `/tmp/manga-worker-package-check`; API imports and installed module entrypoints pass outside checkout, with no Torch.
- Root npm override pins patched gRPC 1.14.6; final install reports zero audit findings. Firebase client 12.10.0 supports the selected Node version; Firebase 13 required Node 24 transitively.
- `git diff --check` passed. Final documentation/pointer checks are recorded in completion output.

## Limits and next action

External sample compatibility remains skipped without supplied sample; the HTTP skip in the normal suite is covered by the separate runner. Live inference, Gemini quality, browser visuals, actual hosted CI, Docker image build, accelerator runtime, and cloud rollout remain unverified. Container packaging was validated with the equivalent non-editable workspace install.

No blockers. Review PR #14 or continue the user's next assignment. Current setup commands and interface migration map are in `docs/development.md`; archived evidence does not authorize future scope or cloud actions.

## PR publication follow-up

The user explicitly requested a pull request with a prominent codebase-change warning and detailed old-to-new onboarding. Added the step-by-step migration procedure to `docs/development.md`; the PR body repeats actionable onboarding and validation limits. Current branch: `chore/repo-management`; default base: `main`. GitHub resolves the previous origin URL to `theJeremiahManalang/koetts`. Publication is authorized; merging and deployment are not requested.

PR created: https://github.com/theJeremiahManalang/koetts/pull/14 (base `main`, head `chore/repo-management`). Main implementation commit: `e566d86`. The PR includes an explicit breaking-codebase warning, old-checkout backup/retirement/restoration steps, tool versions, command/import replacements, validation limits, and rollback instructions. `docs/development.md` contains the same durable onboarding procedure. Post-documentation repository/pointer checks and diff whitespace checks passed; existing runtime acceptance evidence remains linked above. PR is open; no merge or deployment performed. Next action: review PR and CI results.
