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
  const [catalog, setCatalog] = useState<{ uid: string | null; chapters: PublishedChapter[]; loaded: boolean; error: string }>({
    uid: null, chapters: [], loaded: false, error: "",
  });
  useEffect(() => {
    if (!user || !authorizationReady) return;
    let active = true;
    const uid = user.uid;
    setCatalog(previous => previous.uid === uid ? { ...previous, error: "" } : { uid, chapters: [], loaded: false, error: "" });
    void fetch("/api/shared/catalog", { cache: "no-store" }).then(async response => {
      if (!response.ok) throw new Error();
      const data = await response.json() as { chapters: PublishedChapter[] };
      if (!Array.isArray(data.chapters)) throw new Error();
      return data.chapters;
    }).then(data => { if (active) setCatalog({ uid, chapters: data, loaded: true, error: "" }); })
      .catch(() => { if (active) setCatalog(previous => ({ ...previous, loaded: true, error: "The published catalog is unavailable. Please try again later." })); });
    return () => { active = false; };
  }, [user?.uid, authorizationReady]);
  const sameUser = !!user && catalog.uid === user.uid;
  return {
    chapters: sameUser ? catalog.chapters : [],
    loading: authLoading || (!!user && (!sameUser || !catalog.loaded)),
    error: sameUser ? catalog.error : "", signedIn: !!user,
  };
}
