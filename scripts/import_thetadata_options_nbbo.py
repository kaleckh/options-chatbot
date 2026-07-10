from __future__ import annotations

import argparse
import csv
import hashlib
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
from us_equity_market_calendar import (  # noqa: E402
    is_us_equity_market_day,
    us_equity_market_close_time_et,
)


DEFAULT_THETA_URL = "http://127.0.0.1:25503"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "options-validation" / "thetadata-nbbo"
DEFAULT_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
CHAIN_COMPLETENESS_STANDARD_VERSION = "regular_options_provider_chain_completeness_v1"
CHAIN_COMPLETENESS_SCOPE = (
    "every_provider_listed_contract_in_each_requested_symbol_date_time_dte_right_scope"
)
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


def _unproved_chain_completeness(*, limitation: str) -> dict[str, Any]:
    return {
        "standard_version": CHAIN_COMPLETENESS_STANDARD_VERSION,
        "required_scope": CHAIN_COMPLETENESS_SCOPE,
        "status": "not_established",
        "standard_satisfied": False,
        "selection_or_evaluation_authorized": False,
        "limitation": limitation,
        "required_chunk_proofs": [
            "provider_response_exhaustive",
            "provider_contract_identity_set_sha256",
            "trusted_database_contract_identity_set_sha256",
            "provider_eligible_quote_row_set_sha256",
            "trusted_database_eligible_quote_row_set_sha256",
            "eligible_row_set_exact",
        ],
    }


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Expected YYYY-MM-DD date, got {value!r}"
        ) from exc


def _parse_theta_expiration(value: str | None) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip()
    if len(raw) == 8 and raw.isdigit():
        try:
            parsed = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                f"Expected valid YYYYMMDD expiration, got {value!r}"
            ) from exc
        return parsed.strftime("%Y%m%d")
    try:
        parsed = date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Expected YYYYMMDD or YYYY-MM-DD expiration, got {value!r}"
        ) from exc
    return parsed.strftime("%Y%m%d")


def _parse_time(value: str) -> datetime_time:
    try:
        parsed = datetime_time.fromisoformat(str(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Expected HH:MM[:SS] time, got {value!r}"
        ) from exc
    return parsed.replace(tzinfo=None)


def _business_dates(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("--date-to must be on or after --date-from")
    dates: list[date] = []
    current = start
    while current <= end:
        if is_us_equity_market_day(current):
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _parse_symbol_list(value: str | None) -> list[str]:
    raw_symbols = (
        ai_commodity_scan_tickers()
        if not value
        else str(value).replace(";", ",").split(",")
    )
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
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_theta_timestamp(value: Any, trade_date: date) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    if "T" not in normalized and ":" in normalized:
        normalized = f"{trade_date.isoformat()}T{normalized}"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=EASTERN_TZ)
    parsed_utc = parsed.astimezone(UTC)
    if parsed_utc.astimezone(EASTERN_TZ).date() != trade_date:
        return None
    return parsed_utc


def _normalize_option_right(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"call", "c"}:
        return "call"
    if normalized in {"put", "p"}:
        return "put"
    return None


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
            rows: list[dict[str, Any]] = []
            for item in response:
                if not isinstance(item, dict):
                    continue
                contract = item.get("contract")
                data_rows = item.get("data")
                if isinstance(contract, dict) and isinstance(data_rows, list):
                    for data_row in data_rows:
                        if isinstance(data_row, dict):
                            rows.append({**contract, **data_row})
                    continue
                rows.append(item)
            return rows
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def _normalize_theta_quote_row_with_reason(
    row: dict[str, Any],
    *,
    underlying: str,
    trade_date: date,
) -> tuple[dict[str, str] | None, str | None]:
    expiration_raw = row.get("expiration") or row.get("exp")
    right_raw = row.get("right") or row.get("option_type")
    option_type = _normalize_option_right(right_raw)
    strike = _safe_float(row.get("strike"))
    bid = _safe_float(row.get("bid"))
    ask = _safe_float(row.get("ask"))
    if expiration_raw is None or strike is None:
        return None, "missing_contract_fields"
    if option_type is None:
        return None, "invalid_option_right"
    if bid is None or ask is None or bid < 0 or ask <= 0 or ask < bid:
        return None, "invalid_or_non_executable"

    try:
        expiration_token = _parse_theta_expiration(str(expiration_raw))
        expiration = datetime.strptime(str(expiration_token), "%Y%m%d").date()
    except (argparse.ArgumentTypeError, ValueError):
        return None, "invalid_expiration"
    as_of_utc = _parse_theta_timestamp(
        row.get("timestamp") or row.get("datetime"), trade_date
    )
    if as_of_utc is None:
        return None, "missing_or_invalid_provider_timestamp"
    expected_contract_symbol = _occ_contract_symbol(
        underlying, expiration, option_type, strike
    )
    contract_symbol = (
        str(row.get("contract_symbol") or row.get("contract") or "").strip().upper()
    )
    if contract_symbol and contract_symbol != expected_contract_symbol:
        return None, "contract_symbol_lineage_mismatch"
    contract_symbol = contract_symbol or expected_contract_symbol

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
    }, None


def _normalize_theta_quote_row(
    row: dict[str, Any], *, underlying: str, trade_date: date
) -> dict[str, str] | None:
    normalized, _reason = _normalize_theta_quote_row_with_reason(
        row,
        underlying=underlying,
        trade_date=trade_date,
    )
    return normalized


def _theta_get_json(
    session: requests.Session,
    theta_url: str,
    params: dict[str, Any],
    *,
    timeout: float,
) -> Any:
    response = session.get(
        f"{theta_url.rstrip('/')}/v3/option/history/quote",
        params=params,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _write_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unsupported_market_session_times(
    dates: Iterable[date],
    *,
    start_time: str,
    end_time: str,
) -> list[dict[str, Any]]:
    requested_start = _parse_time(start_time)
    requested_end = _parse_time(end_time)
    unsupported: list[dict[str, Any]] = []
    for trade_date in dates:
        close_time = us_equity_market_close_time_et(trade_date)
        if close_time is None:
            unsupported.append(
                {
                    "date": trade_date.isoformat(),
                    "reason": "market_close_time_metadata_missing",
                    "market_close_time_et": None,
                    "requested_start_time_et": requested_start.isoformat(),
                    "requested_end_time_et": requested_end.isoformat(),
                }
            )
            continue
        if requested_start > close_time or requested_end > close_time:
            unsupported.append(
                {
                    "date": trade_date.isoformat(),
                    "reason": "requested_time_after_market_close",
                    "market_close_time_et": close_time.isoformat(),
                    "requested_start_time_et": requested_start.isoformat(),
                    "requested_end_time_et": requested_end.isoformat(),
                }
            )
    return unsupported


def _default_csv_path(
    output_dir: Path, symbols: list[str], date_from: date, date_to: date, interval: str
) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    label = (
        "ai_commodity_scan"
        if symbols == list(ai_commodity_scan_tickers())
        else f"{len(symbols)}symbols"
    )
    return (
        output_dir
        / f"thetadata_opra_nbbo_{label}_{date_from:%Y%m%d}_{date_to:%Y%m%d}_{interval}_{stamp}.csv"
    )


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
    expiration: str | None = None,
    strike_range: int | None = None,
    right: str = "both",
    sleep_seconds: float = 0.0,
    timeout: float = 60.0,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    unsupported_sessions = unsupported_market_session_times(
        dates,
        start_time=start_time,
        end_time=end_time,
    )
    if unsupported_sessions:
        reasons = {str(item.get("reason") or "") for item in unsupported_sessions}
        preflight_errors: list[str] = []
        if "market_close_time_metadata_missing" in reasons:
            preflight_errors.append(
                "authoritative market close-time metadata is missing for a requested market session"
            )
        if "requested_time_after_market_close" in reasons:
            preflight_errors.append(
                "requested quote time is after the scheduled market close"
            )
        return {
            "status": "blocked_preflight_unsupported_market_session_time",
            "source": DEFAULT_SOURCE_LABEL,
            "theta_url": theta_url,
            "interval": interval,
            "start_time": start_time,
            "end_time": end_time,
            "symbols": list(symbols),
            "dates": [item.isoformat() for item in dates],
            "expiration": expiration,
            "min_dte": int(min_dte),
            "max_dte": int(max_dte),
            "strike_range": strike_range,
            "right": right,
            "expected_request_count": len(symbols) * len(dates),
            "request_count": 0,
            "successful_request_count": 0,
            "failed_request_count": 0,
            "empty_request_count": 0,
            "request_surface_complete": False,
            "generated_rows": 0,
            "rows_by_symbol": {},
            "rows_by_date": {},
            "rows_by_right": {},
            "skipped_rows": {},
            "errors": preflight_errors,
            "request_errors": [],
            "empty_requests": [],
            "request_results": [],
            "unsupported_market_sessions": unsupported_sessions,
            "chain_completeness": _unproved_chain_completeness(
                limitation="preflight blocked before provider requests; no option-chain coverage claim is available"
            ),
            "rows": [],
        }
    normalized_requested_right = str(right).strip().lower()
    if normalized_requested_right not in {"call", "put", "both"}:
        raise ValueError(f"Unsupported requested option right {right!r}")
    owns_session = session is None
    http = session or requests.Session()
    rows: list[dict[str, str]] = []
    errors: list[str] = []
    request_errors: list[dict[str, str]] = []
    empty_requests: list[dict[str, str]] = []
    request_results: list[dict[str, Any]] = []
    expected_request_count = len(symbols) * len(dates)
    request_count = 0
    rows_by_symbol: Counter[str] = Counter()
    rows_by_date: Counter[str] = Counter()
    rows_by_right: Counter[str] = Counter()
    skipped_rows: Counter[str] = Counter()
    try:
        for symbol in symbols:
            normalized_symbol = str(symbol).strip().upper()
            for trade_date in dates:
                params: dict[str, Any] = {
                    "symbol": normalized_symbol,
                    "expiration": expiration or "*",
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
                    message = f"{normalized_symbol} {trade_date}: option history quote failed: {exc}"
                    errors.append(message)
                    request_errors.append(
                        {
                            "symbol": normalized_symbol,
                            "date": trade_date.isoformat(),
                            "error_type": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
                    request_results.append(
                        {
                            "request_id": f"{normalized_symbol}:{trade_date.isoformat()}",
                            "symbol": normalized_symbol,
                            "date": trade_date.isoformat(),
                            "status": "provider_request_failed",
                            "provider_request_succeeded": False,
                            "requested_right": normalized_requested_right,
                            "min_dte": int(min_dte),
                            "max_dte": int(max_dte),
                            "start_time": start_time,
                            "end_time": end_time,
                            "provider_response_row_count": 0,
                            "normalized_row_count": 0,
                            "call_row_count": 0,
                            "put_row_count": 0,
                            "lineage_rejection_count": 0,
                            "error_type": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
                    if sleep_seconds > 0:
                        time.sleep(float(sleep_seconds))
                    continue

                raw_rows = _extract_rows(payload)
                request_row_count = 0
                request_right_counts: Counter[str] = Counter()
                request_skipped: Counter[str] = Counter()
                observed_dtes: list[int] = []
                observed_timestamps: list[str] = []
                lineage_rejection_reasons = {
                    "invalid_option_right",
                    "missing_or_invalid_provider_timestamp",
                    "contract_symbol_lineage_mismatch",
                    "mismatched_option_right",
                    "provider_timestamp_outside_requested_window",
                }
                for raw_row in raw_rows:
                    normalized, rejection_reason = (
                        _normalize_theta_quote_row_with_reason(
                            raw_row,
                            underlying=normalized_symbol,
                            trade_date=trade_date,
                        )
                    )
                    if normalized is None:
                        reason = rejection_reason or "invalid_or_non_executable"
                        skipped_rows[reason] += 1
                        request_skipped[reason] += 1
                        continue
                    dte = (date.fromisoformat(normalized["expiry"]) - trade_date).days
                    if dte < int(min_dte) or dte > int(max_dte):
                        skipped_rows["outside_dte_window"] += 1
                        request_skipped["outside_dte_window"] += 1
                        continue
                    if (
                        normalized_requested_right != "both"
                        and normalized["option_type"] != normalized_requested_right
                    ):
                        skipped_rows["mismatched_option_right"] += 1
                        request_skipped["mismatched_option_right"] += 1
                        continue
                    timestamp = datetime.fromisoformat(
                        normalized["as_of_utc"].replace("Z", "+00:00")
                    )
                    local_time = (
                        timestamp.astimezone(EASTERN_TZ).time().replace(tzinfo=None)
                    )
                    if (
                        not _parse_time(start_time)
                        <= local_time
                        <= _parse_time(end_time)
                    ):
                        skipped_rows["provider_timestamp_outside_requested_window"] += 1
                        request_skipped[
                            "provider_timestamp_outside_requested_window"
                        ] += 1
                        continue
                    rows.append(normalized)
                    request_row_count += 1
                    request_right_counts[normalized["option_type"]] += 1
                    rows_by_symbol[normalized_symbol] += 1
                    rows_by_date[trade_date.isoformat()] += 1
                    rows_by_right[normalized["option_type"]] += 1
                    observed_dtes.append(dte)
                    observed_timestamps.append(normalized["as_of_utc"])

                required_rights = (
                    {"call", "put"}
                    if normalized_requested_right == "both"
                    else {normalized_requested_right}
                )
                missing_rights = sorted(
                    right
                    for right in required_rights
                    if request_right_counts[right] <= 0
                )
                lineage_rejection_count = sum(
                    request_skipped[reason] for reason in lineage_rejection_reasons
                )
                request_complete = bool(
                    request_row_count
                    and not missing_rights
                    and lineage_rejection_count == 0
                )
                request_result = {
                    "request_id": f"{normalized_symbol}:{trade_date.isoformat()}",
                    "symbol": normalized_symbol,
                    "date": trade_date.isoformat(),
                    "status": "request_complete"
                    if request_complete
                    else "request_incomplete",
                    "provider_request_succeeded": True,
                    "requested_right": normalized_requested_right,
                    "min_dte": int(min_dte),
                    "max_dte": int(max_dte),
                    "start_time": start_time,
                    "end_time": end_time,
                    "provider_response_row_count": len(raw_rows),
                    "normalized_row_count": request_row_count,
                    "call_row_count": int(request_right_counts["call"]),
                    "put_row_count": int(request_right_counts["put"]),
                    "missing_requested_rights": missing_rights,
                    "lineage_rejection_count": lineage_rejection_count,
                    "skipped_rows": dict(sorted(request_skipped.items())),
                    "observed_min_dte": min(observed_dtes) if observed_dtes else None,
                    "observed_max_dte": max(observed_dtes) if observed_dtes else None,
                    "first_provider_timestamp_utc": min(observed_timestamps)
                    if observed_timestamps
                    else None,
                    "last_provider_timestamp_utc": max(observed_timestamps)
                    if observed_timestamps
                    else None,
                }
                request_results.append(request_result)
                if not request_complete:
                    empty_requests.append(
                        {
                            "symbol": normalized_symbol,
                            "date": trade_date.isoformat(),
                            "reason": (
                                "missing_requested_option_rights"
                                if missing_rights
                                else "invalid_provider_or_contract_lineage"
                                if lineage_rejection_count
                                else "no_normalized_rows_in_requested_dte_window"
                            ),
                            "missing_requested_rights": ",".join(missing_rights),
                        }
                    )

                if sleep_seconds > 0:
                    time.sleep(float(sleep_seconds))
    finally:
        if owns_session:
            http.close()

    request_surface_complete = bool(
        expected_request_count
        and request_count == expected_request_count
        and not request_errors
        and not empty_requests
    )
    return {
        "status": "request_surface_complete"
        if request_surface_complete
        else "blocked_request_surface_incomplete",
        "source": DEFAULT_SOURCE_LABEL,
        "theta_url": theta_url,
        "interval": interval,
        "start_time": start_time,
        "end_time": end_time,
        "symbols": symbols,
        "dates": [item.isoformat() for item in dates],
        "expiration": expiration,
        "min_dte": int(min_dte),
        "max_dte": int(max_dte),
        "strike_range": strike_range,
        "right": right,
        "expected_request_count": expected_request_count,
        "request_count": request_count,
        "successful_request_count": sum(
            1 for item in request_results if item.get("status") == "request_complete"
        ),
        "failed_request_count": len(request_errors),
        "empty_request_count": len(empty_requests),
        "request_surface_complete": request_surface_complete,
        "generated_rows": len(rows),
        "rows_by_symbol": dict(sorted(rows_by_symbol.items())),
        "rows_by_date": dict(sorted(rows_by_date.items())),
        "rows_by_right": dict(sorted(rows_by_right.items())),
        "skipped_rows": dict(sorted(skipped_rows.items())),
        "errors": errors,
        "request_errors": request_errors,
        "empty_requests": empty_requests,
        "request_results": request_results,
        "unsupported_market_sessions": [],
        "chain_completeness": _unproved_chain_completeness(
            limitation=(
                "request success and executable call/put coverage do not prove an exhaustive provider chain "
                "across every listed strike and expiration"
            )
        ),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import ThetaData v3 historical OPRA NBBO option quotes into the validation store."
    )
    parser.add_argument(
        "--date-from",
        required=True,
        type=_parse_iso_date,
        help="Inclusive start date, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--date-to",
        required=True,
        type=_parse_iso_date,
        help="Inclusive end date, YYYY-MM-DD.",
    )
    parser.add_argument(
        "--symbols",
        help="Comma-separated underlyings. Defaults to the full AI commodity scan universe.",
    )
    parser.add_argument("--theta-url", default=DEFAULT_THETA_URL)
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--start-time", default="15:55:00")
    parser.add_argument("--end-time", default="15:55:00")
    parser.add_argument("--min-dte", type=int, default=5)
    parser.add_argument("--max-dte", type=int, default=60)
    parser.add_argument(
        "--expiration",
        type=_parse_theta_expiration,
        help="Optional exact option expiration for ThetaData v3 history requests, YYYYMMDD or YYYY-MM-DD.",
    )
    parser.add_argument("--strike-range", type=int)
    parser.add_argument("--right", choices=("call", "put", "both"), default="both")
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--source", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument(
        "--snapshot-kind",
        default=DAILY_SNAPSHOT_KIND,
        choices=(DAILY_SNAPSHOT_KIND, INTRADAY_SNAPSHOT_KIND),
    )
    parser.add_argument(
        "--db-path",
        help="Optional SQLite path override for the historical options store.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--csv-output", help="Optional exact CSV output path.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse, but do not write CSV or import rows.",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail before writing CSV or database rows when any requested symbol/date fails or returns no usable rows.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    _parse_time(args.start_time)
    _parse_time(args.end_time)
    if args.min_dte < 0 or args.max_dte < args.min_dte:
        parser.error(
            "--max-dte must be greater than or equal to --min-dte, and --min-dte cannot be negative."
        )
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
        expiration=args.expiration,
        strike_range=args.strike_range,
        right=args.right,
        sleep_seconds=float(args.sleep_seconds),
        timeout=float(args.timeout),
    )
    rows = list(build.pop("rows"))
    incomplete_surface = build.get("request_surface_complete") is not True
    preflight_blocked = bool(build.get("unsupported_market_sessions")) or str(
        build.get("status") or ""
    ).startswith("blocked_preflight")
    write_blocked = bool(
        preflight_blocked or (args.require_complete and incomplete_surface)
    )
    csv_path = (
        Path(args.csv_output)
        if args.csv_output
        else _default_csv_path(
            Path(args.output_dir),
            symbols,
            args.date_from,
            args.date_to,
            args.interval,
        )
    )
    dataset_kind = (
        DAILY_DATASET_KIND
        if args.snapshot_kind == DAILY_SNAPSHOT_KIND
        else INTRADAY_DATASET_KIND
    )
    import_result = None
    csv_artifact = None
    if rows and not args.dry_run and not write_blocked:
        _write_csv(csv_path, rows)
        csv_artifact = {
            "path": str(csv_path.resolve()),
            "sha256": _file_sha256(csv_path),
            "row_count": len(rows),
        }
        import_result = import_historical_option_snapshots(
            csv_path,
            args.source,
            dataset_kind=dataset_kind,
            snapshot_kind=args.snapshot_kind,
            db_path=args.db_path,
        )

    database_import_complete = bool(
        import_result
        and csv_artifact
        and import_result.get("batch_id") is not None
        and import_result.get("file_hash") == csv_artifact.get("sha256")
        and import_result.get("source_label") == args.source
        and import_result.get("data_trust") == "trusted"
        and import_result.get("dataset_kind") == dataset_kind
        and Path(str(import_result.get("input_path") or "")).resolve()
        == csv_path.resolve()
        and import_result.get("total_rows") == csv_artifact.get("row_count")
        and int(import_result.get("rejected_rows") or 0) == 0
        and int(import_result.get("imported_rows") or 0)
        + int(import_result.get("duplicate_rows") or 0)
        == csv_artifact.get("row_count")
    )
    artifact_lineage = {
        "csv_path": (csv_artifact or {}).get("path"),
        "csv_sha256": (csv_artifact or {}).get("sha256"),
        "csv_row_count": (csv_artifact or {}).get("row_count"),
        "import_batch_id": (import_result or {}).get("batch_id"),
        "import_file_hash": (import_result or {}).get("file_hash"),
        "import_db_path": (import_result or {}).get("db_path"),
        "import_source_label": (import_result or {}).get("source_label"),
        "import_data_trust": (import_result or {}).get("data_trust"),
        "database_import_complete": database_import_complete,
    }
    for request_result in build.get("request_results") or []:
        if isinstance(request_result, dict):
            request_result["artifact_lineage"] = dict(artifact_lineage)

    payload = {
        **build,
        "source": args.source,
        "csv_path": None
        if args.dry_run or not rows or write_blocked
        else str(csv_path),
        "dry_run": bool(args.dry_run),
        "require_complete": bool(args.require_complete),
        "write_blocked_by_incomplete_surface": write_blocked,
        "snapshot_kind": args.snapshot_kind,
        "dataset_kind": dataset_kind,
        "csv_artifact": csv_artifact,
        "import_result": import_result,
        "database_import_complete": database_import_complete,
    }
    exit_code = (
        1
        if preflight_blocked
        or write_blocked
        or (
            args.require_complete
            and not args.dry_run
            and not payload["database_import_complete"]
        )
        else 0
    )
    if args.json:
        print(json.dumps(payload, indent=2))
        return exit_code

    compact = {
        "status": payload["status"],
        "source": payload["source"],
        "snapshot_kind": payload["snapshot_kind"],
        "generated_rows": payload["generated_rows"],
        "expected_request_count": payload["expected_request_count"],
        "request_count": payload["request_count"],
        "failed_request_count": payload["failed_request_count"],
        "empty_request_count": payload["empty_request_count"],
        "request_surface_complete": payload["request_surface_complete"],
        "write_blocked_by_incomplete_surface": payload[
            "write_blocked_by_incomplete_surface"
        ],
        "csv_path": payload["csv_path"],
        "imported_rows": (import_result or {}).get("imported_rows"),
        "duplicate_rows": (import_result or {}).get("duplicate_rows"),
        "skipped_rows": payload["skipped_rows"],
        "errors": payload["errors"][:5],
    }
    print(json.dumps(compact, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
