import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

export const root = path.resolve(process.cwd(), "..");
const local = path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const execute = promisify(execFile);
export function python(script: string, args: string[]) {
  return execute(process.env.PYTHON_EXECUTABLE || (existsSync(local) ? local : "python"), [path.join(root, script), ...args], {
    cwd: root, timeout: 30 * 60 * 1000, maxBuffer: 20 * 1024 * 1024,
    env: { ...process.env, PYTHONIOENCODING: "utf-8" }, windowsHide: true,
  });
}
