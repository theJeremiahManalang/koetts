import { requireUser } from "../../../../features/identity/require-user";
import { localSharedOnly, sharedCall } from "../../../../features/requests/server/shared";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export async function GET(request: Request) {
  const principal = await requireUser(request); if (principal instanceof Response) return principal;
  const unavailable = localSharedOnly(); if (unavailable) return unavailable;
  try { return Response.json({ chapters: await sharedCall({ action: "catalog" }) }); }
  catch { return Response.json({ error: "Catalog is unavailable." }, { status: 503 }); }
}
