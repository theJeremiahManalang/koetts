import { requireUser } from "../../../../features/identity/require-user";
import { localSharedOnly, sharedCall, validSharedId } from "../../../../features/requests/server/shared";
import { audioKey } from "../../../../features/requests/server/audio-key";
import { issueAudioToken } from "../../../../features/requests/server/audio-token";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  const principal = await requireUser(request); if (principal instanceof Response) return principal;
  const unavailable = localSharedOnly(); if (unavailable) return unavailable;
  const work = new URL(request.url).searchParams.get("work");
  if (!validSharedId(work)) return Response.json({ error: "Invalid chapter." }, { status: 400 });
  try {
    const publication = await sharedCall<{ publication_id: string }>({ action: "published", work_id: work }, request);
    if (!validSharedId(publication.publication_id)) throw new Error();
    const token = issueAudioToken(await audioKey(), principal, work, publication.publication_id);
    return Response.json({ url: `/api/shared/audio?token=${encodeURIComponent(token)}`, expires_in: 300 }, { headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ error: "Published audio is unavailable." }, { status: 404 }); }
}
