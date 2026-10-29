import { createHash } from "node:crypto";
import { requireAdmin, trustedSessionRequest } from "../../../features/identity/require-admin";
import { id, validId, validIdempotencyKey } from "../../../lib/workflow";
import { hostedMode, privateJson, PrivateApiError } from "../../../lib/private-api";
import { python } from "../../../lib/python";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

export const runtime = "nodejs";
const MAX_BODY_BYTES = 11 * 1024 * 1024;
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
const state = globalThis as typeof globalThis & { mangaOcrBusy?: boolean };

async function boundedRequest(request: Request): Promise<Request> {
  const declared = request.headers.get("content-length");
  if (declared !== null && (!/^(?:0|[1-9][0-9]*)$/.test(declared) || Number(declared) > MAX_BODY_BYTES)) {
    throw new RequestLimitError();
  }
  const reader = request.body?.getReader();
  if (!reader) throw new Error("Choose an image first.");
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY_BYTES) {
      await reader.cancel();
      throw new RequestLimitError();
    }
    chunks.push(value);
  }
  return new Request(request.url, {
    method: "POST",
    headers: request.headers,
    body: Buffer.concat(chunks),
  });
}

class RequestLimitError extends Error {}

function uploadToken(key: string): string {
  if (/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(key)) {
    return key.replaceAll("-", "").toLowerCase();
  }
  return createHash("sha256").update(key).digest("hex").slice(0, 32);
}

async function enqueueHostedOcr(request: Request): Promise<Response> {
  if (!trustedSessionRequest(request)) return Response.json({ error: "Invalid origin." }, { status: 403 });
  const key = validIdempotencyKey(request.headers.get("idempotency-key"));
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("multipart/form-data")) {
    return Response.json({ error: "Choose an image first." }, { status: 415 });
  }

  const bounded = await boundedRequest(request);
  const form = await bounded.formData();
  const images = form.getAll("image");
  const image = images.length === 1 ? images[0] : null;
  const models = form.getAll("model");
  if (models.length !== 1 || models[0] !== "magi") {
    return Response.json({ error: "Select MAGI, the available text recognition model." }, { status: 400 });
  }
  if (!(image instanceof File) || !ALLOWED_IMAGE_TYPES.has(image.type) || !image.size || image.size > MAX_IMAGE_BYTES) {
    return Response.json({ error: "Choose a PNG, JPEG or WebP image up to 10 MB." }, { status: 400 });
  }

  const projectValue = form.get("project");
  const project = typeof projectValue === "string" && /^[a-f0-9]{32}$/.test(projectValue)
    ? validId(projectValue)
    : id();
  const revisionValue = form.get("revision");
  if (revisionValue !== null && (typeof revisionValue !== "string" || revisionValue.length > 200 || /[\u0000-\u001f\u007f]/.test(revisionValue))) {
    return Response.json({ error: "The selected project revision is invalid." }, { status: 400 });
  }
  const token = uploadToken(key);
  await privateJson(request, `/uploads/${token}/panel.png`, {
    method: "PUT",
    headers: { "Content-Type": "application/octet-stream" },
    body: Buffer.from(await image.arrayBuffer()),
  });
  const payload: Record<string, string> = { action: "ocr", project, upload_token: token };
  if (typeof revisionValue === "string" && revisionValue) payload.revision = revisionValue;
  const operation = await privateJson(request, "/operations", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": key },
    body: JSON.stringify(payload),
  });
  return Response.json(operation, { status: 202, headers: { "Cache-Control": "private, no-store" } });
}

export async function POST(request: Request) {
  const denied = await requireAdmin(request); if (denied) return denied;
  if (process.env.MANGA_FRONTEND_ONLY === "1") return Response.json({ error: "Processing is available only in the local studio." }, { status: 503 });
  try {
    if (hostedMode()) return await enqueueHostedOcr(request);
  } catch (error) {
    if (error instanceof RequestLimitError) return Response.json({ error: "Image request exceeds the upload limit." }, { status: 413 });
    if (error instanceof PrivateApiError) return Response.json({ error: error.message, code: error.code }, { status: error.status });
    return Response.json({ error: error instanceof Error ? error.message : "Could not enqueue text extraction." }, { status: 400 });
  }

  if (state.mangaOcrBusy) return Response.json({ error: "Another panel is being processed. Please try again shortly." }, { status: 429 });
  if (Number(request.headers.get("content-length")) > MAX_BODY_BYTES) return Response.json({ error: "Image must be 10 MB or smaller." }, { status: 413 });
  let directory: string | undefined;
  state.mangaOcrBusy = true;
  try {
    const data = await request.formData();
    const file = data.get("image");
    if (data.getAll("model").length !== 1 || data.get("model") !== "magi") return Response.json({ error: "Select MAGI, the available text recognition model." }, { status: 400 });
    if (!(file instanceof File) || !ALLOWED_IMAGE_TYPES.has(file.type) || !file.size || file.size > MAX_IMAGE_BYTES) {
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
