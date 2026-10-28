"use client";

import { useEffect, useState } from "react";
import { useAuth } from "../identity/auth-provider";

type RequestContext = { mangaTitle: string; chapter: number; notes: string; status: string };

/** Request context is a reference, never an instruction to overwrite an open project. */
export function StudioRequestContext({ projectTitle, projectStatus }: { projectTitle?: string; projectStatus?: string }) {
  const { user, authorizationReady } = useAuth();
  const [request, setRequest] = useState<RequestContext | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("request");
    if (!id || !user || !authorizationReady) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void (async () => {
      try {
        const token = await user.getIdToken();
        if (controller.signal.aborted) return;
        const response = await fetch(`/api/admin/requests?id=${encodeURIComponent(id)}`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store", signal: controller.signal });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Could not load the request.");
        const item = data.requests?.[0];
        if (!item || typeof item.mangaTitle !== "string" || typeof item.chapter !== "number" || typeof item.notes !== "string" || typeof item.status !== "string") throw new Error("Invalid request data.");
        if (!controller.signal.aborted) setRequest(item);
      } catch (error) {
        if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Could not load the request.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [user, authorizationReady]);
  if (loading) return <p role="status">Loading request details…</p>;
  if (error) return <p className="notice error" role="alert">{error} <a href="/admin/requests">Back to requests</a></p>;
  return <div className="studio-request-context" aria-label={request ? "Selected audiobook request" : "Selected audio project"}><div className="studio-request-title"><h1>{request ? `${request.mangaTitle} · Chapter ${request.chapter}` : projectTitle || "New chapter"}</h1><span className="studio-request-status">{request ? `Status: ${request.status}` : projectStatus || "Awaiting manga pages"}</span></div><p className="studio-request-remarks"><span>Remarks</span>{request?.notes || "No remarks provided."}</p></div>;
  // <p className="control-note">Upload this chapter’s manga pages below, then review the cast and script before rendering audio. If Studio recovered an unfinished job, finish it before starting this chapter. Update the request’s status after reviewing your work.</p>

}
