import "server-only";
import { getAdminAuth } from "../../identity/firebase-admin";

type ReaderRequest = { reader?: string; requester_name?: string };
type Work = { requests: ReaderRequest[] };

/** Enrich only the already authorized admin response; never expose account emails. */
export async function withRequesterNames<T extends Work>(work: T[], projectId: string): Promise<T[]> {
  const identities = new Map<string, string>();
  for (const item of work) for (const request of item.requests) {
    try {
      const value: unknown = JSON.parse(request.reader || "");
      if (Array.isArray(value) && value.length === 2 && value[0] === projectId && typeof value[1] === "string" && value[1].length > 0 && value[1].length <= 128) {
        identities.set(request.reader!, value[1]);
      }
    } catch { /* Legacy local actors have no Firebase profile. */ }
  }
  const names = new Map<string, string>();
  const uids = [...new Set(identities.values())];
  for (let offset = 0; offset < uids.length; offset += 100) {
    const batch = uids.slice(offset, offset + 100);
    try {
      const profiles = await getAdminAuth().getUsers(batch.map(uid => ({ uid })));
      for (const profile of profiles.users) names.set(profile.uid, profile.displayName?.trim() || "Unnamed reader");
      for (const identifier of profiles.notFound) if ("uid" in identifier) names.set(identifier.uid, "Deleted account");
    } catch {
      for (const uid of batch) names.set(uid, "Name unavailable");
    }
  }
  return work.map(item => ({ ...item, requests: item.requests.map(request => ({ ...request,
    requester_name: names.get(identities.get(request.reader || "") || "") || "Name unavailable",
  })) }));
}
