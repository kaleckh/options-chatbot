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


def _sqlite_count(conn: sqlite3.Connection, query: str) -> int:
    return int(conn.execute(query).fetchone()[0])


def audit_sqlite_suggested_trades(db_path: str) -> dict[str, Any]:
    if not os.path.exists(db_path):
        return {
            "store_id": SQLITE_SUGGESTED_TRADES_STORE_ID,
            "status": "skipped",
            "reason": f"SQLite database not found: {db_path}",
            "violations": [],
        }

    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        required_tables = {"suggested_trades", "suggested_trade_reviews"}
        missing_tables = sorted(table for table in required_tables if not _sqlite_table_exists(conn, table))
        if missing_tables:
            return {
                "store_id": SQLITE_SUGGESTED_TRADES_STORE_ID,
                "status": "skipped",
                "reason": f"Missing tables: {', '.join(missing_tables)}",
                "violations": [],
            }

        checks = {
            "suggested_trades_status": """
                SELECT COUNT(*) FROM suggested_trades
                WHERE status IS NULL OR status NOT IN ('open', 'closed')
            """,
            "suggested_trades_direction": """
                SELECT COUNT(*) FROM suggested_trades
                WHERE direction IS NULL OR direction NOT IN ('call', 'put')
            """,
            "suggested_trades_ticker": """
                SELECT COUNT(*) FROM suggested_trades
                WHERE ticker IS NULL OR trim(ticker) = ''
            """,
            "suggested_trades_positive_required_numbers": """
                SELECT COUNT(*) FROM suggested_trades
                WHERE strike <= 0
                   OR contracts <= 0
                   OR entry_option_price <= 0
                   OR stop_loss_pct <= 0
                   OR profit_target_pct <= 0
                   OR time_exit_day <= 0
            """,
            "suggested_trades_nonnegative_nullable_numbers": """
                SELECT COUNT(*) FROM suggested_trades
                WHERE (entry_execution_price IS NOT NULL AND entry_execution_price <= 0)
                   OR (entry_fee_total_usd IS NOT NULL AND entry_fee_total_usd < 0)
                   OR (exit_option_price IS NOT NULL AND exit_option_price < 0)
                   OR (exit_execution_price IS NOT NULL AND exit_execution_price < 0)
                   OR (fee_total_usd IS NOT NULL AND fee_total_usd < 0)
            """,
            "suggested_trade_reviews_orphan_position": """
                SELECT COUNT(*) FROM suggested_trade_reviews r
                LEFT JOIN suggested_trades t ON t.id = r.position_id
                WHERE t.id IS NULL
            """,
            "suggested_trade_reviews_recommendation": """
                SELECT COUNT(*) FROM suggested_trade_reviews
                WHERE recommendation IS NULL OR recommendation NOT IN ('HOLD', 'SELL')
            """,
            "suggested_trade_reviews_nonnegative_nullable_numbers": """
                SELECT COUNT(*) FROM suggested_trade_reviews
                WHERE (current_option_price IS NOT NULL AND current_option_price < 0)
                   OR (entry_execution_price IS NOT NULL AND entry_execution_price <= 0)
                   OR (exit_execution_price IS NOT NULL AND exit_execution_price < 0)
                   OR (fee_total_usd IS NOT NULL AND fee_total_usd < 0)
            """,
        }
        violations = [
            {"constraint_id": constraint_id, "count": count}
            for constraint_id, query in checks.items()
            if (count := _sqlite_count(conn, query)) > 0
        ]

    return {
        "store_id": SQLITE_SUGGESTED_TRADES_STORE_ID,
        "status": "pass" if not violations else "violations_found",
        "violations": violations,
    }


def audit_postgres_tracked_positions(database_url: str | None) -> dict[str, Any]:
    if not database_url:
        return {
            "store_id": POSTGRES_TRACKED_POSITIONS_STORE_ID,
            "status": "skipped",
            "reason": "DATABASE_URL is not configured.",
            "violations": [],
        }
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except Exception as exc:
        return {
            "store_id": POSTGRES_TRACKED_POSITIONS_STORE_ID,
            "status": "skipped",
            "reason": f"psycopg unavailable: {exc}",
            "violations": [],
        }

    checks = {
        "tracked_positions_status": """
            SELECT COUNT(*) AS count FROM tracked_positions
            WHERE status IS NULL OR status NOT IN ('open', 'closed')
        """,
        "tracked_positions_direction": """
            SELECT COUNT(*) AS count FROM tracked_positions
            WHERE direction IS NULL OR direction NOT IN ('call', 'put')
        """,
        "tracked_positions_ticker": """
            SELECT COUNT(*) AS count FROM tracked_positions
            WHERE ticker IS NULL OR btrim(ticker) = ''
        """,
        "tracked_positions_positive_required_numbers": """
            SELECT COUNT(*) AS count FROM tracked_positions
            WHERE strike <= 0
               OR contracts <= 0
               OR entry_option_price <= 0
               OR stop_loss_pct <= 0
               OR profit_target_pct <= 0
               OR time_exit_day <= 0
        """,
        "tracked_positions_nonnegative_nullable_numbers": """
            SELECT COUNT(*) AS count FROM tracked_positions
            WHERE (entry_execution_price IS NOT NULL AND entry_execution_price <= 0)
               OR (entry_fee_total_usd IS NOT NULL AND entry_fee_total_usd < 0)
               OR (exit_option_price IS NOT NULL AND exit_option_price < 0)
               OR (exit_execution_price IS NOT NULL AND exit_execution_price < 0)
               OR (fee_total_usd IS NOT NULL AND fee_total_usd < 0)
        """,
        "position_reviews_recommendation": """
            SELECT COUNT(*) AS count FROM position_reviews
            WHERE recommendation IS NULL OR recommendation NOT IN ('HOLD', 'SELL')
        """,
        "position_reviews_nonnegative_nullable_numbers": """
            SELECT COUNT(*) AS count FROM position_reviews
            WHERE (current_option_price IS NOT NULL AND current_option_price < 0)
               OR (entry_execution_price IS NOT NULL AND entry_execution_price <= 0)
               OR (exit_execution_price IS NOT NULL AND exit_execution_price < 0)
               OR (fee_total_usd IS NOT NULL AND fee_total_usd < 0)
        """,
    }
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                violations = []
                for constraint_id, query in checks.items():
                    cur.execute(query)
                    row = cur.fetchone()
                    count = int(row["count"]) if row else 0
                    if count > 0:
                        violations.append({"constraint_id": constraint_id, "count": count})
    except Exception as exc:
        return {
            "store_id": POSTGRES_TRACKED_POSITIONS_STORE_ID,
            "status": "skipped",
            "reason": f"Postgres audit unavailable: {exc}",
            "violations": [],
        }

    return {
        "store_id": POSTGRES_TRACKED_POSITIONS_STORE_ID,
        "status": "pass" if not violations else "violations_found",
        "violations": violations,
    }


def build_constraint_audit(*, sqlite_suggested_db: str, database_url: str | None) -> dict[str, Any]:
    stores = [
        audit_sqlite_suggested_trades(sqlite_suggested_db),
        audit_postgres_tracked_positions(database_url),
    ]
    return {
        "audit": "repository_constraints",
        "status": "violations_found" if any(store["status"] == "violations_found" for store in stores) else "pass_or_skipped",
        "stores": stores,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Trading Desk repository constraint audit.")
    parser.add_argument("--sqlite-suggested-db", default=str(ROOT / "chat_history.db"))
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    audit = build_constraint_audit(
        sqlite_suggested_db=args.sqlite_suggested_db,
        database_url=args.database_url,
    )
    if args.json:
        print(json.dumps(audit, indent=2, sort_keys=True))
    else:
        print(f"repository_constraints: {audit['status']}")
        for store in audit["stores"]:
            print(f"- {store['store_id']}: {store['status']}")
            if store.get("reason"):
                print(f"  reason: {store['reason']}")
            for violation in store["violations"]:
                print(f"  {violation['constraint_id']}: {violation['count']}")


if __name__ == "__main__":
    main()
