"use client";
import { useEffect, useRef, useState } from "react";
import { AccountNav } from "../identity/account-nav";
import { AdminNav } from "../identity/admin-nav";
import { useAuth } from "../identity/auth-provider";
import { RequireSignIn } from "../identity/require-sign-in";
import { RequestAction } from "./request-action";
import { isAdminRequest, requestActions, requestStatuses, type AdminRequest, type RequestStatus } from "./admin-request-types";

export default function AdminRequestsPage({ studioAvailable = true }: { studioAvailable?: boolean }) {
  return <RequireSignIn><AdminDashboard studioAvailable={studioAvailable} /></RequireSignIn>;
}
function AdminDashboard({ studioAvailable }: { studioAvailable: boolean }) {
  const { user, isAdmin, authorizationReady } = useAuth();
  if (!isAdmin) return <main><h1>Administrator access required</h1><a href="/browse">Return to the reader</a></main>;
  return <Dashboard key={user?.uid} studioAvailable={studioAvailable} ready={authorizationReady} />;
}
function Dashboard({ studioAvailable, ready }: { studioAvailable: boolean; ready: boolean }) {
  const { user } = useAuth();
  const [requests, setRequests] = useState<AdminRequest[]>([]);
  const [filter, setFilter] = useState<RequestStatus | "all">("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [pending, setPending] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [rejecting, setRejecting] = useState<AdminRequest | null>(null);
  const rejectDialog = useRef<HTMLDialogElement>(null);
  const keepRequest = useRef<HTMLButtonElement>(null);
  const rejectTrigger = useRef<HTMLElement | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const updating = useRef(false);
  const active = useRef(false);
  const writable = useRef(ready);
  writable.current = ready;
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => {
    if (rejecting && ready && !rejectDialog.current?.open) {
      rejectDialog.current?.showModal();
      keepRequest.current?.focus();
    }
    if (!ready) { rejectDialog.current?.close(); setRejecting(null); }
    if (!rejecting && rejectTrigger.current) {
      if (rejectTrigger.current.isConnected) rejectTrigger.current.focus();
      else heading.current?.focus();
      rejectTrigger.current = null;
    }
  }, [rejecting, ready]);
  function closeRejection() {
    rejectDialog.current?.close();
    setRejecting(null);
    setError("");
  }
  useEffect(() => {
    if (!user || !ready) return;
    const controller = new AbortController();
    setLoading(true); setError("");
    void (async () => {
      try {
        const token = await user.getIdToken();
        if (controller.signal.aborted) return;
        const response = await fetch("/api/admin/requests", { headers: { Authorization: `Bearer ${token}` }, cache: "no-store", signal: controller.signal });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Could not load requests.");
        if (!Array.isArray(data.requests) || !data.requests.every(isAdminRequest)) throw new Error("The server returned invalid request data.");
        if (!controller.signal.aborted) setRequests(data.requests);
      } catch (error) {
        if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Could not load requests.");
      } finally { if (!controller.signal.aborted) setLoading(false); }
    })();
    return () => controller.abort();
  }, [user, ready, refresh]);
  async function updateStatus(request: AdminRequest, status: RequestStatus) {
    if (!user || !ready || updating.current || loading) return false;
    updating.current = true;
    setPending(request.id); setError(""); setAnnouncement("");
    try {
      const token = await user.getIdToken();
      if (!active.current || !writable.current) return false;
      const response = await fetch("/api/admin/requests", { method: "PATCH", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({ id: request.id, expectedStatus: request.status, status }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not update this request.");
      if (active.current) {
        setRequests(previous => previous.map(item => item.id === request.id ? { ...item, status } : item));
        setAnnouncement(`${request.mangaTitle}, chapter ${request.chapter}, marked ${status}.`);
      }
      return true;
    } catch (error) { if (active.current) setError(error instanceof Error ? error.message : "Could not update this request."); }
    finally { updating.current = false; if (active.current) setPending(""); }
    return false;
  }
  const visible = requests.filter(request => filter === "all" || request.status === filter);
  return <div className="library-shell">
    <header className="site-header admin-site-header">
      <a className="brand" href="/admin/requests" aria-label="KoeTTS admin dashboard"><span className="brand-icon" aria-hidden="true">▥</span><span><span className="eyebrow">ADMIN WORKSPACE</span><span className="brand-title">KoeTTS<span className="brand-dot">.</span></span></span></a>
      <AdminNav active="requests" /><AccountNav />
    </header>
    <main className="requests-page admin-dashboard">
      <div className="requests-heading">
        <div>
          {/* <p className="eyebrow">ALL READER REQUESTS</p> */}
          <h1 ref={heading} tabIndex={-1}>Audiobook requests</h1>
      {/* <p>Review requests and keep each chapter moving.</p> */}
      </div>
      
      <button type="button" className="button" disabled={loading || !!pending || !ready} onClick={() => setRefresh(value => value + 1)}>Refresh requests</button></div> 
      {/* <p className="requests-note">Status changes track progress. Mark ready after reviewing the audio; publication is a separate decision.</p> */}
      {!studioAvailable && <p className="notice">Audio production is available in the local Studio. You can review requests here.</p>}
      {/* <div className="admin-filters" role="group" aria-label="Filter requests by status">
        {(["all", ...requestStatuses] as const).map(status => <button type="button" key={status} className="button" aria-pressed={filter === status} onClick={() => setFilter(status)}>{status === "all" ? "All requests" : status}<span>{requests.filter(item => status === "all" || item.status === status).length}</span></button>)}
      </div> */}
      <p role="status" className="visually-hidden">{announcement}</p>
      {error && !rejecting && <p role="alert" className="notice error">{error}</p>}
        <p className="control-note" role="status">{loading ? "Loading requests…" : `${visible.length} ${visible.length === 1 ? "request" : "requests"}${filter !== "all" ? ` · ${filter}` : ""}`}</p>
        <div className="requests-table-wrap" role="region" aria-label="All audiobook requests" tabIndex={0}>
          <table className="requests-table admin-requests-table"><caption>Audiobook request queue</caption>
            <thead><tr><th scope="col">Manga / chapter</th><th scope="col">Requester</th><th scope="col">Reader note</th><th scope="col">Status</th><th scope="col">Submitted</th><th scope="col">Actions</th></tr></thead>
            <tbody>{!visible.length && <tr><td colSpan={6}><div className="admin-table-empty">
              <h2>{loading ? "Loading requests…" : error ? "Requests unavailable" : requests.length ? `No ${filter} requests` : "No requests yet"}</h2>
              <p>{loading ? "Your request queue will appear here." : error ? "Refresh requests to try again." : requests.length ? "Choose another status to see more requests." : "Requests from readers will appear here."}</p>
            </div></td></tr>}{visible.map(request => <tr key={request.id}>
              <th scope="row"><span className="admin-manga-title" title={request.mangaTitle}>{request.mangaTitle}</span><span className="admin-chapter">Ch. {request.chapter}</span></th>
              <td><span className="admin-requester-name" title={request.requesterName}>{request.requesterName}</span></td>
              <td><span className="admin-reader-note" tabIndex={request.notes ? 0 : undefined} title={request.notes || undefined}>{request.notes || "—"}</span></td>
              <td><span className="admin-status-text">{request.status}</span></td>
              <td>{Number.isNaN(Date.parse(request.createdAt)) ? "—" : new Date(request.createdAt).toLocaleDateString("en-PH", { month: "short", day: "numeric", year: "numeric", timeZone: "Asia/Manila" })}</td>
              <td><div className="request-row-actions admin-request-actions">
                {request.status !== "rejected" && <RequestAction icon="generate" label={studioAvailable ? "Generate" : "Generate (local Studio only)"} href={`/?request=${encodeURIComponent(request.id)}&create=1`} disabled={!studioAvailable || loading || !!pending || !ready} />}
                {requestActions[request.status].map(action => <RequestAction icon={action.status} label={action.label} key={action.status} disabled={loading || !!pending || !ready} onClick={() => {
                  if (action.status === "rejected") {
                    rejectTrigger.current = document.activeElement as HTMLElement | null;
                    setError(""); setRejecting(request);
                  } else void updateStatus(request, action.status);
                }} />)}
                {pending === request.id && <span role="status" className="visually-hidden">Saving…</span>}
              </div></td>
            </tr>)}</tbody>
          </table>
        </div>
      <dialog ref={rejectDialog} className="request-delete-dialog" aria-labelledby="reject-request-heading" aria-describedby="reject-request-description" onCancel={event => { event.preventDefault(); if (!updating.current) closeRejection(); }}>
        <p className="eyebrow">REJECT REQUEST</p>
        <h2 id="reject-request-heading">Reject this request?</h2>
        <p id="reject-request-description">Are you sure you want to reject <strong>{rejecting?.mangaTitle}</strong>, chapter {rejecting?.chapter}? You can reopen the request later.</p>
        {error && rejecting && <p role="alert" className="notice error">{error}</p>}
        <div className="delete-dialog-actions">
          <button ref={keepRequest} type="button" className="button" disabled={!!pending} onClick={closeRejection}>Keep request</button>
          <button type="button" className="button request-delete-confirm" disabled={!!pending || !ready} onClick={async () => { if (rejecting && await updateStatus(rejecting, "rejected") && active.current) closeRejection(); }}>{pending ? "Rejecting…" : "Reject request"}</button>
        </div>
      </dialog>
    </main>
  </div>;
}
