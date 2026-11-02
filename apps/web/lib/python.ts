import { execFile, spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

function repositoryRoot() {
  // Cloud routes use the private service. Importing shared local adapters must
  // not require a Python checkout inside the hosted Next.js runtime.
  if (process.env.MANGA_EXECUTION_MODE === "cloud") return process.cwd();
  const configured = process.env.MANGA_REPO_ROOT;
  if (configured) {
    if (!path.isAbsolute(configured)) throw new Error("MANGA_REPO_ROOT must be absolute");
    return configured;
  }
  let directory = process.cwd();
  while (true) {
    const manifest = path.join(directory, "package.json");
    if (existsSync(manifest) && JSON.parse(readFileSync(manifest, "utf8")).name === "manga-studio") return directory;
    const parent = path.dirname(directory);
    if (parent === directory) break;
    directory = parent;
  }
  // Hosted frontend processing is disabled before this location can be used.
  if (process.env.MANGA_FRONTEND_ONLY === "1") return process.cwd();
  throw new Error("Set MANGA_REPO_ROOT to the monorepo root");
}

export const root = repositoryRoot();
export const dataRoot = (process.env.MANGA_EXECUTION_MODE === "cloud" ? undefined : process.env.MANGA_DATA_ROOT) || path.join(root, "results", "web");
if (!path.isAbsolute(dataRoot)) throw new Error("MANGA_DATA_ROOT must be absolute");
const local = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const execute = promisify(execFile);
export function python(module: string, args: string[]) {
  if (process.env.MANGA_FRONTEND_ONLY === "1" || process.env.MANGA_EXECUTION_MODE && process.env.MANGA_EXECUTION_MODE !== "local") {
    return Promise.reject(new Error("Local Python execution is unavailable in hosted mode."));
  }
  const executable = process.env.PYTHON_EXECUTABLE || local;
  return execute(executable, ["-m", module, ...args], {
    cwd: root, timeout: 30 * 60 * 1000, maxBuffer: 20 * 1024 * 1024,
    env: { ...process.env, MANGA_DATA_ROOT: dataRoot, PYTHONIOENCODING: "utf-8" }, windowsHide: true,
  });
}

/** Send short application requests over stdin, keeping private fields out of argv. */
export function pythonJSON(module: string, input: unknown): Promise<unknown> {
  if (process.env.MANGA_FRONTEND_ONLY === "1" || process.env.MANGA_EXECUTION_MODE && process.env.MANGA_EXECUTION_MODE !== "local") {
    return Promise.reject(new Error("Local Python execution is unavailable in hosted mode."));
  }
  const body = JSON.stringify(input);
  if (Buffer.byteLength(body, "utf8") > 65536) return Promise.reject(new Error("Request too large"));
  const executable = process.env.PYTHON_EXECUTABLE || local;
  return new Promise((resolve, reject) => {
    const child = spawn(executable, ["-m", module], {
      cwd: root,
      env: { ...process.env, MANGA_DATA_ROOT: dataRoot, PYTHONIOENCODING: "utf-8" },
      windowsHide: true,
      stdio: ["pipe", "pipe", "ignore"],
    });
    const chunks: Buffer[] = [];
    let size = 0;
    const timer = setTimeout(() => child.kill(), 30 * 60 * 1000);
    child.stdout.on("data", (chunk: Buffer) => {
      size += chunk.length;
      if (size > 20 * 1024 * 1024) child.kill();
      else chunks.push(chunk);
    });
    child.on("error", () => { clearTimeout(timer); reject(new Error("Shared service unavailable")); });
    child.on("close", code => {
      clearTimeout(timer);
      if (code !== 0 || size > 20 * 1024 * 1024) return reject(new Error("Shared service unavailable"));
      try { resolve(JSON.parse(Buffer.concat(chunks).toString("utf8"))); }
      catch { reject(new Error("Shared service unavailable")); }
    });
    child.stdin.on("error", () => {});
    child.stdin.end(body);
  });
}
