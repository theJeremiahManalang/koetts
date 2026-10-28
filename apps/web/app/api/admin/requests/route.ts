import { FieldValue, Timestamp } from "firebase-admin/firestore";
import { getAdminAuth, getAdminFirestore } from "../../../../features/identity/firebase-admin";
import { adminPrincipal, requireAdmin } from "../../../../features/identity/require-admin";
import { isRequestStatus, normalizeRequestStatus, requestActions } from "../../../../features/requests/admin-request-types";

export const runtime = "nodejs";
const privateHeaders = { "Cache-Control": "private, no-store" };
const validId = (value: unknown): value is string => typeof value === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(value);

export async function GET(request: Request) {
  const denied = await requireAdmin(request);
  if (denied) return denied;
  
  const id = new URL(request.url).searchParams.get("id");
  if (id !== null && !validId(id)) return Response.json({ error: "Invalid request ID." }, { status: 400 });
  try {
    const collection = getAdminFirestore().collection("manga_requests");
    const documents = id ? [await collection.doc(id).get()] : (await collection.get()).docs;
    if (id && !documents[0].exists) return Response.json({ error: "Request not found." }, { status: 404 });
    const requests = documents.map(document => {
      const data = document.data()!;
      const status = normalizeRequestStatus(data.status);
      if (!status) throw new Error("Unrecognized stored request status");
      return { id: document.id, userId: data.userId, mangaTitle: data.mangaTitle, chapter: data.chapter,
        notes: data.notes || "", status, createdAt: data.createdAt instanceof Timestamp ? data.createdAt.toDate().toISOString() : "" };
    });
    // Resolve current profile names for old and new requests without exposing emails.
    const userIds = [...new Set(requests.map(item => item.userId).filter((uid): uid is string => typeof uid === "string" && uid.length > 0 && uid.length <= 128))];
    const names = new Map<string, string>();
    for (let offset = 0; offset < userIds.length; offset += 100) {
      const batch = userIds.slice(offset, offset + 100);
      try {
        const profiles = await getAdminAuth().getUsers(batch.map(uid => ({ uid })));
        for (const profile of profiles.users) names.set(profile.uid, profile.displayName?.trim() || "Unnamed reader");
        for (const identifier of profiles.notFound) if ("uid" in identifier) names.set(identifier.uid, "Deleted account");
      } catch {
        // A profile-service failure must not hide the queue or prevent reviewing requests.
        for (const uid of batch) names.set(uid, "Name unavailable");
      }
    }
    requests.sort((a, b) => b.createdAt.localeCompare(a.createdAt) || a.id.localeCompare(b.id));
    return Response.json({ requests: requests.map(item => ({ ...item, requesterName: names.get(item.userId) || "Name unavailable" })) }, { headers: privateHeaders });
  } catch {
    return Response.json({ error: "Could not load requests. Please retry." }, { status: 500, headers: privateHeaders });
  }
}

export async function PATCH(request: Request) {
  // Mutations require an explicit ID token; ambient session cookies cannot authorize writes.
  if (!/^Bearer \S+$/i.test(request.headers.get("authorization") || "")) {
    return Response.json({ error: "Sign in required." }, { status: 401 });
  }
  const denied = await requireAdmin(request);
  if (denied) return denied;
  let body: unknown;
  try { body = await request.json(); }
  catch { return Response.json({ error: "Invalid JSON." }, { status: 400 }); }
  if (!body || typeof body !== "object" || Array.isArray(body)) return Response.json({ error: "Invalid request data." }, { status: 400 });
  const { id, status, expectedStatus } = body as Record<string, unknown>;
  if (!validId(id) || !isRequestStatus(status) || !isRequestStatus(expectedStatus)
    || !requestActions[expectedStatus].some(action => action.status === status)) {
    return Response.json({ error: "Invalid request status transition." }, { status: 400 });
  }
  try {
    const db = getAdminFirestore();
    const ref = db.collection("manga_requests").doc(id);
    const code = await db.runTransaction(async transaction => {
      const document = await transaction.get(ref);
      if (!document.exists) return 404;
      if (normalizeRequestStatus(document.data()!.status) !== expectedStatus) return 409;
      transaction.update(ref, { status, updatedAt: FieldValue.serverTimestamp(), updatedBy: adminPrincipal(request).uid });
      return 200;
    });
    if (code !== 200) return Response.json({ error: code === 404 ? "Request not found." : "This request changed. Refresh before trying again." }, { status: code, headers: privateHeaders });
    return Response.json({ id, status }, { headers: privateHeaders });
  } catch {
    return Response.json({ error: "Could not update the request. Refresh to check its status before retrying." }, { status: 500, headers: privateHeaders });
  }
}
