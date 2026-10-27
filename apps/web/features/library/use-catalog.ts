"use client";

import { useEffect, useState } from "react";
import { useAuth } from "../identity/auth-provider";

export type PublishedChapter = { work_id: string; manga_id: string; title: string; chapter: number; publication_id: string };
export type PublishedManga = { id: string; title: string; chapters: PublishedChapter[] };

export function groupCatalog(chapters: PublishedChapter[]): PublishedManga[] {
  const groups = new Map<string, PublishedManga>();
  for (const chapter of chapters) {
    let manga = groups.get(chapter.manga_id);
    if (!manga) { manga = { id: chapter.manga_id, title: chapter.title, chapters: [] }; groups.set(manga.id, manga); }
    manga.chapters.push(chapter);
  }
  return Array.from(groups.values(), manga => ({ ...manga, chapters: [...manga.chapters].sort((a, b) => a.chapter - b.chapter) }));
}

export function useCatalog() {
  const { user, authorizationReady, loading: authLoading } = useAuth();
  const [chapters, setChapters] = useState<PublishedChapter[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!user || !authorizationReady) return;
    let active = true;
    setLoading(true); setError("");
    void fetch("/api/shared/catalog", { cache: "no-store" }).then(async response => {
      if (!response.ok) throw new Error();
      const data = await response.json() as { chapters: PublishedChapter[] };
      if (!Array.isArray(data.chapters)) throw new Error();
      return data.chapters;
    }).then(data => { if (active) setChapters(data); })
      .catch(() => { if (active) setError("The published catalog is unavailable. Please try again later."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [user?.uid, authorizationReady]);
  return { chapters: user && authorizationReady ? chapters : [], loading: authLoading || (!!user && (!authorizationReady || loading)), error, signedIn: !!user };
}
