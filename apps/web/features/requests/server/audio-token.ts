import "server-only";
import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import type { UserPrincipal } from "../../identity/require-user";

const lifetimeMs = 5 * 60 * 1000;
const id = /^[a-f0-9]{32}$/;
function subject(principal: UserPrincipal) {
  return createHash("sha256").update(JSON.stringify([principal.project_id, principal.uid])).digest("hex");
}

export function issueAudioToken(key: Buffer, principal: UserPrincipal, work: string, publication: string, now = Date.now()) {
  if (key.length !== 32 || !id.test(work) || !id.test(publication)) throw new Error("Invalid audio token request");
  const payload = Buffer.from(JSON.stringify({ work, publication, subject: subject(principal), expires: now + lifetimeMs })).toString("base64url");
  return `${payload}.${createHmac("sha256", key).update(payload).digest("base64url")}`;
}

export function verifyAudioToken(key: Buffer, token: string, principal: UserPrincipal, now = Date.now()) {
  if (key.length !== 32 || token.length > 1024) throw new Error("Invalid audio token");
  const parts = token.split(".");
  if (parts.length !== 2) throw new Error("Invalid audio token");
  const expected = createHmac("sha256", key).update(parts[0]).digest();
  const actual = Buffer.from(parts[1], "base64url");
  if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) throw new Error("Invalid audio token");
  const data: unknown = JSON.parse(Buffer.from(parts[0], "base64url").toString("utf8"));
  if (!data || typeof data !== "object") throw new Error("Invalid audio token");
  const item = data as Record<string, unknown>;
  if (typeof item.work !== "string" || !id.test(item.work) || typeof item.publication !== "string" || !id.test(item.publication) ||
      item.subject !== subject(principal) || typeof item.expires !== "number" || !Number.isSafeInteger(item.expires) ||
      item.expires <= now || item.expires > now + lifetimeMs) throw new Error("Invalid or expired audio token");
  return { work: item.work, publication: item.publication };
}
