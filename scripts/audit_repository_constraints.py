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
for candidate in (ROOT, BACKEND_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from repository_migrations import (  # noqa: E402
    POSTGRES_TRACKED_POSITIONS_STORE_ID,
    SQLITE_SUGGESTED_TRADES_STORE_ID,
)

try:  # noqa: SIM105 - optional in tests and CI shells without local env files.
    from local_env import load_local_env  # noqa: E402
except Exception:  # pragma: no cover - import availability depends on invocation path.
    load_local_env = None  # type: ignore[assignment]


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
            "suggested_trades_closed_missing_realized_pnl": """
                SELECT COUNT(*) FROM suggested_trades
                WHERE status = 'closed'
                  AND (
                    exit_execution_price IS NULL
                    OR gross_pnl_pct IS NULL
                    OR net_pnl_pct IS NULL
                    OR gross_pnl_usd IS NULL
                    OR net_pnl_usd IS NULL
                  )
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
        "tracked_positions_closed_production_missing_realized_pnl": """
            SELECT COUNT(*) AS count FROM tracked_positions
            WHERE status = 'closed'
              AND (
                proof_eligible IS TRUE
                OR proof_class = 'live_scan_exact_contract'
                OR source_pick_snapshot->>'proof_class' = 'live_scan_exact_contract'
              )
              AND (
                exit_execution_price IS NULL
                OR gross_pnl_pct IS NULL
                OR net_pnl_pct IS NULL
                OR gross_pnl_usd IS NULL
                OR net_pnl_usd IS NULL
              )
        """,
        "tracked_positions_closed_unclassified_missing_realized_pnl": """
            SELECT COUNT(*) AS count FROM tracked_positions
            WHERE status = 'closed'
              AND (
                exit_execution_price IS NULL
                OR gross_pnl_pct IS NULL
                OR net_pnl_pct IS NULL
                OR gross_pnl_usd IS NULL
                OR net_pnl_usd IS NULL
              )
              AND NOT (
                proof_eligible IS TRUE
                OR proof_class = 'live_scan_exact_contract'
                OR source_pick_snapshot->>'proof_class' = 'live_scan_exact_contract'
              )
              AND NOT (
                source_pick_snapshot ? 'backfill_audit_id'
                OR source_pick_snapshot ? 'backfill_signature'
                OR source_pick_snapshot ? 'position_migration_id'
                OR source_pick_snapshot ? 'position_migrated_at_utc'
                OR source_pick_snapshot ? 'historical_position_lifecycle'
                OR source_pick_snapshot ? 'historical_position_exit_snapshot'
                OR source_pick_snapshot ? 'historical_position_migration_as_of'
                OR source_pick_snapshot->>'production_filter_action' = 'research_backfill_not_live_production'
                OR source_pick_snapshot->>'source_separation' = 'historical_selection_not_live_production'
                OR source_pick_snapshot->>'research_only' = 'true'
              )
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
    diagnostic_checks = {
        "tracked_positions_closed_research_backfill_missing_realized_pnl": """
            SELECT COUNT(*) AS count FROM tracked_positions
            WHERE status = 'closed'
              AND (
                exit_execution_price IS NULL
                OR gross_pnl_pct IS NULL
                OR net_pnl_pct IS NULL
                OR gross_pnl_usd IS NULL
                OR net_pnl_usd IS NULL
              )
              AND (
                source_pick_snapshot ? 'backfill_audit_id'
                OR source_pick_snapshot ? 'backfill_signature'
                OR source_pick_snapshot ? 'position_migration_id'
                OR source_pick_snapshot ? 'position_migrated_at_utc'
                OR source_pick_snapshot ? 'historical_position_lifecycle'
                OR source_pick_snapshot ? 'historical_position_exit_snapshot'
                OR source_pick_snapshot ? 'historical_position_migration_as_of'
                OR source_pick_snapshot->>'production_filter_action' = 'research_backfill_not_live_production'
                OR source_pick_snapshot->>'source_separation' = 'historical_selection_not_live_production'
                OR source_pick_snapshot->>'research_only' = 'true'
              )
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
                diagnostics = []
                for diagnostic_id, query in diagnostic_checks.items():
                    cur.execute(query)
                    row = cur.fetchone()
                    count = int(row["count"]) if row else 0
                    if count > 0:
                        diagnostics.append({"diagnostic_id": diagnostic_id, "count": count})
    except Exception as exc:
        return {
            "store_id": POSTGRES_TRACKED_POSITIONS_STORE_ID,
            "status": "skipped",
            "reason": f"Postgres audit unavailable: {exc}",
            "violations": [],
        }

    return {
        "store_id": POSTGRES_TRACKED_POSITIONS_STORE_ID,
        "status": "violations_found" if violations else "pass_with_diagnostics" if diagnostics else "pass",
        "violations": violations,
        "diagnostics": diagnostics,
    }


def build_constraint_audit(*, sqlite_suggested_db: str, database_url: str | None) -> dict[str, Any]:
    stores = [
        audit_sqlite_suggested_trades(sqlite_suggested_db),
        audit_postgres_tracked_positions(database_url),
    ]
    has_violations = any(store["status"] == "violations_found" for store in stores)
    has_diagnostics = any(store["status"] == "pass_with_diagnostics" for store in stores)
    return {
        "audit": "repository_constraints",
        "status": "violations_found" if has_violations else "pass_with_diagnostics" if has_diagnostics else "pass_or_skipped",
        "stores": stores,
    }


def main() -> int:
    if load_local_env is not None:
        load_local_env(ROOT)
    parser = argparse.ArgumentParser(description="Read-only Trading Desk repository constraint audit.")
    parser.add_argument("--sqlite-suggested-db", default=str(ROOT / "chat_history.db"))
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero when hard violations are found.")
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
            for diagnostic in store.get("diagnostics", []):
                print(f"  diagnostic {diagnostic['diagnostic_id']}: {diagnostic['count']}")
    return 1 if args.strict and audit["status"] == "violations_found" else 0


if __name__ == "__main__":
    raise SystemExit(main())
