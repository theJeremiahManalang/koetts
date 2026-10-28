import { getApp, getApps, initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

export function getFirebaseAuth() {
  const config = {
    apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
    authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
    appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
  };
  if (Object.values(config).some(value => !value)) {
    throw new Error("Google sign-in is not configured yet. Please contact the site administrator.");
  }
  return getAuth(getApps().length ? getApp() : initializeApp(config));
}

export function authErrorMessage(error: unknown): string {
  const code = (error as { code?: string } | null)?.code;
  switch (code) {
    case "auth/popup-closed-by-user": return "Sign-in was cancelled. Please try again when you are ready.";
    case "auth/popup-blocked": return "Allow popups for this site, then try Google sign-in again.";
    case "auth/cancelled-popup-request": return "Another sign-in window is already open. Please finish signing in there.";
    case "auth/unauthorized-domain": return "This website is not authorized for Google sign-in yet. Please contact the site administrator.";
    case "auth/operation-not-allowed": return "Google sign-in needs to be enabled by the site administrator.";
    case "auth/network-request-failed": return "Unable to connect. Check your internet connection and try again.";
    case "auth/account-exists-with-different-credential": return "This email already uses another sign-in method. Please contact support to link your Google account.";
    case "auth/user-disabled": return "This account has been disabled. Please contact support.";
    default: return code ? "We could not complete sign-in. Please try again." : error instanceof Error ? error.message : "Unable to load your account. Please try again.";
  }
}
