import { NextResponse, type NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  const path = request.nextUrl.pathname;
  if (
    process.env.MANGA_MAINTENANCE_MODE !== "1" ||
    path === "/api" || path.startsWith("/api/") ||
    path === "/maintenance" || path.startsWith("/maintenance/") ||
    path.startsWith("/_next/") || path === "/favicon.ico" || path.includes(".")
  ) {
    return NextResponse.next();
  }
  return NextResponse.rewrite(new URL("/maintenance", request.url));
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
