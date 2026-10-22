"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./auth-provider";

export function RequireSignIn({ children }: { children: ReactNode }) {
  const { user, loading, authorizationReady, error, login } = useAuth();
  const [loginError, setLoginError] = useState("");
  const [signingIn, setSigningIn] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      const destination = window.location.pathname + window.location.search;
      router.replace(`/login?next=${encodeURIComponent(destination)}`);
    }
  }, [user, loading, router]);

  if (loading || !user) return <main className="loading-screen"><p role="status">{loading ? "Checking your account…" : "Taking you to sign in…"}</p></main>;
  return <div key={user.uid}>
    {!authorizationReady && <p role="alert">{error || "Verifying your account…"} Your draft is retained.
      {error && <button type="button" disabled={signingIn} onClick={() => { setLoginError(""); setSigningIn(true); void login().catch(() => setLoginError("Sign in failed. Please try again.")).finally(() => setSigningIn(false)); }}>Sign in again</button>}
      {loginError && <span>{loginError}</span>}
    </p>}
    <div inert={!authorizationReady}>{children}</div>
  </div>;
}
