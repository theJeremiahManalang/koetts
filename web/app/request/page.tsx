"use client";

import { FormEvent, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

export default function RequestMangaPage() {
  const searchParams = useSearchParams();

  const mangaId =
  searchParams.get("mangaId") || "";

  const chapterId =
  searchParams.get("chapterId") || "";  

  const selectedManga =
    searchParams.get("manga") || "";

  const selectedChapter =
    searchParams.get("chapter") || "";

  const [notes, setNotes] = useState("");
  const [message, setMessage] = useState("");

  function handleSubmit(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();

    const newRequest = {
      id: crypto.randomUUID(),
      mangaTitle: selectedManga,
      chapter: selectedChapter,
      notes,
      status: "PENDING",
      createdAt: new Date().toISOString(),
    };

    const existingRequests = JSON.parse(
      localStorage.getItem("mangaRequests") ||
        "[]"
    );

    existingRequests.push(newRequest);

    localStorage.setItem(
      "mangaRequests",
      JSON.stringify(existingRequests)
    );

    setMessage(
      "Audiobook request submitted successfully!"
    );

    setNotes("");
  }

  return (
    <main className="request-page">
      <section className="request-card">
        <Link href="/browse" className="back-link">
          ← Back to manga
        </Link>

        <p className="browse-eyebrow">
          Audiobook Request
        </p>

        <h1>Request Audiobook</h1>

        <p className="request-intro">
          Request an accessible narrated version
          of this manga chapter.
        </p>

        <div className="request-summary">
          <div>
            <span>Manga</span>
            <strong>
              {selectedManga || "No manga selected"}
            </strong>
          </div>

          <div>
            <span>Chapter</span>
            <strong>
              {selectedChapter ||
                "No chapter selected"}
            </strong>
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="request-form"
        >
          <label>
            Additional Notes
            <textarea
              value={notes}
              onChange={(event) =>
                setNotes(event.target.value)
              }
              placeholder="Optional message for the admin..."
              rows={5}
            />
          </label>

          <button
            type="submit"
            className="submit-request"
            disabled={
              !selectedManga ||
              !selectedChapter
            }
          >
            Submit Audiobook Request
          </button>

          {message && (
            <p
              className="success-message"
              role="status"
            >
              {message}
            </p>
          )}
        </form>
      </section>
    </main>
  );
}