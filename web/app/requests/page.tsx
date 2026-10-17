"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type MangaRequest = {
  id: string;
  mangaId?: string;
  chapterId?: string;

  mangaTitle: string;
  chapter: string;

  notes?: string;

  status: string;
  createdAt: string;
};

export default function MyRequestsPage() {
  const [requests, setRequests] =
    useState<MangaRequest[]>([]);

  const [loading, setLoading] =
    useState(true);

  useEffect(() => {
    try {
      const savedRequests = JSON.parse(
        localStorage.getItem(
          "mangaRequests"
        ) || "[]"
      );

      setRequests(
        savedRequests.reverse()
      );
    } catch (error) {
      console.error(
        "Could not load requests:",
        error
      );
    } finally {
      setLoading(false);
    }
  }, []);

  function formatDate(date: string) {
    return new Date(date).toLocaleString(
      undefined,
      {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }
    );
  }

  function getStatusClass(
    status: string
  ) {
    return `request-status status-${status.toLowerCase()}`;
  }

  if (loading) {
    return (
      <main className="requests-page">
        <p>Loading requests...</p>
      </main>
    );
  }

  return (
    <main className="requests-page">
      <header className="requests-header">
        <div>
          <p className="browse-eyebrow">
            Audiobook Requests
          </p>

          <h1>My Requests</h1>

          <p>
            Track the status of your
            requested manga audiobooks.
          </p>
        </div>

        <Link
          href="/browse"
          className="header-link"
        >
          Browse Manga
        </Link>
      </header>

      {requests.length === 0 ? (
        <section className="empty-requests">
          <h2>No requests yet</h2>

          <p>
            When you request an audiobook
            from a manga chapter, it will
            appear here.
          </p>

          <Link
            href="/browse"
            className="primary-action"
          >
            Browse Manga
          </Link>
        </section>
      ) : (
        <section className="requests-list">
          {requests.map((request) => (
            <article
              key={request.id}
              className="request-item"
            >
              <div className="request-main">
                <div className="request-title-row">
                  <div>
                    <p className="request-manga">
                      {request.mangaTitle}
                    </p>

                    <h2>
                      {request.chapter}
                    </h2>
                  </div>

                  <span
                    className={getStatusClass(
                      request.status
                    )}
                  >
                    {request.status}
                  </span>
                </div>

                {request.notes && (
                  <div className="request-notes">
                    <span>Note</span>

                    <p>
                      {request.notes}
                    </p>
                  </div>
                )}

                <p className="request-date">
                  Requested{" "}
                  {formatDate(
                    request.createdAt
                  )}
                </p>
              </div>

              <div className="request-actions">
                {request.mangaId && (
                  <Link
                    href={`/manga/${request.mangaId}`}
                    className="request-secondary-action"
                  >
                    View Manga
                  </Link>
                )}

                {request.mangaId &&
                  request.chapterId && (
                    <Link
                      href={`/read/${request.mangaId}/${request.chapterId}`}
                      className="read-button"
                    >
                      Read Chapter
                    </Link>
                  )}

                {request.status ===
                  "READY" && (
                  <button
                    type="button"
                    className="listen-button"
                  >
                    ▶ Listen
                  </button>
                )}
              </div>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}