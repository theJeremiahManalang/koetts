"use client";

import { useEffect, useRef, useState } from "react";
import { Toaster, toast } from "sonner";
import { Analysis, Appearance, Character, Line, playbackErrors, scriptFor } from "../lib/analysis";

export default function Home() {
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [index, setIndex] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [direction, setDirection] = useState<"rtl" | "ltr">("rtl");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [appearances, setAppearances] = useState<Appearance[]>([]);
  const [lines, setLines] = useState<Line[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [voices, setVoices] = useState<string[]>([]);
  const [voiceError, setVoiceError] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [audio, setAudio] = useState("");
  const [storageReady, setStorageReady] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const registryInput = useRef<HTMLInputElement>(null);
  const player = useRef<HTMLAudioElement>(null);
  const file = files[index];
  const script = analysis ? scriptFor(analysis, characters, lines, appearances) : null;
  const issues = script ? playbackErrors(script, voices) : [];

  useEffect(() => {
    fetch("/api/voices").then(r => r.json()).then(data => { setVoices(data.voices ?? []); setVoiceError(data.error || (!data.voices?.length ? "No installed speech voices were found." : "")); }).catch(() => setVoiceError("Could not load speech voices."));
    try {
      const stored = localStorage.getItem("manga-character-registry-v1");
      if (stored) setCharacters(parseRegistry(JSON.parse(stored)));
    } catch { toast.error("Saved character registry could not be loaded."); }
    setStorageReady(true);
  }, []);
  useEffect(() => {
    if (!storageReady) return;
    try { localStorage.setItem("manga-character-registry-v1", JSON.stringify(characters)); }
    catch { toast.error("Could not save characters in this browser. Export the registry to keep it."); }
  }, [characters, storageReady]);
  useEffect(() => {
    const urls = files.map(f => URL.createObjectURL(f)); setPreviews(urls);
    return () => urls.forEach(url => URL.revokeObjectURL(url));
  }, [files]);
  useEffect(() => () => { if (audio) URL.revokeObjectURL(audio); }, [audio]);

  function invalidateAudio() { player.current?.pause(); setAudio(""); }
  function resetAnalysis() { invalidateAudio(); setAnalysis(null); setAppearances([]); setLines([]); setError(""); }
  function selectFiles(selected: FileList | null) {
    if (!selected) return;
    const next = Array.from(selected).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    if (!next.length || next.length > 10 || next.some(f => !["image/png", "image/jpeg", "image/webp"].includes(f.type) || !f.size || f.size > 10*1024*1024) || next.reduce((sum, f) => sum+f.size, 0) > 50*1024*1024) {
      setError("Choose 1–10 PNG, JPEG or WebP images: 10 MB each, 50 MB total."); return;
    }
    resetAnalysis(); setFiles(next); setIndex(0); setZoom(100);
  }
  function movePage(from: number, to: number) {
    resetAnalysis(); const next = [...files]; [next[from], next[to]] = [next[to], next[from]]; setFiles(next); setIndex(to);
  }
  async function extract() {
    if (!files.length || busy) return;
    resetAnalysis(); setBusy("Reading your images… The first run can take several minutes.");
    try {
      const body = new FormData(); files.forEach(f => body.append("images", f)); body.append("direction", direction);
      const response = await fetch("/api/extract", { method: "POST", body }); const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      setAnalysis(result); setAppearances(result.pages.flatMap((p: Analysis["pages"][number]) => p.appearances));
      setLines(result.pages.flatMap((p: Analysis["pages"][number]) => p.lines));
      toast.success("Analysis ready", { description: "Review dialogue and assign characters before generating audio." });
    } catch (e) { setError(e instanceof Error ? e.message : "Analysis failed."); }
    finally { setBusy(""); }
  }
  function addCharacter() { invalidateAudio(); setCharacters([...characters, { id: crypto.randomUUID(), name: `Character ${characters.length+1}`, voice: "" }]); }
  function updateCharacter(id: string, patch: Partial<Character>) { invalidateAudio(); setCharacters(characters.map(c => c.id === id ? { ...c, ...patch } : c)); }
  function assignAppearance(appearance: Appearance, characterId: string, wholeCluster = false) {
    invalidateAudio(); setAppearances(appearances.map(a => (wholeCluster ? a.group_id === appearance.group_id : a.id === appearance.id) ? { ...a, character_id: characterId || null } : a));
  }
  function updateLine(id: string, patch: Partial<Line>) { invalidateAudio(); setLines(lines.map(l => l.id === id ? { ...l, ...patch } : l)); }
  function addLine() {
    const page = analysis?.pages[index];
    if (!page) return;
    invalidateAudio();
    setLines([...lines, { id: crypto.randomUUID(), page_id: page.id, sequence: lines.length + 1,
      text: "", bbox: [0, 0, page.width, page.height], detection_index: null, speaker_candidates: [],
      appearance_id: null, included: true, warning: "Manually added; position in reading order after editing" }]);
  }
  function moveLine(from: number, to: number) { invalidateAudio(); const next = [...lines]; [next[from], next[to]] = [next[to], next[from]]; setLines(next); }
  function download(value: unknown, filename: string) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function parseRegistry(value: unknown): Character[] {
    if (!Array.isArray(value) || value.length > 500 || value.some(c => !c || typeof c.id !== "string" || !c.id || typeof c.name !== "string" || typeof c.voice !== "string") || new Set(value.map(c => c.id)).size !== value.length) throw new Error("Invalid character registry.");
    return value.map(c => ({ id: c.id, name: c.name, voice: c.voice }));
  }
  async function importRegistry(file: File | undefined) {
    if (!file) return;
    try {
      if (file.size > 1_000_000) throw new Error("Registry must be smaller than 1 MB.");
      const imported = parseRegistry(JSON.parse(await file.text()));
      invalidateAudio(); setCharacters([...characters.filter(c => !imported.some(i => i.id === c.id)), ...imported]); toast.success("Characters imported");
    } catch (e) { setError(e instanceof Error ? e.message : "Import failed."); }
  }
  async function generateAudio(lineId?: string) {
    if (!script || busy) return;
    const selected = lineId ? { ...script, lines: script.lines.map(l => ({ ...l, included: l.id === lineId })) } : script;
    const errors = playbackErrors(selected, voices);
    if (errors.length) { setError(errors[0]); return; }
    invalidateAudio(); setError(""); setBusy("Generating character voices…");
    try {
      const response = await fetch("/api/audio", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(selected) });
      if (!response.ok) throw new Error((await response.json()).error);
      setAudio(URL.createObjectURL(await response.blob())); toast.success(lineId ? "Line audio ready" : "Dialogue audio ready");
    } catch (e) { setError(e instanceof Error ? e.message : "Audio generation failed."); }
    finally { setBusy(""); }
  }
  async function copyJson() {
    try { await navigator.clipboard.writeText(JSON.stringify(script, null, 2)); toast.success("JSON copied"); }
    catch { setError("Clipboard is unavailable. Use Download JSON instead."); }
  }

  return <div className="app-shell">
    <Toaster position="top-right" closeButton theme="light" />
    <header className="site-header"><a className="brand" href="/" aria-label="Manga Reader home"><span className="brand-icon" aria-hidden="true">▥</span><span><span className="eyebrow">A STORY IN EVERY PANEL</span><span className="brand-title">Manga Reader<span className="brand-dot">.</span></span></span></a><button className="button upload-button" disabled={!!busy} onClick={() => input.current?.click()}>＋ Upload images</button><input ref={input} className="visually-hidden" type="file" multiple accept="image/png,image/jpeg,image/webp" aria-label="Upload manga images" disabled={!!busy} onChange={e => { selectFiles(e.target.files); e.target.value = ""; }} /></header>
    <main><div className="reader-heading"><div><div className="eyebrow">YOUR READING SPACE</div><h1>A voice for every character.</h1><p>Upload, review the dialogue, and bring your characters to life.</p></div><span className="mode-label">Character analysis · Proof of concept</span></div>
      <fieldset disabled={!!busy} className="workspace-controls"><legend className="eyebrow">READING DIRECTION WITHIN EACH IMAGE</legend><div className="segmented-control">{(["rtl", "ltr"] as const).map(d => <button key={d} aria-pressed={direction === d} onClick={() => { if (d !== direction) { resetAnalysis(); setDirection(d); } }}>{d === "rtl" ? "Right to left" : "Left to right"}</button>)}</div><button className="button primary" disabled={!files.length} onClick={extract}>{analysis ? "Analyze again" : "Analyze images"}</button></fieldset>
      {files.length > 0 && <div className="page-list" aria-label="Image order">{files.map((f, i) => <div key={`${f.name}-${i}`}><button className="button" aria-pressed={index === i} disabled={!!busy} onClick={() => { setIndex(i); setZoom(100); }}>{i+1}. {f.name}</button><button className="button" disabled={!!busy || i === 0} aria-label={`Move ${f.name} earlier`} onClick={() => movePage(i, i-1)}>←</button><button className="button" disabled={!!busy || i === files.length-1} aria-label={`Move ${f.name} later`} onClick={() => movePage(i, i+1)}>→</button></div>)}</div>}
      <div className="reader-grid"><section className="art-card" aria-label="Manga artwork"><div className="art-toolbar"><span>{file ? `IMAGE ${index+1} / ${files.length}` : "YOUR MANGA"}</span>{file && <button className="button" disabled={!!busy} onClick={() => { resetAnalysis(); setFiles([]); setIndex(0); }}>Clear images</button>}</div><div className={`art-stage ${file ? "has-image" : ""}`} tabIndex={file ? 0 : undefined}>{file ? <div className="image-canvas" style={{ width: `${zoom}%`, height: `${zoom}%` }}><img src={previews[index]} alt={file.name} /></div> : <div className="art-placeholder"><span className="panel-symbol" aria-hidden="true"><i /><i /><i /></span><h2>Your story starts here.</h2><p>Upload a panel, a page, or several pages.</p></div>}</div>{file && <><div className="zoom-toolbar"><button className="button" disabled={zoom <= 50} aria-label="Zoom out" onClick={() => setZoom(zoom-25)}>−</button><output>{zoom}%</output><button className="button" disabled={zoom >= 300} aria-label="Zoom in" onClick={() => setZoom(zoom+25)}>+</button><button className="button" onClick={() => setZoom(100)}>Fit</button></div><div className="art-caption">{file.name}</div></>}
      {analysis && <div className="story-section"><h2 className="eyebrow">CHARACTER APPEARANCES · IMAGE {index+1}</h2><p className="control-note">Assign each crop, or apply an identity to its suggested cluster. Confirm the same identity across pages.</p><div className="appearance-list">{appearances.filter(a => analysis.pages[index]?.appearances.some(p => p.id === a.id)).map(a => <div className="appearance" key={a.id}>{a.crop && <img src={a.crop} alt={`Character appearance ${a.id}`} />}<span>{a.id}</span><select aria-label={`Identity for ${a.id}`} disabled={!!busy} value={a.character_id ?? ""} onChange={e => assignAppearance(a, e.target.value)}><option value="">Unknown character</option>{characters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select><button className="button" disabled={!!busy || !a.character_id} onClick={() => assignAppearance(a, a.character_id!, true)}>Apply to cluster</button></div>)}</div>{!analysis.pages[index]?.appearances.length && <p className="control-note">No character appearances detected. Assign off-panel speakers directly to dialogue.</p>}</div>}</section>
      <section className="reading-card" aria-label="Dialogue review"><div className="panel-meta"><span>Review before audio</span><span>{lines.length} text regions</span></div><div className="story-section"><h2 className="eyebrow">CHARACTERS & VOICES</h2><p className="control-note">Characters and voice choices stay in this browser. Reuse the same character for recurring appearances.</p><fieldset disabled={!!busy}>{characters.map(c => <div className="character-row" key={c.id}><input aria-label={`Name for ${c.name}`} value={c.name} maxLength={100} onChange={e => updateCharacter(c.id, { name: e.target.value })} /><select aria-label={`Voice for ${c.name}`} value={c.voice} onChange={e => updateCharacter(c.id, { voice: e.target.value })}><option value="">Select voice</option>{c.voice && !voices.includes(c.voice) && <option value={c.voice}>{c.voice} (unavailable)</option>}{voices.map(v => <option key={v}>{v}</option>)}</select></div>)}<div className="action-row"><button className="button" onClick={addCharacter}>＋ Character</button><button className="button" onClick={() => download(characters, "characters.json")} disabled={!characters.length}>Export characters</button><button className="button" onClick={() => registryInput.current?.click()}>Import</button><input ref={registryInput} type="file" className="visually-hidden" accept="application/json" aria-label="Import character registry" onChange={e => { importRegistry(e.target.files?.[0]); e.target.value = ""; }} /></div></fieldset>{voiceError && <p className="control-note" role="status">{voiceError}</p>}</div>
      <div className="story-section dialogue"><div className="dialogue-heading"><h2 className="eyebrow">DIALOGUE</h2>{script && <button className="button copy-json-button" onClick={copyJson}>Copy JSON</button>}</div>{!analysis ? <p className="muted">Analyze your images to review their dialogue here.</p> : !lines.length ? <p>No text was detected. Try a clearer image.</p> : <fieldset disabled={!!busy}>{lines.map((line, i) => <div className="dialogue-editor" key={line.id}><div className="dialogue-heading"><label><input type="checkbox" checked={line.included} onChange={e => updateLine(line.id, { included: e.target.checked })} /> Speak line {i+1}</label><span className="muted">{line.page_id}</span></div><textarea aria-label={`Dialogue line ${i+1}`} value={line.text} maxLength={5000} onChange={e => updateLine(line.id, { text: e.target.value })} /><label className="field-label">Speaker appearance<select value={line.appearance_id ?? ""} onChange={e => updateLine(line.id, { appearance_id: e.target.value || null, character_id: null })}><option value="">Unknown / off-panel speaker</option>{appearances.filter(a => analysis.pages.find(p => p.id === line.page_id)?.appearances.some(p => p.id === a.id)).map(a => <option key={a.id} value={a.id}>{a.id} · {characters.find(c => c.id === a.character_id)?.name || "unassigned"}</option>)}</select></label>{!line.appearance_id && <label className="field-label">Character<select value={line.character_id ?? ""} onChange={e => updateLine(line.id, { character_id: e.target.value || null })}><option value="">Unknown character</option>{characters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>}{line.warning && <p className="control-note">Model note: {line.warning}</p>}<div className="action-row"><button className="button" disabled={i === 0} aria-label={`Move line ${i+1} earlier`} onClick={() => moveLine(i, i-1)}>↑</button><button className="button" disabled={i === lines.length-1} aria-label={`Move line ${i+1} later`} onClick={() => moveLine(i, i+1)}>↓</button><button className="button" onClick={() => generateAudio(line.id)}>Generate this line</button></div></div>)}</fieldset>}</div>
      {script && <div className="playback-section"><p className="control-note">RTL preserves model order. LTR uses a layout fallback. Correct any unusual layout above.</p>{issues.length > 0 && <p className="control-note" role="status">{issues[0]}{issues.length > 1 ? ` (${issues.length} lines need attention.)` : ""}</p>}<div className="action-row"><button className="button" disabled={!!busy} onClick={addLine}>Add dialogue</button><button className="button" onClick={() => download(script, "dialogue.json")}>Download JSON</button><button className="button primary" disabled={!!busy || !!issues.length} onClick={() => generateAudio()}>Generate audio</button></div>{audio && <div className="audio-result"><audio ref={player} controls src={audio} /><a className="button" href={audio} download="dialogue.wav">Download WAV</a></div>}</div>}</section></div>
      <div aria-live="polite">{busy && <p className="notice">{busy}</p>}{error && <p role="alert" className="notice error">{error}</p>}</div><footer className="reader-footer"><span>PNG, JPEG or WebP · 10 MB per image · Up to 10 images</span><span>Installed Windows voices · Local proof of concept</span></footer>
    </main>
  </div>;
}
