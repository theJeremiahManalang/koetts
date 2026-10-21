import "server-only";
import { getAdminAuth } from "./firebase-admin";

export const sessionCookie = "koetts-session";
export type AdminPrincipal = { kind: "firebase"; uid: string; project_id: string };
const principals = new WeakMap<Request, AdminPrincipal>();

/** Read only the identity verified for this exact request, never forwarded headers. */
export function adminPrincipal(request: Request): AdminPrincipal {
  const principal = principals.get(request);
  if (!principal) throw new Error("Administrator identity was not verified.");
  return principal;
}

export function userCredential(request: Request): { header: string; value: string } {
  const bearer = request.headers.get("authorization")?.match(/^Bearer (\S+)$/i)?.[1];
  if (bearer) return { header: "X-KoeTTS-User-Token", value: bearer };
  const session = request.headers.get("cookie")?.split(";").map(value => value.trim()).find(value => value.startsWith(`${sessionCookie}=`))?.slice(sessionCookie.length + 1);
  if (!session) throw new Error("User credential is missing.");
  return { header: "X-KoeTTS-Session-Cookie", value: session };
}
export async function requireAdmin(request: Request): Promise<Response | null> {
  principals.delete(request);
  const authorization = request.headers.get("authorization");
  const session = request.headers.get("cookie")?.split(";").map(value => value.trim()).find(value => value.startsWith(`${sessionCookie}=`))?.slice(sessionCookie.length + 1);
  if (!authorization && !session) return Response.json({ error: "Sign in required." }, { status: 401 });
  try {
    const auth = getAdminAuth();
    const bearer = authorization?.match(/^Bearer (\S+)$/i)?.[1];
    if (authorization && !bearer) return Response.json({ error: "Invalid authentication." }, { status: 401 });
    const token = bearer ? await auth.verifyIdToken(bearer, true) : await auth.verifySessionCookie(session!, true);
    if (token.admin !== true) return Response.json({ error: "Administrator access required." }, { status: 403 });
    principals.set(request, { kind: "firebase", uid: token.uid, project_id: token.aud });
    return null;
  } catch {
    return Response.json({ error: "Unable to verify administrator session. Sign in again or contact the administrator." }, { status: 401 });
  }
}

export function trustedSessionRequest(request: Request) {
  if (request.headers.get("sec-fetch-site") === "cross-site") return false;
  try {
    // Hosting may give Next an internal URL. Use an explicit canonical origin,
    // never an untrusted forwarded-host header, for the browser CSRF boundary.
    const configured = process.env.MANGA_APP_ORIGIN;
    const expected = configured || new URL(request.url).origin;
    if (new URL(expected).origin !== expected) return false;
    return request.headers.get("origin") === expected;
  } catch {
    return false;
  }
}
