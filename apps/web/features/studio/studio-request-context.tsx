"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "../identity/auth-provider";
import { useVerifiedFetch } from "../identity/use-verified-fetch";

type WorkContext = { id: string; title: string; chapter: number; status: string; requests: { notes: string; requester_name?: string }[] };
export type HostedWorkState = { id: string; status: "approved" | "published" } | null;

/** Shared work is a reference; it never overwrites or implicitly links a project. */
export function StudioRequestContext({ hosted, showEmptyState, onWorkState }: { hosted: boolean; showEmptyState: boolean; onWorkState?: (work: HostedWorkState) => void }) {
  const { user, authorizationReady } = useAuth();
  const verifiedFetch = useVerifiedFetch();
  const workId = useSearchParams().get("work");
  const [work, setWork] = useState<WorkContext | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    onWorkState?.(null);
    setWork(null);
    setError("");
    if (!workId) return;
    if (!user || !authorizationReady) return;
    const controller = new AbortController();
    void (async () => {
      try {
        if (!/^[a-f0-9]{32}$/.test(workId)) throw new Error("Invalid shared work reference.");
        const response = await verifiedFetch(`/api/shared/admin?work_id=${encodeURIComponent(workId)}`, { cache: "no-store", signal: controller.signal });
        const data = await response.json();
        if (!response.ok) throw new Error("Shared request context could not be loaded.");
        const item = data.work?.[0];
        if (!item || item.id !== workId || typeof item.title !== "string" || !Number.isInteger(item.chapter) || !Array.isArray(item.requests)) throw new Error("Invalid shared work context.");
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
  }, [workId, user?.uid, authorizationReady, verifiedFetch, onWorkState]);
  if (error) return <p className="notice error" role="alert">{error} <a href="/admin/requests">Back to requests</a></p>;
  if (!workId && !showEmptyState) return null;
  if (!work || work.id !== workId) return <p className="control-note" role="status">{workId ? "Loading selected chapter work…" : hosted ? <>No chapter work selected. <a href="/admin/requests">Choose an approved request</a> before hosted creation.</> : "Standalone local project. Selecting approved chapter work is optional."}</p>;
  return <section className="request-notes" aria-label="Selected audiobook request"><h2>Selected chapter work: {work.title} · Chapter {work.chapter}</h2>
    <p>Approval status: {work.status}. Project linking remains a separate action after creation.</p>
    <ul>{work.requests.map((request, index) => <li key={index}><strong>{request.requester_name || "Name unavailable"}</strong>: {request.notes || "No note provided."}</li>)}</ul>
  </section>;
}
