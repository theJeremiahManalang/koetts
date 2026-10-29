"use client";
import { useEffect, useState } from "react";
import { useAuth } from "../identity/auth-provider";
import { useVerifiedFetch } from "../identity/use-verified-fetch";

type WorkContext = { id: string; title: string; chapter: number; status: string; requests: { notes: string; requester_name?: string }[] };
export type HostedWorkState = { id: string; status: "approved" | "published" } | null;

/** Shared work is a reference; it never overwrites or implicitly links a project. */
export function StudioRequestContext({ onWorkState }: { onWorkState?: (work: HostedWorkState) => void } = {}) {
  const { user, authorizationReady } = useAuth();
  const verifiedFetch = useVerifiedFetch();
  const [work, setWork] = useState<WorkContext | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("work");
    onWorkState?.(null);
    if (!id) { onWorkState?.(null); return; }
    if (!user || !authorizationReady) return;
    const controller = new AbortController();
    void (async () => {
      try {
        if (!/^[a-f0-9]{32}$/.test(id)) throw new Error("Invalid shared work reference.");
        const response = await verifiedFetch(`/api/shared/admin?work_id=${encodeURIComponent(id)}`, { cache: "no-store", signal: controller.signal });
        const data = await response.json();
        if (!response.ok) throw new Error("Shared request context could not be loaded.");
        const item = data.work?.[0];
        if (!item || item.id !== id || typeof item.title !== "string" || !Number.isInteger(item.chapter) || !Array.isArray(item.requests)) throw new Error("Invalid shared work context.");
        if (!controller.signal.aborted) {
          setWork(item); setError("");
          onWorkState?.(item.status === "approved" || item.status === "published" ? { id: item.id, status: item.status } : null);
        }
      } catch (failure) {
        if (!controller.signal.aborted) {
          setError(failure instanceof Error ? failure.message : "Shared request context could not be loaded.");
          onWorkState?.(null);
        }
      }
    })();
    return () => controller.abort();
  }, [user?.uid, authorizationReady, verifiedFetch, onWorkState]);
  if (error) return <p className="notice error" role="alert">{error} <a href="/admin/requests">Back to requests</a></p>;
  if (!work) return null;
  return <section className="request-notes" aria-label="Selected audiobook request"><h2>{work.title} · Chapter {work.chapter}</h2>
    <p>Status: {work.status}. Attach the intended project from the request dashboard after preparing it.</p>
    <ul>{work.requests.map((request, index) => <li key={index}><strong>{request.requester_name || "Name unavailable"}</strong>: {request.notes || "No note provided."}</li>)}</ul>
  </section>;
}
