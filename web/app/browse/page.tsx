"use client";

import Link from "next/link";
import { useState } from "react";
import { mangas } from "../data/manga";
import { CatalogHeader } from "../../components/catalog-header";

const sortOptions = ["Featured", "A–Z", "Chapters", "Audio available"] as const;
type Sort = typeof sortOptions[number];

export default function BrowsePage() {
  const [query, setQuery] = useState("");
  const [genre, setGenre] = useState("All genres");
  const [sort, setSort] = useState<Sort>("Featured");
  const genres = Array.from(new Set(mangas.flatMap(manga => manga.genres))).sort();
  const visible = mangas.filter(manga => (genre === "All genres" || manga.genres.includes(genre)) && `${manga.title} ${manga.description} ${manga.genres.join(" ")}`.toLowerCase().includes(query.toLowerCase())).sort((a, b) => sort === "A–Z" ? a.title.localeCompare(b.title) : sort === "Chapters" ? b.chapters.length - a.chapters.length : sort === "Audio available" ? b.chapters.filter(ch => ch.audioStatus === "ready").length - a.chapters.filter(ch => ch.audioStatus === "ready").length : 0);

  return <div className="catalog-shell"><CatalogHeader /><main className="catalog-page">
    <section className="catalog-hero"><div><p className="eyebrow">A NEW WAY TO EXPERIENCE MANGA</p><h1>Your next story,<br /><span>in words and sound.</span></h1><p>Find a world to get lost in. Read at your own pace,<br className="desktop-break" /> or experience the story through accessible audio.</p><a href="#library" className="button primary">Explore the library <span aria-hidden="true">↓</span></a></div><div className="hero-note"><span className="hero-symbol" aria-hidden="true">▤ <span>♫</span></span><p>Every story deserves<br />to be heard.</p><span className="eyebrow">READING, MADE MORE ACCESSIBLE</span></div></section>
    <section id="library" className="catalog-library" aria-labelledby="library-heading"><div className="catalog-section-heading"><div><p className="eyebrow">THE COLLECTION</p><h2 id="library-heading">Discover manga<span className="catalog-count">{mangas.length}</span></h2></div><p>A little curiosity. A whole new world.</p></div>
    <div className="catalog-filters"><label className="catalog-search"><span aria-hidden="true">⌕</span><span className="visually-hidden">Search manga</span><input type="search" placeholder="Search titles, stories, genres…" value={query} onChange={event => setQuery(event.target.value)} /></label><label><span className="visually-hidden">Filter by genre</span><select value={genre} onChange={event => setGenre(event.target.value)}><option>All genres</option>{genres.map(item => <option key={item}>{item}</option>)}</select></label></div>
    <div className="catalog-sort" role="group" aria-label="Sort manga">{sortOptions.map(option => <button key={option} aria-pressed={sort === option} onClick={() => setSort(option)}>{option}</button>)}</div>
    <p className="catalog-results" role="status">Showing {visible.length} {visible.length === 1 ? "title" : "titles"}</p>
    <div className="catalog-grid">{visible.map(manga => { const latest = manga.chapters[manga.chapters.length - 1]; const ready = manga.chapters.filter(chapter => chapter.audioStatus === "ready").length; return <article className="catalog-manga" key={manga.id}>
      <Link href={`/manga/${manga.id}`} className={`catalog-cover cover-${manga.id}`} aria-label={`View ${manga.title}`}><span className="cover-edition">KoeTTS / {manga.genres[0]}</span><span className="cover-orbit" aria-hidden="true" /><strong>{manga.title}</strong><span className="cover-bottom">{manga.status} <span aria-hidden="true">↗</span></span></Link>
      <div className="catalog-manga-copy"><p className="catalog-genres">{manga.genres.join(" · ")}</p><h3><Link href={`/manga/${manga.id}`}>{manga.title}</Link></h3><p className="catalog-synopsis">{manga.description}</p><dl><div><dt>Status</dt><dd><span className={`catalog-status ${manga.status === "Completed" ? "complete" : ""}`} />{manga.status}</dd></div><div><dt>Chapters</dt><dd>{manga.chapters.length}</dd></div><div><dt>Audio</dt><dd>{ready ? `${ready} chapter ready` : "Not yet available"}</dd></div></dl><Link className="catalog-chapter" href={`/read/${manga.id}/${latest.id}`}><span aria-hidden="true">⊕</span> Ch. {latest.number} — {latest.title}</Link></div>
    </article>; })}</div>
    {visible.length === 0 && <div className="catalog-empty"><h3>No stories found</h3><p>Try another title or genre.</p><button className="button" onClick={() => { setQuery(""); setGenre("All genres"); }}>Clear filters</button></div>}
    </section><aside className="catalog-callout"><div><span className="eyebrow">STORIES FOR EVERYONE</span><h2>A different way to enjoy your favorite manga.</h2><p>Help bring a story to life. Request an accessible audiobook version.</p></div><Link className="button" href="/request">Request audio <span aria-hidden="true">↗</span></Link></aside>
    <footer className="catalog-footer"><span>KoeTTS · Read. Listen. Imagine.</span><span>Made for the way you experience stories.</span></footer>
  </main></div>;
}
