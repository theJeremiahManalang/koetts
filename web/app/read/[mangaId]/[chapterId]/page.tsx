"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { mangas } from "../../../data/manga";

export default function ReaderPage() {
  const params = useParams();

  const manga = mangas.find(
    (item) =>
      item.id === params.mangaId
  );

  const chapter = manga?.chapters.find(
    (item) =>
      item.id === params.chapterId
  );

  if (!manga || !chapter) {
    return <main>Chapter not found.</main>;
  }

  return (
    <main className="reader-page">
      <header className="reader-header">
        <Link
          href={`/manga/${manga.id}`}
        >
          ← {manga.title}
        </Link>

        <div>
          <strong>
            Chapter {chapter.number}
          </strong>

          <span>{chapter.title}</span>
        </div>

        <Link
          href={`/request?manga=${encodeURIComponent(
            manga.title
          )}&chapter=${encodeURIComponent(
            `Chapter ${chapter.number} - ${chapter.title}`
          )}`}
        >
          Request Audiobook
        </Link>
      </header>

      <section className="reader-demo">
        <div className="reader-page-placeholder">
          <span>Page 1</span>

          <p>
            Manga page artwork will be
            displayed here.
          </p>
        </div>

        <div className="reader-page-placeholder">
          <span>Page 2</span>

          <p>
            Manga page artwork will be
            displayed here.
          </p>
        </div>

        <div className="reader-page-placeholder">
          <span>Page 3</span>

          <p>
            Manga page artwork will be
            displayed here.
          </p>
        </div>
      </section>
    </main>
  );
}