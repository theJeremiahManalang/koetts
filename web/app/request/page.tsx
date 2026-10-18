"use client";

import { FormEvent, Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { CatalogHeader } from "../../components/catalog-header";
import { mangas } from "../data/manga";

function RequestForm() {
  const searchParams = useSearchParams();
  const initialManga = mangas.find(item => item.title === searchParams.get("manga") || item.id === searchParams.get("manga"));
  const initialChapter = initialManga?.chapters.find(item => `Chapter ${item.number} - ${item.title}` === searchParams.get("chapter") || item.id === searchParams.get("chapter"));
  const [mangaTitle, setMangaTitle] = useState(initialManga?.title || searchParams.get("manga") || "");
  const [chapterNumber, setChapterNumber] = useState(initialChapter ? String(initialChapter.number) : (searchParams.get("chapter") || "").match(/^(?:Chapter\s+|chapter-)?(\d+(?:\.\d+)?)/i)?.[1] || "");
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const manga = mangas.find(item => item.title.toLowerCase() === mangaTitle.trim().toLowerCase());
  const chapter = manga?.chapters.find(item => item.number === Number(chapterNumber));
  const validRequest = Boolean(mangaTitle.trim() && chapterNumber.trim() && Number.isFinite(Number(chapterNumber)) && Number(chapterNumber) >= 0);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!validRequest || saved) return;
    try {
      const stored: unknown = JSON.parse(localStorage.getItem("mangaRequests") || "[]");
      if (!Array.isArray(stored)) throw new Error("Invalid saved requests");
      stored.push({ id: crypto.randomUUID(), mangaTitle: mangaTitle.trim(), chapter: `Chapter ${chapterNumber}${chapter ? ` - ${chapter.title}` : ""}`, notes: notes.trim(), status: "PENDING", createdAt: new Date().toISOString() });
      localStorage.setItem("mangaRequests", JSON.stringify(stored));
      setSaved(true);
      setError("");
    } catch {
      setError("We couldn't save your request in this browser. Please try again or check your browser storage settings.");
    }
  }

  return <section className="audio-request-card" aria-labelledby="request-heading"><div className="audio-request-card-heading"><span className="eyebrow">AUDIOBOOK REQUEST</span><span className="badge">Chapter narration</span></div><h2 id="request-heading">Bring a chapter to life.</h2><p className="audio-request-description">Choose your story and tell us what would help you enjoy it.</p>
    {saved ? <div className="audio-request-success" role="status"><span className="audio-request-check" aria-hidden="true">✓</span><h3>Your request is saved.</h3><p><strong>{mangaTitle.trim()}</strong><br />Chapter {chapterNumber}{chapter ? ` — ${chapter.title}` : ""}</p><span className="badge">Pending</span><p>Saved on this browser. Requests are not sent to a production team yet.</p><div className="audio-request-success-actions"><Link href="/browse" className="button primary">Back to the library →</Link><button type="button" className="button" onClick={() => { setSaved(false); setChapterNumber(""); setNotes(""); }}>Request another chapter</button></div></div> : <form className="audio-request-form" onSubmit={handleSubmit}>
      <label className="field-label" htmlFor="request-manga">Manga <span className="audio-request-required">Required</span></label><input id="request-manga" type="text" required maxLength={200} value={mangaTitle} onChange={event => { setMangaTitle(event.target.value); setError(""); }} placeholder="Enter the manga title" />
      <label className="field-label" htmlFor="request-chapter">Chapter <span className="audio-request-required">Required</span></label><input id="request-chapter" type="number" required min="0" step="any" value={chapterNumber} onChange={event => { setChapterNumber(event.target.value); setError(""); }} placeholder="e.g. 12" aria-describedby="chapter-guidance" /><p id="chapter-guidance" className="audio-request-hint">{chapter?.audioStatus === "ready" ? "This chapter already has audio marked as ready. You can still request a new version." : chapter?.audioStatus === "processing" ? "Audio for this chapter is currently processing." : "Enter the chapter number you would like narrated."}</p>
      {validRequest && <div className="audio-request-selection"><span className="audio-request-selection-icon" aria-hidden="true">▤</span><div><span className="eyebrow">YOUR SELECTION</span><strong>{mangaTitle.trim()}</strong><span>Chapter {chapterNumber}{chapter ? ` — ${chapter.title}` : ""}</span></div>{manga && <Link href={`/manga/${manga.id}`} aria-label={`View ${manga.title}`}>↗</Link>}</div>}
      <label className="field-label" htmlFor="request-notes">Additional notes <span className="audio-request-required">Optional</span></label><textarea id="request-notes" value={notes} maxLength={2000} onChange={event => setNotes(event.target.value)} placeholder="Share pronunciation notes, accessibility needs, or anything else we should know…" rows={4} /><p className="audio-request-hint audio-request-counter">{notes.length} / 2,000 characters</p>
      {error && <p className="notice error" role="alert">{error}</p>}
      <button type="submit" className="button primary audio-request-submit" disabled={!validRequest}>Save audiobook request <span aria-hidden="true">↗</span></button><p className="audio-request-storage">Requests are saved on this browser only.</p>
    </form>}
  </section>;
}

export default function RequestMangaPage() {
  return <div className="catalog-shell"><CatalogHeader /><main className="audio-request-page"><Link href="/browse" className="account-back">← Back to the library</Link><div className="audio-request-layout"><section className="audio-request-intro"><p className="eyebrow">STORIES FOR EVERYONE</p><h1>Every story deserves<br /><span>to be heard.</span></h1><p>Experience manga in a different way.<br />Request an accessible narrated version of a chapter you love.</p><div className="audio-request-steps"><span className="eyebrow">A LITTLE GUIDANCE</span><ol><li><span>01</span><div><h2>Choose a chapter</h2><p>Enter a manga title and chapter number.</p></div></li><li><span>02</span><div><h2>Make it yours</h2><p>Add any notes or accessibility preferences.</p></div></li><li><span>03</span><div><h2>Save your request</h2><p>Keep your selection on this browser for later.</p></div></li></ol></div><p className="audio-request-help">Looking for your next read? <Link href="/browse">Explore the library ↗</Link></p></section><Suspense fallback={<section className="audio-request-card" role="status">Loading request form…</section>}><RequestForm /></Suspense></div><footer className="catalog-footer"><span>KoeTTS · Read. Listen. Imagine.</span><span>Made for the way you experience stories.</span></footer></main></div>;
}
