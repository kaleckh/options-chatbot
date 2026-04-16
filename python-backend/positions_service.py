from __future__ import annotations

import copy
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import yfinance as yf

from historical_options_store import HistoricalOptionsStore
from market_data_service import (
    get_history as _md_get_history,
    get_option_chain as _md_get_option_chain,
    get_options as _md_get_options,
    request_scope as _market_data_request_scope,
)
from options_execution import (
    commission_total_usd,
    executable_option_price,
    option_pnl_snapshot,
)
from options_chatbot import (
    _check_early_exit,
    _compute_direction_score,
    _compute_tech_score_live,
    _get_profile,
)


_HISTORICAL_OPTIONS_STORE: HistoricalOptionsStore | None = None
_SCAN_PICK_LOG_CACHE: list[dict[str, Any]] | None = None


class _ReviewContext:
    def __init__(self):
        self._spy_ret5: Optional[float] = None
        self._profile_cache: dict[tuple[str, str | None], dict[str, Any]] = {}
        self._underlying_price_cache: dict[str, Optional[float]] = {}
        self._available_expiries_cache: dict[str, list[str]] = {}
        self._option_chain_cache: dict[tuple[str, str], Any] = {}

    def get_spy_ret5(self) -> float:
        if self._spy_ret5 is None:
            self._spy_ret5 = _get_spy_ret5()
        return self._spy_ret5

    def get_profile(self, symbol: str, direction: str | None = None) -> dict[str, Any]:
        key = (str(symbol or "").upper(), str(direction or "").lower() or None)
        if key not in self._profile_cache:
            self._profile_cache[key] = _get_profile(key[0], key[1])
        return self._profile_cache[key]

    def get_current_underlying_price(self, symbol: str) -> Optional[float]:
        key = str(symbol or "").upper()
        if key not in self._underlying_price_cache:
            self._underlying_price_cache[key] = _get_current_underlying_price(key)
        return self._underlying_price_cache[key]

    def get_available_expiries(self, symbol: str) -> list[str]:
        key = str(symbol or "").upper()
        if key not in self._available_expiries_cache:
            try:
                self._available_expiries_cache[key] = list(_cached_options(key) or [])
            except Exception:
                self._available_expiries_cache[key] = []
        return self._available_expiries_cache[key]

    def get_option_chain(self, symbol: str, expiry: str):
        key = (str(symbol or "").upper(), str(expiry))
        if key not in self._option_chain_cache:
            self._option_chain_cache[key] = _cached_option_chain(key[0], key[1])
        return self._option_chain_cache[key]


def _cached_history(
    symbol: str,
    *,
    period: str | None = None,
    start=None,
    end=None,
    interval: str = "1d",
) -> pd.DataFrame:
    return _md_get_history(
        symbol,
        period=period,
        start=start,
        end=end,
        interval=interval,
        ticker_factory=yf.Ticker,
    )


def _cached_options(symbol: str) -> list[str]:
    return _md_get_options(symbol, ticker_factory=yf.Ticker)


def _cached_option_chain(symbol: str, expiry: str):
    return _md_get_option_chain(symbol, expiry, ticker_factory=yf.Ticker)


def _parse_datetime(value: Optional[Any]) -> datetime:
    if not value:
        return datetime.now()
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except Exception:
                return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _normalize_contract_symbol(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    return raw.upper() if raw else None


def _historical_store() -> HistoricalOptionsStore:
    global _HISTORICAL_OPTIONS_STORE
    if _HISTORICAL_OPTIONS_STORE is None:
        _HISTORICAL_OPTIONS_STORE = HistoricalOptionsStore()
    return _HISTORICAL_OPTIONS_STORE


def _format_quote_time_et(minute_et: int | None) -> Optional[str]:
    if minute_et is None:
        return None
    hour = int(minute_et // 60)
    minute = int(minute_et % 60)
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12:02d}:{minute:02d} {suffix} ET"


def _pick_strategy_type(scan_pick: dict[str, Any]) -> str:
    explicit = str(scan_pick.get("strategy_type") or "").strip().lower()
    if explicit:
        return explicit
    if scan_pick.get("short_strike") is not None or scan_pick.get("short_contract_symbol"):
        return "vertical_spread"
    return "single_leg"


def _pick_trade_date(scan_pick: dict[str, Any], filled_at: Optional[str] = None) -> date:
    if filled_at:
        return _parse_datetime(filled_at).date()
    quote_time = str(scan_pick.get("quote_time_et") or "").strip()
    if quote_time:
        try:
            return _parse_datetime(quote_time).date()
        except Exception:
            pass
    recorded = scan_pick.get("source_scan_recorded_at_utc") or scan_pick.get("recorded_at_utc")
    if recorded:
        try:
            return _parse_datetime(recorded).date()
        except Exception:
            pass
    return datetime.now().date()


def _pick_context_fields(scan_pick: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": str(scan_pick.get("ticker") or "").upper(),
        "direction": str(scan_pick.get("direction") or scan_pick.get("type") or "").lower(),
        "strike": _safe_float(
            scan_pick.get("strike")
            if scan_pick.get("strike") is not None
            else scan_pick.get("long_strike")
            if scan_pick.get("long_strike") is not None
            else scan_pick.get("strike_est")
        ),
        "short_strike": _safe_float(scan_pick.get("short_strike")),
        "expiry": str(scan_pick.get("expiry") or "")[:10] or None,
        "contract_symbol": _normalize_contract_symbol(
            scan_pick.get("contract_symbol")
            or scan_pick.get("contractSymbol")
            or scan_pick.get("option_contract_symbol")
        ),
        "short_contract_symbol": _normalize_contract_symbol(scan_pick.get("short_contract_symbol")),
        "strategy_type": _pick_strategy_type(scan_pick),
    }


def _has_resolved_contract_identity(scan_pick: dict[str, Any]) -> bool:
    fields = _pick_context_fields(scan_pick)
    if not fields["contract_symbol"]:
        return False
    if fields["strategy_type"] == "vertical_spread" and fields["short_strike"] is not None:
        return bool(fields["short_contract_symbol"])
    return not bool(scan_pick.get("approximation_only"))


def _entry_quote_snapshot(scan_pick: dict[str, Any]) -> dict[str, Any]:
    snapshot = _safe_dict(scan_pick.get("entry_quote_snapshot"))
    if not snapshot:
        snapshot = {
            "captured_at_et": scan_pick.get("quote_time_et"),
            "captured_at_utc": scan_pick.get("quote_time_utc") or scan_pick.get("source_scan_recorded_at_utc"),
            "ticker": scan_pick.get("ticker"),
            "direction": scan_pick.get("direction") or scan_pick.get("type"),
            "strategy_type": _pick_strategy_type(scan_pick),
            "logged_expiry": scan_pick.get("original_logged_expiry") or scan_pick.get("expiry"),
            "resolved_listed_expiry": scan_pick.get("resolved_listed_expiry"),
            "selection_source": scan_pick.get("selection_source") or scan_pick.get("contract_selection_source"),
            "promotion_class": scan_pick.get("promotion_class"),
            "underlying_price": _safe_float(scan_pick.get("underlying_price_at_selection") or scan_pick.get("stock_price") or scan_pick.get("entry_price")),
            "quote_basis": scan_pick.get("quote_basis"),
            "quote_freshness_status": scan_pick.get("quote_freshness_status"),
            "options_snapshot_status": scan_pick.get("options_snapshot_status"),
            "option_chain_status": scan_pick.get("option_chain_status"),
            "entry_execution_price": _safe_float(scan_pick.get("entry_execution_price")),
            "entry_execution_basis": scan_pick.get("entry_execution_basis"),
            "entry_fee_total_usd": _safe_float(scan_pick.get("entry_fee_total_usd")),
        }
    snapshot.setdefault("captured_at_et", scan_pick.get("quote_time_et"))
    snapshot.setdefault("captured_at_utc", scan_pick.get("quote_time_utc") or scan_pick.get("source_scan_recorded_at_utc"))
    snapshot.setdefault("logged_expiry", scan_pick.get("original_logged_expiry") or scan_pick.get("expiry"))
    snapshot["resolved_listed_expiry"] = scan_pick.get("resolved_listed_expiry") or scan_pick.get("expiry")

    legs = snapshot.get("legs")
    if not isinstance(legs, list) or not legs:
        candidate_legs = scan_pick.get("legs")
        if isinstance(candidate_legs, list) and candidate_legs:
            snapshot["legs"] = copy.deepcopy(candidate_legs)
        else:
            snapshot["legs"] = [
                {
                    "role": "long",
                    "contract_symbol": _normalize_contract_symbol(
                        scan_pick.get("contract_symbol")
                        or scan_pick.get("contractSymbol")
                        or scan_pick.get("option_contract_symbol")
                    ),
                    "strike": _safe_float(scan_pick.get("strike") or scan_pick.get("long_strike") or scan_pick.get("strike_est")),
                    "premium": _safe_float(scan_pick.get("premium") or scan_pick.get("est_premium")),
                    "bid": _safe_float(scan_pick.get("bid")),
                    "ask": _safe_float(scan_pick.get("ask")),
                    "last": _safe_float(scan_pick.get("last")),
                    "mid": _safe_float(scan_pick.get("mid")),
                    "quote_basis": scan_pick.get("quote_basis"),
                    "quote_age_hours": _safe_float(scan_pick.get("quote_age_hours")),
                    "volume": scan_pick.get("contract_volume"),
                    "open_interest": scan_pick.get("contract_open_interest"),
                }
            ]
    if snapshot.get("display_price") is None:
        snapshot["display_price"] = _safe_float(
            scan_pick.get("net_debit")
            if scan_pick.get("net_debit") is not None
            else scan_pick.get("mid")
            if scan_pick.get("mid") is not None
            else scan_pick.get("premium")
            if scan_pick.get("premium") is not None
            else scan_pick.get("est_premium")
        )
    return snapshot


def _should_replace_fill_price(scan_pick: dict[str, Any], fill_price: float) -> bool:
    comparable_candidates = [
        scan_pick.get("entry_execution_price"),
        scan_pick.get("entry_option_price"),
        scan_pick.get("mid"),
        scan_pick.get("premium"),
        scan_pick.get("est_premium"),
    ]
    for candidate in comparable_candidates:
        estimate = _safe_float(candidate)
        if estimate is not None and abs(float(fill_price) - estimate) <= 0.05:
            return True
    return False


def _resolve_historical_comparable_pick(scan_pick: dict[str, Any], *, trade_date: date) -> Optional[dict[str, Any]]:
    fields = _pick_context_fields(scan_pick)
    ticker = fields["ticker"]
    direction = fields["direction"]
    strike = fields["strike"]
    expiry = fields["expiry"]
    if not ticker or direction not in {"call", "put"} or strike is None or not expiry:
        return None
    store = _historical_store()
    try:
        target_expiry = _parse_date(expiry)
    except Exception:
        return None

    if fields["strategy_type"] == "vertical_spread" and fields["short_strike"] is not None:
        long_quote = store.find_entry_contract(
            underlying=ticker,
            trade_date_et=trade_date,
            option_type=direction,
            target_expiry=target_expiry,
            target_strike=float(strike),
            allow_last_price=False,
        )
        if long_quote is None:
            return None
        short_quote = store.find_entry_contract(
            underlying=ticker,
            trade_date_et=trade_date,
            option_type=direction,
            target_expiry=long_quote.expiry,
            target_strike=float(fields["short_strike"]),
            allow_last_price=False,
        )
        if short_quote is None or str(short_quote.expiry) != str(long_quote.expiry):
            return None
        entry_debit = round(float(long_quote.price) - float(short_quote.price), 4)
        if entry_debit <= 0:
            return None
        spread_width = abs(float(short_quote.strike) - float(long_quote.strike))
        return {
            "strategy_type": "vertical_spread",
            "ticker": ticker,
            "direction": direction,
            "strike": round(float(long_quote.strike), 4),
            "short_strike": round(float(short_quote.strike), 4),
            "expiry": str(long_quote.expiry),
            "contract_symbol": long_quote.contract_symbol,
            "short_contract_symbol": short_quote.contract_symbol,
            "entry_execution_price": entry_debit,
            "entry_execution_basis": "historical_comparable_spread_mid",
            "entry_underlying_price": _safe_float(long_quote.underlying_price) or _safe_float(scan_pick.get("stock_price") or scan_pick.get("entry_price")),
            "entry_fee_total_usd": commission_total_usd(contracts=1, sides=2),
            "quote_time_et": _format_quote_time_et(long_quote.quote_minute_et),
            "quote_basis": "mid",
            "selection_source": "historical_comparable_exact_contract",
            "promotion_class": "comparable_exact_contract",
            "approximation_only": False,
            "comparable_contract": True,
            "comparable_contract_basis": "historical_entry_window",
            "comparable_contract_label": "Comparable Exact Contract",
            "resolved_spread_width": round(float(spread_width), 4),
            "resolution_notes": "Resolved from trusted historical option snapshots using nearest listed entry-window contracts.",
        }

    entry_quote = store.find_entry_contract(
        underlying=ticker,
        trade_date_et=trade_date,
        option_type=direction,
        target_expiry=target_expiry,
        target_strike=float(strike),
        allow_last_price=False,
    )
    if entry_quote is None:
        return None
    return {
        "strategy_type": "single_leg",
        "ticker": ticker,
        "direction": direction,
        "strike": round(float(entry_quote.strike), 4),
        "expiry": str(entry_quote.expiry),
        "contract_symbol": entry_quote.contract_symbol,
        "entry_execution_price": round(float(entry_quote.price), 4),
        "entry_execution_basis": f"historical_comparable_{entry_quote.price_basis}",
        "entry_underlying_price": _safe_float(entry_quote.underlying_price) or _safe_float(scan_pick.get("stock_price") or scan_pick.get("entry_price")),
        "entry_fee_total_usd": commission_total_usd(contracts=1),
        "quote_time_et": _format_quote_time_et(entry_quote.quote_minute_et),
        "quote_basis": entry_quote.price_basis,
        "selection_source": "historical_comparable_exact_contract",
        "promotion_class": "comparable_exact_contract",
        "approximation_only": False,
        "comparable_contract": True,
        "comparable_contract_basis": "historical_entry_window",
        "comparable_contract_label": "Comparable Exact Contract",
        "resolution_notes": "Resolved from trusted historical option snapshots using the nearest listed entry-window contract.",
    }


def _resolve_live_contract_row(
    *,
    ticker: str,
    direction: str,
    target_expiry: str,
    target_strike: float,
    required_strikes: list[float] | None = None,
) -> Optional[tuple[str, Any]]:
    try:
        expiries = list(_cached_options(ticker) or [])
    except Exception:
        return None
    if not expiries:
        return None
    try:
        target_expiry_date = _parse_date(target_expiry)
    except Exception:
        target_expiry_date = datetime.now().date()
    sorted_expiries = sorted(
        expiries,
        key=lambda value: abs((_parse_date(value) - target_expiry_date).days),
    )
    required = [round(float(value), 4) for value in list(required_strikes or [])]
    for expiry in sorted_expiries:
        try:
            chain = _cached_option_chain(ticker, expiry)
            option_frame = chain.calls if direction == "call" else chain.puts
            if option_frame is None or option_frame.empty:
                continue
            strike_series = pd.to_numeric(option_frame["strike"], errors="coerce")
            if required:
                available = set(round(float(value), 4) for value in strike_series.dropna().tolist())
                if any(req not in available for req in required):
                    continue
            row = option_frame.loc[(strike_series - float(target_strike)).abs() <= 0.0001]
            if row.empty:
                continue
            return expiry, row.head(1)
        except Exception:
            continue
    return None


def _resolve_live_comparable_pick(scan_pick: dict[str, Any]) -> Optional[dict[str, Any]]:
    fields = _pick_context_fields(scan_pick)
    ticker = fields["ticker"]
    direction = fields["direction"]
    strike = fields["strike"]
    expiry = fields["expiry"]
    if not ticker or direction not in {"call", "put"} or strike is None or not expiry:
        return None

    if fields["strategy_type"] == "vertical_spread" and fields["short_strike"] is not None:
        long_match = _resolve_live_contract_row(
            ticker=ticker,
            direction=direction,
            target_expiry=expiry,
            target_strike=float(strike),
            required_strikes=[float(strike), float(fields["short_strike"])],
        )
        if long_match is None:
            return None
        resolved_expiry, long_row = long_match
        chain = _cached_option_chain(ticker, resolved_expiry)
        option_frame = chain.calls if direction == "call" else chain.puts
        strike_series = pd.to_numeric(option_frame["strike"], errors="coerce")
        short_row = option_frame.loc[(strike_series - float(fields["short_strike"])).abs() <= 0.0001].head(1)
        if short_row.empty:
            return None
        long_bid = _safe_float(long_row["bid"].iloc[0])
        long_ask = _safe_float(long_row["ask"].iloc[0])
        long_last = _safe_float(long_row["lastPrice"].iloc[0])
        short_bid = _safe_float(short_row["bid"].iloc[0])
        short_ask = _safe_float(short_row["ask"].iloc[0])
        short_last = _safe_float(short_row["lastPrice"].iloc[0])
        long_exec = executable_option_price(side="exit", bid=long_bid, ask=long_ask, last=long_last)
        short_exec = executable_option_price(side="entry", bid=short_bid, ask=short_ask, last=short_last)
        long_display = _safe_float(long_exec.get("display_price"))
        short_display = _safe_float(short_exec.get("display_price"))
        if long_display is None or short_display is None:
            return None
        entry_debit = round(max(long_display - short_display, 0.0001), 4)
        spread_width = abs(float(fields["short_strike"]) - float(strike))
        return {
            "strategy_type": "vertical_spread",
            "ticker": ticker,
            "direction": direction,
            "strike": round(float(strike), 4),
            "short_strike": round(float(fields["short_strike"]), 4),
            "expiry": str(resolved_expiry),
            "contract_symbol": _normalize_contract_symbol(long_row.get("contractSymbol").iloc[0]),
            "short_contract_symbol": _normalize_contract_symbol(short_row.get("contractSymbol").iloc[0]),
            "entry_execution_price": entry_debit,
            "entry_execution_basis": "live_comparable_spread_mid",
            "entry_underlying_price": _safe_float(scan_pick.get("stock_price") or scan_pick.get("entry_price")),
            "entry_fee_total_usd": commission_total_usd(contracts=1, sides=2),
            "quote_basis": "mid",
            "selection_source": "live_comparable_exact_contract",
            "promotion_class": "comparable_exact_contract",
            "approximation_only": False,
            "comparable_contract": True,
            "comparable_contract_basis": "live_chain_nearest_listed",
            "comparable_contract_label": "Comparable Exact Contract",
            "resolved_spread_width": round(float(spread_width), 4),
            "resolution_notes": "Resolved from the nearest listed live option chain contracts with matching strikes.",
        }

    single_match = _resolve_live_contract_row(
        ticker=ticker,
        direction=direction,
        target_expiry=expiry,
        target_strike=float(strike),
        required_strikes=[float(strike)],
    )
    if single_match is None:
        return None
    resolved_expiry, row = single_match
    bid = _safe_float(row["bid"].iloc[0])
    ask = _safe_float(row["ask"].iloc[0])
    last_price = _safe_float(row["lastPrice"].iloc[0])
    execution = executable_option_price(side="entry", bid=bid, ask=ask, last=last_price)
    display_price = _safe_float(execution.get("display_price"))
    if display_price is None:
        return None
    return {
        "strategy_type": "single_leg",
        "ticker": ticker,
        "direction": direction,
        "strike": round(float(strike), 4),
        "expiry": str(resolved_expiry),
        "contract_symbol": _normalize_contract_symbol(row.get("contractSymbol").iloc[0]),
        "entry_execution_price": round(float(display_price), 4),
        "entry_execution_basis": "live_comparable_mid",
        "entry_underlying_price": _safe_float(scan_pick.get("stock_price") or scan_pick.get("entry_price")),
        "entry_fee_total_usd": commission_total_usd(contracts=1),
        "quote_basis": str(execution.get("display_basis") or "mid"),
        "selection_source": "live_comparable_exact_contract",
        "promotion_class": "comparable_exact_contract",
        "approximation_only": False,
        "comparable_contract": True,
        "comparable_contract_basis": "live_chain_nearest_listed",
        "comparable_contract_label": "Comparable Exact Contract",
        "resolution_notes": "Resolved from the nearest listed live option chain contract.",
    }


def _scan_pick_log_rows() -> list[dict[str, Any]]:
    global _SCAN_PICK_LOG_CACHE
    if _SCAN_PICK_LOG_CACHE is not None:
        return list(_SCAN_PICK_LOG_CACHE)
    path = Path(__file__).resolve().parents[1] / "data" / "forward-tracking" / "scan_picks.jsonl"
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except Exception:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    except Exception:
        rows = []
    _SCAN_PICK_LOG_CACHE = rows
    return list(rows)


def _find_logged_scan_record(scan_pick: dict[str, Any], trade_date: date) -> Optional[dict[str, Any]]:
    fields = _pick_context_fields(scan_pick)
    for row in _scan_pick_log_rows():
        try:
            if str(row.get("scan_date") or "")[:10] != trade_date.isoformat():
                continue
            if str(row.get("ticker") or "").upper() != fields["ticker"]:
                continue
            if str(row.get("direction") or "").lower() != fields["direction"]:
                continue
            row_long = _safe_float(row.get("long_strike"))
            row_short = _safe_float(row.get("short_strike"))
            if fields["strike"] is None or row_long is None or abs(row_long - float(fields["strike"])) > 0.0001:
                continue
            if fields["short_strike"] is not None:
                if row_short is None or abs(row_short - float(fields["short_strike"])) > 0.0001:
                    continue
            elif row_short is not None:
                continue
            if fields["expiry"] and str(row.get("expiry") or "")[:10] != str(fields["expiry"])[:10]:
                continue
            return row
        except Exception:
            continue
    return None


def _resolve_logged_comparable_pick(scan_pick: dict[str, Any], *, trade_date: date) -> Optional[dict[str, Any]]:
    logged = _find_logged_scan_record(scan_pick, trade_date)
    if not logged:
        return None
    comparable_expiry = str(logged.get("approx_pricing_expiry") or "").strip()
    if not comparable_expiry:
        return None
    fields = _pick_context_fields(scan_pick)
    ticker = fields["ticker"]
    direction = fields["direction"]
    strike = fields["strike"]
    if not ticker or direction not in {"call", "put"} or strike is None:
        return None
    if fields["strategy_type"] == "vertical_spread" and fields["short_strike"] is not None:
        long_match = _resolve_live_contract_row(
            ticker=ticker,
            direction=direction,
            target_expiry=comparable_expiry,
            target_strike=float(strike),
            required_strikes=[float(strike), float(fields["short_strike"])],
        )
        if long_match is None:
            return None
        resolved_expiry, long_row = long_match
        chain = _cached_option_chain(ticker, resolved_expiry)
        option_frame = chain.calls if direction == "call" else chain.puts
        strike_series = pd.to_numeric(option_frame["strike"], errors="coerce")
        short_row = option_frame.loc[(strike_series - float(fields["short_strike"])).abs() <= 0.0001].head(1)
        if short_row.empty:
            return None
        return {
            "strategy_type": "vertical_spread",
            "ticker": ticker,
            "direction": direction,
            "strike": round(float(strike), 4),
            "short_strike": round(float(fields["short_strike"]), 4),
            "expiry": str(resolved_expiry),
            "contract_symbol": _normalize_contract_symbol(long_row.get("contractSymbol").iloc[0]),
            "short_contract_symbol": _normalize_contract_symbol(short_row.get("contractSymbol").iloc[0]),
            "entry_execution_price": _safe_float(scan_pick.get("entry_execution_price")) or _safe_float(logged.get("net_debit")),
            "entry_execution_basis": "logged_comparable_spread_debit",
            "entry_underlying_price": _safe_float(scan_pick.get("stock_price") or scan_pick.get("entry_price") or logged.get("underlying_price")),
            "quote_time_et": scan_pick.get("quote_time_et"),
            "quote_basis": "mid",
            "selection_source": "logged_comparable_exact_contract",
            "promotion_class": "comparable_exact_contract",
            "approximation_only": False,
            "comparable_contract": True,
            "comparable_contract_basis": "logged_nearest_listed_expiry_same_strikes",
            "comparable_contract_label": "Comparable Exact Contract",
            "resolution_notes": "Resolved from the logged nearest listed expiry with matching spread strikes.",
        }
    single_match = _resolve_live_contract_row(
        ticker=ticker,
        direction=direction,
        target_expiry=comparable_expiry,
        target_strike=float(strike),
        required_strikes=[float(strike)],
    )
    if single_match is None:
        return None
    resolved_expiry, row = single_match
    return {
        "strategy_type": "single_leg",
        "ticker": ticker,
        "direction": direction,
        "strike": round(float(strike), 4),
        "expiry": str(resolved_expiry),
        "contract_symbol": _normalize_contract_symbol(row.get("contractSymbol").iloc[0]),
        "entry_execution_price": _safe_float(scan_pick.get("entry_execution_price")) or _safe_float(logged.get("net_debit")),
        "entry_execution_basis": "logged_comparable_entry",
        "entry_underlying_price": _safe_float(scan_pick.get("stock_price") or scan_pick.get("entry_price") or logged.get("underlying_price")),
        "quote_time_et": scan_pick.get("quote_time_et"),
        "quote_basis": "mid",
        "selection_source": "logged_comparable_exact_contract",
        "promotion_class": "comparable_exact_contract",
        "approximation_only": False,
        "comparable_contract": True,
        "comparable_contract_basis": "logged_nearest_listed_expiry_same_strikes",
        "comparable_contract_label": "Comparable Exact Contract",
        "resolution_notes": "Resolved from the logged nearest listed expiry with matching strike.",
    }


def resolve_comparable_contract_pick(
    scan_pick: dict[str, Any],
    *,
    fill_price: float,
    filled_at: Optional[str] = None,
    preserve_fill_price: bool = False,
) -> tuple[dict[str, Any], float, Optional[dict[str, Any]]]:
    source_pick = copy.deepcopy(scan_pick or {})
    fields = _pick_context_fields(source_pick)
    if fields["contract_symbol"] and (fields["strategy_type"] != "vertical_spread" or fields["short_contract_symbol"]):
        return source_pick, float(fill_price), None

    trade_date = _pick_trade_date(source_pick, filled_at)
    resolution = _resolve_historical_comparable_pick(source_pick, trade_date=trade_date)
    if resolution is None:
        resolution = _resolve_logged_comparable_pick(source_pick, trade_date=trade_date)
    if resolution is None:
        resolution = _resolve_live_comparable_pick(source_pick)
    if resolution is None:
        return source_pick, float(fill_price), None

    resolved_pick = copy.deepcopy(source_pick)
    resolved_pick["original_snapshot_before_resolution"] = copy.deepcopy(source_pick)
    for key, value in resolution.items():
        resolved_pick[key] = value
    if resolution.get("contract_symbol"):
        resolved_pick["contract_symbol"] = resolution["contract_symbol"]
    if resolution.get("short_contract_symbol"):
        resolved_pick["short_contract_symbol"] = resolution["short_contract_symbol"]

    next_fill_price = float(fill_price)
    if not preserve_fill_price and _should_replace_fill_price(source_pick, fill_price):
        replacement = _safe_float(resolution.get("entry_execution_price"))
        if replacement is not None and replacement > 0:
            next_fill_price = float(replacement)
            resolved_pick["original_logged_entry_execution_price"] = float(fill_price)
            resolved_pick["entry_execution_basis"] = resolution.get("entry_execution_basis")
    else:
        resolved_pick["resolved_reference_entry_execution_price"] = resolution.get("entry_execution_price")

    return resolved_pick, next_fill_price, resolution


def build_position_payload(
    scan_pick: dict[str, Any],
    fill_price: float,
    contracts: int,
    filled_at: Optional[str] = None,
    notes: Optional[str] = None,
    *,
    require_proof_eligible: bool = False,
    require_resolved_contract: bool = False,
    preserve_fill_price: bool = False,
) -> dict[str, Any]:
    original_scan_pick = copy.deepcopy(scan_pick or {})
    resolved_scan_pick, resolved_fill_price, _resolution = resolve_comparable_contract_pick(
        scan_pick=original_scan_pick,
        fill_price=fill_price,
        filled_at=filled_at,
        preserve_fill_price=preserve_fill_price,
    )
    scan_pick = resolved_scan_pick
    fill_price = float(resolved_fill_price)
    ticker = str(scan_pick.get("ticker") or "").upper()
    direction = str(scan_pick.get("direction") or scan_pick.get("type") or "").lower()
    strike = scan_pick.get("strike") if scan_pick.get("strike") is not None else scan_pick.get("strike_est")
    expiry = scan_pick.get("expiry")
    contract_symbol = _normalize_contract_symbol(
        scan_pick.get("contract_symbol")
        or scan_pick.get("contractSymbol")
        or scan_pick.get("option_contract_symbol")
    )

    if not ticker or direction not in {"call", "put"} or strike is None or not expiry:
        raise ValueError("scan_pick is missing required option fields: ticker, direction/type, strike, or expiry.")
    if fill_price <= 0:
        raise ValueError("fill_price must be greater than 0.")
    if contracts <= 0:
        raise ValueError("contracts must be at least 1.")

    source_scan_session_id = scan_pick.get("source_scan_session_id")
    source_scan_event_key = scan_pick.get("source_scan_event_key")
    source_scan_run_id = scan_pick.get("source_scan_run_id")
    source_scan_recorded_at_utc = scan_pick.get("source_scan_recorded_at_utc")

    source_pick_snapshot = copy.deepcopy(scan_pick)
    source_pick_snapshot["original_logged_expiry"] = (
        original_scan_pick.get("original_logged_expiry")
        or original_scan_pick.get("expiry")
        or source_pick_snapshot.get("original_logged_expiry")
        or source_pick_snapshot.get("expiry")
    )
    source_pick_snapshot["resolved_listed_expiry"] = (
        source_pick_snapshot.get("resolved_listed_expiry")
        or source_pick_snapshot.get("expiry")
    )
    source_pick_snapshot["quote_time_utc"] = (
        source_pick_snapshot.get("quote_time_utc")
        or original_scan_pick.get("quote_time_utc")
        or source_scan_recorded_at_utc
    )
    source_pick_snapshot["entry_quote_snapshot"] = _entry_quote_snapshot(source_pick_snapshot)
    if contract_symbol:
        source_pick_snapshot["contract_symbol"] = contract_symbol
    entry_execution_price = round(float(fill_price), 4)
    estimated_execution_price = _safe_float(scan_pick.get("entry_execution_price"))
    entry_execution_basis = str(scan_pick.get("entry_execution_basis") or "").strip() or None
    if (
        entry_execution_basis
        and estimated_execution_price is not None
        and abs(float(estimated_execution_price) - entry_execution_price) <= 0.0001
    ):
        normalized_entry_execution_basis = entry_execution_basis
    else:
        normalized_entry_execution_basis = "manual_fill"
    strategy_type = _pick_strategy_type(scan_pick)
    entry_fee_total_usd = commission_total_usd(contracts=contracts, sides=2 if strategy_type == "vertical_spread" else 1)

    # Determine proof eligibility
    proof_eligible = True
    proof_ineligibility_reason = None
    selection_source = str(scan_pick.get("selection_source") or scan_pick.get("contract_selection_source") or "").strip()
    promotion_class = str(scan_pick.get("promotion_class") or "").strip()
    quote_time_et = scan_pick.get("quote_time_et")
    bid = _safe_float(scan_pick.get("bid"))
    ask = _safe_float(scan_pick.get("ask"))

    proof_missing: list[str] = []
    if not contract_symbol:
        proof_missing.append("contract_symbol")
    if not quote_time_et:
        proof_missing.append("quote_time_et")
    if bid is None:
        proof_missing.append("bid")
    if ask is None:
        proof_missing.append("ask")
    if estimated_execution_price is None and not scan_pick.get("entry_execution_price"):
        proof_missing.append("entry_execution_price")
    if selection_source != "live_chain_exact_contract":
        proof_missing.append("selection_source_not_exact")
    if promotion_class != "promotable_exact_contract":
        proof_missing.append("promotion_class_not_exact")
    if proof_missing:
        proof_eligible = False
        proof_ineligibility_reason = ", ".join(proof_missing)

    if require_proof_eligible and not proof_eligible:
        raise ValueError(
            f"Proof-lane position creation blocked: {proof_ineligibility_reason}. "
            "All proof-lane positions require exact-contract identity, executable entry quote, "
            "and live_chain_exact_contract selection source."
        )
    if require_resolved_contract and not _has_resolved_contract_identity(scan_pick):
        raise ValueError(
            "Position creation blocked: this pick could not be resolved to an exact listed contract "
            "or a comparable exact contract with full leg identity."
        )

    payload = {
        "status": "open",
        "ticker": ticker,
        "direction": direction,
        "strike": float(strike),
        "expiry": _parse_date(str(expiry)),
        "contract_symbol": contract_symbol,
        "asset_class": scan_pick.get("asset_class"),
        "contracts": int(contracts),
        "entry_option_price": round(float(fill_price), 4),
        "entry_execution_price": entry_execution_price,
        "entry_execution_basis": normalized_entry_execution_basis,
        "entry_fee_total_usd": entry_fee_total_usd,
        "entry_underlying_price": _safe_float(scan_pick.get("stock_price") or scan_pick.get("entry_price")),
        "filled_at": _parse_datetime(filled_at),
        "stop_loss_pct": float(scan_pick.get("stop_loss_pct") or 50.0),
        "profit_target_pct": float(scan_pick.get("profit_target_pct") or 100.0),
        "time_exit_day": int(scan_pick.get("time_exit_day") or 1),
        "peak_pnl_pct": None,
        "last_option_price": None,
        "last_pnl_pct": None,
        "last_recommendation": None,
        "last_recommendation_reason": None,
        "last_reviewed_at": None,
        "source_pick_snapshot": source_pick_snapshot,
        "notes": notes,
        "closed_at": None,
        "exit_option_price": None,
        "exit_execution_price": None,
        "exit_execution_basis": None,
        "exit_reason": None,
        "gross_pnl_pct": None,
        "net_pnl_pct": None,
        "gross_pnl_usd": None,
        "net_pnl_usd": None,
        "fee_total_usd": entry_fee_total_usd,
        "source_scan_session_id": source_scan_session_id,
        "source_scan_event_key": source_scan_event_key,
        "source_scan_run_id": source_scan_run_id,
        "source_scan_recorded_at_utc": source_scan_recorded_at_utc,
        "proof_eligible": proof_eligible,
        "proof_ineligibility_reason": proof_ineligibility_reason,
    }
    return payload


def _get_spy_ret5() -> float:
    try:
        hist = _cached_history("SPY", period="10d")["Close"].dropna()
        if len(hist) >= 6:
            return float((hist.iloc[-1] / hist.iloc[-6] - 1) * 100)
    except Exception:
        pass
    return 0.0


def _get_current_underlying_price(symbol: str) -> Optional[float]:
    try:
        hist = _cached_history(symbol, period="2d")["Close"].dropna()
        if not hist.empty:
            return float(hist.iloc[-1])
    except Exception:
        pass
    return None


def _get_underlying_close_on_or_before(symbol: str, target_date: date) -> Optional[float]:
    lookback_start = target_date - timedelta(days=7)
    try:
        hist = _cached_history(
            symbol,
            start=lookback_start.isoformat(),
            end=(target_date + timedelta(days=1)).isoformat(),
            interval="1d",
        )
    except Exception:
        return None
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None

    closes = hist["Close"].dropna()
    if closes.empty:
        return None

    latest_close: Optional[float] = None
    latest_close_date: Optional[date] = None
    for index, close_value in closes.items():
        try:
            index_date = index.date() if hasattr(index, "date") else _parse_date(index)
        except Exception:
            continue
        if index_date > target_date:
            continue
        latest_close = float(close_value)
        latest_close_date = index_date

    if latest_close_date is None:
        return None
    return latest_close


def _option_intrinsic_value(direction: str, strike: float, underlying_price: float) -> float:
    if direction == "put":
        return max(0.0, float(strike) - float(underlying_price))
    return max(0.0, float(underlying_price) - float(strike))


def _build_expired_auto_close(position: dict[str, Any], review_context: Optional[_ReviewContext] = None) -> dict[str, Any]:
    context = review_context or _ReviewContext()
    fields = _position_contract_fields(position)
    expiry_date = _parse_date(fields["expiry"])
    ticker_symbol = fields["ticker"]
    direction = fields["direction"]
    strike = _safe_float(fields["strike"])
    short_strike = _safe_float(fields["short_strike"])

    underlying_close = _get_underlying_close_on_or_before(ticker_symbol, expiry_date)
    close_basis = "expiry_intrinsic_underlying_close"
    if underlying_close is None:
        underlying_close = context.get_current_underlying_price(ticker_symbol)
        close_basis = "expiry_intrinsic_current_underlying_fallback"

    if underlying_close is None or strike is None:
        exit_price = 0.0
        close_basis = "expiry_zero_value_fallback"
        details = f"Auto-closed after expiry on {expiry_date.isoformat()} with a zero value fallback because no underlying settlement price was available."
    else:
        long_intrinsic = _option_intrinsic_value(direction, strike, underlying_close)
        if fields["strategy_type"] == "vertical_spread" and short_strike is not None:
            short_intrinsic = _option_intrinsic_value(direction, short_strike, underlying_close)
            exit_price = max(0.0, long_intrinsic - short_intrinsic)
        else:
            exit_price = max(0.0, long_intrinsic)
        details = (
            f"Auto-closed after expiry on {expiry_date.isoformat()} using {ticker_symbol} underlying close "
            f"{underlying_close:.2f} and intrinsic settlement."
        )

    return {
        "closed_at": datetime.combine(expiry_date, datetime.min.time()),
        "exit_price": round(float(exit_price), 4),
        "exit_execution_basis": close_basis,
        "exit_reason": "expired_auto_close",
        "notes": details,
    }


def _position_contract_fields(position: dict[str, Any]) -> dict[str, Any]:
    source_pick = _safe_dict(position.get("source_pick_snapshot"))
    return {
        "ticker": str(position.get("ticker") or source_pick.get("ticker") or "").upper(),
        "direction": str(position.get("direction") or source_pick.get("direction") or source_pick.get("type") or "").lower(),
        "strike": _safe_float(position.get("strike") if position.get("strike") is not None else source_pick.get("strike") or source_pick.get("strike_est")),
        "short_strike": _safe_float(source_pick.get("short_strike")),
        "expiry": str(position.get("expiry") or source_pick.get("expiry") or "")[:10],
        "contract_symbol": _normalize_contract_symbol(
            position.get("contract_symbol")
            or source_pick.get("contract_symbol")
            or source_pick.get("contractSymbol")
        ),
        "short_contract_symbol": _normalize_contract_symbol(source_pick.get("short_contract_symbol")),
        "strategy_type": _pick_strategy_type(source_pick),
    }


def _locate_live_option_row(option_frame: pd.DataFrame, *, contract_symbol: Optional[str], strike: Optional[float]) -> pd.DataFrame:
    row = pd.DataFrame()
    if contract_symbol:
        contract_column = None
        for candidate in ("contractSymbol", "contract_symbol"):
            if candidate in option_frame.columns:
                contract_column = candidate
                break
        if contract_column is None:
            return row
        contract_series = option_frame[contract_column].astype(str).str.upper()
        row = option_frame.loc[contract_series == contract_symbol]
    elif strike is not None:
        strike_series = pd.to_numeric(option_frame["strike"], errors="coerce")
        row = option_frame.loc[(strike_series - float(strike)).abs() <= 0.0001]
    return row.head(1)


def _fetch_vertical_spread_quote(
    position: dict[str, Any],
    context: Optional[_ReviewContext] = None,
) -> dict[str, Any]:
    review_context = context or _ReviewContext()
    fields = _position_contract_fields(position)
    ticker_symbol = fields["ticker"]
    expiry = fields["expiry"]
    direction = fields["direction"]
    long_strike = fields["strike"]
    short_strike = fields["short_strike"]
    long_contract_symbol = fields["contract_symbol"]
    short_contract_symbol = fields["short_contract_symbol"]
    warnings: list[str] = []
    underlying_price = review_context.get_current_underlying_price(ticker_symbol)
    profile = review_context.get_profile(ticker_symbol, direction)
    exit_slippage_pct = float((profile.get("filters") or {}).get("exit_slippage_pct", 0.0))
    expiry_date = _parse_date(expiry)
    today = datetime.now().date()

    if today > expiry_date:
        return {
            "expired": True,
            "current_option_price": None,
            "pricing_source": "expired",
            "pricing_state": "unpriced_expiry_not_available",
            "price_trigger_ok": False,
            "warnings": warnings,
            "underlying_price": underlying_price,
        }

    try:
        available_expiries = review_context.get_available_expiries(ticker_symbol)
    except Exception:
        return {
            "expired": False,
            "current_option_price": None,
            "pricing_source": "unavailable",
            "pricing_state": "unpriced_chain_fetch_failed",
            "price_trigger_ok": False,
            "warnings": ["Could not fetch the live options chain for this spread position."],
            "underlying_price": underlying_price,
        }

    if expiry not in available_expiries:
        return {
            "expired": False,
            "current_option_price": None,
            "pricing_source": "unavailable",
            "pricing_state": "unpriced_expiry_not_available",
            "price_trigger_ok": False,
            "warnings": ["The stored spread expiry is not available in the live chain yet."],
            "underlying_price": underlying_price,
        }

    try:
        chain = review_context.get_option_chain(ticker_symbol, expiry)
        option_frame = chain.calls if direction == "call" else chain.puts
        if option_frame is None or option_frame.empty:
            return {
                "expired": False,
                "current_option_price": None,
                "pricing_source": "unavailable",
                "pricing_state": "unpriced_exact_contract_not_in_chain",
                "price_trigger_ok": False,
                "warnings": ["The live option chain returned no contracts for this spread position."],
                "underlying_price": underlying_price,
            }

        long_row = _locate_live_option_row(option_frame, contract_symbol=long_contract_symbol, strike=long_strike)
        short_row = _locate_live_option_row(option_frame, contract_symbol=short_contract_symbol, strike=short_strike)
        if long_row.empty or short_row.empty:
            missing = []
            if long_row.empty:
                missing.append(long_contract_symbol or f"strike {long_strike}")
            if short_row.empty:
                missing.append(short_contract_symbol or f"strike {short_strike}")
            return {
                "expired": False,
                "current_option_price": None,
                "pricing_source": "unavailable",
                "pricing_state": "unpriced_exact_contract_not_in_chain",
                "price_trigger_ok": False,
                "warnings": [f"The live option chain is missing one or more spread legs: {', '.join(str(item) for item in missing)}."],
                "underlying_price": underlying_price,
            }

        long_exec = executable_option_price(
            side="exit",
            bid=_safe_float(long_row["bid"].iloc[0]),
            ask=_safe_float(long_row["ask"].iloc[0]),
            last=_safe_float(long_row["lastPrice"].iloc[0]),
            slippage_pct=exit_slippage_pct,
        )
        short_exec = executable_option_price(
            side="entry",
            bid=_safe_float(short_row["bid"].iloc[0]),
            ask=_safe_float(short_row["ask"].iloc[0]),
            last=_safe_float(short_row["lastPrice"].iloc[0]),
            slippage_pct=exit_slippage_pct,
        )
        long_display = _safe_float(long_exec.get("display_price"))
        short_display = _safe_float(short_exec.get("display_price"))
        if long_display is None or short_display is None:
            return {
                "expired": False,
                "current_option_price": None,
                "pricing_source": "unavailable",
                "pricing_state": "unpriced_chain_fetch_failed",
                "price_trigger_ok": False,
                "warnings": ["The live spread legs could not be displayed from the current quote snapshot."],
                "underlying_price": underlying_price,
            }
        current_option_price = round(max(long_display - short_display, 0.0), 4)
        long_execution = _safe_float(long_exec.get("execution_price"))
        short_execution = _safe_float(short_exec.get("execution_price"))
        current_execution_price = None
        current_execution_basis = None
        if long_execution is not None and short_execution is not None:
            current_execution_price = round(max(long_execution - short_execution, 0.0), 4)
            current_execution_basis = "spread_bidask"
            pricing_state = "priced_spread_exact"
            pricing_source = "spread_mid_exact"
        else:
            pricing_state = "priced_display_only_last"
            pricing_source = "spread_display_only"
            warnings.append(
                "Using display-only spread marks because one or both legs are missing a live executable bid/ask quote."
            )
        return {
            "expired": False,
            "current_option_price": current_option_price,
            "pricing_source": pricing_source,
            "pricing_state": pricing_state,
            "current_execution_price": current_execution_price,
            "current_execution_basis": current_execution_basis,
            "price_trigger_ok": current_execution_price is not None,
            "warnings": warnings,
            "underlying_price": underlying_price,
            "long_leg_display_price": long_display,
            "short_leg_display_price": short_display,
            "long_leg_execution_price": long_execution,
            "short_leg_execution_price": short_execution,
        }
    except Exception:
        return {
            "expired": False,
            "current_option_price": None,
            "pricing_source": "unavailable",
            "pricing_state": "unpriced_chain_fetch_failed",
            "price_trigger_ok": False,
            "warnings": ["The live spread quote could not be refreshed for this position."],
            "underlying_price": underlying_price,
        }


def _fetch_option_quote(position: dict[str, Any], context: Optional[_ReviewContext] = None) -> dict[str, Any]:
    review_context = context or _ReviewContext()
    fields = _position_contract_fields(position)
    if fields["strategy_type"] == "vertical_spread" and (fields["short_contract_symbol"] or fields["short_strike"] is not None):
        return _fetch_vertical_spread_quote(position, review_context)
    ticker_symbol = position["ticker"]
    expiry = str(position["expiry"])[:10]
    strike = float(position["strike"])
    direction = position["direction"]
    contract_symbol = fields["contract_symbol"]
    warnings: list[str] = []
    underlying_price = review_context.get_current_underlying_price(ticker_symbol)
    profile = review_context.get_profile(ticker_symbol, direction)
    exit_slippage_pct = float((profile.get("filters") or {}).get("exit_slippage_pct", 0.0))
    expiry_date = _parse_date(expiry)
    today = datetime.now().date()

    if today > expiry_date:
        return {
            "expired": True,
            "current_option_price": None,
            "pricing_source": "expired",
            "pricing_state": "unpriced_expiry_not_available",
            "price_trigger_ok": False,
            "warnings": warnings,
            "underlying_price": underlying_price,
        }

    try:
        available_expiries = review_context.get_available_expiries(ticker_symbol)
    except Exception:
        available_expiries = []
        warnings.append("Could not fetch the live options chain for this position.")
        return {
            "expired": False,
            "current_option_price": None,
            "pricing_source": "unavailable",
            "pricing_state": "unpriced_chain_fetch_failed",
            "price_trigger_ok": False,
            "warnings": warnings,
            "underlying_price": underlying_price,
        }

    if expiry not in available_expiries:
        warnings.append("The stored expiry is not available in the live chain yet.")
        return {
            "expired": False,
            "current_option_price": None,
            "pricing_source": "unavailable",
            "pricing_state": "unpriced_expiry_not_available",
            "price_trigger_ok": False,
            "warnings": warnings,
            "underlying_price": underlying_price,
        }

    try:
        chain = review_context.get_option_chain(ticker_symbol, expiry)
        option_frame = chain.calls if direction == "call" else chain.puts
        if option_frame is None or option_frame.empty:
            warnings.append("The live option chain returned no contracts for this position.")
            return {
                "expired": False,
                "current_option_price": None,
                "pricing_source": "unavailable",
                "pricing_state": "unpriced_exact_contract_not_in_chain",
                "price_trigger_ok": False,
                "warnings": warnings,
                "underlying_price": underlying_price,
            }

        row = pd.DataFrame()
        if contract_symbol:
            contract_column = None
            for candidate in ("contractSymbol", "contract_symbol"):
                if candidate in option_frame.columns:
                    contract_column = candidate
                    break
            if contract_column is None:
                warnings.append(
                    "The live option chain does not expose contract symbols, so this exact contract could not be verified."
                )
                return {
                    "expired": False,
                    "current_option_price": None,
                    "pricing_source": "unavailable",
                    "pricing_state": "unpriced_exact_contract_missing",
                    "price_trigger_ok": False,
                    "warnings": warnings,
                    "underlying_price": underlying_price,
                }

            contract_series = option_frame[contract_column].astype(str).str.upper()
            row = option_frame.loc[contract_series == contract_symbol]
            if row.empty:
                warnings.append(
                    f"The exact stored contract {contract_symbol} is not present in the live option chain, so this review stays unpriced."
                )
                return {
                    "expired": False,
                    "current_option_price": None,
                    "pricing_source": "unavailable",
                    "pricing_state": "unpriced_exact_contract_not_in_chain",
                    "price_trigger_ok": False,
                    "warnings": warnings,
                    "underlying_price": underlying_price,
                }
        else:
            strike_series = pd.to_numeric(option_frame["strike"], errors="coerce")
            row = option_frame.loc[(strike_series - strike).abs() <= 0.0001]
            if row.empty:
                warnings.append(
                    "The live option chain did not return the exact stored strike, and nearest-strike substitution is disabled for tracked positions."
                )
                return {
                    "expired": False,
                    "current_option_price": None,
                    "pricing_source": "unavailable",
                    "pricing_state": "unpriced_exact_contract_not_in_chain",
                    "price_trigger_ok": False,
                    "warnings": warnings,
                    "underlying_price": underlying_price,
                }

        row = row.head(1)

        bid = _safe_float(row["bid"].iloc[0])
        ask = _safe_float(row["ask"].iloc[0])
        last_price = _safe_float(row["lastPrice"].iloc[0])
        execution = executable_option_price(
            side="exit",
            bid=bid,
            ask=ask,
            last=last_price,
            slippage_pct=exit_slippage_pct,
        )

        if execution.get("display_price") is not None:
            if execution.get("execution_price") is None and execution.get("display_basis") == "last":
                warnings.append(
                    "Using last trade only for display; stop/target checks are suppressed until a live executable bid/ask quote returns."
                )
                pricing_state = "priced_display_only_last"
            elif execution.get("execution_price") is not None:
                pricing_state = "priced_exact"
            else:
                pricing_state = "priced_display_only_last"
            return {
                "expired": False,
                "current_option_price": execution.get("display_price"),
                "pricing_source": "mid" if execution.get("display_basis") == "mid" else execution.get("display_basis"),
                "pricing_state": pricing_state,
                "current_execution_price": execution.get("execution_price"),
                "current_execution_basis": execution.get("execution_basis"),
                "price_trigger_ok": execution.get("execution_price") is not None,
                "warnings": warnings,
                "underlying_price": underlying_price,
            }
    except Exception:
        warnings.append("The live option quote could not be refreshed for this position.")

    return {
        "expired": False,
        "current_option_price": None,
        "pricing_source": "unavailable",
        "pricing_state": "unpriced_chain_fetch_failed",
        "price_trigger_ok": False,
        "warnings": warnings,
        "underlying_price": underlying_price,
    }


def _check_indicator_exit_without_price(pick: dict[str, Any], spy_ret5: float = 0.0, sp: Optional[dict] = None) -> tuple[bool, str]:
    if sp is None:
        sp = _get_profile(pick.get("ticker", ""), pick.get("direction"))

    early_exit_cfg = sp.get("early_exit", {})
    if not early_exit_cfg.get("enabled", False):
        return False, ""

    trade_type = pick["direction"]
    is_bullish = trade_type in ("call", "bullish")

    try:
        tech_live, rsi_live, ret5_live = _compute_tech_score_live(pick["ticker"], trade_type)
    except Exception:
        return False, ""

    dir_score_live = _compute_direction_score(tech_live, trade_type, rsi_live, ret5_live, spy_ret5, sp=sp)

    entry_tech = float(pick.get("tech_score", 50.0) or 50.0)
    tech_decay_threshold = float(early_exit_cfg.get("tech_decay_pct", 35.0))
    if entry_tech > 0:
        decay_pct = (entry_tech - tech_live) / entry_tech * 100
        if decay_pct >= tech_decay_threshold:
            return True, f"tech_score collapsed {decay_pct:.0f}% ({entry_tech:.0f} -> {tech_live:.0f})"

    direction_floor = float(early_exit_cfg.get("direction_floor", 30.0))
    if dir_score_live < direction_floor:
        return True, f"direction_score {dir_score_live:.0f} fell below floor {direction_floor:.0f}"

    if early_exit_cfg.get("momentum_reversal", True):
        entry_ret5 = float(pick.get("ret5", 0.0) or 0.0)
        if entry_ret5 != 0 and ret5_live != 0:
            if is_bullish and entry_ret5 > 0 and ret5_live < -0.3:
                return True, f"momentum reversed: entry ret5 {entry_ret5:+.1f}% -> now {ret5_live:+.1f}%"
            if (not is_bullish) and entry_ret5 < 0 and ret5_live > 0.3:
                return True, f"momentum reversed: entry ret5 {entry_ret5:+.1f}% -> now {ret5_live:+.1f}%"

    if early_exit_cfg.get("rsi_extreme_exit", True):
        if is_bullish and rsi_live >= float(early_exit_cfg.get("rsi_call_ceiling", 78)):
            return True, f"RSI {rsi_live:.0f} hit overbought extreme - reversal risk"
        if (not is_bullish) and rsi_live <= float(early_exit_cfg.get("rsi_put_floor", 22)):
            return True, f"RSI {rsi_live:.0f} hit oversold extreme - reversal risk"

    return False, ""


def review_position(position: dict[str, Any], context: Optional[_ReviewContext] = None) -> dict[str, Any]:
    review_context = context or _ReviewContext()
    filled_at = _parse_datetime(position["filled_at"])
    contract_fields = _position_contract_fields(position)
    is_vertical_spread = contract_fields["strategy_type"] == "vertical_spread" and (
        contract_fields["short_contract_symbol"] or contract_fields["short_strike"] is not None
    )
    entry_option_price = float(position["entry_option_price"])
    stop_loss_pct = float(position["stop_loss_pct"])
    profit_target_pct = float(position["profit_target_pct"])
    time_exit_day = int(position["time_exit_day"])
    days_held = max((datetime.now().date() - filled_at.date()).days, 0)
    stop_option_price = round(entry_option_price * (1.0 - stop_loss_pct / 100.0), 4)
    target_option_price = round(entry_option_price * (1.0 + profit_target_pct / 100.0), 4)

    pricing = _fetch_option_quote(position, review_context)
    warnings = list(pricing.get("warnings") or [])
    current_option_price = pricing.get("current_option_price")
    contracts = int(position.get("contracts") or 1)
    entry_execution_price = _safe_float(position.get("entry_execution_price")) or entry_option_price
    exit_execution_price = _safe_float(pricing.get("current_execution_price"))
    if exit_execution_price is None and pricing.get("price_trigger_ok") and current_option_price is not None:
        exit_execution_price = float(current_option_price)
    entry_fee_total_usd = _safe_float(position.get("entry_fee_total_usd"))
    if entry_fee_total_usd is None:
        entry_fee_total_usd = commission_total_usd(contracts=contracts, sides=2 if is_vertical_spread else 1)
    exit_fee_total_usd = commission_total_usd(contracts=contracts, sides=2 if is_vertical_spread else 1) if exit_execution_price is not None else 0.0
    pnl_snapshot = option_pnl_snapshot(
        entry_execution_price=entry_execution_price,
        exit_execution_price=exit_execution_price,
        contracts=contracts,
        entry_fee_total_usd=entry_fee_total_usd,
        exit_fee_total_usd=exit_fee_total_usd,
    )
    current_pnl_pct = (
        round(float(pnl_snapshot["gross_pnl_pct"]), 1)
        if pnl_snapshot.get("gross_pnl_pct") is not None
        else None
    )

    current_stock_price = pricing.get("underlying_price")
    entry_underlying_price = _safe_float(position.get("entry_underlying_price"))
    current_stock_pct = None
    if current_stock_price is not None and entry_underlying_price and entry_underlying_price > 0:
        current_stock_pct = round((float(current_stock_price) / entry_underlying_price - 1.0) * 100.0, 2)

    existing_peak = _safe_float(position.get("peak_pnl_pct")) or 0.0
    peak_pnl_pct = existing_peak
    if pricing.get("price_trigger_ok") and current_pnl_pct is not None:
        peak_pnl_pct = round(max(existing_peak, current_pnl_pct), 1)

    recommendation = "HOLD"
    reason = "Position remains inside the stop, target, and exit rules."

    source_pick = copy.deepcopy(_safe_dict(position.get("source_pick_snapshot")))
    source_pick.setdefault("ticker", position["ticker"])
    source_pick.setdefault("direction", position["direction"])
    source_pick.setdefault("tech_score", source_pick.get("tech_score", 50.0))
    source_pick.setdefault("direction_score", source_pick.get("direction_score", 50.0))
    source_pick.setdefault("ret5", source_pick.get("ret5", 0.0))
    spy_ret5 = review_context.get_spy_ret5()
    profile = review_context.get_profile(position["ticker"], position["direction"])

    if pricing.get("expired"):
        recommendation = "SELL"
        reason = "Contract expiry has passed, so the position should be closed."
    elif pricing.get("price_trigger_ok") and current_pnl_pct is not None and current_pnl_pct <= -stop_loss_pct:
        recommendation = "SELL"
        reason = f"Live executable exit hit the stop loss at {current_pnl_pct:+.1f}%."
    elif pricing.get("price_trigger_ok") and current_pnl_pct is not None and current_pnl_pct >= profit_target_pct:
        recommendation = "SELL"
        reason = f"Live executable exit hit the profit target at {current_pnl_pct:+.1f}%."
    elif days_held >= time_exit_day:
        recommendation = "SELL"
        reason = f"Time exit reached after {days_held} calendar day(s), versus a {time_exit_day}-day limit."
    else:
        early_exit_cfg = profile.get("early_exit", {})
        min_hold_days = int(early_exit_cfg.get("min_hold_days", 1))
        if days_held >= min_hold_days:
            indicator_exit = False
            indicator_detail = ""
            if pricing.get("price_trigger_ok") and current_pnl_pct is not None:
                min_profit_to_exit = float(early_exit_cfg.get("min_profit_to_exit_pct", 5.0))
                if current_pnl_pct >= min_profit_to_exit:
                    indicator_exit, indicator_detail = _check_early_exit(
                        pick=source_pick,
                        current_pnl_pct=current_pnl_pct,
                        peak_pnl_pct=peak_pnl_pct,
                        sp=profile,
                        spy_ret5=spy_ret5,
                    )
            else:
                indicator_exit, indicator_detail = _check_indicator_exit_without_price(
                    pick=source_pick,
                    spy_ret5=spy_ret5,
                    sp=profile,
                )

            if indicator_exit:
                recommendation = "SELL"
                reason = f"Indicator exit triggered: {indicator_detail}"

    pricing_state = pricing.get("pricing_state") or (
        "priced_exact" if pricing.get("price_trigger_ok") else "unpriced_chain_fetch_failed"
    )

    metrics_snapshot = {
        "days_held": days_held,
        "contract_symbol": _normalize_contract_symbol(
            position.get("contract_symbol")
            or source_pick.get("contract_symbol")
            or source_pick.get("contractSymbol")
        ),
        "stop_option_price": stop_option_price,
        "target_option_price": target_option_price,
        "entry_option_price": entry_option_price,
        "entry_execution_price": entry_execution_price,
        "entry_execution_basis": position.get("entry_execution_basis"),
        "entry_underlying_price": entry_underlying_price,
        "current_underlying_price": current_stock_price,
        "current_stock_pct": current_stock_pct,
        "price_trigger_ok": bool(pricing.get("price_trigger_ok")),
        "pricing_state": pricing_state,
        "exit_execution_price": exit_execution_price,
        "exit_execution_basis": pricing.get("current_execution_basis"),
        "gross_pnl_pct": pnl_snapshot.get("gross_pnl_pct"),
        "net_pnl_pct": pnl_snapshot.get("net_pnl_pct"),
        "gross_pnl_usd": pnl_snapshot.get("gross_pnl_usd"),
        "net_pnl_usd": pnl_snapshot.get("net_pnl_usd"),
        "fee_total_usd": pnl_snapshot.get("fee_total_usd"),
        "expiry": str(position["expiry"])[:10],
    }

    return {
        "position_id": position["id"],
        "reviewed_at": datetime.now().isoformat(),
        "pricing_source": pricing.get("pricing_source"),
        "pricing_state": pricing_state,
        "current_option_price": current_option_price,
        "current_pnl_pct": current_pnl_pct,
        "gross_pnl_pct": pnl_snapshot.get("gross_pnl_pct"),
        "net_pnl_pct": pnl_snapshot.get("net_pnl_pct"),
        "gross_pnl_usd": pnl_snapshot.get("gross_pnl_usd"),
        "net_pnl_usd": pnl_snapshot.get("net_pnl_usd"),
        "entry_execution_price": entry_execution_price,
        "exit_execution_price": exit_execution_price,
        "entry_execution_basis": position.get("entry_execution_basis"),
        "exit_execution_basis": pricing.get("current_execution_basis"),
        "fee_total_usd": pnl_snapshot.get("fee_total_usd"),
        "recommendation": recommendation,
        "reason": reason,
        "warnings": warnings,
        "metrics_snapshot": metrics_snapshot,
        "peak_pnl_pct": peak_pnl_pct,
    }


def review_open_positions(repository, position_ids: Optional[list[int]] = None) -> list[dict[str, Any]]:
    with _market_data_request_scope():
        review_context = _ReviewContext()
        positions = repository.list_positions(status="open")
        if position_ids:
            requested = {int(position_id) for position_id in position_ids}
            positions = [position for position in positions if int(position["id"]) in requested]

        reviewed_positions: list[dict[str, Any]] = []
        for position in positions:
            source_pick = _safe_dict(position.get("source_pick_snapshot"))
            latest_review = position.get("latest_review") or {}
            needs_resolution = not _has_resolved_contract_identity(source_pick)
            resolved_position = False
            if needs_resolution and hasattr(repository, "update_position"):
                resolved_pick, resolved_fill_price, resolution = resolve_comparable_contract_pick(
                    source_pick,
                    fill_price=float(position.get("entry_option_price") or 0.0),
                    filled_at=position.get("filled_at"),
                )
                if resolution is not None and _has_resolved_contract_identity(resolved_pick):
                    strategy_type = _pick_strategy_type(resolved_pick)
                    contracts = max(int(position.get("contracts") or 1), 1)
                    position = repository.update_position(
                        int(position["id"]),
                        {
                            "contract_symbol": _normalize_contract_symbol(resolved_pick.get("contract_symbol")),
                            "strike": float(resolved_pick.get("strike")),
                            "expiry": _parse_date(str(resolved_pick.get("expiry"))),
                            "entry_option_price": round(float(resolved_fill_price), 4),
                            "entry_execution_price": round(float(resolved_fill_price), 4),
                            "entry_execution_basis": str(
                                resolved_pick.get("entry_execution_basis") or "comparable_contract_entry"
                            ),
                            "entry_fee_total_usd": commission_total_usd(
                                contracts=contracts,
                                sides=2 if strategy_type == "vertical_spread" else 1,
                            ),
                            "entry_underlying_price": _safe_float(
                                resolved_pick.get("entry_underlying_price")
                            )
                            or _safe_float(position.get("entry_underlying_price")),
                            "source_pick_snapshot": resolved_pick,
                            "proof_eligible": False,
                            "proof_ineligibility_reason": "comparable_exact_contract",
                        },
                    )
                    resolved_position = True
            if needs_resolution and not resolved_position and source_pick.get("approximation_only") and latest_review:
                reviewed_positions.append(position)
                continue
            review = review_position(position, review_context)
            saved_position = repository.save_review(int(position["id"]), review)
            if (
                review.get("pricing_source") == "expired"
                and review.get("recommendation") == "SELL"
                and hasattr(repository, "close_position")
            ):
                auto_close = _build_expired_auto_close(position, review_context)
                closed_position = repository.close_position(
                    int(position["id"]),
                    exit_price=float(auto_close["exit_price"]),
                    closed_at=auto_close["closed_at"],
                    exit_reason=str(auto_close["exit_reason"]),
                    notes=str(auto_close["notes"]),
                    exit_execution_basis=str(auto_close["exit_execution_basis"]),
                    allow_zero_exit_price=True,
                )
                reviewed_positions.append(closed_position or saved_position)
                continue
            reviewed_positions.append(saved_position)
        return reviewed_positions
