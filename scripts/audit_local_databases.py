from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from local_db_hardening import (  # noqa: E402
    LocalDatabaseRole,
    local_database_manifest,
    local_database_role,
)


def _sqlite_readonly_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _sqlite_table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }


def _sidecar_paths(path: Path) -> dict[str, bool]:
    return {
        "wal": path.with_name(f"{path.name}-wal").exists(),
        "shm": path.with_name(f"{path.name}-shm").exists(),
    }


def _backup_paths(path: Path) -> tuple[str, ...]:
    if path.name == "chat_history.db":
        return tuple(sorted(str(item) for item in path.parent.glob("chat_history.backup-*.db")))
    if path.name == "tracked_positions.db":
        return tuple(sorted(str(item) for item in path.parent.glob("tracked_positions.backup-*")))
    return tuple()


def audit_sqlite_database(role: LocalDatabaseRole, db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {
            "database_id": role.database_id,
            "store_id": role.store_id,
            "path": str(db_path),
            "status": "skipped",
            "reason": "SQLite database not found.",
            "created": False,
            "sidecars": _sidecar_paths(db_path),
            "backups": _backup_paths(db_path),
        }

    before_stat = db_path.stat()
    try:
        with closing(sqlite3.connect(_sqlite_readonly_uri(db_path), uri=True)) as conn:
            tables = _sqlite_table_names(conn)
            quick_check_rows = [str(row[0]) for row in conn.execute("PRAGMA quick_check").fetchall()]
            foreign_key_rows = [
                tuple(row)
                for row in conn.execute("PRAGMA foreign_key_check").fetchall()
            ]
            journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0])
            page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
            page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
    except Exception as exc:
        return {
            "database_id": role.database_id,
            "store_id": role.store_id,
            "path": str(db_path),
            "status": "unreadable",
            "reason": str(exc),
            "created": False,
            "sidecars": _sidecar_paths(db_path),
            "backups": _backup_paths(db_path),
        }

    after_stat = db_path.stat()
    missing_required_tables = sorted(table for table in role.expected_tables if table not in tables)
    missing_optional_tables = sorted(table for table in role.optional_tables if table not in tables)
    quick_check_ok = quick_check_rows == ["ok"]
    foreign_key_ok = not foreign_key_rows
    issues = []
    if missing_required_tables:
        issues.append("missing_required_tables")
    if not quick_check_ok:
        issues.append("quick_check_failed")
    if not foreign_key_ok:
        issues.append("foreign_key_check_failed")

    status = "pass" if not issues else "issues_found"
    if status == "pass" and missing_optional_tables:
        status = "pass_with_warnings"

    return {
        "database_id": role.database_id,
        "store_id": role.store_id,
        "path": str(db_path),
        "status": status,
        "mutability": role.mutability,
        "owner": role.owner,
        "required_tables": role.expected_tables,
        "missing_required_tables": missing_required_tables,
        "missing_optional_tables": missing_optional_tables,
        "quick_check": quick_check_rows,
        "foreign_key_check_count": len(foreign_key_rows),
        "journal_mode": journal_mode,
        "page_count": page_count,
        "page_size": page_size,
        "size_bytes": before_stat.st_size,
        "mtime_ns": before_stat.st_mtime_ns,
        "created": not db_path.exists(),
        "modified_during_audit": (
            before_stat.st_size != after_stat.st_size
            or before_stat.st_mtime_ns != after_stat.st_mtime_ns
        ),
        "sidecars": _sidecar_paths(db_path),
        "backups": _backup_paths(db_path),
    }


def build_local_database_audit(
    *,
    sqlite_suggested_db: Path,
    sqlite_tracked_db: Path | None = None,
    include_legacy_tracked: bool = False,
) -> dict[str, Any]:
    stores = [
        audit_sqlite_database(
            local_database_role("chat_history_sqlite_suggested_trades"),
            sqlite_suggested_db,
        )
    ]
    if include_legacy_tracked:
        stores.append(
            audit_sqlite_database(
                local_database_role("tracked_positions_sqlite_test_legacy"),
                sqlite_tracked_db or ROOT / "data" / "tracked_positions.db",
            )
        )

    classified_out_of_scope = [
        entry
        for entry in local_database_manifest()
        if entry["mutability"] in {"outside_repository_scope", "ignored_sidecar_or_backup"}
    ]
    issue_statuses = {"issues_found", "unreadable"}
    status = "issues_found" if any(store["status"] in issue_statuses for store in stores) else "pass_or_skipped"
    return {
        "audit": "local_databases",
        "status": status,
        "stores": stores,
        "classified_out_of_scope": classified_out_of_scope,
        "rules": {
            "read_only": True,
            "creates_missing_databases": False,
            "runs_schema_init": False,
            "runs_vacuum_or_repair": False,
            "changes_journal_mode": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only local SQLite hardening audit.")
    parser.add_argument("--sqlite-suggested-db", default=str(ROOT / "chat_history.db"))
    parser.add_argument("--sqlite-tracked-db", default=str(ROOT / "data" / "tracked_positions.db"))
    parser.add_argument("--include-legacy-tracked", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    audit = build_local_database_audit(
        sqlite_suggested_db=Path(args.sqlite_suggested_db),
        sqlite_tracked_db=Path(args.sqlite_tracked_db),
        include_legacy_tracked=args.include_legacy_tracked,
    )
    if args.json:
        print(json.dumps(audit, indent=2, sort_keys=True))
    else:
        print(f"local_databases: {audit['status']}")
        for store in audit["stores"]:
            print(f"- {store['database_id']}: {store['status']}")
            if store.get("reason"):
                print(f"  reason: {store['reason']}")
            if store.get("missing_required_tables"):
                print(f"  missing required tables: {', '.join(store['missing_required_tables'])}")
            if store.get("missing_optional_tables"):
                print(f"  missing optional tables: {', '.join(store['missing_optional_tables'])}")


if __name__ == "__main__":
    main()
