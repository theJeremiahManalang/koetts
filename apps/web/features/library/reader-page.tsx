"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { mangas } from "./fixtures/catalog";

export default function ReaderPage() {
  const params = useParams();

  const manga = mangas.find(
    (item) => item.id === params.mangaId
  );

  const chapter = manga?.chapters.find(
    (item) => item.id === params.chapterId
  );

  const [pageIndex, setPageIndex] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [highContrast, setHighContrast] = useState(false);
  const [largeControls, setLargeControls] = useState(false);
  const [showAccessibility, setShowAccessibility] =
    useState(false);

  // Placeholder pages for now.
  // Later these become actual manga image URLs.
  const pages = [
    {
      id: 1,
      label: "Page 1",
      description:
        "Manga artwork for page 1 will appear here.",
    },
    {
      id: 2,
      label: "Page 2",
      description:
        "Manga artwork for page 2 will appear here.",
    },
    {
      id: 3,
      label: "Page 3",
      description:
        "Manga artwork for page 3 will appear here.",
    },
  ];

  function previousPage() {
    setPageIndex((current) =>
      Math.max(0, current - 1)
    );
  }

  function nextPage() {
    setPageIndex((current) =>
      Math.min(pages.length - 1, current + 1)
    );
  }

  function zoomIn() {
    setZoom((current) =>
      Math.min(180, current + 10)
    );
  }

  function zoomOut() {
    setZoom((current) =>
      Math.max(70, current - 10)
    );
  }

  function resetZoom() {
    setZoom(100);
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "ArrowLeft") {
        previousPage();
      }

      if (event.key === "ArrowRight") {
        nextPage();
      }

      if (
        event.key === "+" ||
        event.key === "="
      ) {
        zoomIn();
      }

      if (event.key === "-") {
        zoomOut();
      }
    }

    window.addEventListener(
      "keydown",
      handleKeyDown
    );

    return () =>
      window.removeEventListener(
        "keydown",
        handleKeyDown
      );
  }, []);

  if (!manga || !chapter) {
    return (
      <main className="reader-not-found">
        <h1>Chapter not found</h1>

        <Link href="/browse">
          Return to Browse
        </Link>
      </main>
    );
  }

  const currentPage = pages[pageIndex];

  return (
    <main
      className={[
        "accessible-reader",
        highContrast
          ? "reader-high-contrast"
          : "",
        largeControls
          ? "reader-large-controls"
          : "",
      ].join(" ")}
    >
      <header className="accessible-reader-header">
        <Link
          href={`/manga/${manga.id}`}
          className="reader-back"
        >
          ← {manga.title}
        </Link>

        <div className="reader-chapter-title">
          <strong>
            Chapter {chapter.number}
          </strong>

          <span>{chapter.title}</span>
        </div>

        <button
          type="button"
          className="accessibility-button"
          onClick={() =>
            setShowAccessibility(
              (current) => !current
            )
          }
          aria-expanded={showAccessibility}
        >
          Accessibility
        </button>
      </header>

      {showAccessibility && (
        <section
          className="accessibility-panel"
          aria-label="Accessibility settings"
        >
          <div>
            <strong>Reader Accessibility</strong>

            <p>
              Adjust the reading experience
              for improved visibility and
              navigation.
            </p>
          </div>

          <div className="accessibility-options">
            <label>
              <input
                type="checkbox"
                checked={highContrast}
                onChange={(event) =>
                  setHighContrast(
                    event.target.checked
                  )
                }
              />

              High contrast
            </label>

            <label>
              <input
                type="checkbox"
                checked={largeControls}
                onChange={(event) =>
                  setLargeControls(
                    event.target.checked
                  )
                }
              />

              Larger controls
            </label>
          </div>
        </section>
      )}

      <section className="reader-toolbar">
        <div className="reader-navigation-group">
          <button
            type="button"
            onClick={previousPage}
            disabled={pageIndex === 0}
            aria-label="Previous manga page"
          >
            ← Previous
          </button>

          <span className="page-counter">
            Page {pageIndex + 1} of{" "}
            {pages.length}
          </span>

          <button
            type="button"
            onClick={nextPage}
            disabled={
              pageIndex ===
              pages.length - 1
            }
            aria-label="Next manga page"
          >
            Next →
          </button>
        </div>

        <div
          className="reader-zoom-group"
          aria-label="Zoom controls"
        >
          <button
            type="button"
            onClick={zoomOut}
            disabled={zoom <= 70}
            aria-label="Zoom out"
          >
            −
          </button>

          <button
            type="button"
            onClick={resetZoom}
            className="zoom-value"
            aria-label="Reset zoom to 100 percent"
          >
            {zoom}%
          </button>

          <button
            type="button"
            onClick={zoomIn}
            disabled={zoom >= 180}
            aria-label="Zoom in"
          >
            +
          </button>
        </div>
      </section>

      <section className="reader-stage">
        <div
          className="manga-page-demo"
          style={{
            width: `${zoom}%`,
          }}
          tabIndex={0}
          aria-label={`${currentPage.label}. ${currentPage.description}`}
        >
          <span className="demo-page-number">
            {currentPage.label}
          </span>

          <div className="demo-panel-grid">
            <div />
            <div />
            <div />
            <div />
          </div>

          <p>
            {currentPage.description}
          </p>
        </div>
      </section>

      <footer className="reader-bottom-bar">
        <div className="reader-shortcuts">
          <span>
            ← → Change page
          </span>

          <span>
            + − Zoom
          </span>
        </div>

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
          className="reader-audio-request"
        >
          Request Audiobook
        </Link>
      </footer>
    </main>
  );
}