from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_options_store import (  # noqa: E402
    DAILY_SNAPSHOT_KIND,
    INTRADAY_SNAPSHOT_KIND,
    import_historical_option_snapshots,
)
from scripts.import_thetadata_options_nbbo import (  # noqa: E402
    DAILY_DATASET_KIND,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SOURCE_LABEL,
    DEFAULT_THETA_URL,
    INTRADAY_DATASET_KIND,
    _default_csv_path,
    _write_csv,
    build_thetadata_nbbo_import,
)


DEFAULT_DB_PATH = ROOT / "data" / "options-validation" / "options_history.db"


def _parse_symbol_list(value: str | None) -> set[str] | None:
    if not value:
        return None
    symbols = {item.strip().upper() for item in value.replace(";", ",").split(",") if item.strip()}
    return symbols or None


def _candidate_pairs(run_path: Path, *, symbols: set[str] | None, right: str | None) -> list[tuple[str, date, str]]:
    payload = json.loads(run_path.read_text(encoding="utf8"))
    rows = list(payload.get("unpriced_trades") or []) + list(payload.get("trades") or [])
    pairs: set[tuple[str, date, str]] = set()
    for row in rows:
        symbol = str(row.get("ticker") or row.get("underlying") or "").strip().upper()
        raw_date = str(row.get("date") or row.get("entry_date") or "").strip()[:10]
        raw_right = str(right or row.get("type") or row.get("option_type") or "").strip().lower()
        if raw_right in {"call", "c"}:
            normalized_right = "call"
        elif raw_right in {"put", "p"}:
            normalized_right = "put"
        else:
            continue
        if not symbol or not raw_date:
            continue
        if symbols is not None and symbol not in symbols:
            continue
        pairs.add((symbol, date.fromisoformat(raw_date), normalized_right))
    return sorted(pairs, key=lambda item: (item[1], item[0], item[2]))


def _existing_pairs(
    *,
    db_path: Path,
    pairs: list[tuple[str, date, str]],
    source_label: str,
    snapshot_kind: str,
    min_rows_per_pair: int,
) -> set[tuple[str, date, str]]:
    if not pairs or not db_path.exists():
        return set()
    dates = sorted({item[1].isoformat() for item in pairs})
    symbols = sorted({item[0] for item in pairs})
    rights = sorted({item[2] for item in pairs})
    existing: set[tuple[str, date, str]] = set()
    with sqlite3.connect(db_path) as conn:
        for date_idx in range(0, len(dates), 50):
            date_chunk = dates[date_idx : date_idx + 50]
            date_placeholders = ",".join("?" for _ in date_chunk)
            symbol_placeholders = ",".join("?" for _ in symbols)
            right_placeholders = ",".join("?" for _ in rights)
            rows = conn.execute(
                f"""
                SELECT oq.underlying, oq.quote_date_et, oq.option_type, COUNT(*) AS row_count
                FROM option_quote_snapshots oq
                JOIN import_batches ib ON ib.id = oq.source_batch_id
                WHERE ib.source_label = ?
                  AND ib.data_trust = 'trusted'
                  AND oq.snapshot_kind = ?
                  AND oq.quote_date_et IN ({date_placeholders})
                  AND oq.underlying IN ({symbol_placeholders})
                  AND oq.option_type IN ({right_placeholders})
                  AND oq.bid IS NOT NULL
                  AND oq.ask IS NOT NULL
                  AND oq.bid > 0
                  AND oq.ask >= oq.bid
                GROUP BY oq.underlying, oq.quote_date_et, oq.option_type
                HAVING row_count >= ?
                """,
                [
                    source_label,
                    snapshot_kind,
                    *date_chunk,
                    *symbols,
                    *rights,
                    int(min_rows_per_pair),
                ],
            ).fetchall()
            for symbol, quote_date, option_type, _row_count in rows:
                existing.add((str(symbol).upper(), date.fromisoformat(str(quote_date)), str(option_type).lower()))
    return existing


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import ThetaData NBBO chains for replay candidate ticker/date/right pairs."
    )
    parser.add_argument("run_path", type=Path)
    parser.add_argument("--symbols", help="Optional comma-separated symbol allowlist.")
    parser.add_argument("--right", choices=("call", "put"), help="Override candidate side.")
    parser.add_argument("--theta-url", default=DEFAULT_THETA_URL)
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--source", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument(
        "--snapshot-kind",
        default=INTRADAY_SNAPSHOT_KIND,
        choices=(DAILY_SNAPSHOT_KIND, INTRADAY_SNAPSHOT_KIND),
    )
    parser.add_argument("--start-time", default="10:10:00")
    parser.add_argument("--end-time", default="10:25:00")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--min-dte", type=int, default=0)
    parser.add_argument("--max-dte", type=int, default=60)
    parser.add_argument("--strike-range", type=int, default=35)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--min-existing-rows-per-pair", type=int, default=20)
    parser.add_argument("--max-pairs", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = _parse_symbol_list(args.symbols)
    db_path = Path(args.db_path)
    output_dir = Path(args.output_dir)
    run_path = args.run_path.resolve()
    pairs = _candidate_pairs(run_path, symbols=symbols, right=args.right)
    if int(args.max_pairs or 0) > 0:
        pairs = pairs[: int(args.max_pairs)]
    existing = _existing_pairs(
        db_path=db_path,
        pairs=pairs,
        source_label=args.source,
        snapshot_kind=args.snapshot_kind,
        min_rows_per_pair=max(1, int(args.min_existing_rows_per_pair)),
    )
    missing_pairs = [pair for pair in pairs if pair not in existing]

    grouped: dict[tuple[date, str], list[str]] = defaultdict(list)
    for symbol, trade_date, option_right in missing_pairs:
        grouped[(trade_date, option_right)].append(symbol)

    run_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    progress_path = output_dir / f"run_candidate_chain_import_{run_stamp}.jsonl"
    latest_progress_path = output_dir / "run_candidate_chain_import_latest.jsonl"
    latest_progress_path.parent.mkdir(parents=True, exist_ok=True)
    latest_progress_path.write_text("", encoding="utf8")

    dataset_kind = DAILY_DATASET_KIND if args.snapshot_kind == DAILY_SNAPSHOT_KIND else INTRADAY_DATASET_KIND
    totals: dict[str, Any] = {
        "started_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "run_path": str(run_path),
        "candidate_pair_count": len(pairs),
        "existing_pair_count": len(existing),
        "missing_pair_count": len(missing_pairs),
        "progress_path": str(progress_path),
        "latest_progress_path": str(latest_progress_path),
        "request_count": 0,
        "generated_rows": 0,
        "imported_rows": 0,
        "duplicate_rows": 0,
        "rejected_rows": 0,
        "errors": [],
    }

    for (trade_date, option_right), date_symbols in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        started = time.time()
        date_symbols = sorted(set(date_symbols))
        build = build_thetadata_nbbo_import(
            symbols=date_symbols,
            dates=[trade_date],
            theta_url=args.theta_url,
            interval=args.interval,
            start_time=args.start_time,
            end_time=args.end_time,
            min_dte=int(args.min_dte),
            max_dte=int(args.max_dte),
            strike_range=int(args.strike_range),
            right=option_right,
            sleep_seconds=float(args.sleep_seconds),
            timeout=float(args.timeout),
        )
        rows = list(build.pop("rows"))
        import_result = None
        csv_path = None
        if rows and not args.dry_run:
            csv_path = _default_csv_path(output_dir, date_symbols, trade_date, trade_date, args.interval)
            _write_csv(csv_path, rows)
            import_result = import_historical_option_snapshots(
                csv_path,
                args.source,
                dataset_kind=dataset_kind,
                snapshot_kind=args.snapshot_kind,
                db_path=db_path,
            )

        totals["request_count"] += int(build.get("request_count") or 0)
        totals["generated_rows"] += int(build.get("generated_rows") or 0)
        totals["imported_rows"] += int((import_result or {}).get("imported_rows") or 0)
        totals["duplicate_rows"] += int((import_result or {}).get("duplicate_rows") or 0)
        totals["rejected_rows"] += int((import_result or {}).get("rejected_rows") or 0)
        totals["errors"].extend(build.get("errors") or [])
        event = {
            "event": "date_right_imported" if rows else "date_right_no_rows",
            "date": trade_date.isoformat(),
            "right": option_right,
            "symbol_count": len(date_symbols),
            "symbols": date_symbols,
            "request_count": build.get("request_count"),
            "generated_rows": build.get("generated_rows"),
            "rows_by_symbol": build.get("rows_by_symbol"),
            "skipped_rows": build.get("skipped_rows"),
            "errors": build.get("errors"),
            "csv_path": str(csv_path) if csv_path else None,
            "import_result": import_result,
            "elapsed_seconds": round(time.time() - started, 2),
            "at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        _append_jsonl(progress_path, event)
        _append_jsonl(latest_progress_path, event)

    totals["completed_at_utc"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    print(json.dumps(totals, indent=2, sort_keys=True) if args.json else json.dumps(totals, sort_keys=True))
    return 0 if not totals["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
