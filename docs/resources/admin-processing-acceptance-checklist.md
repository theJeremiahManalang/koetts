# Admin processing acceptance checklist

Create a private copy for each test pass. From the repository root:

```bash
mkdir -p manual-testing
test_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
cp docs/resources/admin-processing-acceptance-checklist.md \
  "manual-testing/admin-processing-$test_stamp.md"
```

The root `manual-testing/` directory is gitignored. Keep local and hosted
observations separate. Never record passwords, ID tokens, cookies, API keys, or
secret values. Gitignore prevents future staging; it does not erase earlier Git
history.

## Test record

| Field | Record |
| --- | --- |
| Tester | |
| Date and timezone | |
| Code revision (`git rev-parse HEAD`) | |
| Browser and version | |
| Local browser URL, if applicable | |
| Hosted URL | |
| Hosted frontend revision, if checked | |
| Test image/sample identifier (no private content) | |
| Private evidence directory | |

Mark each result **Pass**, **Fail**, **Blocked**, or **Not run**. Record observed
behavior, exact non-secret error text, and relevant timestamp in Actual behavior.

## Local acceptance

Start from the repository root with pinned Node/npm and configured local Firebase:

```bash
MANGA_FRONTEND_ONLY=0 MANGA_EXECUTION_MODE=local npm run dev
```

| Check | Expected behavior | Actual behavior and timestamp | Result |
| --- | --- | --- | --- |
| Open local app | Login or signed-in page loads without a Next.js error overlay. Record exact host (`localhost` or `127.0.0.1`). | | Not run |
| Google sign-in | Sign-in completes against the configured Firebase project without unauthorized-domain error. | | Not run |
| Admin access | Approved admin opens `/admin/requests` and Studio at `/`. | | Not run |
| Non-admin boundary | Non-admin cannot access admin actions or processing controls. | | Not run |
| Upload one image | Test image uploads and displays. Record identifier, not private image data. | | Not run |
| Submit chapter request | Request appears for its owner and admin. | | Not run |
| Approve request | Admin approval succeeds; approval alone starts no processing. | | Not run |
| Local standalone creation | Without selected request, Create remains available and labels project standalone. With a request selected, show its title and status. | | Not run |
| Local CPU extraction | If intentionally run, operation reports progress and terminal result; record duration and output quality. | | Not run |
| Local Gemini stage | User starts paid calls manually within approved allowance; record model, call count, result, and observed cost. | | Not run |
| Result review | Artifacts attach to intended project and can be reviewed; do not publish without required human review and exact-export approval. | | Not run |

## Hosted acceptance

Follow current activation and limits approved for this pass. Do not infer that
production is paused or active from this template; verify current status first.

| Check | Expected behavior | Actual behavior and timestamp | Result |
| --- | --- | --- | --- |
| Sign in | Approved admin signs in at hosted URL and reaches admin UI. | | Not run |
| Admin request dashboard | `/admin/requests` loads for admin; non-admin is denied or redirected. | | Not run |
| Private API identity diagnostic | While signed in, `/api/auth/backend` verifies frontend/private API identity without exposing credentials. | | Not run |
| Upload one image | Test image uploads and displays. | | Not run |
| Select approved work | Create is enabled only for approved eligible work; direct Studio entry without selection keeps Create disabled. | | Not run |
| Confirm production state | Admin-visible status matches the intended paused/active state before Create. | | Not run |
| Attempt guarded Create | When paused, UI and API return sanitized paused response; no job or operation starts. | | Not run |
| Operation status stream | Hosted admin receives current/progress/terminal SSE, reconnects to state, and makes no recurring `?job=` requests. | | Not run |
| Scheduler and provider boundary | Verify current scheduler states, provider allowance, call caps, and spend. Do not change them as part of this checklist. | | Not run |
| Playback and session checks | Record authenticated playback/range behavior, sign-out/session revocation, and denial after revocation. | | Not run |
| Recovery checks | Record durable operation recovery/restart and rollback evidence when separately authorized. | | Not run |
| Human review and publication | Review cast, sources, exact script, and exact export before any publication decision. | | Not run |

## Hosted log capture

Record the exact UTC test interval. Use a new private ignored directory each
time. Raw logs may contain operational or user data.

```bash
uv run python tools/capture_hosted_logs.py \
  --since START_UTC \
  --until END_UTC \
  --output results/hosted-validation-UNIQUE
```

Review `summary.json` and relevant `logs.json` entries against this checklist.
Logs do not prove Gemini usage or final cost; reconcile spend separately in the
authorized billing view.

## Pass summary

| Environment | Passed | Failed | Blocked | Not run | Reviewer notes |
| --- | ---: | ---: | ---: | ---: | --- |
| Local | | | | | |
| Hosted | | | | | |

## Outstanding blockers and next actions

-
