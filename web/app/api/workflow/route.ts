import { mkdir, readdir, writeFile, rm } from "node:fs/promises";
import path from "node:path";
import { dataRoot, id, validId, sameOrigin, jsonFile, launch } from "../../../lib/workflow";
import { python } from "../../../lib/python";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function limitedRequest(request: Request) {
  const limit = request.headers.get("content-type")?.startsWith("multipart/form-data") ? 128 * 1024 * 1024 : 5_000_000;
  if (Number(request.headers.get("content-length") || 0) > limit) throw new Error("Request exceeds the upload limit.");
  const reader = request.body?.getReader();
  if (!reader) throw new Error("Request body is empty.");
  const chunks: Uint8Array[] = []; let size = 0;
  while (true) {
    const { done, value } = await reader.read(); if (done) break;
    size += value.byteLength;
    if (size > limit) { await reader.cancel(); throw new Error("Request exceeds the upload limit."); }
    chunks.push(value);
  }
  return new Request(request.url, { method: "POST", headers: request.headers, body: Buffer.concat(chunks) });
}

export async function GET(request: Request) {
  try {
    sameOrigin(request);
    const url = new URL(request.url);
    if (url.searchParams.has("job")) return Response.json(await jsonFile(path.join(dataRoot, "jobs", validId(url.searchParams.get("job")!) + ".json")));
    if (url.searchParams.has("project")) {
      const { stdout } = await python("web_workflow.py", ["snapshot", validId(url.searchParams.get("project")!)]);
      return Response.json(JSON.parse(stdout));
    }
    await mkdir(path.join(dataRoot, "projects"), { recursive: true });
    const projects = [];
    for (const name of await readdir(path.join(dataRoot, "projects"))) {
      if (!/^[a-f0-9]{32}$/.test(name)) continue;
      try { const p = await jsonFile(path.join(dataRoot, "projects", name, "project.json")); projects.push({ id: name, name: p.chapter_id, scenes: p.scenes.length }); } catch { /* incomplete import */ }
    }
    return Response.json({ projects, has_api_key: !!process.env.GEMINI_API_KEY });
  } catch { return Response.json({ error: "Could not load this workspace. A job may still be running; try reloading shortly." }, { status: 409 }); }
}

export async function POST(request: Request) {
  let staging: string | undefined;
  try {
    sameOrigin(request);
    // Custom header prevents simple cross-origin form submissions.
    if (request.headers.get("x-manga-workflow") !== "1") return Response.json({ error: "Invalid request." }, { status: 403 });
    if (Number(request.headers.get("content-length") || 0) > 128 * 1024 * 1024) return Response.json({ error: "Upload limit is 128 MB." }, { status: 413 });
    request = await limitedRequest(request);
    const job = id();
    if (request.headers.get("content-type")?.startsWith("multipart/form-data")) {
      const form = await request.formData();
      const action = String(form.get("action") || "create");
      const project = action === "create" ? id() : validId(String(form.get("project")));
      const mode = String(form.get("mode") || "images");
      if (!["create", "cast-import"].includes(action) || !["images", "chapter", "restore"].includes(mode)) throw new Error("Invalid upload action.");
      const images = form.getAll("images");
      const direction = String(form.get("direction") || "rtl");
      if (!["rtl", "ltr"].includes(direction)) throw new Error("Invalid reading direction.");
      const files = [...images, form.get("chapter"), form.get("cast")].filter(v => v instanceof File) as File[];
      if (files.reduce((n, f) => n + f.size, 0) > 128 * 1024 * 1024) throw new Error("Upload limit is 128 MB.");
      if (action === "create" && mode === "images" && (!images.length || images.length > 10 || images.some(f => !(f instanceof File) || !["image/png", "image/jpeg", "image/webp"].includes(f.type) || !f.size || f.size > 10 * 1024 * 1024))) throw new Error("Choose 1–10 PNG, JPEG or WebP images, up to 10 MB each.");
      if (action === "create" && mode !== "images" && !(form.get("chapter") instanceof File)) throw new Error("Choose a chapter or project ZIP.");
      if (action === "cast-import" && !(form.get("cast") instanceof File)) throw new Error("Choose a cast reference ZIP.");
      staging = path.join(dataRoot, "uploads", job);
      await mkdir(staging, { recursive: true });
      const names = [];
      for (const [i, file] of images.entries()) {
        if (!(file instanceof File)) throw new Error("Invalid image.");
        const name = `${i}.png`; names.push(name); await writeFile(path.join(staging, name), Buffer.from(await file.arrayBuffer()));
      }
      for (const field of ["chapter", "cast"]) {
        const file = form.get(field);
        if (file instanceof File) { if (!file.size || !file.name.toLowerCase().endsWith(".zip")) throw new Error("Reference and project bundles must be ZIP files."); await writeFile(path.join(staging, field + ".zip"), Buffer.from(await file.arrayBuffer())); }
      }
      return Response.json(await launch(project, job, { action, mode, direction, images: names, revision: form.get("revision") }), { status: 202 });
    }
    if (!request.headers.get("content-type")?.startsWith("application/json")) throw new Error("Expected JSON.");
    const text = await request.text();
    if (text.length > 5_000_000) throw new Error("Review request is too large.");
    const payload = JSON.parse(text);
    if (!["cast-create", "plan", "proposal", "cast", "sources", "script", "settings", "narration", "take", "inspect", "render", "export", "bundle"].includes(payload.action)) throw new Error("Unknown action.");
    return Response.json(await launch(validId(payload.project), job, payload), { status: 202 });
  } catch (error) {
    if (staging) await rm(staging, { recursive: true, force: true });
    return Response.json({ error: error instanceof Error ? error.message : "Request failed." }, { status: 400 });
  }
}
