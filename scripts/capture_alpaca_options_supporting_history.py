from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_commodity_universe import ai_commodity_scan_tickers  # noqa: E402
from alpaca_market_data import AlpacaMarketDataClient, alpaca_enabled  # noqa: E402
from historical_options_store import DAILY_SNAPSHOT_KIND  # noqa: E402
from scripts.capture_alpaca_opra_daily_snapshots import load_env_file  # noqa: E402


DEFAULT_DB_PATH = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "ai-commodity-infra" / "alpaca-supporting-history"
PROOF_SOURCE_LABEL = "alpaca_opra_daily_snapshot"
BARS_SOURCE_LABEL = "alpaca_historical_option_bars"
TRADES_SOURCE_LABEL = "alpaca_historical_option_trades"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_symbols(value: str | None) -> list[str]:
    if not value:
        return list(ai_commodity_scan_tickers())
    symbols: list[str] = []
    seen: set[str] = set()
    for chunk in str(value).replace(";", ",").split(","):
        symbol = chunk.strip().upper()
        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    if not symbols:
        raise argparse.ArgumentTypeError("At least one symbol is required.")
    return symbols


def _parse_interval(value: str | None, *, end: bool = False) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) == 10:
        parsed_date = date.fromisoformat(raw)
        parsed = datetime.combine(parsed_date + (timedelta(days=1) if end else timedelta()), time.min, tzinfo=UTC)
        return parsed
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _date_scope(start_utc: datetime, end_utc: datetime) -> tuple[str, str]:
    inclusive_end = end_utc - timedelta(microseconds=1)
    return start_utc.date().isoformat(), inclusive_end.date().isoformat()


def _latest_alpaca_quote_date(db_path: Path, symbols: Sequence[str]) -> str | None:
    if not db_path.exists():
        return None
    clauses = [
        "b.source_label = ?",
        "q.snapshot_kind = ?",
        "q.bid > 0",
        "q.ask >= q.bid",
    ]
    params: list[Any] = [PROOF_SOURCE_LABEL, DAILY_SNAPSHOT_KIND]
    normalized_symbols = [symbol.strip().upper() for symbol in symbols if str(symbol).strip()]
    if normalized_symbols:
        placeholders = ", ".join("?" for _ in normalized_symbols)
        clauses.append(f"q.underlying IN ({placeholders})")
        params.extend(normalized_symbols)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            f"""
            SELECT MAX(q.quote_date_et) AS latest_quote_date
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE {" AND ".join(clauses)}
            """,
            params,
        ).fetchone()
    finally:
        con.close()
    latest = str((row["latest_quote_date"] if row else "") or "").strip()
    return latest or None


def resolve_capture_window(
    *,
    db_path: Path,
    symbols: Sequence[str],
    start: str | None = None,
    end: str | None = None,
) -> tuple[datetime, datetime, dict[str, Any]]:
    start_dt = _parse_interval(start)
    end_dt = _parse_interval(end, end=True)
    latest_quote_date = _latest_alpaca_quote_date(db_path, symbols)
    if start_dt is None:
        if latest_quote_date:
            start_dt = datetime.combine(date.fromisoformat(latest_quote_date), time.min, tzinfo=UTC)
        else:
            start_dt = datetime.now(UTC) - timedelta(days=1)
    if end_dt is None:
        if latest_quote_date and start is None:
            end_dt = datetime.combine(date.fromisoformat(latest_quote_date) + timedelta(days=1), time.min, tzinfo=UTC)
        else:
            end_dt = datetime.now(UTC)
    if end_dt <= start_dt:
        raise ValueError("--end must be later than --start.")
    return start_dt, end_dt, {"latest_alpaca_quote_date": latest_quote_date}


def select_supporting_contracts(
    *,
    db_path: Path,
    symbols: Sequence[str],
    start_utc: datetime,
    end_utc: datetime,
    max_contracts: int,
) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    start_date, end_date = _date_scope(start_utc, end_utc)
    normalized_symbols = [symbol.strip().upper() for symbol in symbols if str(symbol).strip()]
    clauses = [
        "b.source_label = ?",
        "q.snapshot_kind = ?",
        "q.quote_date_et BETWEEN ? AND ?",
        "q.bid > 0",
        "q.ask >= q.bid",
    ]
    params: list[Any] = [PROOF_SOURCE_LABEL, DAILY_SNAPSHOT_KIND, start_date, end_date]
    if normalized_symbols:
        placeholders = ", ".join("?" for _ in normalized_symbols)
        clauses.append(f"q.underlying IN ({placeholders})")
        params.extend(normalized_symbols)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            f"""
            SELECT
                q.contract_symbol,
                q.underlying,
                q.expiry,
                q.option_type,
                q.strike,
                q.quote_date_et,
                q.as_of_utc,
                q.bid,
                q.ask,
                q.volume,
                q.open_interest
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE {" AND ".join(clauses)}
            ORDER BY q.quote_date_et DESC, q.open_interest DESC, q.volume DESC, q.id DESC
            LIMIT ?
            """,
            [*params, max(int(max_contracts), 1) * 4],
        ).fetchall()
    finally:
        con.close()

    contracts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        contract = str(row["contract_symbol"] or "").strip().upper()
        if not contract or contract in seen:
            continue
        seen.add(contract)
        contracts.append(dict(row))
        if len(contracts) >= max(int(max_contracts), 1):
            break
    return contracts


def _chunks(values: Sequence[str], size: int = 100) -> Iterable[list[str]]:
    chunk_size = max(min(int(size), 100), 1)
    for index in range(0, len(values), chunk_size):
        yield list(values[index : index + chunk_size])


def _jsonl_rows(
    *,
    source_label: str,
    rows_by_contract: dict[str, list[dict[str, Any]]],
    contract_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for contract_symbol, rows in sorted(rows_by_contract.items()):
        contract = contract_lookup.get(contract_symbol.upper(), {})
        for row in rows:
            records.append(
                {
                    "source_label": source_label,
                    "contract_symbol": contract_symbol,
                    "underlying": contract.get("underlying"),
                    "expiry": contract.get("expiry"),
                    "option_type": contract.get("option_type"),
                    "strike": contract.get("strike"),
                    "row": row,
                }
            )
    return records


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
            count += 1
    return count


def capture_supporting_history(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    symbols: Sequence[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    max_contracts: int = 60,
    timeframe: str = "1Min",
    client: AlpacaMarketDataClient | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized_symbols = list(symbols or ai_commodity_scan_tickers())
    start_utc, end_utc, window_context = resolve_capture_window(
        db_path=db_path,
        symbols=normalized_symbols,
        start=start,
        end=end,
    )
    contracts = select_supporting_contracts(
        db_path=db_path,
        symbols=normalized_symbols,
        start_utc=start_utc,
        end_utc=end_utc,
        max_contracts=max_contracts,
    )
    contract_symbols = [contract["contract_symbol"] for contract in contracts]
    contract_lookup = {str(contract["contract_symbol"]).upper(): contract for contract in contracts}
    active_client = client or AlpacaMarketDataClient()

    bars_by_contract: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in contract_symbols}
    trades_by_contract: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in contract_symbols}
    errors: list[dict[str, Any]] = []
    if contract_symbols and not dry_run:
        for chunk in _chunks(contract_symbols):
            try:
                chunk_bars = active_client.historical_option_bars(
                    chunk,
                    start=start_utc,
                    end=end_utc,
                    timeframe=timeframe,
                )
                for symbol, rows in chunk_bars.items():
                    bars_by_contract.setdefault(symbol, []).extend(rows)
            except Exception as exc:
                errors.append({"dataset": BARS_SOURCE_LABEL, "symbols": chunk, "type": exc.__class__.__name__, "message": str(exc)})
            try:
                chunk_trades = active_client.historical_option_trades(
                    chunk,
                    start=start_utc,
                    end=end_utc,
                )
                for symbol, rows in chunk_trades.items():
                    trades_by_contract.setdefault(symbol, []).extend(rows)
            except Exception as exc:
                errors.append({"dataset": TRADES_SOURCE_LABEL, "symbols": chunk, "type": exc.__class__.__name__, "message": str(exc)})

    generated_at = _utc_now_iso()
    stamp = generated_at.replace("-", "").replace(":", "").replace("Z", "Z")
    bars_path = output_dir / f"alpaca_option_bars_supporting_{stamp}.jsonl"
    trades_path = output_dir / f"alpaca_option_trades_supporting_{stamp}.jsonl"
    bars_records = _jsonl_rows(
        source_label=BARS_SOURCE_LABEL,
        rows_by_contract=bars_by_contract,
        contract_lookup=contract_lookup,
    )
    trades_records = _jsonl_rows(
        source_label=TRADES_SOURCE_LABEL,
        rows_by_contract=trades_by_contract,
        contract_lookup=contract_lookup,
    )
    if dry_run:
        bars_written = 0
        trades_written = 0
        bars_output = None
        trades_output = None
    else:
        bars_written = _write_jsonl(bars_path, bars_records)
        trades_written = _write_jsonl(trades_path, trades_records)
        bars_output = str(bars_path)
        trades_output = str(trades_path)

    summary = {
        "generated_at_utc": generated_at,
        "provider": "alpaca:sip:opra",
        "symbols": normalized_symbols,
        "window_utc": {
            "start": start_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "end": end_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        },
        "window_context": window_context,
        "contract_count": len(contract_symbols),
        "contracts": contracts,
        "max_contracts": int(max_contracts),
        "timeframe": timeframe,
        "dry_run": bool(dry_run),
        "bars": {
            "source_label": BARS_SOURCE_LABEL,
            "row_count": sum(len(rows) for rows in bars_by_contract.values()),
            "output_path": bars_output,
            "written_rows": bars_written,
        },
        "trades": {
            "source_label": TRADES_SOURCE_LABEL,
            "row_count": sum(len(rows) for rows in trades_by_contract.values()),
            "output_path": trades_output,
            "written_rows": trades_written,
        },
        "errors": errors,
        "proof_grade_bid_ask": False,
        "proof_blocker": "alpaca_historical_option_quotes_endpoint_unavailable",
        "usage_policy": "supporting_trade_and_bar_context_only_not_entry_or_exit_fill_proof",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    if not dry_run:
        summary_path = output_dir / f"supporting_history_{stamp}.json"
        latest_path = output_dir / "latest.json"
        serialized = json.dumps(summary, indent=2)
        summary_path.write_text(serialized, encoding="utf8")
        latest_path.write_text(serialized, encoding="utf8")
        summary["summary_path"] = str(summary_path)
        summary["latest_path"] = str(latest_path)
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf8")
        latest_path.write_text(json.dumps(summary, indent=2), encoding="utf8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture Alpaca historical option bars/trades as supporting context for the AI commodity lane."
    )
    parser.add_argument("--env-file", default=str(ROOT / ".env.local"))
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--symbols", help="Comma-separated underlyings. Defaults to the full AI commodity universe.")
    parser.add_argument("--start", help="Inclusive UTC start timestamp or YYYY-MM-DD. Defaults to latest Alpaca quote date.")
    parser.add_argument("--end", help="Exclusive UTC end timestamp or inclusive YYYY-MM-DD date.")
    parser.add_argument("--max-contracts", type=int, default=60)
    parser.add_argument("--timeframe", default="1Min")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    os.environ.setdefault("OPTIONS_MARKET_DATA_PROVIDER", "alpaca")
    os.environ.setdefault("ALPACA_STOCK_FEED", "sip")
    os.environ.setdefault("ALPACA_OPTIONS_FEED", "opra")
    if not args.dry_run and not alpaca_enabled():
        raise SystemExit("Alpaca market data is not enabled/configured.")

    summary = capture_supporting_history(
        db_path=Path(args.db_path),
        output_dir=Path(args.output_dir),
        symbols=_parse_symbols(args.symbols),
        start=args.start,
        end=args.end,
        max_contracts=int(args.max_contracts),
        timeframe=args.timeframe,
        dry_run=bool(args.dry_run),
    )
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            json.dumps(
                {
                    "contract_count": summary["contract_count"],
                    "bars": summary["bars"],
                    "trades": summary["trades"],
                    "proof_grade_bid_ask": summary["proof_grade_bid_ask"],
                    "proof_blocker": summary["proof_blocker"],
                    "latest_path": summary.get("latest_path"),
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
