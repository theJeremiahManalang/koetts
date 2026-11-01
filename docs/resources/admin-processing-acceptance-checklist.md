# Admin processing acceptance checklist

Use one copy per test pass. Record observations separately for local and hosted
environments. Do not include passwords, ID tokens, cookies, API keys, or secret
values in this file.

## Test record

| Field                                             | Record                                             |
| ------------------------------------------------- | -------------------------------------------------- |
| Tester                                            | me                                                 |
| Date and timezone                                 | 01-02-2026                                         |
| Code revision (`git rev-parse HEAD`)              | b411be03a2cd2842f3e597d25008df6aaed422eb           |
| Browser and version                               | OperaGX                                            |
| Local browser URL, if applicable                  | 127.0.0.0:3000                                     |
| Hosted URL                                        | <https://koetts--koetts-9bf7f.us-east4.hosted.app> |
| Hosted frontend revision, if checked              |                                                    |
| Test image/sample identifier (no private content) |                                                    |
| Evidence directory or link                        |                                                    |

Mark each result as **Pass**, **Fail**, **Blocked**, or **Not run**. Put the
observed behavior, exact non-secret error text, and relevant timestamp in the
Actual behavior column.

## Local acceptance

Start from the repository root with the pinned Node/npm versions and configured
local Firebase environment:

```bash
MANGA_FRONTEND_ONLY=0 MANGA_EXECUTION_MODE=local npm run dev
```

| Check                    | Expected behavior                                                                                                                                              | Actual behavior and timestamp                                                                                                                                              | Result  |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| Open local app           | Login page or signed-in landing page loads without a Next.js error overlay. Record the exact URL host (`localhost` or `127.0.0.1`).                            | Working as expected                                                                                                                                                        | Pass    |
| Google sign-in           | Sign-in completes against Firebase project `koetts-9bf7f`; no unauthorized-domain error.                                                                       | Earlier unauthorized-domain error resolved; admin access succeeded in this pass.                                                                                           | Pass    |
| Admin access             | After signing out and back in, the approved admin can open `/admin/requests` and Studio at `/`.                                                                | Working as expected                                                                                                                                                        | Pass    |
| Non-admin boundary       | A non-admin account cannot access admin actions or processing controls.                                                                                        | Working as expected                                                                                                                                                        | Pass    |
| Upload one image         | One test image uploads and displays correctly. Record the test identifier, not private image data.                                                             | Working as expected                                                                                                                                                        | Pass    |
| Submit a chapter request | The request appears in the request dashboard for its owner and admin.                                                                                          | Working as expected                                                                                                                                                        | Pass    |
| Approve request          | Admin approval succeeds; approval alone starts no processing.                                                                                                  | Working as expected                                                                                                                                                        | Pass    |
| Local standalone creation | Without a selected request, Create remains available and the UI labels the project standalone. With a request selected, show its title and status. | At baseline, no request was selected and Create was available, but the UI did not identify the project as standalone. | Fail |
| Local CPU extraction     | If intentionally run, the operation reports progress and a terminal result; record duration, outcome, and output quality.                                      | Didn't run                                                                                                                                                                 | Not run |
| Local Gemini stage       | User starts any paid call manually. Stay within the approved USD 5 Gemini allowance; record model, call count, result, and observed cost.                      | User reports local audio generation passed; model, call count, and observed cost were not recorded.                                                                        | Pass |
| Result review            | Generated artifacts are attached to the intended project and can be reviewed; do not publish without the required human review and exact-export approval.      | Not separately recorded in this manual pass.                                                                                                                               | Not run |

## Hosted acceptance

Hosted processing remains paused. Do not enable dispatch, resume production, or
start extraction/Gemini jobs as part of this checklist. The paused-state check
below verifies that the guard blocks work.

| Check                           | Expected behavior                                                                                                                                               | Actual behavior and timestamp                                              | Result  |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ------- |
| Sign in                         | Approved admin signs in at the hosted URL and reaches the admin UI.                                                                                             | Working as expected.                                                       | Pass    |
| Admin request dashboard         | `/admin/requests` loads for the admin; non-admin remains denied or redirected.                                                                                  | Working as expected.                                                       | Pass    |
| Private API identity diagnostic | While signed in, `/api/auth/backend` verifies the frontend/private API identity path without exposing credentials.                                              | Working as expected                                                        | Pass    |
| Upload one image                | One test image uploads and displays correctly.                                                                                                                  | Working as expected.                                                       | Pass    |
| Select approved work            | Create is enabled only after opening Studio from an approved request with eligible work selected. Direct Studio without a work selection keeps Create disabled. | Opened Studio directly; after uploading an image, Create appeared enabled. | Fail    |
| Confirm production pause        | Admin-visible status reports production paused before attempting Create.                                                                                        | Working as expected                                                        | Pass    |
| Attempt guarded Create          | UI reports **“Hosted production is paused”**; API returns the sanitized paused response; no job or operation starts.                                            | Confirmed by user: notification showed as expected; no job started.        | Pass    |
| Operation status stream         | Hosted admin gets current/progress/terminal status by SSE, reconnects to current state, and makes no recurring `?job=` requests.                                 | Not deployed or manually checked in the recorded pass.                     | Not run |
| Scheduler and provider boundary | Both hosted schedulers remain paused and provider allowance/call caps remain zero. Do not change configuration for this checklist.                              | Not checked in this manual pass.                                           | Not run |
| Playback and session checks     | Record authenticated playback/range behavior, sign-out/session revocation, and denial after revocation when separately scheduled.                               | Pending.                                                                   | Not run |
| Recovery checks                 | Record durable operation recovery/restart and rollback evidence when separately authorized.                                                                     | Pending.                                                                   | Not run |

## Hosted log capture

Record the exact UTC interval of the manual hosted pass. After the test, an
operator with Cloud Logging access can capture the matching logs into a new,
private, ignored directory:

```bash
uv run python tools/capture_hosted_logs.py \
  --since 2026-11-02T00:00:00Z \
  --until 2026-11-02T00:30:00Z \
  --output results/hosted-validation-YYYYMMDDTHHMMSSZ
```

Replace both example timestamps with the actual UTC test window. Use a new output
directory each time. Review `summary.json` and relevant entries in `logs.json`
against this checklist. Raw logs may contain operational or user data: keep them
private and uncommitted. Logs do not prove Gemini usage or final cost; reconcile
actual spend separately in the GCP billing view.

## Pass summary

| Environment | Passed | Failed | Blocked | Not run | Reviewer notes                             |
| ----------- | -----: | -----: | ------: | ------: | ------------------------------------------ |
| Local       |      8 |      1 |       0 |       2 | Standalone mode needs clearer status text. |
| Hosted      |      6 |      1 |       0 |       4 | Direct entry/Create and SSE remain unverified after fixes. |

### Outstanding blockers and next actions

- Local/hosted selection UI: retest the new explicit state labels and the current
  work selection after client navigation.
- Hosted CPU/Gemini processing: remains intentionally paused; requires a separate
  explicit decision and measured limits before any hosted processing trial.
- Session revocation, authenticated playback, recovery, rollback, and final cost
  reconciliation remain outstanding acceptance evidence.
