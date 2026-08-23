"""Dev-only convenience: keeps the companion server and avatar app's Vite
dev server running while testing locally, restarting either one if it dies.

This is NOT what runs on the actual Pi -- that's systemd's Restart=on-failure
(see BUILD_PLAN.md's Phase 2/5 systemd units, already speced with crash
reporting via pi-client/crash_reporter.py). This script exists because
those two dev processes have no such supervisor at all right now -- they're
just ad-hoc background processes, and they've already died silently once
this session with nothing watching.

Usage: python sunny-companion/dev-watchdog.py
Ctrl+C to stop both.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AVATAR_APP_DIR = REPO_ROOT / "sunny-companion" / "pi-client" / "avatar-app"
RESTART_DELAY_SECONDS = 2

SERVICES = {
    "companion-server": {
        "cmd": [str(REPO_ROOT / "venv" / "Scripts" / "python.exe"), "-m", "uvicorn", "sunny_code.main:app",
                "--host", "127.0.0.1", "--port", "5055"],
        "cwd": REPO_ROOT,
    },
    "avatar-vite": {
        "cmd": ["npm", "run", "dev"],
        "cwd": AVATAR_APP_DIR,
    },
}


def main() -> None:
    processes: dict[str, subprocess.Popen] = {}

    def start(name: str) -> None:
        spec = SERVICES[name]
        print(f"[watchdog] starting {name}", flush=True)
        processes[name] = subprocess.Popen(spec["cmd"], cwd=spec["cwd"], shell=(sys.platform == "win32"))

    for name in SERVICES:
        start(name)

    try:
        while True:
            time.sleep(1)
            for name, proc in list(processes.items()):
                exit_code = proc.poll()
                if exit_code is not None:
                    print(
                        f"[watchdog] {name} exited (code {exit_code}) -- restarting in {RESTART_DELAY_SECONDS}s",
                        flush=True,
                    )
                    time.sleep(RESTART_DELAY_SECONDS)
                    start(name)
    except KeyboardInterrupt:
        print("\n[watchdog] stopping all services", flush=True)
        for proc in processes.values():
            proc.terminate()


if __name__ == "__main__":
    main()
