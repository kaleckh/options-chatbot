"""Detached VACUUM INTO for options_history.db with verification.

Writes a compacted copy next to the live DB, verifies row count and
quick_check, then reports. The file swap is a separate manual step so a
kill mid-run can never damage the live store. Progress goes to
data/options-validation/vacuum_into_progress.log.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "options-validation" / "options_history.db"
TARGET = ROOT / "data" / "options-validation" / "options_history_compacted.db"
LOG = ROOT / "data" / "options-validation" / "vacuum_into_progress.log"


def log(msg: str) -> None:
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    with LOG.open("a", encoding="utf8") as handle:
        handle.write(f"{stamp} {msg}\n")


def main() -> int:
    if TARGET.exists():
        log(f"removing stale partial target ({TARGET.stat().st_size / 2**30:.1f} GB)")
        TARGET.unlink()
    log(f"starting VACUUM INTO; source {DB.stat().st_size / 2**30:.1f} GB")
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=120)
    conn.execute(f"VACUUM INTO '{TARGET.as_posix()}'")
    conn.close()
    log(f"copy written: {TARGET.stat().st_size / 2**30:.1f} GB")
    check = sqlite3.connect(f"file:{TARGET.as_posix()}?mode=ro", uri=True)
    rows = check.execute("SELECT COUNT(*) FROM option_quote_snapshots").fetchone()[0]
    qc = check.execute("PRAGMA quick_check(3)").fetchall()
    check.close()
    log(f"verify: rows={rows} quick_check={qc}")
    log("VACUUM_INTO_COMPLETE swap_pending")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover - operational logging
        log(f"FAILED {type(exc).__name__}: {exc}")
        raise
