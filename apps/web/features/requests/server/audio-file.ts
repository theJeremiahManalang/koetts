import "server-only";
import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { lstat, open, realpath, type FileHandle } from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";

const verified = new Map<string, true>();

async function verifyOpenedArtifact(handle: FileHandle, checksum: string) {
  const before = await handle.stat({ bigint: true });
  if (!before.isFile() || before.size > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error("Invalid artifact");
  const identity = [checksum, before.dev, before.ino, before.size, before.mtimeNs, before.ctimeNs].join(":");
  if (process.platform !== "win32" && verified.has(identity)) return Number(before.size);
  const hash = createHash("sha256");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  let position = 0;
  while (true) {
    const { bytesRead } = await handle.read(buffer, 0, buffer.length, position);
    if (!bytesRead) break;
    hash.update(buffer.subarray(0, bytesRead));
    position += bytesRead;
  }
  const after = await handle.stat({ bigint: true });
  const afterIdentity = [checksum, after.dev, after.ino, after.size, after.mtimeNs, after.ctimeNs].join(":");
  if (identity !== afterIdentity || hash.digest("hex") !== checksum) throw new Error("Artifact integrity check failed");
  if (process.platform !== "win32") {
    if (verified.size >= 1000) verified.delete(verified.keys().next().value!);
    verified.set(identity, true);
  }
  return Number(before.size);
}

/** Serve only immutable artifact files; caller must authorize the selected artifact. */
export async function serveAudioFile(root: string, candidate: string, request: Request): Promise<Response> {
  const artifacts = await realpath(path.join(root, "shared-artifacts"));
  const target = path.resolve(candidate);
  if (await realpath(path.dirname(target)) !== artifacts || !/^[a-f0-9]{64}$/.test(path.basename(target))) throw new Error("Invalid artifact");
  const entry = await lstat(target);
  if (!entry.isFile() || entry.isSymbolicLink()) throw new Error("Invalid artifact");
  const handle = await open(target, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
  try {
    // Verify and stream the same open descriptor, even if the path is replaced.
    const size = await verifyOpenedArtifact(handle, path.basename(target));
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
