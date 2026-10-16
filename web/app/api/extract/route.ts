import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { python } from "../../../lib/python";
export const runtime = "nodejs";
const state = globalThis as typeof globalThis & { mangaAnalysisBusy?: boolean };
export async function POST(request: Request) {
  if (state.mangaAnalysisBusy) return Response.json({ error: "Another analysis is running. Try again shortly." }, { status: 429 });
  if (Number(request.headers.get("content-length")) > 51 * 1024 * 1024) return Response.json({ error: "Uploads must total 50 MB or less." }, { status: 413 });
  let directory: string | undefined;
  state.mangaAnalysisBusy = true;
  try {
    const form = await request.formData();
    const images = form.getAll("images");
    const direction = form.get("direction");
    if (!["rtl", "ltr"].includes(String(direction)) || !images.length || images.length > 10 || images.some(file => !(file instanceof File) || !["image/png", "image/jpeg", "image/webp"].includes(file.type) || !file.size || file.size > 10 * 1024 * 1024)) {
      return Response.json({ error: "Choose a reading direction and 1-10 PNG, JPEG or WebP images, each up to 10 MB." }, { status: 400 });
    }
    const files = images as File[];
    if (files.reduce((n, f) => n + f.size, 0) > 50 * 1024 * 1024) return Response.json({ error: "Uploads must total 50 MB or less." }, { status: 413 });
    directory = await mkdtemp(path.join(tmpdir(), "manga-analysis-"));
    const entries = [];
    for (const [index, file] of files.entries()) {
      const input = path.join(directory, `${index}.image`);
      await writeFile(input, Buffer.from(await file.arrayBuffer()));
      entries.push({ path: input, name: file.name });
    }
    const manifest = path.join(directory, "manifest.json");
    await writeFile(manifest, JSON.stringify({ direction, images: entries }));
    const { stdout } = await python("web_analyze.py", [manifest]);
    return Response.json(JSON.parse(stdout));
  } catch (error) {
    console.error("Analysis failed:", error);
    return Response.json({ error: "Analysis failed. Check the image and installed Python model dependencies; details are in the server terminal." }, { status: 500 });
  } finally {
    try { if (directory) await rm(directory, { recursive: true, force: true }); }
    finally { state.mangaAnalysisBusy = false; }
  }
}
