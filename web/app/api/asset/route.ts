import { requireAdmin } from "../../../lib/require-admin";
import { readFile, realpath } from "node:fs/promises";
import path from "node:path";
import { dataRoot, validId, sameOrigin } from "../../../lib/workflow";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  const denied = await requireAdmin(request); if (denied) return denied;
  if (process.env.MANGA_FRONTEND_ONLY === "1") return Response.json({ error: "Processing is available only in the local studio." }, { status: 503 });
  try {
    sameOrigin(request);
    const url = new URL(request.url), project = validId(url.searchParams.get("project") || "");
    const relative = url.searchParams.get("path") || "";
    const bundle = relative === "bundle.zip";
    if (!bundle && (!/^(input|originals|references|takes|exports)\//.test(relative) || relative.includes("..") || relative.includes("\\") || relative.includes(":"))) throw new Error();
    const base = await realpath(bundle ? path.join(dataRoot, "downloads") : path.join(dataRoot, "projects", project));
    const target = await realpath(path.join(base, bundle ? project + ".zip" : relative));
    if (!target.startsWith(base + path.sep)) throw new Error();
    const types: Record<string, string> = { ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".wav": "audio/wav", ".mp3": "audio/mpeg", ".json": "application/json", ".zip": "application/zip" };
    const mime = types[path.extname(target).toLowerCase()];
    if (!mime) throw new Error();
    const bytes = await readFile(target);
    const headers: Record<string, string> = { "Content-Type": mime, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Accept-Ranges": "bytes", ...(url.searchParams.has("download") ? { "Content-Disposition": `attachment; filename="${bundle ? "reviewed-project.zip" : path.basename(target).replace(/[^a-zA-Z0-9._-]/g, "_")}"` } : {}) };
    const range = request.headers.get("range");
    if (range) {
      const match = /^bytes=(\d*)-(\d*)$/.exec(range);
      if (!match || (!match[1] && !match[2])) return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${bytes.length}` } });
      const start = match[1] ? Number(match[1]) : Math.max(0, bytes.length - Number(match[2]));
      const end = match[1] && match[2] ? Math.min(Number(match[2]), bytes.length - 1) : bytes.length - 1;
      if (start > end || start >= bytes.length) return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${bytes.length}` } });
      return new Response(bytes.subarray(start, end + 1), { status: 206, headers: { ...headers, "Content-Range": `bytes ${start}-${end}/${bytes.length}`, "Content-Length": String(end - start + 1) } });
    }
    return new Response(bytes, { headers: { ...headers, "Content-Length": String(bytes.length) } });
  } catch { return Response.json({ error: "Asset not available." }, { status: 404 }); }
}
