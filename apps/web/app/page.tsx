import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { requireAdmin } from "../features/identity/require-admin";
import StudioWorkspace from "../features/studio/studio-workspace";
import { hostedMode } from "../lib/private-api";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export default async function StudioPage() {
  if (process.env.MANGA_FRONTEND_ONLY === "1") redirect("/browse");
  const hosted = hostedMode();
  const denied = await requireAdmin(new Request("http://localhost/", { headers: await headers() }));
  if (denied?.status === 401) redirect("/login?next=%2F");
  if (denied) redirect("/browse");
  return <StudioWorkspace hosted={hosted} />;
}
