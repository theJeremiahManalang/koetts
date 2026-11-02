import { requireAdmin, trustedSessionRequest } from "../../../features/identity/require-admin";
import { isCloudExecution, PrivateApiError, privateJson } from "../../../lib/private-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "private, no-store" };
const unavailable = () => Response.json({ error: "Hosted production controls are unavailable." }, { status: 503, headers: NO_STORE });
const privateResponse = (response: Response) => {
  const headers = new Headers(response.headers);
  headers.set("Cache-Control", "private, no-store");
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
};

function failure(error: unknown): Response {
  if (error instanceof PrivateApiError) {
    const status = error.status >= 300 && error.status < 400 ? 502 : error.status;
    const message = status === 502 ? "Private service request failed." : error.message;
    return Response.json({ error: message, code: status === 502 ? "private_api_error" : error.code }, { status, headers: NO_STORE });
  }
  return Response.json({ error: "Private service request failed." }, { status: 502, headers: NO_STORE });
}

export async function GET(request: Request) {
  const denied = await requireAdmin(request);
  if (denied) return privateResponse(denied);
  if (!isCloudExecution()) return unavailable();

  try {
    const status = await privateJson(request, "/production/status");
    return Response.json(status, { headers: NO_STORE });
  } catch (error) {
    return failure(error);
  }
}

async function readPauseRequest(request: Request): Promise<{ paused: boolean; reason: string } | null> {
  const contentType = request.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
  if (contentType !== "application/json") return null;
  const declaredLength = request.headers.get("content-length");
  if (declaredLength && (!/^\d+$/.test(declaredLength) || Number(declaredLength) > 4096)) return null;
  const reader = request.body?.getReader();
  if (!reader) return null;
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 4096) { await reader.cancel(); return null; }
      chunks.push(value);
    }
  } catch {
    return null;
  }
  if (!size) return null;
  let body: string;
  try { body = new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks)); } catch { return null; }
  let value: unknown;
  try { value = JSON.parse(body); } catch { return null; }
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  if (Object.keys(record).length !== 2 || !Object.hasOwn(record, "paused") || !Object.hasOwn(record, "reason")) return null;
  if (typeof record.paused !== "boolean" || typeof record.reason !== "string") return null;
  const reason = record.reason.trim();
  if (!reason || reason.length > 500 || /[\u0000-\u001f\u007f]/.test(reason)) return null;
  return { paused: record.paused, reason };
}

export async function POST(request: Request) {
  const denied = await requireAdmin(request);
  if (denied) return privateResponse(denied);
  if (!isCloudExecution()) return unavailable();
  if (!trustedSessionRequest(request)) {
    return Response.json({ error: "Invalid origin." }, { status: 403, headers: NO_STORE });
  }
  const payload = await readPauseRequest(request);
  if (!payload) return Response.json({ error: "Provide a pause state and a reason." }, { status: 400, headers: NO_STORE });

  try {
    const status = await privateJson(request, "/production/pause", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    return Response.json(status, { headers: NO_STORE });
  } catch (error) {
    return failure(error);
  }
}
