"use client";

import { useEffect, useRef, useState } from "react";
import { Toaster, toast } from "sonner";

const sample = [
  { scene: "Mika stands beneath an umbrella on a quiet street while rain falls around her.", speaker: "Mika", dialogue: "You're finally here.", sound: "Rain falling", short: "Mika waits in the rain.", detail: "On a quiet, rain-soaked street, Mika stands beneath her umbrella. She looks up as someone approaches through the rain." },
  { scene: "Ren stops beneath the streetlight, catching his breath as he looks toward Mika.", speaker: "Ren", dialogue: "I promised I would come, didn't I?", sound: "Footsteps on wet pavement", short: "Ren arrives beneath a streetlight.", detail: "Ren comes to a stop in the pool of light cast by a streetlamp. Breathless from the journey, he looks across the wet pavement toward Mika." },
  { scene: "Mika lifts the umbrella, making room for Ren as they begin walking together.", speaker: "Mika", dialogue: "Then let's go home.", sound: "Rain tapping on the umbrella", short: "Mika and Ren walk home together.", detail: "Mika raises her umbrella and moves a little closer to Ren. Sheltered together beneath it, they turn down the quiet street and begin the walk home." },
];
const levels = ["Concise", "Balanced", "Detailed"] as const;
type Level = typeof levels[number];

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [zoom, setZoom] = useState(100);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [texts, setTexts] = useState<string[] | null>(null);

  const [index, setIndex] = useState(0);
  const [level, setLevel] = useState<Level>("Balanced");
  const [speaking, setSpeaking] = useState(false);
  const [speechAvailable, setSpeechAvailable] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const panel = sample[index];
  const scene = level === "Concise" ? panel.short : level === "Detailed" ? panel.detail : panel.scene;
  const count = file ? 1 : sample.length;
  const outputJson = texts === null ? "" : JSON.stringify({ output: texts }, null, 2);

  useEffect(() => {
    setSpeechAvailable("speechSynthesis" in window);
    return () => { if ("speechSynthesis" in window) window.speechSynthesis.cancel(); };
  }, []);
  useEffect(() => {
    if (!file) { setPreview(""); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function stop() {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setSpeaking(false);
  }
  function listen() {
    if (speaking) { stop(); return; }
    if (!speechAvailable) return;
    const utterance = new SpeechSynthesisUtterance(file ? (texts ?? []).join(". ") : `${scene} ${panel.speaker} says: ${panel.dialogue} ${panel.sound}.`);
    utterance.rate = 0.9;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => { setSpeaking(false); setError("Playback could not start. Please try again."); };
    window.speechSynthesis.speak(utterance);
    setSpeaking(true);
  }
  function selectFile(selected: File | null) {
    if (!selected) return;
    if (selected.size > 10 * 1024 * 1024 || !["image/png", "image/jpeg", "image/webp"].includes(selected.type)) {
      setError("Choose a PNG, JPEG or WebP image up to 10 MB."); return;
    }
    stop(); setFile(selected); setZoom(100); setIndex(0); setTexts(null); setError("");
  }
  function removePanel() {
    if (busy) return;
    stop(); setFile(null); setPreview(""); setZoom(100); setIndex(0);
    setTexts(null); setError("");
  }
  async function extract() {
    if (!file || busy) return;
    stop(); setBusy(true); setError(""); setTexts(null);
    try {
      const body = new FormData();
      body.append("image", file); body.append("model", "magi");
      const response = await fetch("/api/extract", { method: "POST", body });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Extraction failed. Please try again.");
      setTexts(result.texts);
      if (result.texts.length) toast.success("Panel extracted", { description: "Your dialogue is ready to read, listen to, or copy." });
      else toast.info("Extraction complete", { description: "No text was detected. Try a clearer panel." });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Extraction failed.";
      setError(message); toast.error("Could not extract panel", { description: message });
    }
    finally { setBusy(false); }
  }
  async function copyOutput() {
    if (texts === null || busy) return;
    try { await navigator.clipboard.writeText(outputJson); toast.success("JSON copied to clipboard"); }
    catch { toast.error("Could not copy JSON", { description: "Check clipboard permissions in your browser and try again." }); }
  }

  return (
    <div className={`app-shell${file ? "" : " is-empty"}`}>
      <Toaster position="top-right" closeButton theme="light" toastOptions={{ style: { background: "var(--surface)", color: "var(--ink)", border: "1px solid var(--line)" } }} />
      <header className="site-header">
        <a className="brand" href="/" aria-label="Manga Reader home"><span className="brand-icon" aria-hidden="true">▥</span><span><span className="eyebrow">A STORY IN EVERY PANEL</span><span className="brand-title">Manga Reader<span className="brand-dot">.</span></span></span></a>
        <button className="button upload-button" disabled={busy} onClick={() => input.current?.click()}><span aria-hidden="true">＋</span> Upload panel</button>
        <input ref={input} className="visually-hidden" type="file" aria-label="Upload manga panel" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={event => { selectFile(event.target.files?.[0] ?? null); event.target.value = ""; }} />
      </header>
      <main>
        <div className="reader-heading"><div><div className="eyebrow">YOUR READING SPACE</div><h1>A little closer to the story.</h1><p>Take it one panel at a time. Read, listen, and linger.</p></div><span className="mode-label"><span className="status-dot" />{file ? "Your panel" : "Sample story"}</span></div>
        <div className="reader-grid">
          <section className="art-card" aria-label="Manga artwork">
            <div className="art-toolbar"><span>{file ? "UPLOADED PANEL" : "THE WAY HOME"}</span>{file ? <div className="panel-actions"><button className="button" disabled={busy} onClick={() => input.current?.click()}>Replace</button><button className="button close-panel" disabled={busy} onClick={removePanel} aria-label="Remove uploaded panel" title="Remove panel">×</button></div> : <span>0{index + 1} / 0{count}</span>}</div>
            <div key={preview} className={`art-stage ${preview ? "has-image" : ""}`} tabIndex={preview ? 0 : undefined} aria-label={preview ? "Manga image viewer. Scroll to explore the zoomed image." : undefined}>
              {preview ? <div className="image-canvas" style={{ width: `${zoom}%`, height: `${zoom}%` }}><img src={preview} alt={file?.name || "Uploaded manga panel"} draggable={false} /></div> : <div className="art-placeholder"><span className="panel-symbol" aria-hidden="true"><i /><i /><i /></span><h2>Panel {index + 1}</h2><p>Your manga artwork belongs here.</p><button className="text-button" onClick={() => input.current?.click()}>Upload a panel <span aria-hidden="true">↗</span></button></div>}
            </div>
            {preview && <div className="zoom-toolbar" role="group" aria-label="Image zoom"><button className="button" aria-label="Zoom out" disabled={zoom <= 50} onClick={() => setZoom(value => Math.max(50, value - 25))}>−</button><output aria-live="polite" aria-label="Zoom level">{zoom}%</output><button className="button" aria-label="Zoom in" disabled={zoom >= 300} onClick={() => setZoom(value => Math.min(300, value + 25))}>+</button><button className="button" onClick={() => setZoom(100)}>Fit</button><span>Scroll to explore</span></div>}
            <div className="art-caption"><span>{file ? file.name : "A quiet street. An unexpected reunion."}</span><span>{file ? "ORIGINAL" : "PREVIEW"}</span></div>
          </section>
          <section className="reading-card" aria-label="Panel narration">
            <div className="panel-meta"><span>Panel {index + 1} of {count}</span><span>{file ? "Uploaded image" : "Chapter 1"}</span></div>
            <div className="story-section"><h2 className="eyebrow">SCENE</h2><p>{file ? "Your uploaded panel is ready to explore. Extract its dialogue to read or listen." : scene}</p></div>
            <div className="story-section dialogue"><div className="dialogue-heading"><h2 className="eyebrow">DIALOGUE</h2><button className="button copy-json-button" onClick={copyOutput} disabled={texts === null || busy}>Copy JSON</button></div>{file ? <div aria-live="polite" aria-busy={busy}>{texts === null ? <p className="muted">{busy ? "Reading your panel…" : "The words in your panel will appear here."}</p> : texts.length ? texts.map((text, i) => <p key={i} className="extracted-line">{text}</p>) : <p className="muted">No text was detected. Try a clearer panel.</p>}<button className="button extract-button" disabled={busy} onClick={extract}>{busy ? "Extracting…" : texts === null ? "Extract dialogue" : "Extract again"}</button></div> : <><h3>{panel.speaker}</h3><p>“{panel.dialogue}”</p></>}</div>
            <div className="story-section"><h2 className="eyebrow">SOUND EFFECT</h2><p className="sound-line"><span aria-hidden="true">≋</span>{file ? "Sound effects aren't analyzed yet." : panel.sound}</p></div>
            <div className="playback-section"><fieldset disabled={!!file}><legend className="eyebrow">NARRATION DETAIL</legend><div className="segmented-control">{levels.map(item => <button key={item} aria-pressed={level === item} onClick={() => { stop(); setLevel(item); }}>{item}</button>)}</div></fieldset>{file && <p className="control-note">Uploaded panels play the extracted text as written.</p>}<div className="playback-controls"><button className="button" disabled={!!file || index === 0} onClick={() => { stop(); setIndex(index - 1); }}>← <span>Previous</span></button><button className="button primary" onClick={listen} disabled={!speechAvailable || busy || (!!file && !texts?.length)}><span aria-hidden="true">{speaking ? "■" : "▶"}</span> {speaking ? "Stop" : "Listen"}</button><button className="button" disabled={!!file || index === count - 1} onClick={() => { stop(); setIndex(index + 1); }}><span>Next</span> →</button></div><p className="listening-note">{speaking ? "Playing narration…" : !speechAvailable ? "Voice playback isn't available in this browser." : "Settle in. Let the story come to you."}</p></div>
          </section>
        </div>
        <div aria-live="polite">{busy && <p className="notice">Reading your panel. The first run can take several minutes.</p>}{error && <p role="alert" className="notice error">{error}</p>}</div>
        <footer className="reader-footer"><span>{file ? "PNG, JPEG or WebP · Up to 10 MB" : "Sample narration · Upload your own panel to begin"}</span><span>Made for a slower kind of reading.</span></footer>
      </main>
    </div>
  );
}
