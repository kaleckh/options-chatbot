from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AI_COMMODITY_UNIVERSE_PATH = ROOT / "data" / "ai-commodity-infra" / "universe.json"

CORE_OPTIONS = "CORE_OPTIONS"
CONDITIONAL_OPTIONS = "CONDITIONAL_OPTIONS"
WATCH_OR_SPOT_ONLY = "WATCH_OR_SPOT_ONLY"
AVOID = "AVOID"
SCAN_ELIGIBLE_BUCKETS = {CORE_OPTIONS, CONDITIONAL_OPTIONS}

_DEFAULT_SCAN_TICKERS = (
    "FCX",
    "SLV",
    "VRT",
    "VST",
    "ETN",
    "GEV",
    "PWR",
    "CCJ",
    "CEG",
    "SCCO",
    "COPX",
    "URA",
    "ALB",
    "SQM",
    "MP",
    "RIO",
    "BHP",
    "TECK",
    "AA",
    "XME",
    "NRG",
    "NVT",
    "CARR",
    "TT",
)
_DEFAULT_INDEX_LIKE_TICKERS = ("SLV", "COPX", "URA", "XME")


def load_ai_commodity_universe(path: Path | str | None = None) -> dict[str, Any]:
    universe_path = Path(path) if path is not None else AI_COMMODITY_UNIVERSE_PATH
    with universe_path.open("r", encoding="utf8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("AI commodity universe must be a JSON object")
    return payload


def iter_ai_commodity_symbols(path: Path | str | None = None) -> list[dict[str, Any]]:
    payload = load_ai_commodity_universe(path)
    symbols = payload.get("symbols")
    if not isinstance(symbols, list):
        raise ValueError("AI commodity universe is missing a symbols list")
    rows: list[dict[str, Any]] = []
    for row in symbols:
        if isinstance(row, dict):
            rows.append(row)
    return rows


def ai_commodity_scan_tickers(path: Path | str | None = None) -> list[str]:
    try:
        rows = iter_ai_commodity_symbols(path)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return list(_DEFAULT_SCAN_TICKERS)

    symbols: list[str] = []
    seen: set[str] = set()
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        bucket = str(row.get("options_bucket") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        if row.get("scan_eligible") is True and bucket in SCAN_ELIGIBLE_BUCKETS:
            symbols.append(symbol)
            seen.add(symbol)
    return symbols or list(_DEFAULT_SCAN_TICKERS)


def ai_commodity_tickers_by_options_bucket(
    bucket: str,
    path: Path | str | None = None,
    *,
    scan_eligible_only: bool = False,
) -> list[str]:
    normalized_bucket = str(bucket or "").strip().upper()
    try:
        rows = iter_ai_commodity_symbols(path)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        rows = []

    symbols: list[str] = []
    seen: set[str] = set()
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        row_bucket = str(row.get("options_bucket") or "").strip().upper()
        if not symbol or symbol in seen or row_bucket != normalized_bucket:
            continue
        if scan_eligible_only and row.get("scan_eligible") is not True:
            continue
        symbols.append(symbol)
        seen.add(symbol)
    return symbols


def ai_commodity_core_options_tickers(path: Path | str | None = None) -> list[str]:
    symbols = ai_commodity_tickers_by_options_bucket(CORE_OPTIONS, path, scan_eligible_only=True)
    return symbols or [symbol for symbol in _DEFAULT_SCAN_TICKERS[:9]]


def ai_commodity_conditional_options_tickers(path: Path | str | None = None) -> list[str]:
    symbols = ai_commodity_tickers_by_options_bucket(CONDITIONAL_OPTIONS, path, scan_eligible_only=True)
    if symbols:
        return symbols
    core = set(ai_commodity_core_options_tickers(path))
    return [symbol for symbol in _DEFAULT_SCAN_TICKERS if symbol not in core]


def ai_commodity_data_ready_tickers(
    available_underlyings: list[str] | tuple[str, ...] | set[str],
    path: Path | str | None = None,
) -> list[str]:
    available = {str(symbol or "").strip().upper() for symbol in available_underlyings or []}
    return [symbol for symbol in ai_commodity_scan_tickers(path) if symbol in available]


def ai_commodity_index_like_tickers(path: Path | str | None = None, *, include_watch: bool = True) -> list[str]:
    try:
        rows = iter_ai_commodity_symbols(path)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return list(_DEFAULT_INDEX_LIKE_TICKERS)

    symbols: list[str] = []
    seen: set[str] = set()
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        if str(row.get("asset_class") or "").strip().lower() != "etf":
            continue
        if include_watch or row.get("scan_eligible") is True:
            symbols.append(symbol)
            seen.add(symbol)
    return symbols or list(_DEFAULT_INDEX_LIKE_TICKERS)


def ai_commodity_symbols_by_bucket(path: Path | str | None = None) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {
        CORE_OPTIONS: [],
        CONDITIONAL_OPTIONS: [],
        WATCH_OR_SPOT_ONLY: [],
        AVOID: [],
    }
    for row in iter_ai_commodity_symbols(path):
        symbol = str(row.get("symbol") or "").strip().upper()
        bucket = str(row.get("options_bucket") or "").strip().upper()
        if symbol and bucket in buckets:
            buckets[bucket].append(symbol)
    return buckets


def validate_ai_commodity_universe(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        return ["symbols must be a non-empty list"]

    required_fields = {
        "symbol",
        "name",
        "asset_class",
        "options_bucket",
        "scan_eligible",
        "primary_theme",
        "theme_tags",
        "supply_chain_role",
        "source_agents",
        "rationale",
        "risk_notes",
    }
    valid_buckets = {CORE_OPTIONS, CONDITIONAL_OPTIONS, WATCH_OR_SPOT_ONLY, AVOID}
    seen: set[str] = set()
    for index, row in enumerate(symbols):
        if not isinstance(row, dict):
            errors.append(f"symbols[{index}] must be an object")
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            errors.append(f"symbols[{index}] missing symbol")
            continue
        if symbol in seen:
            errors.append(f"duplicate symbol {symbol}")
        seen.add(symbol)
        missing = sorted(field for field in required_fields if field not in row)
        if missing:
            errors.append(f"{symbol} missing fields: {', '.join(missing)}")
        bucket = str(row.get("options_bucket") or "").strip().upper()
        if bucket not in valid_buckets:
            errors.append(f"{symbol} invalid options_bucket {bucket!r}")
        if row.get("scan_eligible") is True and bucket not in SCAN_ELIGIBLE_BUCKETS:
            errors.append(f"{symbol} scan_eligible cannot use bucket {bucket}")
        if row.get("scan_eligible") is not True and bucket == CORE_OPTIONS:
            errors.append(f"{symbol} core options entries must be scan eligible")
        for list_field in ("theme_tags", "source_agents", "risk_notes"):
            if not isinstance(row.get(list_field), list) or not row.get(list_field):
                errors.append(f"{symbol} {list_field} must be a non-empty list")
    return errors
