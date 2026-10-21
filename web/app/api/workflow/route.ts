import { createHash } from "node:crypto";
import { requireAdmin } from "../../../lib/require-admin";
import { mkdir, readdir, writeFile, rm } from "node:fs/promises";
import path from "node:path";
import {
  dataRoot,
  dispatchQueued,
  enqueueOperation,
  id,
  jsonFile,
  operationByKey,
  operationStatus,
  sameOrigin,
  validId,
  validIdempotencyKey,
} from "../../../lib/workflow";
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
  const denied = await requireAdmin(request); if (denied) return denied;
  if (process.env.MANGA_FRONTEND_ONLY === "1") return Response.json({ error: "Processing is available only in the local studio." }, { status: 503 });
  try {
    sameOrigin(request);
    const url = new URL(request.url);
    if (url.searchParams.has("job")) {
      const jobId = validId(url.searchParams.get("job")!);
      await dispatchQueued();
      const operation = await operationStatus(jobId);
      if (operation) return Response.json(operation);
      return Response.json(await jsonFile(path.join(dataRoot, "jobs", jobId + ".json")));
    }
    if (url.searchParams.has("key")) {
      const key = validIdempotencyKey(url.searchParams.get("key"));
      await dispatchQueued();
      const operation = await operationByKey(key);
      return operation
        ? Response.json(operation)
        : Response.json({ error: "Operation was not found." }, { status: 404 });
    }
    if (url.searchParams.has("project")) {
      const { stdout } = await python("web_workflow.py", ["snapshot", validId(url.searchParams.get("project")!)]);
      return Response.json(JSON.parse(stdout));
    }
    await mkdir(path.join(dataRoot, "projects"), { recursive: true });
    const projects = [];
    for (const name of await readdir(path.join(dataRoot, "projects"))) {
      if (!/^[a-f0-9]{32}$/.test(name)) continue;
      try { const p = await jsonFile(path.join(dataRoot, "projects", name, "project.json")); projects.push({ id: name, name: p.title || p.chapter_id, scenes: p.scenes.length }); } catch { /* incomplete import */ }
    }
    return Response.json({ projects, has_api_key: !!process.env.GEMINI_API_KEY });
  } catch { return Response.json({ error: "Could not load this workspace. A job may still be running; try reloading shortly." }, { status: 409 }); }
}

export async function POST(request: Request) {
  const denied = await requireAdmin(request); if (denied) return denied;
  if (process.env.MANGA_FRONTEND_ONLY === "1") return Response.json({ error: "Processing is available only in the local studio." }, { status: 503 });
  let staging: string | undefined;
  let enqueueStarted = false;
  try {
    sameOrigin(request);
    // Custom header prevents simple cross-origin form submissions.
    if (request.headers.get("x-manga-workflow") !== "1") return Response.json({ error: "Invalid request." }, { status: 403 });
    const idempotencyKey = validIdempotencyKey(request.headers.get("idempotency-key"));
    if (Number(request.headers.get("content-length") || 0) > 128 * 1024 * 1024) return Response.json({ error: "Upload limit is 128 MB." }, { status: 413 });
    request = await limitedRequest(request);
    if (request.headers.get("content-type")?.startsWith("multipart/form-data")) {
      const form = await request.formData();
      const action = String(form.get("action") || "create");
      const project = action === "create" ? id() : validId(String(form.get("project")));
      const uploadToken = id();
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
      staging = path.join(dataRoot, "uploads", uploadToken);
      await mkdir(staging, { recursive: true });
      const names: string[] = [];
      const sourceHashes: string[] = [];
      for (const [i, file] of images.entries()) {
        if (!(file instanceof File)) throw new Error("Invalid image.");
        const name = `${i}.png`;
        const bytes = Buffer.from(await file.arrayBuffer());
        names.push(name);
        sourceHashes.push(createHash("sha256").update(bytes).digest("hex"));
        await writeFile(path.join(staging, name), bytes);
      }
      for (const field of ["chapter", "cast"]) {
        const file = form.get(field);
        if (file instanceof File) {
          if (!file.size || !file.name.toLowerCase().endsWith(".zip")) throw new Error("Reference and project bundles must be ZIP files.");
          const bytes = Buffer.from(await file.arrayBuffer());
          sourceHashes.push(createHash("sha256").update(bytes).digest("hex"));
          await writeFile(path.join(staging, field + ".zip"), bytes);
        }
      }
      enqueueStarted = true;
      const enqueued = await enqueueOperation({
        action,
        mode,
        direction,
        project,
        revision: form.get("revision") || null,
        images: names,
        upload_token: uploadToken,
        source_hashes: sourceHashes,
      }, idempotencyKey);
      if (enqueued.stored_upload_token !== uploadToken) {
        await rm(staging, { recursive: true, force: true });
      }
      staging = undefined;
      try { await dispatchQueued(); } catch { /* persisted work remains queued for polling recovery */ }
      return Response.json(enqueued.operation, { status: 202 });
    }
    if (!request.headers.get("content-type")?.startsWith("application/json")) throw new Error("Expected JSON.");
    const text = await request.text();
    if (text.length > 5_000_000) throw new Error("Review request is too large.");
    const payload = JSON.parse(text);
    if (!["rename", "cast-create", "plan", "proposal", "cast", "sources", "script", "script-batch", "sync-speakers", "settings", "narration", "take", "inspect", "render", "export", "bundle"].includes(payload.action)) throw new Error("Unknown action.");
    payload.project = validId(payload.project);
    const enqueued = await enqueueOperation(payload, idempotencyKey);
    try { await dispatchQueued(); } catch { /* persisted work remains queued for polling recovery */ }
    return Response.json(enqueued.operation, { status: 202 });
  } catch (error) {
    const code = typeof error === "object" && error && "code" in error ? String(error.code) : undefined;
    // An enqueue transport failure can follow a successful SQLite commit. Keep
    // its inputs for key-based recovery unless rejection proves no ownership.
    if (staging && (!enqueueStarted || code === "idempotency_conflict")) {
      await rm(staging, { recursive: true, force: true });
    }
    const status = code === "idempotency_conflict" ? 409 : 400;
    return Response.json({ error: error instanceof Error ? error.message : "Request failed.", code }, { status });
  }
}
