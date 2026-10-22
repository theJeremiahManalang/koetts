import { GoogleAuth } from "google-auth-library";
import { requireAdmin, userCredential } from "../../../../lib/require-admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Diagnose both identity boundaries without accessing projects or providers. */
export async function GET(request: Request) {
  const denied = await requireAdmin(request);
  if (denied) return denied;
  const base = process.env.S3_API_URL;
  if (!base) return Response.json({ error: "Private API is not configured." }, { status: 503 });
  try {
    const url = new URL(base);
    if (url.protocol !== "https:" || url.pathname !== "/" || url.search || url.hash || url.username || url.password) {
      throw new Error("Invalid service URL");
    }
    const client = await new GoogleAuth().getIdTokenClient(url.origin);
    const serviceToken = await client.idTokenProvider.fetchIdToken(url.origin);
    const credential = userCredential(request);
    // Cloud Run consumes X-Serverless-Authorization. Authorization retains the
    // signed service token for independent verification inside the container.
    const response = await fetch(new URL("/identity", url), {
      headers: {
        Authorization: `Bearer ${serviceToken}`,
        "X-Serverless-Authorization": `Bearer ${serviceToken}`,
        [credential.header]: credential.value,
      },
      signal: AbortSignal.timeout(15_000), cache: "no-store",
    });
    if (!response.ok) return Response.json({ error: "Private API identity verification failed." }, { status: 502 });
    const result = await response.json();
    return Response.json({ verified: true, mode: result.mode }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Private API could not be reached or verified." }, { status: 502 });
  }
}
