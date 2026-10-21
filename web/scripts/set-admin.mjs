import { applicationDefault, initializeApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";

const [uid, action] = process.argv.slice(2);
if (!uid || !["grant", "revoke"].includes(action)) {
  console.error("Usage: node --env-file=.env.local scripts/set-admin.mjs <Firebase UID> <grant|revoke>");
  process.exit(1);
}
const projectId = process.env.FIREBASE_PROJECT_ID || process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
if (!projectId) throw new Error("Set FIREBASE_PROJECT_ID to your intended Firebase project.");
initializeApp({ credential: applicationDefault(), projectId });
const auth = getAuth();
const user = await auth.getUser(uid);
const claims = { ...user.customClaims };
if (action === "grant") claims.admin = true;
else delete claims.admin;
await auth.setCustomUserClaims(uid, claims);
// Invalidate existing sessions when access is removed.
if (action === "revoke") await auth.revokeRefreshTokens(uid);
console.log(`Admin access ${action === "grant" ? "granted" : "revoked"} for UID ${uid} in project ${projectId}. Sign in again to refresh access.`);
