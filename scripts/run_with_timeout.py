from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return


def run_with_timeout(command: list[str], timeout_seconds: float) -> int:
    if not command:
        raise ValueError("command is required")
    if command[0].lower() in {"python", "python.exe", "python3", "python3.exe"}:
        command = [sys.executable, *command[1:]]
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    start_new_session = os.name != "nt"
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        creationflags=creationflags,
        start_new_session=start_new_session,
    )
    try:
        return int(process.wait(timeout=timeout_seconds))
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        print(
            f"Command timed out after {timeout_seconds:g}s and was terminated: {' '.join(command)}",
            file=sys.stderr,
        )
        return 124


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a command with process-tree cleanup on timeout.")
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    timeout_seconds = float(os.environ.get("RUN_WITH_TIMEOUT_SECONDS", args.timeout_seconds))
    if timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if not command:
        parser.error("command is required after --")
    return run_with_timeout(command, timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
