import Link from "next/link";
import { mangas } from "../data/manga";

export default function BrowsePage() {
  return (
    <main className="browse-page">
      <header className="browse-header">
        <div>
          <p className="browse-eyebrow">Accessible Manga</p>
          <h1>Discover Manga</h1>
          <p>
            Read manga normally or request an accessible audiobook version.
          </p>
        </div>

        <Link href="/requests" className="header-link">
          My Requests
        </Link>
      </header>

      <section className="manga-grid">
        {mangas.map((manga) => (
          <Link
            href={`/manga/${manga.id}`}
            key={manga.id}
            className="manga-card"
          >
            <div className="manga-cover">
              <span>{manga.title.charAt(0)}</span>
            </div>

            <div className="manga-card-content">
              <p className="manga-status">{manga.status}</p>

              <h2>{manga.title}</h2>

              <p className="manga-description">
                {manga.description}
              </p>

              <div className="genre-list">
                {manga.genres.map((genre) => (
                  <span key={genre}>{genre}</span>
                ))}
              </div>

              <p className="chapter-count">
                {manga.chapters.length} chapters
              </p>
            </div>
          </Link>
        ))}
      </section>
    </main>
  );
}