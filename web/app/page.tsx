"use client";

import { createContext, useContext, useEffect, useId, useRef, useState, type ButtonHTMLAttributes } from "react";
import { Toaster, toast } from "sonner";
import type { Acting, Job, Project, Segment, Snapshot, Turn } from "../lib/types";

type Tab = "cast" | "proposal" | "sources" | "script" | "audio";
const tabs: [Tab, string][] = [["cast", "Cast"], ["proposal", "AI proposal"], ["sources", "Source & order"], ["script", "Script approval"], ["audio", "Audio & export"]];
const actingFields = (v: Acting) => ({ include: v.include, speaker_id: v.speaker_id, text: v.text, delivery: v.delivery, emotion: v.emotion, style: v.style, pacing: v.pacing });
const assetUrl = (id: string, path: string, download = false) => `/api/asset?project=${encodeURIComponent(id)}&path=${encodeURIComponent(path)}${download ? "&download=1" : ""}`;

const BusyContext = createContext("");
function ActionButton({ disabled, reason, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { reason?: string }) {
  const busy = useContext(BusyContext);
  const hintId = useId();
  const message = busy ? `Wait for the current operation to finish: ${busy}` : disabled ? reason || "Complete the required fields first." : "";
  if (!message) return <button {...props}>{children}</button>;
  return <span className="disabled-action" tabIndex={0} role="group" aria-label={props["aria-label"] || (typeof children === "string" ? children : "Unavailable action")} aria-describedby={hintId}>
    <button {...props} disabled aria-describedby={hintId}>{children}</button>
    <span className="action-tooltip" role="tooltip" id={hintId}>{message}</span>
  </span>;
}

export default function Home() {
  const [projects, setProjects] = useState<{ id: string; name: string; scenes: number }[]>([]);
  const [projectId, setProjectId] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [draft, setDraft] = useState<Project | null>(null);
  const [tab, setTab] = useState<Tab>("cast");
  const [pageIndex, setPageIndex] = useState(0);
  const [sceneId, setSceneId] = useState("");
  const [zoom, setZoom] = useState(100);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [mode, setMode] = useState("images");
  const [archive, setArchive] = useState<File | null>(null);
  const [castZip, setCastZip] = useState<File | null>(null);
  const [direction, setDirection] = useState("rtl");
  const [proposal, setProposal] = useState("");
  const [selectedScenes, setSelectedScenes] = useState<string[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [mp3, setMp3] = useState(false);
  const [bundleReady, setBundleReady] = useState(false);
  const [hasKey, setHasKey] = useState(false);
  const [focusSource, setFocusSource] = useState("");
  const [newCharacter, setNewCharacter] = useState({ char_id: "", name: "", voice: "Kore" });
  const [narration, setNarration] = useState("");
  const [narrationEvidence, setNarrationEvidence] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const mounted = useRef(true);
  const initialized = useRef(false);
  const page = snapshot?.pages[pageIndex];
  const scene = draft?.scenes.find(s => s.scene_id === sceneId);
  const preview = snapshot && page?.preview_path ? assetUrl(projectId, page.preview_path) : previews[pageIndex];
  const focused = draft?.sources.find(s => s.source_id === focusSource && s.page_id === page?.page_id);

  async function api(url: string, options?: RequestInit) {
    const r = await fetch(url, options); const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Request failed.");
    return data;
  }
  async function refreshList() { const data = await api("/api/workflow"); setProjects(data.projects); setHasKey(data.has_api_key); }
  async function loadProject(id: string) {
    const data: Snapshot = await api(`/api/workflow?project=${id}`);
    setProjectId(id); setSnapshot(data); setDraft(structuredClone(data.project)); setDirty(false);
    setHasKey(data.has_api_key); setProposal(JSON.stringify(data.project.proposal?.data ?? null, null, 2));
    setSceneId(previous => data.project.scenes.some(s => s.scene_id === previous) ? previous : data.project.scenes[0]?.scene_id ?? "");
    setSelectedScenes(previous => previous.some(id => data.project.scenes.some(s => s.scene_id === id)) ? previous.filter(id => data.project.scenes.some(s => s.scene_id === id)) : data.project.scenes.map(s => s.scene_id));
    setPageIndex(i => Math.min(i, Math.max(0, data.pages.length - 1)));
    setSegments([]); setBundleReady(false);
    localStorage.setItem("manga-tts-project", id);
  }
  async function watch(job: { id: string; project: string }) {
    localStorage.setItem("manga-tts-job", JSON.stringify(job));
    try {
      while (mounted.current) {
        const state: Job = await api(`/api/workflow?job=${job.id}`);
        setBusy(state.message);
        if (["complete", "failed"].includes(state.status)) {
          localStorage.removeItem("manga-tts-job");
          await refreshList();
          if (state.status === "failed") {
            // Preserve editable drafts on failure; explicit reload recovers partial audio.
            throw new Error(state.message);
          }
          await loadProject(job.project);
          if (state.result?.segments) setSegments(state.result.segments);
          toast.success("Workspace saved");
          return true;
        }
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    } catch (e) { setError(e instanceof Error ? e.message : "Connection interrupted. Reload to reconnect."); }
    finally { setBusy(""); }
    return false;
  }
  useEffect(() => {
    mounted.current = true;
    if (initialized.current) return () => { mounted.current = false; };
    initialized.current = true;
    void (async () => {
      try {
        await refreshList();
        const job = localStorage.getItem("manga-tts-job");
        if (job) { setBusy("Reconnecting to your job…"); await watch(JSON.parse(job)); }
        else { const id = localStorage.getItem("manga-tts-project"); if (id) await loadProject(id); }
      } catch (e) { setError(e instanceof Error ? e.message : "Could not load projects."); }
    })();
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => { const urls = files.map(f => URL.createObjectURL(f)); setPreviews(urls); return () => urls.forEach(u => URL.revokeObjectURL(u)); }, [files]);
  useEffect(() => { const handler = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); } }; window.addEventListener("beforeunload", handler); return () => window.removeEventListener("beforeunload", handler); }, [dirty]);
  function edit(change: (p: Project) => void) { setDraft(p => { if (!p) return p; const next = structuredClone(p); change(next); return next; }); setDirty(true); setBundleReady(false); }
  function canLeave() { return !dirty || window.confirm("Discard unsaved edits in this section?"); }
  function switchTab(next: Tab) { if (next === tab || !canLeave()) return; setDraft(structuredClone(snapshot!.project)); setProposal(JSON.stringify(snapshot!.project.proposal?.data ?? null, null, 2)); setDirty(false); setTab(next); setError(""); }
  async function run(action: string, command: unknown = {}, extra = {}) {
    if (busy || !snapshot) return false;
    setError(""); setBusy("Saving your request…");
    try {
      const job = await api("/api/workflow", { method: "POST", headers: { "Content-Type": "application/json", "X-Manga-Workflow": "1" }, body: JSON.stringify({ project: projectId, revision: snapshot.revision, action, command, ...extra }) });
      const ok = await watch(job);
      if (ok && ["take", "export", "bundle"].includes(action)) setSegments(segments);
      if (ok && action === "bundle") setBundleReady(true);
      return ok;
    } catch (e) { setError(e instanceof Error ? e.message : "Request failed."); setBusy(""); return false; }
  }
  async function upload(form: FormData) {
    setError(""); setBusy("Uploading your files…");
    try { const job = await api("/api/workflow", { method: "POST", headers: { "X-Manga-Workflow": "1" }, body: form }); await watch(job); }
    catch (e) { setError(e instanceof Error ? e.message : "Upload failed."); setBusy(""); }
  }
  function createProject() {
    setTab("cast");
    const form = new FormData(); form.set("action", "create"); form.set("mode", mode); form.set("direction", direction);
    files.forEach(f => form.append("images", f)); if (archive && mode !== "images") form.set("chapter", archive); if (castZip && mode !== "restore") form.set("cast", castZip);
    void upload(form);
  }
  function importCast(file: File | undefined) { if (!file) return; const form = new FormData(); form.set("action", "cast-import"); form.set("project", projectId); form.set("revision", snapshot!.revision); form.set("cast", file); void upload(form); }
  function selectFiles(selected: FileList | null) {
    if (!selected) return;
    const next = Array.from(selected).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    if (next.length > 10 || next.some(f => !["image/png", "image/jpeg", "image/webp"].includes(f.type) || !f.size || f.size > 10 * 1024 * 1024)) { setError("Choose up to 10 PNG, JPEG or WebP images, 10 MB each."); return; }
    setFiles(next); setPageIndex(0); setError("");
  }
  function saveCast(approve = false) { if (!draft) return; void run("cast", { cast: Object.entries(draft.cast).map(([speaker_id, c]) => ({ speaker_id, name: c.name, voice: c.voice, pronunciation: c.pronunciation, acting_notes: c.acting_notes ?? "" })), appearances: draft.appearances.map(({ char_id, speaker_id, rejected }) => ({ char_id, speaker_id, rejected })), approve }); }
  function saveSources() { if (!draft) return; void run("sources", { sources: draft.sources.map(s => ({ ...actingFields(s), source_id: s.source_id, order: s.order, scene_id: s.scene_id, turn_group: s.turn_group, reaction: s.reaction })) }); }
  function saveScript(approve = false) { if (scene) void run("script", { scene_id: scene.scene_id, title: scene.title, context: scene.context, turns: scene.turns.map(t => ({ ...actingFields(t), turn_id: t.turn_id, silence_sec: t.silence_sec })), approve }); }
  function moveSource(id: string, delta: number) { edit(p => { const sorted = [...p.sources].sort((a, b) => a.order - b.order); const from = sorted.findIndex(s => s.source_id === id), to = from + delta; if (to < 0 || to >= sorted.length) return; [sorted[from], sorted[to]] = [sorted[to], sorted[from]]; sorted.forEach((s, i) => { s.order = i; }); p.sources = sorted; }); }
  function speakerSelect(value: string, onChange: (v: string) => void, narrator = true) { return <select aria-label="Speaker" value={value} onChange={e => onChange(e.target.value)}><option value="UNKNOWN">Unresolved speaker</option>{Object.entries(draft?.cast ?? {}).filter(([id]) => narrator || id !== "NARRATOR").map(([id, c]) => <option key={id} value={id}>{c.name}</option>)}</select>; }
  function actingEditor(value: Acting, update: (patch: Partial<Acting>) => void) { return <div className="field-grid"><label className="field-label">Delivery<select value={value.delivery} onChange={e => update({ delivery: e.target.value })}>{["speech", "thought", "shout", "whisper", "narration"].map(d => <option key={d}>{d}</option>)}</select></label><label className="field-label">Emotion<input value={value.emotion} onChange={e => update({ emotion: e.target.value })} /></label><label className="field-label">Acting direction<input value={value.style} onChange={e => update({ style: e.target.value })} /></label><label className="field-label">Pacing<input value={value.pacing} onChange={e => update({ pacing: e.target.value })} /></label></div>; }
  const pendingScenes = snapshot?.project.scenes.filter(s => !snapshot.approved_scenes.includes(s.scene_id)) ?? [];
  const unapprovedSelected = pendingScenes.filter(s => selectedScenes.includes(s.scene_id));
  const unresolved = draft?.appearances.filter(a => !a.rejected && !draft.cast[a.speaker_id]).length ?? 0;
  const audioBlocker = dirty ? "Apply or discard your unsaved edits first. Changed content may need approval again."
    : !snapshot?.cast_approved ? "Approve the cast in the Cast section first."
    : !selectedScenes.length ? "Select at least one scene in Audio & export."
    : unapprovedSelected.length ? `Approve these scenes in Script approval: ${unapprovedSelected.map(s => s.title || s.scene_id).join(", ")}.` : "";
  function openApproval(target: Tab, id?: string) {
    if (busy || !canLeave()) return;
    setDraft(structuredClone(snapshot!.project)); setDirty(false); setError(""); setTab(target);
    if (id) setSceneId(id);
  }

  return <BusyContext.Provider value={busy}><div className="app-shell">
    <Toaster position="top-right" closeButton theme="light" />
    <header className="site-header"><a className="brand" href="/" aria-label="Manga Reader home"><span className="brand-icon" aria-hidden="true">▥</span><span><span className="eyebrow">A STORY IN EVERY PANEL</span><span className="brand-title">Manga Reader<span className="brand-dot">.</span></span></span></a><div className="header-actions"><label className="visually-hidden" htmlFor="projects">Saved project</label><select id="projects" value={projectId} disabled={!!busy} onChange={e => { if (e.target.value && canLeave()) { setBusy("Loading project…"); void loadProject(e.target.value).catch(e => setError(e.message)).finally(() => setBusy("")); } }}><option value="">Saved projects</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name} · {p.id.slice(0, 6)}</option>)}</select><ActionButton className="button" disabled={!!busy} onClick={() => { if (!canLeave()) return; setSnapshot(null); setDraft(null); setProjectId(""); setDirty(false); setFiles([]); setArchive(null); setError(""); setPageIndex(0); localStorage.removeItem("manga-tts-project"); }}>＋ New chapter</ActionButton></div></header>
    <main>
      <div className="reader-heading"><div><div className="eyebrow">YOUR READING SPACE</div><h1>A voice for every character.</h1><p>{snapshot ? "Review the story, direct the voices, and create your audiobook." : "Start with manga images or pick up a saved production."}</p></div><span className="mode-label"><span className="status-dot" />{snapshot ? `${snapshot.project.chapter_id} · ${snapshot.approved_scenes.length}/${snapshot.project.scenes.length} scenes approved` : "Reviewed manga audio"}</span></div>
      <div className="workflow-status" aria-live="polite">{busy && <p className="notice processing"><span className="spinner" aria-hidden="true" />{busy} <span className="control-note">You can return after reloading this page.</span></p>}{error && <div className="notice error" role="alert">{error}{snapshot && <ActionButton className="button" disabled={!!busy} onClick={() => { if (canLeave()) { setBusy("Reloading…"); void loadProject(projectId).then(() => setError("")).catch(e => setError(e.message)).finally(() => setBusy("")); } }}>Reload saved state</ActionButton>}</div>}</div>
      {snapshot && <nav className="workflow-tabs" aria-label="Production steps">{tabs.map(([id, title], i) => <ActionButton key={id} className="button" aria-current={tab === id ? "step" : undefined} disabled={!!busy} onClick={() => switchTab(id)}><span>{String(i + 1).padStart(2, "0")}</span>{title}</ActionButton>)}</nav>}
      {snapshot && <section className="approval-checklist" aria-labelledby="approval-heading">
        <h2 id="approval-heading">Approval checklist</h2>
        <p className="control-note">Approvals below reflect saved work. AI proposals are optional; review text and reading order before approving each scene.</p>
        {dirty && <p className="unsaved" role="status">Unsaved edits in {tabs.find(([id]) => id === tab)?.[1]}. Apply them, then check approvals again.</p>}
        <ul>
          <li><span><strong>Cast</strong> — {snapshot.cast_approved ? "Approved" : "Needs approval"}{unresolved > 0 ? ` · ${unresolved} unresolved appearance(s)` : ""}</span><ActionButton className="button small" onClick={() => openApproval("cast")}>Review cast</ActionButton></li>
          {snapshot.project.scenes.map(s => <li key={s.scene_id}><span><strong>{s.title || s.scene_id}</strong> — {snapshot.approved_scenes.includes(s.scene_id) ? "Approved" : "Needs script approval"}</span><ActionButton className="button small" onClick={() => openApproval("script", s.scene_id)}>Review scene</ActionButton></li>)}
        </ul>
        {!snapshot.project.scenes.length && <p className="control-note">No scenes yet. Review sources and apply their order to build scene turns.</p>}
        {snapshot.cast_approved && !pendingScenes.length && snapshot.project.scenes.length > 0 && !dirty && <p className="control-note">All approvals are current. Select scenes in Audio & export to inspect and render.</p>}
        <p className="control-note">{hasKey ? "Gemini key configured for new audio." : "Gemini key missing: add GEMINI_API_KEY to web/.env.local and restart the server for new audio. Existing current takes can still be exported."}</p>
        <p className="control-note">Export needs current audio takes. Render missing audio first; export validates each chosen take.</p>
      </section>}
      <div className="page-list" aria-label="Page order">{(snapshot ? snapshot.pages.map(p => p.page_id) : files.map(f => f.name)).map((name, i) => <div key={i}><ActionButton className="button" aria-pressed={pageIndex === i} onClick={() => { setPageIndex(i); setZoom(100); }}>{i + 1}. {name}</ActionButton>{!snapshot && <><ActionButton className="button" disabled={!!busy || i === 0} reason="This image is already first." aria-label={`Move ${name} earlier`} onClick={() => { const next = [...files]; [next[i-1], next[i]] = [next[i], next[i-1]]; setFiles(next); setPageIndex(i-1); }}>←</ActionButton><ActionButton className="button" disabled={!!busy || i === files.length - 1} reason="This image is already last." aria-label={`Move ${name} later`} onClick={() => { const next = [...files]; [next[i+1], next[i]] = [next[i], next[i+1]]; setFiles(next); setPageIndex(i+1); }}>→</ActionButton></>}</div>)}</div>
      <div className="reader-grid">
        <section className="art-card" aria-label="Manga artwork"><div className="art-toolbar"><span>{preview ? `IMAGE ${pageIndex + 1} / ${snapshot?.pages.length ?? files.length}` : "YOUR MANGA"}</span><span>{focused ? "HIGHLIGHTED SOURCE" : "VISUAL EVIDENCE"}</span></div>
          <div className={`art-stage ${preview ? "has-image" : ""}`} tabIndex={preview ? 0 : undefined}>{preview ? <div className="evidence-canvas" style={{ width: `${zoom}%` }}><img src={preview} alt={`Manga page ${pageIndex + 1}`} />{focused && page && <svg className="source-overlay" viewBox={`0 0 ${page.width} ${page.height}`} aria-label="Selected text region"><rect x={focused.bbox[0]} y={focused.bbox[1]} width={focused.bbox[2] - focused.bbox[0]} height={focused.bbox[3] - focused.bbox[1]} /></svg>}</div> : <div className="art-placeholder"><span className="panel-symbol" aria-hidden="true"><i /><i /><i /></span><h2>Your story starts here.</h2><p>Upload a panel, a page, or several pages.</p><ActionButton className="button" onClick={() => fileInput.current?.click()} disabled={!!busy || !!snapshot} reason="Start a new chapter to upload different images.">Choose manga images</ActionButton></div>}</div>
          {preview && <><div className="zoom-toolbar"><ActionButton className="button" aria-label="Zoom out" disabled={zoom <= 50} reason="Minimum zoom is 50%." onClick={() => setZoom(zoom - 25)}>−</ActionButton><output>{zoom}%</output><ActionButton className="button" aria-label="Zoom in" disabled={zoom >= 300} reason="Maximum zoom is 300%." onClick={() => setZoom(zoom + 25)}>+</ActionButton><ActionButton className="button" onClick={() => setZoom(100)}>Fit</ActionButton></div><div className="art-caption">{page?.image_filename ?? files[pageIndex]?.name}</div></>}
          {snapshot && draft && <div className="story-section"><h2 className="eyebrow">CHARACTER APPEARANCES · IMAGE {pageIndex + 1}</h2><p className="control-note">A detection is a visual clue, not a confirmed identity. Review assignments in Cast.</p><div className="appearance-list">{draft.appearances.filter(a => a.page_id === page?.page_id).map(a => <div className={`appearance ${a.rejected ? "rejected" : ""}`} key={a.char_id}><img src={assetUrl(projectId, `input/${a.crop_path}`)} alt={`Detected appearance ${a.char_id}`} /><span>{a.char_id}</span><strong>{a.rejected ? "Rejected detection" : draft.cast[a.speaker_id]?.name ?? "Unresolved"}</strong></div>)}</div></div>}
        </section>
        <section className="reading-card" aria-label="Production workspace">
          {!snapshot || !draft ? <><div className="panel-meta"><span>Start a production</span><span>01 / Upload</span></div><fieldset disabled={!!busy}><div className="story-section"><h2 className="eyebrow">BRING YOUR STORY</h2><div className="segmented-control">{[["images", "Images"], ["chapter", "Chapter ZIP"], ["restore", "Restore ZIP"]].map(([id, label]) => <ActionButton key={id} aria-pressed={mode === id} onClick={() => { setMode(id); setArchive(null); }}>{label}</ActionButton>)}</div><input ref={fileInput} className="visually-hidden" type="file" multiple accept="image/png,image/jpeg,image/webp" aria-label="Upload manga images" onChange={e => { selectFiles(e.target.files); e.target.value = ""; setMode("images"); }} />
            {mode === "images" ? <><p className="control-note">Choose up to 10 images, 10 MB each. Arrange their sequence above before extracting.</p><ActionButton className="button" onClick={() => fileInput.current?.click()}>＋ Choose images</ActionButton><label className="field-label">Reading direction<select value={direction} onChange={e => setDirection(e.target.value)}><option value="rtl">Right to left · MagiV3 order</option><option value="ltr">Left to right · layout proposal</option></select></label></> : <label className="field-label">{mode === "restore" ? "Saved project bundle" : "Chapter analysis bundle"}<input key={mode} type="file" accept=".zip" onChange={e => setArchive(e.target.files?.[0] ?? null)} /><span className="control-note">{mode === "restore" ? "Restores references, approvals and retained audio without new generation." : "Use the chapter_analysis.zip produced by your extraction workflow."}</span></label>}
            {mode !== "restore" && <label className="field-label">Cast references ZIP <span className="muted">Optional; you can also create characters from panel crops.</span><input type="file" accept=".zip" onChange={e => setCastZip(e.target.files?.[0] ?? null)} /></label>}
            <div className="action-row"><ActionButton className="button primary" disabled={mode === "images" ? !files.length : !archive} reason={mode === "images" ? "Choose manga images first." : "Choose a ZIP file first."} onClick={createProject}>{mode === "images" ? "Extract & create project" : mode === "restore" ? "Restore project" : "Create project"}</ActionButton></div></div></fieldset><div className="story-section"><h2 className="eyebrow">FROM PANEL TO PERFORMANCE</h2><ol className="journey"><li><strong>Read the page</strong><span>Recover text and propose its order.</span></li><li><strong>Find each voice</strong><span>Match appearances to your cast.</span></li><li><strong>Approve the story</strong><span>Review dialogue and delivery before synthesis.</span></li><li><strong>Listen & export</strong><span>Choose takes and download your chapter.</span></li></ol></div></> : <>
            <div className="panel-meta"><span>{tabs.find(([id]) => id === tab)?.[1]}</span><span className={dirty ? "unsaved" : ""}>{dirty ? "Unsaved edits" : "Applied state saved"}</span></div>
            <fieldset disabled={!!busy}>
              {tab === "cast" && <><div className="story-section"><h2 className="eyebrow">CHARACTERS & VOICES</h2><p className="control-note">Create characters from your uploaded panels below, or optionally import a reference ZIP. No API key is needed to set up your cast.</p><div className="cast-editor"><h3>Create a character from a panel</h3><p className="control-note">Choose one clear appearance as a reference, then name the character and choose a voice. Assign other appearances of this person using their dropdown.</p><label className="field-label">Reference appearance<select value={newCharacter.char_id} onChange={e => setNewCharacter({ ...newCharacter, char_id: e.target.value })}><option value="">Choose a detected appearance</option>{draft.appearances.map(a => <option key={a.char_id} value={a.char_id}>{a.char_id} / {a.page_id}</option>)}</select></label>{newCharacter.char_id && draft.appearances.some(a => a.char_id === newCharacter.char_id) && <img className="cast-reference" src={assetUrl(projectId, `input/${draft.appearances.find(a => a.char_id === newCharacter.char_id)!.crop_path}`)} alt="Selected character reference" />}<div className="field-grid"><label className="field-label">Character name<input value={newCharacter.name} placeholder="For example, Renako or Character 1" maxLength={120} onChange={e => setNewCharacter({ ...newCharacter, name: e.target.value })} /></label><label className="field-label">Voice<select value={newCharacter.voice} onChange={e => setNewCharacter({ ...newCharacter, voice: e.target.value })}>{snapshot.voices.map(v => <option key={v} value={v}>{v}</option>)}</select></label></div><ActionButton className="button" disabled={dirty || !newCharacter.char_id || !newCharacter.name.trim()} reason={dirty ? "Apply your cast edits first." : !newCharacter.char_id ? "Choose a reference appearance first." : "Enter a character name."} onClick={async () => { if (await run("cast-create", newCharacter)) setNewCharacter({ char_id: "", name: "", voice: "Kore" }); }}>Create & assign character</ActionButton>{dirty && <p className="control-note">Click Apply cast to save your edits before creating another character.</p>}</div><label className="field-label">Import cast references<input type="file" accept=".zip" disabled={dirty} onChange={e => { importCast(e.target.files?.[0]); e.target.value = ""; }} /></label><datalist id="voices">{snapshot.voices.map(v => <option key={v} value={v} />)}</datalist>{Object.entries(draft.cast).map(([id, c]) => <div className="cast-editor" key={id}><div className="eyebrow">{id}</div>{c.references?.[0] && <img className="cast-reference" src={assetUrl(projectId, c.references[0])} alt={`${c.name} reference`} />}<div className="field-grid"><label className="field-label">Name<input value={c.name} onChange={e => edit(p => { p.cast[id].name = e.target.value; })} /></label><label className="field-label">Gemini voice<input list="voices" value={c.voice} onChange={e => edit(p => { p.cast[id].voice = e.target.value; })} /></label></div><label className="field-label">Pronunciation<input value={c.pronunciation} onChange={e => edit(p => { p.cast[id].pronunciation = e.target.value; })} /></label><label className="field-label">Base acting notes<textarea value={c.acting_notes ?? ""} onChange={e => edit(p => { p.cast[id].acting_notes = e.target.value; })} /></label></div>)}</div><div className="story-section"><h2 className="eyebrow">IDENTIFY APPEARANCES</h2><p className="control-note">{draft.appearances.filter(a => !a.rejected && !draft.cast[a.speaker_id]).length} unresolved appearance(s). Assign a character to each, or reject false detections. Create missing characters above.</p>{draft.appearances.map((a, i) => <div className="appearance-assignment" key={a.char_id}><ActionButton className="crop-button" aria-label={`Show page for ${a.char_id}`} onClick={() => setPageIndex(snapshot.pages.findIndex(p => p.page_id === a.page_id))}><img src={assetUrl(projectId, `input/${a.crop_path}`)} alt={a.char_id} /></ActionButton><div><span className="control-note">{a.char_id}</span>{speakerSelect(a.speaker_id, value => edit(p => { p.appearances[i].speaker_id = value; }), false)}<label className="check-label"><input type="checkbox" checked={a.rejected} onChange={e => edit(p => { p.appearances[i].rejected = e.target.checked; })} /> Reject false detection</label></div></div>)}</div><div className="action-row sticky-actions"><ActionButton className="button" onClick={() => saveCast()}>Apply cast</ActionButton><ActionButton className="button primary" onClick={() => saveCast(true)}>Apply & approve cast</ActionButton><span className="control-note">{snapshot.cast_approved && !dirty ? "Cast approved" : "Approval required before script approval"}</span></div></>}
              {tab === "proposal" && <><div className="story-section"><h2 className="eyebrow">AI ASSISTED DIRECTION</h2><p>Propose character identities, reading order, scene boundaries and delivery from the chapter evidence.</p><p className="control-note">Generate may use your Gemini quota. Loading a proposal replaces unapproved assignments and script, and clears approvals. Generation alone does not change your script.</p>{!hasKey && <p className="notice">No API key configured on the server. Existing projects remain available for review and export.</p>}<ActionButton className="button primary" disabled={dirty || Object.keys(draft.cast).length < 2} reason={dirty ? "Apply or discard your edits first." : "Create a character from a crop or import cast references first."} onClick={() => void run("plan")}>Generate visual proposal</ActionButton></div>{draft.proposal && <div className="story-section"><label className="field-label">Review or edit proposal<textarea className="json-editor" value={proposal} spellCheck={false} onChange={e => { setProposal(e.target.value); setDirty(true); }} /></label><ActionButton className="button" onClick={() => { try { void run("proposal", JSON.parse(proposal)); } catch { setError("Proposal must be valid JSON."); } }}>Load proposal into review</ActionButton><p className="control-note">Then revisit Cast, Sources and Script to approve the changes.</p></div>}</>}
              {tab === "sources" && <><div className="story-section"><h2 className="eyebrow">SOURCE TEXT & READING ORDER</h2><p className="control-note">All chapter sources in reading order. Select a source to highlight it. Apply grouping before editing final dialogue: rebuilding replaces final turn edits.</p></div>{[...draft.sources].sort((a, b) => a.order - b.order).map((s, rank) => { const index = draft.sources.findIndex(v => v.source_id === s.source_id); const update = (patch: Partial<typeof s>) => edit(p => { Object.assign(p.sources[index], patch); }); return <div className="dialogue-editor" key={s.source_id}><div className="dialogue-heading"><label><input type="checkbox" checked={s.include} onChange={e => update({ include: e.target.checked })} /> Include {rank + 1}</label><ActionButton className="button small" onClick={() => { setFocusSource(s.source_id); setPageIndex(snapshot.pages.findIndex(p => p.page_id === s.page_id)); }}>{s.page_id} · show</ActionButton></div><label className="field-label">Source transcript<textarea value={s.text} onChange={e => update({ text: e.target.value })} onFocus={() => { setFocusSource(s.source_id); setPageIndex(snapshot.pages.findIndex(p => p.page_id === s.page_id)); }} /></label><p className="control-note">Recovered OCR: {s.original_text || "No text recovered — correct from the image."}</p><label className="field-label">Speaker{speakerSelect(s.speaker_id, v => update({ speaker_id: v }))}</label><details><summary>Grouping, acting & reaction</summary><div className="field-grid"><label className="field-label">Scene ID<input value={s.scene_id} onChange={e => update({ scene_id: e.target.value })} /></label><label className="field-label">Turn group<input value={s.turn_group} onChange={e => update({ turn_group: e.target.value })} /></label></div>{actingEditor(s, update)}<label className="field-label">Reaction text (optional)<input value={s.reaction?.text ?? ""} onChange={e => update({ reaction: e.target.value ? { text: e.target.value, silence_sec: s.reaction?.silence_sec ?? 0 } : null })} /></label></details><div className="action-row"><ActionButton className="button small" disabled={rank === 0} reason="This source is already first." onClick={() => moveSource(s.source_id, -1)} aria-label={`Move source ${rank + 1} earlier`}>↑ Earlier</ActionButton><ActionButton className="button small" disabled={rank === draft.sources.length - 1} reason="This source is already last." onClick={() => moveSource(s.source_id, 1)} aria-label={`Move source ${rank + 1} later`}>↓ Later</ActionButton></div></div>; })}<div className="action-row sticky-actions"><ActionButton className="button primary" onClick={saveSources}>Apply sources & rebuild turns</ActionButton></div></>}
              {tab === "script" && <><div className="story-section"><h2 className="eyebrow">THE EXACT SPOKEN SCRIPT</h2><label className="field-label">Scene<select value={sceneId} onChange={e => { if (canLeave()) { setDraft(structuredClone(snapshot.project)); setDirty(false); setSceneId(e.target.value); } }}>{draft.scenes.map(s => <option key={s.scene_id} value={s.scene_id}>{s.title} {snapshot.approved_scenes.includes(s.scene_id) ? "· Approved" : "· Needs approval"}</option>)}</select></label>{!snapshot.cast_approved && <p className="notice">Approve the cast before approving scenes.</p>}</div>{scene && <><label className="field-label">Scene title<input value={scene.title} onChange={e => edit(p => { p.scenes.find(s => s.scene_id === sceneId)!.title = e.target.value; })} /></label><label className="field-label">Scene context<textarea value={scene.context} onChange={e => edit(p => { p.scenes.find(s => s.scene_id === sceneId)!.context = e.target.value; })} /></label>{scene.turns.map((t, i) => { const update = (patch: Partial<Turn>) => edit(p => { Object.assign(p.scenes.find(s => s.scene_id === sceneId)!.turns[i], patch); }); return <div className="dialogue-editor" key={t.turn_id}><div className="dialogue-heading"><label><input type="checkbox" checked={t.include} onChange={e => update({ include: e.target.checked })} /> {t.kind === "narration" ? "Narration" : `Turn ${i + 1}`}</label><span className="control-note">{t.source_ids.length} source(s)</span></div><label className="field-label">Speaker{speakerSelect(t.speaker_id, v => update({ speaker_id: v }))}</label><label className="field-label">Approved wording<textarea value={t.text} onChange={e => update({ text: e.target.value })} /></label>{actingEditor(t, update)}<label className="field-label">Deliberate silence after turn (seconds)<input type="number" min="0" max="30" step="0.1" value={t.silence_sec} onChange={e => update({ silence_sec: Number(e.target.value) })} /></label></div>; })}<div className="action-row sticky-actions"><ActionButton className="button" onClick={() => saveScript()}>Apply script</ActionButton><ActionButton className="button primary" disabled={!snapshot.cast_approved} reason="Approve the cast in the Cast section first." onClick={() => saveScript(true)}>Apply & approve scene</ActionButton></div><details className="story-section"><summary>Add visible-evidence narration</summary><p className="control-note">Save your edits first. This inserts narration at the start of this scene.</p><label className="field-label">Narration text<textarea value={narration} onChange={e => setNarration(e.target.value)} /></label><label className="field-label">Visual evidence source<select value={narrationEvidence} onChange={e => setNarrationEvidence(e.target.value)}><option value="">Choose a source</option>{draft.sources.filter(s => s.scene_id === sceneId).map(s => <option key={s.source_id} value={s.source_id}>{s.source_id}</option>)}</select></label><ActionButton className="button" disabled={dirty || !narration.trim() || !narrationEvidence} reason={dirty ? "Apply your script edits first." : !narration.trim() ? "Enter narration text." : "Choose a visual evidence source."} onClick={() => void run("narration", { scene_id: sceneId, position: 0, text: narration, evidence_source_ids: [narrationEvidence] })}>Insert narration</ActionButton></details></>}</>}
              {tab === "audio" && <><div className="story-section"><h2 className="eyebrow">AUDIO PRODUCTION</h2><p className="control-note">Render only approved scenes. Current takes are reused; regeneration keeps previous takes.</p>{draft.scenes.map(s => <label className="scene-choice" key={s.scene_id}><input type="checkbox" checked={selectedScenes.includes(s.scene_id)} onChange={e => { setSelectedScenes(e.target.checked ? [...selectedScenes, s.scene_id] : selectedScenes.filter(id => id !== s.scene_id)); setSegments([]); }} /><span>{s.title}</span><span className="badge">{snapshot.approved_scenes.includes(s.scene_id) ? "Approved" : "Review needed"}</span></label>)}<div className="action-row"><ActionButton className="button" disabled={!!audioBlocker} reason={audioBlocker} onClick={() => void run("inspect", { scene_ids: selectedScenes })}>Inspect segments</ActionButton><ActionButton className="button primary" disabled={!!audioBlocker} reason={audioBlocker} onClick={() => void run("render", { scene_ids: selectedScenes, regenerate: [] })}>Render selected audio</ActionButton></div><p className="control-note">New audio uses Gemini quota. Inspection and cached playback do not.</p></div>
                {segments.map(seg => <div className="segment-editor" key={seg.segment_id}><div className="dialogue-heading"><h3>{seg.segment_id}</h3><span className="badge">{seg.silence_sec ? `${seg.silence_sec}s silence` : "Speech"}</span></div><p className="segment-transcript">{seg.turns.map(t => t.text).join(" ") || "Deliberate silence"}</p><details><summary>Exact synthesis request</summary><pre>{JSON.stringify(seg.request, null, 2)}</pre></details>{(draft.takes[seg.signature] ?? []).map(take => <div className="take" key={take.take_id}><div className="dialogue-heading"><span>{take.duration_sec.toFixed(2)}s · {take.take_id}</span><ActionButton className="button small" disabled={dirty || draft.selected_takes[`${seg.segment_id}:${seg.signature}`] === take.take_id} reason={dirty ? "Apply your edits first." : "This take is already selected."} onClick={() => void run("take", { segment_id: seg.segment_id, take_id: take.take_id })}>{draft.selected_takes[`${seg.segment_id}:${seg.signature}`] === take.take_id ? "Selected" : "Use this take"}</ActionButton></div><audio controls preload="none" src={assetUrl(projectId, take.path)} />{take.clipped_samples > 0 && <p className="control-note">Clipping detected: {take.clipped_samples} samples.</p>}</div>)}<ActionButton className="button small" disabled={dirty} reason="Apply your edits first." onClick={() => void run("render", { scene_ids: [seg.scene_id], regenerate: [seg.segment_id] })}>Regenerate this segment</ActionButton></div>)}
                <div className="story-section"><h2 className="eyebrow">ASSEMBLE & DOWNLOAD</h2><label className="check-label"><input type="checkbox" checked={mp3} onChange={e => setMp3(e.target.checked)} /> Include MP3 (requires ffmpeg)</label><div className="action-row"><ActionButton className="button primary" disabled={!!audioBlocker} reason={audioBlocker} onClick={() => void run("export", { scene_ids: selectedScenes }, { mp3 })}>Export chosen takes</ActionButton><ActionButton className="button" disabled={dirty} reason="Apply your edits first." onClick={() => void run("bundle")}>Create project bundle</ActionButton></div>{snapshot.exports.length > 0 && <><p className="control-note">Last export. Export again after any script or take change; existing files may reflect an earlier version.</p>{snapshot.exports.includes("chapter_narration.wav") && <audio controls preload="none" src={assetUrl(projectId, "exports/chapter_narration.wav") + `&revision=${snapshot.revision}`} />}<div className="download-list">{snapshot.exports.map(name => <a className="button" key={name} href={assetUrl(projectId, `exports/${name}`, true)}>{name.replace("chapter_narration", "Chapter")}</a>)}</div></>}{bundleReady && <a className="button" href={assetUrl(projectId, "bundle.zip", true)}>Download resumable project ZIP</a>}</div>
                <details className="story-section"><summary>Models, segment budget & pauses</summary>{(["planning_model", "tts_model"] as const).map(key => <label key={key} className="field-label">{key === "planning_model" ? "Planning model" : "Speech model"}<input value={draft.settings[key]} onChange={e => edit(p => { p.settings[key] = e.target.value; })} /></label>)}{(["max_chars", "scene_pause", "segment_pause"] as const).map(key => <label key={key} className="field-label">{key === "max_chars" ? "Characters per segment" : key === "scene_pause" ? "Pause between scenes (seconds)" : "Pause between segments (seconds)"}<input type="number" min={key === "max_chars" ? 100 : 0} step={key === "max_chars" ? 1 : .01} value={draft.settings[key]} onChange={e => edit(p => { p.settings[key] = Number(e.target.value); })} /></label>)}<p className="control-note">Applying settings clears scene approvals. Review scenes again before rendering.</p><ActionButton className="button" onClick={() => void run("settings", { settings: draft.settings })}>Apply settings</ActionButton></details></>}
            </fieldset>
          </>}
        </section>
      </div>
      <footer className="reader-footer"><span>Original images preserved · Human approval before speech</span><span>Local workspace · Mono 24 kHz WAV · Resumable projects</span></footer>
    </main>
  </div></BusyContext.Provider>;
}
