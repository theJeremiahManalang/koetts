import { requireUser } from "../../../../features/identity/require-user";
import { localSharedOnly, sharedCall } from "../../../../features/requests/server/shared";
import { audioKey } from "../../../../features/requests/server/audio-key";
import { verifyAudioToken } from "../../../../features/requests/server/audio-token";
import { serveAudioFile } from "../../../../features/requests/server/audio-file";
import { dataRoot } from "../../../../lib/python";
import { hostedMode, proxyPrivate } from "../../../../lib/private-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  const principal = await requireUser(request); if (principal instanceof Response) return principal;
  const unavailable = localSharedOnly(); if (unavailable) return unavailable;
  let token: { work: string; publication: string };
  try { token = verifyAudioToken(await audioKey(), new URL(request.url).searchParams.get("token") || "", principal); }
  catch { return Response.json({ error: "Audio link expired or is invalid." }, { status: 403 }); }
  try {
    if (hostedMode?.()) {
      const query = new URLSearchParams({ publication_id: token.publication });
      return await proxyPrivate(request, `/shared/published/${encodeURIComponent(token.work)}?${query}`);
    }
    const artifact = await sharedCall<{ path: string }>({ action: "published", work_id: token.work, publication_id: token.publication });
    return await serveAudioFile(dataRoot, artifact.path, request);
  } catch { return Response.json({ error: "Published audio is unavailable." }, { status: 404 }); }
}
