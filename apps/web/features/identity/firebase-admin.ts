import "server-only";
import { applicationDefault, getApps, initializeApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";

export function getAdminAuth() {
  const projectId = process.env.FIREBASE_PROJECT_ID || process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
  if (!projectId) throw new Error("Firebase server project is not configured.");
  const app = getApps().find(app => app.name === "koetts-server") ?? initializeApp({ credential: applicationDefault(), projectId }, "koetts-server");
  return getAuth(app);
}
