from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
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
from supervised_scan import BULLISH_PULLBACK_SCAN_TICKERS


MARKETDATA_CHAIN_URL = "https://api.marketdata.app/v1/options/chain/{symbol}/"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "options-validation" / "marketdata-eod"
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
        return []
    symbols: list[str] = []
    seen: set[str] = set()
    for chunk in str(value).replace(";", ",").split(","):
        symbol = chunk.strip().upper()
        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    return symbols


def _merge_symbols(*groups: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group:
            symbol = str(raw or "").strip().upper()
            if symbol and symbol not in seen:
                output.append(symbol)
                seen.add(symbol)
    return output


def _read_local_marketdata_token() -> str | None:
    for name in (".env", ".env.local"):
        path = ROOT / name
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() not in {"MARKETDATA_TOKEN", "MARKETDATA_API_KEY"}:
                continue
            cleaned = value.strip()
            if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
                cleaned = cleaned[1:-1]
            if cleaned:
                return cleaned
    return None


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


def _date_from_marketdata_expiration(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and "-" in value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    parsed = _safe_float(value)
    if parsed is None:
        return None
    return datetime.fromtimestamp(parsed, tz=EASTERN_TZ).date()


def _array_value(payload: dict[str, Any], key: str, index: int) -> Any:
    values = payload.get(key)
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _iter_marketdata_rows(
    *,
    symbol: str,
    trade_date: date,
    payload: dict[str, Any],
    min_dte: int,
    max_dte: int,
) -> list[dict[str, str]]:
    symbols = payload.get("optionSymbol")
    if not isinstance(symbols, list):
        return []

    rows: list[dict[str, str]] = []
    as_of_utc = _as_of_utc_for_daily_eod(trade_date)
    for index, contract_symbol in enumerate(symbols):
        contract = str(contract_symbol or "").strip().upper()
        if not contract:
            continue
        expiration = _date_from_marketdata_expiration(_array_value(payload, "expiration", index))
        side = str(_array_value(payload, "side", index) or "").strip().lower()
        if expiration is None or side not in {"call", "put"}:
            continue
        dte = (expiration - trade_date).days
        if dte < min_dte or dte > max_dte:
            continue
        rows.append(
            {
                "as_of_utc": as_of_utc,
                "underlying": str(_array_value(payload, "underlying", index) or symbol).strip().upper(),
                "contract_symbol": contract,
                "expiry": expiration.isoformat(),
                "option_type": side,
                "strike": _format_decimal(_safe_float(_array_value(payload, "strike", index)), places=3),
                "bid": _format_decimal(_safe_float(_array_value(payload, "bid", index))),
                "ask": _format_decimal(_safe_float(_array_value(payload, "ask", index))),
                "last": _format_decimal(_safe_float(_array_value(payload, "last", index))),
                "iv": _format_decimal(_safe_float(_array_value(payload, "iv", index)), places=6),
                "underlying_price": _format_decimal(_safe_float(_array_value(payload, "underlyingPrice", index))),
                "volume": _format_int(_safe_int(_array_value(payload, "volume", index))),
                "open_interest": _format_int(_safe_int(_array_value(payload, "openInterest", index))),
            }
        )
    return rows


def _marketdata_get_json(
    session: requests.Session,
    symbol: str,
    *,
    token: str | None,
    trade_date: date,
    min_dte: int,
    max_dte: int,
    timeout: float,
) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params = {
        "date": trade_date.isoformat(),
        "from": (trade_date + timedelta(days=min_dte)).isoformat(),
        "to": (trade_date + timedelta(days=max_dte)).isoformat(),
        "nonstandard": "false",
    }
    response = session.get(
        MARKETDATA_CHAIN_URL.format(symbol=symbol),
        params=params,
        headers=headers,
        timeout=timeout,
    )
    status = int(response.status_code)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError(f"MarketData returned non-JSON status {status}") from exc
    if not isinstance(payload, dict):
        raise ValueError("MarketData returned a non-object response")
    if status not in {200, 203}:
        message = payload.get("errmsg") or payload.get("message") or response.text[:200]
        raise ValueError(f"MarketData request failed ({status}): {message}")
    if payload.get("s") == "error":
        raise ValueError(str(payload.get("errmsg") or "MarketData API error"))
    return status, payload


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _default_csv_path(output_dir: Path, symbols: list[str], date_from: date, date_to: date) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    symbol_label = f"{len(symbols)}symbols"
    if symbols == ["AAPL"]:
        symbol_label = "aapl_demo"
    return output_dir / f"marketdata_options_eod_{symbol_label}_{date_from:%Y%m%d}_{date_to:%Y%m%d}_{stamp}.csv"


def build_marketdata_eod_import(
    *,
    symbols: list[str],
    dates: list[date],
    token: str | None = None,
    allow_demo: bool = False,
    min_dte: int = 5,
    max_dte: int = 60,
    sleep_seconds: float = 0.25,
    timeout: float = 60.0,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    owns_session = session is None
    http = session or requests.Session()
    rows: list[dict[str, str]] = []
    errors: list[str] = []
    skipped_symbols: list[str] = []
    status_counts: Counter[str] = Counter()
    rows_by_symbol: Counter[str] = Counter()
    rows_by_date: Counter[str] = Counter()
    request_count = 0

    if not token and not allow_demo:
        raise ValueError("MARKETDATA_TOKEN is required unless --allow-demo is set.")

    try:
        for symbol in symbols:
            normalized_symbol = symbol.strip().upper()
            if not token and normalized_symbol != "AAPL":
                skipped_symbols.append(normalized_symbol)
                continue
            for trade_date in dates:
                try:
                    status, payload = _marketdata_get_json(
                        http,
                        normalized_symbol,
                        token=token,
                        trade_date=trade_date,
                        min_dte=min_dte,
                        max_dte=max_dte,
                        timeout=timeout,
                    )
                    request_count += 1
                    status_counts[str(status)] += 1
                except Exception as exc:
                    errors.append(f"{normalized_symbol} {trade_date}: option chain failed: {exc}")
                    if sleep_seconds > 0:
                        time.sleep(float(sleep_seconds))
                    continue

                parsed_rows = _iter_marketdata_rows(
                    symbol=normalized_symbol,
                    trade_date=trade_date,
                    payload=payload,
                    min_dte=min_dte,
                    max_dte=max_dte,
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
        "provider": "marketdata.app",
        "symbols": symbols,
        "dates": [item.isoformat() for item in dates],
        "request_count": request_count,
        "http_status_counts": dict(sorted(status_counts.items())),
        "generated_rows": len(rows),
        "rows_by_symbol": dict(sorted(rows_by_symbol.items())),
        "rows_by_date": dict(sorted(rows_by_date.items())),
        "skipped_symbols": sorted(set(skipped_symbols)),
        "errors": errors,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import MarketData.app historical EOD option chains into the validation store."
    )
    parser.add_argument("--date-from", required=True, type=_parse_iso_date, help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--date-to", required=True, type=_parse_iso_date, help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--symbols", help="Comma-separated underlyings to fetch.")
    parser.add_argument("--regular-lane", action="store_true", help="Include the main bullish pullback lane universe.")
    parser.add_argument(
        "--all-ai-commodity-scan-tickers",
        action="store_true",
        help="Include every scan-eligible symbol from data/ai-commodity-infra/universe.json.",
    )
    parser.add_argument("--min-dte", type=int, default=5)
    parser.add_argument("--max-dte", type=int, default=60)
    parser.add_argument(
        "--token",
        default=os.getenv("MARKETDATA_TOKEN") or os.getenv("MARKETDATA_API_KEY") or _read_local_marketdata_token(),
    )
    parser.add_argument(
        "--allow-demo",
        action="store_true",
        help="Allow unauthenticated MarketData demo access. This only works for AAPL option endpoints.",
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--source", default="marketdata_free_eod")
    parser.add_argument("--db-path", help="Optional SQLite path override for the historical options store.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--csv-output", help="Optional exact CSV output path.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse, but do not write CSV or import rows.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = _merge_symbols(
        _parse_symbol_list(args.symbols),
        list(BULLISH_PULLBACK_SCAN_TICKERS) if args.regular_lane else [],
        ai_commodity_scan_tickers() if args.all_ai_commodity_scan_tickers else [],
    )
    dates = _business_dates(args.date_from, args.date_to)
    if args.min_dte < 0 or args.max_dte < args.min_dte:
        parser.error("--max-dte must be greater than or equal to --min-dte, and --min-dte cannot be negative.")
    if not symbols:
        parser.error("No symbols selected. Pass --symbols, --regular-lane, or --all-ai-commodity-scan-tickers.")
    if not dates:
        parser.error("No weekday dates were selected.")

    build = build_marketdata_eod_import(
        symbols=symbols,
        dates=dates,
        token=args.token,
        allow_demo=bool(args.allow_demo),
        min_dte=int(args.min_dte),
        max_dte=int(args.max_dte),
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
        "daily_summary_all_sources": store.snapshot_summary(DAILY_SNAPSHOT_KIND, trusted_only=False),
        "trusted_daily_summary": store.snapshot_summary(DAILY_SNAPSHOT_KIND, trusted_only=True),
        "token_present": bool(args.token),
        "demo_mode": bool(not args.token and args.allow_demo),
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
        "data_trust": (import_result or {}).get("data_trust"),
        "skipped_symbols": payload["skipped_symbols"][:10],
        "skipped_symbol_count": len(payload["skipped_symbols"]),
        "errors": payload["errors"][:5],
        "trusted_daily_quote_count": payload["trusted_daily_summary"].get("quote_count"),
        "all_daily_quote_count": payload["daily_summary_all_sources"].get("quote_count"),
        "token_present": payload["token_present"],
        "demo_mode": payload["demo_mode"],
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
