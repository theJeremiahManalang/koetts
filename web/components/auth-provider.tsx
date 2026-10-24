"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { GoogleAuthProvider, onIdTokenChanged, signInWithPopup, signOut, type User } from "firebase/auth";
import { authErrorMessage, getFirebaseAuth } from "../lib/firebase-client";

type AuthState = {
  user: User | null;
  // Last verified role retains the mounted workspace; authorizationReady gates actions.
  isAdmin: boolean;
  // Initial identity discovery or account changes, never same-account renewal.
  loading: boolean;
  authorizationReady: boolean;
  error: string;
  login: () => Promise<void>;
  logout: () => Promise<void>;
};
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const sessionQueue = useRef<Promise<void>>(Promise.resolve());
  const [state, setState] = useState<Pick<AuthState, "user" | "isAdmin" | "loading" | "authorizationReady" | "error">>({ user: null, isAdmin: false, loading: true, authorizationReady: false, error: "" });
  useEffect(() => {
    let active = true;
    let revision = 0;
    let unsubscribe: (() => void) | undefined;
    try {
      unsubscribe = onIdTokenChanged(getFirebaseAuth(), async user => {
        const current = ++revision;
        setState(previous => previous.user?.uid === user?.uid && user
          ? { ...previous, user, authorizationReady: false, error: "" }
          : { user, isAdmin: false, loading: true, authorizationReady: false, error: "" });
        try {
          const token = user ? await user.getIdTokenResult() : null;
          // Sync an HTTP-only server session before exposing studio navigation.
          const sync = sessionQueue.current.catch(() => {}).then(async () => {
            if (!active || current !== revision) return;
            const session = await fetch("/api/auth/session", {
              method: user ? "POST" : "DELETE",
              headers: user ? { Authorization: `Bearer ${token!.token}` } : {},
            });
            if (!session.ok) throw new Error("Could not establish a secure server session. Contact the administrator.");
          });
          sessionQueue.current = sync;
          await sync;
          if (active && current === revision) setState({ user, isAdmin: token?.claims.admin === true, loading: false, authorizationReady: !!user, error: "" });
        } catch (error) {
          if (active && current === revision) setState(previous => ({ ...previous, loading: false, authorizationReady: false, error: authErrorMessage(error) }));
        }
      }, error => {
        ++revision;
        if (active) setState(previous => ({ ...previous, loading: false, authorizationReady: false, error: authErrorMessage(error) }));
      });
    } catch (error) {
      setState({ user: null, isAdmin: false, loading: false, authorizationReady: false, error: authErrorMessage(error) });
    }
    return () => { active = false; ++revision; unsubscribe?.(); };
  }, []);

  async function login() {
    const provider = new GoogleAuthProvider();
    provider.setCustomParameters({ prompt: "select_account" });
    await signInWithPopup(getFirebaseAuth(), provider);
  }
  async function logout() {
    const clear = sessionQueue.current.catch(() => {}).then(async () => {
      const response = await fetch("/api/auth/session", { method: "DELETE" });
      if (!response.ok) throw new Error("Could not clear the server session. Try signing out again.");
    });
    sessionQueue.current = clear;
    await clear;
    await signOut(getFirebaseAuth());
  }
  return <AuthContext.Provider value={{ ...state, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth must be used within AuthProvider");
  return auth;
}
