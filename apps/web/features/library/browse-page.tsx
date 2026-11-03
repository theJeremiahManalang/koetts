"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AccountNav } from "../identity/account-nav";
import { useAuth } from "../identity/auth-provider";
import { manga, browseShelves, type DemoManga, type DemoChapter } from "../temp-data/manga";
import "./browse.css";
import { RequestPreviewModal } from "./request-preview-modal";
import { MangaShelf } from "./manga-shelf";

function Cover({ title }: { title: string }) {
  return <div className="browse-cover" aria-hidden="true"><span>KOETTS · AUDIO EDITION</span><svg viewBox="0 0 48 48" fill="none"><path d="M10 27v-5a14 14 0 0 1 28 0v5M10 25H7v13h8V25h-5Zm28 0h3v13h-8V25h5Z" stroke="currentColor" strokeWidth="2" /></svg><strong>{title}</strong><span>A STORY WORTH HEARING</span></div>;
}

export default function BrowsePage() {
  const { user, loading } = useAuth();
  const [requestOpen, setRequestOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [genre, setGenre] = useState("All stories");
  const [selected, setSelected] = useState<DemoManga | null>(null);
  const [chapter, setChapter] = useState<{ manga: DemoManga; chapter: DemoChapter } | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const featured = manga[0];
  const genres = ["All stories", ...new Set(manga.flatMap(item => item.genres))];
  const visible = manga.filter(item => (genre === "All stories" || item.genres.includes(genre)) &&
    [item.title, item.author, ...item.genres].join(" ").toLowerCase().includes(query.trim().toLowerCase()));

  function openDetails(item: DemoManga, button: HTMLButtonElement) {
    opener.current = button;
    setSelected(item);
  }
  function closeDetails() {
    setSelected(null);
  }
  useEffect(() => {
    if (selected) closeButton.current?.focus();
    else opener.current?.focus();
  }, [selected]);
  useEffect(() => { if (!user) { setSelected(null); setChapter(null); } }, [user]);

  function card(item: DemoManga, rank?: number) {
    return <button type="button" className="browse-card" key={item.id} aria-label={`View ${item.title}`} aria-pressed={selected?.id === item.id} onClick={event => openDetails(item, event.currentTarget)}>
      <div className="browse-card-art">{rank && <span className="browse-rank" aria-label={`Rank ${rank}`}>{rank}</span>}<Cover title={item.title} /><span className="browse-card-arrow" aria-hidden="true">↗</span></div>
      <strong>{item.title}</strong><span>{item.genres.join(" · ")}</span><small>{item.chapters.length} audio {item.chapters.length === 1 ? "chapter" : "chapters"}</small>
    </button>;
  }

  return <div className="browse-preview" onKeyDown={event => { if (event.key === "Escape" && selected && !requestOpen) { event.stopPropagation(); closeDetails(); } }}>
    <RequestPreviewModal key={user?.uid ?? "guest"} open={requestOpen} signedIn={!!user} onDismiss={() => setRequestOpen(false)} />
    <header className="browse-topbar">
      <Link href="/browse" className="browse-brand"><span aria-hidden="true">♫</span><div>KoeTTS<small>MANGA, WITH A VOICE</small></div></Link>
      <nav className="browse-links" aria-label="Library navigation"><Link href="/browse" aria-current="page">Browse</Link><button type="button" onClick={() => setRequestOpen(true)}>Request</button></nav>
      <label className="browse-search"><span aria-hidden="true">⌕</span><span className="visually-hidden">Search manga, authors, or genres</span><input type="search" placeholder="Search manga, authors, or genres" value={query} onChange={event => setQuery(event.target.value)} /></label>
      <AccountNav />
    </header>
    <div className={`browse-workspace${selected && user ? " has-details" : ""}`}>
      <main className="browse-discovery">
        <div className="browse-section-label"><span>YOUR NEXT WORLD AWAITS</span><span className="browse-demo">Demo collection · UI preview</span></div>
        {loading ? <p role="status">Checking your account…</p> : !user ? <section className="browse-empty"><h1>Stories worth listening to.</h1><p>Sign in to explore the manga audiobook collection.</p><Link href="/login" className="browse-primary">Sign in</Link></section> : <>
          <section className="browse-hero" aria-labelledby="featured-title"><div className="browse-hero-cover"><Cover title={featured.title} /></div><div className="browse-hero-copy"><span className="browse-tag">♫ FEATURED AUDIOBOOK</span><p className="browse-overline">LET THE STORY FIND YOU</p><h1 id="featured-title">{featured.title}</h1><p className="browse-hero-meta">{featured.genres.join(" · ")}<span>•</span>{featured.chapters.length} audio chapters</p><p className="browse-hero-description">{featured.synopsis}</p><button type="button" className="browse-primary" onClick={event => openDetails(featured, event.currentTarget)}>Explore manga <span aria-hidden="true">↗</span></button></div><span className="browse-hero-number" aria-hidden="true">01</span></section>
          <div className="browse-filters" aria-label="Filter by genre">{genres.map(item => <button type="button" key={item} aria-pressed={genre === item} onClick={() => setGenre(item)}>{item}</button>)}</div>
          {query.trim() || genre !== "All stories" ? <>
            <p role="status" className="browse-results">{visible.length} {visible.length === 1 ? "story" : "stories"} found</p>
            <MangaShelf id="browse-results" title="Search results" subtitle="FIND YOUR KIND OF STORY">{visible.map(item => card(item))}</MangaShelf>
            {!visible.length && <div className="browse-empty"><h3>No stories found</h3><p>Try a different title, author, or genre.</p><button type="button" className="browse-primary" onClick={() => { setQuery(""); setGenre("All stories"); }}>Reset filters</button></div>}
          </> : <>
            <MangaShelf id="browse-recent" title="Recently added" subtitle="FRESH ON THE SHELF">{browseShelves.recent.map(item => card(item))}</MangaShelf>
            <MangaShelf id="browse-top" title="Top 10 Mangas" subtitle="DEMO CHART · STORIES TO GET LOST IN">{browseShelves.top.map((item, index) => card(item, index + 1))}</MangaShelf>
            <section className="browse-request-banner" aria-labelledby="browse-request-title"><span className="browse-request-icon" aria-hidden="true">♫</span><div><h2 id="browse-request-title">Request a manga</h2><p>Can't find the manga you'd love to hear? Tell us what we should bring to audio next.</p></div><button type="button" className="browse-primary" onClick={() => setRequestOpen(true)}>＋ Request a manga</button></section>
            <MangaShelf id="browse-picks" title="Today's Top Picks for You" subtitle="CURATED DEMO PICKS · FIND A NEW FAVORITE">{browseShelves.picks.map(item => card(item))}</MangaShelf>
          </>}
          <footer className="browse-footer"><span>KoeTTS · A different way to experience manga</span><span>Read. Listen. Imagine.</span></footer>
        </>}
      </main>
      {selected && user && <aside className="browse-details" aria-labelledby="details-title"><div className="browse-details-top"><span>MANGA DETAILS</span><button ref={closeButton} type="button" aria-label="Close manga details" onClick={closeDetails}>×</button></div><div className="browse-details-summary"><Cover title={selected.title} /><div><h2 id="details-title">{selected.title}</h2><p>By {selected.author}</p><div className="browse-genres">{selected.genres.map(item => <span key={item}>{item}</span>)}</div></div></div><button type="button" className="browse-primary browse-listen" disabled>▶ Listen now</button><p className="browse-preview-note">Audio preview unavailable · Demo content</p><h3>Synopsis</h3><p className="browse-synopsis">{selected.synopsis}</p><div className="browse-chapter-heading"><h3>Chapters <span>({selected.chapters.length})</span></h3><span>In story order</span></div><p className="browse-preview-note">Select a chapter to preview its player details.</p><ol className="browse-chapters">{selected.chapters.map(item => <li key={item.id}><button type="button" aria-pressed={chapter?.manga.id === selected.id && chapter.chapter.id === item.id} onClick={() => setChapter({ manga: selected, chapter: item })}><span className="browse-chapter-number">{String(item.number).padStart(2, "0")}</span><span>{item.title}</span><small>{item.duration}</small></button></li>)}</ol></aside>}
    </div>
    <section className="browse-player" aria-label="Audiobook player preview"><div className="browse-player-track">{chapter && user ? <><Cover title={chapter.manga.title} /><div><strong>Ch. {chapter.chapter.number} · {chapter.chapter.title}</strong><span>{chapter.manga.title}</span></div></> : <><span className="browse-player-placeholder" aria-hidden="true">♫</span><div><strong>Your next chapter starts here</strong><span>Select a manga, then choose a chapter</span></div></>}</div><div className="browse-player-controls"><div><button type="button" disabled aria-label="Previous chapter">Ⅰ◀</button><button type="button" disabled className="browse-play" aria-label="Play">▶</button><button type="button" disabled aria-label="Next chapter">▶Ⅰ</button></div><div className="browse-timeline"><span>0:00</span><span className="browse-track-line" /><span>{chapter && user ? chapter.chapter.duration : "0:00"}</span></div></div><div className="browse-player-note"><span>Audio preview unavailable</span><label>Volume <input type="range" disabled aria-label="Volume" defaultValue="70" /></label></div></section>
  </div>;
}
