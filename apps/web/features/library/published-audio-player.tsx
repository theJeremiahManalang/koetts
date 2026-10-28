"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../identity/auth-provider";

export function PublishedAudioPlayer({ workId }: { workId: string }) {
  const { user, authorizationReady } = useAuth();
  const ready = useRef(false);
  ready.current = !!user && authorizationReady;
  const [url, setUrl] = useState("");
  const urlRef = useRef("");
  urlRef.current = url;
  const [error, setError] = useState("");
  const audio = useRef<HTMLAudioElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generation = useRef(0);
  const inFlight = useRef<number | null>(null);
  const retried = useRef(false);
  const resume = useRef<{ time: number; playing: boolean } | null>(null);

  const refresh = useCallback(async () => {
    if (!ready.current) return;
    const current = generation.current;
    if (inFlight.current === current) return;
    inFlight.current = current;
    try {
      const response = await fetch(`/api/shared/playback?work=${encodeURIComponent(workId)}`, { cache: "no-store" });
      if (!response.ok) throw new Error();
      const result = await response.json() as { url: string; expires_in: number };
      if (typeof result.url !== "string" || !result.url.startsWith("/api/shared/audio?") ||
          typeof result.expires_in !== "number" || !Number.isFinite(result.expires_in) || result.expires_in <= 0) throw new Error();
      if (generation.current !== current) return;
      if (audio.current && urlRef.current) resume.current = { time: audio.current.currentTime, playing: !audio.current.paused };
      setError(""); setUrl(result.url);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => { void refresh(); }, Math.max(1000, (result.expires_in - 30) * 1000));
    } catch {
      if (generation.current === current) setError("Audio could not be loaded. Please try again.");
    } finally {
      if (inFlight.current === current) inFlight.current = null;
    }
  }, [workId]);

  useEffect(() => {
    generation.current += 1;
    if (ready.current) void refresh();
    return () => { generation.current += 1; if (timer.current) clearTimeout(timer.current); };
  }, [refresh, authorizationReady, user?.uid]);

  return <div className="published-audio-player">
    {!url && !error && <p role="status">Loading audio…</p>}
    {url && <audio ref={audio} controls preload="metadata" src={url} aria-label="Published chapter audio"
      onLoadedMetadata={() => {
        retried.current = false;
        const saved = resume.current;
        resume.current = null;
        if (!saved || !audio.current) return;
        const duration = audio.current.duration;
        audio.current.currentTime = Number.isFinite(duration) ? Math.min(saved.time, duration) : saved.time;
        if (saved.playing) void audio.current.play().catch(() => setError("Press play to continue listening."));
      }}
      onError={() => { if (retried.current) { setError("Audio could not be played. Please try again."); return; } retried.current = true; void refresh(); }} />}
    {error && <p role="alert">{error} <button type="button" onClick={() => { retried.current = false; void refresh(); }}>Retry</button></p>}
  </div>;
}
