from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from repository_indexes import indexes_for_store  # noqa: E402
from repository_migrations import (  # noqa: E402
    POSTGRES_TRACKED_POSITIONS_STORE_ID,
    SQLITE_SUGGESTED_TRADES_STORE_ID,
)


def _sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _sqlite_index_columns(conn: sqlite3.Connection, index_name: str) -> tuple[str, ...]:
    columns: list[str] = []
    for row in conn.execute(f"PRAGMA index_xinfo({index_name})").fetchall():
        row_tuple = tuple(row)
        is_key_column = bool(row_tuple[5]) if len(row_tuple) > 5 else True
        column_name = row_tuple[2] if len(row_tuple) > 2 else None
        if not is_key_column or column_name is None:
            continue
        is_desc = bool(row_tuple[3]) if len(row_tuple) > 3 else False
        columns.append(f"{column_name} DESC" if is_desc else str(column_name))
    return tuple(columns)


def audit_sqlite_suggested_indexes(db_path: str) -> dict[str, Any]:
    if not os.path.exists(db_path):
        return {
            "store_id": SQLITE_SUGGESTED_TRADES_STORE_ID,
            "status": "skipped",
            "reason": f"SQLite database not found: {db_path}",
            "missing_indexes": [],
        }

    with closing(sqlite3.connect(db_path)) as conn:
        required_tables = {"suggested_trades", "suggested_trade_reviews"}
        missing_tables = sorted(table for table in required_tables if not _sqlite_table_exists(conn, table))
        if missing_tables:
            return {
                "store_id": SQLITE_SUGGESTED_TRADES_STORE_ID,
                "status": "skipped",
                "reason": f"Missing tables: {', '.join(missing_tables)}",
                "missing_indexes": [],
            }

        observed: dict[str, tuple[str, ...]] = {}
        for table_name in required_tables:
            for row in conn.execute(f"PRAGMA index_list({table_name})").fetchall():
                index_name = str(row[1])
                observed[index_name] = _sqlite_index_columns(conn, index_name)

    expected = [
        index
        for index in indexes_for_store(SQLITE_SUGGESTED_TRADES_STORE_ID)
        if index.status == "db_existing"
    ]
    missing_indexes = [
        {
            "index_name": index.index_name,
            "table": index.table,
            "expected_columns": index.columns,
        }
        for index in expected
        if index.index_name not in observed
    ]
    return {
        "store_id": SQLITE_SUGGESTED_TRADES_STORE_ID,
        "status": "pass" if not missing_indexes else "missing_indexes",
        "observed_indexes": observed,
        "missing_indexes": missing_indexes,
    }


def audit_postgres_tracked_indexes(database_url: str | None) -> dict[str, Any]:
    if not database_url:
        return {
            "store_id": POSTGRES_TRACKED_POSITIONS_STORE_ID,
            "status": "skipped",
            "reason": "DATABASE_URL is not configured.",
            "missing_indexes": [],
        }
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except Exception as exc:
        return {
            "store_id": POSTGRES_TRACKED_POSITIONS_STORE_ID,
            "status": "skipped",
            "reason": f"psycopg unavailable: {exc}",
            "missing_indexes": [],
        }

    expected = [
        index
        for index in indexes_for_store(POSTGRES_TRACKED_POSITIONS_STORE_ID)
        if index.status == "db_existing"
    ]
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename IN ('tracked_positions', 'position_reviews')
                    """
                )
                observed = {row["indexname"]: row["indexdef"] for row in cur.fetchall()}
    except Exception as exc:
        return {
            "store_id": POSTGRES_TRACKED_POSITIONS_STORE_ID,
            "status": "skipped",
            "reason": f"Postgres index audit unavailable: {exc}",
            "missing_indexes": [],
        }

    missing_indexes = [
        {
            "index_name": index.index_name,
            "table": index.table,
            "expected_columns": index.columns,
        }
        for index in expected
        if index.index_name not in observed
    ]
    return {
        "store_id": POSTGRES_TRACKED_POSITIONS_STORE_ID,
        "status": "pass" if not missing_indexes else "missing_indexes",
        "observed_indexes": observed,
        "missing_indexes": missing_indexes,
    }


def build_index_audit(*, sqlite_suggested_db: str, database_url: str | None) -> dict[str, Any]:
    stores = [
        audit_sqlite_suggested_indexes(sqlite_suggested_db),
        audit_postgres_tracked_indexes(database_url),
    ]
    return {
        "audit": "repository_indexes",
        "status": "missing_indexes" if any(store["status"] == "missing_indexes" for store in stores) else "pass_or_skipped",
        "stores": stores,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Trading Desk repository index audit.")
    parser.add_argument("--sqlite-suggested-db", default=str(ROOT / "chat_history.db"))
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    audit = build_index_audit(
        sqlite_suggested_db=args.sqlite_suggested_db,
        database_url=args.database_url,
    )
    if args.json:
        print(json.dumps(audit, indent=2, sort_keys=True))
    else:
        print(f"repository_indexes: {audit['status']}")
        for store in audit["stores"]:
            print(f"- {store['store_id']}: {store['status']}")
            if store.get("reason"):
                print(f"  reason: {store['reason']}")
            for missing in store.get("missing_indexes", []):
                print(f"  missing {missing['index_name']} on {missing['table']}")


if __name__ == "__main__":
    main()
