import "server-only";
import { getAdminAuth } from "./firebase-admin";

export const sessionCookie = "koetts-session";
export async function requireAdmin(request: Request): Promise<Response | null> {
  const authorization = request.headers.get("authorization");
  const session = request.headers.get("cookie")?.split(";").map(value => value.trim()).find(value => value.startsWith(`${sessionCookie}=`))?.slice(sessionCookie.length + 1);
  if (!authorization && !session) return Response.json({ error: "Sign in required." }, { status: 401 });
  try {
    const auth = getAdminAuth();
    const bearer = authorization?.match(/^Bearer (\S+)$/i)?.[1];
    if (authorization && !bearer) return Response.json({ error: "Invalid authentication." }, { status: 401 });
    const token = bearer ? await auth.verifyIdToken(bearer, true) : await auth.verifySessionCookie(session!, true);
    if (token.admin !== true) return Response.json({ error: "Administrator access required." }, { status: 403 });
    return null;
  } catch {
    return Response.json({ error: "Unable to verify administrator session. Sign in again or contact the administrator." }, { status: 401 });
  }
}

export function trustedSessionRequest(request: Request) {
  return request.headers.get("origin") === new URL(request.url).origin && request.headers.get("sec-fetch-site") !== "cross-site";
}
