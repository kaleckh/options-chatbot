from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from datetime import UTC, date, datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_commodity_universe import ai_commodity_scan_tickers  # noqa: E402
from historical_options_store import (  # noqa: E402
    DAILY_SNAPSHOT_KIND,
    INTRADAY_SNAPSHOT_KIND,
    import_historical_option_snapshots,
)


DEFAULT_THETA_URL = "http://127.0.0.1:25503"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "options-validation" / "thetadata-nbbo"
DEFAULT_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
EASTERN_TZ = ZoneInfo("America/New_York")
DAILY_DATASET_KIND = "daily_parquet"
INTRADAY_DATASET_KIND = "intraday_csv"
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


def _parse_time(value: str) -> datetime_time:
    try:
        parsed = datetime_time.fromisoformat(str(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected HH:MM[:SS] time, got {value!r}") from exc
    return parsed.replace(tzinfo=None)


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


def _parse_symbol_list(value: str | None) -> list[str]:
    raw_symbols = ai_commodity_scan_tickers() if not value else str(value).replace(";", ",").split(",")
    symbols: list[str] = []
    seen: set[str] = set()
    for item in raw_symbols:
        symbol = str(item).strip().upper()
        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    if not symbols:
        raise argparse.ArgumentTypeError("At least one symbol is required.")
    return symbols


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_decimal(value: float | int | None, *, places: int = 4) -> str:
    if value is None:
        return ""
    rounded = round(float(value), places)
    text = f"{rounded:.{places}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_theta_timestamp(value: Any, trade_date: date) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        local_stamp = datetime.combine(trade_date, datetime_time(15, 55), tzinfo=EASTERN_TZ)
        return local_stamp.astimezone(UTC)
    normalized = raw.replace("Z", "+00:00")
    if "T" not in normalized and ":" in normalized:
        normalized = f"{trade_date.isoformat()}T{normalized}"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=EASTERN_TZ)
    return parsed.astimezone(UTC)


def _occ_contract_symbol(root: str, expiration: date, right: str, strike: float) -> str:
    option_right = str(right or "").strip().upper()
    if option_right in {"CALL", "C"}:
        side = "C"
    elif option_right in {"PUT", "P"}:
        side = "P"
    else:
        raise ValueError(f"Unsupported option right {right!r}")
    strike_mills = int(round(float(strike) * 1000))
    return f"{str(root).strip().upper()}{expiration.strftime('%y%m%d')}{side}{strike_mills:08d}"


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        response = payload.get("response")
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def _normalize_theta_quote_row(row: dict[str, Any], *, underlying: str, trade_date: date) -> dict[str, str] | None:
    expiration_raw = row.get("expiration") or row.get("exp")
    right_raw = row.get("right") or row.get("option_type")
    strike = _safe_float(row.get("strike"))
    bid = _safe_float(row.get("bid"))
    ask = _safe_float(row.get("ask"))
    if expiration_raw is None or right_raw is None or strike is None:
        return None
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None

    expiration = date.fromisoformat(str(expiration_raw)[:10])
    as_of_utc = _parse_theta_timestamp(row.get("timestamp") or row.get("datetime"), trade_date)
    option_type = "call" if str(right_raw).strip().lower() in {"call", "c"} else "put"
    contract_symbol = str(row.get("contract_symbol") or row.get("contract") or "").strip().upper()
    if not contract_symbol:
        contract_symbol = _occ_contract_symbol(underlying, expiration, right_raw, strike)

    return {
        "as_of_utc": _utc_iso(as_of_utc),
        "underlying": underlying.upper(),
        "contract_symbol": contract_symbol,
        "expiry": expiration.isoformat(),
        "option_type": option_type,
        "strike": _format_decimal(strike, places=3),
        "bid": _format_decimal(bid),
        "ask": _format_decimal(ask),
        "last": "",
        "iv": "",
        "underlying_price": _format_decimal(_safe_float(row.get("underlying_price"))),
        "volume": "",
        "open_interest": "",
    }


def _theta_get_json(
    session: requests.Session,
    theta_url: str,
    params: dict[str, Any],
    *,
    timeout: float,
) -> Any:
    response = session.get(f"{theta_url.rstrip('/')}/v3/option/history/quote", params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _write_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _default_csv_path(output_dir: Path, symbols: list[str], date_from: date, date_to: date, interval: str) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    label = "ai_commodity_scan" if symbols == list(ai_commodity_scan_tickers()) else f"{len(symbols)}symbols"
    return output_dir / f"thetadata_opra_nbbo_{label}_{date_from:%Y%m%d}_{date_to:%Y%m%d}_{interval}_{stamp}.csv"


def build_thetadata_nbbo_import(
    *,
    symbols: list[str],
    dates: list[date],
    theta_url: str = DEFAULT_THETA_URL,
    interval: str = "1m",
    start_time: str = "15:55:00",
    end_time: str = "15:55:00",
    min_dte: int = 5,
    max_dte: int = 60,
    strike_range: int | None = None,
    right: str = "both",
    sleep_seconds: float = 0.0,
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
    skipped_rows: Counter[str] = Counter()
    try:
        for symbol in symbols:
            normalized_symbol = str(symbol).strip().upper()
            for trade_date in dates:
                params: dict[str, Any] = {
                    "symbol": normalized_symbol,
                    "expiration": "*",
                    "date": trade_date.strftime("%Y%m%d"),
                    "interval": interval,
                    "format": "json",
                    "start_time": start_time,
                    "end_time": end_time,
                    "max_dte": int(max_dte),
                    "right": right,
                }
                if strike_range is not None:
                    params["strike_range"] = int(strike_range)
                try:
                    payload = _theta_get_json(http, theta_url, params, timeout=timeout)
                    request_count += 1
                except Exception as exc:
                    errors.append(f"{normalized_symbol} {trade_date}: option history quote failed: {exc}")
                    if sleep_seconds > 0:
                        time.sleep(float(sleep_seconds))
                    continue

                for raw_row in _extract_rows(payload):
                    normalized = _normalize_theta_quote_row(
                        raw_row,
                        underlying=normalized_symbol,
                        trade_date=trade_date,
                    )
                    if normalized is None:
                        skipped_rows["invalid_or_non_executable"] += 1
                        continue
                    dte = (date.fromisoformat(normalized["expiry"]) - trade_date).days
                    if dte < int(min_dte) or dte > int(max_dte):
                        skipped_rows["outside_dte_window"] += 1
                        continue
                    rows.append(normalized)
                    rows_by_symbol[normalized_symbol] += 1
                    rows_by_date[trade_date.isoformat()] += 1

                if sleep_seconds > 0:
                    time.sleep(float(sleep_seconds))
    finally:
        if owns_session:
            http.close()

    return {
        "source": DEFAULT_SOURCE_LABEL,
        "theta_url": theta_url,
        "interval": interval,
        "start_time": start_time,
        "end_time": end_time,
        "symbols": symbols,
        "dates": [item.isoformat() for item in dates],
        "min_dte": int(min_dte),
        "max_dte": int(max_dte),
        "strike_range": strike_range,
        "right": right,
        "request_count": request_count,
        "generated_rows": len(rows),
        "rows_by_symbol": dict(sorted(rows_by_symbol.items())),
        "rows_by_date": dict(sorted(rows_by_date.items())),
        "skipped_rows": dict(sorted(skipped_rows.items())),
        "errors": errors,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import ThetaData v3 historical OPRA NBBO option quotes into the validation store."
    )
    parser.add_argument("--date-from", required=True, type=_parse_iso_date, help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--date-to", required=True, type=_parse_iso_date, help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--symbols", help="Comma-separated underlyings. Defaults to the full AI commodity scan universe.")
    parser.add_argument("--theta-url", default=DEFAULT_THETA_URL)
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--start-time", default="15:55:00")
    parser.add_argument("--end-time", default="15:55:00")
    parser.add_argument("--min-dte", type=int, default=5)
    parser.add_argument("--max-dte", type=int, default=60)
    parser.add_argument("--strike-range", type=int)
    parser.add_argument("--right", choices=("call", "put", "both"), default="both")
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--source", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument("--snapshot-kind", default=DAILY_SNAPSHOT_KIND, choices=(DAILY_SNAPSHOT_KIND, INTRADAY_SNAPSHOT_KIND))
    parser.add_argument("--db-path", help="Optional SQLite path override for the historical options store.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--csv-output", help="Optional exact CSV output path.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse, but do not write CSV or import rows.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    _parse_time(args.start_time)
    _parse_time(args.end_time)
    if args.min_dte < 0 or args.max_dte < args.min_dte:
        parser.error("--max-dte must be greater than or equal to --min-dte, and --min-dte cannot be negative.")
    symbols = _parse_symbol_list(args.symbols)
    dates = _business_dates(args.date_from, args.date_to)
    if not dates:
        parser.error("No weekday dates were selected.")

    build = build_thetadata_nbbo_import(
        symbols=symbols,
        dates=dates,
        theta_url=args.theta_url,
        interval=args.interval,
        start_time=args.start_time,
        end_time=args.end_time,
        min_dte=int(args.min_dte),
        max_dte=int(args.max_dte),
        strike_range=args.strike_range,
        right=args.right,
        sleep_seconds=float(args.sleep_seconds),
        timeout=float(args.timeout),
    )
    rows = list(build.pop("rows"))
    csv_path = Path(args.csv_output) if args.csv_output else _default_csv_path(
        Path(args.output_dir),
        symbols,
        args.date_from,
        args.date_to,
        args.interval,
    )
    dataset_kind = DAILY_DATASET_KIND if args.snapshot_kind == DAILY_SNAPSHOT_KIND else INTRADAY_DATASET_KIND
    import_result = None
    if rows and not args.dry_run:
        _write_csv(csv_path, rows)
        import_result = import_historical_option_snapshots(
            csv_path,
            args.source,
            dataset_kind=dataset_kind,
            snapshot_kind=args.snapshot_kind,
            db_path=args.db_path,
        )

    payload = {
        **build,
        "source": args.source,
        "csv_path": None if args.dry_run or not rows else str(csv_path),
        "dry_run": bool(args.dry_run),
        "snapshot_kind": args.snapshot_kind,
        "dataset_kind": dataset_kind,
        "import_result": import_result,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    compact = {
        "source": payload["source"],
        "snapshot_kind": payload["snapshot_kind"],
        "generated_rows": payload["generated_rows"],
        "request_count": payload["request_count"],
        "csv_path": payload["csv_path"],
        "imported_rows": (import_result or {}).get("imported_rows"),
        "duplicate_rows": (import_result or {}).get("duplicate_rows"),
        "skipped_rows": payload["skipped_rows"],
        "errors": payload["errors"][:5],
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
