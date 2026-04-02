from __future__ import annotations

import copy
import math
from datetime import date, datetime
from typing import Any, Optional

import pandas as pd
import yfinance as yf

from market_data_service import (
    get_history as _md_get_history,
    get_option_chain as _md_get_option_chain,
    get_options as _md_get_options,
    request_scope as _market_data_request_scope,
)
from options_chatbot import (
    _check_early_exit,
    _compute_direction_score,
    _compute_tech_score_live,
    _get_profile,
)


class _ReviewContext:
    def __init__(self):
        self._spy_ret5: Optional[float] = None
        self._profile_cache: dict[str, dict[str, Any]] = {}
        self._underlying_price_cache: dict[str, Optional[float]] = {}
        self._available_expiries_cache: dict[str, list[str]] = {}
        self._option_chain_cache: dict[tuple[str, str], Any] = {}

    def get_spy_ret5(self) -> float:
        if self._spy_ret5 is None:
            self._spy_ret5 = _get_spy_ret5()
        return self._spy_ret5

    def get_profile(self, symbol: str) -> dict[str, Any]:
        key = str(symbol or "").upper()
        if key not in self._profile_cache:
            self._profile_cache[key] = _get_profile(key)
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


def _normalize_contract_symbol(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    return raw.upper() if raw else None


def build_position_payload(
    scan_pick: dict[str, Any],
    fill_price: float,
    contracts: int,
    filled_at: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
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

    source_pick_snapshot = copy.deepcopy(scan_pick)
    if contract_symbol:
        source_pick_snapshot["contract_symbol"] = contract_symbol

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
        "exit_reason": None,
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


def _fetch_option_quote(position: dict[str, Any], context: Optional[_ReviewContext] = None) -> dict[str, Any]:
    review_context = context or _ReviewContext()
    ticker_symbol = position["ticker"]
    expiry = str(position["expiry"])[:10]
    strike = float(position["strike"])
    direction = position["direction"]
    contract_symbol = _normalize_contract_symbol(
        position.get("contract_symbol")
        or (position.get("source_pick_snapshot") or {}).get("contract_symbol")
        or (position.get("source_pick_snapshot") or {}).get("contractSymbol")
    )
    warnings: list[str] = []
    underlying_price = review_context.get_current_underlying_price(ticker_symbol)
    expiry_date = _parse_date(expiry)
    today = datetime.now().date()

    if today > expiry_date:
        return {
            "expired": True,
            "current_option_price": None,
            "pricing_source": "expired",
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
                    "price_trigger_ok": False,
                    "warnings": warnings,
                    "underlying_price": underlying_price,
                }

        row = row.head(1)

        bid = _safe_float(row["bid"].iloc[0])
        ask = _safe_float(row["ask"].iloc[0])
        last_price = _safe_float(row["lastPrice"].iloc[0])

        if bid and ask and ask >= bid:
            return {
                "expired": False,
                "current_option_price": round((bid + ask) / 2.0, 4),
                "pricing_source": "mid",
                "price_trigger_ok": True,
                "warnings": warnings,
                "underlying_price": underlying_price,
            }

        if last_price and last_price > 0:
            warnings.append(
                "Using last trade only for display; stop/target checks are suppressed until a live bid/ask midpoint returns."
            )
            return {
                "expired": False,
                "current_option_price": round(last_price, 4),
                "pricing_source": "last_price",
                "price_trigger_ok": False,
                "warnings": warnings,
                "underlying_price": underlying_price,
            }
    except Exception:
        warnings.append("The live option quote could not be refreshed for this position.")

    return {
        "expired": False,
        "current_option_price": None,
        "pricing_source": "unavailable",
        "price_trigger_ok": False,
        "warnings": warnings,
        "underlying_price": underlying_price,
    }


def _check_indicator_exit_without_price(pick: dict[str, Any], spy_ret5: float = 0.0, sp: Optional[dict] = None) -> tuple[bool, str]:
    if sp is None:
        sp = _get_profile(pick.get("ticker", ""))

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
    current_pnl_pct = None
    if current_option_price is not None and entry_option_price > 0:
        current_pnl_pct = round((float(current_option_price) / entry_option_price - 1.0) * 100.0, 1)

    current_stock_price = pricing.get("underlying_price")
    entry_underlying_price = _safe_float(position.get("entry_underlying_price"))
    current_stock_pct = None
    if current_stock_price is not None and entry_underlying_price and entry_underlying_price > 0:
        current_stock_pct = round((float(current_stock_price) / entry_underlying_price - 1.0) * 100.0, 2)

    existing_peak = _safe_float(position.get("peak_pnl_pct")) or 0.0
    peak_pnl_pct = existing_peak
    if pricing.get("pricing_source") == "mid" and current_pnl_pct is not None:
        peak_pnl_pct = round(max(existing_peak, current_pnl_pct), 1)

    recommendation = "HOLD"
    reason = "Position remains inside the stop, target, and exit rules."

    source_pick = copy.deepcopy(position.get("source_pick_snapshot") or {})
    source_pick.setdefault("ticker", position["ticker"])
    source_pick.setdefault("direction", position["direction"])
    source_pick.setdefault("tech_score", source_pick.get("tech_score", 50.0))
    source_pick.setdefault("direction_score", source_pick.get("direction_score", 50.0))
    source_pick.setdefault("ret5", source_pick.get("ret5", 0.0))
    spy_ret5 = review_context.get_spy_ret5()
    profile = review_context.get_profile(position["ticker"])

    if pricing.get("expired"):
        recommendation = "SELL"
        reason = "Contract expiry has passed, so the position should be closed."
    elif pricing.get("price_trigger_ok") and current_pnl_pct is not None and current_pnl_pct <= -stop_loss_pct:
        recommendation = "SELL"
        reason = f"Live option midpoint hit the stop loss at {current_pnl_pct:+.1f}%."
    elif pricing.get("price_trigger_ok") and current_pnl_pct is not None and current_pnl_pct >= profit_target_pct:
        recommendation = "SELL"
        reason = f"Live option midpoint hit the profit target at {current_pnl_pct:+.1f}%."
    elif days_held >= time_exit_day:
        recommendation = "SELL"
        reason = f"Time exit reached after {days_held} calendar day(s), versus a {time_exit_day}-day limit."
    else:
        early_exit_cfg = profile.get("early_exit", {})
        min_hold_days = int(early_exit_cfg.get("min_hold_days", 1))
        if days_held >= min_hold_days:
            indicator_exit = False
            indicator_detail = ""
            if pricing.get("pricing_source") == "mid" and current_pnl_pct is not None:
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
        "entry_underlying_price": entry_underlying_price,
        "current_underlying_price": current_stock_price,
        "current_stock_pct": current_stock_pct,
        "price_trigger_ok": bool(pricing.get("price_trigger_ok")),
        "expiry": str(position["expiry"])[:10],
    }

    return {
        "position_id": position["id"],
        "reviewed_at": datetime.now().isoformat(),
        "pricing_source": pricing.get("pricing_source"),
        "current_option_price": current_option_price,
        "current_pnl_pct": current_pnl_pct,
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
            review = review_position(position, review_context)
            reviewed_positions.append(repository.save_review(int(position["id"]), review))
        return reviewed_positions
