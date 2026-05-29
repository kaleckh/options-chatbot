from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_commodity_universe import ai_commodity_scan_tickers  # noqa: E402
from historical_options_store import (  # noqa: E402
    DAILY_QUOTE_MINUTE_ET,
    DAILY_SNAPSHOT_KIND,
    HistoricalOptionsStore,
    import_historical_option_snapshots,
)
from us_equity_market_calendar import is_us_equity_market_day  # noqa: E402


SOURCE_LABEL = "onclickmedia_research_grade_eod_bidask"
SOURCE_GRADE = "research_grade_eod_bidask"
SNAPSHOT_KIND = "daily_eod"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "ai-commodity-infra" / "onclickmedia-eod"
DEFAULT_BASE_URL = "https://api.onclickmedia.com/options/"
DEFAULT_TARGET_SHARED_DATES = 100
EASTERN_TZ = "America/New_York"
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


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_date(value: Any, *, field_name: str = "date") -> date:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field_name} is required")
    return date.fromisoformat(raw[:10])


def _parse_optional_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    return date.fromisoformat(raw[:10]) if raw else None


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


def _float_or_none(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _format_decimal(value: float | int | None, *, places: int = 6) -> str:
    if value is None:
        return ""
    rounded = round(float(value), places)
    text = f"{rounded:.{places}f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _format_int(value: int | None) -> str:
    return "" if value is None else str(int(value))


def _as_of_utc_for_daily_eod(quote_date: date) -> str:
    from datetime import time
    from zoneinfo import ZoneInfo

    hour = DAILY_QUOTE_MINUTE_ET // 60
    minute = DAILY_QUOTE_MINUTE_ET % 60
    local_stamp = datetime.combine(
        quote_date,
        time(hour=int(hour), minute=int(minute)),
        tzinfo=ZoneInfo(EASTERN_TZ),
    )
    return local_stamp.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _clean_greeks(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    greeks: dict[str, float] = {}
    for key, raw in value.items():
        parsed = _float_or_none(raw)
        if parsed is not None:
            greeks[str(key)] = parsed
    return greeks or None


def _occ_contract_symbol(symbol: str, expiration: date, option_type: str, strike: float) -> str:
    root = "".join(ch for ch in str(symbol or "").upper() if ch.isalnum())
    if not root:
        raise ValueError("symbol is required")
    right = "C" if str(option_type or "").lower().startswith("c") else "P"
    strike_int = int(round(float(strike) * 1000))
    return f"{root}{expiration:%y%m%d}{right}{strike_int:08d}"


def _quality_flags(row: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    bid = row.get("bid")
    ask = row.get("ask")
    volume = row.get("volume")
    open_interest = row.get("open_interest")
    if bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid:
        flags.append("executable_bid_ask")
    else:
        flags.append("non_executable_bid_ask")
        if bid is None:
            flags.append("missing_bid")
        elif bid <= 0:
            flags.append("zero_bid")
        if ask is None:
            flags.append("missing_ask")
        elif ask <= 0:
            flags.append("zero_ask")
        if bid is not None and ask is not None and ask < bid:
            flags.append("crossed_bid_ask")
    if not volume:
        flags.append("zero_or_missing_volume")
    if not open_interest:
        flags.append("zero_or_missing_open_interest")
    if row.get("greeks"):
        flags.append("has_greeks")
    return flags


def normalize_chain_row(
    symbol: str,
    quote_date: date,
    raw_row: dict[str, Any],
    *,
    retrieved_at_utc: str,
) -> dict[str, Any]:
    expiration = _parse_date(raw_row.get("expiration"), field_name="expiration")
    option_type_raw = str(raw_row.get("type") or "").strip().lower()
    if option_type_raw not in {"call", "put", "c", "p"}:
        raise ValueError("type must be call/put")
    option_type = "call" if option_type_raw in {"call", "c"} else "put"
    strike = _float_or_none(raw_row.get("strike"))
    if strike is None:
        raise ValueError("strike is required")

    bid = _float_or_none(raw_row.get("bid"))
    ask = _float_or_none(raw_row.get("ask"))
    mark = _float_or_none(raw_row.get("mark"))
    last = _float_or_none(raw_row.get("last"))
    greeks = _clean_greeks(raw_row.get("greeks"))
    normalized: dict[str, Any] = {
        "source_label": SOURCE_LABEL,
        "source_grade": SOURCE_GRADE,
        "proof_grade": False,
        "snapshot_kind": SNAPSHOT_KIND,
        "quote_date": quote_date.isoformat(),
        "retrieved_at_utc": retrieved_at_utc,
        "underlying": str(symbol).strip().upper(),
        "contract_symbol": _occ_contract_symbol(symbol, expiration, option_type, strike),
        "expiration": expiration.isoformat(),
        "expiry": expiration.isoformat(),
        "option_type": option_type,
        "strike": strike,
        "last": last,
        "bid": bid,
        "bid_size": _int_or_none(raw_row.get("bid_size")),
        "ask": ask,
        "ask_size": _int_or_none(raw_row.get("ask_size")),
        "mark": mark,
        "volume": _int_or_none(raw_row.get("volume")),
        "open_interest": _int_or_none(raw_row.get("open_interest")),
        "greeks": greeks,
    }
    if greeks:
        normalized.update({f"greek_{key}": value for key, value in greeks.items()})
    if bid is not None and ask is not None:
        normalized["spread"] = round(ask - bid, 6)
        mid = (bid + ask) / 2.0
        normalized["spread_pct_of_mid"] = round(((ask - bid) / mid) * 100.0, 6) if mid > 0 else None
    else:
        normalized["spread"] = None
        normalized["spread_pct_of_mid"] = None
    normalized["quality_flags"] = _quality_flags(normalized)
    return normalized


class OnclickMediaClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 60.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "options-chatbot-research-importer/1.0",
        )

    def _get_json(self, params: dict[str, Any]) -> Any:
        response = self.session.get(self.base_url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.json()

    def available_dates(self, symbol: str) -> list[date]:
        normalized_symbol = str(symbol).strip().upper()
        payload = self._get_json({"ticker": normalized_symbol, "list": "date"})
        raw_dates = payload.get(normalized_symbol) if isinstance(payload, dict) else None
        if not isinstance(raw_dates, list):
            return []
        dates: list[date] = []
        for raw in raw_dates:
            try:
                dates.append(_parse_date(raw))
            except ValueError:
                continue
        return sorted(set(dates))

    def option_chain(self, symbol: str, quote_date: date) -> list[dict[str, Any]]:
        payload = self._get_json(
            {
                "ticker": str(symbol).strip().upper(),
                "date": quote_date.isoformat(),
                "output": "json-v1",
            }
        )
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []


def select_recent_shared_dates(
    availability: dict[str, Iterable[date]],
    *,
    target_count: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[date]:
    sets = [set(dates) for dates in availability.values()]
    if not sets:
        return []
    shared = set.intersection(*sets)
    if start_date is not None:
        shared = {item for item in shared if item >= start_date}
    if end_date is not None:
        shared = {item for item in shared if item <= end_date}
    shared = {item for item in shared if is_us_equity_market_day(item)}
    selected = sorted(shared)
    if target_count > 0:
        selected = selected[-target_count:]
    return selected


def _chain_path(output_dir: Path, symbol: str, quote_date: date) -> Path:
    return output_dir / "chains" / symbol.upper() / f"{quote_date.isoformat()}.jsonl.gz"


def _request_key(symbol: str, quote_date: date) -> str:
    return f"{symbol.upper()}|{quote_date.isoformat()}"


def _load_manifest(output_dir: Path) -> dict[str, Any]:
    path = output_dir / "manifest.json"
    if not path.exists():
        return {"source_label": SOURCE_LABEL, "requests": {}}
    payload = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(payload, dict):
        return {"source_label": SOURCE_LABEL, "requests": {}}
    if not isinstance(payload.get("requests"), dict):
        payload["requests"] = {}
    return payload


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")
    tmp.replace(path)


def _write_chain_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    tmp.replace(path)


def _iter_chain_rows(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                yield parsed


def _write_import_csv(
    path: Path,
    *,
    output_dir: Path,
    symbols: list[str],
    quote_dates: list[date],
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    executable_rows = 0
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for quote_date in quote_dates:
            as_of_utc = _as_of_utc_for_daily_eod(quote_date)
            for symbol in symbols:
                chain_path = _chain_path(output_dir, symbol, quote_date)
                if not chain_path.exists():
                    continue
                for row in _iter_chain_rows(chain_path):
                    bid = _float_or_none(row.get("bid"))
                    ask = _float_or_none(row.get("ask"))
                    if bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid:
                        executable_rows += 1
                    writer.writerow(
                        {
                            "as_of_utc": as_of_utc,
                            "underlying": str(row.get("underlying") or symbol).strip().upper(),
                            "contract_symbol": str(row.get("contract_symbol") or "").strip().upper(),
                            "expiry": str(row.get("expiry") or row.get("expiration") or "")[:10],
                            "option_type": str(row.get("option_type") or "").strip().lower(),
                            "strike": _format_decimal(_float_or_none(row.get("strike")), places=3),
                            "bid": _format_decimal(bid),
                            "ask": _format_decimal(ask),
                            "last": _format_decimal(_float_or_none(row.get("last"))),
                            "iv": "",
                            "underlying_price": "",
                            "volume": _format_int(_int_or_none(row.get("volume"))),
                            "open_interest": _format_int(_int_or_none(row.get("open_interest"))),
                        }
                    )
                    row_count += 1
    return {
        "csv_path": str(path),
        "csv_rows": row_count,
        "csv_executable_bid_ask_rows": executable_rows,
    }


def _summarize_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    row_count = 0
    executable = 0
    volume_oi = 0
    option_type_counts: Counter[str] = Counter()
    expiry_dates: set[str] = set()
    flag_counts: Counter[str] = Counter()
    for row in rows:
        row_count += 1
        flags = {str(flag) for flag in row.get("quality_flags") or []}
        flag_counts.update(flags)
        if "executable_bid_ask" in flags:
            executable += 1
        if "executable_bid_ask" in flags and row.get("volume") and row.get("open_interest"):
            volume_oi += 1
        option_type = str(row.get("option_type") or "").strip().lower()
        if option_type:
            option_type_counts[option_type] += 1
        expiry = str(row.get("expiration") or row.get("expiry") or "").strip()
        if expiry:
            expiry_dates.add(expiry)
    return {
        "row_count": row_count,
        "executable_bid_ask_rows": executable,
        "executable_with_volume_oi_rows": volume_oi,
        "option_type_counts": dict(sorted(option_type_counts.items())),
        "expiry_count": len(expiry_dates),
        "first_expiry": min(expiry_dates) if expiry_dates else None,
        "last_expiry": max(expiry_dates) if expiry_dates else None,
        "quality_flag_counts": dict(sorted(flag_counts.items())),
    }


def _summarize_chain_file(path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                rows.append(parsed)
    return _summarize_rows(rows)


def _fetch_with_retries(
    client: OnclickMediaClient,
    symbol: str,
    quote_date: date,
    *,
    retries: int,
    retry_sleep_seconds: float,
) -> list[dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(max(int(retries), 1)):
        try:
            return client.option_chain(symbol, quote_date)
        except Exception as exc:  # pragma: no cover - exercised through integration runs
            last_error = exc
            if attempt + 1 < max(int(retries), 1):
                time.sleep(max(float(retry_sleep_seconds), 0.0) * (attempt + 1))
    assert last_error is not None
    raise last_error


def import_onclickmedia_eod(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    symbols: list[str] | None = None,
    target_shared_dates: int = DEFAULT_TARGET_SHARED_DATES,
    start_date: date | None = None,
    end_date: date | None = None,
    max_symbols: int | None = None,
    max_dates: int | None = None,
    delay_seconds: float = 0.05,
    retries: int = 3,
    retry_sleep_seconds: float = 1.0,
    force: bool = False,
    progress_every: int = 0,
    db_path: Path | str | None = None,
    csv_output: Path | str | None = None,
    client: OnclickMediaClient | None = None,
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    requested_symbols = list(symbols or ai_commodity_scan_tickers())
    if max_symbols is not None:
        requested_symbols = requested_symbols[: max(int(max_symbols), 0)]
    client = client or OnclickMediaClient()
    generated_at = _utc_now_iso()

    availability: dict[str, list[date]] = {}
    availability_errors: dict[str, str] = {}
    for symbol in requested_symbols:
        try:
            availability[symbol] = client.available_dates(symbol)
        except Exception as exc:  # pragma: no cover - exercised through integration runs
            availability[symbol] = []
            availability_errors[symbol] = str(exc)
    selected_dates = select_recent_shared_dates(
        availability,
        target_count=int(target_shared_dates),
        start_date=start_date,
        end_date=end_date,
    )
    if max_dates is not None:
        selected_dates = selected_dates[-max(int(max_dates), 0) :]

    manifest = _load_manifest(output_dir)
    manifest["source_label"] = SOURCE_LABEL
    manifest["source_grade"] = SOURCE_GRADE
    manifest["proof_grade"] = False
    manifest["updated_at_utc"] = generated_at
    manifest["base_url"] = getattr(client, "base_url", DEFAULT_BASE_URL)
    requests_manifest = manifest.setdefault("requests", {})

    totals: Counter[str] = Counter()
    per_symbol: dict[str, Counter[str]] = defaultdict(Counter)
    per_date: dict[str, Counter[str]] = defaultdict(Counter)
    errors: list[dict[str, Any]] = []
    skipped_existing = 0
    fetched_pairs = 0

    for quote_date in selected_dates:
        for symbol in requested_symbols:
            key = _request_key(symbol, quote_date)
            output_path = _chain_path(output_dir, symbol, quote_date)
            previous = requests_manifest.get(key) if isinstance(requests_manifest.get(key), dict) else {}
            if (
                not force
                and output_path.exists()
                and previous.get("status") == "success"
                and int(previous.get("row_count") or 0) >= 0
            ):
                stats = {
                    "row_count": int(previous.get("row_count") or 0),
                    "executable_bid_ask_rows": int(previous.get("executable_bid_ask_rows") or 0),
                    "executable_with_volume_oi_rows": int(previous.get("executable_with_volume_oi_rows") or 0),
                }
                skipped_existing += 1
            elif not force and output_path.exists():
                stats = _summarize_chain_file(output_path)
                requests_manifest[key] = {
                    "status": "success",
                    "source": "existing_file",
                    "symbol": symbol,
                    "quote_date": quote_date.isoformat(),
                    "output_path": str(output_path),
                    "row_count": stats["row_count"],
                    "executable_bid_ask_rows": stats["executable_bid_ask_rows"],
                    "executable_with_volume_oi_rows": stats["executable_with_volume_oi_rows"],
                    "url_params": {"ticker": symbol, "date": quote_date.isoformat(), "output": "json-v1"},
                }
                skipped_existing += 1
            else:
                retrieved_at = _utc_now_iso()
                try:
                    raw_rows = _fetch_with_retries(
                        client,
                        symbol,
                        quote_date,
                        retries=retries,
                        retry_sleep_seconds=retry_sleep_seconds,
                    )
                    normalized_rows: list[dict[str, Any]] = []
                    rejected_rows = 0
                    reject_reasons: Counter[str] = Counter()
                    for raw_row in raw_rows:
                        try:
                            normalized_rows.append(
                                normalize_chain_row(
                                    symbol,
                                    quote_date,
                                    raw_row,
                                    retrieved_at_utc=retrieved_at,
                                )
                            )
                        except Exception as exc:
                            rejected_rows += 1
                            reject_reasons[str(exc)] += 1
                    _write_chain_rows(output_path, normalized_rows)
                    stats = _summarize_rows(normalized_rows)
                    stats["rejected_rows"] = rejected_rows
                    stats["reject_reasons"] = dict(reject_reasons)
                    requests_manifest[key] = {
                        "status": "success",
                        "source": "api",
                        "symbol": symbol,
                        "quote_date": quote_date.isoformat(),
                        "retrieved_at_utc": retrieved_at,
                        "output_path": str(output_path),
                        "row_count": stats["row_count"],
                        "executable_bid_ask_rows": stats["executable_bid_ask_rows"],
                        "executable_with_volume_oi_rows": stats["executable_with_volume_oi_rows"],
                        "rejected_rows": rejected_rows,
                        "reject_reasons": dict(reject_reasons),
                        "url_params": {"ticker": symbol, "date": quote_date.isoformat(), "output": "json-v1"},
                    }
                    fetched_pairs += 1
                    if delay_seconds > 0:
                        time.sleep(delay_seconds)
                except Exception as exc:  # pragma: no cover - exercised through integration runs
                    stats = {"row_count": 0, "executable_bid_ask_rows": 0, "executable_with_volume_oi_rows": 0}
                    error = {
                        "symbol": symbol,
                        "quote_date": quote_date.isoformat(),
                        "error": str(exc),
                    }
                    errors.append(error)
                    requests_manifest[key] = {
                        "status": "error",
                        "symbol": symbol,
                        "quote_date": quote_date.isoformat(),
                        "error": str(exc),
                        "url_params": {"ticker": symbol, "date": quote_date.isoformat(), "output": "json-v1"},
                    }

            totals["row_count"] += int(stats.get("row_count") or 0)
            totals["executable_bid_ask_rows"] += int(stats.get("executable_bid_ask_rows") or 0)
            totals["executable_with_volume_oi_rows"] += int(stats.get("executable_with_volume_oi_rows") or 0)
            totals["request_pairs"] += 1
            per_symbol[symbol]["date_count"] += 1
            per_symbol[symbol]["row_count"] += int(stats.get("row_count") or 0)
            per_symbol[symbol]["executable_bid_ask_rows"] += int(stats.get("executable_bid_ask_rows") or 0)
            per_symbol[symbol]["executable_with_volume_oi_rows"] += int(
                stats.get("executable_with_volume_oi_rows") or 0
            )
            per_date[quote_date.isoformat()]["symbol_count"] += 1
            per_date[quote_date.isoformat()]["row_count"] += int(stats.get("row_count") or 0)
            per_date[quote_date.isoformat()]["executable_bid_ask_rows"] += int(
                stats.get("executable_bid_ask_rows") or 0
            )
            if progress_every and totals["request_pairs"] % max(int(progress_every), 1) == 0:
                print(
                    json.dumps(
                        {
                            "progress_pairs": int(totals["request_pairs"]),
                            "fetched_pairs": fetched_pairs,
                            "skipped_existing_pairs": skipped_existing,
                            "row_count": int(totals["row_count"]),
                            "latest_symbol": symbol,
                            "latest_date": quote_date.isoformat(),
                            "error_pairs": len(errors),
                        },
                        sort_keys=True,
                    ),
                    file=sys.stderr,
                    flush=True,
                )

    date_counts = {symbol: len(dates) for symbol, dates in availability.items()}
    import_csv_result: dict[str, Any] | None = None
    db_import_result: dict[str, Any] | None = None
    if db_path is not None and selected_dates:
        csv_path = Path(csv_output) if csv_output else (
            output_dir
            / "imports"
            / f"onclickmedia_options_eod_{len(requested_symbols)}symbols_{selected_dates[0]:%Y%m%d}_{selected_dates[-1]:%Y%m%d}.csv"
        )
        import_csv_result = _write_import_csv(
            csv_path,
            output_dir=output_dir,
            symbols=requested_symbols,
            quote_dates=selected_dates,
        )
        if import_csv_result["csv_rows"] > 0:
            db_import_result = import_historical_option_snapshots(
                csv_path,
                SOURCE_LABEL,
                dataset_kind="daily_parquet",
                snapshot_kind=DAILY_SNAPSHOT_KIND,
                db_path=db_path,
            )

    store_summary = None
    trusted_store_summary = None
    if db_path is not None:
        store = HistoricalOptionsStore(db_path)
        store_summary = store.snapshot_summary(DAILY_SNAPSHOT_KIND, trusted_only=False)
        trusted_store_summary = store.snapshot_summary(DAILY_SNAPSHOT_KIND, trusted_only=True)

    summary = {
        "generated_at_utc": _utc_now_iso(),
        "source_label": SOURCE_LABEL,
        "source_grade": SOURCE_GRADE,
        "proof_grade": False,
        "snapshot_kind": SNAPSHOT_KIND,
        "usage_policy": "research_grade_eod_bidask_for_signal_and_fillability_research_not_opra_intraday_proof",
        "source_url": DEFAULT_BASE_URL,
        "output_dir": str(output_dir),
        "manifest_path": str(output_dir / "manifest.json"),
        "symbols": requested_symbols,
        "symbol_count": len(requested_symbols),
        "availability": {
            "date_counts": date_counts,
            "min_date_count": min(date_counts.values()) if date_counts else 0,
            "max_date_count": max(date_counts.values()) if date_counts else 0,
            "first_dates": {
                symbol: (dates[0].isoformat() if dates else None)
                for symbol, dates in sorted(availability.items())
            },
            "latest_dates": {
                symbol: (dates[-1].isoformat() if dates else None)
                for symbol, dates in sorted(availability.items())
            },
            "errors": availability_errors,
        },
        "selected_shared_dates": {
            "count": len(selected_dates),
            "target_count": int(target_shared_dates),
            "first": selected_dates[0].isoformat() if selected_dates else None,
            "last": selected_dates[-1].isoformat() if selected_dates else None,
            "dates": [item.isoformat() for item in selected_dates],
        },
        "row_count": int(totals["row_count"]),
        "executable_bid_ask_rows": int(totals["executable_bid_ask_rows"]),
        "executable_with_volume_oi_rows": int(totals["executable_with_volume_oi_rows"]),
        "executable_bid_ask_pct": round(
            (totals["executable_bid_ask_rows"] / totals["row_count"]) * 100.0,
            4,
        )
        if totals["row_count"]
        else 0.0,
        "executable_with_volume_oi_pct": round(
            (totals["executable_with_volume_oi_rows"] / totals["row_count"]) * 100.0,
            4,
        )
        if totals["row_count"]
        else 0.0,
        "request_pairs": int(totals["request_pairs"]),
        "fetched_pairs": fetched_pairs,
        "skipped_existing_pairs": skipped_existing,
        "error_pairs": len(errors),
        "errors": errors[:25],
        "import_csv": import_csv_result,
        "db_import_result": db_import_result,
        "daily_summary_all_sources": store_summary,
        "trusted_daily_summary": trusted_store_summary,
        "per_symbol": {symbol: dict(counter) for symbol, counter in sorted(per_symbol.items())},
        "per_date": {day: dict(counter) for day, counter in sorted(per_date.items())},
        "data_quality_caveats": [
            "OnclickMedia is aggregated from public/free sources and is not OPRA-certified intraday NBBO.",
            "Rows are end-of-day chains; use for research fillability and directional replay, not final proof-grade execution claims.",
            "Keep Alpaca OPRA forward captures as the proof-grade source label.",
        ],
    }
    manifest["latest_summary_path"] = str(output_dir / "latest.json")
    _write_json_atomic(output_dir / "manifest.json", manifest)
    _write_json_atomic(output_dir / "latest.json", summary)
    timestamp = summary["generated_at_utc"].replace(":", "").replace("-", "")
    _write_json_atomic(output_dir / f"onclickmedia_eod_summary_{timestamp}.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import OnclickMedia historical EOD options chains for the AI commodity lane."
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--symbols", help="Comma-separated symbols. Defaults to the AI commodity scan universe.")
    parser.add_argument("--target-shared-dates", type=int, default=DEFAULT_TARGET_SHARED_DATES)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--max-symbols", type=int)
    parser.add_argument("--max-dates", type=int)
    parser.add_argument("--delay-seconds", type=float, default=0.05)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-sleep-seconds", type=float, default=1.0)
    parser.add_argument("--progress-every", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--db-path", help="Optional SQLite path to import normalized EOD rows into.")
    parser.add_argument("--csv-output", help="Optional exact CSV path for the normalized DB import file.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = import_onclickmedia_eod(
        output_dir=Path(args.output_dir),
        symbols=_parse_symbol_list(args.symbols),
        target_shared_dates=args.target_shared_dates,
        start_date=_parse_optional_date(args.start_date),
        end_date=_parse_optional_date(args.end_date),
        max_symbols=args.max_symbols,
        max_dates=args.max_dates,
        delay_seconds=args.delay_seconds,
        retries=args.retries,
        retry_sleep_seconds=args.retry_sleep_seconds,
        force=args.force,
        progress_every=args.progress_every,
        db_path=args.db_path,
        csv_output=args.csv_output,
    )
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    compact = {
        "source_label": summary["source_label"],
        "source_grade": summary["source_grade"],
        "proof_grade": summary["proof_grade"],
        "symbols": summary["symbol_count"],
        "shared_dates": summary["selected_shared_dates"]["count"],
        "first_date": summary["selected_shared_dates"]["first"],
        "last_date": summary["selected_shared_dates"]["last"],
        "row_count": summary["row_count"],
        "executable_bid_ask_rows": summary["executable_bid_ask_rows"],
        "executable_with_volume_oi_rows": summary["executable_with_volume_oi_rows"],
        "error_pairs": summary["error_pairs"],
        "csv_path": (summary.get("import_csv") or {}).get("csv_path"),
        "csv_rows": (summary.get("import_csv") or {}).get("csv_rows"),
        "imported_rows": (summary.get("db_import_result") or {}).get("imported_rows"),
        "duplicate_rows": (summary.get("db_import_result") or {}).get("duplicate_rows"),
        "data_trust": (summary.get("db_import_result") or {}).get("data_trust"),
        "latest_json": str(Path(args.output_dir) / "latest.json"),
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
