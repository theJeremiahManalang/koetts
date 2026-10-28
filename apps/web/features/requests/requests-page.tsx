"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { LibraryHeader } from "../library/library-ui";
import { RequireSignIn } from "../identity/require-sign-in";
import { useAuth } from "../identity/auth-provider";
import { useVerifiedFetch } from "../identity/use-verified-fetch";

type ReaderRequest = {
  id: string; work_id: string; manga_id: string; title: string; chapter: number; notes: string;
  status: "pending" | "approved" | "published"; created_at: string;
};

export default function RequestsPage() {
  return <RequireSignIn><RequestsTable /></RequireSignIn>;
}

function RequestsTable() {
  const { user, authorizationReady } = useAuth();
  const verifiedFetch = useVerifiedFetch();
  const [requests, setRequests] = useState<ReaderRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [selected, setSelected] = useState<ReaderRequest | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const deleteTrigger = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!user || !authorizationReady) return;
    let active = true;
    setLoading(true);
    setError("");
    void fetch("/api/shared/requests", { cache: "no-store" }).then(async response => {
      if (!response.ok) throw new Error();
      return await response.json() as { requests: ReaderRequest[] };
    }).then(data => { if (active) setRequests(data.requests); })
      .catch(() => { if (active) setError("Your requests could not be loaded. Please reload and try again."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [user?.uid, authorizationReady]);

  useEffect(() => {
    if (selected && dialog.current && !dialog.current.open) {
      dialog.current.showModal();
      cancelButton.current?.focus();
    }
  }, [selected]);

  useEffect(() => { if (announcement) heading.current?.focus(); }, [announcement]);

  function closeDialog() {
    dialog.current?.close();
    setSelected(null);
    setError("");
    deleteTrigger.current?.focus();
  }
  async function deleteRequest() {
    if (!selected || pending) return;
    setPending(true);
    try {
      const response = await verifiedFetch("/api/shared/requests", {
        method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: selected.id }),
      });
      if (!response.ok) throw new Error();
      setRequests(current => current.filter(item => item.id !== selected.id));
      setAnnouncement(`Request for ${selected.title}, chapter ${selected.chapter}, deleted.`);
      closeDialog();
    } catch { setError("Could not delete this request. Please try again."); }
    finally { setPending(false); }
  }

  return <div className="library-shell"><LibraryHeader />
    <main className="requests-page">
      <div className="requests-heading"><div><p className="eyebrow">YOUR AUDIOBOOK LIBRARY</p><h1 ref={heading} tabIndex={-1}>My requests</h1><p>Keep track of the stories you’d like to hear.</p></div><Link href="/request" className="primary-action">New request <span aria-hidden="true">＋</span></Link></div>
      <p className="requests-note">These are the requests associated with your account.</p>
      <p className="visually-hidden" role="status">{announcement}</p>
      {error && !selected && <p role="alert" className="notice error">{error}</p>}
      {loading ? <p role="status">Loading requests…</p> : !error && <>
        <div className="requests-table-wrap" role="region" aria-label="Manga requests table" tabIndex={0}><table className="requests-table">
          <caption><span>Requested manga</span><span>{requests.length} {requests.length === 1 ? "request" : "requests"}</span></caption>
          <thead><tr><th scope="col">Manga</th><th scope="col">Chapter</th><th scope="col">Status</th><th scope="col">Requested</th><th scope="col">Actions</th></tr></thead>
          <tbody>{requests.map(request => {
            const timestamp = Date.parse(request.created_at.replace(" ", "T") + "Z");
            return <tr key={request.id}>
              <th scope="row"><strong>{request.title}</strong></th>
              <td>{request.chapter}</td><td><span className="request-status">{request.status}</span></td>
              <td>{Number.isNaN(timestamp) ? "—" : new Date(timestamp).toLocaleDateString()}</td>
              <td><div className="request-row-actions">{request.status === "published" ? <Link className="button" href={`/manga/${request.manga_id}`}>View audiobook <span aria-hidden="true">↗</span></Link> : <span className="request-unavailable">Not published yet</span>}
                <button type="button" className="button request-delete" aria-label={`Delete request for ${request.title}, chapter ${request.chapter}`} onClick={event => { deleteTrigger.current = event.currentTarget; setError(""); setSelected(request); }}>Delete</button>
              </div></td>
            </tr>;
          })}</tbody>
        </table></div>
        {!requests.length && <div className="library-empty"><h2>No requests yet</h2><p>Request a manga chapter to see it here.</p><Link href="/request" className="primary-action">Request an audiobook</Link></div>}
      </>}
      <dialog ref={dialog} className="request-delete-dialog" aria-labelledby="delete-heading" aria-describedby="delete-description" onCancel={event => { event.preventDefault(); closeDialog(); }}>
        <span className="delete-dialog-symbol" aria-hidden="true">×</span><p className="eyebrow">REMOVE REQUEST</p><h2 id="delete-heading">Delete this request?</h2>
        <p id="delete-description">Remove your request for <strong>{selected?.title}</strong>, chapter {selected?.chapter}? Other readers’ requests and published audio remain available.</p>
        {error && selected && <p className="notice error" role="alert">{error}</p>}
        <div className="delete-dialog-actions"><button ref={cancelButton} type="button" className="button" disabled={pending} onClick={closeDialog}>Keep request</button><button type="button" className="button request-delete-confirm" disabled={pending} onClick={() => void deleteRequest()}>{pending ? "Deleting…" : "Delete request"}</button></div>
      </dialog>
    </main>
  </div>;
}
