/** Browser-local demo requests; no shared request backend exists yet. */
export type MangaRequest = { id: string; mangaTitle: string; chapter: string; notes: string; status: string; createdAt: string };
export const samples: MangaRequest[] = [
  { id: "sample-echoes", mangaTitle: "Echoes of Tomorrow", chapter: "2", notes: "A narrated version of Static.", status: "PENDING", createdAt: "2026-10-20T02:00:00Z" },
  { id: "sample-garden", mangaTitle: "Moon Garden", chapter: "2", notes: "I'd love to listen to Moonflowers.", status: "PROCESSING", createdAt: "2026-10-19T02:00:00Z" },
];
