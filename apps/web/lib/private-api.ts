import "server-only";
import { GoogleAuth } from "google-auth-library";
import { userCredential } from "../features/identity/require-admin";

const REQUEST_TIMEOUT_MS = 30_000;
const ERROR_CODES = /^[a-z][a-z0-9_]{0,63}$/;

export class PrivateApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "PrivateApiError";
    this.status = status;
    this.code = code;
  }
}

/** Local execution remains the default; invalid explicit settings fail closed. */
export function hostedMode(): boolean {
  const mode = process.env.MANGA_EXECUTION_MODE;
  if (mode === undefined || mode === "local") return false;
  if (mode === "cloud") return true;
  throw new PrivateApiError(503, "invalid_execution_mode", "Private service is unavailable.");
}

function apiOrigin(): URL {
  const value = process.env.S3_API_URL;
  if (!value) throw new PrivateApiError(503, "private_api_unconfigured", "Private service is unavailable.");
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.username || url.password || url.pathname !== "/" || url.search || url.hash) throw new Error();
    return url;
  } catch {
    throw new PrivateApiError(503, "private_api_misconfigured", "Private service is unavailable.");
  }
}

function privateUrl(origin: URL, path: string): URL {
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\") || /[\u0000-\u001f]/.test(path)) {
    throw new PrivateApiError(500, "invalid_private_path", "Private service is unavailable.");
  }
  const url = new URL(path, origin);
  if (url.origin !== origin.origin) throw new PrivateApiError(500, "invalid_private_path", "Private service is unavailable.");
  return url;
}

async function serviceToken(audience: string): Promise<string> {
  try {
    const client = await new GoogleAuth().getIdTokenClient(audience);
    const token = await client.idTokenProvider.fetchIdToken(audience);
    if (!token) throw new Error();
    return token;
  } catch {
    throw new PrivateApiError(503, "private_api_auth_unavailable", "Private service is unavailable.");
  }
}

const FORBIDDEN_HEADERS = new Set([
  "authorization", "proxy-authorization", "cookie", "x-serverless-authorization",
  "x-koetts-user-token", "x-koetts-session-cookie",
]);
const ALLOWED_REQUEST_HEADERS = new Set(["accept", "content-type", "range", "if-range", "idempotency-key"]);

/** Call a fixed relative private API path using separate service and user credentials. */
export async function privateApi(request: Request, path: string, init: RequestInit = {}): Promise<Response> {
  const origin = apiOrigin();
  const url = privateUrl(origin, path);
  const credential = userCredential(request);
  const token = await serviceToken(origin.origin);
  const headers = new Headers();
  new Headers(init.headers).forEach((value, key) => {
    const normalized = key.toLowerCase();
    if (ALLOWED_REQUEST_HEADERS.has(normalized) && !FORBIDDEN_HEADERS.has(normalized)) headers.set(key, value);
  });
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("X-Serverless-Authorization", `Bearer ${token}`);
  headers.set(credential.header, credential.value);

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const signal = init.signal ? AbortSignal.any([controller.signal, init.signal]) : controller.signal;
  try {
    return await fetch(url, {
      ...init,
      headers,
      signal,
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    throw new PrivateApiError(503, "private_api_unavailable", "Private service is unavailable.");
  } finally {
    clearTimeout(timeout);
  }
}

function safeError(response: Response, value: unknown): PrivateApiError {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const error = (value as { error?: unknown }).error;
    if (error && typeof error === "object" && !Array.isArray(error)) {
      const { code, message } = error as { code?: unknown; message?: unknown };
      if (typeof code === "string" && ERROR_CODES.test(code) && typeof message === "string") {
        const clean = message.replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, 200);
        if (clean) return new PrivateApiError(response.status, code, clean);
      }
    }
  }
  return new PrivateApiError(response.status, "private_api_error", "Private service request failed.");
}

function safeForwardedHeader(key: string, value: string): string | null {
  if (/[\u0000-\u001f\u007f]/.test(value) || value.length > 512) return null;
  switch (key) {
    case "content-type": {
      const [mediaType, ...parameters] = value.split(";").map(part => part.trim());
      const normalizedType = mediaType.toLowerCase();
      const allowed = /^audio\/[a-z0-9.+-]+$/.test(normalizedType) || new Set([
        "application/octet-stream", "application/zip", "application/json",
        "image/png", "image/jpeg", "image/webp",
      ]).has(normalizedType);
      if (!allowed) return "application/octet-stream";
      if (parameters.length && !(normalizedType === "application/json" && parameters.length === 1 && /^charset=utf-8$/i.test(parameters[0]))) return null;
      return value;
    }
    case "content-length":
      return /^(?:0|[1-9][0-9]{0,14})$/.test(value) ? value : null;
    case "content-range":
      return /^(?:bytes (?:\d+-\d+|\*)\/\d+|bytes=\d+-\d+)$/.test(value) ? value : null;
    case "accept-ranges":
      return value === "bytes" ? value : null;
    case "content-disposition":
      return /^attachment(?:;\s*filename="[\w .-]{1,120}"|;\s*filename\*=UTF-8''[A-Za-z0-9._%+-]{1,240})?$/i.test(value) ? value : null;
    case "etag":
      return /^(?:W\/)?"[\x21\x23-\x7e]{1,200}"$/.test(value) ? value : null;
    default:
      return null;
  }
}

/** Parse JSON while retaining backend HTTP status and only safe typed errors. */
export async function privateJson<T>(request: Request, path: string, init: RequestInit = {}): Promise<T> {
  const response = await privateApi(request, path, init);
  let value: unknown;
  try { value = await response.json(); }
  catch { throw new PrivateApiError(response.status, "private_api_invalid_response", "Private service response is invalid."); }
  if (!response.ok) throw safeError(response, value);
  return value as T;
}

/** Stream a private artifact response and expose only byte-stream metadata. */
export async function proxyPrivate(request: Request, path: string, init: RequestInit = {}): Promise<Response> {
  const sourceHeaders = new Headers(init.headers);
  const range = request.headers.get("range");
  const ifRange = request.headers.get("if-range");
  if (range) sourceHeaders.set("Range", range);
  if (ifRange) sourceHeaders.set("If-Range", ifRange);
  const response = await privateApi(request, path, { ...init, method: init.method || "GET", headers: sourceHeaders });
  const headers = new Headers({
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
  });
  for (const key of ["content-type", "content-length", "content-range", "accept-ranges", "content-disposition", "etag"]) {
    const value = response.headers.get(key);
    const safe = value && safeForwardedHeader(key, value);
    if (safe) headers.set(key, safe);
  }
  if (!response.ok && response.status !== 206 && response.status !== 416) {
    let error: PrivateApiError;
    try { error = safeError(response, await response.clone().json()); }
    catch {
      await response.body?.cancel().catch(() => {});
      return Response.json({ error: { code: "private_api_error", message: "Private service request failed." } }, { status: response.status, headers });
    }
    await response.body?.cancel().catch(() => {});
    return Response.json({ error: { code: error.code, message: error.message } }, { status: error.status, headers });
  }
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}
