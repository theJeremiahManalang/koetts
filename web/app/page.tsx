import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { requireAdmin } from "../lib/require-admin";
import StudioWorkspace from "./studio-workspace";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export default async function StudioPage() {
  const denied = await requireAdmin(new Request("http://localhost/", { headers: await headers() }));
  if (denied?.status === 401) redirect("/login?next=%2F");
  if (denied) redirect("/browse");
  return <StudioWorkspace />;
}
