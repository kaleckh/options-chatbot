from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "options-validation" / "options_history.db"


def _dir_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "file_count": 0, "bytes": 0, "largest_files": []}
    files: list[tuple[int, Path]] = []
    for item in path.rglob("*"):
        if item.is_file():
            try:
                files.append((item.stat().st_size, item))
            except OSError:
                continue
    return {
        "path": str(path),
        "exists": True,
        "file_count": len(files),
        "bytes": sum(size for size, _ in files),
        "largest_files": [
            {"path": str(file_path), "bytes": size}
            for size, file_path in sorted(files, reverse=True)[:15]
        ],
    }


def _index_columns(conn: sqlite3.Connection, table: str) -> dict[str, list[str]]:
    indexes: dict[str, list[str]] = {}
    for row in conn.execute(f"PRAGMA index_list({table})"):
        index_name = str(row[1])
        indexes[index_name] = [str(info[2]) for info in conn.execute(f"PRAGMA index_info({index_name})")]
    return indexes


def audit_options_db(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"db_path": str(db_path), "exists": False}
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        quote_count = int(conn.execute("SELECT COUNT(*) FROM option_quote_snapshots").fetchone()[0])
        batch_count = int(conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0])
        coverage = dict(
            conn.execute(
                """
                SELECT
                    MIN(quote_date_et) AS min_quote_date_et,
                    MAX(quote_date_et) AS max_quote_date_et,
                    COUNT(DISTINCT quote_date_et) AS quote_dates,
                    COUNT(DISTINCT underlying) AS underlyings,
                    COUNT(DISTINCT contract_symbol) AS contracts
                FROM option_quote_snapshots
                """
            ).fetchone()
        )
        source_batches = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    source_label,
                    data_trust,
                    dataset_kind,
                    COUNT(*) AS batches,
                    SUM(total_rows) AS total_rows,
                    SUM(imported_rows) AS imported_rows,
                    SUM(duplicate_rows) AS duplicate_rows,
                    SUM(rejected_rows) AS rejected_rows,
                    MAX(imported_at_utc) AS latest_imported_at_utc
                FROM import_batches
                GROUP BY source_label, data_trust, dataset_kind
                ORDER BY batches DESC, imported_rows DESC
                """
            )
        ]
        quote_sources = [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    b.source_label,
                    b.data_trust,
                    q.snapshot_kind,
                    COUNT(*) AS quote_rows,
                    COUNT(DISTINCT q.underlying) AS underlyings,
                    COUNT(DISTINCT q.quote_date_et) AS quote_dates
                FROM option_quote_snapshots q
                JOIN import_batches b
                  ON b.id = q.source_batch_id
                GROUP BY b.source_label, b.data_trust, q.snapshot_kind
                ORDER BY quote_rows DESC
                """
            )
        ]
        return {
            "db_path": str(db_path),
            "exists": True,
            "db_bytes": db_path.stat().st_size,
            "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
            "page_count": conn.execute("PRAGMA page_count").fetchone()[0],
            "page_size": conn.execute("PRAGMA page_size").fetchone()[0],
            "quote_count": quote_count,
            "batch_count": batch_count,
            "coverage": coverage,
            "source_batches": source_batches,
            "quote_sources": quote_sources,
            "indexes": {
                "option_quote_snapshots": _index_columns(conn, "option_quote_snapshots"),
                "import_batches": _index_columns(conn, "import_batches"),
            },
        }
    finally:
        conn.close()


def build_report(db_path: Path) -> dict[str, Any]:
    data_roots = [
        ROOT / "data" / "options-validation",
        ROOT / "data" / "profitability-lab",
        ROOT / "data" / "options-lanes",
        ROOT / "data" / "forward-tracking",
    ]
    db = audit_options_db(db_path)
    recommendations: list[str] = []
    if db.get("exists"):
        indexes = db.get("indexes", {})
        quote_indexes = indexes.get("option_quote_snapshots", {})
        batch_indexes = indexes.get("import_batches", {})
        if "idx_option_quotes_source_batch_snapshot_date" not in quote_indexes:
            recommendations.append("Create idx_option_quotes_source_batch_snapshot_date for source/trust-scoped audits.")
        if "idx_import_batches_source_trust_kind" not in batch_indexes:
            recommendations.append("Create idx_import_batches_source_trust_kind for source/trust/kind filtering.")
        recommendations.append("Treat data/options-validation/options_history.db as the central quote source of truth.")
        recommendations.append("Treat CSV/parquet files under data/options-validation/*/imports as raw import artifacts, not query sources.")
        recommendations.append("Keep run JSON under data/options-validation/runs and robustness reports under data/profitability-lab as reproducibility artifacts.")
    return {
        "db": db,
        "data_roots": [_dir_summary(root) for root in data_roots],
        "recommendations": recommendations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit options quote data storage and centralization.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_report(Path(args.db_path))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        db = report["db"]
        print(f"DB: {db.get('db_path')} ({db.get('quote_count', 0):,} quote rows)")
        print("Recommendations:")
        for item in report["recommendations"]:
            print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
