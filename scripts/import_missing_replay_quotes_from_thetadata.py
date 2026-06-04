from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_options_store import INTRADAY_SNAPSHOT_KIND, import_historical_option_snapshots  # noqa: E402
from scripts.import_thetadata_options_nbbo import (  # noqa: E402
    CSV_FIELDNAMES,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SOURCE_LABEL,
    DEFAULT_THETA_URL,
    INTRADAY_DATASET_KIND,
    _extract_rows,
    _normalize_theta_quote_row,
)


OCC_RE = re.compile(r"^(?P<root>[A-Z.]+)(?P<expiry>\d{6})(?P<right>[CP])(?P<strike>\d{8})$")


def _filter_values(values: list[str] | None, *, upper: bool = False) -> set[str]:
    parsed: set[str] = set()
    for value in values or []:
        for item in str(value).split(","):
            text = item.strip()
            if text:
                parsed.add(text.upper() if upper else text)
    return parsed


def _parse_occ(symbol: str) -> dict[str, Any] | None:
    match = OCC_RE.match(str(symbol or "").strip().upper())
    if not match:
        return None
    expiry_raw = match.group("expiry")
    expiry = date(2000 + int(expiry_raw[:2]), int(expiry_raw[2:4]), int(expiry_raw[4:6]))
    right = match.group("right")
    return {
        "root": match.group("root"),
        "expiry": expiry,
        "right": right,
        "option_type": "call" if right == "C" else "put",
        "strike": int(match.group("strike")) / 1000.0,
    }


def _missing_items(
    run_paths: list[Path],
    *,
    tickers: set[str] | None = None,
    contract_symbols: set[str] | None = None,
    quote_dates: set[str] | None = None,
) -> list[dict[str, Any]]:
    items: dict[tuple[str, str], dict[str, Any]] = {}
    ticker_filter = tickers or set()
    contract_filter = contract_symbols or set()
    quote_date_filter = quote_dates or set()
    for path in run_paths:
        payload = json.loads(path.read_text(encoding="utf8"))
        for trade in payload.get("unpriced_trades") or []:
            ticker = str(trade.get("ticker") or "").strip().upper()
            if ticker_filter and ticker not in ticker_filter:
                continue
            quote_date = str(trade.get("missing_quote_date") or "").strip()
            if not quote_date:
                continue
            if quote_date_filter and quote_date[:10] not in quote_date_filter:
                continue
            for key in ("missing_long_contract_symbol", "missing_short_contract_symbol"):
                contract = str(trade.get(key) or "").strip().upper()
                if contract_filter and contract not in contract_filter:
                    continue
                parsed = _parse_occ(contract)
                if not parsed:
                    continue
                item = items.setdefault(
                    (quote_date, contract),
                    {
                        "quote_date": date.fromisoformat(quote_date[:10]),
                        "contract_symbol": contract,
                        **parsed,
                        "source_occurrences": [],
                    },
                )
                item["source_occurrences"].append(
                    {
                        "run_path": str(path),
                        "ticker": trade.get("ticker"),
                        "entry_date": trade.get("date"),
                        "source_field": key,
                        "unpriced_reason": trade.get("unpriced_reason"),
                    }
                )
    return [items[key] for key in sorted(items)]


def _expand_items(items: list[dict[str, Any]], *, lookahead_calendar_days: int) -> list[dict[str, Any]]:
    if int(lookahead_calendar_days) <= 0:
        return list(items)

    expanded: dict[tuple[date, str], dict[str, Any]] = {}
    for item in items:
        start: date = item["quote_date"]
        expiry: date = item["expiry"]
        end = min(expiry, start + timedelta(days=int(lookahead_calendar_days)))
        current = start
        while current <= end:
            if current.weekday() < 5:
                expanded[(current, item["contract_symbol"])] = {
                    **item,
                    "quote_date": current,
                    "original_missing_quote_date": start,
                }
            current += timedelta(days=1)
    return [expanded[key] for key in sorted(expanded)]


def _json_item(item: dict[str, Any]) -> dict[str, Any]:
    quote_date_value = item.get("quote_date")
    expiry_value = item.get("expiry")
    original_value = item.get("original_missing_quote_date")
    return {
        "quote_date": quote_date_value.isoformat() if isinstance(quote_date_value, date) else str(quote_date_value),
        "original_missing_quote_date": (
            original_value.isoformat() if isinstance(original_value, date) else str(original_value)
        )
        if original_value
        else None,
        "contract_symbol": item.get("contract_symbol"),
        "underlying": item.get("root"),
        "expiry": expiry_value.isoformat() if isinstance(expiry_value, date) else str(expiry_value),
        "option_type": item.get("option_type"),
        "right": item.get("right"),
        "strike": item.get("strike"),
        "source_occurrences": sorted(
            item.get("source_occurrences") or [],
            key=lambda row: (
                str(row.get("run_path") or ""),
                str(row.get("entry_date") or ""),
                str(row.get("source_field") or ""),
            ),
        ),
    }


def _repair_manifest(
    *,
    base_items: list[dict[str, Any]],
    request_items: list[dict[str, Any]],
    expanded_item_count: int,
    max_requests: int,
) -> dict[str, Any]:
    return {
        "base_targets": [_json_item(item) for item in base_items],
        "request_targets": [_json_item(item) for item in request_items],
        "base_target_count": len(base_items),
        "request_target_count": len(request_items),
        "source_occurrence_count": sum(len(item.get("source_occurrences") or []) for item in base_items),
        "max_requests_applied": int(max_requests) > 0 and len(request_items) < int(expanded_item_count),
    }


def _theta_rows_for_contract(
    session: requests.Session,
    *,
    theta_url: str,
    item: dict[str, Any],
    start_time: str,
    end_time: str,
    interval: str,
    timeout: float,
) -> list[dict[str, str]]:
    trade_date: date = item["quote_date"]
    params: dict[str, Any] = {
        "symbol": item["root"],
        "expiration": item["expiry"].strftime("%Y%m%d"),
        "date": trade_date.strftime("%Y%m%d"),
        "interval": interval,
        "format": "json",
        "start_time": start_time,
        "end_time": end_time,
        "right": item["right"],
        "strike": item["strike"],
    }
    response = session.get(f"{theta_url.rstrip('/')}/v3/option/history/quote", params=params, timeout=timeout)
    response.raise_for_status()

    matches: list[dict[str, str]] = []
    for raw_row in _extract_rows(response.json()):
        normalized = _normalize_theta_quote_row(raw_row, underlying=item["root"], trade_date=trade_date)
        if not normalized:
            continue
        if normalized["contract_symbol"] == item["contract_symbol"]:
            matches.append(normalized)
    return matches


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import exact ThetaData quotes needed by replay unpriced trades.")
    parser.add_argument("run_paths", nargs="+", type=Path)
    parser.add_argument("--theta-url", default=DEFAULT_THETA_URL)
    parser.add_argument("--source", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument("--snapshot-kind", default=INTRADAY_SNAPSHOT_KIND, choices=(INTRADAY_SNAPSHOT_KIND,))
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--start-time", default="15:55:00")
    parser.add_argument("--end-time", default="15:55:00")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--db-path")
    parser.add_argument(
        "--lookahead-calendar-days",
        type=int,
        default=0,
        help="Also request this many calendar days after each missing quote date, capped at expiration.",
    )
    parser.add_argument("--max-requests", type=int, default=0, help="Optional cap on expanded ThetaData requests.")
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
    parser.add_argument("--dry-run", action="store_true", help="Fetch and normalize rows, but do not write summaries, CSVs, or DB imports.")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Print the de-duplicated repair manifest without requesting ThetaData or writing files.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    run_paths = [path.resolve() for path in args.run_paths]
    target_filters = {
        "tickers": sorted(_filter_values(args.ticker, upper=True)),
        "contract_symbols": sorted(_filter_values(args.contract_symbol, upper=True)),
        "quote_dates": sorted(_filter_values(args.quote_date)),
    }
    base_items = _missing_items(
        run_paths,
        tickers=set(target_filters["tickers"]),
        contract_symbols=set(target_filters["contract_symbols"]),
        quote_dates=set(target_filters["quote_dates"]),
    )
    items = _expand_items(base_items, lookahead_calendar_days=int(args.lookahead_calendar_days))
    expanded_item_count = len(items)
    if int(args.max_requests) > 0:
        items = items[: int(args.max_requests)]
    no_write = bool(args.dry_run or args.plan_only)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    csv_path = Path(args.output_dir) / f"thetadata_opra_nbbo_exact_missing_intraday_{stamp}.csv"
    summary_path = Path(args.output_dir) / f"thetadata_exact_missing_intraday_{stamp}.json"

    rows: list[dict[str, str]] = []
    errors: list[str] = []
    rows_by_contract: Counter[str] = Counter()
    rows_by_date: Counter[str] = Counter()
    request_count = 0
    if not args.plan_only:
        with requests.Session() as session:
            for item in items:
                try:
                    matches = _theta_rows_for_contract(
                        session,
                        theta_url=args.theta_url,
                        item=item,
                        start_time=args.start_time,
                        end_time=args.end_time,
                        interval=args.interval,
                        timeout=float(args.timeout),
                    )
                    request_count += 1
                except Exception as exc:
                    errors.append(f"{item['quote_date']} {item['contract_symbol']}: {exc}")
                    continue
                if not matches:
                    errors.append(f"{item['quote_date']} {item['contract_symbol']}: no matched rows")
                    continue
                for row in matches:
                    rows.append(row)
                    rows_by_contract[row["contract_symbol"]] += 1
                    rows_by_date[row["as_of_utc"][:10]] += 1

    import_result = None
    if rows and not no_write:
        _write_csv(csv_path, rows)
        import_result = import_historical_option_snapshots(
            csv_path,
            args.source,
            dataset_kind=INTRADAY_DATASET_KIND,
            snapshot_kind=args.snapshot_kind,
            db_path=args.db_path,
        )

    payload = {
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "input_run_paths": [str(path) for path in run_paths],
        "target_filters": target_filters,
        "dry_run": bool(args.dry_run),
        "plan_only": bool(args.plan_only),
        "write_artifacts": not no_write,
        "base_unique_items": len(base_items),
        "unique_items": len(items),
        "expanded_unique_items": expanded_item_count,
        "request_count": request_count,
        "lookahead_calendar_days": int(args.lookahead_calendar_days),
        "normalized_rows": len(rows),
        "csv_path": None if no_write or not rows else str(csv_path.resolve()),
        "summary_path": None if no_write else str(summary_path.resolve()),
        "repair_manifest": _repair_manifest(
            base_items=base_items,
            request_items=items,
            expanded_item_count=expanded_item_count,
            max_requests=int(args.max_requests),
        ),
        "rows_by_contract": dict(sorted(rows_by_contract.items())),
        "rows_by_date": dict(sorted(rows_by_date.items())),
        "errors": errors,
        "import_result": import_result,
    }
    if not no_write:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf8")
    print(
        json.dumps(
            payload
            if args.json
            else {
                k: payload[k]
                for k in (
                    "dry_run",
                    "plan_only",
                    "unique_items",
                    "request_count",
                    "normalized_rows",
                    "csv_path",
                    "summary_path",
                    "import_result",
                )
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
