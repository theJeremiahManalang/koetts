import { NextResponse } from "next/server";
import { requireAdmin } from "../../../../features/identity/require-admin";
import { hostedMode, privateApi, PrivateApiError } from "../../../../lib/private-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function operationId(value: string | null): string {
  if (!value || !/^[a-f0-9]{32}$/.test(value)) throw new Error("Invalid operation identifier");
  return value;
}

export async function GET(request: Request) {
  const denied = await requireAdmin(request);
  if (denied) return denied;
  if (!hostedMode()) return NextResponse.json({ error: "Operation streams are hosted only." }, { status: 503 });
  try {
    const id = operationId(new URL(request.url).searchParams.get("job"));
    return await privateApi(request, `/operations/${id}/events`, { headers: { Accept: "text/event-stream" }, signal: request.signal });
  } catch (error) {
    if (error instanceof PrivateApiError) {
      return NextResponse.json({ error: error.message, code: error.code }, { status: error.status });
    }
    return NextResponse.json({ error: "Invalid operation identifier" }, { status: 400 });
  }
}
