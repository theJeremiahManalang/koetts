import { execFile } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

function repositoryRoot() {
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
export const dataRoot = process.env.MANGA_DATA_ROOT || path.join(root, "results", "web");
if (!path.isAbsolute(dataRoot)) throw new Error("MANGA_DATA_ROOT must be absolute");
const local = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const execute = promisify(execFile);
export function python(module: string, args: string[]) {
  const executable = process.env.PYTHON_EXECUTABLE || local;
  return execute(executable, ["-m", module, ...args], {
    cwd: root, timeout: 30 * 60 * 1000, maxBuffer: 20 * 1024 * 1024,
    env: { ...process.env, MANGA_DATA_ROOT: dataRoot, PYTHONIOENCODING: "utf-8" }, windowsHide: true,
  });
}
