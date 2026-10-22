# Google sign-in

The login and signup pages both use Firebase Authentication's Google provider.
The first successful Google sign-in creates an account; subsequent sign-ins reuse it.
Firebase's browser persistence keeps users signed in across reloads and synchronizes
sign-out between tabs. Both account pages return signed-in users to `/browse`.

## Firebase project setup

The repository currently selects project `koetts-9bf7f` in `.firebaserc`.

1. In Firebase Console, open Project settings > Your apps, select or register the
   web app, and copy its web configuration.
2. Add these public web configuration values to `apps/web/.env.local` (preserve any
   existing server environment settings):

   ```dotenv
   NEXT_PUBLIC_FIREBASE_API_KEY=your-web-api-key
   NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=koetts-9bf7f.firebaseapp.com
   NEXT_PUBLIC_FIREBASE_PROJECT_ID=koetts-9bf7f
   NEXT_PUBLIC_FIREBASE_APP_ID=your-web-app-id
   ```

3. In Authentication > Sign-in method, enable **Google**, choose
   `engr.jeremiah.m@gmail.com` as the project support email, and save.
   Alternatively, the Google provider and known domains are prepared in
   `firebase.json`. After Firebase CLI login, apply them from the repository root:
   `npx --yes firebase-tools@latest deploy --only auth --project koetts-9bf7f`.
   The local configuration alone does not enable the remote provider.
4. In Authentication > Settings > Authorized domains, add the actual deployed
   hostname and local development hostnames (`localhost` and `127.0.0.1` as used).
   Enter hostnames without protocols or port numbers.
5. Restart the development server. For App Hosting, add the same four environment
   variables to `apps/web/apphosting.yaml` with BUILD availability, then rebuild and
   deploy. Next.js embeds `NEXT_PUBLIC_` values at build time.

The Firebase web configuration is public. Never put a service account private key
or the server's Gemini API key into `NEXT_PUBLIC_` variables.

## Server authorization and administrator setup

Only the boolean custom claim `admin: true` grants studio access. Email addresses
and legacy role strings do not grant access. There is no self-service promotion API.

1. Configure server credentials using Application Default Credentials (ADC). On
   Google Cloud, use the runtime's attached service account with the required Firebase
   Authentication permissions. Locally, use ADC or point GOOGLE_APPLICATION_CREDENTIALS
   to a service-account JSON file outside the repository. Never use NEXT_PUBLIC_ for it.
2. Set FIREBASE_PROJECT_ID in apps/web/.env.local to the same project as the public web config.
3. Sign in with Google once, then copy the intended administrator's UID from Firebase
   Console > Authentication > Users. From apps/web/, with trusted administrative credentials:

   node --env-file=.env.local scripts/set-admin.mjs <UID> grant

   To remove administrator access and revoke existing sessions:

   node --env-file=.env.local scripts/set-admin.mjs <UID> revoke

   These commands preserve unrelated claims. Verify the target project and UID first.
   The script needs permission to manage Firebase Authentication users.
4. Sign out and sign in again after changing roles. A granted claim does not appear
   in already-issued tokens until they refresh. Revocation invalidates refresh tokens
   and server checks reject revoked sessions and ID tokens.

The root studio page verifies access on the server before rendering. Unauthenticated
visitors go to login; authenticated non-admins go to Browse. Workflow GET/POST,
extraction POST and asset GET verify admin credentials before reading files or running
Python. No credentials yields 401; a verified non-admin token yields 403.

The browser sends Firebase ID tokens in Authorization headers for studio API calls.
An HTTP-only, SameSite=Strict, one-hour session cookie supports protected image,
audio and download URLs without tokens in URLs. Cookies are Secure in production.
Session creation and deletion require a matching Origin header; token and session
verification check revocation. The provider renews the cookie on ID-token changes
and clears it on sign-out. Session sync must succeed before admin navigation appears.

Behind App Hosting, `MANGA_APP_ORIGIN` pins the exact public HTTPS origin for
session CSRF checks. This avoids comparing the browser origin with Next's internal
proxy URL. Forwarded-host headers never define trusted origins. Local execution
without this setting compares against the request URL; invalid configured origins
fail closed.

Same-user token renewal preserves mounted studio and request drafts. While session
verification is pending or fails, protected controls are inert and studio requests
are blocked. Inline reauthentication can restore access without discarding edits.
Sign-out or an account change clears the private workspace.

The server pins verified actor identity into durable workflow requests. Approval
history records the actor, reviewed revision and subject fingerprint in the same
project commit as the approval. Local CLI identities are explicitly distinguished
from Firebase users; history does not replace approval-validity checks.

`GET /api/auth/backend` is an admin-only diagnostic for the optional private Python
API configured by `S3_API_URL`. It verifies both the calling service and the user
without exposing identity or accessing projects. See [S3 deployment](S3_DEPLOYMENT.md)
for service permissions, verification-only rollout and rollback.

The existing local-only origin checks and MANGA_FRONTEND_ONLY processing switch
remain in effect. App Hosting configured with MANGA_FRONTEND_ONLY=1 still redirects
`/` to Browse and disables processing even for admins. Hosting the Python studio
remotely requires a separate deployment decision.

Files: lib/firebase-admin.ts initializes the server SDK; lib/require-admin.ts verifies
permissions; app/api/auth/session/route.ts manages session cookies; scripts/set-admin.mjs
manages claims. app/studio-workspace.tsx holds the previous client studio UI behind
the server page guard.

## Verification

Run `npm run typecheck`, `npm test`, and `npm run build` from `web`.
With Firebase configured, check login and signup using a Google account, reload
Browse, and sign out. Verify a normal user does not see the generator button,
then assign an admin claim, sign in again, and verify the button targets `/`.
Close the Google popup and retry; blocking popups should show a useful error.

References: [Google sign-in](https://firebase.google.com/docs/auth/web/google-signin)
and [custom claims](https://firebase.google.com/docs/auth/admin/custom-claims).
