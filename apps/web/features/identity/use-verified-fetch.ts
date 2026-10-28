"use client";

import { useCallback, useRef } from "react";
import { useAuth } from "./auth-provider";
import { getFirebaseAuth } from "./firebase-client";

/** Pin an interactive request to the identity that initiated it. */
export function useVerifiedFetch() {
  const { user, authorizationReady } = useAuth();
  const authorization = useRef({ uid: user?.uid, ready: authorizationReady });
  authorization.current = { uid: user?.uid, ready: authorizationReady };
  return useCallback(async (url: string, options: RequestInit = {}) => {
    const uid = authorization.current.uid;
    const current = getFirebaseAuth().currentUser;
    if (!uid || !authorization.current.ready || !current || current.uid !== uid) throw new Error("Verify your account before continuing.");
    const token = await current.getIdToken();
    if (!authorization.current.ready || authorization.current.uid !== uid || getFirebaseAuth().currentUser?.uid !== uid) throw new Error("Verify your account before continuing.");
    const headers = new Headers(options.headers);
    headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(url, { ...options, headers });
    if (authorization.current.uid !== uid) throw new Error("Your account changed. Please sign in again.");
    return response;
  }, []);
}
