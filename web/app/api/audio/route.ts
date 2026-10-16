import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { python } from "../../../lib/python";
export const runtime = "nodejs";
const state = globalThis as typeof globalThis & { mangaAudioBusy?: boolean };
export async function POST(request: Request) {
  if (state.mangaAudioBusy) return Response.json({ error: "Audio generation is already running." }, { status: 429 });
  if (Number(request.headers.get("content-length")) > 2_000_000) return Response.json({ error: "Script is too large." }, { status: 413 });
  state.mangaAudioBusy = true;
  let directory: string | undefined;
  try {
    const text = await request.text();
    if (Buffer.byteLength(text) > 2_000_000) return Response.json({ error: "Script is too large." }, { status: 413 });
    JSON.parse(text);
    directory = await mkdtemp(path.join(tmpdir(), "manga-audio-"));
    const input = path.join(directory, "script.json"), output = path.join(directory, "chapter.wav");
    await writeFile(input, text);
    await python("web_audio.py", [input, output]);
    return new Response(await readFile(output), { headers: { "Content-Type": "audio/wav", "Content-Disposition": 'attachment; filename="dialogue.wav"', "Cache-Control": "no-store" } });
  } catch (error) {
    console.error("Audio failed:", error);
    return Response.json({ error: "Audio could not be generated. Check included text, speaker assignments and available voices. Details are in the server terminal." }, { status: 400 });
  } finally {
    try { if (directory) await rm(directory, { recursive: true, force: true }); }
    finally { state.mangaAudioBusy = false; }
  }
}
