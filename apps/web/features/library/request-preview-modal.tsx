"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

export function RequestPreviewModal({
  open,
  signedIn,
  onDismiss,
}: {
  open: boolean;
  signedIn: boolean;
  onDismiss: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [title, setTitle] = useState("");
  const [chapter, setChapter] = useState("");
  const [notes, setNotes] = useState("");
  const [preview, setPreview] = useState(false);
  const valid =
    !!title.trim() &&
    title.length <= 200 &&
    /^[0-9]{1,4}$/.test(chapter) &&
    Number(chapter) > 0 &&
    notes.length <= 4000;

  useEffect(() => {
    const element = dialog.current;
    if (!open || !element) return;
    const opener = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    setPreview(false);
    element.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      element.close();
      document.body.style.overflow = overflow;
      if (opener?.isConnected) opener.focus({ preventScroll: true });
    };
  }, [open]);

  return (
    <dialog
      ref={dialog}
      className="browse-request-modal [&_.browse-tag]:mb-[16px] [&_label>small]:ml-[6px] [&_label>small]:text-[10px] [&_label>small]:font-normal [&_label>small]:text-[var(--muted)] m-auto max-h-[calc(100dvh-40px)] w-[min(500px,calc(100vw-32px))] overflow-y-auto rounded-[18px] border border-[var(--line)] bg-[var(--surface)] p-[30px] text-[var(--ink)] shadow-[0_24px_100px_#0008] backdrop:bg-[#050a0dc9] [@media(max-width:700px)]:mt-auto [@media(max-width:700px)]:mx-0 [@media(max-width:700px)]:mb-0 [@media(max-width:700px)]:max-h-[90dvh] [@media(max-width:700px)]:w-full [@media(max-width:700px)]:max-w-none [@media(max-width:700px)]:rounded-[18px_18px_0_0] [@media(max-width:700px)]:px-[20px] [@media(max-width:700px)]:pt-[24px] [@media(max-width:700px)]:pb-[max(24px,env(safe-area-inset-bottom))]"
      aria-labelledby="request-modal-title"
      aria-describedby="request-modal-description"
      onCancel={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onDismiss();
      }}
      onKeyDown={(event) => event.stopPropagation()}
    >
      <button
        type="button"
        className="browse-modal-close absolute top-[18px] right-[18px] size-[36px] rounded-[50%] border-none bg-[#283331] text-[24px]!"
        aria-label="Close request modal"
        onClick={onDismiss}
      >
        ×
      </button>
      <span className="browse-tag mb-[20px] inline-block rounded-[20px] bg-[#204139] px-[10px] py-[7px] text-[9px] tracking-[1px] text-[var(--accent)] [@media(max-width:700px)]:mb-[13px] [@media(max-width:700px)]:text-[7px]">
        MANGA, WITH A VOICE
      </span>
      <h2
        className="mt-0 mr-[36px] mb-[10px] ml-0 text-[26px] font-bold tracking-[-.6px]"
        id="request-modal-title"
      >
        Request a manga
      </h2>
      <p
        className="text-[13px] leading-[1.6] text-[var(--muted)]"
        id="request-modal-description"
      >
        Tell us which chapter you’d love to hear.
      </p>
      <p className="browse-modal-notice my-[18px] mx-0 rounded-[8px] border border-[#39594e] bg-[#223b34] px-[12px] py-[10px] text-[13px] leading-[1.6] text-[var(--muted)]">
        UI preview only. Nothing is sent or saved.
      </p>
      {!signedIn ? (
        <div className="browse-modal-actions [&>button:not(.browse-primary)]:rounded-[24px] [&>button:not(.browse-primary)]:border [&>button:not(.browse-primary)]:border-[var(--line)] [&>button:not(.browse-primary)]:bg-transparent [&>button:not(.browse-primary)]:px-[18px] [&>button:not(.browse-primary)]:py-[11px] [&>button:not(.browse-primary)]:text-[12px]! mt-[10px] flex flex-wrap items-center justify-end gap-[12px]">
          <p className="text-[13px] leading-[1.6] text-[var(--muted)]">
            Sign in to preview a manga request.
          </p>
          <Link
            href="/login?next=%2Fbrowse"
            className="browse-primary inline-flex items-center justify-center gap-[24px] rounded-[24px] border-none bg-[var(--accent)] px-[20px] py-[12px] text-[12px]! font-bold! text-[#102c27] [&:hover:not(:disabled)]:bg-[#8cebd7]"
          >
            Sign in
          </Link>
        </div>
      ) : preview ? (
        <div
          className="browse-modal-confirmation [overflow-wrap:anywhere]"
          role="status"
        >
          <h3 className="mt-[20px] mr-0 mb-[12px] ml-0 text-[18px]">
            Request preview
          </h3>
          <p className="text-[13px] leading-[1.6] text-[var(--muted)]">
            <strong>{title.trim()}</strong> · Chapter {Number(chapter)}
          </p>
          {notes && (
            <p className="browse-modal-notes whitespace-pre-wrap text-[13px] leading-[1.6] text-[var(--muted)]">
              {notes}
            </p>
          )}
          <p className="text-[13px] leading-[1.6] text-[var(--muted)]">
            This request has not been submitted. Your draft stays here until you
            leave this page.
          </p>
          <div className="browse-modal-actions [&>button:not(.browse-primary)]:rounded-[24px] [&>button:not(.browse-primary)]:border [&>button:not(.browse-primary)]:border-[var(--line)] [&>button:not(.browse-primary)]:bg-transparent [&>button:not(.browse-primary)]:px-[18px] [&>button:not(.browse-primary)]:py-[11px] [&>button:not(.browse-primary)]:text-[12px]! mt-[10px] flex flex-wrap items-center justify-end gap-[12px]">
            <button
              type="button"
              className="browse-primary inline-flex items-center justify-center gap-[24px] rounded-[24px] border-none bg-[var(--accent)] px-[20px] py-[12px] text-[12px]! font-bold! text-[#102c27] [&:hover:not(:disabled)]:bg-[#8cebd7]"
              onClick={onDismiss}
            >
              Back to browsing
            </button>
            <button type="button" onClick={() => setPreview(false)}>
              Edit draft
            </button>
          </div>
        </div>
      ) : (
        <form
          className="grid gap-[18px]"
          onSubmit={(event) => {
            event.preventDefault();
            if (valid) setPreview(true);
          }}
        >
          <label
            className="block text-[12px] font-semibold"
            htmlFor="modal-manga-title"
          >
            Manga title <small>Required</small>
            <input
              className="mt-[8px] block bg-[var(--surface)]!"
              autoFocus
              id="modal-manga-title"
              required
              maxLength={200}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="e.g. The Azure Chronicle"
            />
          </label>
          <label
            className="block text-[12px] font-semibold"
            htmlFor="modal-manga-chapter"
          >
            Chapter <small>Required</small>
            <input
              className="mt-[8px] block bg-[var(--surface)]!"
              id="modal-manga-chapter"
              required
              inputMode="numeric"
              pattern="[0-9]{1,4}"
              maxLength={4}
              value={chapter}
              onChange={(event) =>
                setChapter(
                  event.target.value.replace(/[^0-9]/g, "").slice(0, 4),
                )
              }
              placeholder="e.g. 12"
              aria-describedby="modal-chapter-hint"
            />
            <small id="modal-chapter-hint">
              Choose a chapter from 1 to 9999.
            </small>
          </label>
          <label
            className="block text-[12px] font-semibold"
            htmlFor="modal-manga-notes"
          >
            Additional details <small>Optional</small>
            <textarea
              className="mt-[8px] block bg-[var(--paper)]! min-h-[90px]! resize-y"
              id="modal-manga-notes"
              maxLength={4000}
              rows={3}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Anything you’d like us to know?"
            />
          </label>
          <div className="browse-modal-actions [&>button:not(.browse-primary)]:rounded-[24px] [&>button:not(.browse-primary)]:border [&>button:not(.browse-primary)]:border-[var(--line)] [&>button:not(.browse-primary)]:bg-transparent [&>button:not(.browse-primary)]:px-[18px] [&>button:not(.browse-primary)]:py-[11px] [&>button:not(.browse-primary)]:text-[12px]! mt-[10px] flex flex-wrap items-center justify-end gap-[12px]">
            <button type="button" onClick={onDismiss}>
              Cancel
            </button>
            <button
              type="submit"
              className="browse-primary inline-flex items-center justify-center gap-[24px] rounded-[24px] border-none bg-[var(--accent)] px-[20px] py-[12px] text-[12px]! font-bold! text-[#102c27] [&:hover:not(:disabled)]:bg-[#8cebd7]"
              disabled={!valid}
            >
              Preview request <span aria-hidden="true">↗</span>
            </button>
          </div>
        </form>
      )}
    </dialog>
  );
}
