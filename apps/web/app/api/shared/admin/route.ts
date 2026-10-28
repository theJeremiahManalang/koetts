import { withRequesterNames } from "../../../../features/requests/server/requester-names";
import { adminPrincipal, requireAdmin, trustedSessionRequest } from "../../../../features/identity/require-admin";
import { localSharedOnly, principalKey, readSharedJson, sharedCall, validRevision, validSharedId } from "../../../../features/requests/server/shared";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const denied = await requireAdmin(request); if (denied) return denied;
  const unavailable = localSharedOnly(); if (unavailable) return unavailable;
  const id = new URL(request.url).searchParams.get("work_id");
  if (id !== null && !validSharedId(id)) return Response.json({ error: "Invalid work." }, { status: 400 });
  try {
    const work = await sharedCall<{ id: string; requests: { reader?: string }[] }[]>({ action: "work" });
    const selected = id === null ? work : work.filter(item => item.id === id);
    if (id !== null && !selected.length) return Response.json({ error: "Work not found." }, { status: 404 });
    return Response.json({ work: await withRequesterNames(selected, adminPrincipal(request).project_id) }, { headers: { "Cache-Control": "private, no-store" } });
  }
  catch { return Response.json({ error: "Shared work is unavailable." }, { status: 503 }); }
}

export async function POST(request: Request) {
  const denied = await requireAdmin(request); if (denied) return denied;
  const unavailable = localSharedOnly(); if (unavailable) return unavailable;
  if (!trustedSessionRequest(request)) return Response.json({ error: "Invalid origin." }, { status: 403 });
  try {
    const body = await readSharedJson(request);
    if (!validSharedId(body.work_id)) return Response.json({ error: "Invalid work." }, { status: 400 });
    const actor = principalKey(adminPrincipal(request));
    const base = { work_id: body.work_id, actor };
    let payload: Record<string, unknown>;
    switch (body.action) {
      case "approve": payload = { action: "approve", ...base }; break;
      case "link":
        if (!validSharedId(body.project_id)) return Response.json({ error: "Invalid project." }, { status: 400 });
        payload = { action: "link", ...base, project_id: body.project_id }; break;
      case "prepare":
        if (!validRevision(body.revision)) return Response.json({ error: "Invalid revision." }, { status: 400 });
        payload = { action: "prepare", ...base, revision: body.revision }; break;
      case "review":
        if (!validRevision(body.revision) || !validSharedId(body.candidate_id)) return Response.json({ error: "Invalid review." }, { status: 400 });
        payload = { action: "review", ...base, revision: body.revision, candidate_id: body.candidate_id }; break;
      case "publish":
        if (!validRevision(body.revision) || !validSharedId(body.review_id) ||
            !(body.expected_publication === null || validSharedId(body.expected_publication))) return Response.json({ error: "Invalid publication." }, { status: 400 });
        payload = { action: "publish", ...base, revision: body.revision, review_id: body.review_id, expected_publication: body.expected_publication }; break;
      default: return Response.json({ error: "Invalid action." }, { status: 400 });
    }
    return Response.json({ result: await sharedCall(payload) }, { headers: { "Cache-Control": "private, no-store" } });
  } catch { return Response.json({ error: "Shared work could not be updated. Reload and try again." }, { status: 409 }); }
}
