# S4 shared requests and publication

Objective: implement the approved four-phase S4 plan on
`feat/shared-managed-request`. The user approved automatic continuation through
phase gates and passing, scoped commits. All four phases and local acceptance are
complete; the completion evidence is in `docs/alignment-status.md`.

## Decisions and boundaries

- Deduplicate by whitespace-normalized, case-folded title, chapter number and the
  default audio configuration. Each reader owns a separate request and original notes.
- Reader statuses are pending, approved and published. Admins see all notes and link
  one existing valid studio project per chapter work. Relinking invalidates old review
  identities and retains any accepted publication.
- Admin audition candidates are immutable copies. Explicit review and publication
  remain separate decisions bound to revision, export version, settings and checksums.
- Published audio requires verified reader identity plus an expiring token. Source
  images stay private. Future manga-page API and cloud shared storage remain outside S4.
- No live publication, paid generation, model inference, deployment or credential change
  was performed. Tests use synthetic decisions and audio in disposable workspaces.

## Completed work

Engine request/review/publication storage, trusted worker orchestration, authenticated
Next routes, reader token/range delivery, request/admin/studio integration, published
catalog and playback are implemented. CLI and web exports share version invalidation.
Reader and admin audition audio survive same-user renewal. Reader accessibility
controls remain available. Old browser-local data is untouched and is not imported.

Changed boundaries include `manga_tts.shared_requests`, shared router export metadata,
`manga_worker.shared` and workflow services, web identity/shared APIs and existing
request/library/studio screens. Documentation and acceptance tests cover these paths.
See `docs/alignment-status.md` for the requirement-by-requirement evidence.

## Verification

Pinned Node 22.22.3/npm 10.9.8 and uv 0.11.16/Python 3.11.15 were used for final gates.

- `PATH=/home/ssuish/.nvm/versions/node/v22.22.3/bin:$PATH UV_CACHE_DIR=/tmp/manga-s4-uv-cache npm run check`
  passed: repo checks, Ruff, 117 Python tests (two optional skips), 55 web tests,
  typecheck and production build. Log: `/tmp/manga-s4-complete-check.log`.
- `PATH=/home/ssuish/.nvm/versions/node/v22.22.3/bin:$PATH UV_CACHE_DIR=/tmp/manga-s4-uv-cache npm run test:http`
  passed studio and frontend-only checks, including the complete fake-backed S4 flow.
  Log: `/tmp/manga-s4-complete-http.log`.
- `PATH=/home/ssuish/.nvm/versions/node/v22.22.3/bin:$PATH UV_CACHE_DIR=/tmp/manga-s4-uv-cache .venv/bin/python /tmp/manga-s4-browser-runner.py`
  passed Chromium at 1440×900 and 390×844, including actual playback/seeking, reader
  and admin renewal, accessibility, requests, publication and linked studio navigation.
  Log: `/tmp/manga-s4-pinned-browser.log`. Browser dependencies and fixture identities
  were replaced only in the disposable copy. Screenshots are temporary `/tmp` artifacts.
- Pinned `npm run build` passed after the final contrast adjustment. Pinned
  `npm run check:repo` and `git diff --check` passed after the documentation update.

The full suite skips HTTP without an externally supplied server (the separate runner
executes it) and external sample compatibility without a supplied sample. Initial
sandbox/cache build failures and earlier Node 24 checks are recorded separately in
alignment evidence; final pinned gates passed.

## Review and next action

Two-axis review against `ede54cd946143fa6f9c2a1fc847aacff6520b479` found no remaining
S4 spec gap. All blocking standards findings were fixed and re-reviewed, including
CLI export identity, audio-path integrity, review recovery and reader/admin renewal.
A trusted-snapshot data-clump observation remains accepted and nonblocking.

Next eligible work: resolve the S5 cloud inputs when that scope is assigned. No S4
work or external blocker remains. Cloud rollout authorization is not implied.
