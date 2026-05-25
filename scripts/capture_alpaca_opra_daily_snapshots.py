from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_commodity_universe import ai_commodity_scan_tickers  # noqa: E402
from alpaca_market_data import (  # noqa: E402
    ALPACA_OPTIONS_SOURCE,
    AlpacaMarketDataClient,
    alpaca_enabled,
    primary_provider_label,
    _chain_from_alpaca,
)
from historical_options_store import (  # noqa: E402
    DAILY_SNAPSHOT_KIND,
    HistoricalOptionsStore,
    import_historical_option_snapshots,
)
from us_equity_market_calendar import (  # noqa: E402
    is_us_equity_market_day as _is_us_equity_market_day,
    previous_market_day as _previous_market_day,
)


EASTERN_TZ = ZoneInfo("America/New_York")
DEFAULT_OUTPUT_DIR = ROOT / "data" / "options-validation" / "alpaca-opra-daily"
DEFAULT_HISTORICAL_DB_PATH = ROOT / "data" / "options-validation" / "options_history.db"
DAILY_DATASET_KIND = "daily_parquet"
SNAPSHOT_CAPTURABLE_AFTER_ET = datetime_time(16, 20)
CSV_FIELDNAMES = [
    "as_of_utc",
    "underlying",
    "contract_symbol",
    "expiry",
    "option_type",
    "strike",
    "bid",
    "ask",
    "last",
    "iv",
    "underlying_price",
    "volume",
    "open_interest",
]


def _parse_symbol_list(value: str | None) -> list[str]:
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


def load_env_file(path: Path) -> dict[str, str]:
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded
    for raw_line in path.read_text(encoding="utf8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def _parse_utc_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _target_trade_date(now_utc: datetime) -> date:
    now_et = now_utc.astimezone(EASTERN_TZ)
    if _is_us_equity_market_day(now_et.date()) and now_et.time() >= SNAPSHOT_CAPTURABLE_AFTER_ET:
        return now_et.date()
    return _previous_market_day(now_et.date())


def parse_target_trade_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    return date.fromisoformat(raw[:10])


def resolve_target_trade_date(
    *,
    now_utc: datetime,
    requested_target_date: str | date | None = None,
) -> date:
    inferred = _target_trade_date(now_utc)
    target = parse_target_trade_date(requested_target_date) or inferred
    if not _is_us_equity_market_day(target):
        raise ValueError(f"Target date {target.isoformat()} is not a US equity market trading date.")
    if target > inferred:
        raise ValueError(
            f"Target date {target.isoformat()} is later than the latest snapshot-capturable trade date "
            f"{inferred.isoformat()}."
        )
    return target


def _default_csv_path(output_dir: Path, symbols: list[str], target_date: date) -> Path:
    label = "ai_commodity_scan" if symbols == list(ai_commodity_scan_tickers()) else f"{len(symbols)}symbols"
    return output_dir / f"alpaca_opra_daily_{label}_{target_date.isoformat()}.csv"


def _extract_underlying_price(client: AlpacaMarketDataClient, symbol: str) -> float | None:
    try:
        bar = client.latest_stock_bar(symbol)
    except Exception:
        return None
    for key in ("c", "close", "price", "last"):
        value = bar.get(key) if isinstance(bar, dict) else None
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _row_timestamp(row: dict[str, Any], fallback: datetime) -> datetime:
    return (
        _parse_utc_timestamp(row.get("latestQuoteTime"))
        or _parse_utc_timestamp(row.get("lastTradeDate"))
        or _parse_utc_timestamp(row.get("latestTradeDate"))
        or fallback
    )


def _option_rows_from_chain(
    *,
    symbol: str,
    underlying_price: float | None,
    chain: Any,
    captured_at_utc: datetime,
    target_date: date,
    min_dte: int,
    max_dte: int,
    require_fresh_quote_date: bool,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    rows: list[dict[str, Any]] = []
    skips: Counter[str] = Counter()
    for frame_name in ("calls", "puts"):
        frame = getattr(chain, frame_name, None)
        if frame is None or frame.empty:
            continue
        option_type = "call" if frame_name == "calls" else "put"
        for _, option in frame.iterrows():
            contract_symbol = str(option.get("contractSymbol") or "").strip().upper()
            expiry_raw = str(option.get("expiration") or "").strip()[:10]
            if not contract_symbol or not expiry_raw:
                skips["missing_contract_or_expiry"] += 1
                continue
            try:
                expiry = date.fromisoformat(expiry_raw)
            except ValueError:
                skips["invalid_expiry"] += 1
                continue
            dte = (expiry - target_date).days
            if dte < int(min_dte) or dte > int(max_dte):
                skips["outside_dte_window"] += 1
                continue

            quote_time = _row_timestamp(dict(option), captured_at_utc)
            quote_date_et = quote_time.astimezone(EASTERN_TZ).date()
            if require_fresh_quote_date and quote_date_et != target_date:
                skips["stale_quote_date"] += 1
                continue

            try:
                bid = float(option.get("bid") or 0.0)
                ask = float(option.get("ask") or 0.0)
            except (TypeError, ValueError):
                skips["invalid_bid_ask"] += 1
                continue
            if bid <= 0 or ask <= 0 or ask < bid:
                skips["non_executable_quote"] += 1
                continue

            rows.append(
                {
                    "as_of_utc": _utc_iso(quote_time),
                    "underlying": symbol.upper(),
                    "contract_symbol": contract_symbol,
                    "expiry": expiry.isoformat(),
                    "option_type": option_type,
                    "strike": float(option.get("strike") or 0.0),
                    "bid": bid,
                    "ask": ask,
                    "last": float(option.get("lastPrice") or 0.0),
                    "iv": float(option.get("impliedVolatility") or 0.0),
                    "underlying_price": underlying_price,
                    "volume": int(option.get("volume") or 0),
                    "open_interest": int(option.get("openInterest") or 0),
                }
            )
    return rows, skips


def build_alpaca_opra_daily_snapshot(
    *,
    symbols: Iterable[str],
    client: AlpacaMarketDataClient | None = None,
    captured_at_utc: datetime | None = None,
    target_date: date | None = None,
    min_dte: int = 5,
    max_dte: int = 60,
    require_fresh_quote_date: bool = True,
    sleep_seconds: float = 0.0,
) -> dict[str, Any]:
    captured_at = captured_at_utc or datetime.now(UTC)
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=UTC)
    captured_at = captured_at.astimezone(UTC)
    trade_date = target_date or _target_trade_date(captured_at)
    active_client = client or AlpacaMarketDataClient()
    normalized_symbols = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    rows: list[dict[str, Any]] = []
    rows_by_symbol: Counter[str] = Counter()
    skips_by_symbol: dict[str, dict[str, int]] = {}
    errors: list[dict[str, str]] = []
    request_count = 0

    for symbol in normalized_symbols:
        try:
            underlying_price = _extract_underlying_price(active_client, symbol)
            contracts = active_client.option_contracts(
                symbol,
                expiration_date_gte=(trade_date + timedelta(days=max(int(min_dte), 0))).isoformat(),
                expiration_date_lte=(trade_date + timedelta(days=max(int(max_dte), int(min_dte)))).isoformat(),
            )
            request_count += 2
            contracts_by_expiry: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for contract in contracts:
                expiry = str(contract.get("expiration_date") or "").strip()[:10]
                if expiry:
                    contracts_by_expiry[expiry].append(contract)

            symbol_rows: list[dict[str, Any]] = []
            symbol_skips: Counter[str] = Counter()
            for expiry, expiry_contracts in sorted(contracts_by_expiry.items()):
                snapshots: dict[str, dict[str, Any]] = {}
                for option_type in ("call", "put"):
                    snapshots.update(
                        active_client.option_chain_snapshots(
                            symbol,
                            expiration_date=expiry,
                            option_type=option_type,
                        )
                    )
                    request_count += 1
                    if sleep_seconds > 0:
                        time.sleep(float(sleep_seconds))
                chain = _chain_from_alpaca(symbol, expiry, expiry_contracts, snapshots)
                parsed_rows, parsed_skips = _option_rows_from_chain(
                    symbol=symbol,
                    underlying_price=underlying_price,
                    chain=chain,
                    captured_at_utc=captured_at,
                    target_date=trade_date,
                    min_dte=min_dte,
                    max_dte=max_dte,
                    require_fresh_quote_date=require_fresh_quote_date,
                )
                symbol_rows.extend(parsed_rows)
                symbol_skips.update(parsed_skips)

            rows.extend(symbol_rows)
            rows_by_symbol[symbol] = len(symbol_rows)
            skips_by_symbol[symbol] = dict(sorted(symbol_skips.items()))
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc), "type": exc.__class__.__name__})

    return {
        "provider": primary_provider_label(),
        "options_source": ALPACA_OPTIONS_SOURCE,
        "captured_at_utc": _utc_iso(captured_at),
        "target_date": trade_date.isoformat(),
        "symbols": normalized_symbols,
        "min_dte": int(min_dte),
        "max_dte": int(max_dte),
        "require_fresh_quote_date": bool(require_fresh_quote_date),
        "request_count": int(request_count),
        "generated_rows": len(rows),
        "rows_by_symbol": dict(sorted(rows_by_symbol.items())),
        "skips_by_symbol": skips_by_symbol,
        "errors": errors,
        "rows": rows,
    }


def write_snapshot_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in CSV_FIELDNAMES})


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture current Alpaca OPRA option-chain bid/ask snapshots into the exact replay store."
    )
    parser.add_argument("--env-file", default=str(ROOT / ".env.local"))
    parser.add_argument("--symbols", help="Comma-separated symbols. Defaults to the full AI commodity scan universe.")
    parser.add_argument(
        "--all-ai-commodity-scan-tickers",
        action="store_true",
        help="Capture every scan-eligible AI commodity symbol. This is also the default when --symbols is omitted.",
    )
    parser.add_argument("--min-dte", type=int, default=5)
    parser.add_argument("--max-dte", type=int, default=60)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--source", default="alpaca_opra_daily_snapshot")
    parser.add_argument("--target-date", help="Explicit US equity market trade date to label the OPRA snapshot, YYYY-MM-DD.")
    parser.add_argument("--db-path", help="Optional SQLite path override for the historical options store.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--csv-output", help="Optional exact CSV output path.")
    parser.add_argument(
        "--allow-stale-quote-date",
        action="store_true",
        help="Keep contracts whose latest quote timestamp is not on the target trade date.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse, but do not write CSV or import rows.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    os.environ.setdefault("OPTIONS_MARKET_DATA_PROVIDER", "alpaca")
    os.environ.setdefault("ALPACA_STOCK_FEED", "sip")
    os.environ.setdefault("ALPACA_OPTIONS_FEED", "opra")
    resolved_db_path = Path(args.db_path) if args.db_path else DEFAULT_HISTORICAL_DB_PATH
    os.environ["HISTORICAL_OPTIONS_DB_PATH"] = str(resolved_db_path)
    if not alpaca_enabled():
        raise SystemExit("Alpaca market data is not enabled/configured; refusing to capture non-Alpaca snapshots.")
    if str(os.getenv("ALPACA_OPTIONS_FEED") or "opra").strip().lower() != "opra":
        raise SystemExit("ALPACA_OPTIONS_FEED must be opra for this exact replay capture.")
    if args.min_dte < 0 or args.max_dte < args.min_dte:
        parser.error("--max-dte must be greater than or equal to --min-dte, and --min-dte cannot be negative.")
    try:
        target_date = resolve_target_trade_date(
            now_utc=datetime.now(UTC),
            requested_target_date=args.target_date,
        )
    except ValueError as exc:
        parser.error(str(exc))

    symbols = ai_commodity_scan_tickers() if args.all_ai_commodity_scan_tickers else _parse_symbol_list(args.symbols)
    build = build_alpaca_opra_daily_snapshot(
        symbols=symbols,
        target_date=target_date,
        min_dte=int(args.min_dte),
        max_dte=int(args.max_dte),
        require_fresh_quote_date=not bool(args.allow_stale_quote_date),
        sleep_seconds=float(args.sleep_seconds),
    )
    rows = list(build.pop("rows"))

    csv_path = Path(args.csv_output) if args.csv_output else _default_csv_path(
        Path(args.output_dir),
        symbols,
        date.fromisoformat(str(build["target_date"])),
    )
    import_result = None
    if rows and not args.dry_run:
        write_snapshot_csv(csv_path, rows)
        import_result = import_historical_option_snapshots(
            csv_path,
            args.source,
            dataset_kind=DAILY_DATASET_KIND,
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            db_path=resolved_db_path,
        )

    store = HistoricalOptionsStore(resolved_db_path)
    payload = {
        **build,
        "csv_path": None if args.dry_run or not rows else str(csv_path),
        "dry_run": bool(args.dry_run),
        "import_result": import_result,
        "trusted_daily_summary": store.snapshot_summary(DAILY_SNAPSHOT_KIND, trusted_only=True),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    compact = {
        "provider": payload["provider"],
        "target_date": payload["target_date"],
        "generated_rows": payload["generated_rows"],
        "request_count": payload["request_count"],
        "csv_path": payload["csv_path"],
        "imported_rows": (import_result or {}).get("imported_rows"),
        "duplicate_rows": (import_result or {}).get("duplicate_rows"),
        "errors": payload["errors"][:5],
        "trusted_daily_quote_count": payload["trusted_daily_summary"].get("quote_count"),
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
