import "server-only";
import { randomBytes, randomUUID } from "node:crypto";
import { link, mkdir, readFile, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { dataRoot } from "../../../lib/python";
import { hostedMode } from "../../../lib/private-api";

let cached: Promise<Buffer> | undefined;

/** Persist a local signing key atomically so restarts and multiple processes agree. */
export function audioKey(): Promise<Buffer> {
  if (hostedMode()) return cloudKey();
  if (!cached) cached = loadKey().catch(error => { cached = undefined; throw error; });
  return cached;
}

function cloudKey(): Promise<Buffer> {
  const value = process.env.MANGA_AUDIO_SIGNING_KEY;
  if (!value || !/^(?:[A-Za-z0-9+/]{4}){10}[A-Za-z0-9+/]{3}=$/.test(value)) {
    return Promise.reject(new Error("Hosted audio signing key is unavailable."));
  }
  const key = Buffer.from(value, "base64");
  if (key.length !== 32 || key.toString("base64") !== value) {
    return Promise.reject(new Error("Hosted audio signing key is unavailable."));
  }
  return Promise.resolve(key);
}

async function loadKey(): Promise<Buffer> {
  await mkdir(dataRoot, { recursive: true });
  const target = path.join(dataRoot, ".shared-audio-key");
  const temporary = path.join(dataRoot, `.shared-audio-key-${randomUUID()}`);
  try {
    await writeFile(temporary, randomBytes(32), { mode: 0o600, flag: "wx" });
    try { await link(temporary, target); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error; }
  } finally {
    await unlink(temporary).catch(() => {});
  }
  const key = await readFile(target);
  if (key.length !== 32) throw new Error("Invalid local audio signing key");
  return key;
}
