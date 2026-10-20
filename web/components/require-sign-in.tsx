"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./auth-provider";

export function RequireSignIn({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      const destination = window.location.pathname + window.location.search;
      router.replace(`/login?next=${encodeURIComponent(destination)}`);
    }
  }, [user, loading, router]);

  if (loading || !user) return <main className="loading-screen"><p role="status">{loading ? "Checking your account…" : "Taking you to sign in…"}</p></main>;
  return children;
}
