from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any


OCC_RE = re.compile(r"^(?P<root>[A-Z.]+)(?P<expiry>\d{6})(?P<right>[CP])(?P<strike>\d{8})$")


def filter_values(values: list[str] | None, *, upper: bool = False) -> set[str]:
    parsed: set[str] = set()
    for value in values or []:
        for item in str(value).split(","):
            text = item.strip()
            if text:
                parsed.add(text.upper() if upper else text)
    return parsed


def target_filters(
    *,
    tickers: list[str] | None = None,
    contract_symbols: list[str] | None = None,
    quote_dates: list[str] | None = None,
) -> dict[str, list[str]]:
    return {
        "tickers": sorted(filter_values(tickers, upper=True)),
        "contract_symbols": sorted(filter_values(contract_symbols, upper=True)),
        "quote_dates": sorted(filter_values(quote_dates)),
    }


def parse_occ(symbol: str) -> dict[str, Any] | None:
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


def contract_parts(symbol: str) -> dict[str, Any]:
    parsed = parse_occ(symbol)
    text = str(symbol or "").strip().upper()
    if not parsed:
        return {"contract_symbol": text}
    return {
        "contract_symbol": text,
        "underlying": parsed["root"],
        "expiry": parsed["expiry"].isoformat(),
        "option_type": parsed["option_type"],
        "strike": parsed["strike"],
    }


def _candidate_contract_fields(trade: dict[str, Any], *, include_fallback_contracts: bool) -> list[str]:
    fields = [
        key
        for key in ("missing_long_contract_symbol", "missing_short_contract_symbol")
        if str(trade.get(key) or "").strip()
    ]
    if fields or not include_fallback_contracts:
        return fields
    return [
        key
        for key in ("long_contract_symbol", "short_contract_symbol")
        if str(trade.get(key) or "").strip()
    ]


def _target_allowed(
    *,
    trade: dict[str, Any],
    contract: str,
    quote_date: str,
    tickers: set[str],
    contract_symbols: set[str],
    quote_dates: set[str],
) -> bool:
    ticker = str(trade.get("ticker") or "").strip().upper()
    if tickers and ticker not in tickers:
        return False
    if quote_dates and quote_date[:10] not in quote_dates:
        return False
    if contract_symbols and contract not in contract_symbols:
        return False
    return True


def missing_items_from_run_paths(
    run_paths: list[Path],
    *,
    tickers: set[str] | None = None,
    contract_symbols: set[str] | None = None,
    quote_dates: set[str] | None = None,
    include_fallback_contracts: bool = False,
) -> list[dict[str, Any]]:
    items: dict[tuple[str, str], dict[str, Any]] = {}
    ticker_filter = tickers or set()
    contract_filter = contract_symbols or set()
    quote_date_filter = quote_dates or set()
    for path in run_paths:
        payload = json.loads(path.read_text(encoding="utf8"))
        for trade in payload.get("unpriced_trades") or []:
            quote_date = str(trade.get("missing_quote_date") or "").strip()
            if not quote_date:
                continue
            for key in _candidate_contract_fields(trade, include_fallback_contracts=include_fallback_contracts):
                contract = str(trade.get(key) or "").strip().upper()
                parsed = parse_occ(contract)
                if not parsed:
                    continue
                if not _target_allowed(
                    trade=trade,
                    contract=contract,
                    quote_date=quote_date,
                    tickers=ticker_filter,
                    contract_symbols=contract_filter,
                    quote_dates=quote_date_filter,
                ):
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


def expand_items(items: list[dict[str, Any]], *, lookahead_calendar_days: int) -> list[dict[str, Any]]:
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


def json_item(item: dict[str, Any]) -> dict[str, Any]:
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


def repair_attempt_key(
    *,
    source_artifact: str | None,
    ticker: str | None,
    contract_symbol: str,
    missing_quote_date: str,
) -> str:
    source = str(source_artifact or "").replace("\\", "/")
    return "|".join(
        [
            source,
            str(ticker or "").upper(),
            str(contract_symbol or "").upper(),
            str(missing_quote_date or "")[:10],
        ]
    )


def base_target_key(item: dict[str, Any]) -> tuple[str, str]:
    return (str(item.get("quote_date")), str(item.get("contract_symbol") or "").upper())


def original_target_key(item: dict[str, Any]) -> tuple[str, str]:
    original = item.get("original_missing_quote_date") or item.get("quote_date")
    return (str(original), str(item.get("contract_symbol") or "").upper())


def repair_manifest(
    *,
    base_items: list[dict[str, Any]],
    request_items: list[dict[str, Any]],
    expanded_item_count: int,
    max_requests: int,
) -> dict[str, Any]:
    return {
        "base_targets": [json_item(item) for item in base_items],
        "request_targets": [json_item(item) for item in request_items],
        "base_target_count": len(base_items),
        "request_target_count": len(request_items),
        "source_occurrence_count": sum(len(item.get("source_occurrences") or []) for item in base_items),
        "max_requests_applied": int(max_requests) > 0 and len(request_items) < int(expanded_item_count),
    }
