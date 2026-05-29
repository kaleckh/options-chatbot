from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_options_store import (
    DAILY_SNAPSHOT_KIND,
    INTRADAY_SNAPSHOT_KIND,
    import_historical_option_snapshots,
)
from scripts.import_thetadata_options_nbbo import (
    DAILY_DATASET_KIND,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SOURCE_LABEL,
    DEFAULT_THETA_URL,
    INTRADAY_DATASET_KIND,
    _business_dates,
    _default_csv_path,
    _write_csv,
    build_thetadata_nbbo_import,
)
from supervised_scan import BULLISH_PULLBACK_SCAN_TICKERS


DEFAULT_DB_PATH = ROOT / "data" / "options-validation" / "options_history.db"


def _parse_date(value: str) -> date:
    return date.fromisoformat(str(value).strip())


def _parse_minute_et(value: str) -> int:
    parts = str(value).strip().split(":")
    if len(parts) < 2:
        raise ValueError(f"Invalid time: {value!r}")
    return int(parts[0]) * 60 + int(parts[1])


def _target_dates(*, end: date, count: int) -> list[date]:
    cursor = end
    selected: list[date] = []
    while len(selected) < int(count):
        dates = _business_dates(cursor, cursor)
        if dates:
            selected.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(selected))


def _existing_pairs(
    *,
    db_path: Path,
    dates: list[date],
    symbols: list[str],
    source_label: str,
    snapshot_kind: str,
    min_rows_per_pair: int,
    quote_minute_et: int | None = None,
) -> set[tuple[str, str]]:
    if not db_path.exists():
        return set()
    date_values = [item.isoformat() for item in dates]
    if not date_values or not symbols:
        return set()
    existing: set[tuple[str, str]] = set()
    with sqlite3.connect(db_path) as conn:
        for idx in range(0, len(date_values), 50):
            chunk = date_values[idx : idx + 50]
            date_placeholders = ",".join("?" for _ in chunk)
            symbol_placeholders = ",".join("?" for _ in symbols)
            params: list[Any] = [
                source_label,
                snapshot_kind,
                *chunk,
                *symbols,
            ]
            minute_filter = ""
            if quote_minute_et is not None:
                minute_filter = "AND oq.quote_minute_et = ?"
                params.append(int(quote_minute_et))
            rows = conn.execute(
                f"""
                SELECT oq.quote_date_et, oq.underlying, COUNT(*) AS row_count
                FROM option_quote_snapshots oq
                JOIN import_batches ib ON ib.id = oq.source_batch_id
                WHERE ib.source_label = ?
                  AND oq.snapshot_kind = ?
                  AND oq.quote_date_et IN ({date_placeholders})
                  AND oq.underlying IN ({symbol_placeholders})
                  {minute_filter}
                GROUP BY oq.quote_date_et, oq.underlying
                HAVING row_count >= ?
                """,
                [*params, int(min_rows_per_pair)],
            ).fetchall()
            for quote_date, symbol, _row_count in rows:
                existing.add((str(quote_date), str(symbol).upper()))
    return existing


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resumable last-chance ThetaData NBBO backfill for the main bullish pullback lane."
    )
    parser.add_argument("--end-date", type=_parse_date, default=date(2026, 5, 22))
    parser.add_argument("--target-dates", type=int, default=110)
    parser.add_argument("--symbols", default=",".join(BULLISH_PULLBACK_SCAN_TICKERS))
    parser.add_argument("--theta-url", default=DEFAULT_THETA_URL)
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--source", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument(
        "--snapshot-kind",
        default=DAILY_SNAPSHOT_KIND,
        choices=(DAILY_SNAPSHOT_KIND, INTRADAY_SNAPSHOT_KIND),
    )
    parser.add_argument("--start-time", default="15:55:00")
    parser.add_argument("--end-time", default="15:55:00")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--min-dte", type=int, default=0)
    parser.add_argument("--max-dte", type=int, default=60)
    parser.add_argument("--strike-range", type=int, default=25)
    parser.add_argument("--right", choices=("call", "put", "both"), default="call")
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument(
        "--min-existing-rows-per-pair",
        type=int,
        default=20,
        help="Treat a symbol/date as complete only after this many rows exist for this source and snapshot kind.",
    )
    parser.add_argument("--max-dates", type=int, help="Optional cap for this run, useful for smoke tests.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = [item.strip().upper() for item in str(args.symbols).split(",") if item.strip()]
    dates = _target_dates(end=args.end_date, count=max(1, int(args.target_dates)))
    if args.max_dates:
        dates = dates[: max(1, int(args.max_dates))]

    db_path = Path(args.db_path)
    output_dir = Path(args.output_dir)
    run_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    progress_path = output_dir / f"main_lane_last_chance_progress_{run_stamp}.jsonl"
    latest_progress_path = output_dir / "main_lane_last_chance_progress_latest.jsonl"
    latest_progress_path.parent.mkdir(parents=True, exist_ok=True)
    latest_progress_path.write_text("", encoding="utf8")
    existing = _existing_pairs(
        db_path=db_path,
        dates=dates,
        symbols=symbols,
        source_label=args.source,
        snapshot_kind=args.snapshot_kind,
        min_rows_per_pair=max(1, int(args.min_existing_rows_per_pair)),
        quote_minute_et=(
            _parse_minute_et(args.start_time)
            if str(args.start_time).strip() == str(args.end_time).strip()
            else None
        ),
    )
    dataset_kind = DAILY_DATASET_KIND if args.snapshot_kind == DAILY_SNAPSHOT_KIND else INTRADAY_DATASET_KIND

    totals: dict[str, Any] = {
        "started_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "progress_path": str(progress_path),
        "latest_progress_path": str(latest_progress_path),
        "date_count": len(dates),
        "symbol_count": len(symbols),
        "request_count": 0,
        "generated_rows": 0,
        "imported_rows": 0,
        "duplicate_rows": 0,
        "rejected_rows": 0,
        "skipped_existing_pairs": len(existing),
        "errors": [],
    }

    for trade_date in dates:
        missing_symbols = [
            symbol for symbol in symbols if (trade_date.isoformat(), symbol) not in existing
        ]
        if not missing_symbols:
            event = {
                "event": "date_skipped_existing",
                "date": trade_date.isoformat(),
                "missing_symbol_count": 0,
                "at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
            _append_jsonl(progress_path, event)
            _append_jsonl(latest_progress_path, event)
            continue

        started = time.time()
        build = build_thetadata_nbbo_import(
            symbols=missing_symbols,
            dates=[trade_date],
            theta_url=args.theta_url,
            interval=args.interval,
            start_time=args.start_time,
            end_time=args.end_time,
            min_dte=int(args.min_dte),
            max_dte=int(args.max_dte),
            strike_range=int(args.strike_range),
            right=args.right,
            sleep_seconds=float(args.sleep_seconds),
            timeout=float(args.timeout),
        )
        rows = list(build.pop("rows"))
        import_result = None
        csv_path = None
        if rows and not args.dry_run:
            csv_path = _default_csv_path(
                output_dir,
                missing_symbols,
                trade_date,
                trade_date,
                args.interval,
            )
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
            "event": "date_imported" if rows else "date_no_rows",
            "date": trade_date.isoformat(),
            "missing_symbol_count": len(missing_symbols),
            "missing_symbols": missing_symbols,
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
    if args.json:
        print(json.dumps(totals, indent=2, sort_keys=True))
    else:
        print(json.dumps(totals, indent=2, sort_keys=True))
    return 0 if not totals["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
