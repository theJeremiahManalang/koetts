"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { RequireSignIn } from "../identity/require-sign-in";
import { LibraryHeader, MangaCover } from "./library-ui";
import { groupCatalog, useCatalog } from "./use-catalog";

export default function MangaDetailsPage() {
  return <RequireSignIn><MangaDetails /></RequireSignIn>;
}

function MangaDetails() {
  const params = useParams();
  const { chapters, loading, error } = useCatalog();
  const manga = groupCatalog(chapters).find(item => item.id === params.id);
  if (loading) return <main className="loading-screen"><p role="status">Loading manga…</p></main>;
  if (error) return <main className="not-found"><p role="alert">{error}</p><Link href="/browse">Return to Browse</Link></main>;
  if (!manga) return <main className="not-found"><h1>Manga not found</h1><Link href="/browse">← Return to Browse</Link></main>;
  return <div className="library-shell"><LibraryHeader /><main className="manga-details-page library-page">
    <Link href="/browse" className="back-link">← Back to the collection</Link>
    <section className="manga-hero"><MangaCover id={manga.id} title={manga.title} /><div className="manga-info">
      <p className="eyebrow">THE KOETTS COLLECTION</p><h1>{manga.title}</h1>
      <p className="detail-description">Published chapter audio is ready to listen to.</p>
      <div className="detail-stats"><span><strong>{manga.chapters.length}</strong> published {manga.chapters.length === 1 ? "chapter" : "chapters"}</span></div>
      <Link href={`/read/${manga.id}/${manga.chapters[0].work_id}`} className="primary-action">Listen to chapter {manga.chapters[0].chapter} ↗</Link>
    </div></section>
    <section className="chapter-section"><div className="section-heading"><div><p className="browse-eyebrow">Chapters</p><h2>Choose a chapter</h2></div><span>{manga.chapters.length} published</span></div>
      <div className="chapter-list">{manga.chapters.map(chapter => <article className="chapter-row" key={chapter.work_id}>
        <span className="chapter-index" aria-hidden="true">{String(chapter.chapter).padStart(2, "0")}</span>
        <div className="chapter-row-info"><h3>Chapter {chapter.chapter}</h3><span className="audio-ready">✓ Audiobook available</span></div>
        <div className="chapter-actions"><Link href={`/read/${manga.id}/${chapter.work_id}`} className="listen-button" aria-label={`Listen to chapter ${chapter.chapter}`}>▶ Listen</Link></div>
      </article>)}</div>
      <p className="chapter-intro">Manga pages are not available here yet.</p>
      <Link href={`/request?manga=${encodeURIComponent(manga.title)}`} className="button">Request another chapter</Link>
    </section>
  </main></div>;
}
