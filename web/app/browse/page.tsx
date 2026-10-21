"use client";
import Link from "next/link";
import { useRef, useState } from "react";
import { mangas } from "../data/manga";
import { LibraryHeader, MangaCover } from "../../components/library-ui";
const genres = ["All genres", ...new Set(mangas.flatMap(manga => manga.genres))];
export default function BrowsePage() {
  const [query, setQuery] = useState("");
  const searchInput = useRef<HTMLInputElement>(null);
  const [genre, setGenre] = useState("All genres");
  const [audioOnly, setAudioOnly] = useState(false);
  const visible = mangas.filter(manga =>
    `${manga.title} ${manga.description} ${manga.genres.join(" ")}`.toLowerCase().includes(query.trim().toLowerCase()) &&
    (genre === "All genres" || manga.genres.includes(genre)) &&
    (!audioOnly || manga.chapters.some(chapter => chapter.audioStatus === "ready")));
  function reset() { setQuery(""); setGenre("All genres"); setAudioOnly(false); }
  return <div className="library-shell"><LibraryHeader />
    <main className="browse-page library-page">
      <section className="library-intro">
        <div><p className="eyebrow">THE MANGA LIBRARY</p><h1>Your next world<br />is a page away<span className="brand-dot">.</span></h1><p>Discover a story. Follow every panel.<br />Experience manga through reading and sound.</p></div>
        <aside className="library-note"><span className="note-symbol" aria-hidden="true">♪</span><h2>Stories for every reader.</h2><p>Look for audiobook-ready chapters, or request an audio version of the stories you love.</p><Link href="/request">Request an audiobook <span aria-hidden="true">↗</span></Link></aside>
      </section>
      <section aria-labelledby="collection-title">
        <div className="collection-heading"><div><p className="eyebrow">FIND YOUR NEXT READ</p><h2 id="collection-title">Explore the collection</h2></div>
          <div className="library-search" role="search">
            <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg>
            <label className="visually-hidden" htmlFor="manga-search">Search manga</label>
            <input ref={searchInput} id="manga-search" type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search manga or genres" />
            {query && <button type="button" className="library-search-clear" aria-label="Clear search" onClick={() => { setQuery(""); searchInput.current?.focus(); }}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="m7 7 10 10M17 7 7 17" /></svg></button>}
          </div>
        </div>
        <div className="library-filters"><div className="genre-filters" aria-label="Filter by genre">{genres.map(item => <button key={item} type="button" aria-pressed={genre === item} onClick={() => setGenre(item)}>{item}</button>)}</div>
          <label className="library-audio-filter"><input type="checkbox" checked={audioOnly} onChange={event => setAudioOnly(event.target.checked)} /> Audiobook ready</label></div>
        <p className="library-results" role="status">{visible.length} {visible.length === 1 ? "story" : "stories"}{audioOnly ? " with audio chapters" : " to explore"}</p>
        <div className="manga-grid">{visible.map(manga => {
          const audio = manga.chapters.some(chapter => chapter.audioStatus === "ready");
          return <Link href={`/manga/${manga.id}`} key={manga.id} className="manga-card">
            <MangaCover id={manga.id} title={manga.title} />
            <div className="manga-card-content"><div className="card-meta"><span className="manga-status">{manga.status}</span><span>{manga.chapters.length} chapters</span></div>
              <h2>{manga.title}</h2><p className="manga-description">{manga.description}</p>
              <div className="genre-list">{manga.genres.map(item => <span key={item}>{item}</span>)}</div>
              <div className="card-bottom"><span className={audio ? "audio-ready" : "library-muted"}>{audio ? "♪ Audiobook available" : "Available to read"}</span><span aria-hidden="true">↗</span></div>
            </div></Link>;
        })}</div>
        {!visible.length && <div className="library-empty"><h3>No stories found</h3><p>Try another title or broaden your filters.</p><button type="button" className="button" onClick={reset}>Clear search and filters</button></div>}
      </section>
      <footer className="library-footer"><span>KoeTTS · A different way to experience manga</span><span>Read. Listen. Imagine.</span></footer>
    </main></div>;
}
