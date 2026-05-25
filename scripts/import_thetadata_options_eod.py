from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_commodity_universe import ai_commodity_scan_tickers
from historical_options_store import (
    DAILY_QUOTE_MINUTE_ET,
    DAILY_SNAPSHOT_KIND,
    HistoricalOptionsStore,
    import_historical_option_snapshots,
)


DEFAULT_THETA_URL = "http://127.0.0.1:25510"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "options-validation" / "thetadata-eod"
DEFAULT_CORE_SYMBOLS = ("FCX", "SLV", "VRT", "VST", "ETN", "GEV", "PWR", "CCJ", "CEG")
DAILY_DATASET_KIND = "daily_parquet"
EASTERN_TZ = ZoneInfo("America/New_York")
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


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected YYYY-MM-DD date, got {value!r}") from exc


def _parse_symbol_list(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_CORE_SYMBOLS)
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


def _business_dates(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("--date-to must be on or after --date-from")
    dates: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _theta_date(value: Any) -> date:
    raw = str(value or "").strip()
    if len(raw) != 8 or not raw.isdigit():
        raise ValueError(f"Expected Theta YYYYMMDD date, got {value!r}")
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def _theta_date_arg(value: date) -> str:
    return value.strftime("%Y%m%d")


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _format_decimal(value: float | int | None, *, places: int = 4) -> str:
    if value is None:
        return ""
    rounded = round(float(value), places)
    text = f"{rounded:.{places}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _format_int(value: int | None) -> str:
    return "" if value is None else str(int(value))


def _as_of_utc_for_daily_eod(trade_date: date) -> str:
    hour = DAILY_QUOTE_MINUTE_ET // 60
    minute = DAILY_QUOTE_MINUTE_ET % 60
    local_stamp = datetime(
        trade_date.year,
        trade_date.month,
        trade_date.day,
        int(hour),
        int(minute),
        tzinfo=EASTERN_TZ,
    )
    return local_stamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _occ_contract_symbol(root: str, expiration: date, right: str, theta_strike: int) -> str:
    option_right = str(right or "").strip().upper()
    if option_right not in {"C", "P"}:
        raise ValueError(f"Unsupported option right {right!r}")
    return f"{str(root).strip().upper()}{expiration.strftime('%y%m%d')}{option_right}{int(theta_strike):08d}"


def _header_index(payload: dict[str, Any]) -> dict[str, int]:
    header = payload.get("header") if isinstance(payload, dict) else None
    columns = header.get("format") if isinstance(header, dict) else None
    if not isinstance(columns, list):
        raise ValueError("Theta payload is missing header.format")
    return {str(name): index for index, name in enumerate(columns)}


def _item_value(row: list[Any], index: dict[str, int], key: str) -> Any:
    position = index.get(key)
    if position is None or position >= len(row):
        return None
    return row[position]


def _stock_close_by_date(payload: dict[str, Any]) -> dict[date, float]:
    index = _header_index(payload)
    output: dict[date, float] = {}
    response = payload.get("response")
    if not isinstance(response, list):
        return output
    for row in response:
        if not isinstance(row, list):
            continue
        try:
            trade_date = _theta_date(_item_value(row, index, "date"))
        except ValueError:
            continue
        close = _safe_float(_item_value(row, index, "close"))
        if close is not None:
            output[trade_date] = close
    return output


def _iter_option_eod_rows(
    *,
    symbol: str,
    payload: dict[str, Any],
    min_dte: int,
    max_dte: int,
    underlying_prices: dict[date, float] | None = None,
) -> Iterable[dict[str, str]]:
    index = _header_index(payload)
    response = payload.get("response")
    if not isinstance(response, list):
        return
    underlying_lookup = underlying_prices or {}

    for item in response:
        if not isinstance(item, dict):
            continue
        contract = item.get("contract")
        ticks = item.get("ticks")
        if not isinstance(contract, dict) or not isinstance(ticks, list):
            continue

        try:
            expiration = _theta_date(contract.get("expiration"))
            theta_strike = int(contract.get("strike"))
            option_right = str(contract.get("right") or "").upper()
            contract_symbol = _occ_contract_symbol(symbol, expiration, option_right, theta_strike)
        except (TypeError, ValueError):
            continue

        option_type = "call" if option_right == "C" else "put"
        strike = theta_strike / 1000.0
        for tick in ticks:
            if not isinstance(tick, list):
                continue
            try:
                trade_date = _theta_date(_item_value(tick, index, "date"))
            except ValueError:
                continue
            dte = (expiration - trade_date).days
            if dte < min_dte or dte > max_dte:
                continue

            bid = _safe_float(_item_value(tick, index, "bid"))
            ask = _safe_float(_item_value(tick, index, "ask"))
            close = _safe_float(_item_value(tick, index, "close"))
            volume = _safe_int(_item_value(tick, index, "volume"))
            yield {
                "as_of_utc": _as_of_utc_for_daily_eod(trade_date),
                "underlying": symbol.upper(),
                "contract_symbol": contract_symbol,
                "expiry": expiration.isoformat(),
                "option_type": option_type,
                "strike": _format_decimal(strike, places=3),
                "bid": _format_decimal(bid),
                "ask": _format_decimal(ask),
                "last": _format_decimal(close),
                "iv": "",
                "underlying_price": _format_decimal(underlying_lookup.get(trade_date)),
                "volume": _format_int(volume),
                "open_interest": "",
            }


def _theta_get_json(
    session: requests.Session,
    theta_url: str,
    path: str,
    params: dict[str, Any],
    *,
    timeout: float,
) -> dict[str, Any]:
    base = theta_url.rstrip("/")
    response = session.get(f"{base}{path}", params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Theta returned a non-object response from {path}")
    if payload.get("error"):
        raise ValueError(f"Theta error from {path}: {payload['error']}")
    return payload


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _default_csv_path(output_dir: Path, symbols: list[str], date_from: date, date_to: date) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    symbol_label = "ai_commodity_core" if symbols == list(DEFAULT_CORE_SYMBOLS) else f"{len(symbols)}symbols"
    return output_dir / f"thetadata_options_eod_{symbol_label}_{date_from:%Y%m%d}_{date_to:%Y%m%d}_{stamp}.csv"


def build_thetadata_eod_import(
    *,
    symbols: list[str],
    dates: list[date],
    theta_url: str = DEFAULT_THETA_URL,
    min_dte: int = 5,
    max_dte: int = 60,
    include_underlying_price: bool = False,
    sleep_seconds: float = 3.1,
    timeout: float = 60.0,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    owns_session = session is None
    http = session or requests.Session()
    rows: list[dict[str, str]] = []
    errors: list[str] = []
    request_count = 0
    rows_by_symbol: Counter[str] = Counter()
    rows_by_date: Counter[str] = Counter()
    try:
        for symbol in symbols:
            normalized_symbol = symbol.strip().upper()
            for trade_date in dates:
                underlying_prices: dict[date, float] = {}
                if include_underlying_price:
                    try:
                        stock_payload = _theta_get_json(
                            http,
                            theta_url,
                            "/v2/hist/stock/eod",
                            {
                                "root": normalized_symbol,
                                "start_date": _theta_date_arg(trade_date),
                                "end_date": _theta_date_arg(trade_date),
                            },
                            timeout=timeout,
                        )
                        request_count += 1
                        underlying_prices = _stock_close_by_date(stock_payload)
                    except Exception as exc:
                        errors.append(f"{normalized_symbol} {trade_date}: stock EOD failed: {exc}")
                    if sleep_seconds > 0:
                        time.sleep(float(sleep_seconds))

                try:
                    option_payload = _theta_get_json(
                        http,
                        theta_url,
                        "/v2/bulk_hist/option/eod",
                        {
                            "root": normalized_symbol,
                            "exp": 0,
                            "start_date": _theta_date_arg(trade_date),
                            "end_date": _theta_date_arg(trade_date),
                        },
                        timeout=timeout,
                    )
                    request_count += 1
                except Exception as exc:
                    errors.append(f"{normalized_symbol} {trade_date}: option EOD failed: {exc}")
                    if sleep_seconds > 0:
                        time.sleep(float(sleep_seconds))
                    continue

                parsed_rows = list(
                    _iter_option_eod_rows(
                        symbol=normalized_symbol,
                        payload=option_payload,
                        min_dte=min_dte,
                        max_dte=max_dte,
                        underlying_prices=underlying_prices,
                    )
                )
                rows.extend(parsed_rows)
                rows_by_symbol[normalized_symbol] += len(parsed_rows)
                rows_by_date[trade_date.isoformat()] += len(parsed_rows)
                if sleep_seconds > 0:
                    time.sleep(float(sleep_seconds))
    finally:
        if owns_session:
            http.close()

    return {
        "symbols": symbols,
        "dates": [item.isoformat() for item in dates],
        "theta_url": theta_url,
        "request_count": request_count,
        "generated_rows": len(rows),
        "rows_by_symbol": dict(sorted(rows_by_symbol.items())),
        "rows_by_date": dict(sorted(rows_by_date.items())),
        "errors": errors,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import ThetaData local-terminal bulk option EOD chains into the validation store."
    )
    parser.add_argument("--date-from", required=True, type=_parse_iso_date, help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--date-to", required=True, type=_parse_iso_date, help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument(
        "--symbols",
        help=f"Comma-separated underlyings. Defaults to core AI commodity symbols: {','.join(DEFAULT_CORE_SYMBOLS)}.",
    )
    parser.add_argument(
        "--all-ai-commodity-scan-tickers",
        action="store_true",
        help="Use every scan-eligible symbol from data/ai-commodity-infra/universe.json.",
    )
    parser.add_argument("--theta-url", default=DEFAULT_THETA_URL)
    parser.add_argument("--min-dte", type=int, default=5)
    parser.add_argument("--max-dte", type=int, default=60)
    parser.add_argument(
        "--include-underlying-price",
        action="store_true",
        help="Also fetch stock EOD closes from Theta and attach them to every option row.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=3.1,
        help="Pause after each Theta request. Free accounts are documented around 20 requests/minute.",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--source", default="thetadata_free_eod")
    parser.add_argument("--db-path", help="Optional SQLite path override for the historical options store.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--csv-output", help="Optional exact CSV output path.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse, but do not write CSV or import rows.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = (
        ai_commodity_scan_tickers()
        if args.all_ai_commodity_scan_tickers
        else _parse_symbol_list(args.symbols)
    )
    dates = _business_dates(args.date_from, args.date_to)
    if args.min_dte < 0 or args.max_dte < args.min_dte:
        parser.error("--max-dte must be greater than or equal to --min-dte, and --min-dte cannot be negative.")
    if not dates:
        parser.error("No weekday dates were selected.")

    build = build_thetadata_eod_import(
        symbols=symbols,
        dates=dates,
        theta_url=args.theta_url,
        min_dte=int(args.min_dte),
        max_dte=int(args.max_dte),
        include_underlying_price=bool(args.include_underlying_price),
        sleep_seconds=float(args.sleep_seconds),
        timeout=float(args.timeout),
    )
    rows = list(build.pop("rows"))

    csv_path = Path(args.csv_output) if args.csv_output else _default_csv_path(
        Path(args.output_dir),
        symbols,
        args.date_from,
        args.date_to,
    )
    import_result = None
    if rows and not args.dry_run:
        _write_csv(csv_path, rows)
        import_result = import_historical_option_snapshots(
            csv_path,
            args.source,
            dataset_kind=DAILY_DATASET_KIND,
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            db_path=args.db_path,
        )

    store = HistoricalOptionsStore(args.db_path)
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
