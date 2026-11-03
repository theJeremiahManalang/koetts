"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

export function RequestPreviewModal({ open, signedIn, onDismiss }: { open: boolean; signedIn: boolean; onDismiss: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [title, setTitle] = useState("");
  const [chapter, setChapter] = useState("");
  const [notes, setNotes] = useState("");
  const [preview, setPreview] = useState(false);
  const valid = !!title.trim() && title.length <= 200 && /^[0-9]{1,4}$/.test(chapter) && Number(chapter) > 0 && notes.length <= 4000;

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

  return <dialog ref={dialog} className="browse-request-modal" aria-labelledby="request-modal-title" aria-describedby="request-modal-description" onCancel={event => { event.preventDefault(); event.stopPropagation(); onDismiss(); }} onKeyDown={event => event.stopPropagation()}>
    <button type="button" className="browse-modal-close" aria-label="Close request modal" onClick={onDismiss}>×</button>
    <span className="browse-tag">MANGA, WITH A VOICE</span>
    <h2 id="request-modal-title">Request a manga</h2>
    <p id="request-modal-description">Tell us which chapter you’d love to hear.</p>
    <p className="browse-modal-notice">UI preview only. Nothing is sent or saved.</p>
    {!signedIn ? <div className="browse-modal-actions"><p>Sign in to preview a manga request.</p><Link href="/login?next=%2Fbrowse" className="browse-primary">Sign in</Link></div> : preview ? <div className="browse-modal-confirmation" role="status">
      <h3>Request preview</h3><p><strong>{title.trim()}</strong> · Chapter {Number(chapter)}</p>{notes && <p className="browse-modal-notes">{notes}</p>}<p>This request has not been submitted. Your draft stays here until you leave this page.</p>
      <div className="browse-modal-actions"><button type="button" className="browse-primary" onClick={onDismiss}>Back to browsing</button><button type="button" onClick={() => setPreview(false)}>Edit draft</button></div>
    </div> : <form onSubmit={event => { event.preventDefault(); if (valid) setPreview(true); }}>
      <label htmlFor="modal-manga-title">Manga title <small>Required</small><input autoFocus id="modal-manga-title" required maxLength={200} value={title} onChange={event => setTitle(event.target.value)} placeholder="e.g. The Azure Chronicle" /></label>
      <label htmlFor="modal-manga-chapter">Chapter <small>Required</small><input id="modal-manga-chapter" required inputMode="numeric" pattern="[0-9]{1,4}" maxLength={4} value={chapter} onChange={event => setChapter(event.target.value.replace(/[^0-9]/g, "").slice(0, 4))} placeholder="e.g. 12" aria-describedby="modal-chapter-hint" /><small id="modal-chapter-hint">Choose a chapter from 1 to 9999.</small></label>
      <label htmlFor="modal-manga-notes">Additional details <small>Optional</small><textarea id="modal-manga-notes" maxLength={4000} rows={3} value={notes} onChange={event => setNotes(event.target.value)} placeholder="Anything you’d like us to know?" /></label>
      <div className="browse-modal-actions"><button type="button" onClick={onDismiss}>Cancel</button><button type="submit" className="browse-primary" disabled={!valid}>Preview request <span aria-hidden="true">↗</span></button></div>
    </form>}
  </dialog>;
}
