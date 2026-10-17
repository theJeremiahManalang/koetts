import { mkdir, readFile, writeFile, rename } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { python, root } from "./python";

export const dataRoot = path.join(root, "results", "web");
export const id = () => randomUUID().replaceAll("-", "");
export function validId(value: string) { if (!/^[a-f0-9]{32}$/.test(value)) throw new Error("Invalid identifier"); return value; }
export function sameOrigin(request: Request) {
  const url = new URL(request.url);
  const host = request.headers.get("host") || "";
  if (!/^(localhost|127\.0\.0\.1)(:\d+)?$/.test(host)) throw new Error("This application is local-only.");
  const origin = request.headers.get("origin");
  if (origin && origin !== `${url.protocol}//${host}`) throw new Error("Cross-origin requests are not allowed.");
  if (request.headers.get("sec-fetch-site") === "cross-site") throw new Error("Cross-site requests are not allowed.");
}
export async function jsonFile(file: string) { return JSON.parse(await readFile(file, "utf8")); }
export async function atomicJson(file: string, value: unknown) {
  const temporary = file + "." + id() + ".tmp";
  await writeFile(temporary, JSON.stringify(value)); await rename(temporary, file);
}

// Kept across development reloads. Python also holds the same workspace lock as CLI.
const globalState = globalThis as typeof globalThis & { workflowBusy?: Set<string> };
const busy = globalState.workflowBusy ??= new Set();
export async function launch(project: string, job: string, payload: Record<string, unknown>) {
  if (busy.has(project)) throw new Error("This project is already processing. Wait for it to finish.");
  if (busy.size >= 2) throw new Error("Two jobs are already running. Please wait.");
  busy.add(project);
  try {
    await mkdir(path.join(dataRoot, "jobs"), { recursive: true });
    await writeFile(path.join(dataRoot, "jobs", job + ".request.json"), JSON.stringify({ ...payload, project }));
    await atomicJson(path.join(dataRoot, "jobs", job + ".json"), { id: job, project, status: "queued", message: "Starting…" });
    void python("web_workflow.py", ["job", job]).catch(async () => {
      await atomicJson(path.join(dataRoot, "jobs", job + ".json"), { id: job, project, status: "failed", message: "Worker stopped. Reload the project to recover saved work; check Python dependencies." });
    }).finally(() => busy.delete(project));
  } catch (error) { busy.delete(project); throw error; }
  return { id: job, project };
}
