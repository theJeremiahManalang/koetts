"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { RequireSignIn } from "../identity/require-sign-in";
import { PublishedAudioPlayer } from "./published-audio-player";
import { useCatalog } from "./use-catalog";

export default function ReaderPage() {
  return <RequireSignIn><PublishedReader /></RequireSignIn>;
}

function PublishedReader() {
  const params = useParams();
  const { chapters, loading, error } = useCatalog();
  const [showAccessibility, setShowAccessibility] = useState(false);
  const [highContrast, setHighContrast] = useState(false);
  const [largeControls, setLargeControls] = useState(false);
  const chapter = chapters.find(item => item.manga_id === params.mangaId && item.work_id === params.chapterId);
  if (loading) return <main className="loading-screen"><p role="status">Loading chapter…</p></main>;
  if (error && !chapter) return <main className="reader-not-found"><p role="alert">{error}</p><Link href="/browse">Return to Browse</Link></main>;
  if (!chapter) return <main className="reader-not-found"><h1>Chapter not found</h1><Link href="/browse">Return to Browse</Link></main>;
  return <main className={["accessible-reader", highContrast ? "reader-high-contrast" : "", largeControls ? "reader-large-controls" : ""].join(" ")}>
    <header className="accessible-reader-header"><Link href={`/manga/${chapter.manga_id}`} className="reader-back">← {chapter.title}</Link><div className="reader-chapter-title"><strong>Chapter {chapter.chapter}</strong><span>Published audiobook</span></div><button type="button" className="accessibility-button" aria-expanded={showAccessibility} aria-controls="reader-accessibility" onClick={() => setShowAccessibility(current => !current)}>Accessibility</button></header>
    {showAccessibility && <section id="reader-accessibility" className="accessibility-panel" aria-label="Reader accessibility settings"><div><strong>Reader accessibility</strong><p>Adjust contrast and control size.</p></div><div className="accessibility-options"><label><input type="checkbox" checked={highContrast} onChange={event => setHighContrast(event.target.checked)} /> High contrast</label><label><input type="checkbox" checked={largeControls} onChange={event => setLargeControls(event.target.checked)} /> Larger controls</label></div></section>}
    <section className="reader-stage" aria-label="Chapter audio"><div className="reader-audio-panel" tabIndex={0}>
      <p className="eyebrow">NOW LISTENING</p><h1>{chapter.title}</h1><h2>Chapter {chapter.chapter}</h2>
      {error && <p role="alert">{error}</p>}
      <PublishedAudioPlayer key={chapter.work_id} workId={chapter.work_id} />
      <p>Manga pages are not available here yet.</p>
    </div></section>
    <footer className="reader-bottom-bar"><Link href={`/manga/${chapter.manga_id}`}>← All published chapters</Link><Link href={`/request?manga=${encodeURIComponent(chapter.title)}`} className="reader-audio-request">Request another chapter</Link></footer>
  </main>;
}
