"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { mangas } from "./fixtures/catalog";
import { LibraryHeader, MangaCover } from "./library-ui";

export default function MangaDetailsPage() {
  const params = useParams();

  const manga = mangas.find(
    (item) => item.id === params.id
  );

  if (!manga) {
    return (
      <main className="not-found">
        <h1>Manga not found</h1>

        <Link href="/browse">
          ← Return to Browse
        </Link>
      </main>
    );
  }

  return (
    <div className="library-shell"><LibraryHeader /><main className="manga-details-page library-page">
      <Link href="/browse" className="back-link">
        ← Back to the collection
      </Link>

      <section className="manga-hero">
        <MangaCover id={manga.id} title={manga.title} />

        <div className="manga-info">
          <p className="manga-status">
            {manga.status}
          </p>

          <p className="eyebrow">THE KOETTS COLLECTION</p><h1>{manga.title}</h1>

          <div className="genre-list">
            {manga.genres.map((genre) => (
              <span key={genre}>{genre}</span>
            ))}
          </div>

          <p className="detail-description">
            {manga.description}
          </p>

          <div className="detail-stats"><span><strong>{manga.chapters.length}</strong> chapters</span><span><strong>{manga.chapters.filter(chapter => chapter.audioStatus === "ready").length}</strong> audiobook ready</span></div>
          <Link
            href={`/read/${manga.id}/${manga.chapters[0].id}`}
            className="primary-action"
          >
            Start reading · Chapter 1 ↗
          </Link>
        </div>
      </section>

      <section className="chapter-section">
        <div className="section-heading">
          <div>
            <p className="browse-eyebrow">
              Chapters
            </p>

            <h2>Choose your next chapter</h2>
          </div>

          <span>
            {manga.chapters.length} chapters
          </span>
        </div>

        <p className="chapter-intro">Read at your own pace, or explore the available audio chapters.</p><div className="chapter-list">
          {manga.chapters.map((chapter) => (
            <article
              className="chapter-row"
              key={chapter.id}
            >
              <span className="chapter-index" aria-hidden="true">{String(chapter.number).padStart(2, "0")}</span><div className="chapter-row-info">
                <p className="chapter-number">
                  Chapter {chapter.number}
                </p>

                <h3>{chapter.title}</h3>

                {chapter.audioStatus === "none" && <span className="library-muted">Audio available on request</span>}
                {chapter.audioStatus === "ready" && (
                  <span className="audio-ready">
                    ✓ Audiobook Ready
                  </span>
                )}

                {chapter.audioStatus ===
                  "processing" && (
                  <span className="audio-processing">
                    Processing Audiobook
                  </span>
                )}
              </div>

              <div className="chapter-actions">
                <Link
                  href={`/read/${manga.id}/${chapter.id}`}
                  className="read-button"
                  aria-label={`Read chapter ${chapter.number}: ${chapter.title}`}
                >
                  Read
                </Link>

                {chapter.audioStatus ===
                "none" ? (
                    <Link
                    href={`/request?mangaId=${encodeURIComponent(
                      manga.id
                    )}&chapterId=${encodeURIComponent(
                      chapter.id
                    )}&manga=${encodeURIComponent(
                      manga.title
                    )}&chapter=${encodeURIComponent(
                      `Chapter ${chapter.number} - ${chapter.title}`
                    )}`}
                    className="request-audio-button"
                    aria-label={`Request audiobook for chapter ${chapter.number}: ${chapter.title}`}
                  >
                    Request Audiobook
                  </Link>
                ) : chapter.audioStatus ===
                  "ready" ? (
                  <button
                    type="button"
                    className="listen-button"
                    aria-label={`Listen to chapter ${chapter.number}: ${chapter.title}`}
                  >
                    ▶ Listen
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled
                    className="processing-button"
                  >
                    Processing
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>
    </main></div>
  );
}
