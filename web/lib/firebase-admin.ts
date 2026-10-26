import "server-only";
import { applicationDefault, getApps, initializeApp } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";
import { getFirestore } from "firebase-admin/firestore";

function getAdminApp() {
  const projectId = process.env.FIREBASE_PROJECT_ID || process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID;
  if (!projectId) throw new Error("Firebase server project is not configured.");
  const app = getApps().find(app => app.name === "koetts-server") ?? initializeApp({ credential: applicationDefault(), projectId }, "koetts-server");
  return app;
}

export function getAdminAuth() {
  return getAuth(getAdminApp());
}

export function getAdminFirestore() {
  const databaseId = process.env.FIRESTORE_DATABASE_ID;

  if(!databaseId){
    throw new Error("Firestore database ID is not configured");
  }

  return getFirestore(getAdminApp(), databaseId);
}
