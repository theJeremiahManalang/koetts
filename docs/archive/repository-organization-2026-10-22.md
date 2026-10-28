# Repository organization evidence — 22 October 2026

## Scope and approval

The user approved the rewritten repository organization scope with “yes”. Work covered domain ownership, entrypoint compatibility, stale material cleanup, developer documentation, harness rewriting, and removing repository-shared skills. No cloud, paid generation, or publication work was included.

## Changes and preservation

- Moved model identity, image helpers, MAGI adaptation, and lazy runner selection into `manga_vision/`. Root modules remain aliases to the same module objects, preserving legacy imports and monkeypatch behavior. Runtime callers import the owning package directly.
- Moved studio workspaces, draft helpers, ordering helpers, and snapshot types into `web/features/studio/`. Next.js routes remain entrypoints; shared identity, library UI, and server transport remain under `web/components/` and `web/lib/`.
- Removed five unreachable route-adjacent UI copies. The retained components match their previous implementations apart from import paths. Removed two unselected `web/lib/*.test.cjs` copies; their only differences from retained tests were relative import paths.
- Archived unique historical inspection, research, validation, review, recovery, and starter material. Removed a superseded handoff containing only stale routing/status. Preserved accepted target decisions, migration scopes, and durable alignment evidence.
- Added the developer setup guide, refreshed root/web/image/model guides, corrected stale authentication claims, and updated source maps and links.
- Replaced shared workflow skill discovery with scoped pipeline instructions. Retained supplied writing principles and skill mechanics as explicit documentation references. Removed all three repository-shared skills and their lockfile after updating active pointers.
- Removed the generated Firebase debug log and ignored local tool caches/settings and standalone example output. Results, supplied samples, model caches, credentials, and existing environment files were preserved.

## Verification

Checks ran on the resulting source tree. Node used `/home/ssuish/.nvm/versions/node/v22.22.3/bin` ahead of the default shell PATH. Python checks used a disposable environment at `/tmp/manga-repo-check-env` with CPython 3.13.11 and dependencies installed from the repository audio/API manifests. Model inference remains documented against a separate Python 3.11 environment and was not exercised here.

| Check | Result |
| --- | --- |
| `/tmp/manga-repo-check-env/bin/python -m unittest discover -s tests -v` | 101 tests, 99 passed, 2 optional skips |
| `npm test` in `web/` | 9 test files passed |
| `npm run typecheck` in `web/` | Passed |
| `npm run build` in `web/` | Passed after fresh `.next` cache and process/port access |
| `/tmp/manga-repo-check-env/bin/python tests/verify_local_http.py` | Passed studio and frontend-only production modes; includes one HTTP integration test |
| `run.py --help`, `python -m manga_tts --help` with the selected interpreter | Passed without model downloads |
| Legacy `config`, `files`, `magi`, `runners` imports | All alias the canonical module objects |
| Local Markdown links | Validated throughout root/scoped guides and `docs/`, including archived material |
| `git diff --check` | Passed |

The full suite skipped external saved-project compatibility because no sample was supplied and HTTP integration because no server URL was configured. The separate disposable HTTP runner subsequently exercised the HTTP integration test against its own temporary production server. External sample compatibility remains unverified.

Initial default-shell web attempts failed because its Node executable lacked modern syntax and test-runner support. Initial Python lacked Pillow. A cached-only dependency attempt lacked required API package versions; the disposable environment was then installed normally. Initial Turbopack builds failed with `binding to a port: Operation not permitted`; a fresh-cache retry with required process access passed. These environment failures did not require source configuration changes.

The HTTP runner copied source and dependencies to temporary runtimes, replaced identity verification only in those copies, and cleared provider keys. No live inference, provider quality evaluation, browser visual audit, or deployment was performed.

## Harness walkthroughs

These are static instruction walkthroughs, not actual model evaluations or context-window fit claims.

| Scenario | Expected route and observed instruction consistency |
| --- | --- |
| Substantial new task | Root guide reaches `docs/agents/prompt-approval.md`; grounded rewrite and explicit approval precede execution. |
| Quick question | Approval guide permits direct answers. |
| Approved follow-up | Existing approval continues to authorize routine work within scope. |
| Material scope change | Approval guide requires a renewed rewrite for the changed portion. |
| Explicit bypass | Approval guide honors an explicit request to skip rewriting. |
| Pipeline or root worker change | Root/web pointers reach `manga_tts/AGENTS.md`; invariants and affected checks remain reachable. |
| Harness edit | Root pointer reaches `docs/agents/writing.md`; skill packaging is disclosed through `skill-mechanics.md`. |
| Hosting or migration | Root pointers reach provider-specific project guides or target/scope/evidence documents. Removed generic cloud skill has no active incoming pointer. |

Reading costs measured using whitespace-separated words and UTF-8 bytes, comparing `HEAD` before this task with the rewritten files:

| Reading unit | Before words/bytes | After words/bytes |
| --- | --- | --- |
| Root guide | 433 / 3708 | 296 / 2545 |
| Web guide, including generated Next.js block | 204 / 1496 | 210 / 1629 |
| Workflow skill body versus scoped pipeline guide | 449 / 3687 | 436 / 3563 |
| Writing skill versus disclosed writing guide | 1777 / 10886 | 1750 / 10683 |

The root guide is smaller. Web guidance grows slightly to name current ownership and authentication boundaries. Skill descriptions no longer contribute repository-wide discovery context. These measurements are text counts, not tokenizer counts.
