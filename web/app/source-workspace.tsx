"use client";

import { useState, type ButtonHTMLAttributes, type ComponentType, type ReactNode } from "react";
import { toast } from "sonner";
import type { Page, Project, Source } from "../lib/types";
import { moveTo, orderedSources, orderIssues, replaceSourceSlots, splitOrderConflicts } from "../lib/source-order";

type Props = {
  project: Project; pages: Page[]; dirty: boolean;
  asset: (path: string) => string;
  edit: (change: (project: Project) => void) => void;
  save: () => void;
  showSource: (source: Source) => void;
  showPage: (id: string) => void;
  Button: ComponentType<ButtonHTMLAttributes<HTMLButtonElement> & { reason?: string }>;
};

export function SourceWorkspace({ project, pages, dirty, asset, edit, save, showSource, showPage, Button }: Props) {
  const [view, setView] = useState<"images" | "panels" | "dialogue">("images");
  const [pageId, setPageId] = useState(pages[0]?.page_id || "");
  const [panelFilter, setPanelFilter] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [dragged, setDragged] = useState<string | null>(null);
  const [target, setTarget] = useState<string | null>(null);
  const pageOrder = project.page_order?.length ? project.page_order : pages.map(p => p.page_id);
  const orderedPages = pageOrder.map(id => pages.find(p => p.page_id === id)!).filter(Boolean);
  const page = pages.find(p => p.page_id === pageId) ?? orderedPages[0];
  const panels = [...(page?.panels || [])].sort((a, b) => (a.reading_order ?? 0) - (b.reading_order ?? 0));
  const panelOrder = project.panel_order?.[page?.page_id] ?? panels.map(p => p.panel_id);
  const sorted = orderedSources(project);
  const visibleSources = sorted.filter(s => (!pageId || s.page_id === page?.page_id) && (!panelFilter || s.panel_id === panelFilter));
  const source = project.sources.find(s => s.source_id === sourceId);
  const issues = orderIssues(project);

  function moved(message: string) {
    toast.success(message, { id: "source-order", description: "Order updated in your draft. Save when you finish reviewing.", duration: 3500 });
  }
  function moveImage(from: number, to: number) {
    const ids = moveTo(pageOrder, from, to);
    edit(p => {
      p.page_order = ids;
      const sources = orderedSources(p);
      p.sources = ids.flatMap(id => sources.filter(s => s.page_id === id));
      p.sources.forEach((s, order) => { s.order = order; });
    });
    moved(`Image moved to position ${to + 1}`);
  }
  function movePanel(from: number, to: number) {
    if (!page) return;
    const ids = moveTo(panelOrder, from, to);
    edit(p => {
      p.panel_order = { ...p.panel_order, [page.page_id]: ids };
      const sources = orderedSources(p).filter(s => s.page_id === page.page_id);
      const next = [...ids.flatMap(id => sources.filter(s => s.panel_id === id)), ...sources.filter(s => !s.panel_id || !ids.includes(s.panel_id))];
      replaceSourceSlots(p, next.map(s => s.source_id));
    });
    moved(`Panel moved to position ${to + 1}`);
  }
  function moveDialogue(from: number, to: number) {
    edit(p => replaceSourceSlots(p, moveTo(visibleSources.map(s => s.source_id), from, to)));
    moved(`Dialogue moved to position ${to + 1} in this view`);
  }
  function choosePage(id: string) { setPageId(id); setPanelFilter(""); setSourceId(""); if (id) showPage(id); }
  function selectSource(item: Source) { setSourceId(item.source_id); showSource(item); }
  function update(patch: Partial<Source>) {
    if (source) edit(p => { Object.assign(p.sources.find(s => s.source_id === source.source_id)!, patch); });
  }

  function row(id: string, index: number, ids: string[], move: (from: number, to: number) => void, label: string, content: ReactNode) {
    return <li key={id} className={`source-order-row ${target === id && dragged !== id ? "drop-target" : ""} ${dragged === id ? "dragging" : ""}`}
      onDragOver={e => { if (dragged && ids.includes(dragged)) { e.preventDefault(); e.dataTransfer.dropEffect = "move"; setTarget(id); } }}
      onDrop={e => { e.preventDefault(); if (dragged && dragged !== id && ids.includes(dragged)) move(ids.indexOf(dragged), index); setDragged(null); setTarget(null); }}>
      <Button className="source-drag-handle" draggable={ids.length > 1} aria-label={`Reorder ${label}. Use arrow keys, Home or End.`}
        onDragStart={e => { e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", id); setDragged(id); }}
        onDragEnd={() => { setDragged(null); setTarget(null); }}
        onKeyDown={e => { const to = { ArrowUp: index - 1, ArrowDown: index + 1, Home: 0, End: ids.length - 1 }[e.key]; if (to !== undefined) { e.preventDefault(); if (to >= 0 && to < ids.length && to !== index) move(index, to); } }}><span aria-hidden="true">⠿</span></Button>
      <div className="source-order-content">{content}</div>
      <label className="source-position">Move to<select aria-label={`Move ${label} to position`} value={index} onChange={e => move(index, Number(e.target.value))}>{ids.map((_, i) => <option key={i} value={i}>{i + 1}</option>)}</select></label>
    </li>;
  }

  return <div className="source-workspace"><h2>Source & reading order</h2><p className="control-note">Drag to reorder, or choose an exact position with Move to. Image and panel moves carry their dialogue with them.</p>
    <div className="segmented-control source-view-switch" aria-label="Reading order level">{(["images", "panels", "dialogue"] as const).map(id => <Button key={id} aria-pressed={view === id} onClick={() => { setView(id); if (id === "panels" && !pageId && orderedPages[0]) choosePage(orderedPages[0].page_id); setDragged(null); setTarget(null); }}>{id === "images" ? `Images · ${pages.length}` : id === "panels" ? "Panels" : "Dialogue"}</Button>)}</div>
    {view !== "images" && <label className="field-label">Image<select value={pageId} onChange={e => choosePage(e.target.value)}>{view === "dialogue" && <option value="">All images</option>}{orderedPages.map((p, i) => <option value={p.page_id} key={p.page_id}>{i + 1}. {p.image_filename}</option>)}</select></label>}
    {view === "images" && <ol className="source-order-list" aria-label="Image reading order">{orderedPages.map((p, i) => row(p.page_id, i, pageOrder, moveImage, p.page_id, <div className="source-image-row"><Button className="source-image-preview" aria-label={`Show ${p.page_id}`} onClick={() => showPage(p.page_id)}>{(p.original_path || p.annotated_path) && <img src={asset((p.original_path || p.annotated_path)!)} alt="" />}</Button><div><strong>Image {i + 1}</strong><span>{p.image_filename}</span><span>{project.sources.filter(s => s.page_id === p.page_id).length} dialogue sources</span><Button className="button small" onClick={() => { choosePage(p.page_id); setView("panels"); }}>Review panels →</Button></div></div>))}</ol>}
    {view === "panels" && <><ol className="source-order-list" aria-label="Panel reading order">{panelOrder.map((id, i) => {
      const panel = panels.find(p => p.panel_id === id);
      return row(id, i, panelOrder, movePanel, id, <div className="source-image-row"><Button className="source-image-preview" aria-label={`Review dialogue in ${id}`} onClick={() => { setPanelFilter(id); setSourceId(""); setView("dialogue"); }}>{panel && page && (page.original_path || page.annotated_path) && <svg viewBox={`${panel.bbox[0]} ${panel.bbox[1]} ${panel.bbox[2] - panel.bbox[0]} ${panel.bbox[3] - panel.bbox[1]}`} role="img" aria-label={`Panel ${i + 1}`}><image href={asset((page.original_path || page.annotated_path)!)} width={page.width} height={page.height} /></svg>}</Button><div><strong>Panel {i + 1}</strong><span>{id}</span><span>{project.sources.filter(s => s.page_id === page?.page_id && s.panel_id === id).length} dialogue sources</span><Button className="button small" onClick={() => { setPanelFilter(id); setSourceId(""); setView("dialogue"); }}>Order dialogue →</Button></div></div>);
    })}</ol>{!panelOrder.length && <p className="control-note">No panel boundaries were detected on this image. You can still reorder its dialogue.</p>}<Button className="button small" onClick={() => { setPanelFilter(""); setView("dialogue"); }}>Review all dialogue on this image</Button><p className="control-note">Text without a detected panel stays after the detected panels when you move a panel.</p></>}
    {view === "dialogue" && <><label className="field-label">Panel<select value={panelFilter} disabled={!pageId} onChange={e => { setPanelFilter(e.target.value); setSourceId(""); }}><option value="">All panels</option>{panelOrder.map((id, i) => <option key={id} value={id}>Panel {i + 1}</option>)}</select></label><ol className="source-order-list dialogue-order-list" aria-label="Dialogue reading order">{visibleSources.map((s, i) => row(s.source_id, i, visibleSources.map(item => item.source_id), moveDialogue, s.source_id, <Button className={`source-summary ${sourceId === s.source_id ? "selected" : ""}`} aria-pressed={sourceId === s.source_id} onClick={() => selectSource(s)}><strong>{project.cast[s.speaker_id]?.name || "Unresolved speaker"} {!s.include && "· Excluded"}</strong><span>{s.text || "No text recovered — select to transcribe"}</span><small>{s.page_id} · {s.scene_id}</small></Button>))}</ol>{!visibleSources.length && <p className="control-note">No dialogue sources in this view. Choose another panel or image.</p>}
      {source && <section className="source-detail" aria-label="Selected dialogue editor"><div className="dialogue-heading"><h3>Edit selected dialogue</h3><Button className="button small" onClick={() => showSource(source)}>Show on image</Button></div><label className="check-label"><input type="checkbox" checked={source.include} onChange={e => update({ include: e.target.checked })} /> Include in script</label><label className="field-label">Transcript<textarea value={source.text} onChange={e => update({ text: e.target.value })} /></label><details><summary>Original detected text</summary><p className="control-note">{source.original_text || "No text recovered. Transcribe from the manga image."}</p></details><label className="field-label">Speaker<select value={source.speaker_id} onChange={e => update({ speaker_id: e.target.value, speaker_origin: "manual" })}><option value="UNKNOWN">Unresolved speaker</option>{Object.entries(project.cast).map(([id, c]) => <option value={id} key={id}>{c.name}</option>)}</select></label><details key={source.source_id}><summary>Scene grouping, delivery & reaction</summary><div className="field-grid">{(["scene_id", "turn_group", "emotion", "style", "pacing"] as const).map(key => <label className="field-label" key={key}>{({ scene_id: "Scene ID", turn_group: "Speaking group", emotion: "Emotion", style: "Acting direction", pacing: "Pacing" })[key]}<input value={source[key]} onChange={e => update({ [key]: e.target.value })} /></label>)}<label className="field-label">Delivery<select value={source.delivery} onChange={e => update({ delivery: e.target.value })}>{["speech", "thought", "shout", "whisper", "narration"].map(d => <option key={d}>{d}</option>)}</select></label></div><label className="field-label">Reaction text<input value={source.reaction?.text || ""} onChange={e => update({ reaction: e.target.value ? { text: e.target.value, silence_sec: source.reaction?.silence_sec || 0 } : null })} /></label></details></section>}
    </>}
    {issues.length > 0 && <div className="action-guidance" role="status"><strong>Grouping needs review</strong>{issues.map(issue => <p key={issue}>{issue}</p>)}<p>Keep this order and split the repeated groups into new parts, or move the items back together. Review scene scripts again afterward.</p><Button className="button small" onClick={() => { edit(splitOrderConflicts); toast.info("Repeated groups split", { description: "Reading order is preserved. Review the rebuilt scenes after saving." }); }}>Split repeated groups</Button></div>}
    <div className="cast-save-bar"><span className={dirty ? "unsaved" : "control-note"}>{dirty ? "Unsaved order and transcript changes" : "Saved reading order"}</span><p className="control-note">Saving rebuilds dialogue turns and clears scene approvals. It can replace edits made in Script approval.</p><Button className="button primary" disabled={issues.length > 0} reason="Resolve the grouping issues above first." onClick={save}>Save order & rebuild script</Button></div>
  </div>;
}
