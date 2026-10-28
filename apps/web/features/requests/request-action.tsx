"use client";

import { useId, useState } from "react";

type ActionIcon = "generate" | "approved" | "rejected" | "submitted" | "processing" | "ready";

function Icon({ name }: { name: ActionIcon }) {
  const paths: Record<ActionIcon, React.ReactNode> = {
    generate: <><path d="m9 5 11 7-11 7V5Z" /><path d="M4 8v8" /></>,
    approved: <path d="m5 12 4 4L19 6" />,
    rejected: <path d="m6 6 12 12M6 18 18 6" />,
    submitted: <><path d="M3 10a9 9 0 1 1 2 8M3 4v6h6" /></>,
    processing: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    ready: <><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></>,
  };
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export function RequestAction({ icon, label, href, disabled, onClick }: {
  icon: ActionIcon; label: string; href?: string; disabled?: boolean; onClick?: () => void;
}) {
  const id = useId();
  const [dismissed, setDismissed] = useState(false);
  const description = { "aria-label": label, "aria-describedby": id, className: `request-icon-action${icon === "rejected" ? " is-destructive" : ""}` };
  return <span className="request-action-tooltip" data-dismissed={dismissed || undefined} onMouseEnter={() => setDismissed(false)} onFocus={() => setDismissed(false)} onKeyDown={event => { if (event.key === "Escape") setDismissed(true); }}>
    {href && !disabled ? <a {...description} href={href}><Icon name={icon} /></a> : <button {...description} type="button" disabled={disabled} onClick={onClick}><Icon name={icon} /></button>}
    <span id={id} role="tooltip" className="request-action-label">{label}</span>
  </span>;
}
