"""Run S0 HTTP checks in a disposable runtime, preserving repository results.

Use the audio environment's interpreter. Default mode builds and starts production;
--dev skips the build, and --webpack selects an explicit diagnostic dev fallback.
"""
import argparse
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(base, route, method="GET"):
    request = urllib.request.Request(base + route, method=method)
    try:
        return urllib.request.build_opener(NoRedirect).open(request, timeout=60)
    except urllib.error.HTTPError as response:
        return response


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def stop_group(process):
    """Stop all owned children, including after a parent exits unexpectedly."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    except ProcessLookupError:
        pass
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--webpack", action="store_true")
    args = parser.parse_args()
    if args.webpack and not args.dev:
        parser.error("--webpack requires --dev; production verification uses npm run build")
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="manga-s0-http-") as directory:
        runtime = Path(directory)
        for source in repo.glob("*.py"):
            shutil.copy2(source, runtime / source.name)
        for name in ("manga_tts", "tests"):
            shutil.copytree(repo / name, runtime / name, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(repo / "web", runtime / "web", ignore=shutil.ignore_patterns(
            "node_modules", ".next", "*.tsbuildinfo"))
        # A real copy keeps Turbopack resolution and generated files inside the runtime.
        shutil.copytree(repo / "web/node_modules", runtime / "web/node_modules", symlinks=True)
        env = {**os.environ, "PYTHON_EXECUTABLE": sys.executable,
               "GEMINI_API_KEY": "", "NEXT_TELEMETRY_DISABLED": "1"}
        env.pop("MANGA_WEB_TEST_URL", None)
        for frontend_only in (False, True):
            env["MANGA_FRONTEND_ONLY"] = "1" if frontend_only else "0"
            label = "frontend-only" if frontend_only else "studio"
            if not args.dev:
                build = subprocess.Popen(["npm", "run", "build"], cwd=runtime / "web", env=env,
                                         start_new_session=True)
                try:
                    code = build.wait(timeout=180)
                    if code:
                        raise subprocess.CalledProcessError(code, build.args)
                finally:
                    stop_group(build)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            command = ["npm", "run", "dev" if args.dev else "start", "--", "--port", str(port)]
            if args.webpack:
                command.append("--webpack")
            with (runtime / (label + ".log")).open("w+") as log:
                server = subprocess.Popen(command, cwd=runtime / "web", env=env,
                                          stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    deadline = time.monotonic() + 90
                    while True:
                        check(server.poll() is None, label + " server exited")
                        check(time.monotonic() < deadline, label + " startup timed out")
                        try:
                            with fetch(base, "/api/workflow") as response:
                                if response.status == (503 if frontend_only else 200):
                                    break
                        except (OSError, TimeoutError):
                            pass
                        time.sleep(.1)
                    if frontend_only:
                        with fetch(base, "/") as response:
                            check(response.status in (307, 308), "Missing frontend-only redirect")
                            check(response.headers.get("Location", "").endswith("/browse"), "Wrong redirect")
                        for route, method in [("/api/workflow", "GET"), ("/api/workflow", "POST"),
                                              ("/api/asset", "GET"), ("/api/extract", "POST")]:
                            with fetch(base, route, method) as response:
                                check(response.status == 503, "Processing guard failed: " + route)
                    else:
                        for route in ("/", "/browse", "/request", "/manga/echoes-of-tomorrow",
                                      "/read/echoes-of-tomorrow/chapter-1"):
                            with fetch(base, route) as response:
                                check(response.status == 200, "Route failed: " + route)
                                check(b"<html" in response.read(), "Missing HTML: " + route)
                        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests",
                                        "-p", "test_web_http.py", "-v"], cwd=runtime,
                                       env={**env, "MANGA_WEB_TEST_URL": base}, check=True, timeout=120)
                    print(label + " HTTP checks passed", flush=True)
                finally:
                    try:
                        stop_group(server)
                    finally:
                        log.seek(0)
                        print(log.read(), flush=True)


if __name__ == "__main__":
    main()
