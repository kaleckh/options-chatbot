from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from local_env import load_local_env  # noqa: E402
from scripts.operational_provenance import build_operational_provenance, utc_now_iso  # noqa: E402


REPORT_ID = "evidence_store_backup"
DEFAULT_BACKUP_ROOT = ROOT / "data" / "backups"
DEFAULT_RETENTION_DAYS = 14
DEFAULT_SQLITE_STORES: tuple[tuple[str, Path], ...] = (
    ("chat_history", ROOT / "chat_history.db"),
    ("forward_tracking_authoritative", ROOT / "data" / "options-validation" / "forward_tracking_authoritative.db"),
    ("options_history", ROOT / "data" / "options-validation" / "options_history.db"),
)


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _sqlite_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _backup_sqlite_store(store_id: str, source_path: Path, destination_dir: Path) -> dict[str, Any]:
    destination_path = destination_dir / f"{store_id}.db"
    if not source_path.exists():
        return {
            "store_id": store_id,
            "store_type": "sqlite",
            "source_path": str(source_path),
            "status": "skipped_missing",
            "destination_path": str(destination_path),
        }
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with closing(sqlite3.connect(_sqlite_uri(source_path), uri=True)) as source_conn:
            with closing(sqlite3.connect(destination_path)) as destination_conn:
                source_conn.backup(destination_conn)
                destination_conn.execute("PRAGMA quick_check").fetchall()
    except Exception as exc:
        return {
            "store_id": store_id,
            "store_type": "sqlite",
            "source_path": str(source_path),
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "destination_path": str(destination_path),
        }
    return {
        "store_id": store_id,
        "store_type": "sqlite",
        "source_path": str(source_path),
        "status": "backed_up",
        "destination_path": str(destination_path),
        "source_size_bytes": source_path.stat().st_size,
        "backup_size_bytes": destination_path.stat().st_size,
    }


def _backup_postgres(destination_dir: Path, *, database_url: str | None = None) -> dict[str, Any]:
    url = database_url or os.getenv("OPTIONS_BACKUP_DATABASE_URL") or os.getenv("DATABASE_URL")
    destination_path = destination_dir / "tracked_positions_postgres.dump"
    if not url:
        return {
            "store_id": "postgres_tracked_positions",
            "store_type": "postgres",
            "status": "skipped_missing_database_url",
            "destination_path": str(destination_path),
        }
    pg_dump = os.getenv("PG_DUMP") or "pg_dump"
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [pg_dump, "--format=custom", "--file", str(destination_path), str(url)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=900,
        )
    except Exception as exc:
        return {
            "store_id": "postgres_tracked_positions",
            "store_type": "postgres",
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "destination_path": str(destination_path),
            "database_url_present": True,
        }
    if result.returncode != 0:
        return {
            "store_id": "postgres_tracked_positions",
            "store_type": "postgres",
            "status": "failed",
            "error": (result.stderr or result.stdout or "pg_dump failed").strip(),
            "destination_path": str(destination_path),
            "database_url_present": True,
        }
    return {
        "store_id": "postgres_tracked_positions",
        "store_type": "postgres",
        "status": "backed_up",
        "destination_path": str(destination_path),
        "database_url_present": True,
        "backup_size_bytes": destination_path.stat().st_size if destination_path.exists() else 0,
    }


def _parse_backup_timestamp(path: Path) -> datetime | None:
    try:
        return datetime.strptime(path.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _prune_old_backups(backup_root: Path, *, retention_days: int, now: datetime) -> list[str]:
    backup_root.mkdir(parents=True, exist_ok=True)
    cutoff = now - timedelta(days=max(int(retention_days), 0))
    root_resolved = backup_root.resolve()
    removed: list[str] = []
    for child in backup_root.iterdir():
        timestamp = _parse_backup_timestamp(child)
        if timestamp is None or timestamp >= cutoff:
            continue
        target = child.resolve()
        if root_resolved not in target.parents:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed.append(str(child))
    return removed


def _copy_weekly(run_dir: Path, weekly_copy_dir: Path, *, generated_at: datetime) -> dict[str, Any]:
    iso_year, iso_week, _ = generated_at.isocalendar()
    destination = weekly_copy_dir / "options-chatbot" / f"{iso_year}-W{iso_week:02d}" / run_dir.name
    if destination.exists():
        return {"status": "skipped_exists", "destination_path": str(destination)}
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(run_dir, destination)
    return {"status": "copied", "destination_path": str(destination)}


def run_evidence_backup(
    *,
    backup_root: Path = DEFAULT_BACKUP_ROOT,
    sqlite_stores: tuple[tuple[str, Path], ...] = DEFAULT_SQLITE_STORES,
    include_postgres: bool = True,
    database_url: str | None = None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    weekly_copy_dir: Path | None = None,
    weekly_copy: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    load_local_env(ROOT)
    generated = generated_at_utc or utc_now_iso()
    generated_dt = datetime.fromisoformat(generated.replace("Z", "+00:00")).astimezone(UTC)
    run_dir = backup_root / _stamp()
    sqlite_dir = run_dir / "sqlite"
    postgres_dir = run_dir / "postgres"
    run_dir.mkdir(parents=True, exist_ok=True)

    stores: list[dict[str, Any]] = []
    for store_id, source_path in sqlite_stores:
        stores.append(_backup_sqlite_store(store_id, Path(source_path), sqlite_dir))
    if include_postgres:
        stores.append(_backup_postgres(postgres_dir, database_url=database_url))

    pruned = _prune_old_backups(backup_root, retention_days=retention_days, now=generated_dt)
    failures = [store for store in stores if store.get("status") == "failed"]
    skipped = [store for store in stores if str(store.get("status") or "").startswith("skipped")]
    status = "backup_failed" if failures else "backup_completed"
    manifest = {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated,
        "backup_root": str(backup_root),
        "run_dir": str(run_dir),
        "retention_days": int(retention_days),
        "stores": stores,
        "store_count": len(stores),
        "failure_count": len(failures),
        "skipped_count": len(skipped),
        "weekly_copy": {"status": "not_requested"},
        "pruned_paths": pruned,
        "provenance": build_operational_provenance(run_id_prefix="evidence_backup", generated_at_utc=generated),
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if weekly_copy and weekly_copy_dir is not None:
        manifest["weekly_copy"] = _copy_weekly(run_dir, weekly_copy_dir, generated_at=generated_dt)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        copied_destination = Path(str(manifest["weekly_copy"].get("destination_path") or ""))
        if manifest["weekly_copy"].get("status") == "copied" and copied_destination.exists():
            (copied_destination / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Back up local evidence stores into data/backups.")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument("--skip-postgres", action="store_true")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--weekly-copy-dir", type=Path, default=None)
    parser.add_argument("--weekly-copy", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    weekly_dir = args.weekly_copy_dir or (
        Path(os.getenv("OPTIONS_BACKUP_WEEKLY_COPY_DIR"))
        if os.getenv("OPTIONS_BACKUP_WEEKLY_COPY_DIR")
        else None
    )
    manifest = run_evidence_backup(
        backup_root=args.backup_root,
        include_postgres=not args.skip_postgres,
        database_url=args.database_url,
        retention_days=args.retention_days,
        weekly_copy_dir=weekly_dir,
        weekly_copy=bool(args.weekly_copy),
    )
    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print(f"{REPORT_ID}: {manifest['status']} run_dir={manifest['run_dir']}")
    if args.strict and manifest["failure_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
