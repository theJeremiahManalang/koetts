"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { RequireSignIn } from "../identity/require-sign-in";
import { PublishedAudioPlayer } from "./published-audio-player";
import { useCatalog } from "./use-catalog";

export default function ReaderPage() {
  return <RequireSignIn><PublishedReader /></RequireSignIn>;
}

function PublishedReader() {
  const params = useParams();
  const { chapters, loading, error } = useCatalog();
  const chapter = chapters.find(item => item.manga_id === params.mangaId && item.work_id === params.chapterId);
  if (loading) return <main className="loading-screen"><p role="status">Loading chapter…</p></main>;
  if (error) return <main className="reader-not-found"><p role="alert">{error}</p><Link href="/browse">Return to Browse</Link></main>;
  if (!chapter) return <main className="reader-not-found"><h1>Chapter not found</h1><Link href="/browse">Return to Browse</Link></main>;
  return <main className="accessible-reader">
    <header className="accessible-reader-header"><Link href={`/manga/${chapter.manga_id}`} className="reader-back">← {chapter.title}</Link><div className="reader-chapter-title"><strong>Chapter {chapter.chapter}</strong><span>Published audiobook</span></div></header>
    <section className="reader-stage" aria-label="Chapter audio"><div className="reader-audio-panel" tabIndex={0}>
      <p className="eyebrow">NOW LISTENING</p><h1>{chapter.title}</h1><h2>Chapter {chapter.chapter}</h2>
      <PublishedAudioPlayer key={chapter.work_id} workId={chapter.work_id} />
      <p>Manga pages are not available here yet.</p>
    </div></section>
    <footer className="reader-bottom-bar"><Link href={`/manga/${chapter.manga_id}`}>← All published chapters</Link><Link href={`/request?manga=${encodeURIComponent(chapter.title)}`} className="reader-audio-request">Request another chapter</Link></footer>
  </main>;
}
