import { requireAdmin, trustedSessionRequest } from "../../../../features/identity/require-admin";
import { hostedMode, privateJson, PrivateApiError } from "../../../../lib/private-api";
import { validId } from "../../../../lib/workflow";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const limit = 10 * 1024 * 1024;

/** Stage one bounded object through the authenticated service, without local files. */
export async function PUT(request: Request) {
  const denied = await requireAdmin(request); if (denied) return denied;
  if (process.env.MANGA_FRONTEND_ONLY === "1") return Response.json({ error: "Hosted uploads are unavailable." }, { status: 503 });
  if (!trustedSessionRequest(request) || request.headers.get("x-manga-workflow") !== "1") {
    return Response.json({ error: "Invalid origin or workflow request." }, { status: 403 });
  }
  try {
    if (!hostedMode()) return Response.json({ error: "Individual hosted uploads are unavailable." }, { status: 503 });
    const url = new URL(request.url);
    const token = validId(url.searchParams.get("token") || "");
    const name = url.searchParams.get("name") || "";
    if (!/^(?:[0-9]|[1-3][0-9])\.png$|^(?:chapter|cast)\.zip$|^panel\.png$/.test(name)) throw new Error("Invalid upload filename.");
    if (request.headers.get("content-type") !== "application/octet-stream") return Response.json({ error: "Expected a binary object." }, { status: 415 });
    const declared = request.headers.get("content-length");
    if (declared && (!/^\d+$/.test(declared) || declared.length > 12)) throw new Error("Invalid upload length.");
    if (declared && Number(declared) > limit) return Response.json({ error: "Each upload must be 10 MiB or smaller." }, { status: 413 });
    const reader = request.body?.getReader();
    if (!reader) throw new Error("Empty upload.");
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      size += value.byteLength;
      if (size > limit) { await reader.cancel(); return Response.json({ error: "Each upload must be 10 MiB or smaller." }, { status: 413 }); }
      chunks.push(value);
    }
    if (!size || declared && size !== Number(declared)) throw new Error("Empty or incomplete upload.");
    return Response.json(await privateJson(request, `/uploads/${token}/${name}`, {
      method: "PUT", headers: { "Content-Type": "application/octet-stream" }, body: Buffer.concat(chunks),
    }), { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    if (error instanceof PrivateApiError) return Response.json({ error: error.message, code: error.code }, { status: error.status });
    return Response.json({ error: error instanceof Error ? error.message : "Upload failed." }, { status: 400 });
  }
}
