import "server-only";
import { constants } from "node:fs";
import { open, realpath } from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";

/** Serve only immutable artifact files; caller must authorize the selected artifact. */
export async function serveAudioFile(root: string, candidate: string, request: Request): Promise<Response> {
  const artifacts = await realpath(path.join(root, "shared-artifacts"));
  const target = await realpath(candidate);
  if (path.dirname(target) !== artifacts || !/^[a-f0-9]{64}$/.test(path.basename(target))) throw new Error("Invalid artifact");
  const handle = await open(target, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
  try {
    const stat = await handle.stat();
    if (!stat.isFile() || !Number.isSafeInteger(stat.size)) throw new Error("Invalid artifact");
    const size = stat.size;
    const headers: Record<string, string> = {
      "Content-Type": "audio/wav", "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Accept-Ranges": "bytes",
    };
    const range = request.headers.get("range");
    let start = 0, end = size - 1;
    if (range) {
      const match = /^bytes=(\d*)-(\d*)$/.exec(range);
      if (!match || (!match[1] && !match[2]) || size === 0) {
        await handle.close();
        return new Response(null, { status: 416, headers: { ...headers, "Content-Range": `bytes */${size}` } });
      }
      const first = match[1] ? Number(match[1]) : null;
      const last = match[2] ? Number(match[2]) : null;
      if ((first !== null && !Number.isSafeInteger(first)) || (last !== null && !Number.isSafeInteger(last)) ||
          (first === null && (!last || last < 1))) {
        await handle.close();
        return new Response(null, { status: 416, headers: { ...headers, "Content-Range": `bytes */${size}` } });
      }
      start = first === null ? Math.max(0, size - last!) : first;
      end = first !== null && last !== null ? Math.min(last, size - 1) : size - 1;
      if (start >= size || start > end) {
        await handle.close();
        return new Response(null, { status: 416, headers: { ...headers, "Content-Range": `bytes */${size}` } });
      }
      headers["Content-Range"] = `bytes ${start}-${end}/${size}`;
    }
    headers["Content-Length"] = String(size === 0 ? 0 : end - start + 1);
    if (size === 0) { await handle.close(); return new Response(null, { headers }); }
    const stream = handle.createReadStream({ start, end, autoClose: true });
    return new Response(Readable.toWeb(stream) as ReadableStream<Uint8Array>, { status: range ? 206 : 200, headers });
  } catch (error) {
    await handle.close();
    throw error;
  }
}
