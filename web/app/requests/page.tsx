"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { LibraryHeader } from "../../components/library-ui";
import { mangas } from "../data/manga";
import { RequireSignIn } from "../../components/require-sign-in";

type MangaRequest = { id: string; mangaTitle: string; chapter: string; notes: string; status: string; createdAt: string };
const samples: MangaRequest[] = [
  { id: "sample-echoes", mangaTitle: "Echoes of Tomorrow", chapter: "2", notes: "A narrated version of Static.", status: "PENDING", createdAt: "2026-10-20T02:00:00Z" },
  { id: "sample-garden", mangaTitle: "Moon Garden", chapter: "2", notes: "I'd love to listen to Moonflowers.", status: "PROCESSING", createdAt: "2026-10-19T02:00:00Z" },
];
function isRequest(value: unknown): value is MangaRequest {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return ["id", "mangaTitle", "chapter", "notes", "status", "createdAt"].every(key => typeof item[key] === "string");
}
export default function RequestsPage() {
  return <RequireSignIn><RequestsTable /></RequireSignIn>;
}

function RequestsTable() {
  const [requests, setRequests] = useState<MangaRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [selected, setSelected] = useState<MangaRequest | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const deleteTrigger = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem("mangaRequests") || "[]");
      if (!Array.isArray(saved) || !saved.every(isRequest)) throw new Error();
      const next = localStorage.getItem("mangaRequestSamplesAdded") ? saved : [...saved, ...samples.filter(sample => !saved.some(item => item.id === sample.id))];
      localStorage.setItem("mangaRequests", JSON.stringify(next));
      localStorage.setItem("mangaRequestSamplesAdded", "true");
      setRequests(next);
    } catch { setError("Could not load your saved requests. Check that browser storage is available, then reload."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (selected && dialog.current && !dialog.current.open) {
      dialog.current.showModal();
      cancelButton.current?.focus();
    }
  }, [selected]);

  useEffect(() => {
    if (announcement) heading.current?.focus();
  }, [announcement]);

  function closeDialog() {
    dialog.current?.close();
    setSelected(null);
    setError("");
    deleteTrigger.current?.focus();
  }
  function deleteRequest() {
    if (!selected) return;
    try {
      // Read the latest list so deleting does not discard requests added in another tab.
      const saved: unknown = JSON.parse(localStorage.getItem("mangaRequests") || "[]");
      if (!Array.isArray(saved) || !saved.every(isRequest)) throw new Error();
      const next = saved.filter(item => item.id !== selected.id);
      localStorage.setItem("mangaRequests", JSON.stringify(next));
      setRequests(next);
      setAnnouncement(`Request for ${selected.mangaTitle}, chapter ${selected.chapter}, deleted.`);
      closeDialog();
    } catch { setError("Could not delete this request. Please try again."); }
  }

  return <div className="library-shell"><LibraryHeader />
    <main className="requests-page">
      <div className="requests-heading"><div><p className="eyebrow">YOUR AUDIOBOOK LIBRARY</p><h1 ref={heading} tabIndex={-1}>My requests</h1><p>Keep track of the stories you’d like to hear.</p></div><Link href="/request" className="primary-action">New request <span aria-hidden="true">＋</span></Link></div>
      <p className="requests-note">Requests are saved in this browser. Two sample requests are included to preview the table.</p>
      <p className="visually-hidden" role="status">{announcement}</p>
      {error && !selected && <p role="alert" className="notice error">{error}</p>}
      {loading ? <p role="status">Loading requests…</p> : !error && <>
        <div className="requests-table-wrap" role="region" aria-label="Manga requests table" tabIndex={0}><table className="requests-table">
          <caption><span>Requested manga</span><span>{requests.length} {requests.length === 1 ? "request" : "requests"}</span></caption>
          <thead><tr><th scope="col">Manga</th><th scope="col">Chapter</th><th scope="col">Status</th><th scope="col">Requested</th><th scope="col">Actions</th></tr></thead>
          <tbody>{requests.map(request => {
            const manga = mangas.find(item => item.title.toLowerCase() === request.mangaTitle.trim().toLowerCase());
            return <tr key={request.id}>
              <th scope="row"><strong>{request.mangaTitle}</strong>{request.id.startsWith("sample-") && <span className="request-sample">Sample</span>}</th>
              <td>{request.chapter}</td><td><span className={`request-status ${request.status === "PROCESSING" ? "is-processing" : ""}`}>{request.status.toLowerCase().replaceAll("_", " ")}</span></td>
              <td>{Number.isNaN(Date.parse(request.createdAt)) ? "—" : new Date(request.createdAt).toLocaleDateString("en-PH", { month: "short", day: "numeric", year: "numeric", timeZone: "Asia/Manila" })}</td>
              <td><div className="request-row-actions">{manga ? <Link className="button" href={`/manga/${manga.id}`} aria-label={`View ${request.mangaTitle}`}>View manga <span aria-hidden="true">↗</span></Link> : <span className="request-unavailable">Not in the library yet</span>}
                <button type="button" className="button request-delete" aria-label={`Delete request for ${request.mangaTitle}, chapter ${request.chapter}`} onClick={event => { deleteTrigger.current = event.currentTarget; setError(""); setSelected(request); }}>Delete</button>
              </div></td>
            </tr>;
          })}</tbody>
        </table></div>
        {!requests.length && <div className="library-empty"><h2>No requests yet</h2><p>Request a manga chapter to see it here.</p><Link href="/request" className="primary-action">Request an audiobook</Link></div>}
      </>}
      <dialog ref={dialog} className="request-delete-dialog" aria-labelledby="delete-heading" aria-describedby="delete-description" onCancel={event => { event.preventDefault(); closeDialog(); }}>
        <span className="delete-dialog-symbol" aria-hidden="true">×</span><p className="eyebrow">REMOVE REQUEST</p><h2 id="delete-heading">Delete this request?</h2>
        <p id="delete-description">Are you sure you want to delete your request for <strong>{selected?.mangaTitle}</strong>, chapter {selected?.chapter}? This removes the request from this browser. The manga stays in the library.</p>
        {error && selected && <p className="notice error" role="alert">{error}</p>}
        <div className="delete-dialog-actions"><button ref={cancelButton} type="button" className="button" onClick={closeDialog}>Keep request</button><button type="button" className="button request-delete-confirm" onClick={deleteRequest}>Delete request</button></div>
      </dialog>
    </main>
  </div>;
}
