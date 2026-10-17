"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { mangas } from "../../data/manga";

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
    <main className="manga-details-page">
      <Link href="/browse" className="back-link">
        ← Browse
      </Link>

      <section className="manga-hero">
        <div className="detail-cover">
          {manga.title.charAt(0)}
        </div>

        <div className="manga-info">
          <p className="manga-status">
            {manga.status}
          </p>

          <h1>{manga.title}</h1>

          <div className="genre-list">
            {manga.genres.map((genre) => (
              <span key={genre}>{genre}</span>
            ))}
          </div>

          <p className="detail-description">
            {manga.description}
          </p>

          <Link
            href={`/read/${manga.id}/${manga.chapters[0].id}`}
            className="primary-action"
          >
            Start Reading
          </Link>
        </div>
      </section>

      <section className="chapter-section">
        <div className="section-heading">
          <div>
            <p className="browse-eyebrow">
              Chapters
            </p>

            <h2>Chapter List</h2>
          </div>

          <span>
            {manga.chapters.length} chapters
          </span>
        </div>

        <div className="chapter-list">
          {manga.chapters.map((chapter) => (
            <article
              className="chapter-row"
              key={chapter.id}
            >
              <div>
                <p className="chapter-number">
                  Chapter {chapter.number}
                </p>

                <h3>{chapter.title}</h3>

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
                  >
                    Request Audiobook
                  </Link>
                ) : chapter.audioStatus ===
                  "ready" ? (
                  <button
                    type="button"
                    className="listen-button"
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
    </main>
  );
}