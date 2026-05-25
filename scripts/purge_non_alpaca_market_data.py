"""
Purge persisted market-data cache rows that are not Alpaca sourced.

This intentionally leaves tracked positions alone. It only cleans reusable
market-data caches so future scans cannot silently reuse old Yahoo/network or
unlabeled rows.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import historical_options_store as hos
import market_data_service as mds
from local_env import load_local_env


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup = path.with_name(f"{path.stem}.before-alpaca-purge-{stamp}{path.suffix}")
    shutil.copy2(path, backup)
    return backup


def _delete_market_cache(conn: sqlite3.Connection, *, execute: bool) -> dict[str, int]:
    results: dict[str, int] = {}
    statements = {
        "daily_history": """
            DELETE FROM daily_history
            WHERE source IS NULL
               OR NOT (LOWER(source) LIKE '%alpaca%' AND LOWER(source) LIKE '%sip%')
        """,
        "ticker_info_cache": """
            DELETE FROM ticker_info_cache
            WHERE source IS NULL
               OR NOT (LOWER(source) LIKE '%alpaca%' AND LOWER(source) LIKE '%sip%')
        """,
        "earnings_dates_cache": """
            DELETE FROM earnings_dates_cache
            WHERE source IS NULL
               OR NOT (LOWER(source) LIKE '%alpaca%' AND LOWER(source) LIKE '%sip%')
        """,
        "option_expiries_cache": """
            DELETE FROM option_expiries_cache
            WHERE source IS NULL
               OR NOT (LOWER(source) LIKE '%alpaca%' AND LOWER(source) LIKE '%opra%')
        """,
        "option_chain_snapshot_cache": """
            DELETE FROM option_chain_snapshot_cache
            WHERE source IS NULL
               OR NOT (LOWER(source) LIKE '%alpaca%' AND LOWER(source) LIKE '%opra%')
        """,
    }
    for table, sql in statements.items():
        count_sql = f"SELECT COUNT(*) FROM ({sql.replace('DELETE FROM', 'SELECT 1 FROM', 1)})"
        count = int(conn.execute(count_sql).fetchone()[0])
        results[table] = count
        if execute and count:
            conn.execute(sql)
    if execute:
        conn.commit()
    return results


def _delete_historical_options(conn: sqlite3.Connection, *, execute: bool) -> dict[str, int]:
    stale_batches = [
        int(row[0])
        for row in conn.execute(
            """
            SELECT id
            FROM import_batches
            WHERE LOWER(source_label) NOT LIKE '%alpaca%'
               OR LOWER(source_label) NOT LIKE '%opra%'
            """
        ).fetchall()
    ]
    if not stale_batches:
        return {"option_quote_snapshots": 0, "import_batches": 0}
    placeholders = ", ".join("?" for _ in stale_batches)
    quote_count = int(
        conn.execute(
            f"SELECT COUNT(*) FROM option_quote_snapshots WHERE source_batch_id IN ({placeholders})",
            stale_batches,
        ).fetchone()[0]
    )
    if execute:
        conn.execute(
            f"DELETE FROM option_quote_snapshots WHERE source_batch_id IN ({placeholders})",
            stale_batches,
        )
        conn.execute(
            f"DELETE FROM import_batches WHERE id IN ({placeholders})",
            stale_batches,
        )
        conn.commit()
    return {"option_quote_snapshots": quote_count, "import_batches": len(stale_batches)}


def _print_results(label: str, results: dict[str, int]) -> None:
    print(label)
    for key, value in results.items():
        print(f"  {key}: {value}")


def main(argv: list[str] | None = None) -> int:
    load_local_env(ROOT)
    parser = argparse.ArgumentParser(
        description="Purge non-Alpaca market-data cache rows."
    )
    parser.add_argument("--market-db", default=os.getenv("MARKET_DATA_DB_PATH") or str(mds.DEFAULT_MARKET_DATA_DB_PATH))
    parser.add_argument("--historical-options-db", default=os.getenv("HISTORICAL_OPTIONS_DB_PATH") or str(hos.DEFAULT_HISTORICAL_OPTIONS_DB_PATH))
    parser.add_argument("--execute", action="store_true", help="Actually delete rows. Default is dry-run.")
    parser.add_argument("--backup", action="store_true", help="Create .before-alpaca-purge DB backups before deleting rows.")
    args = parser.parse_args(argv)

    market_db = Path(args.market_db)
    historical_db = Path(args.historical_options_db)
    mode = "execute" if args.execute else "dry-run"
    print(f"mode={mode}")

    if market_db.exists():
        previous_market_db = os.environ.get("MARKET_DATA_DB_PATH")
        os.environ["MARKET_DATA_DB_PATH"] = str(market_db)
        try:
            mds._SCHEMA_READY.discard(str(market_db))
            mds._ensure_schema()
        finally:
            if previous_market_db is None:
                os.environ.pop("MARKET_DATA_DB_PATH", None)
            else:
                os.environ["MARKET_DATA_DB_PATH"] = previous_market_db
        backup = _backup(market_db) if args.execute and args.backup else None
        with sqlite3.connect(market_db) as conn:
            market_results = _delete_market_cache(conn, execute=args.execute)
        _print_results(f"market_db={market_db}", market_results)
        if backup:
            print(f"  backup={backup}")
    else:
        print(f"market_db={market_db} missing")

    if historical_db.exists():
        hos.init_schema(historical_db)
        backup = _backup(historical_db) if args.execute and args.backup else None
        with sqlite3.connect(historical_db) as conn:
            historical_results = _delete_historical_options(conn, execute=args.execute)
        _print_results(f"historical_options_db={historical_db}", historical_results)
        if backup:
            print(f"  backup={backup}")
    else:
        print(f"historical_options_db={historical_db} missing")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
