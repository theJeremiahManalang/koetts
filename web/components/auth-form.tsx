"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "./auth-provider";
import { authErrorMessage } from "../lib/firebase-client";

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const signup = mode === "signup";
  const { user, isAdmin, loading, authorizationReady, error, login } = useAuth();
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  const signingIn = useRef(false);

  useEffect(() => {
    if (user && authorizationReady && !loading) {
      const next = new URLSearchParams(window.location.search).get("next") || "/browse";
      // Only return to known local pages; never follow an external redirect URL.
      const allowed = ["/request", "/requests", "/browse", ...(isAdmin ? ["/"] : [])].includes(next.split("?")[0]);
      router.replace(allowed ? next : "/browse");
    }
  }, [user, isAdmin, loading, authorizationReady, router]);

  async function handleGoogleSignIn() {
    if (signingIn.current) return;
    signingIn.current = true;
    setPending(true);
    setMessage("");
    try {
      await login();
    } catch (error) {
      setMessage(authErrorMessage(error));
    } finally {
      signingIn.current = false;
      setPending(false);
    }
  }

  return <main className="browse-auth-page">
    <div className="browse-auth-container"><Link href="/browse" className="back-link">← Back to Browse</Link>
      <section className="browse-auth-card" aria-labelledby="auth-heading">
        <p className="browse-eyebrow">KoeTTS · Accessible Manga</p>
        <h1 id="auth-heading">{signup ? "Welcome to KoeTTS" : "Welcome back"}</h1>
        <p className="browse-auth-intro">Sign in with Google to explore the stories you love.</p>
        <div className="browse-auth-form" aria-busy={loading || pending}>
          {(message || error) && <p className="browse-auth-message" role="alert">{message || error}</p>}
          <button type="button" className="browse-auth-submit" disabled={loading || pending || (!!user && authorizationReady)} onClick={handleGoogleSignIn}>
            {loading ? "Checking your account…" : pending ? "Signing in…" : user && authorizationReady ? "Opening your library…" : "Continue with Google"}
            <span aria-hidden="true">→</span>
          </button>
          <p className="browse-auth-hint">New here? Your account is created automatically on your first Google sign-in.</p>
        </div>
        <Link href="/browse" className="browse-auth-guest">Continue browsing →</Link>
      </section>
      <p className="browse-auth-footer">Read manga your way. Read, listen, imagine.</p>
    </div>
  </main>;
}
