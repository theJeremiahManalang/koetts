"""Run shared metadata acceptance against a disposable, loopback Firestore emulator."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

VERSION = "1.19.8"
CHECKSUM = "9d43599ed6151199e8d604dc87fac51218e49e5f3a48519b1ae560bbe5e3382d"
FILENAME = f"cloud-firestore-emulator-v{VERSION}.jar"

SUITES = {
    "all": ["tests.integration.test_shared_firestore", "tests.integration.test_cloud_persistence",
            "tests.integration.test_cloud_operations", "tests.integration.test_cloud_execution",
            "tests.integration.test_cloud_request_quotas", "tests.integration.test_cloud_application",
            "tests.integration.test_cloud_admission", "tests.integration.test_cloud_budget",
            "tests.integration.test_cloud_gc", "tests.integration.test_cloud_rollback", "tests.integration.test_cloud_metadata_views",
            "tests.unit.engine.test_shared_requests", "tests.unit.worker.test_shared_service"],
    "contention": [
        "tests.integration.test_shared_firestore.FirestoreSharedTests.test_concurrent_duplicate_requests_retain_original_notes_and_reader_isolation",
        "tests.integration.test_cloud_operations.FirestoreOperationStoreTests.test_same_key_contention_and_changed_input_conflict",
    ],
    "rollback": ["tests.integration.test_cloud_rollback"],
}


def emulator_jar(root):
    supplied = os.environ.get("FIRESTORE_EMULATOR_JAR")
    candidates = [Path(supplied)] if supplied else [
        Path.home() / ".cache/firebase/emulators" / FILENAME,
        root / ".cache/firestore" / FILENAME,
    ]
    jar = next((candidate for candidate in candidates if candidate.is_file()), None)
    if jar is None and supplied:
        raise ValueError("FIRESTORE_EMULATOR_JAR is not a file")
    if jar is None:
        jar = candidates[-1]
        jar.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=jar.parent, delete=False) as output:
            temporary = Path(output.name)
        try:
            with urllib.request.urlopen(f"https://storage.googleapis.com/firebase-preview-drop/emulator/{FILENAME}", timeout=60) as response:
                with temporary.open("wb") as output:
                    shutil.copyfileobj(response, output)
            with temporary.open("rb") as downloaded:
                if hashlib.file_digest(downloaded, "sha256").hexdigest() != CHECKSUM:
                    raise ValueError("Downloaded emulator checksum mismatch")
            temporary.replace(jar)
        finally:
            temporary.unlink(missing_ok=True)
    with jar.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != CHECKSUM:
            raise ValueError("Expected the pinned Firestore emulator; checksum mismatch")
    return jar


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=SUITES, default="all")
    parser.add_argument("--repeat", type=int, choices=range(1, 11), default=1)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    if not shutil.which("java"):
        raise ValueError("Java 11 or newer is required for the pinned Firestore emulator")
    jar = emulator_jar(root)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="manga-firestore-") as directory:
        log = Path(directory) / "emulator.log"
        with log.open("w") as output:
            emulator = subprocess.Popen(["java", "-jar", str(jar), "--host=127.0.0.1", f"--port={port}"],
                                        cwd=directory, stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 45
            while True:
                if emulator.poll() is not None:
                    raise RuntimeError("Emulator stopped: " + log.read_text()[-2000:])
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Emulator did not become ready") from None
                    time.sleep(.1)
            env = {**os.environ, "FIRESTORE_EMULATOR_HOST": f"127.0.0.1:{port}", "MANGA_SHARED_BACKEND": "sqlite"}
            subprocess.run([sys.executable, "-m", "unittest", *(SUITES[args.suite] * args.repeat), "-v"],
                           cwd=root, env=env, check=True, timeout=180)
            print("Firestore emulator contracts and SQLite parity passed; no live project was used.")
        finally:
            emulator.terminate()
            try:
                emulator.wait(timeout=10)
            except subprocess.TimeoutExpired:
                emulator.kill()
                emulator.wait(timeout=5)


if __name__ == "__main__":
    main()
