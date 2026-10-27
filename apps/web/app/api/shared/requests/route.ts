import { requireUser } from "../../../../features/identity/require-user";
import { trustedSessionRequest } from "../../../../features/identity/require-admin";
import { localSharedOnly, principalKey, readSharedJson, sharedCall, validSharedId } from "../../../../features/requests/server/shared";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const principal = await requireUser(request); if (principal instanceof Response) return principal;
  const unavailable = localSharedOnly(); if (unavailable) return unavailable;
  try { return Response.json({ requests: await sharedCall({ action: "requests", reader: principalKey(principal) }) }); }
  catch { return Response.json({ error: "Requests are unavailable." }, { status: 503 }); }
}

export async function POST(request: Request) {
  const principal = await requireUser(request); if (principal instanceof Response) return principal;
  const unavailable = localSharedOnly(); if (unavailable) return unavailable;
  if (!trustedSessionRequest(request)) return Response.json({ error: "Invalid origin." }, { status: 403 });
  try {
    const body = await readSharedJson(request);
    if (typeof body.title !== "string" || !body.title.trim() || body.title.length > 200 ||
        typeof body.chapter !== "string" || !/^[0-9]{1,4}$/.test(body.chapter) || Number(body.chapter) < 1 ||
        typeof body.notes !== "string" || body.notes.length > 4000) return Response.json({ error: "Invalid request." }, { status: 400 });
    const result = await sharedCall({ action: "submit", reader: principalKey(principal), title: body.title, chapter: body.chapter, notes: body.notes });
    return Response.json({ request: result });
  } catch { return Response.json({ error: "Request could not be saved." }, { status: 400 }); }
}

export async function DELETE(request: Request) {
  const principal = await requireUser(request); if (principal instanceof Response) return principal;
  const unavailable = localSharedOnly(); if (unavailable) return unavailable;
  if (!trustedSessionRequest(request)) return Response.json({ error: "Invalid origin." }, { status: 403 });
  try {
    const body = await readSharedJson(request);
    if (!validSharedId(body.id)) return Response.json({ error: "Invalid request." }, { status: 400 });
    await sharedCall({ action: "delete", reader: principalKey(principal), request_id: body.id });
    return Response.json({ deleted: true });
  } catch { return Response.json({ error: "Request could not be deleted." }, { status: 404 }); }
}
