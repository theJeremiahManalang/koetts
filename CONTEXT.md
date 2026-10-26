# Active task handoff

## Objective and approval

Identify and fix the CI failure on PR #14. User approved the bounded implementation prompt on 2026-10-26.

## Finding and decision

The failing job was `verify_fresh_checkout.py`. Its temporary checkout copied `docs/` but omitted root `firebase.json`. The repository checker therefore reported the archived baseline's valid `../../firebase.json` link as broken. Add `firebase.json` to the verifier's copied root files; leave the archived link unchanged.

## Changed paths

- `tools/verify_fresh_checkout.py`: copy root `firebase.json` into the disposable checkout.
- `CONTEXT.md`: record this task and its verification.

## Verification

- `PATH=/home/ssuish/.nvm/versions/node/v22.22.3/bin:/home/ssuish/.local/bin:/usr/local/bin:/usr/bin:/bin uv run --locked python tools/verify_fresh_checkout.py`: passed. Fresh checkout install succeeded; `check:repo` passed; 105 Python tests ran (103 passed, 2 optional skips); 33 web tests passed; no-Torch assertion and external-directory CLI help checks passed.
- `git diff --check`: passed.
- Initial run with default Node 24/npm 11 stopped at `npm ci` because project requires Node 22/npm 10. Rerun used pinned Node 22.22.3/npm 10.9.8.

## Blockers and next action

No local blockers. Commit and push the fix to PR #14 to rerun hosted CI; no commit or push performed.
