import { requireAdmin } from "../../../../features/identity/require-admin";
import { localSharedOnly, sharedCall, validSharedId } from "../../../../features/requests/server/shared";
import { serveAudioFile } from "../../../../features/requests/server/audio-file";
import { dataRoot } from "../../../../lib/python";
import { hostedMode, proxyPrivate } from "../../../../lib/private-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  const denied = await requireAdmin(request); if (denied) return denied;
  const unavailable = localSharedOnly(); if (unavailable) return unavailable;
  const id = new URL(request.url).searchParams.get("id");
  if (!validSharedId(id)) return Response.json({ error: "Invalid candidate." }, { status: 400 });
  try {
    if (hostedMode?.()) return await proxyPrivate(request, `/shared/candidates/${encodeURIComponent(id)}`);
    const artifact = await sharedCall<{ path: string }>({ action: "candidate", candidate_id: id });
    return await serveAudioFile(dataRoot, artifact.path, request);
  } catch { return Response.json({ error: "Review audio is unavailable." }, { status: 404 }); }
}
