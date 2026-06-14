from __future__ import annotations

import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def current_host_name() -> str:
    return (
        os.getenv("OPTIONS_EVIDENCE_HOST")
        or os.getenv("COMPUTERNAME")
        or os.getenv("HOSTNAME")
        or platform.node()
        or "unknown"
    ).strip()


def _git_text(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return text or None


def current_commit_sha() -> str | None:
    return _git_text(["rev-parse", "HEAD"])


def current_branch_name() -> str | None:
    return _git_text(["rev-parse", "--abbrev-ref", "HEAD"])


def build_operational_provenance(
    *,
    run_id_prefix: str,
    generated_at_utc: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or utc_now_iso()
    commit_sha = current_commit_sha()
    host = current_host_name()
    run_id_parts = [run_id_prefix, host, commit_sha[:12] if commit_sha else "unknown", generated]
    payload: dict[str, Any] = {
        "generated_at_utc": generated,
        "run_id": ":".join(str(part) for part in run_id_parts),
        "host": host,
        "commit_sha": commit_sha,
        "short_commit_sha": commit_sha[:12] if commit_sha else None,
        "branch": current_branch_name(),
        "repository_root": str(ROOT),
    }
    if extra:
        payload.update(extra)
    return payload
