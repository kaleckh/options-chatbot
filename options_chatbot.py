#!/usr/bin/env
#  python3
"""
Options Trading Engine
Powered by Yahoo Finance (yfinance)

Specializes in:
- US large-cap stocks and ETFs with high options liquidity
- Single-leg positions: long/short calls and puts
- DTE range: 5–35 days to expiration

Free enhancements:
- IV Analysis: HV30, HV Rank, IV vs HV comparison
- Earnings calendar: warns when earnings fall within your DTE
- Market context: VIX level, SPY/QQQ trend, market regime
- Put/Call ratio: directional sentiment from live options flow
- Paper trading journal: log trades and track real P&L
- Strategy backtester: simulate how a strategy would have performed historically
- Daily predictions tracker: log directional calls, auto-grade them, track accuracy over time
"""

import os
import re
import json
import math
import glob
import shutil
import subprocess
from functools import wraps
from typing import Optional
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import yfinance as yf

from expectancy_calibration import (
    DEFAULT_SHRINKAGE_TRADES,
    DEFAULT_SPARSE_WARNING_TRADES,
    DEFAULT_SURFACE_MIN_TRADES,
    build_expectancy_surface,
    lookup_calibrated_expectancy,
    normalized_market_regime,
)
from market_data_service import (
    get_earnings_dates as _md_get_earnings_dates,
    get_fast_info as _md_get_fast_info,
    get_history as _md_get_history,
    get_option_chain as _md_get_option_chain,
    get_options as _md_get_options,
    get_ticker_info as _md_get_ticker_info,
    request_scope as _market_data_request_scope,
)

_ET = ZoneInfo("America/New_York")

def _market_is_open() -> bool:
    """Return True only if US equities market is currently in regular session (9:30–16:00 ET, Mon–Fri)."""
    now = datetime.now(_ET)
    if now.weekday() >= 5:
        return False
    open_  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_ = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_ <= now <= close_

RISK_FREE_RATE = 0.045  # 4.5% — approximate 3-month T-bill. Update periodically.

# System-wide DTE bounds — enforced across scan, _fetch_best_option, and WFO.
DTE_MIN = 5   # never enter a position with fewer than 5 days to expiry
DTE_MAX = 35  # never look for expirations beyond 35 days out
DEFAULT_SCAN_PICKS = 1

# Only trade names that are seasoned enough to replay honestly and liquid enough
# that stock movement and option execution are easier to trust.
UNDERLYING_LIQUIDITY_WINDOW = 20
UNDERLYING_FILTERS = {
    "history_days_min": 252,
    "avg_volume_20d_min": 3_000_000,
    "avg_dollar_volume_20d_min": 250_000_000,
}

DEFAULT_WATCHLIST = [
    # ── Index ETFs (bypass sector rule, use index strategy profile) ───────────
    "SPY", "QQQ", "IWM", "DIA", "XLK",
    # ── Technology ────────────────────────────────────────────────────────────
    "AAPL", "NVDA", "MSFT", "META", "AMD",
    # ── Communication Services ────────────────────────────────────────────────
    "GOOGL", "NFLX", "DIS", "T", "CMCSA",
    # ── Financials ────────────────────────────────────────────────────────────
    "JPM", "GS", "BAC", "V", "C",
    # ── Healthcare ────────────────────────────────────────────────────────────
    "UNH", "LLY", "JNJ", "ABBV", "PFE",
    # ── Energy ────────────────────────────────────────────────────────────────
    "XOM", "CVX", "OXY", "COP", "SLB",
    # ── Consumer Discretionary ────────────────────────────────────────────────
    "TSLA", "AMZN", "MCD", "NKE", "SBUX",
    # ── Consumer Staples ──────────────────────────────────────────────────────
    "WMT", "KO", "COST", "PG", "PM",
    # ── Industrials ───────────────────────────────────────────────────────────
    "CAT", "BA", "DE", "LMT", "RTX",
    # ── Materials ─────────────────────────────────────────────────────────────
    "FCX", "NEM", "CLF", "AA", "LIN",
    # ── Real Estate ───────────────────────────────────────────────────────────
    "AMT", "PLD", "SPG", "WELL", "EQR",
    # ── Speculative / High-Beta ───────────────────────────────────────────────
    "COIN", "MSTR", "PLTR", "ARM", "SMCI",
]

# High-beta names most likely to make the big % moves needed for 2x options gains
HIGH_BETA_WATCHLIST = [
    "NVDA", "TSLA", "AMD", "COIN", "PLTR", "MSTR", "ARM", "SMCI",
    "NFLX", "META", "GOOGL", "AMZN", "AAPL", "MSFT",
    "LLY", "OXY", "FCX", "CLF",   # high-IV / high-beta additions
]

# Tickers treated as broad-market indexes (use index strategy profile, no earnings filter)
INDEX_TICKERS = {"QQQ", "SPY", "IWM", "DIA", "XLK"}

def _asset_class(ticker: str) -> str:
    """'index' for broad-market ETFs, 'equity' for everything else."""
    return "index" if ticker.upper() in INDEX_TICKERS else "equity"


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


def _cached_ticker_info(symbol: str) -> dict:
    return _md_get_ticker_info(symbol, ticker_factory=yf.Ticker)


def _cached_earnings_dates(symbol: str) -> pd.DataFrame:
    return _md_get_earnings_dates(symbol, ticker_factory=yf.Ticker)


def _cached_options(symbol: str) -> list[str]:
    return _md_get_options(symbol, ticker_factory=yf.Ticker)


def _cached_options_metadata(symbol: str):
    return _md_get_options(symbol, ticker_factory=yf.Ticker, include_metadata=True)


def _cached_option_chain(symbol: str, expiry: str):
    return _md_get_option_chain(symbol, expiry, ticker_factory=yf.Ticker)


def _cached_option_chain_metadata(symbol: str, expiry: str):
    return _md_get_option_chain(symbol, expiry, ticker_factory=yf.Ticker, include_metadata=True)


def _cached_fast_info(symbol: str):
    return _md_get_fast_info(symbol, ticker_factory=yf.Ticker)


def _fast_info_last_price(fast_info) -> float:
    if not fast_info:
        return 0.0
    if isinstance(fast_info, dict):
        getter = fast_info.get
    else:
        getter = lambda key: getattr(fast_info, key, None)
    for key in ("last_price", "regular_market_price", "lastPrice", "regularMarketPrice"):
        value = getter(key)
        if value is not None:
            try:
                return float(value)
            except Exception:
                continue
    return 0.0


def _market_data_scoped(fn):
    @wraps(fn)
    def _wrapped(*args, **kwargs):
        with _market_data_request_scope():
            return fn(*args, **kwargs)
    return _wrapped


def _underlying_liquidity_snapshot(hist, window: int = UNDERLYING_LIQUIDITY_WINDOW) -> dict:
    """Summarize whether an underlying is seasoned and liquid enough to trade."""
    if hist is None or hist.empty or "Close" not in hist or "Volume" not in hist:
        return {
            "eligible": False,
            "history_days": 0,
            "avg_volume_20d": 0.0,
            "avg_dollar_volume_20d": 0.0,
            "liquidity_tier": "insufficient",
            "failures": ["Missing close/volume history"],
        }

    closes = hist["Close"].dropna().astype(float)
    if closes.empty:
        return {
            "eligible": False,
            "history_days": 0,
            "avg_volume_20d": 0.0,
            "avg_dollar_volume_20d": 0.0,
            "liquidity_tier": "insufficient",
            "failures": ["Missing close history"],
        }

    volumes = hist["Volume"].reindex(closes.index).fillna(0.0).astype(float)
    history_days = int(len(closes))
    calc_window = min(int(window), history_days)
    avg_volume_20d = float(volumes.tail(calc_window).mean()) if calc_window else 0.0
    avg_dollar_volume_20d = float((closes.tail(calc_window) * volumes.tail(calc_window)).mean()) if calc_window else 0.0

    failures: list[str] = []
    if history_days < int(UNDERLYING_FILTERS["history_days_min"]):
        failures.append("Insufficient trading history")
    if avg_volume_20d < float(UNDERLYING_FILTERS["avg_volume_20d_min"]):
        failures.append("Average stock volume too low")
    if avg_dollar_volume_20d < float(UNDERLYING_FILTERS["avg_dollar_volume_20d_min"]):
        failures.append("Average dollar volume too low")

    if avg_volume_20d >= 10_000_000 and avg_dollar_volume_20d >= 1_000_000_000:
        tier = "elite"
    elif avg_volume_20d >= float(UNDERLYING_FILTERS["avg_volume_20d_min"]) and avg_dollar_volume_20d >= float(UNDERLYING_FILTERS["avg_dollar_volume_20d_min"]):
        tier = "liquid"
    else:
        tier = "thin"

    return {
        "eligible": not failures,
        "history_days": history_days,
        "avg_volume_20d": round(avg_volume_20d, 0),
        "avg_dollar_volume_20d": round(avg_dollar_volume_20d, 2),
        "liquidity_tier": tier,
        "failures": failures,
    }


def _candidate_rank_tuple(candidate: dict) -> tuple:
    calibrated = candidate.get("calibrated_expectancy_pct")
    promotable_exact = str(candidate.get("promotion_class") or "").strip().lower() == "promotable_exact_contract"
    dense_calibration = bool(candidate.get("calibration_is_dense"))
    calibrated_value = (
        float(calibrated)
        if calibrated is not None and promotable_exact and dense_calibration
        else -9999.0
    )
    return (
        1 if promotable_exact else 0,
        1 if dense_calibration else 0,
        calibrated_value,
        float(candidate.get("direction_score", 0.0) or 0.0),
        float(candidate.get("quality_score", 0.0) or 0.0),
        float(candidate.get("tech_score", 0.0) or 0.0),
    )


def _candidate_signal_value(candidate: dict) -> float:
    return float(candidate.get("direction_score", 0.0) or 0.0)


def _live_contract_selection_source(option_snapshot: dict | None) -> str:
    if not option_snapshot:
        return "model_contract_fallback"
    if bool(option_snapshot.get("live_chain")) and option_snapshot.get("contract_symbol"):
        return "live_chain_exact_contract"
    return "model_contract_fallback"


def _live_pick_promotion_class(
    *,
    has_exact_contract: bool,
    calibration_lookup: Optional[dict],
    dense_calibration: Optional[dict],
) -> str:
    if not has_exact_contract:
        return "research_bootstrap"
    if calibration_lookup is not None and dense_calibration is None:
        return "research_sparse_calibration"
    if dense_calibration is not None:
        return "promotable_exact_contract"
    return "research_bootstrap"


def _load_expectancy_surface_for_live(
    min_trades: int = DEFAULT_SURFACE_MIN_TRADES,
    bucket_size: int = 10,
    *,
    truth_lane: str = "historical_imported_daily",
    playbook: str = "broad",
) -> dict | None:
    try:
        from wfo_optimizer import (
            IMPORTED_DAILY_TRUTH_SOURCE,
            MIN_IMPORTED_QUOTE_COVERAGE_PCT,
            load_last_imported_daily_results,
        )
    except Exception:
        return None

    normalized_truth_lane = str(truth_lane or IMPORTED_DAILY_TRUTH_SOURCE).strip().lower() or IMPORTED_DAILY_TRUTH_SOURCE
    if normalized_truth_lane != IMPORTED_DAILY_TRUTH_SOURCE:
        return None

    result = load_last_imported_daily_results()
    if not result:
        return None
    if str(result.get("truth_source") or "").strip().lower() != IMPORTED_DAILY_TRUTH_SOURCE:
        return None
    if str(result.get("playbook") or "").strip().lower() != str(playbook or "broad").strip().lower():
        return None
    if float(result.get("quote_coverage_pct", 0.0) or 0.0) < float(MIN_IMPORTED_QUOTE_COVERAGE_PCT):
        return None

    return build_expectancy_surface(
        result=result,
        min_trades=min_trades,
        bucket_size=bucket_size,
        shrinkage_trades=DEFAULT_SHRINKAGE_TRADES,
        sparse_warning_trades=DEFAULT_SPARSE_WARNING_TRADES,
    )


def _get_profile(ticker: str) -> dict:
    """Return the strategy profile dict for the given ticker."""
    return STRATEGY_PROFILES[_asset_class(ticker)]

# ─── Risk settings (user can update account_size mid-conversation) ────────────
# Claude will read/write these via the manage_risk_settings tool.
# risk_settings is a live alias for STRATEGY_PROFILE["risk"] — defined after STRATEGY_PROFILE below

PAPER_TRADES_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trades.json")
PREDICTIONS_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predictions.json")

# ─── Dual Strategy Profiles ────────────────────────────────────────────────────
# Two independent parameter sets — identical structure, different defaults.
# equity: single stocks — existing values, unchanged.
# index:  broad-market ETFs — longer DTE, tighter delta, lower VIX threshold.
STRATEGY_PROFILES: dict[str, dict] = {
    "equity": {
        "name": "OTM Short-Duration Momentum Strategy (Equity)",
        "philosophy": (
            "Buy OTM calls or puts on high-conviction momentum signals with strict entry filters. "
            "Entry is gated by signal quality, volatility regime, and liquidity. "
            "Position size scales with conviction. Exit rules are fixed and non-negotiable."
        ),
        "confidence_weights": {
            "iv_percentile": 0.40,
            "delta":         0.30,
            "dte":           0.20,
            "technical":     0.10,
        },
        "targets": {
            "delta_optimal":     0.30,
            "delta_falloff":     0.20,
            "dte_optimal":       10,
            "dte_falloff":       20,
            "iv_percentile_max": 50,
        },
        "filters": {
            "vix_defense_threshold":        25.0,
            "atr_expansion_stop_mult":       1.5,
            "defense_position_mult":         0.5,
            "liquidity_spread_max_pct":      1.5,
            "illiquid_extra_margin_pct":    10.0,
            "min_option_mid_price":          0.30,
            "min_option_volume":            100,
            "min_option_open_interest":     500,
            "max_option_quote_age_hours":   48.0,
            "min_calibrated_expectancy_pct": 10.0,
            "entry_slippage_pct":            5.0,
            "exit_slippage_pct":             5.0,
            "iv_crush_z_threshold":          2.0,
            "iv_crush_confidence_penalty":  20.0,
            "min_ev_return_pct":            10.0,
        },
        "risk": {
            "stop_loss_pct":       50.0,
            "profit_target_pct":  100.0,
            "max_position_pct":     3.0,
            "min_position_pct":     0.5,
            "account_size":        None,
            "max_drawdown_pct":    15.0,
            "dte_0_max_pct":        0.5,
            "time_exit_pct":       50.0,
        },
        "entry": {
            "entry_momentum_pct":  0.50,
            "min_direction_score": 55.0,
            "min_tech_score":      65.0,
        },
        "direction_score_weights": {
            "tech":     0.55,
            "regime":   0.30,
            "momentum": 0.15,
        },
        "rsi_overextension": {
            "severe_threshold":   72,
            "moderate_threshold": 68,
            "severe_penalty":     15.0,
            "moderate_penalty":    8.0,
        },
        "quality_score_weights": {
            "iv_rank": 0.40,
            "delta":   0.35,
            "dte":     0.25,
        },
        "early_exit": {
            "enabled":                True,
            "min_hold_days":          1,
            "tech_decay_pct":         35.0,
            "direction_floor":        30.0,
            "momentum_reversal":      True,
            "rsi_extreme_exit":       True,
            "rsi_call_ceiling":       78,
            "rsi_put_floor":          22,
            "trailing_profit_pct":    40.0,
            "trailing_giveback_pct":  50.0,
            "min_profit_to_exit_pct": 5.0,
        },
    },
    "index": {
        "name": "OTM Index Momentum Strategy",
        "philosophy": (
            "Trade broad-market ETFs with longer duration, tighter delta targeting, "
            "and a lower VIX defense threshold — indexes have lower realized vol and "
            "are more directly correlated with the VIX regime."
        ),
        "confidence_weights": {
            "iv_percentile": 0.40,
            "delta":         0.30,
            "dte":           0.20,
            "technical":     0.10,
        },
        "targets": {
            "delta_optimal":     0.30,
            "delta_falloff":     0.10,   # tighter window — less OTM tolerance
            "dte_optimal":       21,     # longer duration, less gamma risk
            "dte_falloff":       14,     # ±14 days
            "iv_percentile_max": 40,     # indexes run lower IV than single stocks
        },
        "filters": {
            "vix_defense_threshold":        20.0,   # more directly VIX-correlated
            "atr_expansion_stop_mult":       1.5,
            "defense_position_mult":         0.5,
            "liquidity_spread_max_pct":      1.5,
            "illiquid_extra_margin_pct":    10.0,
            "min_option_mid_price":          0.30,
            "min_option_volume":            100,
            "min_option_open_interest":     500,
            "max_option_quote_age_hours":   48.0,
            "min_calibrated_expectancy_pct": 10.0,
            "entry_slippage_pct":            5.0,
            "exit_slippage_pct":             5.0,
            "iv_crush_z_threshold":          2.0,
            "iv_crush_confidence_penalty":  20.0,
            "min_ev_return_pct":            10.0,
        },
        "risk": {
            "stop_loss_pct":       45.0,   # tighter — indexes move less
            "profit_target_pct":  100.0,
            "max_position_pct":     2.5,
            "min_position_pct":     0.5,
            "account_size":        None,
            "max_drawdown_pct":    15.0,
            "dte_0_max_pct":        0.5,
            "time_exit_pct":       50.0,
        },
        "entry": {
            "entry_momentum_pct":  0.30,   # indexes need less momentum to signal
            "min_direction_score": 55.0,
            "min_tech_score":      65.0,
        },
        "direction_score_weights": {
            "tech":     0.55,
            "regime":   0.30,
            "momentum": 0.15,
        },
        "rsi_overextension": {
            "severe_threshold":   72,
            "moderate_threshold": 68,
            "severe_penalty":     15.0,
            "moderate_penalty":    8.0,
        },
        "quality_score_weights": {
            "iv_rank": 0.40,
            "delta":   0.35,
            "dte":     0.25,
        },
        "early_exit": {
            "enabled":                True,
            "min_hold_days":          1,
            "tech_decay_pct":         35.0,
            "direction_floor":        30.0,
            "momentum_reversal":      True,
            "rsi_extreme_exit":       True,
            "rsi_call_ceiling":       78,
            "rsi_put_floor":          22,
            "trailing_profit_pct":    40.0,
            "trailing_giveback_pct":  50.0,
            "min_profit_to_exit_pct": 5.0,
        },
    },
}

# Backwards-compat alias — all existing code referencing STRATEGY_PROFILE gets equity profile
STRATEGY_PROFILE = STRATEGY_PROFILES["equity"]

# ── Persist / restore both profiles across restarts ───────────────────────────
_DIR_OC      = os.path.dirname(os.path.abspath(__file__))
PROFILE_FILES = {
    "equity": os.path.join(_DIR_OC, "strategy_profile.json"),          # keeps backwards compat
    "index":  os.path.join(_DIR_OC, "strategy_profile_index.json"),
}
CHANGELOG_FILES = {
    "equity": os.path.join(_DIR_OC, "brain_changelog.json"),
    "index":  os.path.join(_DIR_OC, "brain_changelog_index.json"),
}
# Backwards-compat single-profile aliases
PROFILE_FILE   = PROFILE_FILES["equity"]
CHANGELOG_FILE = CHANGELOG_FILES["equity"]


def _log_brain_update(source: str, note: str, profile: str = "equity") -> None:
    """Append one timestamped entry to the profile's changelog file."""
    from datetime import timezone
    entry = {
        "ts":      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source":  source,
        "note":    note,
        "profile": profile,
    }
    cfile = CHANGELOG_FILES.get(profile, CHANGELOG_FILES["equity"])
    try:
        log = []
        if os.path.exists(cfile):
            with open(cfile) as f:
                log = json.load(f)
        log.append(entry)
        with open(cfile, "w") as f:
            json.dump(log, f, indent=2)
    except Exception:
        pass


def _save_profile(note: str = "", profile: str = "equity") -> None:
    """Write one strategy profile to disk. Call after every Apply."""
    sp = STRATEGY_PROFILES[profile]
    with open(PROFILE_FILES[profile], "w") as f:
        json.dump(
            {k: v for k, v in sp.items() if k not in ("name", "philosophy")},
            f, indent=2,
        )
    _log_brain_update(source="apply", note=note or f"{profile} strategy profile updated", profile=profile)


def _load_profile() -> None:
    """Merge saved profiles into STRATEGY_PROFILES in-place (runs at import time)."""
    for profile, pfile in PROFILE_FILES.items():
        if not os.path.exists(pfile):
            continue
        try:
            with open(pfile) as f:
                saved = json.load(f)
            sp = STRATEGY_PROFILES[profile]
            for section in ("confidence_weights", "targets", "filters", "risk", "entry",
                            "direction_score_weights", "rsi_overextension", "quality_score_weights",
                            "early_exit"):
                if section in saved and isinstance(saved[section], dict):
                    sp[section].update(saved[section])
        except Exception:
            pass  # corrupt file — fall back to defaults silently


_load_profile()  # restore on every import / app startup

# Live alias so legacy code that reads risk_settings["x"] auto-reflects equity changes
risk_settings = STRATEGY_PROFILE["risk"]


# ─── Black-Scholes Greeks ──────────────────────────────────────────────────────

def _norm_pdf(x: float) -> float:
    return math.exp(-x * x / 2.0) / math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _bs_greeks(S, K, T, r, sigma, option_type) -> dict:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {}
    try:
        sqrtT = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrtT)
        d2 = d1 - sigma * sqrtT
        nd1, nd2 = _norm_cdf(d1), _norm_cdf(d2)
        pdf_d1 = _norm_pdf(d1)
        disc = math.exp(-r * T)

        if option_type == "call":
            price = S * nd1 - K * disc * nd2
            delta = nd1
        else:
            price = K * disc * _norm_cdf(-d2) - S * _norm_cdf(-d1)
            delta = nd1 - 1.0

        gamma = pdf_d1 / (S * sigma * sqrtT)
        theta_call = (-S * pdf_d1 * sigma / (2.0 * sqrtT) - r * K * disc * nd2) / 365.0
        theta_put  = (-S * pdf_d1 * sigma / (2.0 * sqrtT) + r * K * disc * _norm_cdf(-d2)) / 365.0
        theta = theta_call if option_type == "call" else theta_put
        vega = S * sqrtT * pdf_d1 / 100.0

        return {
            "bs_price": round(price, 4),
            "delta":    round(delta, 4),
            "gamma":    round(gamma, 6),
            "theta":    round(theta, 4),   # $ per calendar day
            "vega":     round(vega, 4),    # $ per 1% IV move
        }
    except (ValueError, ZeroDivisionError, OverflowError):
        return {}


def _enrich_row(row, S, option_type, exp_str, today) -> dict:
    exp_dt = datetime.strptime(exp_str, "%Y-%m-%d")
    dte = max((exp_dt - today).days, 0)
    T = dte / 365.0
    iv   = row.get("impliedVolatility") or 0.0
    K    = row.get("strike") or 0.0
    vol  = int(row.get("volume") or 0)
    oi   = int(row.get("openInterest") or 0)
    bid  = row.get("bid") or 0.0
    ask  = row.get("ask") or 0.0
    last = row.get("lastPrice") or 0.0
    mid  = round((bid + ask) / 2, 2) if bid and ask else last

    greeks = _bs_greeks(S, K, T, RISK_FREE_RATE, iv, option_type) if iv and T > 0 else {}
    break_even = round(K + mid, 2) if option_type == "call" and mid else (round(K - mid, 2) if mid else None)

    return {
        "type": option_type,
        "strike": K,
        "expiration": exp_str,
        "dte": dte,
        "last": last,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "volume": vol,
        "open_interest": oi,
        "vol_oi_ratio": round(vol / oi, 2) if oi else None,
        "iv_pct": round(iv * 100, 1),
        "in_the_money": bool(row.get("inTheMoney")),
        "break_even": break_even,
        "underlying_price": S,
        **greeks,
    }


def _get_price(ticker_obj=None, symbol: str | None = None) -> float:
    symbol_name = (symbol or getattr(ticker_obj, "ticker", None) or getattr(ticker_obj, "symbol", None) or "")
    if symbol_name:
        try:
            hist = _cached_history(str(symbol_name).upper(), period="1d", interval="5m")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception:
            pass
        try:
            fast_info = _cached_fast_info(str(symbol_name).upper())
            price = _fast_info_last_price(fast_info)
            if price:
                return price
        except Exception:
            pass
    if ticker_obj is not None:
        hist = ticker_obj.history(period="1d", interval="5m")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        info = getattr(ticker_obj, "info", {}) or {}
        return float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
    return 0.0


# ─── Tool 1: Stock snapshot ────────────────────────────────────────────────────

@_market_data_scoped
def get_stock_snapshot(symbol: str) -> str:
    try:
        symbol_up = symbol.upper()
        hist = _cached_history(symbol_up, period="5d", interval="5m")
        info = _cached_ticker_info(symbol_up) or {}

        if not hist.empty:
            last      = float(hist["Close"].iloc[-1])
            day_open  = float(hist["Open"].resample("D").first().iloc[-1])
            day_high  = float(hist["High"].resample("D").max().iloc[-1])
            day_low   = float(hist["Low"].resample("D").min().iloc[-1])
            day_vol   = int(hist["Volume"].resample("D").sum().iloc[-1])
            daily_closes = hist["Close"].resample("D").last().dropna()
        else:
            last     = info.get("currentPrice") or info.get("regularMarketPrice") or _fast_info_last_price(_cached_fast_info(symbol_up))
            day_open = info.get("regularMarketOpen")
            day_high = info.get("dayHigh")
            day_low  = info.get("dayLow")
            day_vol  = info.get("regularMarketVolume")
            daily_closes = pd.Series(dtype=float)

        prev_close = (
            info.get("previousClose")
            or info.get("regularMarketPreviousClose")
            or (float(daily_closes.iloc[-2]) if len(daily_closes) >= 2 else None)
        )
        change_pct = round((last / prev_close - 1) * 100, 2) if last and prev_close else None

        return json.dumps({
            "symbol": symbol_up,
            "last_price": round(last, 2),
            "open": round(day_open, 2) if day_open else None,
            "high": round(day_high, 2) if day_high else None,
            "low":  round(day_low,  2) if day_low  else None,
            "volume": day_vol,
            "prev_close": round(prev_close, 2) if prev_close else None,
            "change_pct": change_pct,
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector"),
            "source": "Yahoo Finance (~15-min delayed)",
        })
    except Exception as e:
        return json.dumps({"error": str(e), "symbol": symbol.upper()})


# ─── Tool 2: Options chain ─────────────────────────────────────────────────────

@_market_data_scoped
def get_options_chain(symbol: str, option_type: str = None,
                      max_dte: int = DTE_MAX, expiration_date: str = None) -> str:
    try:
        today = datetime.now()
        symbol_up = symbol.upper()
        all_exps = _cached_options(symbol_up)

        if expiration_date:
            target_exps = [expiration_date] if expiration_date in all_exps else []
        else:
            target_exps = [e for e in all_exps
                           if 0 <= (datetime.strptime(e, "%Y-%m-%d") - today).days <= max_dte]

        if not target_exps:
            return json.dumps({"error": f"No expirations within {max_dte} DTE",
                               "available": list(all_exps[:10])})

        S = _get_price(symbol=symbol_up)
        options = []
        for exp in target_exps:
            chain = _cached_option_chain(symbol_up, exp)
            frames = []
            if option_type != "put":  frames.append(("call", chain.calls))
            if option_type != "call": frames.append(("put",  chain.puts))
            for otype, df in frames:
                for _, row in df.iterrows():
                    options.append(_enrich_row(row.to_dict(), S, otype, exp, today))

        options.sort(key=lambda x: x.get("volume") or 0, reverse=True)
        return json.dumps({
            "symbol": symbol_up,
            "underlying_price": round(S, 2),
            "expirations_fetched": target_exps,
            "contracts_found": len(options),
            "top_40_by_volume": options[:40],
            "greeks_method": "Black-Scholes",
        }, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Tool 3: Multi-ticker screener ────────────────────────────────────────────

@_market_data_scoped
def screen_options(symbols: list, option_type: str = "both",
                   max_dte: int = 21, min_volume: int = 100) -> str:
    if isinstance(symbols, str):
        symbols = [symbols]
    today = datetime.now()
    all_opts = []

    for sym in symbols[:6]:
        try:
            sym_up = sym.upper()
            target_exps = [e for e in _cached_options(sym_up)
                           if 0 <= (datetime.strptime(e, "%Y-%m-%d") - today).days <= max_dte]
            if not target_exps:
                continue
            S = _get_price(symbol=sym_up)
            for exp in target_exps:
                chain = _cached_option_chain(sym_up, exp)
                frames = []
                if option_type != "put":  frames.append(("call", chain.calls))
                if option_type != "call": frames.append(("put",  chain.puts))
                for otype, df in frames:
                    for _, row in df.iterrows():
                        if (row.get("volume") or 0) < min_volume:
                            continue
                        enriched = _enrich_row(row.to_dict(), S, otype, exp, today)
                        enriched["symbol"] = sym_up
                        all_opts.append(enriched)
        except Exception:
            continue

    all_opts.sort(key=lambda x: x.get("volume") or 0, reverse=True)
    return json.dumps({
        "tickers_screened": [s.upper() for s in symbols],
        "filters": {"option_type": option_type, "max_dte": max_dte, "min_volume": min_volume},
        "total_qualifying": len(all_opts),
        "top_35_by_volume": all_opts[:35],
        "greeks_method": "Black-Scholes",
    }, indent=2, default=str)


# ─── Tool 4: High-leverage / 2x screener ─────────────────────────────────────

@_market_data_scoped
def find_high_leverage_options(
    symbols: list = None,
    option_type: str = "both",
    max_dte: int = 14,
    min_volume: int = 50,
    max_move_needed_pct: float = 12.0,
) -> str:
    """
    Screens for options with the highest probability of a 100%+ gain.

    For each contract, calculates:
    - move_needed_pct: % the underlying must move to approximately double the option price
      Formula: (option_mid / delta) / underlying_price × 100
    - leverage_ratio: how many dollars the option gains per 1% move in underlying
      Formula: delta × underlying_price / 100 × 100  (per contract)
    - gamma_efficiency: gamma per dollar of premium (higher = more explosive)

    Sorted by move_needed_pct ascending — top results need the smallest move to 2x.
    """
    if symbols is None:
        symbols = HIGH_BETA_WATCHLIST
    if isinstance(symbols, str):
        symbols = [symbols]

    today = datetime.now()
    candidates = []

    for sym in symbols[:8]:
        try:
            sym_up = sym.upper()
            target_exps = [e for e in _cached_options(sym_up)
                           if 0 <= (datetime.strptime(e, "%Y-%m-%d") - today).days <= max_dte]
            if not target_exps:
                continue

            S = _get_price(symbol=sym_up)
            if not S:
                continue

            for exp in target_exps:
                chain = _cached_option_chain(sym_up, exp)
                dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
                T = max(dte, 1) / 365.0

                frames = []
                if option_type != "put":  frames.append(("call", chain.calls))
                if option_type != "call": frames.append(("put",  chain.puts))

                for otype, df in frames:
                    for _, row in df.iterrows():
                        vol = int(row.get("volume") or 0)
                        if vol < min_volume:
                            continue

                        iv  = row.get("impliedVolatility") or 0.0
                        K   = row.get("strike") or 0.0
                        bid = row.get("bid") or 0.0
                        ask = row.get("ask") or 0.0
                        mid = round((bid + ask) / 2, 2) if bid and ask else (row.get("lastPrice") or 0.0)

                        if mid < 0.05 or not iv:
                            continue

                        greeks = _bs_greeks(S, K, T, RISK_FREE_RATE, iv, otype)
                        if not greeks:
                            continue

                        delta = abs(greeks.get("delta") or 0)
                        gamma = greeks.get("gamma") or 0

                        if delta < 0.05:  # too far OTM — delta unreliable
                            continue

                        # % move in underlying needed to ~double option price
                        move_needed_pct = round((mid / delta) / S * 100, 1)

                        if move_needed_pct > max_move_needed_pct:
                            continue

                        # $ gain per 1% move in underlying (per contract = ×100)
                        leverage_ratio = round(delta * S * 0.01 * 100, 2)

                        # Gamma per dollar of premium — higher = more explosive upside
                        gamma_efficiency = round(gamma / mid, 4) if mid else 0

                        oi = int(row.get("openInterest") or 0)
                        break_even = round(K + mid, 2) if otype == "call" else round(K - mid, 2)

                        candidates.append({
                            "symbol": sym_up,
                            "type": otype,
                            "strike": K,
                            "expiration": exp,
                            "dte": dte,
                            "mid": mid,
                            "cost_per_contract": round(mid * 100, 2),
                            "volume": vol,
                            "open_interest": oi,
                            "iv_pct": round(iv * 100, 1),
                            "delta": round(greeks.get("delta") or 0, 3),
                            "gamma": round(gamma, 5),
                            "theta": greeks.get("theta"),
                            "break_even": break_even,
                            "underlying_price": round(S, 2),
                            "move_needed_pct": move_needed_pct,
                            "leverage_per_contract": leverage_ratio,
                            "gamma_efficiency": gamma_efficiency,
                            "in_the_money": bool(row.get("inTheMoney")),
                        })
        except Exception:
            continue

    # Sort by smallest move needed (easiest path to 100% gain)
    candidates.sort(key=lambda x: x["move_needed_pct"])

    return json.dumps({
        "tickers_screened": [s.upper() for s in symbols[:8]],
        "criteria": {
            "max_dte": max_dte,
            "min_volume": min_volume,
            "max_move_needed_pct": max_move_needed_pct,
            "goal": "100% gain (option doubles in value)",
        },
        "candidates_found": len(candidates),
        "top_20_easiest_to_double": candidates[:20],
        "note": (
            "move_needed_pct = approximate % underlying move for option to 2x. "
            "Lower = easier. Based on current delta — actual move needed will differ "
            "as delta changes (gamma effect). Not a guarantee of profit."
        ),
    }, indent=2, default=str)


# ─── Tool 5: Expirations ───────────────────────────────────────────────────────

@_market_data_scoped
def get_expirations(symbol: str) -> str:
    try:
        symbol_up = symbol.upper()
        today = datetime.now()
        results = []
        all_exps = _cached_options(symbol_up)
        for exp in all_exps:
            try:
                dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
                if 0 <= dte <= 21:
                    results.append({"date": exp, "dte": dte})
            except ValueError:
                continue
        return json.dumps({"symbol": symbol_up, "expirations_within_21_days": results,
                           "all_available": list(all_exps)})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Tool 5: IV & Volatility Analysis ─────────────────────────────────────────

@_market_data_scoped
def get_iv_analysis(symbol: str) -> str:
    """
    Calculates:
    - HV10, HV30, HV60 (realized historical volatility)
    - HV Rank over 1 year (proxy for IV rank — how elevated is vol vs history)
    - Current ATM implied volatility from nearest 14-45 DTE expiration
    - IV vs HV spread (positive = options expensive, negative = options cheap)
    """
    try:
        today = datetime.now()
        symbol_up = symbol.upper()

        # ── Historical volatility ──────────────────────────────────────────────
        hist = _cached_history(symbol_up, period="1y")
        if hist.empty or len(hist) < 30:
            return json.dumps({"error": "Not enough price history for vol calculation"})

        closes = hist["Close"].dropna()
        log_ret = np.log(closes / closes.shift(1)).dropna()

        def hv(window):
            return float(log_ret.rolling(window).std().iloc[-1] * np.sqrt(252) * 100)

        hv10 = round(hv(10), 1)
        hv30 = round(hv(30), 1)
        hv60 = round(hv(60), 1)

        # HV rank: where is current 30-day HV relative to its 1-year range?
        rolling_hv30 = log_ret.rolling(30).std() * np.sqrt(252) * 100
        hv30_max = float(rolling_hv30.max())
        hv30_min = float(rolling_hv30.min())
        hv_rank = round((hv30 - hv30_min) / (hv30_max - hv30_min) * 100, 1) if hv30_max != hv30_min else 50.0

        if   hv_rank >= 80: hv_regime = "VERY HIGH — vol near 1-year peak, premium selling favored"
        elif hv_rank >= 60: hv_regime = "ELEVATED — above-average vol, be selective buying"
        elif hv_rank >= 40: hv_regime = "MODERATE — neutral vol environment"
        elif hv_rank >= 20: hv_regime = "LOW — below-average vol, buying cheaper than usual"
        else:               hv_regime = "VERY LOW — vol near 1-year trough, options are cheap"

        # ── Current ATM implied volatility ────────────────────────────────────
        S = _get_price(symbol=symbol_up)
        atm_iv = None
        atm_exp = None
        for exp in _cached_options(symbol_up):
            dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
            if 14 <= dte <= 45:
                chain = _cached_option_chain(symbol_up, exp)
                calls = chain.calls
                if calls.empty:
                    continue
                idx = (calls["strike"] - S).abs().idxmin()
                iv_val = calls.loc[idx, "impliedVolatility"]
                if iv_val and iv_val > 0:
                    atm_iv = round(float(iv_val) * 100, 1)
                    atm_exp = exp
                break

        iv_hv_spread = round(atm_iv - hv30, 1) if atm_iv else None
        if iv_hv_spread is not None:
            if   iv_hv_spread >  15: iv_assessment = "OPTIONS EXPENSIVE — IV >> HV, elevated risk premium, consider selling"
            elif iv_hv_spread >   5: iv_assessment = "SLIGHTLY EXPENSIVE — IV moderately above HV"
            elif iv_hv_spread > -5:  iv_assessment = "FAIRLY PRICED — IV ≈ HV"
            else:                    iv_assessment = "OPTIONS CHEAP — IV below realized vol, favorable for buyers"
        else:
            iv_assessment = "Could not determine (no ATM IV available)"

        return json.dumps({
            "symbol": symbol_up,
            "underlying_price": round(S, 2),
            "realized_volatility": {
                "hv10_pct": hv10,
                "hv30_pct": hv30,
                "hv60_pct": hv60,
            },
            "hv_rank": {
                "rank_pct": hv_rank,
                "1y_low_pct": round(hv30_min, 1),
                "1y_high_pct": round(hv30_max, 1),
                "regime": hv_regime,
            },
            "implied_volatility": {
                "atm_iv_pct": atm_iv,
                "expiration_used": atm_exp,
                "iv_vs_hv30_spread": iv_hv_spread,
                "assessment": iv_assessment,
            },
            "note": "HV Rank uses realized vol as proxy (true IV rank requires paid historical IV data)",
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Tool 6: Earnings calendar ────────────────────────────────────────────────

@_market_data_scoped
def get_earnings_info(symbol: str) -> str:
    """
    Returns next earnings date, days until earnings, and a warning
    if earnings fall within the next 21 days (major IV event risk).
    """
    try:
        symbol_up = symbol.upper()
        t = None
        today = datetime.now()
        next_date = None

        # Try earnings_dates DataFrame first (most reliable)
        try:
            ed = _cached_earnings_dates(symbol_up)
            if ed is not None and not ed.empty:
                future = ed[ed.index.tz_localize(None) >= today] if ed.index.tzinfo else ed[ed.index >= today]
                if not future.empty:
                    next_date = future.index[-1]  # yfinance lists newest first, take last for soonest future
                    # Actually earnings_dates may be sorted descending, get the earliest future date
                    future_sorted = future.sort_index()
                    next_date = future_sorted.index[0]
        except Exception:
            pass

        # Fallback: try calendar
        if next_date is None:
            try:
                t = t or yf.Ticker(symbol_up)
                cal = t.calendar
                if isinstance(cal, dict):
                    dates = cal.get("Earnings Date", [])
                    if dates:
                        next_date = dates[0] if hasattr(dates[0], "date") else None
            except Exception:
                pass

        if next_date is None:
            return json.dumps({
                "symbol": symbol_up,
                "next_earnings": "Not found",
                "warning": "Could not determine earnings date — check manually before trading",
            })

        next_date_dt = next_date.to_pydatetime() if hasattr(next_date, "to_pydatetime") else next_date
        next_date_dt = next_date_dt.replace(tzinfo=None)
        days_until = (next_date_dt - today).days

        warning = None
        if days_until <= 0:
            warning = "EARNINGS IMMINENT or PASSED — check if post-earnings IV crush applies"
        elif days_until <= 7:
            warning = f"⚠️  EARNINGS IN {days_until} DAYS — IV will spike into earnings then CRUSH after. High risk for option buyers."
        elif days_until <= 21:
            warning = f"⚠️  EARNINGS IN {days_until} DAYS — falls within typical 5–35 DTE window. Factor IV crush into your exit plan."

        return json.dumps({
            "symbol": symbol_up,
            "next_earnings_date": next_date_dt.strftime("%Y-%m-%d"),
            "days_until_earnings": days_until,
            "warning": warning,
            "advice": (
                "If buying options: exit BEFORE earnings to avoid IV crush. "
                "If selling options: premium is richest just before earnings — sell then let IV crush work for you."
            ) if warning else "Earnings not within 21-day window — standard analysis applies.",
        })
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Tool 7: Market context (VIX + SPY/QQQ trend) ────────────────────────────

@_market_data_scoped
def get_market_context() -> str:
    """
    Fetches:
    - VIX level and 5-day change (fear gauge)
    - SPY and QQQ 1-month price trend
    - Market regime interpretation
    - Overall options environment (cheap vs expensive)
    """
    try:
        today = datetime.now()

        # VIX
        vix_hist = _cached_history("^VIX", period="10d")
        vix_now  = round(float(vix_hist["Close"].iloc[-1]), 2)
        vix_5d   = round(float(vix_hist["Close"].iloc[-5]), 2) if len(vix_hist) >= 5 else vix_now
        vix_chg  = round(vix_now - vix_5d, 2)

        if   vix_now < 13: vix_regime = "VERY LOW — market extremely complacent, options are cheap"
        elif vix_now < 17: vix_regime = "LOW — calm market, options cheaply priced"
        elif vix_now < 22: vix_regime = "NORMAL — typical volatility environment"
        elif vix_now < 28: vix_regime = "ELEVATED — fear rising, options getting expensive"
        elif vix_now < 35: vix_regime = "HIGH FEAR — options expensive, premium selling has edge"
        else:              vix_regime = "EXTREME FEAR / CRISIS — very expensive options, huge moves expected"

        vix_trend = "RISING (fear increasing)" if vix_chg > 1 else "FALLING (fear decreasing)" if vix_chg < -1 else "STABLE"

        # SPY trend
        spy_hist = _cached_history("SPY", period="1mo")
        spy_now  = round(float(spy_hist["Close"].iloc[-1]), 2)
        spy_1w   = round(float(spy_hist["Close"].iloc[-5]), 2)
        spy_1mo  = round(float(spy_hist["Close"].iloc[0]), 2)
        spy_1w_chg  = round((spy_now / spy_1w  - 1) * 100, 2)
        spy_1mo_chg = round((spy_now / spy_1mo - 1) * 100, 2)

        # QQQ trend
        qqq_hist = _cached_history("QQQ", period="1mo")
        qqq_now  = round(float(qqq_hist["Close"].iloc[-1]), 2)
        qqq_1mo  = round(float(qqq_hist["Close"].iloc[0]), 2)
        qqq_1mo_chg = round((qqq_now / qqq_1mo - 1) * 100, 2)

        if   spy_1mo_chg >  3: market_trend = "BULLISH — strong uptrend over past month"
        elif spy_1mo_chg >  0: market_trend = "MILDLY BULLISH — slight upward drift"
        elif spy_1mo_chg > -3: market_trend = "NEUTRAL/CHOPPY — sideways action"
        elif spy_1mo_chg > -7: market_trend = "BEARISH — moderate downtrend"
        else:                  market_trend = "STRONGLY BEARISH — significant selloff in progress"

        options_env = (
            "BUYER'S MARKET — low VIX, cheap premiums, good time to buy calls/puts"
            if vix_now < 18 else
            "SELLER'S MARKET — elevated VIX, rich premiums, selling premium has edge"
            if vix_now > 25 else
            "NEUTRAL — balanced environment, evaluate each name individually"
        )

        return json.dumps({
            "timestamp": today.strftime("%Y-%m-%d %H:%M"),
            "vix": {
                "current": vix_now,
                "5d_ago": vix_5d,
                "5d_change": vix_chg,
                "trend": vix_trend,
                "regime": vix_regime,
            },
            "spy": {
                "price": spy_now,
                "1w_change_pct": spy_1w_chg,
                "1mo_change_pct": spy_1mo_chg,
            },
            "qqq": {
                "price": qqq_now,
                "1mo_change_pct": qqq_1mo_chg,
            },
            "market_trend": market_trend,
            "options_environment": options_env,
            "recommendation": (
                "Favor CALLS on individual names with bullish setups" if spy_1mo_chg > 2 and vix_now < 22
                else "Favor PUTS or hedges — market in downtrend" if spy_1mo_chg < -3
                else "Be selective — mixed signals, focus on individual stock catalysts"
            ),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Tool 8: Put/Call ratio ────────────────────────────────────────────────────

@_market_data_scoped
def get_put_call_ratio(symbol: str, max_dte: int = 21) -> str:
    """
    Calculates the put/call volume ratio across all near-term expirations.

    P/C > 1.2  → bearish sentiment (heavy put buying)
    P/C 0.8–1.2 → neutral
    P/C < 0.8  → bullish sentiment (heavy call buying)

    Also shows P/C by expiration and highlights the most active strikes.
    """
    try:
        today = datetime.now()
        symbol_up = symbol.upper()
        S = _get_price(symbol=symbol_up)

        total_call_vol = 0
        total_put_vol  = 0
        total_call_oi  = 0
        total_put_oi   = 0
        by_expiration  = []
        top_strikes    = []

        for exp in _cached_options(symbol_up):
            dte = (datetime.strptime(exp, "%Y-%m-%d") - today).days
            if not (0 <= dte <= max_dte):
                continue

            chain = _cached_option_chain(symbol_up, exp)
            c_vol = int(chain.calls["volume"].sum() or 0)
            p_vol = int(chain.puts["volume"].sum()  or 0)
            c_oi  = int(chain.calls["openInterest"].sum() or 0)
            p_oi  = int(chain.puts["openInterest"].sum()  or 0)

            total_call_vol += c_vol
            total_put_vol  += p_vol
            total_call_oi  += c_oi
            total_put_oi   += p_oi

            pc = round(p_vol / c_vol, 2) if c_vol else None
            by_expiration.append({"expiration": exp, "dte": dte,
                                  "call_volume": c_vol, "put_volume": p_vol,
                                  "put_call_ratio": pc})

            # Top call and put strike by volume this expiration
            if not chain.calls.empty:
                top_c = chain.calls.nlargest(1, "volume").iloc[0]
                top_strikes.append({"exp": exp, "type": "call",
                                    "strike": top_c["strike"], "volume": int(top_c["volume"] or 0),
                                    "distance_pct": round((top_c["strike"] - S) / S * 100, 1)})
            if not chain.puts.empty:
                top_p = chain.puts.nlargest(1, "volume").iloc[0]
                top_strikes.append({"exp": exp, "type": "put",
                                    "strike": top_p["strike"], "volume": int(top_p["volume"] or 0),
                                    "distance_pct": round((top_p["strike"] - S) / S * 100, 1)})

        overall_pc = round(total_put_vol / total_call_vol, 2) if total_call_vol else None

        if overall_pc is None:
            sentiment = "No data"
        elif overall_pc > 1.5: sentiment = "VERY BEARISH — heavy put buying, market expects downside"
        elif overall_pc > 1.2: sentiment = "BEARISH — put volume significantly outpaces calls"
        elif overall_pc > 0.9: sentiment = "SLIGHTLY BEARISH / NEUTRAL"
        elif overall_pc > 0.7: sentiment = "NEUTRAL / SLIGHTLY BULLISH"
        elif overall_pc > 0.5: sentiment = "BULLISH — call volume dominates"
        else:                  sentiment = "VERY BULLISH — aggressive call buying"

        top_strikes.sort(key=lambda x: x["volume"], reverse=True)

        return json.dumps({
            "symbol": symbol_up,
            "underlying_price": round(S, 2),
            "overall": {
                "total_call_volume": total_call_vol,
                "total_put_volume":  total_put_vol,
                "put_call_ratio":    overall_pc,
                "sentiment":         sentiment,
                "call_oi": total_call_oi,
                "put_oi":  total_put_oi,
                "oi_put_call_ratio": round(total_put_oi / total_call_oi, 2) if total_call_oi else None,
            },
            "by_expiration": by_expiration,
            "most_active_strikes": top_strikes[:10],
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Tool 9: Position sizing & risk check ────────────────────────────────────

def calculate_position_size(
    option_price: float,
    account_size: float = None,
    max_risk_pct: float = None,
    dte: int = 5,
    confidence: int = 5,
) -> str:
    """
    Calculates safe position sizing for a single options trade.

    confidence (1–10): scales premium-at-risk linearly from min_position_pct
    up to max_position_pct. Use your honest assessment of edge.
    """
    acct = account_size or risk_settings["account_size"]

    if not acct:
        return json.dumps({
            "error": "Account size not set.",
            "fix": "Tell me your account size (e.g. 'my account is $10,000') and I'll size the trade for you.",
        })

    # 0DTE always uses the hard cap regardless of confidence
    if dte == 0:
        risk_pct = risk_settings["dte_0_max_pct"]
        confidence_note = "0DTE hard cap — confidence scaling disabled for binary outcomes."
    elif max_risk_pct is not None:
        risk_pct = max_risk_pct
        confidence_note = f"Manual override: {risk_pct}%"
    else:
        # Linear interpolation: confidence 1 → min, 10 → max
        lo  = risk_settings["min_position_pct"]
        hi  = risk_settings["max_position_pct"]
        c   = max(1, min(10, confidence))
        risk_pct = round(lo + (c - 1) / 9.0 * (hi - lo), 2)
        confidence_note = (
            f"Confidence {c}/10 → {risk_pct}% of account "
            f"(scale: {lo}% at 1 → {hi}% at 10)"
        )

    max_risk_dollars  = round(acct * risk_pct / 100, 2)
    cost_per_contract = round(option_price * 100, 2)
    max_contracts     = int(max_risk_dollars // max(cost_per_contract, 0.01))
    actual_risk       = round(max_contracts * cost_per_contract, 2)
    pct_of_account    = round(actual_risk / acct * 100, 2)

    if max_contracts <= 0:
        return json.dumps({
            "error": "Trade exceeds the current risk budget.",
            "account_size": acct,
            "option_price": option_price,
            "risk_budget_dollars": max_risk_dollars,
            "cost_per_contract": cost_per_contract,
            "confidence_sizing": {
                "confidence_score": confidence,
                "risk_pct_applied": risk_pct,
                "note": confidence_note,
            },
            "fix": "Lower the option premium, reduce the manual risk override, or increase account size before taking this trade.",
        }, indent=2)

    stop_loss_pct   = risk_settings["stop_loss_pct"]
    stop_loss_value = round(option_price * (1 - stop_loss_pct / 100), 2)
    stop_loss_loss  = round(actual_risk * stop_loss_pct / 100, 2)

    max_dd          = risk_settings["max_drawdown_pct"]
    trades_to_limit = int(max_dd / risk_pct) if risk_pct else 0

    warning = None
    if dte == 0:
        warning = "⚠️  0DTE is binary — full loss is common. Size is already capped."

    return json.dumps({
        "account_size":      acct,
        "option_price":      option_price,
        "cost_per_contract": cost_per_contract,
        "confidence_sizing": {
            "confidence_score":  confidence,
            "risk_pct_applied":  risk_pct,
            "note":              confidence_note,
        },
        "sizing": {
            "max_contracts":   max_contracts,
            "total_cost":      actual_risk,
            "pct_of_account":  pct_of_account,
            "max_loss_if_zero": actual_risk,
        },
        "stop_loss": {
            "exit_at_option_price": stop_loss_value,
            "loss_if_stopped":      stop_loss_loss,
            "pct_of_account_lost":  round(stop_loss_loss / acct * 100, 2),
            "rule": f"Exit if option drops {stop_loss_pct}% from entry",
        },
        "drawdown_context": {
            "this_trade_impact_pct":    pct_of_account,
            "trades_until_dd_limit":    trades_to_limit,
            "warning":                  warning,
        },
    }, indent=2)


# ─── Tool 10: Update risk settings ────────────────────────────────────────────

def manage_risk_settings(
    # ── Risk / exit params ────────────────────────────────────────────────────
    account_size: float = None,
    max_drawdown_pct: float = None,
    stop_loss_pct: float = None,
    profit_target_pct: float = None,
    min_position_pct: float = None,
    max_position_pct: float = None,
    dte_0_max_pct: float = None,
    # ── Strategy filter params ────────────────────────────────────────────────
    vix_defense_threshold: float = None,
    defense_position_mult: float = None,
    atr_expansion_stop_mult: float = None,
    min_ev_return_pct: float = None,
    liquidity_spread_max_pct: float = None,
    illiquid_extra_margin_pct: float = None,
    min_option_mid_price: float = None,
    min_option_volume: int = None,
    min_option_open_interest: int = None,
    max_option_quote_age_hours: float = None,
    min_calibrated_expectancy_pct: float = None,
    entry_slippage_pct: float = None,
    exit_slippage_pct: float = None,
    iv_crush_z_threshold: float = None,
    iv_crush_confidence_penalty: float = None,
    # ── Confidence target params ──────────────────────────────────────────────
    delta_target: float = None,
    dte_target: int = None,
) -> str:
    """
    View or update any part of the unified strategy profile (risk rules, entry filters,
    confidence targets). Call with NO arguments to display the full current profile.
    Call with specific arguments to update those values.
    """
    sp  = STRATEGY_PROFILE
    rsk = sp["risk"]
    flt = sp["filters"]
    tgt = sp["targets"]

    # ── Track changes: capture before values, apply, record after ─────────────
    _changes: dict[str, dict] = {}

    def _apply(store: dict, key: str, new_val):
        if new_val is not None:
            old = store.get(key)
            store[key] = new_val
            if old != new_val:
                _changes[key] = {"before": old, "after": new_val}

    _apply(rsk, "account_size",               account_size)
    _apply(rsk, "max_drawdown_pct",           max_drawdown_pct)
    _apply(rsk, "stop_loss_pct",              stop_loss_pct)
    _apply(rsk, "profit_target_pct",          profit_target_pct)
    _apply(rsk, "min_position_pct",           min_position_pct)
    _apply(rsk, "max_position_pct",           max_position_pct)
    _apply(rsk, "dte_0_max_pct",              dte_0_max_pct)
    _apply(flt, "vix_defense_threshold",      vix_defense_threshold)
    _apply(flt, "defense_position_mult",      defense_position_mult)
    _apply(flt, "atr_expansion_stop_mult",    atr_expansion_stop_mult)
    _apply(flt, "min_ev_return_pct",          min_ev_return_pct)
    _apply(flt, "liquidity_spread_max_pct",   liquidity_spread_max_pct)
    _apply(flt, "illiquid_extra_margin_pct",  illiquid_extra_margin_pct)
    _apply(flt, "min_option_mid_price",       min_option_mid_price)
    _apply(flt, "min_option_volume",          min_option_volume)
    _apply(flt, "min_option_open_interest",   min_option_open_interest)
    _apply(flt, "max_option_quote_age_hours", max_option_quote_age_hours)
    _apply(flt, "min_calibrated_expectancy_pct", min_calibrated_expectancy_pct)
    _apply(flt, "entry_slippage_pct",         entry_slippage_pct)
    _apply(flt, "exit_slippage_pct",          exit_slippage_pct)
    _apply(flt, "iv_crush_z_threshold",       iv_crush_z_threshold)
    _apply(flt, "iv_crush_confidence_penalty", iv_crush_confidence_penalty)
    if delta_target is not None:
        _apply(tgt, "delta_optimal", delta_target)
    if dte_target is not None:
        _apply(tgt, "dte_optimal", dte_target)

    # ── Build full profile snapshot ───────────────────────────────────────────
    acct = rsk.get("account_size")
    cw   = sp["confidence_weights"]

    result = {
        "strategy_name": sp["name"],
        "confidence_score": {
            "weights": {
                "iv_rank":  f"{round(cw['iv_percentile'] * 100)}%",
                "delta":    f"{round(cw['delta'] * 100)}%",
                "dte":      f"{round(cw['dte'] * 100)}%",
            },
            "targets": {
                "delta_optimal":  tgt["delta_optimal"],
                "delta_falloff":  tgt["delta_falloff"],
                "dte_optimal":    tgt["dte_optimal"],
                "dte_falloff":    tgt["dte_falloff"],
            },
        },
        "entry_filters": {
            "iv_crush_z_threshold":        flt["iv_crush_z_threshold"],
            "iv_crush_confidence_penalty": flt["iv_crush_confidence_penalty"],
            "liquidity_spread_max_pct":    flt["liquidity_spread_max_pct"],
            "illiquid_extra_margin_pct":   flt["illiquid_extra_margin_pct"],
            "min_option_mid_price":        flt["min_option_mid_price"],
            "min_option_volume":           flt["min_option_volume"],
            "min_option_open_interest":    flt["min_option_open_interest"],
            "max_option_quote_age_hours":  flt["max_option_quote_age_hours"],
            "min_calibrated_expectancy_pct": flt["min_calibrated_expectancy_pct"],
            "entry_slippage_pct":          flt["entry_slippage_pct"],
            "exit_slippage_pct":           flt["exit_slippage_pct"],
            "min_ev_return_pct":           flt["min_ev_return_pct"],
        },
        "market_regime": {
            "vix_defense_threshold":    flt["vix_defense_threshold"],
            "defense_position_mult":    flt["defense_position_mult"],
            "atr_expansion_stop_mult":  flt["atr_expansion_stop_mult"],
        },
        "risk_and_exits": {
            "account_size":       acct or "not set",
            "stop_loss_pct":      rsk["stop_loss_pct"],
            "profit_target_pct":  rsk["profit_target_pct"],
            "min_position_pct":   rsk["min_position_pct"],
            "max_position_pct":   rsk["max_position_pct"],
            "max_drawdown_pct":   rsk["max_drawdown_pct"],
            "dte_0_max_pct":      rsk["dte_0_max_pct"],
        },
    }

    if acct:
        result["dollar_limits"] = {
            "max_per_trade_$":    round(acct * rsk["max_position_pct"] / 100, 2),
            "min_per_trade_$":    round(acct * rsk["min_position_pct"] / 100, 2),
            "max_0dte_$":         round(acct * rsk["dte_0_max_pct"] / 100, 2),
            "max_drawdown_$":     round(acct * rsk["max_drawdown_pct"] / 100, 2),
        }

    if _changes:
        result["changes"] = {
            "date": datetime.now(_ET).strftime("%Y-%m-%d %H:%M ET"),
            "updated": {
                k: {"before": v["before"], "after": v["after"]}
                for k, v in _changes.items()
            },
        }

    return json.dumps(result, indent=2)


# ─── Tool 11: Paper trading journal ──────────────────────────────────────────

def _load_trades() -> list:
    if os.path.exists(PAPER_TRADES_FILE):
        try:
            with open(PAPER_TRADES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_trades(trades: list):
    with open(PAPER_TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2, default=str)


@_market_data_scoped
def log_paper_trade(
    action: str = "list",
    symbol: str = None,
    option_type: str = None,
    strike: float = None,
    expiration: str = None,
    entry_price: float = None,
    underlying_entry: float = None,
    contracts: int = 1,
    notes: str = None,
    trade_id: int = None,
    exit_price: float = None,
) -> str:
    """
    Paper trading journal — log, track, and close options trades.

    action="add"   — log a new trade
    action="list"  — show all trades + summary stats (win rate, total P&L)
    action="check" — estimate current P&L for open trades using Black-Scholes
    action="close" — mark a trade closed with a final exit price
    """
    trades = _load_trades()
    today = datetime.now()

    if action == "add":
        if not all([symbol, option_type, strike, expiration, entry_price]):
            return json.dumps({"error": "Required: symbol, option_type, strike, expiration, entry_price"})
        exp_dt = datetime.strptime(expiration, "%Y-%m-%d")
        dte = (exp_dt - today).days
        new_id = max((t["id"] for t in trades), default=0) + 1
        stop_px = round(entry_price * (1 - risk_settings["stop_loss_pct"] / 100), 2)
        trade = {
            "id": new_id,
            "symbol": symbol.upper(),
            "option_type": option_type.lower(),
            "strike": strike,
            "expiration": expiration,
            "dte_at_entry": dte,
            "entry_price": entry_price,
            "cost_per_contract": round(entry_price * 100, 2),
            "contracts": contracts,
            "total_cost": round(entry_price * 100 * contracts, 2),
            "underlying_entry": underlying_entry,
            "entry_date": today.strftime("%Y-%m-%d"),
            "stop_loss_price": stop_px,
            "target_2x_price": round(entry_price * 2, 2),
            "status": "open",
            "exit_price": None,
            "exit_date": None,
            "pnl_pct": None,
            "pnl_dollars": None,
            "notes": notes or "",
        }
        trades.append(trade)
        _save_trades(trades)
        return json.dumps({
            "message": f"Trade #{new_id} logged.",
            "trade": trade,
            "reminders": {
                "stop_loss": f"Exit if option falls to ${stop_px}",
                "target":    f"Take profit at ${trade['target_2x_price']} (100% gain)",
                "expires":   f"{expiration} ({dte} DTE)",
            },
        }, indent=2)

    elif action == "list":
        if not trades:
            return json.dumps({"message": "No paper trades logged yet.", "total": 0})
        closed = [t for t in trades if t["status"] == "closed"]
        open_t  = [t for t in trades if t["status"] == "open"]
        wins    = [t for t in closed if (t.get("pnl_pct") or 0) > 0]
        losses  = [t for t in closed if (t.get("pnl_pct") or 0) <= 0]
        return json.dumps({
            "summary": {
                "total_trades": len(trades),
                "open": len(open_t),
                "closed": len(closed),
                "win_rate": f"{round(len(wins)/len(closed)*100,1)}%" if closed else "N/A",
                "avg_win_pct":  round(sum(t["pnl_pct"] for t in wins)   / len(wins),   1) if wins   else None,
                "avg_loss_pct": round(sum(t["pnl_pct"] for t in losses) / len(losses), 1) if losses else None,
                "total_pnl_dollars": round(sum(t.get("pnl_dollars") or 0 for t in closed), 2),
            },
            "open_trades":   open_t,
            "recent_closed": closed[-10:],
        }, indent=2, default=str)

    elif action == "check":
        open_t = [t for t in trades if t["status"] == "open"]
        if trade_id:
            open_t = [t for t in open_t if t["id"] == trade_id]
        if not open_t:
            return json.dumps({"message": "No open trades to check."})
        results = []
        for t in open_t:
            try:
                symbol_up = str(t["symbol"]).upper()
                S = _get_price(symbol=symbol_up)
                exp_dt = datetime.strptime(t["expiration"], "%Y-%m-%d")
                dte = max((exp_dt - today).days, 0)
                T = dte / 365.0
                # Try to get real IV from chain, fall back to HV30
                iv = None
                try:
                    ch = _cached_option_chain(symbol_up, t["expiration"])
                    df = ch.calls if t["option_type"] == "call" else ch.puts
                    if not df.empty:
                        idx = (df["strike"] - S).abs().idxmin()
                        iv_raw = df.loc[idx, "impliedVolatility"]
                        if iv_raw and iv_raw > 0:
                            iv = float(iv_raw)
                except Exception:
                    pass
                if not iv:
                    h = _cached_history(symbol_up, period="2mo")
                    if len(h) >= 30:
                        lr = np.log(h["Close"] / h["Close"].shift(1)).dropna()
                        iv = float(lr.rolling(30).std().iloc[-1] * np.sqrt(252))
                if T <= 0:
                    cur = max(0.0, S - t["strike"]) if t["option_type"] == "call" else max(0.0, t["strike"] - S)
                elif iv:
                    g = _bs_greeks(S, t["strike"], T, RISK_FREE_RATE, iv, t["option_type"])
                    cur = g.get("bs_price") if g else None
                else:
                    cur = None
                if cur is not None:
                    pct = round((cur / t["entry_price"] - 1) * 100, 1)
                    dlr = round((cur - t["entry_price"]) * 100 * t["contracts"], 2)
                    if pct >= 100:     flag = "🚀 2x TARGET — consider taking profit"
                    elif pct >= 50:    flag = "🟢 BIG WINNER — consider partial exit"
                    elif pct > 0:      flag = "🟢 PROFIT"
                    elif pct > -risk_settings["stop_loss_pct"]: flag = "🔴 LOSS"
                    else:              flag = "⛔ STOP LOSS HIT — exit now"
                else:
                    pct, dlr, flag = None, None, "Cannot price"
                results.append({
                    "id": t["id"],
                    "trade": f"{t['symbol']} {t['option_type'].upper()} ${t['strike']} {t['expiration']}",
                    "entry_price": t["entry_price"],
                    "current_value_est": round(cur, 4) if cur else None,
                    "underlying_now": round(S, 2),
                    "dte_remaining": dte,
                    "pnl_pct": pct,
                    "pnl_dollars": dlr,
                    "status": flag,
                })
            except Exception as e:
                results.append({"id": t["id"], "error": str(e)})
        return json.dumps({"updates": results, "note": "Values estimated via Black-Scholes"}, indent=2)

    elif action == "close":
        if trade_id is None or exit_price is None:
            return json.dumps({"error": "Required: trade_id and exit_price"})
        for t in trades:
            if t["id"] == trade_id:
                if t["status"] == "closed":
                    return json.dumps({"error": f"Trade #{trade_id} already closed."})
                pct = round((exit_price / t["entry_price"] - 1) * 100, 1)
                dlr = round((exit_price - t["entry_price"]) * 100 * t["contracts"], 2)
                t.update({"status": "closed", "exit_price": exit_price,
                           "exit_date": today.strftime("%Y-%m-%d"),
                           "pnl_pct": pct, "pnl_dollars": dlr})
                _save_trades(trades)
                return json.dumps({
                    "message": f"Trade #{trade_id} closed.",
                    "outcome": "WIN 🟢" if pct > 0 else "LOSS 🔴",
                    "pnl_pct": pct, "pnl_dollars": dlr,
                }, indent=2)
        return json.dumps({"error": f"Trade #{trade_id} not found."})

    return json.dumps({"error": f"Unknown action '{action}'. Use: add, list, check, close"})


# ─── Tool 12: Daily predictions tracker ───────────────────────────────────────

def _load_predictions() -> list:
    if os.path.exists(PREDICTIONS_FILE):
        try:
            with open(PREDICTIONS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_predictions(preds: list):
    with open(PREDICTIONS_FILE, "w") as f:
        json.dump(preds, f, indent=2, default=str)

@_market_data_scoped
def log_prediction(
    action: str = "log",
    ticker: str = None,
    direction: str = None,
    target_move_pct: float = None,
    target_date: str = None,
    confidence: int = 5,
    reasoning: str = "",
    prediction_id: int = None,
    scan_date: str = None,
) -> str:
    """
    action="log"    — record a new daily prediction (fetches entry price automatically)
    action="grade"  — grade predictions: checks TP/SL hit on any day before expiry, not just at target_date.
                      Pass scan_date="YYYY-MM-DD" to grade only one run's picks.
    action="list"   — show all predictions + accuracy stats
    action="delete" — remove a prediction by id
    """
    preds = _load_predictions()
    today = datetime.now()

    # ── list ──────────────────────────────────────────────────────────────────
    if action == "list":
        if not preds:
            return json.dumps({"message": "No predictions recorded yet."})

        # Keep live scan, manual chat calls, and synthetic backfills separate.
        scan_preds     = [p for p in preds if p.get("type") == "daily_scan"]
        backfill_preds = [p for p in preds if p.get("source") == "backfill" or p.get("type") == "backfill"]
        manual_preds   = [
            p for p in preds
            if p.get("type") != "daily_scan"
            and p.get("source") != "backfill"
            and p.get("type") != "backfill"
        ]

        def _stats(subset):
            _non_action = ("manual_exit", "replaced")
            graded  = [p for p in subset if p.get("outcome") and p["outcome"] not in _non_action]
            hits    = [p for p in graded if p["outcome"] == "hit"]
            dir_ok  = [p for p in graded if p["outcome"] in ("hit", "directional")]
            pending = [p for p in subset if not p.get("outcome")]
            return {
                "total":               len(subset),
                "graded":              len(graded),
                "pending":             len(pending),
                "hit_rate_pct":        round(len(hits)   / len(graded) * 100, 1) if graded else None,
                "directional_rate_pct": round(len(dir_ok) / len(graded) * 100, 1) if graded else None,
            }

        summary = {
            # Algorithmic scan model stats — these reflect the Direction Score model accuracy
            "scan_model": _stats(scan_preds),
            # Synthetic historical labels generated by backfill_predictions()
            "backfill_predictions": _stats(backfill_preds),
            # Manually-logged predictions from chat — Claude's own direct calls
            "manual_predictions": _stats(manual_preds),
            "predictions": preds,
            "_note": (
                "scan_model = daily_scan algorithmic picks (Direction Score + Quality Score model). "
                "backfill_predictions = synthetic historical labels from backfill_predictions(). "
                "manual_predictions = predictions logged directly via chat. "
                "Do NOT conflate these sources when assessing model performance."
            ),
        }
        return json.dumps(summary, indent=2, default=str)

    # ── grade ─────────────────────────────────────────────────────────────────
    if action == "grade":
        graded_count = 0
        # Fetch SPY regime data once for all picks (reused by early exit checks)
        _spy_ret5_grade = 0.0
        try:
            _spy_grade = _cached_history("SPY", period="10d")["Close"].dropna()
            if len(_spy_grade) >= 6:
                _spy_ret5_grade = float((_spy_grade.iloc[-1] / _spy_grade.iloc[-6] - 1) * 100)
        except Exception:
            pass
        for p in preds:
            if p.get("outcome"):
                continue
            if scan_date and p.get("entry_date", "")[:10] != scan_date:
                continue
            try:
                entry_dt  = datetime.strptime(p["entry_date"][:10], "%Y-%m-%d")
                target_dt = datetime.strptime(p["target_date"],      "%Y-%m-%d")
            except Exception:
                continue
            # Skip only if the scan date is in the future
            if today.date() < entry_dt.date():
                continue
            # Extract entry fields early — needed for same-day live P&L snapshot
            _entry_raw_early = p.get("entry_open_price") or p.get("entry_price") or p.get("stock_price")
            _entry_px  = float(_entry_raw_early) if _entry_raw_early else 0.0
            _is_bull   = p.get("direction") in ("bullish", "call")
            _premium   = float(p.get("est_premium") or 0.0)

            try:
                is_same_day = entry_dt.date() == today.date()
                if is_same_day:
                    # Same-day: only update live P&L snapshot — do NOT grade.
                    # The day's high/low includes price action before entry time,
                    # so SL/TP checks would use stale extremes and false-trigger.
                    fi   = _cached_fast_info(p["ticker"])
                    _cur = _fast_info_last_price(fi)
                    p["current_stock_px"]  = round(_cur, 2)
                    p["current_stock_pct"] = round((_cur / _entry_px - 1) * 100, 2) if _entry_px else None
                    # Fetch live option mid price for P&L display
                    try:
                        _exp = p.get("expiry")
                        _K   = p.get("strike_est")
                        if _exp and _K:
                            _avail = _cached_options(p["ticker"])
                            if _avail and _exp in _avail:
                                _ch  = _cached_option_chain(p["ticker"], _exp)
                                _df  = _ch.calls if _is_bull else _ch.puts
                                _row = _df.iloc[(_df["strike"] - float(_K)).abs().argsort()[:1]]
                                if not _row.empty:
                                    _bid = float(_row["bid"].iloc[0])
                                    _ask = float(_row["ask"].iloc[0])
                                    if _bid > 0 and _ask > 0:
                                        _live_mid = round((_bid + _ask) / 2, 2)
                                        p["current_option_px"] = _live_mid
                                        if _premium > 0:
                                            p["current_pnl_pct"] = round((_live_mid / _premium - 1) * 100, 1)
                    except Exception:
                        pass
                    continue  # skip grading until next trading day
                else:
                    fetch_end   = (max(today, target_dt) + timedelta(days=3)).strftime("%Y-%m-%d")
                    fetch_start = (entry_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                    hist        = _cached_history(p["ticker"], start=fetch_start, end=fetch_end)
                if not is_same_day and hist.empty:
                    # Last-resort fallback for non-same-day picks
                    fb   = _cached_history(p["ticker"], period="5d", interval="1d")
                    hist = fb[fb.index.date > entry_dt.date()]
                if hist.empty:
                    p["grade_error"] = "No market data available yet"
                    continue
            except Exception as e:
                p["grade_error"] = str(e)
                continue

            # If pick was made outside market hours, resolve next-open price on first grade
            if p.get("entry_at_open") and p.get("entry_open_price") is None:
                try:
                    _oh = _cached_history(
                        p["ticker"],
                        start=entry_dt.strftime("%Y-%m-%d"),
                        end=(entry_dt + timedelta(days=10)).strftime("%Y-%m-%d"),
                    )
                    _after = _oh[_oh.index.date > entry_dt.date()]
                    if not _after.empty:
                        p["entry_open_price"] = round(float(_after["Open"].iloc[0]), 2)
                except Exception:
                    pass

            _entry_raw = p.get("entry_open_price") or p.get("entry_price")
            if _entry_raw is None:
                p["grade_error"] = "Missing entry price"
                continue
            entry_price   = float(_entry_raw)
            direction     = p["direction"]
            is_bullish    = direction in ("bullish", "call")
            dir_factor    = 1.0 if is_bullish else -1.0
            delta         = float(p.get("delta_est")             or 0.0)
            premium       = float(p.get("est_premium")           or 0.0)
            stop_pct      = abs(float(p.get("stop_loss_pct")     or 50.0))
            tp_pct        = abs(float(p.get("profit_target_pct") or 100.0))
            time_exit_day = p.get("time_exit_day")
            dte           = max(int(p.get("target_dte") or p.get("dte") or 7), 1)
            theta_per_day = 0.0 if is_same_day else (premium / dte if premium > 0 else 0.0)

            exit_price   = None
            exit_reason  = None
            exit_day_idx = None
            exit_opt_pct = None

            for day_idx, (ts, row) in enumerate(hist.iterrows()):
                days_held = day_idx + 1
                row_date  = ts.date()
                close_px  = float(row["Close"])

                # TP: intraday favorable price (spike could be a real exit opportunity)
                # SL: end-of-day close only (intraday lows cause false positives on options)
                if premium > 0 and delta > 0:
                    fav_px    = float(row["High"]) if is_bullish else float(row["Low"])
                    fav_move  = fav_px - entry_price
                    raw_fav   = max(0.01, premium + dir_factor * delta * fav_move
                                    - theta_per_day * days_held)
                    fav_gain  = (raw_fav / premium - 1) * 100

                    if fav_gain >= tp_pct:
                        exit_price   = close_px
                        exit_reason  = "tp_hit"
                        exit_opt_pct = tp_pct
                        exit_day_idx = day_idx
                        break

                    adv_px    = float(row["Low"]) if is_bullish else float(row["High"])
                    adv_move  = adv_px - entry_price
                    raw_adv   = max(0.01, premium + dir_factor * delta * adv_move
                                    - theta_per_day * days_held)
                    adv_gain  = (raw_adv / premium - 1) * 100

                    if adv_gain <= -stop_pct:
                        exit_price   = close_px
                        exit_reason  = "sl_hit"
                        exit_opt_pct = -stop_pct
                        exit_day_idx = day_idx
                        break

                if time_exit_day and days_held >= time_exit_day:
                    exit_price   = close_px
                    exit_reason  = "time_exit"
                    exit_day_idx = day_idx
                    break

                if row_date >= target_dt.date():
                    exit_price   = close_px
                    exit_reason  = "expired"
                    exit_day_idx = day_idx
                    break

            # No exit condition met yet — update current live P&L snapshot but stay pending
            if exit_price is None:
                # Fallback: if the targeted range returned nothing, try the last 5 trading days
                _hist_for_pnl = hist
                if _hist_for_pnl.empty:
                    try:
                        _fb = _cached_history(p["ticker"], period="5d")
                        _fb = _fb[_fb.index.date > entry_dt.date()]
                        if not _fb.empty:
                            _hist_for_pnl = _fb
                    except Exception:
                        pass
                if not _hist_for_pnl.empty:
                    latest_close = float(_hist_for_pnl["Close"].iloc[-1])
                    p["current_stock_px"]  = round(latest_close, 2)
                    p["current_stock_pct"] = round((latest_close / entry_price - 1) * 100, 2) if entry_price else None
                    # current_pnl_pct is NOT computed here — the display layer computes it
                    # from live chain prices (live_premium / est_premium) to avoid delta estimation.

                    # Attempt to get the actual live option mid price from the chain.
                    # Only use chain pricing when expiry was stored at scan time (real pick).
                    # Picks with expiry=None have theoretical est_premium — comparisons would be misleading.
                    _live_mid = None
                    try:
                        _exp = p.get("expiry")   # must be a real stored expiry, not target_date
                        _K   = p.get("strike_est")
                        if _exp and _K:
                            # Only use chain pricing when expiry was stored at scan time.
                            # Verify expiry is still in the available list; skip if already expired.
                            _avail = _cached_options(p["ticker"])  # tuple of valid expiry strings
                            if _avail and _exp in _avail:
                                _ch  = _cached_option_chain(p["ticker"], _exp)
                                _df  = _ch.calls if is_bullish else _ch.puts
                                # Snap to nearest strike (no fixed tolerance)
                                _K_f = float(_K)
                                _row = _df.iloc[(_df["strike"] - _K_f).abs().argsort()[:1]]
                                if not _row.empty:
                                    _bid = float(_row["bid"].iloc[0])
                                    _ask = float(_row["ask"].iloc[0])
                                    if _bid > 0 and _ask > 0:
                                        _live_mid = round((_bid + _ask) / 2, 2)
                                        # Recalculate P&L from the real mid price
                                        _real_pct = (_live_mid / premium - 1) * 100
                                        p["current_pnl_pct"] = round(
                                            max(-stop_pct, min(tp_pct, _real_pct)), 1
                                        )
                    except Exception:
                        pass
                    if _live_mid is not None:
                        p["current_option_px"] = _live_mid
                    else:
                        p.pop("current_option_px", None)  # don't show a made-up price

                    # ── Smart early exit check ────────────────────────────────
                    _ee_sp  = _get_profile(p.get("ticker", ""))
                    _ee_cfg = _ee_sp.get("early_exit", {})
                    _days_held_total = (today.date() - entry_dt.date()).days

                    if (_ee_cfg.get("enabled", False)
                        and p.get("type") == "daily_scan"
                        and _days_held_total >= int(_ee_cfg.get("min_hold_days", 1))
                        and premium > 0 and delta > 0):

                        # Determine current option P&L %
                        _cur_pnl = p.get("current_pnl_pct")
                        if _cur_pnl is None and _live_mid is not None and premium > 0:
                            _cur_pnl = round((_live_mid / premium - 1) * 100, 1)
                        if _cur_pnl is None:
                            # Delta-based fallback
                            _stock_move = latest_close - entry_price
                            _raw_opt = max(0.01, premium + dir_factor * delta * _stock_move
                                           - theta_per_day * _days_held_total)
                            _cur_pnl = round((_raw_opt / premium - 1) * 100, 1)

                        # Track peak P&L across grading cycles
                        _peak = float(p.get("peak_pnl_pct", 0))
                        if _cur_pnl > _peak:
                            _peak = _cur_pnl
                        p["peak_pnl_pct"] = round(_peak, 1)

                        _ee_min_profit = float(_ee_cfg.get("min_profit_to_exit_pct", 5.0))
                        if _cur_pnl >= _ee_min_profit:
                            _should_exit, _exit_detail = _check_early_exit(
                                pick=p,
                                current_pnl_pct=_cur_pnl,
                                peak_pnl_pct=_peak,
                                sp=_ee_sp,
                                spy_ret5=_spy_ret5_grade,
                            )
                            if _should_exit:
                                exit_price   = latest_close
                                exit_reason  = "indicator_exit"
                                exit_day_idx = len(hist) - 1 if not hist.empty else 0
                                exit_opt_pct = max(-stop_pct, min(tp_pct, _cur_pnl))
                                p["indicator_exit_detail"] = _exit_detail
                                # Fall through to outcome determination below
                    elif p.get("type") == "daily_scan" and premium > 0:
                        # Still track peak even when early exit not triggered
                        _cur_pnl = p.get("current_pnl_pct")
                        if _cur_pnl is not None:
                            _peak = float(p.get("peak_pnl_pct", 0))
                            if _cur_pnl > _peak:
                                p["peak_pnl_pct"] = round(_cur_pnl, 1)

                if exit_price is None:
                    continue

            actual_move_pct = round((exit_price / entry_price - 1) * 100, 2)
            predicted_move  = p.get("target_move_pct")
            if not predicted_move:
                _stock_tp = p.get("stock_tp")
                if _stock_tp is not None and entry_price:
                    predicted_move = abs((float(_stock_tp) / entry_price - 1) * 100)
                else:
                    predicted_move = 0

            if exit_reason == "tp_hit":
                outcome = "hit"
            elif exit_reason == "sl_hit":
                outcome = "miss"
            elif exit_reason == "indicator_exit":
                # Smart exits are gated by min_profit_to_exit_pct, so always profitable
                outcome = "hit" if (exit_opt_pct is not None and exit_opt_pct > 0) else "directional"
            else:
                dir_correct = (is_bullish and actual_move_pct > 0) or \
                              (not is_bullish and actual_move_pct < 0)
                mag_ok = abs(actual_move_pct) >= abs(predicted_move) * 0.5 if predicted_move else dir_correct
                if dir_correct and mag_ok:
                    outcome = "hit"
                elif dir_correct:
                    outcome = "directional"
                else:
                    outcome = "miss"

            option_gain_pct  = None
            daily_option_pnl: list[dict] = []
            if p.get("type") == "daily_scan" and premium > 0 and delta > 0:
                if exit_opt_pct is not None:
                    option_gain_pct = round(exit_opt_pct, 1)
                else:
                    raw_gain = dir_factor * delta * (entry_price * actual_move_pct / 100.0) / premium * 100.0
                    option_gain_pct = round(max(-stop_pct, min(tp_pct, raw_gain)), 1)

                hold_rows   = list(hist.iterrows())[: (exit_day_idx or len(hist) - 1) + 1]
                prev_opt_px = premium
                for di, (ts2, row2) in enumerate(hold_rows):
                    stock_px   = float(row2["Close"])
                    stock_move = stock_px - entry_price
                    raw_opt    = max(0.01, premium + dir_factor * delta * stock_move
                                    - theta_per_day * (di + 1))
                    raw_pct    = (raw_opt / premium - 1) * 100
                    capped_pct = max(-stop_pct, min(tp_pct, raw_pct))
                    capped_opt = premium * (1 + capped_pct / 100)
                    daily_option_pnl.append({
                        "date":      ts2.strftime("%Y-%m-%d"),
                        "stock_px":  round(stock_px, 2),
                        "stock_chg": round((stock_px / entry_price - 1) * 100, 2),
                        "opt_px":    round(capped_opt, 2),
                        "day_pct":   round((capped_opt / prev_opt_px - 1) * 100, 1),
                        "cum_pct":   round(capped_pct, 1),
                    })
                    prev_opt_px = capped_opt

            update = {
                "outcome":         outcome,
                "exit_price":      round(exit_price, 2),
                "actual_move_pct": actual_move_pct,
                "graded_date":     today.strftime("%Y-%m-%d"),
                "exit_reason":     exit_reason,
            }
            if option_gain_pct is not None:
                update["option_gain_pct"] = option_gain_pct
            if daily_option_pnl:
                update["daily_option_pnl"] = daily_option_pnl
            p.update(update)
            graded_count += 1

        _save_predictions(preds)
        return json.dumps({"message": f"Graded {graded_count} prediction(s).",
                           "predictions": preds}, indent=2, default=str)

    # ── ungrade ───────────────────────────────────────────────────────────────
    if action == "ungrade":
        ungraded_count = 0
        _grade_fields = ["outcome", "exit_price", "actual_move_pct", "graded_date",
                         "exit_reason", "option_gain_pct", "est_option_gain_pct",
                         "daily_option_pnl", "current_pnl_pct", "current_option_px",
                         "current_stock_pct", "current_stock_px", "grade_error",
                         "entry_open_price"]
        for p in preds:
            if not p.get("outcome"):
                continue
            if scan_date and p.get("entry_date", "")[:10] != scan_date:
                continue
            for key in _grade_fields:
                p.pop(key, None)
            ungraded_count += 1
        _save_predictions(preds)
        return json.dumps({"message": f"Ungraded {ungraded_count} prediction(s)."})

    # ── delete ────────────────────────────────────────────────────────────────
    if action == "delete":
        before = len(preds)
        preds = [p for p in preds if p.get("id") != prediction_id]
        _save_predictions(preds)
        return json.dumps({"message": f"Deleted prediction #{prediction_id}." if len(preds) < before
                           else f"Prediction #{prediction_id} not found."})

    # ── log ───────────────────────────────────────────────────────────────────
    if action == "log":
        if not ticker or not direction:
            return json.dumps({"error": "ticker and direction are required for action='log'"})
        if direction not in ("bullish", "bearish"):
            return json.dumps({"error": "direction must be 'bullish' or 'bearish'"})
        if not target_date:
            # default: 5 calendar days out
            target_date = (today + timedelta(days=5)).strftime("%Y-%m-%d")

        # Fetch current price as entry
        try:
            entry_price = round(_get_price(symbol=ticker.upper()), 2)
        except Exception as e:
            return json.dumps({"error": f"Could not fetch price for {ticker}: {e}"})

        new_id = max((p.get("id", 0) for p in preds), default=0) + 1
        pred = {
            "id":               new_id,
            "ticker":           ticker.upper(),
            "direction":        direction,
            "target_move_pct":  target_move_pct,
            "entry_date":       today.strftime("%Y-%m-%d"),
            "entry_price":      entry_price,
            "target_date":      target_date,
            "confidence":       max(1, min(10, confidence)),
            "reasoning":        reasoning,
            "outcome":          None,
        }
        preds.append(pred)
        _save_predictions(preds)
        return json.dumps({
            "message": f"Prediction #{new_id} logged.",
            "prediction": pred,
        }, indent=2, default=str)

    return json.dumps({"error": f"Unknown action '{action}'. Use: log, grade, list, delete"})


# ─── Tool 13: Retroactive prediction backfill ─────────────────────────────────

@_market_data_scoped
def backfill_predictions(
    tickers: list = None,
    lookback_days: int = 90,
    horizon_days: int = 5,
    overwrite: bool = False,
) -> str:
    """
    Retroactively generate and grade predictions for every past trading day.

    Signal logic (using only data available at market open that day):
      - 5-day return  (short momentum)
      - 20-day return (medium trend)
      - Position of close vs 20-day simple moving average

    Direction rules:
      bullish  if  5d_ret >  1.0%  AND  price > SMA20
      bearish  if  5d_ret < -1.0%  AND  price < SMA20

    Confidence scales with signal strength (1–10).
    Skips days where the signal is ambiguous.

    All predictions are graded immediately (target date has already passed).
    """
    if tickers is None:
        tickers = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "META", "AMD"]

    preds      = _load_predictions()
    existing   = set()
    if not overwrite:
        existing = {(p["ticker"], p["entry_date"]) for p in preds}

    today       = datetime.now().date()
    fetch_start = (datetime.now() - timedelta(days=lookback_days + 60)).strftime("%Y-%m-%d")
    fetch_end   = today.strftime("%Y-%m-%d")

    added = 0
    skipped_neutral = 0
    next_id = max((p.get("id", 0) for p in preds), default=0) + 1

    for ticker in tickers:
        try:
            ticker_up = ticker.upper()
            hist = _cached_history(ticker_up, start=fetch_start, end=fetch_end, interval="1d")
            if hist.empty or len(hist) < 25:
                continue
            closes = hist["Close"]
            opens  = hist["Open"]
            dates  = [d.date() for d in hist.index]

            for i in range(24, len(dates)):
                pred_date   = dates[i]          # the "today" for this prediction
                target_date = None
                # find the trading day ~horizon_days later
                for j in range(i + 1, min(i + horizon_days + 6, len(dates))):
                    if (dates[j] - pred_date).days >= horizon_days:
                        target_date = dates[j]
                        exit_idx    = j
                        break
                if target_date is None:
                    continue                     # not enough future data
                if (today - target_date).days < 0:
                    continue                     # target not yet reached

                date_str = pred_date.strftime("%Y-%m-%d")
                if (ticker_up, date_str) in existing:
                    continue

                # Signal: use data available *before* market open on pred_date
                #   close[i-1]  = yesterday's close (known at open)
                #   close[i-20..i-1] = last 20 closes
                c_now  = float(closes.iloc[i - 1])   # yesterday's close = entry proxy
                c_5    = float(closes.iloc[i - 6])   # 5 trading days ago
                sma20  = float(closes.iloc[i - 20: i].mean())
                ret5   = (c_now / c_5 - 1) * 100

                # Entry price = open on pred_date
                entry_price = round(float(opens.iloc[i]), 2)

                # Direction decision (threshold from the ticker's active profile)
                _sp = _get_profile(ticker)
                _mom_thr = float(_sp.get("entry", {}).get("entry_momentum_pct", 0.5))
                if ret5 > _mom_thr and c_now > sma20:
                    direction = "bullish"
                    # confidence: scales 6–9 with strength of signal
                    conf = min(9, 6 + int(min(ret5 - _mom_thr, 6) / 2))
                elif ret5 < -_mom_thr and c_now < sma20:
                    direction = "bearish"
                    conf = min(9, 6 + int(min(abs(ret5) - _mom_thr, 6) / 2))
                else:
                    skipped_neutral += 1
                    continue

                # Expected move = half of recent 5-day absolute move
                target_move_pct = round(abs(ret5) * 0.5, 2)

                # Grade immediately
                exit_price      = round(float(closes.iloc[exit_idx]), 2)
                actual_move_pct = round((exit_price / entry_price - 1) * 100, 2)
                dir_correct = (direction == "bullish" and actual_move_pct > 0) or \
                              (direction == "bearish" and actual_move_pct < 0)
                mag_ok = abs(actual_move_pct) >= target_move_pct * 0.5 if target_move_pct else dir_correct
                if dir_correct and mag_ok:
                    outcome = "hit"
                elif dir_correct:
                    outcome = "directional"
                else:
                    outcome = "miss"

                pred = {
                    "id":               next_id,
                    "ticker":           ticker_up,
                    "type":             "backfill",
                    "direction":        direction,
                    "target_move_pct":  target_move_pct,
                    "entry_date":       date_str,
                    "entry_price":      entry_price,
                    "target_date":      target_date.strftime("%Y-%m-%d"),
                    "confidence":       conf,
                    "reasoning":        f"5d_ret={ret5:+.1f}% vs SMA20 ({sma20:.2f})",
                    "outcome":          outcome,
                    "exit_price":       exit_price,
                    "actual_move_pct":  actual_move_pct,
                    "graded_date":      today.strftime("%Y-%m-%d"),
                    "source":           "backfill",
                }
                preds.append(pred)
                existing.add((ticker_up, date_str))
                next_id += 1
                added += 1

        except Exception:
            pass

    _save_predictions(preds)

    # Summary stats
    backfill_preds = [p for p in preds if p.get("source") == "backfill"]
    _non_action = ("manual_exit", "replaced")
    graded  = [p for p in backfill_preds if p.get("outcome") and p["outcome"] not in _non_action]
    hits    = [p for p in graded if p["outcome"] == "hit"]
    dir_ok  = [p for p in graded if p["outcome"] in ("hit", "directional")]

    return json.dumps({
        "message":          f"Backfilled {added} predictions across {len(tickers)} tickers.",
        "skipped_neutral":  skipped_neutral,
        "total_backfill":   len(backfill_preds),
        "hit_rate_pct":     round(len(hits) / len(graded) * 100, 1) if graded else None,
        "directional_rate_pct": round(len(dir_ok) / len(graded) * 100, 1) if graded else None,
        "tickers":          tickers,
        "lookback_days":    lookback_days,
        "horizon_days":     horizon_days,
    }, indent=2)


# ─── Tool 14: Historical strategy backtester ──────────────────────────────────

@_market_data_scoped
def backtest_strategy(
    symbol: str,
    option_type: str = "signal",   # "call" | "put" | "signal" (auto from momentum)
    dte_at_entry: int = None,      # defaults to the symbol profile's target DTE
    delta_target: float = None,    # defaults to STRATEGY_PROFILE["targets"]["delta_optimal"]
    lookback_days: int = 252,
    stop_loss_pct: float = None,   # defaults to STRATEGY_PROFILE["risk"]["stop_loss_pct"]
    profit_target_pct: float = None,  # defaults to STRATEGY_PROFILE["risk"]["profit_target_pct"]
    position_size_dollars: float = None,
    # Filters matching the bot's live rules
    vix_max: float = None,         # defaults to STRATEGY_PROFILE["filters"]["vix_defense_threshold"]
    hv_rank_max: float = 80.0,     # skip days estimated HV rank > this
    require_signal: bool = True,   # only trade on momentum+trend signal days (like bot)
) -> str:
    """
    Backtests the bot's ACTUAL methodology over historical data:

    Entry filters (all must pass to take a trade):
      1. Momentum signal: 5-day return direction aligns with option_type
         (or auto-selects direction when option_type='signal')
      2. Trend confirmation: price > SMA20 for calls, price < SMA20 for puts
      3. VIX proxy filter: estimated market vol < vix_max (uses SPY HV as proxy)
      4. HV rank filter: current 30-day HV not in top hv_rank_max% of trailing year
         (avoids buying expensive options — mirrors the bot's IV rank rule)

    Strike selection:
      - Searches for strike with BS delta closest to delta_target
        (bot targets 0.20–0.40 OTM delta range)

    Exit rules (same as live bot):
      - Stop-loss at stop_loss_pct% of premium
      - Profit target at profit_target_pct% gain
      - Hold to expiry otherwise (intrinsic value only)

    Position sizing:
      - Uses confidence-scaled sizing: stronger signal → larger position
        (mirrors the 7–40% linear confidence scale)
    """
    try:
        # Resolve defaults from the symbol's active profile.
        symbol_up = symbol.upper()
        _profile = _get_profile(symbol)
        if dte_at_entry is None:
            dte_at_entry = max(DTE_MIN, min(DTE_MAX, int(_profile["targets"]["dte_optimal"])))
        if delta_target      is None: delta_target      = _profile["targets"]["delta_optimal"]
        if stop_loss_pct     is None: stop_loss_pct     = _profile["risk"]["stop_loss_pct"]
        if profit_target_pct is None: profit_target_pct = _profile["risk"]["profit_target_pct"]
        if vix_max           is None: vix_max           = _profile["filters"]["vix_defense_threshold"]

        # Dollar sizing: explicit param → risk_settings account → fallback $1 000
        if position_size_dollars is None:
            acct = _profile["risk"].get("account_size") or 0
            position_size_dollars = acct * 0.10 if acct else 1_000.0

        fetch_days = lookback_days + dte_at_entry + 120
        hist = _cached_history(symbol_up, period=f"{fetch_days}d")
        if hist.empty or len(hist) < 80:
            return json.dumps({"error": f"Not enough price history for {symbol}"})

        # Also fetch SPY as VIX proxy (HV of SPY ≈ market vol regime)
        spy_hist = _cached_history("SPY", period=f"{fetch_days}d") if symbol_up != "SPY" else hist
        spy_closes = spy_hist["Close"].dropna()

        closes = hist["Close"].dropna()
        highs  = hist["High"].reindex(closes.index).ffill()
        lows   = hist["Low"].reindex(closes.index).ffill()
        n = len(closes)

        # Build a lookup: date → SPY HV30 (for VIX proxy filter)
        spy_hv_by_idx = {}
        for si in range(30, len(spy_closes)):
            lr = [math.log(float(spy_closes.iloc[j]) / float(spy_closes.iloc[j-1]))
                  for j in range(si - 30, si) if j > 0]
            if len(lr) >= 20:
                spy_hv_by_idx[si] = float(np.std(lr) * math.sqrt(252)) * 100  # annualised %

        # Build rolling 252-day HV percentile lookup for this ticker (HV rank proxy)
        hv_history = []
        for ci in range(30, n):
            lr = [math.log(float(closes.iloc[j]) / float(closes.iloc[j-1]))
                  for j in range(ci - 30, ci) if j > 0]
            hv_history.append(float(np.std(lr) * math.sqrt(252)) * 100 if len(lr) >= 20 else 0.0)

        # Pre-fetch known earnings dates to skip bars where earnings fall within hold window
        _earnings_date_strs: set[str] = set()
        try:
            _ed_df = _cached_earnings_dates(symbol_up)
            if _ed_df is not None and not _ed_df.empty:
                for _edt in _ed_df.index:
                    _earnings_date_strs.add(str(_edt)[:10])
        except Exception:
            pass

        simulated  = []
        skipped    = {"no_signal": 0, "vix_filter": 0, "hv_rank_filter": 0,
                      "no_valid_strike": 0, "tech_score": 0, "ev_gate": 0, "earnings": 0}

        # Pull thresholds from the correct profile for this ticker
        _sp        = _get_profile(symbol)
        _min_tech  = float(_sp["entry"].get("min_tech_score", 55.0))
        _min_dir   = float(_sp["entry"].get("min_direction_score", 35.0))
        _min_ev    = float(_sp["filters"].get("min_ev_return_pct", 10.0))

        for i in range(50, min(n - dte_at_entry - 1, lookback_days + 50)):
            S0 = float(closes.iloc[i])

            # ── HV calculations ────────────────────────────────────────────────
            log_rets = [math.log(float(closes.iloc[j]) / float(closes.iloc[j-1]))
                        for j in range(i - 30, i) if j > 0]
            if len(log_rets) < 20:
                continue
            hv30 = float(np.std(log_rets) * math.sqrt(252))
            if hv30 <= 0:
                continue

            # ── Filter 1: VIX proxy (SPY HV30 as market vol regime) ────────────
            spy_idx_now = min(int(i * len(spy_closes) / n), len(spy_closes) - 1)
            spy_hv  = spy_hv_by_idx.get(spy_idx_now, 0)
            if spy_hv > vix_max:
                skipped["vix_filter"] += 1
                continue

            # ── Earnings gate: skip if known earnings fall within hold window ─────
            if _earnings_date_strs:
                _bar_dt = datetime.strptime(str(closes.index[i])[:10], "%Y-%m-%d")
                _earn_skip = any(
                    0 <= (datetime.strptime(_es, "%Y-%m-%d") - _bar_dt).days <= dte_at_entry
                    for _es in _earnings_date_strs
                    if len(_es) == 10
                )
                if _earn_skip:
                    skipped["earnings"] += 1
                    continue

            # ── Filter 2: HV rank proxy — skip if vol is historically expensive ──
            hv_hist_idx = i - 30
            if hv_hist_idx >= len(hv_history) and hv_hist_idx < 0:
                continue
            trailing = [hv_history[j] for j in range(max(0, hv_hist_idx - 252), hv_hist_idx + 1)
                        if hv_history[j] > 0]
            hv_rank = 50.0  # neutral default
            if trailing:
                hv_rank = sum(1 for v in trailing if v <= hv30 * 100) / len(trailing) * 100
                if hv_rank > hv_rank_max:
                    skipped["hv_rank_filter"] += 1
                    continue

            # ── Filter 3: Full scoring pipeline (same as live scanner + brain) ──
            _p_arr = closes.values[:i + 1].astype(float)
            _idx   = len(_p_arr) - 1

            sma20 = float(np.mean(_p_arr[_idx - 20:_idx]))
            sma50 = float(np.mean(_p_arr[_idx - 50:_idx]))
            ret5  = (S0 / float(closes.iloc[i - 5]) - 1) * 100 if i >= 5 else 0.0

            # RSI 14 from historical closes
            _diffs    = np.diff(_p_arr[max(0, _idx - 15):_idx + 1])
            _avg_up   = float(np.mean(_diffs[_diffs > 0])) if np.any(_diffs > 0) else 0.0
            _avg_down = float(np.mean(-_diffs[_diffs < 0])) if np.any(_diffs < 0) else 0.0
            rsi14     = 100.0 - 100.0 / (1.0 + _avg_up / (_avg_down + 1e-9))

            # MACD (EMA12 − EMA26) from historical closes
            _k12, _k26 = 2.0 / 13.0, 2.0 / 27.0
            _e12 = _e26 = float(_p_arr[0])
            _e12p = _e26p = _e12
            for _px in _p_arr[1:]:
                _e12p, _e26p = _e12, _e26
                _e12 = float(_px) * _k12 + _e12 * (1 - _k12)
                _e26 = float(_px) * _k26 + _e26 * (1 - _k26)
            macd        = _e12 - _e26
            macd_rising = macd > (_e12p - _e26p)

            # SPY 5-day return for regime alignment score
            spy_idx_5 = max(0, spy_idx_now - 5)
            spy_ret5  = (float(spy_closes.iloc[spy_idx_now]) /
                         float(spy_closes.iloc[spy_idx_5]) - 1) * 100

            # Tech score — same formula as _compute_tech_score_live
            def _tech_score_bt(tt: str) -> float:
                if tt == "call":
                    _tr  = (50.0 if S0 > sma20 else 0.0) + (50.0 if sma20 > sma50 else 0.0)
                    _rs  = max(0.0, 100.0 - abs(rsi14 - 55.0) * (100.0 / 35.0))
                    _mcd = 100.0 if macd > 0 and macd_rising else (50.0 if macd > 0 else 0.0)
                else:
                    _tr  = (50.0 if S0 < sma20 else 0.0) + (50.0 if sma20 < sma50 else 0.0)
                    _rs  = max(0.0, 100.0 - abs(rsi14 - 45.0) * (100.0 / 35.0))
                    _mcd = 100.0 if macd < 0 and not macd_rising else (50.0 if macd < 0 else 0.0)
                return _tr * 0.40 + _rs * 0.35 + _mcd * 0.25

            if option_type == "signal":
                # Auto-select direction: pick whichever passes gates with higher direction_score
                _best_dir, _best_ds, _best_ts = None, -1.0, 0.0
                for _tt in ("call", "put"):
                    _ts = _tech_score_bt(_tt)
                    if _ts < _min_tech:
                        continue
                    _ds = _compute_direction_score(_ts, _tt, rsi14, ret5, spy_ret5, sp=_sp)
                    if _ds >= _min_dir and _ds > _best_ds:
                        _best_ds, _best_dir, _best_ts = _ds, _tt, _ts
                if _best_dir is None:
                    skipped["no_signal"] += 1
                    continue
                trade_type      = _best_dir
                tech_score      = _best_ts
                direction_score = _best_ds
            else:
                trade_type  = option_type
                tech_score  = _tech_score_bt(trade_type)
                if tech_score < _min_tech:
                    skipped["tech_score"] += 1
                    continue
                direction_score = _compute_direction_score(
                    tech_score, trade_type, rsi14, ret5, spy_ret5, sp=_sp)
                if direction_score < _min_dir:
                    skipped["no_signal"] += 1
                    continue

            # IV crush proxy: z-score of current HV30 vs trailing HV distribution
            # (mirrors brain's _calculate_iv_skew — uses HV as IV proxy in backtest)
            _hv_slice = [hv_history[j] for j in range(max(0, hv_hist_idx - 252), hv_hist_idx + 1)
                         if hv_history[j] > 0]
            if len(_hv_slice) >= 10:
                _hv_mean = float(np.mean(_hv_slice))
                _hv_std  = float(np.std(_hv_slice))
                if _hv_std > 0:
                    _hv_z = (hv30 * 100 - _hv_mean) / _hv_std
                    if _hv_z >= _sp["filters"]["iv_crush_z_threshold"]:
                        _crush_pen = _sp["filters"]["iv_crush_confidence_penalty"]
                        direction_score = max(0.0, direction_score - _crush_pen)
                        if direction_score < _min_dir:
                            skipped["no_signal"] += 1
                            continue

            # EV gate — same as live scanner
            _p_win = direction_score / 100.0
            _ev    = _p_win * profit_target_pct - (1.0 - _p_win) * stop_loss_pct
            if require_signal and _ev < _min_ev:
                skipped["ev_gate"] += 1
                continue

            # Position sizing — direction_score drives allocation (same 7–40% scale)
            _risk = _sp["risk"]
            lo = float(_risk["min_position_pct"]) / 100
            hi = float(_risk["max_position_pct"]) / 100
            conf_pct = lo + (direction_score / 100.0) * (hi - lo)
            acct = _risk.get("account_size") or 0
            if acct:
                trade_dollars = round(acct * conf_pct, 2)
            else:
                trade_dollars = round(position_size_dollars * conf_pct, 2)

            # ATR stop widening — same multiplier as brain (_get_market_regime)
            _tr_vals = []
            for _ai in range(max(1, i - 27), i + 1):
                _h = float(highs.iloc[_ai])
                _l = float(lows.iloc[_ai])
                _cp = float(closes.iloc[_ai - 1])
                _tr_vals.append(max(_h - _l, abs(_h - _cp), abs(_l - _cp)))
            _atr14 = float(np.mean(_tr_vals[-14:])) if len(_tr_vals) >= 14 else 0.0
            _atr28 = float(np.mean(_tr_vals)) if _tr_vals else _atr14
            _atr_expanding = _atr14 > _atr28 * 1.05
            _stop_mult = float(_sp["filters"]["atr_expansion_stop_mult"]) if _atr_expanding else 1.0

            # ── Strike selection: find strike closest to delta_target ───────────
            T = dte_at_entry / 365.0
            best_strike = None
            best_delta_diff = 999
            for offset_pct in [x * 0.5 for x in range(-10, 16)]:  # -5% to +7.5% in 0.5% steps
                K_cand = round(S0 * (1 + offset_pct / 100), 2)
                g = _bs_greeks(S0, K_cand, T, RISK_FREE_RATE, hv30, trade_type)
                if not g:
                    continue
                d = abs(g.get("delta", 0))
                diff = abs(d - delta_target)
                if diff < best_delta_diff:
                    best_delta_diff = diff
                    best_strike = K_cand
                    best_entry_g = g

            if best_strike is None or not best_entry_g.get("bs_price") or best_entry_g["bs_price"] < 0.01:
                skipped["no_valid_strike"] += 1
                continue

            K        = best_strike
            entry_px = best_entry_g["bs_price"]
            stop_px  = entry_px * (1 - (stop_loss_pct / 100) * _stop_mult)
            target_px = entry_px * (1 + profit_target_pct / 100)

            # ── Simulate holding through DTE ───────────────────────────────────
            exit_px     = None
            exit_reason = "expired"

            for d in range(1, dte_at_entry + 1):
                fi = i + d
                if fi >= n:
                    break
                S_now = float(closes.iloc[fi])
                T_now = max((dte_at_entry - d) / 365.0, 0)

                if T_now <= 0:
                    exit_px = max(0.0, S_now - K) if trade_type == "call" else max(0.0, K - S_now)
                    exit_reason = "expired"
                    break

                g = _bs_greeks(S_now, K, T_now, RISK_FREE_RATE, hv30, trade_type)
                opt_now = g.get("bs_price", 0.0) if g else 0.0

                if opt_now <= stop_px:
                    exit_px = opt_now
                    exit_reason = f"stop_loss ({stop_loss_pct}%)"
                    break
                if opt_now >= target_px:
                    exit_px = target_px              # cap at limit price, like a real limit order
                    exit_reason = f"profit_target ({profit_target_pct}%)"
                    break

            if exit_px is None:
                fi = min(i + dte_at_entry, n - 1)
                S_exp    = float(closes.iloc[fi])
                intrinsic = max(0.0, S_exp - K) if trade_type == "call" else max(0.0, K - S_exp)
                # Cap at profit target — mirrors live behaviour where a limit order
                # would have filled before expiry if the option reached the target
                exit_px  = min(intrinsic, target_px)

            quality_score = _compute_quality_score(hv_rank, abs(best_entry_g.get("delta", 0)), dte_at_entry, sp=_sp)

            pnl_pct     = round((exit_px / entry_px - 1) * 100, 1)
            pnl_dollars = round(trade_dollars * pnl_pct / 100, 2)
            simulated.append({
                "entry_date":       str(closes.index[i])[:10],
                "underlying_entry": round(S0, 2),
                "option_type":      trade_type,
                "strike":           K,
                "delta":            round(abs(best_entry_g.get("delta", 0)), 3),
                "entry_option_px":  round(entry_px, 4),
                "exit_option_px":   round(exit_px, 4),
                "exit_reason":      exit_reason,
                "pnl_pct":          pnl_pct,
                "pnl_dollars":      pnl_dollars,
                "position_dollars": trade_dollars,
                "hv30_as_iv":       round(hv30 * 100, 1),
                "signal_5d_ret":    round(ret5, 2),
                "direction_score":  round(direction_score, 1),
                "tech_score":       round(tech_score, 1),
                "quality_score":    round(quality_score, 1),
                "rsi14":            round(rsi14, 1),
                "ev_pct":           round(_ev, 1),
            })

        if not simulated:
            return json.dumps({
                "error": "No valid simulated trades. Try wider parameters or disable filters.",
                "skipped": skipped,
            })

        wins    = [t for t in simulated if t["pnl_pct"] > 0]
        losses  = [t for t in simulated if t["pnl_pct"] <= 0]
        doubles = [t for t in simulated if t["pnl_pct"] >= profit_target_pct]
        stopped = [t for t in simulated if "stop_loss" in t["exit_reason"]]

        avg_pnl  = round(sum(t["pnl_pct"] for t in simulated) / len(simulated), 1)
        avg_win  = round(sum(t["pnl_pct"] for t in wins)   / len(wins),   1) if wins   else 0
        avg_loss = round(sum(t["pnl_pct"] for t in losses) / len(losses), 1) if losses else 0
        ev = round((len(wins)/len(simulated)) * avg_win + (len(losses)/len(simulated)) * avg_loss, 1)

        total_pnl_dollars        = round(sum(t["pnl_dollars"]      for t in simulated), 2)
        total_capital_deployed   = round(sum(t["position_dollars"]  for t in simulated), 2)
        total_return_pct         = round(
            total_pnl_dollars / total_capital_deployed * 100, 1
        ) if total_capital_deployed else 0

        # Build equity curve: running cumulative P&L + per-trade breakdown
        equity_curve = []
        cumulative_dollars = 0.0
        cumulative_capital = 0.0
        peak_dollars = 0.0
        max_dd_pct   = 0.0
        for trade in simulated:
            cumulative_dollars  = round(cumulative_dollars + trade["pnl_dollars"], 2)
            cumulative_capital += trade["position_dollars"]
            peak_dollars        = max(peak_dollars, cumulative_dollars)
            if peak_dollars > 0:
                dd = (peak_dollars - cumulative_dollars) / peak_dollars * 100
                max_dd_pct = max(max_dd_pct, dd)
            cum_return_pct = round(
                cumulative_dollars / cumulative_capital * 100, 2
            ) if cumulative_capital else 0.0
            equity_curve.append({
                "date":           trade["entry_date"],
                "cumulative_pnl": cumulative_dollars,
                "cum_return_pct": cum_return_pct,
                "trade_pnl_pct":  trade["pnl_pct"],
                "win":            trade["pnl_pct"] > 0,
            })

        return json.dumps({
            "symbol": symbol.upper(),
            "strategy": {
                "option_type":           option_type,
                "dte_at_entry":          dte_at_entry,
                "delta_target":          delta_target,
                "stop_loss_pct":         stop_loss_pct,
                "profit_target_pct":     profit_target_pct,
                "lookback_days":         lookback_days,
                "vix_max":               vix_max,
                "hv_rank_max":           hv_rank_max,
                "require_signal":        require_signal,
                "IMPORTANT_CAVEAT": (
                    "IV estimated from 30-day HV. Real options used actual implied vol, "
                    "which varies. This simulation shows if the STOCK made the required move, "
                    "not guaranteed option P&L. Use as directional signal, not precise forecast."
                ),
            },
            "filters": {
                "days_skipped_no_signal":       skipped["no_signal"],
                "days_skipped_tech_score_low":  skipped["tech_score"],
                "days_skipped_ev_gate":         skipped["ev_gate"],
                "days_skipped_vix_too_high":    skipped["vix_filter"],
                "days_skipped_hv_rank_high":    skipped["hv_rank_filter"],
                "days_skipped_earnings":        skipped["earnings"],
                "days_skipped_no_strike":       skipped["no_valid_strike"],
                "days_traded":                  len(simulated),
                "score_gates": {
                    "min_tech_score":       _min_tech,
                    "min_direction_score":  _min_dir,
                    "min_ev_return_pct":    _min_ev,
                },
            },
            "results": {
                "trades_simulated":       len(simulated),
                "win_rate_pct":           round(len(wins)/len(simulated)*100, 1),
                "avg_pnl_pct":            avg_pnl,
                "expected_value_pct":     ev,
                "avg_winning_trade_pct":  avg_win,
                "avg_losing_trade_pct":   avg_loss,
                "hit_profit_target_pct":  round(len(doubles)/len(simulated)*100, 1),
                "stopped_out_pct":        round(len(stopped)/len(simulated)*100, 1),
                "expired_worthless_pct":  round(
                    sum(1 for t in simulated if t["exit_reason"]=="expired" and t["pnl_pct"]<-90)
                    / len(simulated) * 100, 1),
                "total_pnl_dollars":      total_pnl_dollars,
                "total_capital_deployed": total_capital_deployed,
                "total_return_pct":       total_return_pct,
                "max_drawdown_pct":       round(max_dd_pct, 1),
            },
            "equity_curve":  equity_curve,
            "best_trade":    max(simulated, key=lambda x: x["pnl_pct"]),
            "worst_trade":   min(simulated, key=lambda x: x["pnl_pct"]),
            "all_trades":    simulated,
        }, indent=2)

    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Strategy engine helpers (internal, not exposed as standalone tools) ──────

def _compute_tech_score_live(symbol: str, option_type: str = "call") -> float:
    """
    Fetch recent price history and compute a direction-aware technical setup score (0–100).

    Uses the same RSI + MACD + SMA formula as the optimizer's _tech_score():
      40% SMA trend (price / sma20 / sma50 alignment)
      35% RSI 14 positioning (momentum building in the right direction)
      25% MACD histogram direction

    Returns 50.0 (neutral) if data cannot be fetched.
    """
    try:
        hist = _cached_history(symbol, period="90d")["Close"].dropna()
        if len(hist) < 55:
            return 50.0
        p = hist.values.astype(float)
        n = len(p)
        idx = n - 2 if _market_is_open() and n >= 2 else n - 1
        if idx < 50:
            return 50.0, 50.0, 0.0

        # SMA20 / SMA50
        sma20 = float(np.mean(p[idx - 20 : idx]))
        sma50 = float(np.mean(p[idx - 50 : idx]))
        price = float(p[idx])

        # RSI 14
        diffs = np.diff(p[idx - 15 : idx + 1])
        avg_up   = float(np.mean(diffs[diffs > 0])) if np.any(diffs > 0) else 0.0
        avg_down = float(np.mean(-diffs[diffs < 0])) if np.any(diffs < 0) else 0.0
        rs   = avg_up / (avg_down + 1e-9)
        rsi14 = 100.0 - 100.0 / (1.0 + rs)

        # MACD (EMA12 − EMA26)
        k12, k26 = 2.0 / 13.0, 2.0 / 27.0
        ema12 = ema26 = float(p[0])
        ema12_prev = ema26_prev = ema12
        for px in p[1:]:
            ema12_prev, ema26_prev = ema12, ema26
            ema12 = float(px) * k12 + ema12 * (1 - k12)
            ema26 = float(px) * k26 + ema26 * (1 - k26)
        macd      = ema12 - ema26
        macd_prev = ema12_prev - ema26_prev
        macd_rising = macd > macd_prev

        trade_type = option_type.lower()
        if trade_type == "call":
            trend  = (50.0 if price > sma20 else 0.0) + (50.0 if sma20 > sma50 else 0.0)
            rsi_s  = max(0.0, 100.0 - abs(rsi14 - 55.0) * (100.0 / 35.0))
            macd_s = 100.0 if macd > 0 and macd_rising else (50.0 if macd > 0 else 0.0)
        else:
            trend  = (50.0 if price < sma20 else 0.0) + (50.0 if sma20 < sma50 else 0.0)
            rsi_s  = max(0.0, 100.0 - abs(rsi14 - 45.0) * (100.0 / 35.0))
            macd_s = 100.0 if macd < 0 and not macd_rising else (50.0 if macd < 0 else 0.0)

        score = trend * 0.40 + rsi_s * 0.35 + macd_s * 0.25
        ret5 = round(float(price / p[idx - 5] - 1) * 100, 2) if idx >= 5 else 0.0
        return round(float(score), 1), round(rsi14, 1), ret5
    except Exception:
        return 50.0, 50.0, 0.0


def _fetch_best_option(
    ticker: str,
    trade_type: str,         # "call" or "put"
    delta_target: float,
    target_dte: int,
    stock_price: float = 0.0,
    hv30_fallback: float = 0.30,
) -> dict | None:
    """
    Fetch the real options chain and return the strike/premium closest to delta_target.

    Works both during market hours (uses bid/ask mid) and after hours (uses lastPrice).
    Falls back to Black-Scholes on HV30 if the chain is completely unavailable.

    Returns a dict with keys: strike, premium, expiry, dte, delta, iv, live_chain
    Returns None if no valid option could be found at all.
    """
    best: dict | None = None
    best_diff = 999.0

    # ── Fetch current stock price if not provided ─────────────────────────────
    _S = stock_price
    try:
        if not _S:
            _S = float(_cached_history(ticker, period="2d")["Close"].dropna().iloc[-1])
    except Exception:
        pass
    if not _S:
        return None

    # ── Try real options chain first ──────────────────────────────────────────
    try:
        _exp_snapshot = _cached_options_metadata(ticker)
        _exps = list(_exp_snapshot.value or []) if getattr(_exp_snapshot, "status", None) == "fresh" else []
        if _exps:
            _today_d = datetime.now().date()
            # Filter to expirations within system-wide DTE bounds
            _valid_exps = [
                e for e in _exps
                if DTE_MIN <= (datetime.strptime(e, "%Y-%m-%d").date() - _today_d).days <= DTE_MAX
            ]
            if not _valid_exps:
                raise ValueError(f"No expirations between {DTE_MIN}–{DTE_MAX} DTE")
            _best_exp = min(
                _valid_exps,
                key=lambda e: abs((datetime.strptime(e, "%Y-%m-%d").date() - _today_d).days - target_dte)
            )
            _actual_dte = (datetime.strptime(_best_exp, "%Y-%m-%d").date() - _today_d).days
            _T          = max(_actual_dte, 1) / 365.0
            _chain_snapshot = _cached_option_chain_metadata(ticker, _best_exp)
            if getattr(_chain_snapshot, "status", None) != "fresh":
                raise ValueError("option chain snapshot is not fresh")
            _chain = _chain_snapshot.value
            _df         = _chain.calls if trade_type == "call" else _chain.puts

            for _, _row in _df.iterrows():
                _K    = float(_row.get("strike") or 0)
                if _K <= 0:
                    continue

                # Premium: bid/ask mid during hours, lastPrice after hours
                _bid  = float(_row.get("bid")       or 0)
                _ask  = float(_row.get("ask")       or 0)
                _last = float(_row.get("lastPrice") or 0)
                if _bid > 0 and _ask > 0:
                    _mid = (_bid + _ask) / 2
                elif _last > 0:
                    _mid = _last
                else:
                    continue
                if _mid < 0.01:
                    continue

                _contract_volume = int(_row.get("volume") or 0)
                _open_interest = int(_row.get("openInterest") or 0)
                _last_trade_age_hours = None
                _last_trade_raw = _row.get("lastTradeDate")
                if _last_trade_raw is not None:
                    try:
                        if hasattr(_last_trade_raw, "to_pydatetime"):
                            _last_trade_dt = _last_trade_raw.to_pydatetime()
                        elif isinstance(_last_trade_raw, datetime):
                            _last_trade_dt = _last_trade_raw
                        else:
                            _last_trade_dt = datetime.fromisoformat(str(_last_trade_raw).replace("Z", "+00:00"))
                        _now_dt = datetime.now(_last_trade_dt.tzinfo) if getattr(_last_trade_dt, "tzinfo", None) else datetime.now()
                        _last_trade_age_hours = max((_now_dt - _last_trade_dt).total_seconds() / 3600.0, 0.0)
                    except Exception:
                        _last_trade_age_hours = None

                # IV: use chain value when available, else HV30 for delta calc only
                _iv  = float(_row.get("impliedVolatility") or 0)
                _vol = _iv if _iv > 0.01 else hv30_fallback

                _g = _bs_greeks(_S, _K, _T, RISK_FREE_RATE, _vol, trade_type)
                if not _g:
                    continue

                _diff = abs(abs(_g.get("delta", 0)) - delta_target)
                if _diff < best_diff:
                    best_diff = _diff
                    best = {
                        "strike":     _K,
                        "premium":    round(_mid, 4),
                        "bid":        round(_bid, 4),
                        "ask":        round(_ask, 4),
                        "expiry":     _best_exp,
                        "dte":        _actual_dte,
                        "delta":      round(abs(_g.get("delta", 0)), 3),
                        "iv":         round(_iv, 4),
                        "volume":     _contract_volume,
                        "open_interest": _open_interest,
                        "quote_age_hours": round(_last_trade_age_hours, 2) if _last_trade_age_hours is not None else None,
                        "contract_symbol": str(_row.get("contractSymbol") or "").strip().upper() or None,
                        "quote_basis": "mid" if (_bid > 0 and _ask > 0) else "last",
                        "live_chain": True,
                        "options_snapshot_status": getattr(_exp_snapshot, "status", None),
                        "option_chain_status": getattr(_chain_snapshot, "status", None),
                    }
    except Exception:
        pass

    if best is not None:
        return best

    # ── BS fallback: real-increment strikes priced on HV30 ───────────────────
    try:
        _S_fb = _S  # already fetched above
        if _S >= 200:  _inc = 5.0
        elif _S >= 50: _inc = 1.0
        else:          _inc = 0.5
        _base = round(round(_S / _inc) * _inc, 2)
        _clamped_dte = max(DTE_MIN, min(DTE_MAX, target_dte))
        _T    = _clamped_dte / 365.0
        for _K in [round(_base + i * _inc, 2) for i in range(-20, 21)]:
            _g = _bs_greeks(_S, _K, _T, RISK_FREE_RATE, hv30_fallback, trade_type)
            if not _g:
                continue
            _diff = abs(abs(_g.get("delta", 0)) - delta_target)
            if _diff < best_diff:
                best_diff = _diff
                best = {
                    "strike":     _K,
                    "premium":    round(float(_g.get("bs_price", 0)), 4),
                    "expiry":     None,
                    "dte":        target_dte,
                    "delta":      round(abs(_g.get("delta", 0)), 3),
                    "iv":         round(hv30_fallback, 4),
                    "contract_symbol": None,
                    "quote_basis": "model",
                    "live_chain": False,
                }
    except Exception:
        pass

    return best


def _compute_quality_score(iv_pct: float, delta_val: float, dte: int, sp=None) -> float:
    """
    Option quality score (0-100): how good is the option to buy if direction is right?
    Components: IV rank (40%) + delta fit (35%) + DTE fit (25%)
    Independent of direction — purely about option economics.
    Pass sp=_get_profile(ticker) to use the correct profile for the ticker.
    """
    import math as _math
    if sp is None:
        sp = STRATEGY_PROFILE

    iv_score    = max(0.0, 100.0 - iv_pct)   # 0th pct = 100, 100th pct = 0

    d_opt   = float(sp["targets"]["delta_optimal"])
    d_fall  = float(sp["targets"]["delta_falloff"])
    delta_score = 100.0 * _math.exp(-((abs(delta_val) - d_opt) ** 2) / (2 * d_fall ** 2))

    t_opt   = float(sp["targets"]["dte_optimal"])
    t_fall  = float(sp["targets"]["dte_falloff"])
    dte_score = 100.0 * _math.exp(-((dte - t_opt) ** 2) / (2 * max(t_fall, 1.0) ** 2))

    _qw     = sp.get("quality_score_weights", {})
    _w_iv   = float(_qw.get("iv_rank", 0.40))
    _w_d    = float(_qw.get("delta",   0.35))
    _w_dte  = float(_qw.get("dte",     0.25))
    _w_tot  = _w_iv + _w_d + _w_dte or 1.0
    quality = (iv_score * _w_iv + delta_score * _w_d + dte_score * _w_dte) / _w_tot
    return round(min(100.0, max(0.0, quality)), 1)


def _compute_direction_score(
    tech_score: float,
    trade_type: str,     # "call" or "put"
    rsi14: float,
    ret5: float,         # 5-day % return of the underlying
    spy_ret5: float,     # 5-day % return of SPY (market regime)
    sp=None,             # strategy profile dict; defaults to STRATEGY_PROFILE (equity)
) -> float:
    """
    Direction Score (0-100): how likely is the stock to move in the intended direction?

    Three weighted components:
      55% tech score        (RSI/MACD/SMA directional alignment)
      30% regime alignment  (SPY moving same direction as trade?)
      15% momentum strength (magnitude of 5-day move in trade direction)

    Minus an RSI overextension penalty (0-15 pts) for mean-reversion risk:
      if bullish and RSI > 72 → -15 pts; RSI > 68 → -8 pts
      if bearish and RSI < 28 → -15 pts; RSI < 32 → -8 pts
    """
    if sp is None:
        sp = STRATEGY_PROFILE
    _dw  = sp.get("direction_score_weights", {})
    _w_tech = float(_dw.get("tech",     0.55))
    _w_reg  = float(_dw.get("regime",   0.30))
    _w_mom  = float(_dw.get("momentum", 0.15))
    _rsi_oe = sp.get("rsi_overextension", {})
    _sev_t  = float(_rsi_oe.get("severe_threshold",   72))
    _mod_t  = float(_rsi_oe.get("moderate_threshold", 68))
    _sev_p  = float(_rsi_oe.get("severe_penalty",     15.0))
    _mod_p  = float(_rsi_oe.get("moderate_penalty",    8.0))

    is_bullish = (trade_type == "call")

    # ── Regime alignment (0-100): is SPY moving with the trade? ──────────────
    spy_aligned   = (is_bullish and spy_ret5 > 0) or (not is_bullish and spy_ret5 < 0)
    spy_magnitude = abs(spy_ret5)
    if spy_magnitude < 0.5:
        regime_score = 50.0                              # flat market = neutral
    elif spy_aligned:
        regime_score = min(100.0, 50.0 + spy_magnitude * 16.7)
    else:
        regime_score = max(0.0, 50.0 - spy_magnitude * 16.7)

    # ── Momentum strength (0-100): how big is the move in the right direction? ─
    move_in_trade_direction = ret5 if is_bullish else -ret5
    mom_score = min(100.0, max(0.0, move_in_trade_direction / 5.0 * 100.0))

    # ── Weighted blend ────────────────────────────────────────────────────────
    _w_total = _w_tech + _w_reg + _w_mom or 1.0
    raw = (tech_score * _w_tech + regime_score * _w_reg + mom_score * _w_mom) / _w_total

    # ── RSI overextension penalty ─────────────────────────────────────────────
    if is_bullish:
        penalty = _sev_p if rsi14 > _sev_t else (_mod_p if rsi14 > _mod_t else 0.0)
    else:
        _bear_sev_t = 100.0 - _sev_t   # mirror: 72 → 28
        _bear_mod_t = 100.0 - _mod_t   # mirror: 68 → 32
        penalty = _sev_p if rsi14 < _bear_sev_t else (_mod_p if rsi14 < _bear_mod_t else 0.0)

    return round(max(0.0, min(100.0, raw - penalty)), 1)


def _check_early_exit(
    pick: dict,
    current_pnl_pct: float,
    peak_pnl_pct: float,
    sp: dict = None,
    spy_ret5: float = 0.0,
) -> tuple:
    """
    Check whether a pending pick should be exited early based on indicator
    degradation. Only called for profitable picks held >= min_hold_days.

    Returns (should_exit: bool, reason_detail: str).
    """
    if sp is None:
        sp = _get_profile(pick.get("ticker", ""))

    ee = sp.get("early_exit", {})
    if not ee.get("enabled", False):
        return False, ""

    ticker     = pick["ticker"]
    trade_type = pick["direction"]
    is_bull    = trade_type in ("call", "bullish")

    # ── 1. Trailing profit giveback (no API call) ─────────────────────────
    trail_activate = float(ee.get("trailing_profit_pct", 40.0))
    trail_giveback = float(ee.get("trailing_giveback_pct", 50.0))
    if peak_pnl_pct >= trail_activate and current_pnl_pct < peak_pnl_pct:
        pct_given_back = (peak_pnl_pct - current_pnl_pct) / peak_pnl_pct * 100
        if pct_given_back >= trail_giveback:
            return True, (
                f"profit giveback: peak {peak_pnl_pct:+.1f}% -> now {current_pnl_pct:+.1f}% "
                f"({pct_given_back:.0f}% of gains lost)"
            )

    # ── 2-5. Fetch live indicators (one call via existing function) ───────
    try:
        tech_live, rsi_live, ret5_live = _compute_tech_score_live(ticker, trade_type)
    except Exception:
        return False, ""  # can't compute indicators — skip

    dir_score_live = _compute_direction_score(
        tech_live, trade_type, rsi_live, ret5_live, spy_ret5, sp=sp,
    )

    # ── 2. Tech score decay ───────────────────────────────────────────────
    entry_tech = float(pick.get("tech_score", 50))
    tech_decay_threshold = float(ee.get("tech_decay_pct", 35.0))
    if entry_tech > 0:
        decay_pct = (entry_tech - tech_live) / entry_tech * 100
        if decay_pct >= tech_decay_threshold:
            return True, (
                f"tech_score collapsed {decay_pct:.0f}% "
                f"({entry_tech:.0f} -> {tech_live:.0f})"
            )

    # ── 3. Direction score below floor ────────────────────────────────────
    dir_floor = float(ee.get("direction_floor", 30.0))
    if dir_score_live < dir_floor:
        return True, (
            f"direction_score {dir_score_live:.0f} below floor {dir_floor:.0f} "
            f"(entry was {pick.get('direction_score', '?')})"
        )

    # ── 4. Momentum reversal ─────────────────────────────────────────────
    if ee.get("momentum_reversal", True):
        entry_ret5 = float(pick.get("ret5", 0))
        if entry_ret5 != 0 and ret5_live != 0:
            if is_bull and entry_ret5 > 0 and ret5_live < -0.3:
                return True, (
                    f"momentum reversed: entry ret5 {entry_ret5:+.1f}% -> now {ret5_live:+.1f}%"
                )
            if not is_bull and entry_ret5 < 0 and ret5_live > 0.3:
                return True, (
                    f"momentum reversed: entry ret5 {entry_ret5:+.1f}% -> now {ret5_live:+.1f}%"
                )

    # ── 5. RSI extreme against trade ─────────────────────────────────────
    if ee.get("rsi_extreme_exit", True):
        if is_bull and rsi_live >= float(ee.get("rsi_call_ceiling", 78)):
            return True, f"RSI {rsi_live:.0f} hit overbought extreme — reversal risk"
        if not is_bull and rsi_live <= float(ee.get("rsi_put_floor", 22)):
            return True, f"RSI {rsi_live:.0f} hit oversold extreme — reversal risk"

    return False, ""


def _generate_trade_strategy(
    trade_type: str,
    direction_score: float,
    quality_score: float,
    iv_rank: float,
    rsi14: float,
    spy_ret5: float,
    est_premium: float,
    stop_loss_pct: float,
    profit_target_pct: float,
    stock_price: float,
    delta_est: float,
) -> dict:
    """
    Generate an adaptive TP/SL strategy for a single pick.

    Returns:
      sl_option_px   : option price at stop loss
      tp_option_px   : option price at take profit
      stock_sl       : underlying price where stop triggers
      stock_tp       : underlying price where target triggers
      label          : short table label (≤ 20 chars)
      comment        : 1-sentence strategy note
    """
    is_bullish   = (trade_type == "call")
    sl_option_px = round(est_premium * (1 - stop_loss_pct   / 100), 3)
    tp_option_px = round(est_premium * (1 + profit_target_pct / 100), 3)

    # Approximate underlying move needed to hit TP or SL via delta
    d = max(delta_est, 0.05)
    stock_move_to_tp = (est_premium * profit_target_pct / 100) / d
    stock_move_to_sl = (est_premium * stop_loss_pct    / 100) / d
    if is_bullish:
        stock_tp = round(stock_price + stock_move_to_tp, 2)
        stock_sl = round(stock_price - stock_move_to_sl, 2)
    else:
        stock_tp = round(stock_price - stock_move_to_tp, 2)
        stock_sl = round(stock_price + stock_move_to_sl, 2)

    spy_aligned = (is_bullish and spy_ret5 > 0) or (not is_bullish and spy_ret5 < 0)
    rsi_extreme = (is_bullish and rsi14 > 68) or (not is_bullish and rsi14 < 32)

    # Priority-ordered rule set — first match wins
    if rsi_extreme:
        label   = "⚠ RSI caution"
        comment = (
            f"RSI at {'overbought' if is_bullish else 'oversold'} extreme ({rsi14:.0f}) — "
            "mean-reversion risk is elevated. Exit immediately if momentum stalls; don't hold into expiry."
        )
    elif not spy_aligned and abs(spy_ret5) >= 1.5:
        label   = "⚠ Regime risk"
        comment = (
            f"SPY is moving {'up' if spy_ret5 > 0 else 'down'} {abs(spy_ret5):.1f}% while this trade fades "
            "the market. Reduce to 60% of normal size and take profit at 50–60% of target if reached."
        )
    elif iv_rank >= 65:
        label   = "Exit early"
        comment = (
            f"IV at {iv_rank:.0f}th percentile — options are expensive and IV crush can erode gains "
            "even on a winning move. Target 50–60% of full profit and exit before last 2 days."
        )
    elif direction_score >= 78 and quality_score >= 65 and spy_aligned:
        label   = "Hold to target"
        comment = (
            "High-conviction setup with market regime aligned. Hold to the full profit target; "
            "if the option doubles early, consider activating a trailing stop at 80% of peak value."
        )
    elif direction_score >= 65 and iv_rank <= 20:
        label   = "Let it breathe"
        comment = (
            f"IV very low ({iv_rank:.0f}th pct) — premium is cheap so theta decay is slow. "
            "Hold to the full target without rushing; the trade has time on its side."
        )
    elif direction_score < 60:
        label   = "Lighter size"
        comment = (
            "Direction signal is moderate. Consider half normal size; take profit at 60% of target "
            "and do not average in if the trade moves against you early."
        )
    else:
        label   = "Standard"
        comment = "Follow stop and target as set. No unusual risk factors detected."

    return {
        "sl_option_px": sl_option_px,
        "tp_option_px": tp_option_px,
        "stock_sl":     stock_sl,
        "stock_tp":     stock_tp,
        "label":        label,
        "comment":      comment,
    }

@_market_data_scoped
def scan_daily_top_trades(
    n_picks: int = DEFAULT_SCAN_PICKS,
    dte: int = None,
    min_confidence: float = None,
    min_tech_score: float = None,
    calibration_playbook: str = "broad",
) -> list:
    """
    Scan DEFAULT_WATCHLIST for the highest-confidence option setups right now.

    For each ticker:
      1. Fetch 90d price history
      2. Compute HV30, IV percentile, technical indicators
      3. Detect bullish (call) or bearish (put) momentum signal
      4. Score with the 4-component confidence formula
      5. Filter by min_confidence and positive EV

    Returns up to n_picks candidates sorted by confidence score descending.
    Each entry is a dict suitable for direct storage as a prediction record.
    """
    scan_target_dte = None if dte is None else max(DTE_MIN, min(DTE_MAX, int(dte)))

    min_confidence_override = min_confidence
    min_tech_score_override = min_tech_score
    # Entry gates from STRATEGY_PROFILE — overridable by caller for testing
    candidates: list[dict] = []

    # Fetch SPY regime data once for all tickers
    _spy_ret5 = 0.0
    try:
        _spy_hist = _cached_history("SPY", period="10d")["Close"].dropna()
        if len(_spy_hist) >= 6:
            _spy_ret5 = float((_spy_hist.iloc[-1] / _spy_hist.iloc[-6] - 1) * 100)
    except Exception:
        pass
    expectancy_surface = _load_expectancy_surface_for_live(playbook=calibration_playbook)
    market_regime_bucket = normalized_market_regime(spy_ret5=_spy_ret5)
    market_open = _market_is_open()

    for ticker in DEFAULT_WATCHLIST:
        _ac = _asset_class(ticker)
        sp  = _get_profile(ticker)
        ticker_min_confidence = (
            float(sp["entry"].get("min_direction_score", 35.0))
            if min_confidence_override is None else float(min_confidence_override)
        )
        ticker_min_tech_score = (
            float(sp["entry"].get("min_tech_score", 55.0))
            if min_tech_score_override is None else float(min_tech_score_override)
        )
        try:
            hist_frame = _cached_history(ticker, period="400d")
            liquidity_snapshot = _underlying_liquidity_snapshot(hist_frame)
            if not liquidity_snapshot["eligible"]:
                continue

            hist = hist_frame["Close"].dropna().tail(90)
            if len(hist) < 55:
                continue
            prices = hist.values.astype(float)
            n      = len(prices)
            signal_idx = n - 2 if market_open and n >= 2 else n - 1
            if signal_idx < 50:
                continue
            price  = float(prices[signal_idx])
            _entry_stock_price = price

            # Sector fetch — equity only
            if _ac == "equity":
                try:
                    _sector = _cached_ticker_info(ticker).get("sector")
                except Exception:
                    _sector = None
            else:
                _sector = None

            # HV30
            log_rets = np.log(prices[1:] / prices[:-1])
            hv30 = float(np.std(log_rets[signal_idx - 30 : signal_idx]) * math.sqrt(252))
            if hv30 <= 0:
                continue

            # IV percentile (rank of today's hv30 vs 90-day rolling hv30 history)
            hv_hist = []
            for i in range(30, signal_idx + 1):
                hv_i = float(np.std(log_rets[max(0, i - 30) : i]) * math.sqrt(252))
                if hv_i > 0:
                    hv_hist.append(hv_i)
            iv_pct = float(np.sum(np.array(hv_hist) <= hv30) / max(len(hv_hist), 1) * 100) if hv_hist else 50.0

            # Momentum signal (same logic as backtest)
            ret5  = (price / float(prices[signal_idx - 5]) - 1) * 100
            sma20 = float(np.mean(prices[signal_idx - 20 : signal_idx]))
            sma50 = float(np.mean(prices[signal_idx - 50 : signal_idx]))

            _mom_thr = float(sp.get("entry", {}).get("entry_momentum_pct", 0.5))
            bullish = ret5 >  _mom_thr and price > sma20
            bearish = ret5 < -_mom_thr and price < sma20
            if not bullish and not bearish:
                continue
            trade_type = "call" if bullish else "put"

            # Technical setup score — gate early to avoid expensive strike search on weak setups
            tech, _rsi14_live, _ret5_live = _compute_tech_score_live(ticker, trade_type)
            rsi14 = _rsi14_live
            ret5 = _ret5_live
            if tech < ticker_min_tech_score:
                continue

            ticker_target_dte = (
                max(DTE_MIN, min(DTE_MAX, int(sp["targets"].get("dte_optimal", 10))))
                if scan_target_dte is None else scan_target_dte
            )

            # ── Earnings gate: skip if earnings fall within the DTE window ──────
            if _ac == "equity":
                _earnings_skip = False
                try:
                    _ed = _cached_earnings_dates(ticker)
                    if _ed is not None and not _ed.empty:
                        _today_dt = datetime.now().replace(tzinfo=None)
                        _future_ed = _ed[_ed.index.tz_localize(None) >= _today_dt] if _ed.index.tzinfo else _ed[_ed.index >= _today_dt]
                        if not _future_ed.empty:
                            _next_earn = _future_ed.sort_index().index[0].to_pydatetime().replace(tzinfo=None)
                            _days_to_earn = (_next_earn - _today_dt).days
                            if 0 <= _days_to_earn <= ticker_target_dte:
                                _earnings_skip = True  # earnings inside our hold window → skip
                except Exception:
                    _earnings_skip = True
                if _earnings_skip:
                    continue

            # ── Fetch real options chain: actual strike + bid/ask (or lastPrice) ─
            _opt = _fetch_best_option(
                ticker,
                trade_type,
                float(sp["targets"]["delta_optimal"]),
                ticker_target_dte,
                stock_price=_entry_stock_price,
                hv30_fallback=hv30,
            )
            if _opt is None:
                continue

            best_strike = _opt["strike"]
            est_premium = _opt["premium"]
            delta_val   = _opt["delta"]
            actual_exp  = _opt["expiry"]
            actual_dte  = _opt["dte"]

            # Liquidity gate — same as brain (skip if bid/ask spread too wide)
            _liq = _check_trade_liquidity(
                _opt.get("bid"),
                _opt.get("ask"),
                contract_volume=_opt.get("volume"),
                open_interest=_opt.get("open_interest"),
                quote_age_hours=_opt.get("quote_age_hours"),
                sp=sp,
            )
            if _liq["is_illiquid"]:
                continue

            # Direction Score: predicts if stock moves the right way (this is the headline)
            direction_score = _compute_direction_score(tech, trade_type, rsi14, ret5, _spy_ret5, sp=sp)

            # IV crush check — same as brain (penalise if strike IV >> HV distribution)
            try:
                _skew = _calculate_iv_skew(ticker, best_strike, trade_type, actual_exp or "", sp=sp)
                _iv_pen = _skew["iv_crush_penalty_pts"]
                if _iv_pen > 0:
                    direction_score = max(0.0, direction_score - _iv_pen)
            except Exception:
                pass

            if direction_score < ticker_min_confidence:
                continue

            # Per-ticker profile values
            _stop_loss_pct     = float(sp["risk"]["stop_loss_pct"])
            _profit_target_pct = float(sp["risk"]["profit_target_pct"])
            _min_empirical_ev  = float(sp["filters"].get("min_calibrated_expectancy_pct", 0.0))

            # Market regime — ATR stop widening + defense mode (same as brain)
            try:
                _regime = _get_market_regime(ticker, sp=sp)
                _adj_stop_pct  = round(_stop_loss_pct * _regime["stop_loss_mult"], 1)
                _adj_size_mult = _regime["position_size_mult"]
            except Exception:
                _adj_stop_pct  = _stop_loss_pct
                _adj_size_mult = 1.0

            # Quality Score: rates the option to buy if direction is right
            quality_score = _compute_quality_score(iv_pct, delta_val, actual_dte, sp=sp)

            calibration_lookup = lookup_calibrated_expectancy(
                expectancy_surface,
                direction_score=direction_score,
                quality_score=quality_score,
                market_regime=market_regime_bucket,
                trade_type=trade_type,
                tech_score=tech,
                require_positive=True,
                allow_overall=False,
            )
            calibration = (
                calibration_lookup
                if calibration_lookup is not None and bool(calibration_lookup.get("dense_cohort"))
                else None
            )
            ev_pct = float(calibration.get("avg_pnl_pct")) if calibration else None
            if ev_pct is not None and ev_pct < _min_empirical_ev:
                continue

            # Build human-readable signal reasons
            reasons: list[str] = []
            if bullish:
                if price > sma20:  reasons.append(f"Price ${price:.0f} above SMA20 ${sma20:.0f}")
                if sma20 > sma50:  reasons.append("SMA20 above SMA50 — uptrend confirmed")
                reasons.append(f"+{ret5:.1f}% 5-day momentum")
            else:
                if price < sma20:  reasons.append(f"Price ${price:.0f} below SMA20 ${sma20:.0f}")
                if sma20 < sma50:  reasons.append("SMA20 below SMA50 — downtrend confirmed")
                reasons.append(f"{ret5:.1f}% 5-day momentum")
            if iv_pct < 30:
                reasons.append(f"Low IV rank ({iv_pct:.0f}th pct) — relatively cheap options")
            elif iv_pct > 70:
                reasons.append(f"High IV rank ({iv_pct:.0f}th pct) — options are expensive, consider smaller size")

            # Regime alignment reason
            if abs(_spy_ret5) >= 0.5:
                spy_dir = "rising" if _spy_ret5 > 0 else "falling"
                aligned = (bullish and _spy_ret5 > 0) or (bearish and _spy_ret5 < 0)
                reasons.append(f"SPY {spy_dir} {_spy_ret5:+.1f}% (regime {'aligned ✓' if aligned else 'opposing ✗'})")

            today_str   = datetime.now(_ET).strftime("%Y-%m-%d %H:%M ET")
            _at_open    = not _market_is_open()   # pick made outside market hours
            # Use the actual option expiry date when available; otherwise estimate
            if actual_exp:
                target_str = actual_exp
            else:
                _raw_target = datetime.now() + timedelta(days=actual_dte + 2)
                while _raw_target.weekday() >= 5:
                    _raw_target += timedelta(days=1)
                target_str = _raw_target.strftime("%Y-%m-%d")

            strategy = _generate_trade_strategy(
                trade_type=trade_type,
                direction_score=direction_score,
                quality_score=quality_score,
                iv_rank=iv_pct,
                rsi14=rsi14,
                spy_ret5=_spy_ret5,
                est_premium=est_premium,
                stop_loss_pct=_adj_stop_pct,   # ATR-widened stop if volatility expanding
                profit_target_pct=_profit_target_pct,
                stock_price=_entry_stock_price,
                delta_est=delta_val,
            )
            target_move_pct = round(abs((strategy["stock_tp"] / _entry_stock_price - 1) * 100), 2) if _entry_stock_price else None

            contract_selection_source = _live_contract_selection_source(_opt)
            has_exact_contract = contract_selection_source == "live_chain_exact_contract"
            promotion_class = _live_pick_promotion_class(
                has_exact_contract=has_exact_contract,
                calibration_lookup=calibration_lookup,
                dense_calibration=calibration,
            )

            candidates.append({
                "ticker":             ticker,
                "direction":          trade_type,
                "option_type":        trade_type,
                "direction_score":    round(direction_score, 1),
                "quality_score":      round(quality_score, 1),
                "tech_score":         round(tech, 1),
                "iv_rank":            round(iv_pct, 1),
                "iv_percentile":      round(iv_pct, 1),
                "iv_pct":             round(iv_pct, 1),
                "delta_est":          round(delta_val, 2),
                "delta":              round(float(_opt.get("delta") or delta_val), 3),
                "stock_price":        round(_entry_stock_price, 2),
                "underlying_price_at_selection": round(_entry_stock_price, 2),
                "strike_est":         best_strike,   # real market strike — no rounding
                "strike":             best_strike,
                "expiry":             actual_exp or target_str,
                "contract_symbol":    _opt.get("contract_symbol"),
                "live_chain":         actual_exp is not None,  # True = real bid/ask, False = BS estimate
                "dte":                actual_dte,
                "bid":                _opt.get("bid"),
                "ask":                _opt.get("ask"),
                "mid":                round(est_premium, 4),
                "est_premium":        round(est_premium, 4),
                "stop_loss_pct":      _adj_stop_pct,    # ATR-adjusted (may be wider than base)
                "profit_target_pct":  _profit_target_pct,
                "atr_stop_widened":   _adj_stop_pct != _stop_loss_pct,
                "ev_pct":             round(ev_pct, 1) if ev_pct is not None else None,
                "calibrated_expectancy_pct": round(ev_pct, 2) if ev_pct is not None else None,
                "calibration_source": calibration_lookup.get("lookup_source") if calibration_lookup else None,
                "calibration_trades": calibration_lookup.get("trades") if calibration_lookup else None,
                "calibration_raw_expectancy_pct": calibration_lookup.get("avg_pnl_pct_raw") if calibration_lookup else None,
                "calibration_parent_expectancy_pct": calibration_lookup.get("parent_avg_pnl_pct") if calibration_lookup else None,
                "calibration_used_parent_shrinkage": calibration_lookup.get("used_parent_shrinkage") if calibration_lookup else None,
                "calibration_sparse_warning": calibration_lookup.get("sparse_warning") if calibration_lookup else None,
                "calibration_density": calibration_lookup.get("calibration_density") if calibration_lookup else None,
                "calibration_is_dense": bool(calibration_lookup.get("dense_cohort")) if calibration_lookup else False,
                "surface_provenance": calibration_lookup.get("surface_provenance") if calibration_lookup else None,
                "ret5":               round(ret5, 2),
                "rsi14":              round(rsi14, 1),
                "spy_ret5":           round(_spy_ret5, 2),
                "entry_date":         today_str,
                "quote_time_et":      today_str,
                "quote_basis":        _opt.get("quote_basis"),
                "options_snapshot_status": _opt.get("options_snapshot_status"),
                "option_chain_status": _opt.get("option_chain_status"),
                "selection_source":   contract_selection_source,
                "contract_selection_source": contract_selection_source,
                "promotion_class":    promotion_class,
                "promotable":         promotion_class == "promotable_exact_contract",
                "target_date":        target_str,
                "entry_price":        round(_entry_stock_price, 2),   # prev day's close (last complete candle)
                "entry_at_open":      _at_open,          # True = market was closed, use next-open price
                "entry_open_price":   None,               # filled on first grade after market opens
                "target_move_pct":    target_move_pct,
                "signal_reasons":     reasons,
                "strategy_label":     strategy["label"],
                "strategy_comment":   strategy["comment"],
                "sl_option_px":       strategy["sl_option_px"],
                "tp_option_px":       strategy["tp_option_px"],
                "stock_sl":           strategy["stock_sl"],
                "stock_tp":           strategy["stock_tp"],
                "time_exit_pct":      float(sp["risk"].get("time_exit_pct", 50.0)),
                "time_exit_day":      max(1, math.ceil(actual_dte * float(sp["risk"].get("time_exit_pct", 50.0)) / 100)),
                "type":               "daily_scan",
                "outcome":            None,
                "asset_class":        _ac,
                "sector":             _sector,
                "avg_volume_20d":     liquidity_snapshot["avg_volume_20d"],
                "avg_dollar_volume_20d": liquidity_snapshot["avg_dollar_volume_20d"],
                "underlying_liquidity_tier": liquidity_snapshot["liquidity_tier"],
                "history_days":       liquidity_snapshot["history_days"],
                "contract_volume":    _opt.get("volume"),
                "contract_open_interest": _opt.get("open_interest"),
                "quote_age_hours":    _opt.get("quote_age_hours"),
            })
        except Exception:
            continue

    candidates.sort(key=_candidate_rank_tuple, reverse=True)

    # ── Sector concentration: equity picks — max 2 from same sector ───────────
    _sector_counts: dict[str, int] = {}
    _accepted: list[dict] = []
    _overflow: list[dict] = []
    for _c in candidates:
        if len(_accepted) >= n_picks:
            _overflow.append(_c)
            continue
        if _c.get("asset_class") == "index":
            _accepted.append(_c)
        else:
            _sec = _c.get("sector") or "Unknown"
            if _sector_counts.get(_sec, 0) < 2:
                _accepted.append(_c)
                _sector_counts[_sec] = _sector_counts.get(_sec, 0) + 1
            else:
                _overflow.append(_c)

    # Fill any remaining slots with overflow picks (respecting sector rule)
    for _c in _overflow:
        if len(_accepted) >= n_picks:
            break
        if _c.get("asset_class") == "equity":
            _sec = _c.get("sector") or "Unknown"
            if _sector_counts.get(_sec, 0) < 2:
                _accepted.append(_c)
                _sector_counts[_sec] = _sector_counts.get(_sec, 0) + 1

    return _accepted


def roll_forward_daily_picks(
    pending_picks: list,
    n_picks: int = DEFAULT_SCAN_PICKS,
    candidates: list[dict] | None = None,
) -> dict:
    """
    Re-score the full watchlist each morning and apply roll-forward logic.

    Rules:
    - Pending picks whose (ticker, direction) still ranks in the top n_picks
      are ROLLED: entry_price, est_premium, strike_est, expiry, id, and
      entry_date are preserved; scoring fields are refreshed from today's scan.
    - Freed slots are filled with NEW picks from the scored list.
    - If a new pick shares (ticker, strike_est, expiry) with a rolled pick,
      it is suppressed — the rolled version wins.

    Returns:
        {
            "rolled":   [...],  # picks kept with refreshed scores
            "new":      [...],  # brand-new picks filling open slots
            "dropped":  [...],  # picks that fell out of the top-n ranking
        }
    """
    today_str = datetime.now(_ET).strftime("%Y-%m-%d")

    # Score full watchlist — large n_picks so we see all qualifying candidates
    all_candidates = list(candidates) if candidates is not None else scan_daily_top_trades(n_picks=len(DEFAULT_WATCHLIST))

    # Determine which (ticker, direction) pairs sit in today's top-n
    top_n_keys  = {(c["ticker"], c["direction"]) for c in all_candidates[:n_picks]}
    cand_lookup = {(c["ticker"], c["direction"]): c for c in all_candidates}

    rolled:  list[dict] = []
    dropped: list[dict] = []

    for p in pending_picks:
        key = (p.get("ticker", ""), p.get("direction", ""))
        if key in top_n_keys:
            fresh   = cand_lookup[key]
            updated = dict(p)
            # Refresh scoring + signal fields; preserve entry anchor fields
            for _f in ("direction_score", "tech_score", "quality_score",
                       "iv_rank", "ret5", "rsi14", "spy_ret5", "ev_pct",
                       "calibrated_expectancy_pct", "calibration_source", "calibration_trades",
                       "signal_reasons", "strategy_label", "strategy_comment",
                       "selection_source", "contract_selection_source", "promotion_class",
                       "promotable", "options_snapshot_status", "option_chain_status",
                       "quote_basis", "quote_time_et", "contract_symbol"):
                if _f in fresh:
                    updated[_f] = fresh[_f]
            updated["pick_status"]      = "rolled"
            updated["roll_count"]       = p.get("roll_count", 0) + 1
            updated["last_rolled_date"] = today_str
            if "original_entry_date" not in updated:
                updated["original_entry_date"] = p.get("entry_date", today_str)
            rolled.append(updated)
        else:
            dropped.append(p)

    # Fill empty slots with new picks
    slots_needed   = n_picks - len(rolled)
    used_keys      = {(r["ticker"], r["direction"]) for r in rolled}
    rolled_anchors = {(r["ticker"], r.get("strike_est"), r.get("expiry")) for r in rolled}

    new_picks: list[dict] = []
    for c in all_candidates:
        if slots_needed <= 0:
            break
        key = (c["ticker"], c["direction"])
        if key in used_keys:
            continue
        # Suppress duplicate exposure (same ticker+strike+expiry already rolled)
        anchor = (c["ticker"], c.get("strike_est"), c.get("expiry"))
        if anchor in rolled_anchors:
            continue
        fresh_pick = dict(c)
        fresh_pick["pick_status"]         = "new"
        fresh_pick["roll_count"]          = 0
        fresh_pick["original_entry_date"] = fresh_pick["entry_date"]
        new_picks.append(fresh_pick)
        used_keys.add(key)
        slots_needed -= 1

    return {"rolled": rolled, "new": new_picks, "dropped": dropped}


def generate_position_recommendations(
    pending_picks: list,
    n_picks: int = DEFAULT_SCAN_PICKS,
    candidates: list[dict] | None = None,
) -> dict:
    """
    Re-score all pending picks against today's market data and produce
    HOLD / EXIT / REPLACE recommendations for each.

    If no pending picks exist, falls back to a plain scan_daily_top_trades().

    Returns:
        {
            "active_positions": [
                {**pick, "recommendation": "HOLD"|"EXIT"|"REPLACE",
                 "rec_reason": str, "fresh_direction_score": float,
                 "score_delta": float, "replace_with": dict|None},
            ],
            "new_opportunities": [...],
        }
    """
    # ── No pending picks → just do a fresh scan ──────────────────────────────
    if not pending_picks:
        fresh = list(candidates)[:n_picks] if candidates is not None else scan_daily_top_trades(n_picks=n_picks)
        for p in fresh:
            p["pick_status"] = "new"
            p["roll_count"] = 0
            p["original_entry_date"] = p.get("entry_date", "")
        return {"active_positions": [], "new_opportunities": fresh}

    # ── Full rescore of watchlist ─────────────────────────────────────────────
    all_candidates = list(candidates) if candidates is not None else scan_daily_top_trades(n_picks=len(DEFAULT_WATCHLIST))
    cand_lookup = {(c["ticker"], c["direction"]): c for c in all_candidates}

    # Thresholds
    SCORE_DROP_THRESHOLD = 15     # direction score drop > 15 pts → EXIT
    REPLACE_ADVANTAGE    = 10     # new candidate must beat old by 10+ pts
    SL_PROXIMITY_FACTOR  = 0.70   # within 70% of stop loss → EXIT

    active_positions: list[dict] = []
    hold_keys: set[tuple] = set()

    for p in pending_picks:
        key = (p.get("ticker", ""), p.get("direction", ""))
        rec = dict(p)
        fresh = cand_lookup.get(key)

        old_score = _candidate_signal_value(p)
        current_pnl = p.get("current_pnl_pct")
        stop_loss = float(p.get("stop_loss_pct", 50))

        # ── Determine recommendation ─────────────────────────────────────────
        if fresh is None:
            # Ticker no longer passes scan gates (momentum flipped, tech failed, etc.)
            rec["recommendation"] = "EXIT"
            rec["rec_reason"] = "No longer meets scan criteria — failed momentum, tech, or EV gates"
            rec["fresh_direction_score"] = None
            rec["score_delta"] = None
        else:
            fresh_score = _candidate_signal_value(fresh)
            delta = fresh_score - old_score
            rec["fresh_direction_score"] = round(fresh_score, 1)
            rec["score_delta"] = round(delta, 1)

            # Check stop loss proximity
            if current_pnl is not None and current_pnl <= -(stop_loss * SL_PROXIMITY_FACTOR):
                rec["recommendation"] = "EXIT"
                rec["rec_reason"] = (
                    f"Approaching stop loss — current P&L {current_pnl:+.1f}% "
                    f"(stop at -{stop_loss:.0f}%)"
                )
            elif delta < -SCORE_DROP_THRESHOLD:
                rec["recommendation"] = "EXIT"
                rec["rec_reason"] = (
                    f"Direction score degraded {old_score:.0f}% → {fresh_score:.0f}% "
                    f"({delta:+.0f} pts)"
                )
            else:
                # Still qualifies → HOLD; refresh scoring fields
                rec["recommendation"] = "HOLD"
                rec["rec_reason"] = f"Still ranks well — direction score {fresh_score:.0f}%"
                for _f in ("direction_score", "tech_score", "quality_score",
                           "iv_rank", "ret5", "rsi14", "spy_ret5", "ev_pct",
                           "signal_reasons", "strategy_label", "strategy_comment",
                           "selection_source", "contract_selection_source", "promotion_class",
                           "promotable", "options_snapshot_status", "option_chain_status",
                           "quote_basis", "quote_time_et", "contract_symbol",
                           "calibrated_expectancy_pct", "calibration_source", "calibration_trades"):
                    if _f in fresh:
                        rec[_f] = fresh[_f]
                hold_keys.add(key)

        rec["replace_with"] = None
        active_positions.append(rec)

    # ── For EXIT picks, check if a replacement is available ───────────────────
    for rec in active_positions:
        if rec["recommendation"] != "EXIT":
            continue
        old_score = _candidate_signal_value(rec)
        best_replacement = None
        best_adv = 0
        for c in all_candidates:
            ckey = (c["ticker"], c["direction"])
            if ckey in hold_keys:
                continue
            # Don't suggest a ticker that's already an active position
            if any(ckey == (a.get("ticker"), a.get("direction")) for a in active_positions):
                continue
            adv = _candidate_signal_value(c) - old_score
            if adv >= REPLACE_ADVANTAGE and adv > best_adv:
                best_replacement = c
                best_adv = adv
        if best_replacement:
            rec["recommendation"] = "REPLACE"
            rec["rec_reason"] += (
                f" — replace with {best_replacement['ticker']} "
                f"{best_replacement['direction'].upper()} "
                f"({_candidate_signal_value(best_replacement):+.1f})"
            )
            rec["replace_with"] = best_replacement

    # ── Fill remaining slots with new opportunities ───────────────────────────
    slots_available = max(0, n_picks - len([r for r in active_positions
                                             if r["recommendation"] == "HOLD"]))
    used_keys = {(r["ticker"], r["direction"]) for r in active_positions}
    new_opportunities: list[dict] = []
    for c in all_candidates:
        if slots_available <= 0:
            break
        ckey = (c["ticker"], c["direction"])
        if ckey in used_keys:
            continue
        # Skip if already suggested as a replacement
        if any(r.get("replace_with") and
               (r["replace_with"]["ticker"], r["replace_with"]["direction"]) == ckey
               for r in active_positions):
            continue
        fresh_pick = dict(c)
        fresh_pick["pick_status"] = "new"
        fresh_pick["roll_count"] = 0
        fresh_pick["original_entry_date"] = fresh_pick.get("entry_date", "")
        new_opportunities.append(fresh_pick)
        used_keys.add(ckey)
        slots_available -= 1

    return {
        "active_positions": active_positions,
        "new_opportunities": new_opportunities,
    }


def _check_trade_liquidity(
    bid: float,
    ask: float,
    *,
    contract_volume: int = None,
    open_interest: int = None,
    quote_age_hours: float = None,
    sp: dict = None,
) -> dict:
    """
    Bid-ask spread as % of mid-price.
    If spread > 1.5% flag as illiquid and require 10% extra profit margin.
    """
    if sp is None:
        sp = STRATEGY_PROFILE
    f = sp["filters"]
    if not bid or not ask or ask <= bid:
        return {
            "mid_price": None,
            "spread_pct": 999.0,
            "is_illiquid": True,
            "extra_margin_pct": f["illiquid_extra_margin_pct"],
            "contract_volume": contract_volume,
            "open_interest": open_interest,
            "quote_age_hours": quote_age_hours,
            "reasons": ["no_valid_bid_ask"],
            "flag": "No valid bid/ask",
        }
    mid = (bid + ask) / 2.0
    spread_pct = (ask - bid) / mid * 100.0
    reasons: list[str] = []
    if mid < float(f.get("min_option_mid_price", 0.30)):
        reasons.append("premium_too_low")
    if spread_pct > f["liquidity_spread_max_pct"]:
        reasons.append("wide_spread")
    if contract_volume is not None and int(contract_volume) < int(f.get("min_option_volume", 0)):
        reasons.append("low_contract_volume")
    if open_interest is not None and int(open_interest) < int(f.get("min_option_open_interest", 0)):
        reasons.append("low_open_interest")
    if quote_age_hours is not None and float(quote_age_hours) > float(f.get("max_option_quote_age_hours", 9999.0)):
        reasons.append("stale_quote")
    illiquid = bool(reasons)
    return {
        "mid_price":       round(mid, 4),
        "spread_pct":      round(spread_pct, 2),
        "is_illiquid":     illiquid,
        "contract_volume": contract_volume,
        "open_interest":   open_interest,
        "quote_age_hours": round(float(quote_age_hours), 2) if quote_age_hours is not None else None,
        "reasons":         reasons,
        "extra_margin_pct": f["illiquid_extra_margin_pct"] if illiquid else 0.0,
        "flag": (
            f"Contract blocked: {', '.join(reasons)}"
            if illiquid else f"Liquid contract — spread {spread_pct:.1f}%"
        ),
    }


def _get_market_regime(symbol: str, sp: dict = None) -> dict:
    """
    VIX + ATR regime detector.
    VIX > 25 → Defense Mode (50% position sizes).
    ATR expanding (14d > 28d avg by 5%) → stop-loss ×1.5.
    """
    if sp is None:
        sp = _get_profile(symbol)
    # VIX
    try:
        vix = float(_cached_history("^VIX", period="5d")["Close"].iloc[-1])
    except Exception:
        vix = 20.0

    # ATR (14-day vs 28-day to detect expansion)
    atr_14 = atr_28 = 0.0
    atr_expanding = False
    try:
        hist = _cached_history(symbol, period="45d")
        hi, lo, cl = hist["High"].values, hist["Low"].values, hist["Close"].values
        trs = [max(hi[i] - lo[i], abs(hi[i] - cl[i-1]), abs(lo[i] - cl[i-1]))
               for i in range(1, len(cl))]
        if len(trs) >= 28:
            atr_14 = float(np.mean(trs[-14:]))
            atr_28 = float(np.mean(trs[-28:]))
            atr_expanding = atr_14 > atr_28 * 1.05
        elif len(trs) >= 14:
            atr_14 = atr_28 = float(np.mean(trs[-14:]))
    except Exception:
        pass

    defense = vix > sp["filters"]["vix_defense_threshold"]
    stop_mult = sp["filters"]["atr_expansion_stop_mult"] if atr_expanding else 1.0
    pos_mult  = sp["filters"]["defense_position_mult"] if defense else 1.0

    notes = []
    if defense:
        notes.append(f"VIX {vix:.0f} > {sp['filters']['vix_defense_threshold']:.0f} → Defense Mode: position sizes halved")
    if atr_expanding:
        notes.append(f"ATR expanding ({atr_14:.3f} > {atr_28:.3f}) → stop-loss widened to {stop_mult:.1f}×")

    return {
        "vix":                    round(vix, 2),
        "atr_14d":                round(atr_14, 4),
        "atr_28d":                round(atr_28, 4),
        "atr_expanding":          atr_expanding,
        "defense_mode":           defense,
        "regime":                 "⚠️ DEFENSE" if defense else "✅ NORMAL",
        "position_size_mult":     pos_mult,
        "stop_loss_mult":         round(stop_mult, 1),
        "regime_notes":           notes if notes else ["Normal market conditions"],
    }


def _calculate_iv_skew(symbol: str, target_strike: float, option_type: str, expiry: str, sp: dict = None) -> dict:
    """
    Vertical skew: (OTM IV − ATM IV) / ATM IV for the target strike.
    Time skew: near-term ATM IV minus next-expiry ATM IV.
    IV crush check: if target IV > HV30_mean + 2σ, apply confidence penalty.
    """
    symbol_name = str(symbol)
    if sp is None:
        sp = _get_profile(symbol_name)
    spot = None
    atm_iv = target_iv = None
    vertical_skew = 0.0
    near_iv = far_iv = None
    time_skew = 0.0
    z_score = 0.0
    hv_mean = hv_std = None
    iv_crush_penalty = 0.0
    iv_crush_warning = ""

    # Get spot price
    try:
        spot = float(_cached_history(symbol_name, period="2d")["Close"].iloc[-1])
    except Exception:
        pass

    # Vertical skew from target expiry
    if spot is not None:
        try:
            chain = _cached_option_chain(symbol_name, expiry)
            opts = chain.calls if option_type.lower() == "call" else chain.puts
            opts = opts[opts["impliedVolatility"] > 0]

            atm_row = opts.iloc[(opts["strike"] - spot).abs().argsort()[:1]]
            tgt_row = opts.iloc[(opts["strike"] - target_strike).abs().argsort()[:1]]

            atm_iv    = round(float(atm_row["impliedVolatility"].values[0]) * 100, 2)
            target_iv = round(float(tgt_row["impliedVolatility"].values[0]) * 100, 2)
            vertical_skew = (target_iv - atm_iv) / atm_iv if atm_iv else 0.0
        except Exception:
            pass

    # Time skew: compare near vs next expiry ATM IV
    if spot is not None:
        try:
            exps = _cached_options(symbol_name)
            if len(exps) >= 2:
                def _atm_iv(exp):
                    c = _cached_option_chain(symbol_name, exp)
                    o = c.calls if option_type.lower() == "call" else c.puts
                    o = o[o["impliedVolatility"] > 0]
                    r = o.iloc[(o["strike"] - spot).abs().argsort()[:1]]
                    return round(float(r["impliedVolatility"].values[0]) * 100, 2)
                near_iv = _atm_iv(exps[0])
                far_iv  = _atm_iv(exps[1])
                time_skew = near_iv - far_iv
        except Exception:
            pass

    # IV crush check: compare target IV to 30-day HV rolling distribution
    if target_iv is not None:
        try:
            hist90 = _cached_history(symbol_name, period="120d")
            log_rets = np.log(hist90["Close"] / hist90["Close"].shift(1)).dropna().values
            windows = [float(np.std(log_rets[i-30:i]) * math.sqrt(252) * 100)
                       for i in range(30, len(log_rets))]
            if windows:
                hv_mean = float(np.mean(windows))
                hv_std  = float(np.std(windows))
                z_score = (target_iv - hv_mean) / hv_std if hv_std > 0 else 0.0
                thresh  = sp["filters"]["iv_crush_z_threshold"]
                if z_score >= thresh:
                    iv_crush_penalty = sp["filters"]["iv_crush_confidence_penalty"]
                    iv_crush_warning = (
                        f"⚠️ IV CRUSH RISK: strike IV {target_iv:.1f}% is "
                        f"{z_score:.1f}σ above 30-day HV mean ({hv_mean:.1f}%) "
                        f"→ confidence reduced by {iv_crush_penalty:.0f} points"
                    )
        except Exception:
            pass

    v_note = (
        "OTM priced rich vs ATM"   if vertical_skew >  0.10 else
        "OTM priced cheap vs ATM"  if vertical_skew < -0.05 else
        "Normal vertical skew"
    )
    t_note = (
        "Near-term premium elevated"  if time_skew >  5 else
        "Near-term premium depressed" if time_skew < -3 else
        "Normal time structure"
    )

    return {
        "atm_iv":               atm_iv,
        "target_strike_iv":     target_iv,
        "vertical_skew_pct":    round(vertical_skew * 100, 2),
        "vertical_skew_note":   v_note,
        "near_expiry_atm_iv":   near_iv,
        "next_expiry_atm_iv":   far_iv,
        "time_skew":            round(time_skew, 2) if near_iv and far_iv else None,
        "time_skew_note":       t_note,
        "iv_zscore_vs_hv30":    round(z_score, 2),
        "hv30_mean":            round(hv_mean, 2) if hv_mean else None,
        "hv30_std":             round(hv_std,  2) if hv_std  else None,
        "iv_crush_penalty_pts": iv_crush_penalty,
        "iv_crush_warning":     iv_crush_warning,
    }


def _calculate_ev(delta: float, avg_win_pct: float, avg_loss_pct: float,
                  capital_at_risk: float, extra_margin_pct: float = 0.0,
                  confidence: float = None, sp: dict = None,
                  empirical_expectancy_pct: float = None,
                  empirical_win_rate_pct: float = None,
                  required_ev_floor_pct: float = None,
                  ev_source: str = "heuristic") -> dict:
    """
    EV = (P_profit × avg_win) − (P_loss × avg_loss)
    Uses confidence score (0–100) as P(profit) when available; falls back to
    |delta| only if confidence is not supplied.
    Trade signal fires only when EV ≥ min_ev_return_pct (10%) AND EV > 0.
    Extra margin requirement raised if option is illiquid.
    """
    if sp is None:
        sp = STRATEGY_PROFILE
    if empirical_expectancy_pct is not None:
        p_win = min(max((empirical_win_rate_pct or 0.0) / 100.0, 0.01), 0.99)
        ev_pct = float(empirical_expectancy_pct)
        threshold = (
            float(required_ev_floor_pct)
            if required_ev_floor_pct is not None
            else float(sp["filters"].get("min_calibrated_expectancy_pct", 0.0))
        ) + extra_margin_pct
    elif confidence is not None:
        p_win = min(max(confidence / 100.0, 0.01), 0.99)
        threshold = sp["filters"]["min_ev_return_pct"] + extra_margin_pct
        ev_pct = (p_win * avg_win_pct) - ((1.0 - p_win) * abs(avg_loss_pct))
    else:
        p_win = min(abs(delta), 0.99)
        threshold = sp["filters"]["min_ev_return_pct"] + extra_margin_pct
        ev_pct = (p_win * avg_win_pct) - ((1.0 - p_win) * abs(avg_loss_pct))
    p_loss = 1.0 - p_win
    ev_dollars = capital_at_risk * ev_pct / 100.0
    signal = ev_pct > 0 and ev_pct >= threshold
    return {
        "source":             ev_source,
        "p_profit":           round(p_win, 3),
        "p_loss":             round(p_loss, 3),
        "avg_win_pct":        avg_win_pct,
        "avg_loss_pct":       avg_loss_pct,
        "ev_pct":             round(ev_pct, 2),
        "ev_dollars":         round(ev_dollars, 2),
        "required_ev_pct":    round(threshold, 1),
        "trade_signal":       signal,
        "ev_note": (
            f"✅ EV {ev_pct:.1f}% ≥ {threshold:.0f}% required" if signal
            else f"❌ EV {ev_pct:.1f}% < {threshold:.0f}% required"
        ),
    }

@_market_data_scoped
def evaluate_trade_signal(
    symbol: str,
    option_type: str,
    strike: float,
    expiry: str,
    bid: float = None,
    ask: float = None,
    contract_volume: int = None,
    open_interest: int = None,
    quote_age_hours: float = None,
    delta: float = None,
    iv_percentile: float = None,
    dte: int = None,
    position_dollars: float = 1000.0,
    avg_win_pct: float = 80.0,
    avg_loss_pct: float = 40.0,
) -> str:
    """
    Master trade evaluator — runs every strategy filter and returns a unified signal.

    Combines:
      1. Confidence score (IV rank, Delta, DTE, Technical setup — weights optimizer-tuned)
      2. IV vertical + time skew; IV crush penalty if OTM IV > HV mean + 2σ
      3. Liquidity check — blocks missing/two-sided quotes and flags illiquid spreads, volume, OI, and stale chains
      4. Market regime — VIX + ATR expansion (Defense Mode, stop-loss widening)
      5. EV formula — (P_win × avg_win) − (P_loss × avg_loss) using delta as P_win proxy
    """
    try:
        _eval_sp = _get_profile(symbol)
        out: dict = {
            "symbol":      symbol.upper(),
            "option_type": option_type,
            "strike":      strike,
            "expiry":      expiry,
        }
        direction_score = None
        quality_score = None
        spy_ret5 = 0.0
        market_regime_bucket = None
        calibration = None
        expectancy_surface = _load_expectancy_surface_for_live()

        # ── 1. Direction Score + Quality Score (replaces single confidence) ──────
        confidence_score = None
        if iv_percentile is not None and delta is not None and dte is not None:
            tech, rsi14_live, ret5_live = _compute_tech_score_live(symbol, option_type)

            # Fetch SPY 5-day return for regime alignment
            try:
                _spy_hist = _cached_history("SPY", period="10d")["Close"].dropna()
                spy_ret5 = float(_spy_hist.iloc[-1] / _spy_hist.iloc[-6] - 1) * 100 if len(_spy_hist) >= 6 else 0.0
            except Exception:
                spy_ret5 = 0.0

            direction_score = _compute_direction_score(tech, option_type, rsi14_live, ret5_live, spy_ret5, sp=_eval_sp)
            quality_score   = _compute_quality_score(iv_percentile, abs(delta), dte, sp=_eval_sp)
            market_regime_bucket = normalized_market_regime(spy_ret5=spy_ret5)

            # Use direction score as the headline for PROCEED/AVOID gating
            confidence_score = direction_score
            out["confidence"] = {
                "direction_score":  round(direction_score, 1),
                "quality_score":    round(quality_score, 1),
                "tech_score":       round(tech, 1),
                "rsi14":            round(rsi14_live, 1),
                "spy_5d_ret":       round(spy_ret5, 2),
                "iv_percentile":    iv_percentile,
                "delta":            delta,
                "dte":              dte,
            }

        # ── 2. IV skew + crush check ──────────────────────────────────────────
        iv_crush_penalty = 0.0
        skew = _calculate_iv_skew(symbol, strike, option_type, expiry, sp=_eval_sp)
        out["iv_skew"] = skew
        iv_crush_penalty = skew["iv_crush_penalty_pts"]
        if confidence_score is not None and iv_crush_penalty > 0:
            adjusted = max(0.0, confidence_score - iv_crush_penalty)
            out["confidence"]["direction_score_adj"] = round(adjusted, 1)
            out["confidence"]["iv_crush_penalty"]    = -iv_crush_penalty
            confidence_score = adjusted
        if confidence_score is not None and quality_score is not None:
            calibration_lookup = lookup_calibrated_expectancy(
                expectancy_surface,
                direction_score=confidence_score,
                quality_score=quality_score,
                market_regime=market_regime_bucket,
                trade_type=option_type,
                tech_score=tech,
                require_positive=True,
                allow_overall=False,
            )
            calibration = (
                calibration_lookup
                if calibration_lookup is not None and bool(calibration_lookup.get("dense_cohort"))
                else None
            )
            out["confidence"]["market_regime_bucket"] = market_regime_bucket
            out["confidence"]["calibrated_expectancy_pct"] = (
                round(float(calibration.get("avg_pnl_pct", 0.0) or 0.0), 2)
                if calibration else None
            )
            out["confidence"]["calibration_source"] = calibration_lookup.get("lookup_source") if calibration_lookup else None
            out["confidence"]["calibration_trades"] = calibration_lookup.get("trades") if calibration_lookup else 0
            out["confidence"]["calibration_raw_expectancy_pct"] = (
                round(float(calibration_lookup.get("avg_pnl_pct_raw", 0.0) or 0.0), 2)
                if calibration_lookup else None
            )
            out["confidence"]["calibration_parent_expectancy_pct"] = (
                round(float(calibration_lookup.get("parent_avg_pnl_pct", 0.0) or 0.0), 2)
                if calibration_lookup and calibration_lookup.get("parent_avg_pnl_pct") is not None else None
            )
            out["confidence"]["calibration_used_parent_shrinkage"] = (
                bool(calibration_lookup.get("used_parent_shrinkage")) if calibration_lookup else None
            )
            out["confidence"]["calibration_sparse_warning"] = (
                calibration_lookup.get("sparse_warning") if calibration_lookup else None
            )
            out["confidence"]["calibration_density"] = (
                calibration_lookup.get("calibration_density") if calibration_lookup else None
            )
            out["confidence"]["surface_provenance"] = (
                calibration_lookup.get("surface_provenance") if calibration_lookup else None
            )

        # ── 3. Liquidity check ────────────────────────────────────────────────
        extra_margin = 0.0
        liq = _check_trade_liquidity(
            bid,
            ask,
            contract_volume=contract_volume,
            open_interest=open_interest,
            quote_age_hours=quote_age_hours,
            sp=_eval_sp,
        )
        extra_margin = liq["extra_margin_pct"]
        out["liquidity"] = liq

        # ── 4. Market regime ──────────────────────────────────────────────────
        regime = _get_market_regime(symbol, sp=_eval_sp)
        out["market_regime"] = regime

        base_stop   = float(_eval_sp["risk"]["stop_loss_pct"])
        adj_stop    = round(base_stop * regime["stop_loss_mult"], 1)
        adj_dollars = round(position_dollars * regime["position_size_mult"], 2)
        out["adjusted_parameters"] = {
            "position_dollars":  adj_dollars,
            "stop_loss_pct":     adj_stop,
            "profit_target_pct": float(_eval_sp["risk"]["profit_target_pct"]),
            "regime_notes":      regime["regime_notes"],
        }

        # ── 5. EV calculation ─────────────────────────────────────────────────
        ev_signal = False
        if delta is not None:
            if expectancy_surface is not None and calibration is None:
                ev = {
                    "source": "replay_calibrated_unavailable",
                    "p_profit": None,
                    "p_loss": None,
                    "avg_win_pct": avg_win_pct,
                    "avg_loss_pct": avg_loss_pct,
                    "ev_pct": None,
                    "ev_dollars": None,
                    "required_ev_pct": round(float(_eval_sp["filters"].get("min_calibrated_expectancy_pct", 0.0)), 1),
                    "trade_signal": False,
                    "ev_note": "âŒ No dense positive replay-backed expectancy is available for this score/regime bucket.",
                }
            else:
                ev = _calculate_ev(
                    delta,
                    avg_win_pct,
                    avg_loss_pct,
                    adj_dollars,
                    extra_margin,
                    confidence=confidence_score,
                    sp=_eval_sp,
                    empirical_expectancy_pct=(
                        float(calibration.get("avg_pnl_pct", 0.0) or 0.0)
                        if calibration else None
                    ),
                    empirical_win_rate_pct=(
                        float(calibration.get("win_rate_pct", 0.0) or 0.0)
                        if calibration else None
                    ),
                    required_ev_floor_pct=float(_eval_sp["filters"].get("min_calibrated_expectancy_pct", 0.0)),
                    ev_source="replay_calibrated" if calibration else "heuristic",
                )
            ev_signal = ev["trade_signal"]
            out["expected_value"] = ev

        # ── 6. Overall recommendation ─────────────────────────────────────────
        blocks   = []
        warnings = []

        min_direction_score = float(_eval_sp.get("entry", {}).get("min_direction_score", 35.0))
        if confidence_score is not None and confidence_score < min_direction_score:
            blocks.append(f"Direction score too low ({confidence_score:.0f}/{min_direction_score:.0f} required)")
        if skew["iv_crush_warning"]:
            warnings.append(skew["iv_crush_warning"])
        # Earnings proximity warning (same check as daily scan)
        if dte is not None:
            try:
                _ed_df = _cached_earnings_dates(symbol)
                if _ed_df is not None and not _ed_df.empty:
                    _now_dt = datetime.now().replace(tzinfo=None)
                    _fed = _ed_df[_ed_df.index.tz_localize(None) >= _now_dt] if _ed_df.index.tzinfo else _ed_df[_ed_df.index >= _now_dt]
                    if not _fed.empty:
                        _next_e = _fed.sort_index().index[0].to_pydatetime().replace(tzinfo=None)
                        _days_e = (_next_e - _now_dt).days
                        if 0 <= _days_e <= dte:
                            warnings.append(
                                f"⚠️ EARNINGS in {_days_e} day(s) — within your {dte}-day hold window. "
                                f"Expect elevated IV and gap risk."
                            )
            except Exception:
                pass
        if out.get("liquidity", {}).get("is_illiquid"):
            blocks.append(out["liquidity"]["flag"])
        if expectancy_surface is not None and delta is not None and calibration is None:
            blocks.append("No dense positive replay-backed expectancy is available for this setup.")
        if regime["defense_mode"]:
            warnings.append(f"⚠️ Defense Mode — VIX {regime['vix']:.0f}")
        if not ev_signal and delta is not None:
            blocks.append(out.get("expected_value", {}).get("ev_note", "EV check failed"))

        if not blocks and ev_signal:
            rec = "✅ PROCEED" if (confidence_score or 0) >= 60 else "⚠️ PROCEED WITH CAUTION"
        else:
            rec = "❌ AVOID" if blocks else "⚠️ CAUTION"

        out["recommendation"] = {
            "signal":   rec,
            "warnings": warnings,
            "blocks":   blocks,
            "summary":  (
                f"{rec} | Confidence {confidence_score:.0f}/100"
                if confidence_score is not None else rec
            ),
        }
        if calibration is not None:
            out["promotion_class"] = "promotable_exact_contract"
        elif expectancy_surface is not None:
            out["promotion_class"] = "research_sparse_calibration"
        else:
            out["promotion_class"] = "research_bootstrap"
        out["promotable"] = out["promotion_class"] == "promotable_exact_contract"

        return json.dumps(out, indent=2)

    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_stock_snapshot",
        "description": (
            "Get current stock price, today's open/high/low, volume, and percent change. "
            "Call this first for any specific ticker to get the underlying price."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Ticker, e.g. 'AAPL'"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_options_chain",
        "description": (
            "Fetch the options chain with Black-Scholes Greeks (delta, gamma, theta, vega), "
            "IV, volume, open interest, bid/ask, and break-even. Returns top 40 by volume. "
            "Use for deep analysis of a single ticker."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "option_type": {"type": "string", "enum": ["call", "put"],
                                "description": "Omit for both."},
                "max_dte": {"type": "integer", "default": 21,
                            "description": "Max days to expiration. Use 1 for 0DTE."},
                "expiration_date": {"type": "string",
                                    "description": "Specific date YYYY-MM-DD (optional)."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "screen_options",
        "description": (
            "Scan options across multiple tickers at once. "
            "Best for finding hottest plays across the market. Max 6 tickers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"},
                            "description": "List of tickers (max 6)."},
                "option_type": {"type": "string", "enum": ["call", "put", "both"], "default": "both"},
                "max_dte": {"type": "integer", "default": 21},
                "min_volume": {"type": "integer", "default": 100},
            },
            "required": ["symbols"],
        },
    },
    {
        "name": "find_high_leverage_options",
        "description": (
            "PURPOSE-BUILT for 'double my money' / '100% gain' requests. "
            "Screens options across high-beta large-caps and ranks them by "
            "'move_needed_pct' — the smallest % move the underlying needs to make "
            "the option approximately double in value. Lower move_needed_pct = easier path to 2x. "
            "Also shows leverage_per_contract ($ gain per 1% move) and gamma_efficiency. "
            "ALWAYS use this tool when user asks for 100%+ gain potential or wants to double their money."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tickers to scan (max 8). Defaults to high-beta watchlist if omitted.",
                },
                "option_type": {
                    "type": "string",
                    "enum": ["call", "put", "both"],
                    "description": "Use 'call' for bullish plays, 'put' for bearish. Default 'both'.",
                    "default": "both",
                },
                "max_dte": {
                    "type": "integer",
                    "description": "Max days to expiration. Default 14 for 2-week window.",
                    "default": 14,
                },
                "min_volume": {
                    "type": "integer",
                    "description": "Minimum daily volume. Default 50.",
                    "default": 50,
                },
                "max_move_needed_pct": {
                    "type": "number",
                    "description": "Only show options that need less than this % move to double. Default 12.",
                    "default": 12.0,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_expirations",
        "description": "List available options expiration dates within 21 days for a ticker.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_iv_analysis",
        "description": (
            "ALWAYS call this before recommending options on a ticker. "
            "Returns: HV10/30/60 (realized vol), HV Rank 0-100 (how elevated vol is vs past year), "
            "current ATM implied volatility, and IV vs HV spread (positive = options expensive). "
            "Tells you whether to favor buying or selling premium."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Stock ticker"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_earnings_info",
        "description": (
            "ALWAYS call this before recommending options on a single stock (not ETFs). "
            "Returns next earnings date and days until earnings. "
            "Earnings within your DTE = IV crush risk for buyers, opportunity for sellers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_market_context",
        "description": (
            "Get the current market regime: VIX level and trend, SPY/QQQ price trend, "
            "and overall options environment (buyer's vs seller's market). "
            "Call this at the start of any broad market scan or when user asks about overall conditions."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_put_call_ratio",
        "description": (
            "Calculate the put/call volume and OI ratio for a ticker across all near-term expirations. "
            "Shows directional sentiment, most active strikes, and per-expiration breakdown. "
            "P/C > 1.2 = bearish flow. P/C < 0.8 = bullish flow."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "max_dte": {"type": "integer", "default": 21,
                            "description": "Max DTE to include in ratio. Default 21."},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "calculate_position_size",
        "description": (
            "ALWAYS call this after identifying a specific trade to recommend. "
            "Given an option price, account size, and your confidence score (1-10), returns "
            "the number of contracts, total dollar risk, stop-loss price, and drawdown impact. "
            "Confidence scales premium-at-risk linearly: 1=0.5% of account, 10=3.0% of account. "
            "Be honest — only use 8-10 when you have strong conviction from multiple confirming signals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "option_price": {
                    "type": "number",
                    "description": "Mid price of the option (e.g. 1.45)",
                },
                "account_size": {
                    "type": "number",
                    "description": "User's account size in dollars. Use stored value if already known.",
                },
                "dte": {
                    "type": "integer",
                    "description": "Days to expiration — 0DTE always uses the 2% hard cap regardless of confidence.",
                    "default": 5,
                },
                "confidence": {
                    "type": "integer",
                    "description": (
                        "Your confidence in this trade on a 1–10 scale. "
                        "Maps linearly to position size: 1→0.5%, 5→~1.6%, 10→3.0% of account. "
                        "1-3: weak signal, high uncertainty. "
                        "4-6: moderate edge, decent setup. "
                        "7-8: strong confluence of signals. "
                        "9-10: exceptional setup — multiple strong confirming factors, ideal conditions."
                    ),
                    "default": 5,
                },
                "max_risk_pct": {
                    "type": "number",
                    "description": "Hard override for risk %. Ignores confidence scale. Leave blank normally.",
                },
            },
            "required": ["option_price"],
        },
    },
    {
        "name": "manage_risk_settings",
        "description": (
            "Read or update any part of the strategy profile — confidence weights, entry filters, "
            "market-regime rules, and risk/exit parameters. "
            "Call with no arguments to show the full current configuration. "
            "Call with any subset of arguments to apply only those changes. "
            "Always call this when the user mentions account size, risk tolerance, position sizing, "
            "stop-loss, profit targets, IV thresholds, VIX rules, EV filters, delta targets, or DTE targets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                # ── Risk / exit ───────────────────────────────────────────────
                "account_size":         {"type": "number",  "description": "Total trading account size in dollars"},
                "max_drawdown_pct":     {"type": "number",  "description": "Pause all trading after this % portfolio drawdown (default 15)"},
                "stop_loss_pct":        {"type": "number",  "description": "Exit when option loses this % of premium paid (default 50)"},
                "profit_target_pct":    {"type": "number",  "description": "Take profit when option gains this % of premium paid (default 100)"},
                "min_position_pct":     {"type": "number",  "description": "Minimum position size as % of account — floor for low-confidence trades (default 0.5)"},
                "max_position_pct":     {"type": "number",  "description": "Maximum position size as % of account — ceiling for high-confidence trades (default 3.0 equity / 2.5 index)"},
                "dte_0_max_pct":        {"type": "number",  "description": "Cap 0DTE trades to this % of account (default 0.5)"},
                # ── Market regime / defense ───────────────────────────────────
                "vix_defense_threshold":     {"type": "number",  "description": "VIX level that triggers defense mode — cut position sizes (default 25)"},
                "defense_position_mult":     {"type": "number",  "description": "Multiply all position sizes by this in defense mode, e.g. 0.5 = half size (default 0.5)"},
                "atr_expansion_stop_mult":   {"type": "number",  "description": "Widen stop-loss by this multiplier when ATR expands (default 1.5)"},
                # ── Entry filters ─────────────────────────────────────────────
                "min_ev_return_pct":         {"type": "number",  "description": "Minimum expected-value return on capital to emit a trade signal (default 8)"},
                "liquidity_spread_max_pct":  {"type": "number",  "description": "Max bid/ask spread as % of mid price before the liquidity gate blocks a trade (default 10)"},
                "illiquid_extra_margin_pct": {"type": "number",  "description": "Extra EV margin required when option is near the liquidity boundary (default 5)"},
                "iv_crush_z_threshold":      {"type": "number",  "description": "Z-score above 30-day HV mean at which we penalise for IV-crush risk (default 1.5)"},
                "iv_crush_confidence_penalty": {"type": "number","description": "Confidence points subtracted when IV crush risk is detected (default 15)"},
                # ── Targets (confidence scoring) ──────────────────────────────
                "delta_target":    {"type": "number",  "description": "Optimal delta for peak confidence score, e.g. 0.30 (default 0.30)"},
                "dte_target":      {"type": "integer", "description": "Optimal DTE at entry for peak confidence score, e.g. 7 (default 7)"},
            },
            "required": [],
        },
    },
    {
        "name": "log_paper_trade",
        "description": (
            "Paper trading journal — log, track, and close options trades to measure real performance. "
            "Use action='add' to log a new trade after recommending it. "
            "Use action='list' to show all trades and the win rate / total P&L summary. "
            "Use action='check' to estimate current P&L for open trades using live prices + Black-Scholes. "
            "Use action='close' to record the final exit price and lock in the result. "
            "ALWAYS offer to log a trade after giving a specific recommendation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action":            {"type": "string", "enum": ["add", "list", "check", "close"],
                                      "description": "What to do: add/list/check/close"},
                "symbol":            {"type": "string", "description": "Ticker e.g. NVDA"},
                "option_type":       {"type": "string", "enum": ["call", "put"]},
                "strike":            {"type": "number", "description": "Strike price"},
                "expiration":        {"type": "string", "description": "Expiration date YYYY-MM-DD"},
                "entry_price":       {"type": "number", "description": "Option mid price at entry"},
                "underlying_entry":  {"type": "number", "description": "Stock price at entry"},
                "contracts":         {"type": "integer", "default": 1},
                "notes":             {"type": "string", "description": "Optional trade thesis/notes"},
                "trade_id":          {"type": "integer", "description": "For check/close actions"},
                "exit_price":        {"type": "number", "description": "Option price at exit (for close)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "log_prediction",
        "description": (
            "Daily market prediction tracker — log directional predictions and grade them automatically when the target date arrives. "
            "action='log': record a new prediction (ticker, direction=bullish/bearish, target_move_pct, target_date, confidence 1-10, reasoning). "
            "Entry price is fetched automatically. "
            "action='grade': fetch actual prices and score all ungraded predictions whose target date has passed. "
            "Outcomes: 'hit' (direction + ~magnitude correct), 'directional' (direction only), 'miss'. "
            "action='list': show all predictions and overall accuracy stats. "
            "action='delete': remove a prediction by prediction_id. "
            "Make a prediction each day and grade previous ones to build a real track record."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action":           {"type": "string", "enum": ["log", "grade", "list", "delete"],
                                     "description": "What to do"},
                "ticker":           {"type": "string", "description": "Stock/ETF ticker e.g. NVDA"},
                "direction":        {"type": "string", "enum": ["bullish", "bearish"],
                                     "description": "Predicted price direction"},
                "target_move_pct":  {"type": "number",
                                     "description": "Expected % move (e.g. 3.5 for +3.5%). Positive = up."},
                "target_date":      {"type": "string",
                                     "description": "Date by which the move should happen YYYY-MM-DD (default: 5 days)"},
                "confidence":       {"type": "integer", "minimum": 1, "maximum": 10,
                                     "description": "Conviction 1-10"},
                "reasoning":        {"type": "string",
                                     "description": "Why you expect this move"},
                "prediction_id":    {"type": "integer",
                                     "description": "For delete action"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "backfill_predictions",
        "description": (
            "Retroactively generates and grades daily directional predictions for every past trading day. "
            "For each day in the lookback window it computes a momentum+trend signal (5-day return vs 20-day SMA), "
            "logs a bullish or bearish prediction at that day's open price, then grades it immediately using the "
            "actual close on the target date. Skips neutral/ambiguous days. "
            "Use this to build a historical track record so the bot can see what its signal is actually good at. "
            "Safe to re-run — won't duplicate entries unless overwrite=True."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers":       {"type": "array", "items": {"type": "string"},
                                  "description": "List of tickers to backfill (default: SPY QQQ NVDA TSLA AAPL META AMD)"},
                "lookback_days": {"type": "integer", "default": 90,
                                  "description": "How many calendar days back to generate predictions for"},
                "horizon_days":  {"type": "integer", "default": 5,
                                  "description": "How many trading days forward each prediction targets"},
                "overwrite":     {"type": "boolean", "default": False,
                                  "description": "If true, regenerate predictions even if that date already exists"},
            },
            "required": [],
        },
    },
    {
        "name": "backtest_strategy",
        "description": (
            "Backtests the bot's ACTUAL trading methodology over historical price data. "
            "Applies the same entry filters the bot uses live: momentum+trend signal, VIX proxy filter, "
            "HV rank filter, and delta-targeted strike selection. Position size scales with signal confidence. "
            "Shows win rate, avg P&L, expected value, total dollar P&L, and equity curve. "
            "Use when the user asks 'how would this strategy have performed?' or wants to validate "
            "the bot's approach before risking real money. "
            "IMPORTANT: IV is estimated from 30-day HV — treat as directional signal, not exact P&L."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":                {"type": "string",  "description": "Ticker to backtest, e.g. NVDA"},
                "option_type":           {"type": "string",  "enum": ["call", "put", "signal"],
                                          "description": "'signal' auto-selects direction from momentum (default)", "default": "signal"},
                "dte_at_entry":          {"type": "integer", "description": "DTE when buying each option (e.g. 7, 14)", "default": 7},
                "delta_target":          {"type": "number",  "description": "Target BS delta for strike selection (0.15–0.45, default 0.30)", "default": 0.30},
                "lookback_days":         {"type": "integer", "description": "Trading days of history to test (252 = ~1 year)", "default": 252},
                "stop_loss_pct":         {"type": "number",  "description": "Exit if option loses this % (default 50)", "default": 50.0},
                "profit_target_pct":     {"type": "number",  "description": "Take profit at this % gain (default 100 = 2x)", "default": 100.0},
                "position_size_dollars": {"type": "number",  "description": "Base dollar size per trade; scales with signal confidence. Default: 10% of account or $1000"},
                "vix_max":               {"type": "number",  "description": "Skip days when estimated market vol > this (default 35)", "default": 35.0},
                "hv_rank_max":           {"type": "number",  "description": "Skip days when HV rank > this percentile (default 80)", "default": 80.0},
                "require_signal":        {"type": "boolean", "description": "Only trade on momentum+trend signal days (default true)", "default": True},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "evaluate_trade_signal",
        "description": (
            "Master trade evaluator — runs ALL strategy filters on a specific option contract "
            "and returns a unified PROCEED / CAUTION / AVOID signal. "
            "Always call this before recommending a specific options contract. "
            "Computes: (1) Confidence score weighted by IV rank 40%, delta 30%, DTE 30%. "
            "(2) IV vertical + time skew; penalises confidence by 20 pts if OTM IV is >2σ above "
            "30-day HV mean (IV crush risk). "
            "(3) Liquidity check — blocks missing bid/ask quotes and flags wide spreads, low volume/OI, and stale chains. "
            "(4) Market regime — VIX + ATR; Defense Mode halves position size, expanding ATR widens stop 1.5×. "
            "(5) EV formula: EV = (delta × avg_win) − ((1−delta) × avg_loss); signal only if EV ≥ 10%."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol":          {"type": "string",  "description": "Ticker, e.g. NVDA"},
                "option_type":     {"type": "string",  "enum": ["call", "put"]},
                "strike":          {"type": "number",  "description": "Strike price"},
                "expiry":          {"type": "string",  "description": "Expiration date YYYY-MM-DD"},
                "bid":             {"type": "number",  "description": "Current bid price"},
                "ask":             {"type": "number",  "description": "Current ask price"},
                "contract_volume": {"type": "integer", "description": "Latest option contract volume, if known"},
                "open_interest":   {"type": "integer", "description": "Latest option open interest, if known"},
                "quote_age_hours": {"type": "number",  "description": "Hours since the last trade/quote update, if known"},
                "delta":           {"type": "number",  "description": "Option delta (positive number, e.g. 0.30)"},
                "iv_percentile":   {"type": "number",  "description": "IV rank/percentile 0-100 (from get_iv_analysis)"},
                "dte":             {"type": "integer", "description": "Days to expiration"},
                "position_dollars":{"type": "number",  "description": "Dollar size before regime adjustments", "default": 1000},
                "avg_win_pct":     {"type": "number",  "description": "Expected % gain when trade wins (default 80 = 0.8x)", "default": 80},
                "avg_loss_pct":    {"type": "number",  "description": "Expected % loss when trade loses (default 40)", "default": 40},
            },
            "required": ["symbol", "option_type", "strike", "expiry"],
        },
    },
]

TOOL_DISPATCH = {
    "get_stock_snapshot":         get_stock_snapshot,
    "get_options_chain":          get_options_chain,
    "screen_options":             screen_options,
    "find_high_leverage_options": find_high_leverage_options,
    "get_expirations":            get_expirations,
    "get_iv_analysis":            get_iv_analysis,
    "get_earnings_info":          get_earnings_info,
    "get_market_context":         get_market_context,
    "get_put_call_ratio":         get_put_call_ratio,
    "calculate_position_size":    calculate_position_size,
    "manage_risk_settings":       manage_risk_settings,
    "log_paper_trade":            log_paper_trade,
    "log_prediction":             log_prediction,
    "backfill_predictions":       backfill_predictions,
    "backtest_strategy":          backtest_strategy,
    "evaluate_trade_signal":      evaluate_trade_signal,
}


def run_tool(name: str, inputs: dict) -> str:
    fn = TOOL_DISPATCH.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return fn(**inputs)
    except Exception as e:
        return json.dumps({"error": type(e).__name__, "message": str(e)})


# ─── Claude CLI via subprocess ─────────────────────────────────────────────────

def _build_tool_schema_text() -> str:
    lines = [
        "Call tools one at a time using this exact format:\n"
        "<tool_call>{\"tool\": \"name\", \"args\": {...}}</tool_call>\n"
        "\nAvailable tools:"
    ]
    for tool in TOOLS:
        desc = tool["description"].split("\n")[0][:120]
        props = tool["input_schema"].get("properties", {})
        req = tool["input_schema"].get("required", [])
        args = ", ".join(f"{k}{'*' if k in req else ''}" for k in props)
        lines.append(f"\n{tool['name']}({args})\n  {desc}")
    return "\n".join(lines)


def _build_prompt(messages: list) -> str:
    parts = ["CONVERSATION:\n"]
    for msg in messages:
        role = msg["role"].upper()
        content = msg["content"]
        if isinstance(content, str):
            parts.append(f"{role}: {content}\n\n")
        elif isinstance(content, list):
            chunks = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                t = item.get("type", "")
                if t == "text" and item.get("text"):
                    chunks.append(_strip_tool_calls(item["text"]))
                elif t == "tool_result":
                    result = item.get("content", "")
                    if len(result) > 3000:
                        result = result[:3000] + "...[truncated]"
                    chunks.append(f"<tool_result>{result}</tool_result>")
            if chunks:
                parts.append(f"{role}: {''.join(chunks)}\n\n")
    parts.append("ASSISTANT:")
    return "".join(parts)


def _find_claude() -> str:
    """Return the path to the claude executable, searching common Windows locations."""
    # 1. Already on PATH
    found = shutil.which("claude")
    if found:
        return found
    # 2. Windows App (Claude Desktop) install — version number varies, take newest
    pattern = os.path.expanduser(
        "~/AppData/Local/Packages/Claude_*/LocalCache/Roaming/Claude/claude-code/*/claude.exe"
    )
    matches = sorted(glob.glob(pattern))
    if matches:
        return matches[-1]
    # 3. VS Code extension copy — also version-numbered, take newest
    pattern2 = os.path.expanduser(
        "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude.exe"
    )
    matches2 = sorted(glob.glob(pattern2))
    if matches2:
        return matches2[-1]
    return "claude"  # will raise FileNotFoundError with original message


CHAT_MODEL = "claude-haiku-4-5-20251001"  # fast model; change to claude-sonnet-4-6 for deeper analysis


def _call_claude_cli(prompt: str, system: str = "") -> str:
    try:
        cmd = [_find_claude(), "-p", "--tools", "", "--no-session-persistence",
               "--model", CHAT_MODEL]
        if system:
            cmd += ["--system-prompt", system]
        result = subprocess.run(
            cmd,
            input=prompt, capture_output=True, text=True,
            timeout=120, encoding="utf-8",
        )
        if result.returncode != 0 and result.stderr:
            # If model flag unsupported by this CLI version, retry without it
            if "model" in result.stderr.lower() or "unknown" in result.stderr.lower():
                cmd_fallback = [c for c in cmd if c not in ("--model", CHAT_MODEL)]
                result = subprocess.run(
                    cmd_fallback,
                    input=prompt, capture_output=True, text=True,
                    timeout=120, encoding="utf-8",
                )
            if result.returncode != 0 and result.stderr:
                return f"[CLI Error: {result.stderr[:200]}]"
        return result.stdout.strip()
    except FileNotFoundError:
        return "[Error: 'claude' command not found. Ensure Claude Code is installed.]"
    except subprocess.TimeoutExpired:
        return "[Error: Claude CLI timed out after 120s.]"
    except Exception as e:
        return f"[Error calling Claude CLI: {e}]"


def _parse_tool_calls(response: str) -> list:
    matches = re.findall(r'<tool_call>(.*?)</tool_call>', response, re.DOTALL)
    calls = []
    for i, m in enumerate(matches):
        try:
            data = json.loads(m.strip())
            data["_id"] = f"call_{i}"
            calls.append(data)
        except json.JSONDecodeError:
            pass
    return calls


def _strip_tool_calls(text: str) -> str:
    return re.sub(r'<tool_call>.*?</tool_call>', '', text, flags=re.DOTALL).strip()


# ─── Conversation history trimmer ─────────────────────────────────────────────

MAX_HISTORY = 20  # max messages to keep (10 user/assistant exchanges)


def _trim_history(conversation: list) -> list:
    """Drop oldest messages when history grows long, preserving turn structure."""
    if len(conversation) <= MAX_HISTORY:
        return conversation
    trimmed = conversation[-MAX_HISTORY:]
    # Never start with an assistant turn — drop until we hit a user message
    while trimmed and trimmed[0]["role"] == "assistant":
        trimmed = trimmed[1:]
    return trimmed


# ─── System prompt ─────────────────────────────────────────────────────────────

def _get_system_prompt() -> str:
    """Build the system prompt dynamically from STRATEGY_PROFILE so any slider
    changes in the Risk Engine tab are immediately reflected in Claude's instructions."""
    sp  = STRATEGY_PROFILE
    cw  = sp["confidence_weights"]
    tgt = sp["targets"]
    flt = sp["filters"]
    rsk = sp["risk"]

    iv_w    = round(cw["iv_percentile"] * 100)
    d_w     = round(cw["delta"]         * 100)
    dte_w   = round(cw["dte"]           * 100)

    illiq_total = round(flt["min_ev_return_pct"] + flt["illiquid_extra_margin_pct"])

    return f"""You are a strategy explainer for an options trading model. Your role is strictly limited to:

1. Explaining how this strategy and model work
2. Defining options terminology
3. Describing why a specific pick was generated (why that strike, why that DTE, what the scores mean)
4. Explaining backtest and scan results

## Hard Boundaries — never cross these
- Do NOT tell the user whether to buy, sell, or hold any position
- Do NOT give position sizing advice ("buy X contracts", "risk Y% of your account")
- Do NOT give entry/exit timing advice ("buy now", "wait for a pullback")
- Do NOT ask for or comment on the user's account size, portfolio, or personal finances
- Do NOT say things like "I recommend", "you should", "this looks like a good trade for you"
- If asked anything account-specific or personalized ("should I take this trade?", "how much should I put in?"), respond:
  "I can explain what the model shows and why, but I can't make personalized trading recommendations. Consult a licensed financial advisor for that."

## Response Style
- Lead with the answer. No preamble, no filler.
- Bullets/tables for data. One sentence per idea.
- Never repeat what a tool result already shows.

## Strategy Overview (for explanations)
- Universe: SPY QQQ AAPL NVDA TSLA META MSFT AMZN GOOGL AMD NFLX COIN PLTR
- Single-leg long calls/puts only. {DTE_MIN}–{DTE_MAX} DTE required. No 0DTE.
- Target delta {tgt["delta_optimal"] - tgt["delta_falloff"]:.2f}–{tgt["delta_optimal"] + tgt["delta_falloff"]:.2f} OTM (sweet spot {tgt["delta_optimal"]:.2f}).

## Scores — how to explain them
- **Direction Score** (0–100): predicts whether the stock will move in the right direction. Formula: tech setup 55% + SPY regime alignment 30% + momentum 15% − RSI overextension penalty. ≥60 = model says PROCEED / 40–59 = CAUTION / <40 = AVOID.
- **Quality Score** (0–100): rates the option contract itself (not the stock direction). IV rank {iv_w}% + delta fit {d_w}% + DTE fit {dte_w}%. IV crush penalty: -{flt["iv_crush_confidence_penalty"]:.0f}pts if IV >{flt["iv_crush_z_threshold"]:.1f}σ above HV.
- Direction Score gates entry. Quality Score ranks the contract. Both are required to appear in any pick explanation.
- **EV**: expected value = (|delta| × avg_win%) − ((1−|delta|) × avg_loss%). Must be ≥{flt["min_ev_return_pct"]:.0f}% to pass.

## Why This Strike / Why This DTE — how to explain a pick
When explaining a specific scan pick:
1. State the Direction Score and what drove it (tech score, momentum, regime)
2. State the Quality Score and what drove it (IV rank, delta fit, DTE fit)
3. Explain why the DTE was chosen: {DTE_MIN}–{DTE_MAX} day window avoids 0DTE binary risk and captures momentum without excessive theta decay
4. Explain why the delta/strike was chosen: ~{tgt["delta_optimal"]:.2f} delta balances leverage vs probability; too low = lottery, too high = expensive with little leverage
5. Note the time exit: the model closes at day {rsk.get("time_exit_pct", 50):.0f}% of original DTE to avoid theta bleed on sideways trades
6. Note any veto flags: earnings within DTE, IV rank >85, bid-ask spread >20%

## Greeks Reference (for definitions)
- **Delta**: probability proxy + directional sensitivity. 0.70–0.90 deep ITM | 0.45–0.55 ATM | 0.20–0.40 OTM sweet spot | <0.15 lottery
- **Theta**: time decay cost per day. Accelerates sharply in the last 3 DTE — why this strategy avoids very short-dated options.
- **Vega**: sensitivity to implied volatility. IV spikes before earnings, crushes 30–60% after — why the model vetoes trades inside an earnings window.
- **IV Rank**: where current IV sits vs its 52-week range. <30 = historically cheap | >70 = historically expensive (buying premium here is penalized in Quality Score).
- **Put/Call Ratio**: >1.5 bearish flow | 0.8–1.2 neutral | <0.6 bullish flow.

## Risk Rules (for explanations only — not personalized advice)
- Model stop-loss: {rsk["stop_loss_pct"]:.0f}% premium loss. Profit target: {rsk["profit_target_pct"]:.0f}%.
- **Time exit**: closes at {rsk.get("time_exit_pct", 50):.0f}% of original DTE elapsed — prevents theta bleed on sideways trades.
- Regime defense: VIX>{flt["vix_defense_threshold"]:.0f} reduces model position sizing. VIX>35 = no new entries.

## Daily Predictions (log_prediction)

**Two separate prediction sources — never conflate them:**
- **`daily_scan` picks** = output of the quantitative Direction Score + Quality Score model. When the user asks about "the predictions", these are what they mean. Report stats from `summary.scan_model`.
- **Manual predictions** = picks logged directly via `log_prediction(action="log")` in chat. Stats from `summary.manual_predictions`.

**Workflow when asked about predictions:**
1. `log_prediction(action="grade")` first — grade any whose target date has passed
2. `log_prediction(action="list")` — report scan model stats and manual stats separately
3. Explain the Direction Score rationale behind scan picks — do NOT dismiss them based on manual hit rate
4. Never apply your manual track record to the scan model's output — they are independent signals

**Grading:**
- "hit" = direction correct AND magnitude within 50% of target
- "directional" = direction correct, move smaller than expected
- "miss" = direction wrong

## Backtesting (backtest_strategy)
When explaining a backtest:
1. Run `backtest_strategy` with the requested parameters
2. Explain win rate, expected value, and how often the profit target was hit
3. Note benchmark context (random 50% baseline gives EV near 0)
4. Always note: IV is estimated from historical vol — actual option prices depend on implied vol at the time
5. Explain what the results suggest about the strategy parameters (DTE, delta, ticker) — do not say "you should trade this"

Key metrics to explain:
- `win_rate_pct`: % of trades profitable at exit
- `expected_value_pct`: average P&L per trade (positive = statistical edge)
- `hit_profit_target_pct`: % of trades that reached the profit target
- `stopped_out_pct`: % of trades stopped out

## Data Notes
- Market data from Yahoo Finance (~15-min delayed)
- Greeks via Black-Scholes from live IV
- HV Rank uses realized vol as proxy for true IV rank
- This platform is for informational and educational purposes only. Nothing here is financial advice.

## Scan Watchlist
{{watchlist}}

Today: {{datetime}}  |  Risk-free rate: {{rfr}}%
"""

# SYSTEM_PROMPT is intentionally removed — use _get_system_prompt() which reads live from STRATEGY_PROFILE


# ─── Main chat loop ─────────────────────────────────────────────────────────────

def chat():
    conversation = []
    system = _get_system_prompt().format(
        watchlist=", ".join(DEFAULT_WATCHLIST),
        datetime=datetime.now().strftime("%A, %Y-%m-%d %H:%M ET"),
        rfr=round(RISK_FREE_RATE * 100, 1),
    ) + "\n\n## Tool Calling\n" + _build_tool_schema_text()

    print()
    print("=" * 66)
    print("  📈  Options Trading Assistant  —  Enhanced Edition")
    print("  Claude Sonnet 4.6  x  Yahoo Finance (free, ~15-min delayed)")
    print("  16 tools: Greeks · IV Rank · Earnings · VIX · P/C Ratio")
    print("    · 2x Screener · Position Sizing · Risk Management")
    print("    · Paper Trading Journal · Strategy Backtester · Brain")
    print("  Scope: Large-cap high-beta single-leg | 5–35 DTE | 15% max drawdown")
    print("=" * 66)
    print()
    print("  STEP 1 — Tell the bot your account size so it can size every")
    print("           trade safely (required for position sizing):")
    print('    "My account is $10,000"')
    print()
    print("  STEP 2 — Try asking:")
    print()
    print("  [ Market Overview ]")
    print('    "What\'s the market setup right now — should I be buying or selling premium?"')
    print('    "What does the VIX say about options pricing today?"')
    print()
    print("  [ Find Trades ]")
    print('    "Find me the best option trade to double my money within 2 weeks"')
    print('    "Scan the market for the hottest calls right now"')
    print('    "Best NVDA calls this week — are options cheap or expensive?"')
    print()
    print("  [ Specific Analysis ]")
    print('    "Analyze TSLA — I\'m bearish, what put should I buy?"')
    print('    "Show me SPY 0DTE options and the put/call ratio"')
    print('    "Does AAPL have earnings coming up that would affect my trade?"')
    print()
    print("  [ Backtest a Strategy ]")
    print('    "Backtest buying NVDA 5% OTM calls with 7 DTE over the past year"')
    print('    "How would buying weekly SPY puts have performed in the last 6 months?"')
    print('    "Test a TSLA call strategy — 3% OTM, 14 DTE, 50% stop, 2x target"')
    print()
    print("  [ Paper Trading Journal ]")
    print('    "Log this trade in my paper trading journal"')
    print('    "How are my open paper trades doing right now?"')
    print('    "Show me my paper trading win rate and total P&L"')
    print('    "Close trade #3 — I sold it for $2.10"')
    print()
    print("  [ Risk & Sizing ]")
    print('    "How many contracts of the NVDA $X call should I buy?"')
    print('    "What is my max drawdown limit and how many losing trades until I hit it?"')
    print('    "Change my stop-loss to 40% and max trade risk to 3%"')
    print()
    print("  Type 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye! Trade safe. 📈")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye", "q"):
            print("Goodbye! Trade safe. 📈")
            break

        conversation.append({"role": "user", "content": user_input})
        print()

        while True:
            raw = _call_claude_cli(_build_prompt(_trim_history(conversation)), system=system)

            tool_calls = _parse_tool_calls(raw)
            visible_text = _strip_tool_calls(raw)

            if visible_text:
                print(f"Assistant: {visible_text}")

            if not tool_calls:
                conversation.append({"role": "assistant", "content": visible_text or raw})
                print()
                break

            # Execute each tool call and collect results
            tool_results = []
            for call in tool_calls:
                tool_name = call.get("tool", "")
                tool_args = call.get("args", {})
                arg_str = json.dumps(tool_args)
                preview = arg_str[:72] + ("..." if len(arg_str) > 72 else "")
                print(f"  🔍 {tool_name}({preview})")
                result = run_tool(tool_name, tool_args)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call["_id"],
                    "content": result,
                })

            # Add assistant turn and tool results to conversation history
            conversation.append({"role": "assistant", "content": [{"type": "text", "text": raw}]})
            conversation.append({"role": "user", "content": tool_results})

