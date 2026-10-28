"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "./auth-provider";

export function AccountNav() {
  const { user, isAdmin, authorizationReady, loading, error: accountError, logout } = useAuth();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const menu = useRef<HTMLDetailsElement>(null);
  const firstName = user?.displayName?.trim().split(/\s+/)[0] || user?.email?.split("@")[0] || "Reader";
  const initial = Array.from(firstName)[0].toLocaleUpperCase();

  useEffect(() => {
    function closeOutside(event: PointerEvent) {
      if (menu.current && !menu.current.contains(event.target as Node)) menu.current.open = false;
    }
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && menu.current?.open) {
        menu.current.open = false;
        menu.current.querySelector("summary")?.focus();
      }
    }
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);
  async function handleLogout() {
    setPending(true);
    setError("");
    try { await logout(); }
    catch { setError("Could not sign out. Please try again."); }
    finally { setPending(false); }
  }
  return <nav className="browse-account-nav" aria-label="Account navigation">
    {loading ? <span role="status">Checking account…</span> : user ? <>
      <details className="account-dropdown" ref={menu} onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) event.currentTarget.open = false;
      }}>
        <summary className="account-dropdown-trigger" aria-label={`Account options for ${firstName}`}>
          <span className="account-first-name">{firstName}</span>
          <span className="account-avatar" aria-hidden="true">{initial}</span>
        </summary>
        <div className="account-dropdown-panel">
          <Link href="/requests" onClick={() => { if (menu.current) menu.current.open = false; }}>My Requests <span aria-hidden="true">↗</span></Link>
          {isAdmin && authorizationReady && <>
            <Link href="/admin/requests" onClick={() => { if (menu.current) menu.current.open = false; }}>Admin dashboard <span aria-hidden="true">↗</span></Link>
            <Link href="/" onClick={() => { if (menu.current) menu.current.open = false; }}>Studio <span aria-hidden="true">↗</span></Link>
          </>}
          <button type="button" disabled={pending} onClick={handleLogout}>{pending ? "Signing out…" : "Sign Out"}<span aria-hidden="true">→</span></button>
        </div>
      </details>
    </> : <>
      <Link href="/login" className="primary-action">Sign in <span aria-hidden="true">↗</span></Link>
    </>}
    {(error || (user && accountError)) && <span className="browse-auth-message" role="alert">{error || accountError}</span>}
  </nav>;
}
