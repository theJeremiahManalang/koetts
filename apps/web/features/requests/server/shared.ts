import "server-only";
import { pythonJSON } from "../../../lib/python";
import { hostedMode, privateJson } from "../../../lib/private-api";

export const validSharedId = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{32}$/.test(value);
export const validRevision = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
export const principalKey = (principal: { project_id: string; uid: string }) => JSON.stringify([principal.project_id, principal.uid]);

export function localSharedOnly(): Response | null {
  return process.env.MANGA_FRONTEND_ONLY === "1"
    ? Response.json({ error: "Shared processing is available only in the local studio." }, { status: 503 })
    : null;
}

export async function sharedCall<T = unknown>(payload: Record<string, unknown>, request?: Request): Promise<T> {
  if (hostedMode()) {
    if (!request) throw new Error("Verified user request is required.");
    return privateJson<T>(request, "/shared", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
  }
  const result = await pythonJSON("manga_worker.shared", payload);
  if (!result || typeof result !== "object" || !("ok" in result) || result.ok !== true || !("result" in result)) {
    throw new Error("Shared request is unavailable or has changed.");
  }
  return result.result as T;
}

export async function readSharedJson(request: Request): Promise<Record<string, unknown>> {
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) throw new Error("Expected JSON");
  if (Number(request.headers.get("content-length") || 0) > 16384) throw new Error("Request too large");
  const reader = request.body?.getReader();
  if (!reader) throw new Error("Missing body");
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > 16384) { await reader.cancel(); throw new Error("Request too large"); }
    chunks.push(value);
  }
  const value: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid body");
  return value as Record<string, unknown>;
}
