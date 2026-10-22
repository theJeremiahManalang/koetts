import { NextResponse } from "next/server";
import { getAdminAuth } from "../../../../features/identity/firebase-admin";
import { sessionCookie, trustedSessionRequest } from "../../../../features/identity/require-admin";
export const runtime = "nodejs";
const expiresIn = 60 * 60 * 1000;
const options = { httpOnly: true, sameSite: "strict" as const, secure: process.env.NODE_ENV === "production", path: "/" };

export async function POST(request: Request) {
  if (!trustedSessionRequest(request)) return NextResponse.json({ error: "Invalid origin." }, { status: 403 });
  const token = request.headers.get("authorization")?.match(/^Bearer (\S+)$/i)?.[1];
  if (!token || token.length > 16000) return NextResponse.json({ error: "Sign in required." }, { status: 401 });
  try {
    const auth = getAdminAuth();
    await auth.verifyIdToken(token, true);
    const session = await auth.createSessionCookie(token, { expiresIn });
    const response = NextResponse.json({ success: true }, { headers: { "Cache-Control": "no-store" } });
    response.cookies.set(sessionCookie, session, { ...options, maxAge: expiresIn / 1000 });
    return response;
  } catch {
    return NextResponse.json({ error: "Could not establish a secure server session." }, { status: 401 });
  }
}
export async function DELETE(request: Request) {
  if (!trustedSessionRequest(request)) return NextResponse.json({ error: "Invalid origin." }, { status: 403 });
  const response = NextResponse.json({ success: true }, { headers: { "Cache-Control": "no-store" } });
  response.cookies.set(sessionCookie, "", { ...options, maxAge: 0 });
  return response;
}
