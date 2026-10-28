"use client";
import { useId, useState } from "react";

type Action = "approve" | "link" | "prepare" | "review" | "publish";
const symbols: Record<Action, string> = { approve: "✓", link: "↗", prepare: "♫", review: "✓", publish: "↑" };

export function RequestAction({ action, label, disabled, onClick }: {
  action: Action; label: string; disabled?: boolean; onClick: () => void;
}) {
  const id = useId();
  const [dismissed, setDismissed] = useState(false);
  return <span className="shared-action-tooltip" data-dismissed={dismissed || undefined}
    onMouseEnter={() => setDismissed(false)} onFocus={() => setDismissed(false)}
    onKeyDown={event => { if (event.key === "Escape") setDismissed(true); }}>
    <button type="button" className="button" aria-label={label} aria-describedby={id} disabled={disabled} onClick={onClick}>
      <span aria-hidden="true" className="shared-action-symbol" data-symbol={symbols[action]} />
      <span>{label}</span>
    </button><span id={id} role="tooltip" className="shared-action-label">{label}</span>
  </span>;
}
