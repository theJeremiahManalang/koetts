"use client";

import { useEffect, useState } from "react";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [texts, setTexts] = useState<string[] | null>(null);
  const [copyStatus, setCopyStatus] = useState("");
  const outputJson = texts === null ? "" : JSON.stringify({ output: texts }, null, 2);

  async function copyOutput() {
    try {
      await navigator.clipboard.writeText(outputJson);
      setCopyStatus("Copied!");
    } catch {
      setCopyStatus("Could not copy automatically. Select and copy the JSON below.");
    }
  }

  useEffect(() => {
    if (!file) { setPreview(""); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  async function extract() {
    if (!file || busy) return;
    setBusy(true); setError(""); setTexts(null); setCopyStatus("");
    try {
      const body = new FormData();
      body.append("image", file); body.append("model", "magi");
      const response = await fetch("/api/extract", { method: "POST", body });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Extraction failed. Please try again.");
      setTexts(result.texts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed.");
    } finally { setBusy(false); }
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-5 py-12">
      <header><h1 className="text-3xl font-bold">Manga text</h1><p className="mt-2 text-slate-600">Upload a panel, then click a model to extract its text.</p></header>
      <section className="space-y-5 rounded-xl border border-slate-200 bg-white p-6">
        <div><label className="mb-2 block font-semibold" htmlFor="panel">1. Upload your panel</label>
          <input id="panel" type="file" accept="image/png,image/jpeg,image/webp" disabled={busy}
            className="w-full text-sm file:mr-4 file:rounded-md file:border-0 file:bg-slate-100 file:px-4 file:py-2 disabled:opacity-50"
            onChange={(event) => {
              const selected = event.target.files?.[0] ?? null;
              setTexts(null); setError(""); setCopyStatus("");
              if (selected && (selected.size > 10 * 1024 * 1024 || !["image/png", "image/jpeg", "image/webp"].includes(selected.type))) {
                setFile(null); setError("Choose a PNG, JPEG or WebP image up to 10 MB."); return;
              }
              setFile(selected);
            }} />
          <p className="mt-2 text-xs text-slate-500">PNG, JPEG or WebP · Up to 10 MB</p>
        </div>
        {preview && <img src={preview} alt="Selected manga panel" className="mx-auto max-h-80 max-w-full rounded-md object-contain" />}
        <div><h2 className="mb-2 font-semibold">2. Click a model to extract</h2>
          <button onClick={extract} disabled={!file || busy} className="rounded-lg bg-slate-900 px-5 py-3 font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40">{busy ? "Extracting…" : "MAGI v3 · Extract text"}</button>
          <p className="mt-3 text-xs text-slate-500">Comic Text Detector is detection-only and cannot transcribe text.</p>
        </div>
      </section>
      <div aria-live="polite" aria-busy={busy}>
        {busy && <p className="text-sm text-slate-600">Reading your panel. The first run downloads the model and can take several minutes.</p>}
        {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{error}</p>}
        {texts !== null && <section className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Extracted text · JSON</h2>
            <button onClick={copyOutput} className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700">Copy JSON</button>
          </div>
          {copyStatus && <p role="status" className="mb-3 text-sm text-slate-600">{copyStatus}</p>}
          {!texts.length && <p className="mb-3 text-slate-500">No text was detected. Try a clearer panel.</p>}
          <pre tabIndex={0} aria-label="Extracted text as JSON" className="max-h-96 overflow-auto rounded-lg bg-slate-100 p-4 text-sm whitespace-pre-wrap break-words"><code>{outputJson}</code></pre>
        </section>}
      </div>
    </main>
  );
}
