"""API launcher for the Outlook add-in integration.

Runs the FastAPI server as a foreground process. Ctrl-C stops it cleanly.
"""
from __future__ import annotations

import atexit
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

load_dotenv(ROOT / ".env")

PROCESSES: list[subprocess.Popen] = []


def start_process(name: str, cmd: list[str]) -> subprocess.Popen:
    print(f"[{name}] Starting: {' '.join(cmd)}", flush=True)

    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=os.environ.copy(),
    )
    PROCESSES.append(proc)

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(f"[{name}] {line}", end="", flush=True)

    threading.Thread(target=pump, daemon=True).start()
    return proc


def start_api(host: str, port: int) -> subprocess.Popen:
    reload_enabled = os.getenv("QUOTING_API_RELOAD", "1") != "0"

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "quoting.api.review_api:app",
        "--host",
        host,
        "--port",
        str(port),
    ]

    if reload_enabled:
        cmd += ["--reload", "--reload-dir", str(ROOT)]

    return start_process("api", cmd)


def shutdown() -> None:
    for proc in PROCESSES:
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    deadline = time.time() + 5

    for proc in PROCESSES:
        if proc.poll() is not None:
            continue

        remaining = max(0.1, deadline - time.time())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass


def handle_signal(signum: int, _frame: object) -> None:
    print(f"\n[launcher] Received signal {signum}. Shutting down...", flush=True)
    shutdown()
    sys.exit(0)


def main() -> None:
    host = os.getenv("QUOTING_API_HOST", "127.0.0.1")
    port = int(os.getenv("QUOTING_API_PORT", "8000"))

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    atexit.register(shutdown)

    local_url = f"http://{host}:{port}"
    print(f"[launcher] API on {local_url}", flush=True)

    api_proc = start_api(host, port)

    while True:
        time.sleep(0.5)

        if api_proc.poll() is not None:
            print(f"[launcher] API exited with code {api_proc.returncode}", flush=True)
            shutdown()
            sys.exit(api_proc.returncode or 0)


if __name__ == "__main__":
    main()
