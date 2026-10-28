"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { RequireSignIn } from "../identity/require-sign-in";
import { useAuth } from "../identity/auth-provider";
import { getFirebaseAuth } from "../identity/firebase-client";

import { AdminNav } from "../identity/admin-nav";
import { AccountNav } from "../identity/account-nav";
import { RequestAction } from "./request-action";

type Candidate = { id: string; revision: string; export_id: string };
type Review = Candidate & { candidate_id: string };
type Work = {
  id: string; title: string; chapter: number; status: "pending" | "approved" | "published";
  requests: { id: string; notes: string; requester_name?: string }[];
  link: { project_id: string } | null; publication_id: string | null;
  candidate: Candidate | null; review: Review | null;
};
type StudioProject = { id: string; name: string };

async function jsonRequest(url: string, options?: RequestInit) {
  const response = await fetch(url, { ...options, cache: "no-store" });
  if (!response.ok) throw new Error("The action could not be completed. Reload and try again.");
  return response.json();
}

export default function AdminRequestsPage() {
  const { user, isAdmin, authorizationReady } = useAuth();
  if (!user || !isAdmin) return <main><h1>Administrator access required</h1><Link href="/browse">Return to the library</Link></main>;
  return <RequireSignIn><AdminWork uid={user.uid} authorizationReady={authorizationReady} /></RequireSignIn>;
}

function AdminWork({ uid, authorizationReady }: { uid: string; authorizationReady: boolean }) {
  const authorization = useRef({ uid, ready: authorizationReady });
  authorization.current = { uid, ready: authorizationReady };
  const [work, setWork] = useState<Work[]>([]);
  const [projects, setProjects] = useState<StudioProject[]>([]);
  const [selectedProjects, setSelectedProjects] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const hasLoaded = useRef(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    const [shared, studio] = await Promise.all([jsonRequest("/api/shared/admin"), jsonRequest("/api/workflow")]);
    setWork(shared.work as Work[]);
    setProjects(studio.projects as StudioProject[]);
    hasLoaded.current = true;
  }, []);

  useEffect(() => {
    if (!authorizationReady) return;
    let active = true;
    if (!hasLoaded.current) setLoading(true);
    void refresh().catch(() => { if (active) setError("Shared work could not be loaded. Please reload."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [authorizationReady, refresh]);

  async function action(item: Work, command: string, fields: Record<string, unknown> = {}) {
    if (busy || !authorizationReady) return;
    setBusy(item.id); setError(""); setMessage("");
    try {
      const current = getFirebaseAuth().currentUser;
      if (!current || current.uid !== uid) throw new Error("Verify your account before continuing.");
      const token = await current.getIdToken();
      const verifyActor = () => {
        if (!authorization.current.ready || authorization.current.uid !== uid || getFirebaseAuth().currentUser?.uid !== uid) {
          throw new Error("Verify your account before continuing.");
        }
      };
      verifyActor();
      let payload: Record<string, unknown> = { action: command, work_id: item.id, ...fields };
      if (command === "prepare") {
        if (!item.link) throw new Error("Attach a studio project first.");
        const snapshot = await jsonRequest(`/api/workflow?project=${encodeURIComponent(item.link.project_id)}`, { headers: { Authorization: `Bearer ${token}` } });
        payload = { ...payload, revision: snapshot.revision };
      }
      verifyActor();
      await jsonRequest("/api/shared/admin", {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` }, body: JSON.stringify(payload),
      });
      verifyActor();
      await refresh();
      setMessage(command === "publish" ? "Reviewed audio is published." : command === "review" ? "Audio review recorded." : command === "prepare" ? "Export is ready to audition." : command === "link" ? "Studio project attached." : "Request approved.");
    } catch (failure) { setError(failure instanceof Error ? failure.message : "The action could not be completed."); }
    finally { setBusy(""); }
  }

  return <main className="admin-requests-page">
    <header className="admin-header"><div><p className="browse-eyebrow">Admin</p><h1>Audiobook requests</h1><p>Approve chapter work, attach a studio project, and review its export before publication.</p></div><AdminNav active="requests" /><AccountNav /></header>
    {message && <p role="status" className="notice">{message}</p>}
    {error && <p role="alert" className="notice error">{error}</p>}
    {loading ? <p role="status">Loading requests…</p> : work.length === 0 ? <section className="empty-requests"><h2>No requests yet</h2><p>Reader requests will appear here.</p></section> :
      <section className="admin-request-list">{work.map(item => {
        const project = selectedProjects[item.id] ?? item.link?.project_id ?? "";
        const reviewMatchesCandidate = !!item.review && !!item.candidate && item.review.revision === item.candidate.revision && item.review.export_id === item.candidate.export_id;
        return <article key={item.id} className="admin-request-card">
          <div className="admin-request-info"><div className="admin-request-heading"><div><p className="request-manga">{item.title}</p><h2>Chapter {item.chapter}</h2></div><span className={`request-status status-${item.status}`}>{item.status}</span></div>
            <p>{item.requests.length} {item.requests.length === 1 ? "reader request" : "reader requests"}</p>
            <div className="request-notes"><strong>Readers and notes</strong><ul>{item.requests.map(request => <li key={request.id}><strong>{request.requester_name || "Name unavailable"}</strong><p>{request.notes || "No note provided."}</p></li>)}</ul></div>
            {item.status === "pending" && <RequestAction action="approve" label="Approve request" disabled={!!busy || !authorizationReady} onClick={() => void action(item, "approve")} />}
            {item.status === "approved" && !item.link && <Link className="button" href={`/?work=${encodeURIComponent(item.id)}&create=1`}>Prepare new studio project</Link>}
            {item.status !== "pending" && <>
              <label>Studio project <select value={project} disabled={!!busy} onChange={event => setSelectedProjects(current => ({ ...current, [item.id]: event.target.value }))}><option value="">Select a saved project</option>{projects.map(saved => <option key={saved.id} value={saved.id}>{saved.name} · {saved.id.slice(0, 6)}</option>)}</select></label>
              <div className="admin-actions"><button type="button" className="button" disabled={!!busy || !project || project === item.link?.project_id} onClick={() => void action(item, "link", { project_id: project })}>{item.link ? "Replace project link" : "Attach project"}</button>
                {item.link && <Link className="button" href={`/?project=${encodeURIComponent(item.link.project_id)}&work=${encodeURIComponent(item.id)}`}>Open linked studio project</Link>}</div>
              <p className="control-note">Upload authorized images in the studio. Replacing a project link invalidates earlier reviews; published audio remains available.</p>
              {item.link && <><RequestAction action="prepare" label="Prepare export for audition" disabled={!!busy || !authorizationReady} onClick={() => void action(item, "prepare")} />
                {item.candidate && <div className="request-notes"><strong>Latest audition candidate</strong><audio controls preload="none" src={`/api/shared/candidate?id=${encodeURIComponent(item.candidate.id)}`} /><RequestAction action="review" label="Record audio review" disabled={!!busy || !authorizationReady} onClick={() => void action(item, "review", { candidate_id: item.candidate!.id, revision: item.candidate!.revision })} /><p className="control-note">Record your decision after reviewing this exact export.</p></div>}
                {item.review && <div className="request-notes"><strong>Reviewed export</strong><audio controls preload="none" src={`/api/shared/candidate?id=${encodeURIComponent(item.review.candidate_id)}`} /><RequestAction action="publish" label="Publish reviewed audio" disabled={!!busy || !authorizationReady || !reviewMatchesCandidate} onClick={() => void action(item, "publish", { review_id: item.review!.id, revision: item.review!.revision, expected_publication: item.publication_id })} />{!reviewMatchesCandidate && <p className="control-note">The latest candidate differs from this review. Record a review for the current export before publishing.</p>}</div>}
              </>}
            </>}
          </div>
        </article>;
      })}</section>}
  </main>;
}
