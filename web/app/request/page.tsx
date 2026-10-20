"use client";

import { FormEvent, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { LibraryHeader } from "../../components/library-ui";
import { RequireSignIn } from "../../components/require-sign-in";

export default function RequestMangaPage() {
  return <RequireSignIn><RequestForm /></RequireSignIn>;
}

function RequestForm() {
  const searchParams = useSearchParams();
  const [selectedManga, setSelectedManga] = useState(() => searchParams.get("manga") || "");
  const [selectedChapter, setSelectedChapter] = useState(() =>
    (searchParams.get("chapter") || "").match(/^(?:Chapter\s+)?([0-9]{1,4})(?=\s|$)/i)?.[1] || "");
  const [notes, setNotes] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const valid = !!selectedManga.trim() && /^[0-9]{1,4}$/.test(selectedChapter);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!valid) return;
    setError("");
    setMessage("");
    try {
      const existing: unknown = JSON.parse(localStorage.getItem("mangaRequests") || "[]");
      if (!Array.isArray(existing)) throw new Error();
      const newRequest = { id: crypto.randomUUID(), mangaTitle: selectedManga.trim(), chapter: selectedChapter, notes, status: "PENDING", createdAt: new Date().toISOString() };
      localStorage.setItem("mangaRequests", JSON.stringify([...existing, newRequest]));
      setMessage(`Your request for ${selectedManga.trim()}, chapter ${selectedChapter}, has been saved.`);
      setNotes("");
    } catch { setError("Your request could not be saved. Check that browser storage is available and try again."); }
  }

  return <div className="library-shell"><LibraryHeader />
    <main className="request-page request-compose">
      <div className="request-compose-heading"><p className="eyebrow">A STORY WORTH HEARING</p><h1>Give your next read a voice<span className="brand-dot">.</span></h1><p>Tell us which manga chapter you’d love to experience as an audiobook.</p></div>
      <div className="request-compose-grid">
        <section className="request-card" aria-labelledby="request-form-title">
          <div className="request-card-heading"><span className="request-form-icon" aria-hidden="true">♪</span><div><h2 id="request-form-title">Request an audiobook</h2><p>Start with a manga and one chapter.</p></div></div>
          <form onSubmit={handleSubmit} className="request-form">
            <div className="request-fields">
              <label htmlFor="request-manga">Manga title <span className="request-required">Required</span>
                <input id="request-manga" type="text" required value={selectedManga} onChange={event => { setSelectedManga(event.target.value); setMessage(""); }} placeholder="e.g. Echoes of Tomorrow" autoComplete="off" />
              </label>
              <label htmlFor="request-chapter">Chapter <span className="request-required">Required</span>
                <input id="request-chapter" type="text" inputMode="numeric" pattern="[0-9]{1,4}" maxLength={4} required value={selectedChapter} onChange={event => { setSelectedChapter(event.target.value.replace(/[^0-9]/g, "").slice(0, 4)); setMessage(""); }} placeholder="e.g. 12" aria-describedby="chapter-hint" />
                <small id="chapter-hint">Up to 4 digits.</small>
              </label>
            </div>
            <label htmlFor="request-notes"><span>Additional notes <span className="request-required">Optional</span></span>
              <textarea id="request-notes" value={notes} onChange={event => setNotes(event.target.value)} placeholder="Anything we should know about this chapter or your narration preferences?" rows={4} />
            </label>
            <div className="request-submit-area"><p>One chapter per request. You can track it in My requests.</p><button type="submit" className="submit-request" disabled={!valid}>Submit request <span aria-hidden="true">↗</span></button></div>
            {error && <p className="notice error" role="alert">{error}</p>}
            {message && <div className="request-saved" role="status"><span aria-hidden="true">✓</span><div><strong>Request saved</strong><p>{message}</p><Link href="/requests">View my requests →</Link></div></div>}
          </form>
        </section>
        <aside className="request-guide" aria-labelledby="request-guide-title">
          <p className="eyebrow">FROM PANELS TO SOUND</p><h2 id="request-guide-title">Your story.<br /> A new way to listen.</h2>
          <ol><li><span>01</span><div><h3>Choose your chapter</h3><p>Enter the manga title and chapter number you have in mind.</p></div></li><li><span>02</span><div><h3>Make your request</h3><p>Add any helpful notes, then save your request.</p></div></li><li><span>03</span><div><h3>Keep track</h3><p>Find your saved requests and their status in My requests.</p></div></li></ol>
          <div className="request-guide-footer"><p>Looking for your next story?</p><Link href="/browse">Explore the collection <span aria-hidden="true">↗</span></Link></div>
        </aside>
      </div>
      <p className="request-storage-note">Requests are currently saved in this browser.</p>
    </main>
  </div>;
}
