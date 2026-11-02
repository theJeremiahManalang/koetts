import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { requireAdmin } from "../../../features/identity/require-admin";
import AdminRequestsPage from "../../../features/requests/admin-requests-page";
import { isCloudExecution } from "../../../lib/private-api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export default async function Page() {
  if (process.env.MANGA_FRONTEND_ONLY === "1") redirect("/browse");
  const denied = await requireAdmin(new Request("http://localhost/admin/requests", { headers: await headers() }));
  if (denied?.status === 401) redirect("/login?next=%2Fadmin%2Frequests");
  if (denied) redirect("/browse");
  return <AdminRequestsPage productionControlsEnabled={isCloudExecution()} />;
}
