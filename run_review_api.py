"""API launcher for the Outlook add-in integration.

Runs the FastAPI server and a cloudflared tunnel as one foreground process.
Ctrl-C stops both cleanly.

Writes the detected public tunnel URL to <project>/.tunnel_url as soon as
cloudflared reports it.
"""
from __future__ import annotations

import atexit
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
TUNNEL_FILE = ROOT / ".tunnel_url"

for p in (ROOT, SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

load_dotenv(ROOT / ".env")

TRYCLOUDFLARE_RE = re.compile(
    r"https://[a-z0-9-]+\.trycloudflare\.com",
    re.IGNORECASE,
)

PROCESSES: list[subprocess.Popen] = []


def resolve_cloudflared() -> str | None:
    explicit = os.getenv("CLOUDFLARED_BIN")
    if explicit:
        return explicit if shutil.which(explicit) or Path(explicit).exists() else None
    return shutil.which("cloudflared")


def clear_tunnel_url() -> None:
    try:
        if TUNNEL_FILE.exists():
            TUNNEL_FILE.unlink()
            print(f"[tunnel] Removed stale {TUNNEL_FILE.name}", flush=True)
    except Exception as exc:
        print(f"[tunnel] WARNING: could not remove {TUNNEL_FILE}: {exc}", flush=True)


def publish_tunnel_url(url: str) -> None:
    try:
        TUNNEL_FILE.write_text(url, encoding="utf-8")
        os.environ["API_BASE_URL"] = url
        print(f"[tunnel] Wrote {TUNNEL_FILE.name}: {url}", flush=True)
    except Exception as exc:
        print(f"[tunnel] WARNING: could not write {TUNNEL_FILE}: {exc}", flush=True)


def cloudflared_cmd(local_url: str) -> list[str]:
    bin_path = resolve_cloudflared()
    if not bin_path:
        raise RuntimeError("cloudflared not found")

    config = os.getenv("CLOUDFLARED_CONFIG")
    if not config:
        default_cfg = Path.home() / ".cloudflared" / "config.yml"
        if default_cfg.exists():
            config = str(default_cfg)

    if config:
        print(f"[tunnel] Using cloudflared config: {config}", flush=True)
        return [bin_path, "tunnel", "--config", config, "run"]

    print("[tunnel] No config file found — using quick tunnel (random URL).", flush=True)
    return [
        bin_path,
        "tunnel",
        "--url",
        local_url,
        "--no-autoupdate",
        "--loglevel",
        "info",
    ]


def start_process(
    name: str,
    cmd: list[str],
    *,
    on_line: callable | None = None,
) -> subprocess.Popen:
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
            if on_line:
                on_line(line)

    threading.Thread(target=pump, daemon=True).start()
    return proc


def start_tunnel(local_url: str, expected_base: str | None) -> subprocess.Popen | None:
    if os.getenv("QUOTING_DISABLE_TUNNEL"):
        print("[tunnel] Disabled via QUOTING_DISABLE_TUNNEL=1", flush=True)
        return None

    if not resolve_cloudflared():
        print(
            "[tunnel] cloudflared not found. Skipping tunnel.\n"
            "         Install cloudflared or set QUOTING_DISABLE_TUNNEL=1.",
            flush=True,
        )
        return None

    clear_tunnel_url()

    expected_host = urlparse(expected_base).hostname if expected_base else None
    announced = {"done": False}

    def on_line(line: str) -> None:
        if announced["done"]:
            return

        match = TRYCLOUDFLARE_RE.search(line)
        if not match:
            return

        announced["done"] = True
        actual = match.group(0)
        actual_host = urlparse(actual).hostname

        publish_tunnel_url(actual)

        if expected_host and actual_host != expected_host:
            print(
                f"[tunnel] Note: cloudflared opened {actual}, "
                f"which differs from API_BASE_URL in .env ({expected_host}). "
                f".tunnel_url takes precedence.",
                flush=True,
            )
        else:
            print(f"[tunnel] Public URL: {actual}", flush=True)

    return start_process("cloudflared", cloudflared_cmd(local_url), on_line=on_line)


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
    clear_tunnel_url()

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
    api_base = os.getenv("API_BASE_URL")

    if not api_base:
        print(
            "[run_review_api] Note: API_BASE_URL is not set in .env. "
            "The launcher will write the live tunnel URL to .tunnel_url.",
            flush=True,
        )

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    atexit.register(shutdown)

    local_url = f"http://{host}:{port}"

    tunnel_proc = start_tunnel(local_url, api_base)
    api_proc = start_api(host, port)

    # Keep this launcher alive as long as both important processes are alive.
    while True:
        time.sleep(0.5)

        if api_proc.poll() is not None:
            print(f"[launcher] API exited with code {api_proc.returncode}", flush=True)
            shutdown()
            sys.exit(api_proc.returncode or 0)

        if tunnel_proc is not None and tunnel_proc.poll() is not None:
            print(
                f"[launcher] cloudflared exited with code {tunnel_proc.returncode}. "
                "Continuing without tunnel — API is still available at "
                f"{local_url}",
                flush=True,
            )
            tunnel_proc = None


if __name__ == "__main__":
    main()