import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { python, root } from "./python";
import type { JobStatus } from "./types";

export const dataRoot = path.join(root, "results", "web");
export const id = () => randomUUID().replaceAll("-", "");
export function validId(value: string) {
  if (!/^[a-f0-9]{32}$/.test(value)) throw new Error("Invalid identifier");
  return value;
}
export function validIdempotencyKey(value: string | null): string {
  if (!value || value.length > 200 || /[\u0000-\u001f]/.test(value)) {
    throw new Error("A valid Idempotency-Key header is required.");
  }
  return value;
}
export function sameOrigin(request: Request) {
  const url = new URL(request.url);
  const host = request.headers.get("host") || "";
  if (!/^(localhost|127\.0\.0\.1)(:\d+)?$/.test(host)) throw new Error("This application is local-only.");
  const origin = request.headers.get("origin");
  if (origin && origin !== `${url.protocol}//${host}`) throw new Error("Cross-origin requests are not allowed.");
  if (request.headers.get("sec-fetch-site") === "cross-site") throw new Error("Cross-site requests are not allowed.");
}
export async function jsonFile(file: string) {
  return JSON.parse(await readFile(file, "utf8"));
}

type OperationEnvelope = {
  operation: { id: string; project: string; status: JobStatus; message: string };
  stored_upload_token?: string;
};

async function pythonJson<T>(args: string[]): Promise<T> {
  const { stdout } = await python("web_workflow.py", args);
  const value = JSON.parse(stdout) as T | { error?: string; code?: string };
  if (value && typeof value === "object" && "error" in value && value.error) {
    const error = new Error(value.error) as Error & { code?: string };
    error.code = value.code;
    throw error;
  }
  return value as T;
}

export async function enqueueOperation(payload: Record<string, unknown>, key: string): Promise<OperationEnvelope> {
  const token = id();
  const requests = path.join(dataRoot, "requests");
  const requestPath = path.join(requests, token + ".json");
  await mkdir(requests, { recursive: true });
  await writeFile(requestPath, JSON.stringify(payload));
  try {
    return await pythonJson<OperationEnvelope>(["enqueue", token, key]);
  } finally {
    await rm(requestPath, { force: true });
  }
}

const globalState = globalThis as typeof globalThis & {
  workflowWorkers?: Map<string, Promise<unknown>>;
};
const workers = globalState.workflowWorkers ??= new Map();

export type WorkerClaim = { id: string; fence: number };
export interface ExecutionAdapter {
  start(claim: WorkerClaim): void;
}

export class LocalSubprocessExecutor implements ExecutionAdapter {
  start(claim: WorkerClaim) {
    const operationId = validId(claim.id);
    const workerKey = `${operationId}:${claim.fence}`;
    if (workers.has(workerKey)) return;
    const worker = python("web_workflow.py", ["run", operationId, String(claim.fence)])
      .catch(() => undefined)
      .finally(() => workers.delete(workerKey));
    workers.set(workerKey, worker);
  }
}

const executor: ExecutionAdapter = new LocalSubprocessExecutor();

export async function dispatchQueued() {
  // One MAGI and one pipeline slot; the transactional store skips occupied projects/stages.
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const claim = await pythonJson<{ id: string; fence: number } | null>(["claim-next"]);
    if (!claim) return;
    executor.start(claim);
  }
}

export async function operationStatus(operationId: string) {
  return pythonJson<Record<string, unknown> | null>(["status", validId(operationId)]);
}

export async function operationByKey(key: string) {
  return pythonJson<Record<string, unknown> | null>(["lookup-key", key]);
}
