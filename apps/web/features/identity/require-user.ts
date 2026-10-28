import "server-only";
import { getAdminAuth } from "./firebase-admin";
import { sessionCookie } from "./require-admin";

export type UserPrincipal = { kind: "firebase"; uid: string; project_id: string };

/** Authenticate a reader from a verified Firebase token or session cookie. */
export async function requireUser(request: Request): Promise<UserPrincipal | Response> {
  const authorization = request.headers.get("authorization");
  const session = request.headers.get("cookie")?.split(";").map(value => value.trim())
    .find(value => value.startsWith(`${sessionCookie}=`))?.slice(sessionCookie.length + 1);
  if (!authorization && !session) return Response.json({ error: "Sign in required." }, { status: 401 });
  const bearer = authorization?.match(/^Bearer (\S+)$/i)?.[1];
  if (authorization && !bearer) return Response.json({ error: "Invalid authentication." }, { status: 401 });
  try {
    const auth = getAdminAuth();
    const token = bearer ? await auth.verifyIdToken(bearer, true) : await auth.verifySessionCookie(session!, true);
    if (typeof token.uid !== "string" || !token.uid || typeof token.aud !== "string" || !token.aud) throw new Error();
    return { kind: "firebase", uid: token.uid, project_id: token.aud };
  } catch {
    return Response.json({ error: "Unable to verify your session. Sign in again." }, { status: 401 });
  }
}
