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

export default function AdminRequestsPage() {
  const [requests, setRequests] = useState<MangaRequest[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadRequests();
  }, []);

  function loadRequests() {
    try {
      const savedRequests = JSON.parse(
        localStorage.getItem("mangaRequests") || "[]"
      );

      setRequests(savedRequests.reverse());
    } catch (error) {
      console.error("Could not load manga requests:", error);
    } finally {
      setLoading(false);
    }
  }

  function updateRequestStatus(
    requestId: string,
    newStatus: string
  ) {
    const savedRequests: MangaRequest[] = JSON.parse(
      localStorage.getItem("mangaRequests") || "[]"
    );

    const updatedRequests = savedRequests.map((request) =>
      request.id === requestId
        ? {
            ...request,
            status: newStatus,
          }
        : request
    );

    localStorage.setItem(
      "mangaRequests",
      JSON.stringify(updatedRequests)
    );

    setRequests([...updatedRequests].reverse());
  }

  function handleGenerateAudio(requestId: string) {
    /*
      Later, your teammate can replace this with:

      await fetch(`/api/admin/requests/${requestId}/generate`, {
        method: "POST",
      });

      For now we simulate generation by changing
      the status to PROCESSING.
    */

    updateRequestStatus(requestId, "PROCESSING");
  }

  function formatDate(date: string) {
    return new Date(date).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  if (loading) {
    return (
      <main className="admin-requests-page">
        <p>Loading requests...</p>
      </main>
    );
  }

  return (
    <main className="admin-requests-page">
      <header className="admin-header">
        <div>
          <p className="browse-eyebrow">Admin</p>
          <h1>Audiobook Requests</h1>
          <p>
            Review and manage manga audiobook generation requests.
          </p>
        </div>

        <Link href="/browse" className="header-link">
          View Manga Reader
        </Link>
      </header>

      {requests.length === 0 ? (
        <section className="empty-requests">
          <h2>No requests yet</h2>
          <p>
            User audiobook requests will appear here.
          </p>
        </section>
      ) : (
        <section className="admin-request-list">
          {requests.map((request) => (
            <article
              key={request.id}
              className="admin-request-card"
            >
              <div className="admin-request-info">
                <div className="admin-request-heading">
                  <div>
                    <p className="request-manga">
                      {request.mangaTitle}
                    </p>

                    <h2>{request.chapter}</h2>
                  </div>

                  <span
                    className={`request-status status-${request.status.toLowerCase()}`}
                  >
                    {request.status}
                  </span>
                </div>

                {request.notes && (
                  <div className="request-notes">
                    <span>User Note</span>
                    <p>{request.notes}</p>
                  </div>
                )}

                <p className="request-date">
                  Requested {formatDate(request.createdAt)}
                </p>

                <p className="request-id">
                  Request ID: {request.id}
                </p>
              </div>

              <div className="admin-actions">
                {request.status === "PENDING" && (
                  <>
                    <button
                      type="button"
                      className="reject-button"
                      onClick={() =>
                        updateRequestStatus(
                          request.id,
                          "REJECTED"
                        )
                      }
                    >
                      Reject
                    </button>

                    <button
                      type="button"
                      className="approve-button"
                      onClick={() =>
                        updateRequestStatus(
                          request.id,
                          "APPROVED"
                        )
                      }
                    >
                      Approve
                    </button>
                  </>
                )}

                {request.status === "APPROVED" && (
                  <button
                    type="button"
                    className="generate-button"
                    onClick={() =>
                      handleGenerateAudio(request.id)
                    }
                  >
                    Generate Audio
                  </button>
                )}

                {request.status === "PROCESSING" && (
                  <button
                    type="button"
                    className="ready-button"
                    onClick={() =>
                      updateRequestStatus(
                        request.id,
                        "READY"
                      )
                    }
                  >
                    Mark Ready
                  </button>
                )}

                {request.status === "READY" && (
                  <span className="admin-complete">
                    ✓ Audiobook Ready
                  </span>
                )}

                {request.status === "REJECTED" && (
                  <button
                    type="button"
                    className="approve-button"
                    onClick={() =>
                      updateRequestStatus(
                        request.id,
                        "APPROVED"
                      )
                    }
                  >
                    Reopen Request
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