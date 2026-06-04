from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_env import load_local_env
from scripts.regular_options_repair_targets import (  # noqa: E402
    contract_parts,
    filter_values,
    missing_items_from_run_paths,
    target_filters,
)

load_local_env(ROOT)

DEFAULT_DB = ROOT / "data" / "options-validation" / "options_history.db"


def _classify_contract(conn: sqlite3.Connection, *, contract_symbol: str, quote_date: str, source_labels: list[str]) -> dict[str, Any]:
    parts = contract_parts(contract_symbol)
    params: list[Any] = [parts["contract_symbol"], quote_date]
    source_clause = ""
    if source_labels:
        placeholders = ", ".join("?" for _ in source_labels)
        source_clause = f" AND b.source_label IN ({placeholders})"
        params.extend(source_labels)
    exact_count = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE q.contract_symbol = ?
          AND q.quote_date_et = ?
          AND q.bid IS NOT NULL
          AND q.ask IS NOT NULL
          AND q.bid > 0
          AND q.ask >= q.bid
          AND b.data_trust = 'trusted'
          {source_clause}
        """,
        tuple(params),
    ).fetchone()[0]
    if exact_count:
        return {**parts, "missing_quote_date": quote_date, "classification": "importer_or_lookup_missed_existing_exact_rows", "exact_row_count": int(exact_count)}

    same_expiry_params: list[Any] = [
        parts.get("underlying"),
        quote_date,
        parts.get("expiry"),
        parts.get("option_type"),
    ]
    if source_labels:
        same_expiry_params.extend(source_labels)
    same_expiry_count = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE q.underlying = ?
          AND q.quote_date_et = ?
          AND q.expiry = ?
          AND q.option_type = ?
          AND q.bid IS NOT NULL
          AND q.ask IS NOT NULL
          AND q.bid > 0
          AND q.ask >= q.bid
          AND b.data_trust = 'trusted'
          {source_clause}
        """,
        tuple(same_expiry_params),
    ).fetchone()[0]
    if same_expiry_count:
        classification = "provider_no_match_exact_contract_with_same_expiry_chain"
    else:
        classification = "no_same_expiry_chain_rows_on_missing_date"
    return {
        **parts,
        "missing_quote_date": quote_date,
        "classification": classification,
        "exact_row_count": 0,
        "same_expiry_chain_row_count": int(same_expiry_count),
    }


def classify_run(
    run_path: Path,
    *,
    db_path: Path = DEFAULT_DB,
    source_labels: list[str] | None = None,
    tickers: set[str] | None = None,
    contract_symbols: set[str] | None = None,
    quote_dates: set[str] | None = None,
) -> dict[str, Any]:
    labels = source_labels or ["thetadata_opra_nbbo_1m"]
    ticker_filter = tickers or set()
    contract_filter = contract_symbols or set()
    quote_date_filter = quote_dates or set()
    rows: list[dict[str, Any]] = []
    for item in missing_items_from_run_paths(
        [run_path],
        tickers=ticker_filter,
        contract_symbols=contract_filter,
        quote_dates=quote_date_filter,
        include_fallback_contracts=True,
    ):
        occurrence = (item.get("source_occurrences") or [{}])[0]
        rows.append(
            {
                "ticker": occurrence.get("ticker"),
                "source_field": occurrence.get("source_field"),
                "contract_symbol": item["contract_symbol"],
                "missing_quote_date": item["quote_date"].isoformat(),
            }
        )

    classified: list[dict[str, Any]] = []
    with sqlite3.connect(db_path) as conn:
        for row in rows:
            classified.append(
                {
                    **row,
                    **_classify_contract(conn, contract_symbol=row["contract_symbol"], quote_date=row["missing_quote_date"], source_labels=labels),
                }
            )
    counts = Counter(item["classification"] for item in classified)
    by_ticker = Counter(str(item.get("ticker") or "unknown") for item in classified)
    return {
        "run_path": str(run_path),
        "db_path": str(db_path),
        "source_labels": labels,
        "target_filters": target_filters(
            tickers=list(ticker_filter),
            contract_symbols=list(contract_filter),
            quote_dates=list(quote_date_filter),
        ),
        "classified_count": len(classified),
        "classification_counts": dict(counts),
        "by_ticker": dict(by_ticker),
        "classified": classified,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify unpriced exact replay contracts using local trusted option rows.")
    parser.add_argument("run_path", type=Path)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--source-labels", default="thetadata_opra_nbbo_1m")
    parser.add_argument(
        "--ticker",
        action="append",
        default=[],
        help="Limit targets to one or more comma-separated tickers. Can be repeated.",
    )
    parser.add_argument(
        "--contract-symbol",
        action="append",
        default=[],
        help="Limit targets to one or more comma-separated exact OCC contract symbols. Can be repeated.",
    )
    parser.add_argument(
        "--quote-date",
        action="append",
        default=[],
        help="Limit targets to one or more comma-separated missing quote dates in YYYY-MM-DD form. Can be repeated.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    labels = [item.strip() for item in str(args.source_labels).split(",") if item.strip()]
    report = classify_run(
        args.run_path,
        db_path=args.db_path,
        source_labels=labels,
        tickers=filter_values(args.ticker, upper=True),
        contract_symbols=filter_values(args.contract_symbol, upper=True),
        quote_dates=filter_values(args.quote_date),
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(json.dumps({k: v for k, v in report.items() if k != "classified"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
