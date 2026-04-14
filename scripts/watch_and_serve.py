from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path("/Users/dave/Documents/Coding/Quality Review Agent")
WATCH_DIRS = [
    ROOT / "src",
    ROOT / "examples",
]
WATCH_FILES = [
    ROOT / "review-output-schema.json",
    ROOT / "README.md",
]
SERVER_CMD = ["python3", "-m", "personalens", "serve"]


def iter_watched_files() -> list[Path]:
    files: list[Path] = []
    for directory in WATCH_DIRS:
        if directory.exists():
            files.extend(path for path in directory.rglob("*") if path.is_file())
    for file_path in WATCH_FILES:
        if file_path.exists():
            files.append(file_path)
    return files


def snapshot() -> dict[str, float]:
    state: dict[str, float] = {}
    for path in iter_watched_files():
        try:
            state[str(path)] = path.stat().st_mtime
        except FileNotFoundError:
            continue
    return state


def start_server() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    return subprocess.Popen(SERVER_CMD, cwd=ROOT, env=env)


def stop_server(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def main() -> int:
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set.", file=sys.stderr)
        return 1

    proc = start_server()
    last_state = snapshot()
    print("Watching for changes. Server will restart automatically.")

    try:
        while True:
            time.sleep(1)
            current_state = snapshot()
            if current_state != last_state:
                print("Change detected. Restarting server...")
                stop_server(proc)
                proc = start_server()
                last_state = current_state

            if proc.poll() is not None:
                print("Server stopped unexpectedly. Restarting...")
                proc = start_server()
                last_state = snapshot()
    except KeyboardInterrupt:
        print("\nStopping watcher...")
    finally:
        stop_server(proc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
