import { requireAdmin } from "../../../features/identity/require-admin";
import { python } from "../../../lib/python";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

export const runtime = "nodejs";
const state = globalThis as typeof globalThis & { mangaOcrBusy?: boolean };

export async function POST(request: Request) {
  const denied = await requireAdmin(request); if (denied) return denied;
  if (process.env.MANGA_FRONTEND_ONLY === "1") return Response.json({ error: "Processing is available only in the local studio." }, { status: 503 });
  if (state.mangaOcrBusy) return Response.json({ error: "Another panel is being processed. Please try again shortly." }, { status: 429 });
  if (Number(request.headers.get("content-length")) > 11 * 1024 * 1024) return Response.json({ error: "Image must be 10 MB or smaller." }, { status: 413 });
  let directory: string | undefined;
  state.mangaOcrBusy = true;
  try {
    const data = await request.formData();
    const file = data.get("image");
    if (data.get("model") !== "magi") return Response.json({ error: "Select MAGI, the available text recognition model." }, { status: 400 });
    if (!(file instanceof File) || !["image/png", "image/jpeg", "image/webp"].includes(file.type) || !file.size || file.size > 10 * 1024 * 1024) {
      return Response.json({ error: "Choose a PNG, JPEG or WebP image up to 10 MB." }, { status: 400 });
    }
    directory = await mkdtemp(path.join(tmpdir(), "manga-ocr-"));
    const input = path.join(directory, "panel");
    await writeFile(input, Buffer.from(await file.arrayBuffer()));
    const { stdout } = await python("manga_worker.extract", [input]);
    const result = JSON.parse(stdout);
    if (!Array.isArray(result.texts) || !result.texts.every((value: unknown) => typeof value === "string")) throw new Error("Invalid OCR response");
    return Response.json({ texts: result.texts });
  } catch (error) {
    console.error("OCR failed:", error);
    return Response.json({ error: "Could not extract text. Check that the image is valid and the Python model dependencies are installed. See the server terminal for details." }, { status: 500 });
  } finally {
    try { if (directory) await rm(directory, { recursive: true, force: true }); }
    finally { state.mangaOcrBusy = false; }
  }
}
