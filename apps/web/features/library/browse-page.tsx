"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { LibraryHeader, MangaCover } from "./library-ui";
import { groupCatalog, useCatalog } from "./use-catalog";

export default function BrowsePage() {
  const { chapters, loading, error, signedIn } = useCatalog();
  const [query, setQuery] = useState("");
  const searchInput = useRef<HTMLInputElement>(null);
  const visible = groupCatalog(chapters).filter(manga => manga.title.toLowerCase().includes(query.trim().toLowerCase()));
  return <div className="library-shell"><LibraryHeader />
    <main className="browse-page library-page">
      <section className="library-intro">
        <div><p className="eyebrow">THE MANGA LIBRARY</p><h1>Your next world<br />is a page away<span className="brand-dot">.</span></h1><p>Discover published chapter audio.<br />Listen at your own pace.</p></div>
        <aside className="library-note"><span className="note-symbol" aria-hidden="true">♪</span><h2>Stories for every reader.</h2><p>Request audio for a chapter you would like to hear.</p><Link href="/request">Request an audiobook <span aria-hidden="true">↗</span></Link></aside>
      </section>
      <section aria-labelledby="collection-title">
        <div className="collection-heading"><div><p className="eyebrow">FIND YOUR NEXT LISTEN</p><h2 id="collection-title">Explore the collection</h2></div>
          <div className="library-search" role="search"><label className="visually-hidden" htmlFor="manga-search">Search manga</label><input ref={searchInput} id="manga-search" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search manga" />{query && <button type="button" className="library-search-clear" aria-label="Clear search" onClick={() => { setQuery(""); searchInput.current?.focus(); }}>×</button>}</div>
        </div>
        {!signedIn && !loading ? <div className="library-empty"><h3>Sign in to explore</h3><p>Published audio is available to signed-in readers.</p><Link href="/login" className="button">Sign in</Link></div> : loading ? <p role="status">Loading the published catalog…</p> : error ? <p role="alert" className="notice error">{error}</p> : <>
          <p className="library-results" role="status">{visible.length} {visible.length === 1 ? "story" : "stories"} with published audio</p>
          <div className="manga-grid">{visible.map(manga => <Link href={`/manga/${manga.id}`} key={manga.id} className="manga-card"><MangaCover id={manga.id} title={manga.title} /><div className="manga-card-content"><div className="card-meta"><span className="manga-status">Published audio</span><span>{manga.chapters.length} {manga.chapters.length === 1 ? "chapter" : "chapters"}</span></div><h2>{manga.title}</h2><div className="card-bottom"><span className="audio-ready">♪ Audiobook available</span><span aria-hidden="true">↗</span></div></div></Link>)}</div>
          {!visible.length && <div className="library-empty"><h3>{query ? "No stories found" : "No published audio yet"}</h3><p>{query ? "Try another title." : "Request a chapter to get started."}</p><Link href="/request" className="button">Request an audiobook</Link></div>}
        </>}
      </section>
      <footer className="library-footer"><span>KoeTTS · A different way to experience manga</span><span>Read. Listen. Imagine.</span></footer>
    </main></div>;
}
