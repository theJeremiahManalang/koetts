"use client";

import { useId, useRef, useState } from "react";
import { toast } from "sonner";

type Props = {
  files: File[];
  previews: Map<File, string>;
  selected: number;
  disabled: boolean;
  onSelect: (index: number) => void;
  onReorder: (files: File[]) => void;
};

export function ImageOrder({ files, previews, selected, disabled, onSelect, onReorder }: Props) {
  const instructions = useId();
  const [dragged, setDragged] = useState<File | null>(null);
  const [target, setTarget] = useState<number | null>(null);
  const handles = useRef(new Map<File, HTMLButtonElement>());
  const identities = useRef(new Map<File, number>());

  function move(file: File, to: number, focus = false) {
    const from = files.indexOf(file);
    if (disabled || from < 0 || to < 0 || to >= files.length || from === to) return;
    const next = [...files];
    next.splice(from, 1);
    next.splice(to, 0, file);
    onReorder(next);
    toast.success(`${file.name} moved to position ${to + 1}`, {
      id: "image-order", description: "This order will be used when creating the chapter.", duration: 3000,
    });
    if (focus) requestAnimationFrame(() => handles.current.get(file)?.focus());
  }

  return <section className="image-order" aria-labelledby={`${instructions}-heading`}>
    <div className="image-order-heading"><div><h2 id={`${instructions}-heading`}>Arrange your images</h2><p id={instructions}>Drag the grip to reorder, or use Earlier and Later. Select a thumbnail to inspect it below. Read the sequence from 1 onward.</p></div>
      <div className="action-row">
        <button type="button" className="button small" disabled={disabled || files.length < 2} onClick={() => {
          onReorder([...files].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true })));
          toast.success("Images sorted by filename", { id: "image-order", description: "Numbered filenames are sorted naturally, such as 1, 2, 10." });
        }}>Sort by filename</button>
        <button type="button" className="button small" disabled={disabled || files.length < 2} onClick={() => {
          onReorder([...files].reverse());
          toast.success("Image order reversed", { id: "image-order", description: "Review the numbered thumbnails before creating the chapter." });
        }}>Reverse order</button>
      </div>
    </div>
    <ol className="image-order-list" aria-describedby={instructions}>
      {files.map((file, i) => {
        if (!identities.current.has(file)) identities.current.set(file, identities.current.size);
        return <li key={identities.current.get(file)} className={`image-order-card ${selected === i ? "selected" : ""} ${dragged === file ? "dragging" : ""} ${target === i && dragged !== file ? "drop-target" : ""}`}
          onDragOver={e => { if (!disabled && dragged) { e.preventDefault(); e.dataTransfer.dropEffect = "move"; setTarget(i); } }}
          onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setTarget(current => current === i ? null : current); }}
          onDrop={e => { if (!disabled && dragged) { e.preventDefault(); move(dragged, i); } setDragged(null); setTarget(null); }}>
          <div className="image-order-meta"><span>IMAGE {i + 1}</span><button type="button" className="image-drag-handle" disabled={disabled || files.length < 2}
            ref={element => { if (element) handles.current.set(file, element); else handles.current.delete(file); }}
            draggable={!disabled && files.length > 1} aria-label={`Reorder ${file.name}, position ${i + 1}. Use arrow keys to move, Home for first, End for last.`}
            onDragStart={e => { if (disabled) { e.preventDefault(); return; } e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", file.name); setDragged(file); }}
            onDragEnd={() => { setDragged(null); setTarget(null); }}
            onKeyDown={e => { const to = { ArrowLeft: i - 1, ArrowUp: i - 1, ArrowRight: i + 1, ArrowDown: i + 1, Home: 0, End: files.length - 1 }[e.key]; if (to !== undefined) { e.preventDefault(); move(file, to, true); } }}><span aria-hidden="true">⠿</span></button></div>
          <button type="button" className="image-order-preview" disabled={disabled} aria-pressed={selected === i} aria-label={`Preview image ${i + 1}: ${file.name}`} onClick={() => onSelect(i)}>
            {previews.get(file) ? <img src={previews.get(file)} alt="" draggable={false} /> : <span>Loading preview…</span>}
          </button>
          <span className="image-order-name" title={file.name}>{file.name}</span>
          <div className="image-order-moves"><button type="button" className="button small" disabled={disabled || i === 0} aria-label={`Move ${file.name} earlier`} onClick={() => move(file, i - 1, true)}>← Earlier</button><button type="button" className="button small" disabled={disabled || i === files.length - 1} aria-label={`Move ${file.name} later`} onClick={() => move(file, i + 1, true)}>Later →</button></div>
        </li>;
      })}
    </ol>
    <p className="control-note">{files.length} image{files.length === 1 ? "" : "s"} · This sets the order of uploaded images. Reading direction controls the panels within each image.</p>
  </section>;
}
