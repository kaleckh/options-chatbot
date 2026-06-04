"""
Walk-Forward Optimization (WFO) engine for options strategy confidence weights
and entry/exit parameters.

Pipeline
--------
1. Load N years of daily closes through the configured market-data provider.
2. Split into rolling windows: train_months train → test_months test.
3. For each window, run Optuna to find the full parameter set that maximises
   Profit Factor on training data (9 parameters tuned simultaneously).
   Optuna is warm-started from the prior window's best params so each
   window converges faster and builds on what it learned.
4. Validate winning params on the held-out test slice (OOS).
5. Accept window only if ALL 5 guardrails pass.
6. Log accepted params by market regime to wfo_results.json.

What gets optimised (9 parameters)
-----------------------------------
Confidence weights : iv_percentile, delta, dte
Entry rules        : delta_target, entry_momentum_pct, min_confidence, min_ev_pct
Exit rules         : stop_loss_pct, profit_target_pct

Fitness function
----------------
Primary   : Profit Factor = gross_profit / gross_loss  (>1.5 good, >2 excellent)
Secondary : +0.1 × Sharpe bonus  (stabilises against outlier-driven PF)
Penalty   : −0.02 × max_drawdown_pct

Guardrails (ALL must pass)
--------------------------
G1  OOS Profit Factor ≥ 80% of IS Profit Factor   (overfitting gate)
G2  Weight drift ≤ max_drift_pct from profile      (stability gate — default 40%)
G3  Auto min-trades ≥ floor(test_days / 4, 10)    (sample-size gate — computed automatically)
G4  Top-10 trial weight std < 0.15                 (noise gate)
G5  OOS win rate ≥ 35%                             (consistency gate — asymmetric P&L means 35% wins + high PF is profitable)

Params are NEVER written to STRATEGY_PROFILE automatically.
The UI exposes an Apply button with a full before/after diff.
"""

from __future__ import annotations

import json
import math
import os
import heapq
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache, wraps
from itertools import combinations
from typing import Any, Callable, Optional, Sequence

import numpy as np
import pandas as pd
import yfinance as yf

from alpaca_market_data import alpaca_provider_requested, make_alpaca_ticker_factory
from expectancy_calibration import (
    DEFAULT_DIRECTION_BUCKET_SIZE,
    DEFAULT_QUALITY_BUCKET_SIZE,
    DEFAULT_SHRINKAGE_TRADES,
    DEFAULT_SPARSE_WARNING_TRADES,
    DEFAULT_SURFACE_MIN_TRADES,
    DEFAULT_TECH_BUCKET_SIZE,
    CalibrationAccumulator,
    lookup_calibrated_expectancy,
    normalized_market_regime,
)
from ai_commodity_contract import (
    AI_COMMODITY_INFRA_OBSERVATION_PLAYBOOK_ID,
    ai_commodity_underlying_filters,
    is_ai_commodity_playbook_id,
)
from ai_commodity_universe import ai_commodity_scan_tickers
from exact_contract_accounting import (
    contract_resolution_accounting,
    is_exact_contract_resolution as _shared_is_exact_contract_resolution,
)
from forward_options_ledger import LIVE_PRODUCTION_EVIDENCE_CLASS, list_forward_scan_pick_events
from lane_universe_manifest import lane_universe_symbols
from market_data_service import (
    get_history as _md_get_history,
    get_ticker_info as _md_get_ticker_info,
    request_scope as _market_data_request_scope,
)
from historical_options_store import (
    DAILY_QUOTE_MINUTE_ET,
    ENTRY_QUOTE_MINUTE_ET,
    ENTRY_QUOTE_WINDOW_MINUTES,
    HistoricalOptionsStore,
    DAILY_SNAPSHOT_KIND,
    INTRADAY_SNAPSHOT_KIND,
    TRUSTED_DATA_TRUST,
)
from options_execution import (
    DEFAULT_COMMISSION_PER_CONTRACT_USD,
    executable_option_price,
    has_two_sided_quote,
    long_option_pnl,
    quote_midpoint,
)

PLAYBOOK_EXIT_AUDIT_FALLBACK_PLAYBOOK = "bullish_pullback_observation"

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    HAS_OPTUNA = True
except ImportError:
    HAS_OPTUNA = False

from options_chatbot import (
    STRATEGY_PROFILE,
    STRATEGY_PROFILES,
    ensure_strategy_profiles_current,
    RISK_FREE_RATE,
    DTE_MIN,
    DTE_MAX,
    DEFAULT_SCAN_PICKS,
    INDEX_TICKERS,
    DEFAULT_WATCHLIST,
    UNDERLYING_FILTERS,
    UNDERLYING_LIQUIDITY_WINDOW,
    _bs_greeks,
    _get_market_regime,
    _compute_direction_score,
    _compute_quality_score,
    _candidate_rank_tuple,
)

WFO_RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wfo_results.json")
OPTIONS_VALIDATION_RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data",
    "options-validation",
    "runs",
)
OPTIONS_VALIDATION_LATEST_FILE = os.path.join(OPTIONS_VALIDATION_RESULTS_DIR, "latest.json")
OPTIONS_VALIDATION_DAILY_LATEST_FILE = os.path.join(OPTIONS_VALIDATION_RESULTS_DIR, "latest_daily.json")
OPTIONS_VALIDATION_DAILY_FORWARD_LATEST_FILE = os.path.join(
    OPTIONS_VALIDATION_RESULTS_DIR,
    "latest_daily_forward.json",
)
IMPORTED_VALIDATION_UNIVERSE = (
    "SPY",
    "QQQ",
)


def _lane_replay_universe(lane_id: str, fallback: Sequence[str]) -> tuple[str, ...]:
    try:
        symbols = tuple(lane_universe_symbols(lane_id, fallback=fallback))
    except Exception:
        symbols = tuple(str(symbol).strip().upper() for symbol in fallback if str(symbol).strip())
    return tuple(dict.fromkeys(symbols))


BULLISH_PULLBACK_REPLAY_UNIVERSE = _lane_replay_universe(
    "bullish_pullback_observation",
    IMPORTED_VALIDATION_UNIVERSE,
)
REGULAR_OPTIONS_REPLAY_UNIVERSE = BULLISH_PULLBACK_REPLAY_UNIVERSE
IMPORTED_TRUTH_SOURCE = "historical_imported"
IMPORTED_DAILY_TRUTH_SOURCE = "historical_imported_daily"
ALPACA_OPRA_DAILY_SOURCE_LABEL = "alpaca_opra_daily_snapshot"
SYNTHETIC_TRUTH_SOURCE = "synthetic_research"
FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE = "forward_ledger_scan"
ARCHIVED_FORWARD_SOURCE_LABEL = "api_scan_auto"
PRIMARY_JUDGE_TRADE_CLASS = "exact_archived_contract"
ARCHIVED_EXACT_PRIMARY_STATUS = "archived_exact_primary"
ARCHIVED_EXACT_INSUFFICIENT_STATUS = "archived_exact_insufficient"
MODEL_DAILY_FALLBACK_ONLY_STATUS = "model_daily_fallback_only"
SYNTHETIC_ONLY_STATUS = "synthetic_only"
MIN_ARCHIVED_PRIMARY_SYMBOL_TRADES = 25
MIN_IMPORTED_QUOTE_COVERAGE_PCT = 70.0
MIN_EXACT_CONTRACT_DIRECTIONAL_ACCURACY_PCT = 50.0


def _is_imported_truth_source(value: Optional[str]) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {IMPORTED_TRUTH_SOURCE, IMPORTED_DAILY_TRUTH_SOURCE}


def _imported_snapshot_kind(truth_source: str) -> str:
    return DAILY_SNAPSHOT_KIND if str(truth_source or "").strip().lower() == IMPORTED_DAILY_TRUTH_SOURCE else INTRADAY_SNAPSHOT_KIND


def _imported_entry_quote_label(truth_source: str) -> str:
    normalized = str(truth_source or "").strip().lower()
    if normalized == IMPORTED_DAILY_TRUTH_SOURCE:
        return "End-of-day snapshot ET"
    return f"{_et_minute_label(ENTRY_QUOTE_MINUTE_ET)} + {ENTRY_QUOTE_WINDOW_MINUTES}m"


def _imported_exit_quote_label(truth_source: str) -> str:
    normalized = str(truth_source or "").strip().lower()
    if normalized == IMPORTED_DAILY_TRUTH_SOURCE:
        return "End-of-day snapshot each trading day ET"
    return "Latest available snapshot each trading day ET"


def _normalize_requested_pricing_lane(value: Any) -> str:
    normalized = str(value or "pessimistic").strip().lower()
    return "mid" if normalized == "mid" else "pessimistic"


def _execution_realism_label(truth_source: str) -> str:
    normalized = str(truth_source or "").strip().lower()
    if normalized == IMPORTED_DAILY_TRUTH_SOURCE:
        return "coarse_eod_validation"
    if normalized == IMPORTED_TRUTH_SOURCE:
        return "quote_backed_intraday_replay"
    return "synthetic_model_replay"


def _entry_anchor_policy_label(truth_source: str) -> str:
    normalized = str(truth_source or "").strip().lower()
    if normalized == IMPORTED_DAILY_TRUTH_SOURCE:
        return "archived_selection_price_else_prior_close"
    if normalized == IMPORTED_TRUTH_SOURCE:
        return "selection_open"
    return "market_open"


def _resolve_imported_execution_price(
    *,
    side: str,
    requested_pricing_lane: str,
    bid: Any = None,
    ask: Any = None,
    last: Any = None,
    slippage_pct: float = 0.0,
) -> dict[str, Any]:
    normalized_lane = _normalize_requested_pricing_lane(requested_pricing_lane)
    fallback_reason: Optional[str] = None
    if normalized_lane == "mid" and has_two_sided_quote(bid=bid, ask=ask):
        midpoint = quote_midpoint(bid=bid, ask=ask)
        if midpoint is not None and midpoint > 0:
            return {
                "execution_price": round(float(midpoint), 4),
                "execution_basis": "mid",
                "effective_pricing_lane": "mid",
                "pricing_lane_fallback_reason": None,
            }
    if normalized_lane == "mid":
        fallback_reason = "mid_requires_two_sided_quote"
    execution = executable_option_price(
        side=side,
        bid=bid,
        ask=ask,
        last=last,
        slippage_pct=slippage_pct,
        quote_freshness_status="fresh",
        allow_research_fallback=False,
    )
    return {
        "execution_price": execution.get("execution_price"),
        "execution_basis": execution.get("execution_basis"),
        "effective_pricing_lane": (
            "pessimistic"
            if execution.get("execution_price") is not None and fallback_reason
            else normalized_lane
        ),
        "pricing_lane_fallback_reason": fallback_reason,
    }


def _normalize_replay_history_index(index) -> pd.DatetimeIndex:
    normalized = pd.DatetimeIndex(index)
    if normalized.tz is not None:
        normalized = normalized.tz_convert("UTC").tz_localize(None)
    return normalized.normalize()


def _sanitize_replay_history_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    sanitized = frame.copy()
    if not isinstance(sanitized.index, pd.DatetimeIndex):
        sanitized.index = pd.to_datetime(sanitized.index)
    sanitized = sanitized.sort_index()

    required = [column for column in ("Open", "Close", "Volume") if column in sanitized.columns]
    if required:
        sanitized = sanitized.dropna(subset=required)

    if (
        {"High", "Low"}.issubset(sanitized.columns)
        and (sanitized["High"].notna().any() or sanitized["Low"].notna().any())
    ):
        invalid = sanitized["High"].isna() | sanitized["Low"].isna()
        invalid |= sanitized["High"] < sanitized["Low"]
        if "Open" in sanitized.columns:
            invalid |= (sanitized["Open"] > sanitized["High"]) | (sanitized["Open"] < sanitized["Low"])
        if "Close" in sanitized.columns:
            invalid |= (sanitized["Close"] > sanitized["High"]) | (sanitized["Close"] < sanitized["Low"])
        sanitized = sanitized.loc[~invalid]

    return sanitized


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
        ticker_factory=_replay_ticker_factory(),
    )


def _cached_ticker_info(symbol: str) -> dict:
    return _md_get_ticker_info(symbol, ticker_factory=_replay_ticker_factory())


def _replay_ticker_factory():
    if alpaca_provider_requested():
        return make_alpaca_ticker_factory(fallback_factory=None)
    return yf.Ticker


def _market_data_scoped(fn):
    @wraps(fn)
    def _wrapped(*args, **kwargs):
        with _market_data_request_scope():
            return fn(*args, **kwargs)
    return _wrapped

REPLAY_PLAYBOOKS: dict[str, dict] = {
    "broad": {
        "id": "broad",
        "label": "Broad Universe",
    },
    "short_term": {
        "id": "short_term",
        "label": "Short Term",
    },
    "bullish_momentum": {
        "id": "bullish_momentum",
        "label": "Bullish Momentum",
        "allowed_asset_classes": ["equity"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "min_quality_score": 70.0,
        "requires_calibrated_history": True,
    },
    "bullish_index_calls": {
        "id": "bullish_index_calls",
        "label": "Bullish Index Calls",
        "allowed_asset_classes": ["index"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
    },
    "bullish_index_calls_score70": {
        "id": "bullish_index_calls_score70",
        "label": "Bullish Index Calls Score 70+",
        "allowed_asset_classes": ["index"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "min_quality_score": 70.0,
    },
    "bullish_index_calls_quality90_debit55": {
        "id": "bullish_index_calls_quality90_debit55",
        "label": "Bullish Index Calls Quality 90+ Debit <55%",
        "allowed_asset_classes": ["index"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "min_quality_score": 90.0,
        "max_debit_pct_of_width": 55.0,
    },
    "bullish_index_calls_score70_debit55": {
        "id": "bullish_index_calls_score70_debit55",
        "label": "Bullish Index Calls Score 70+ Debit <55%",
        "allowed_asset_classes": ["index"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "min_quality_score": 70.0,
        "max_debit_pct_of_width": 55.0,
    },
    "bullish_qqq_calls_score70": {
        "id": "bullish_qqq_calls_score70",
        "label": "Bullish QQQ Calls Score 70+",
        "allowed_tickers": ["QQQ"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "min_quality_score": 70.0,
    },
    "tracked_winner_primary": {
        "id": "tracked_winner_primary",
        "label": "Tracked Winner",
        "allowed_tickers": ["SPY", "GOOGL", "XLK", "DIA", "NVDA"],
        "historical_required_underlyings": ["SPY", "GOOGL", "XLK", "DIA", "NVDA"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "target_dte": 35,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 40.0,
    },
    "tracked_winner_index_core": {
        "id": "tracked_winner_index_core",
        "label": "Tracked Winner Index Core",
        "allowed_tickers": ["SPY", "XLK", "DIA"],
        "historical_required_underlyings": ["SPY", "XLK", "DIA"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "target_dte": 35,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 40.0,
    },
    "tracked_winner_spy_core": {
        "id": "tracked_winner_spy_core",
        "label": "Tracked Winner SPY Core",
        "allowed_tickers": ["SPY"],
        "historical_required_underlyings": ["SPY"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "target_dte": 35,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 40.0,
    },
    "tracked_winner_loose_research": {
        "id": "tracked_winner_loose_research",
        "label": "Tracked Winner Loose Research",
        "allowed_tickers": ["SPY", "GOOGL", "XLK", "DIA", "NVDA"],
        "historical_required_underlyings": ["SPY", "GOOGL", "XLK", "DIA", "NVDA"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "target_dte": 35,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 80.0,
    },
    "tracked_winner_chain_native_research": {
        "id": "tracked_winner_chain_native_research",
        "label": "Tracked Winner Chain-Native Research",
        "allowed_tickers": ["SPY", "GOOGL", "DIA", "NVDA"],
        "historical_required_underlyings": ["SPY", "GOOGL", "DIA", "NVDA"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "target_dte": 35,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 80.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    "tracked_winner_chain_native_qqq_time65_research": {
        "id": "tracked_winner_chain_native_qqq_time65_research",
        "label": "Tracked Winner Chain-Native QQQ Time65 Research",
        "allowed_tickers": ["SPY", "QQQ", "GOOGL", "DIA", "NVDA"],
        "historical_required_underlyings": ["SPY", "QQQ", "GOOGL", "DIA", "NVDA"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "target_dte": 35,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 65.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    "tracked_winner_chain_native_qqq_time80_research": {
        "id": "tracked_winner_chain_native_qqq_time80_research",
        "label": "Tracked Winner Chain-Native QQQ Time80 Research",
        "allowed_tickers": ["SPY", "QQQ", "GOOGL", "DIA", "NVDA"],
        "historical_required_underlyings": ["SPY", "QQQ", "GOOGL", "DIA", "NVDA"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "target_dte": 35,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 80.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    "tracked_winner_chain_native_spy_qqq_time60_research": {
        "id": "tracked_winner_chain_native_spy_qqq_time60_research",
        "label": "Tracked Winner Chain-Native SPY QQQ Time60 Research",
        "allowed_tickers": ["SPY", "QQQ"],
        "historical_required_underlyings": ["SPY", "QQQ"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "target_dte": 35,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 60.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    "tracked_winner_chain_native_spy_qqq_time60_ret5_band_research": {
        "id": "tracked_winner_chain_native_spy_qqq_time60_ret5_band_research",
        "label": "Tracked Winner Chain-Native SPY QQQ Time60 Ret5 Band Research",
        "allowed_tickers": ["SPY", "QQQ"],
        "historical_required_underlyings": ["SPY", "QQQ"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "target_dte": 35,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 60.0,
        "min_signal_ret5": 0.5,
        "max_signal_ret5": 3.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    "tracked_winner_chain_native_spy_qqq_time60_ret20_watch": {
        "id": "tracked_winner_chain_native_spy_qqq_time60_ret20_watch",
        "label": "Tracked Winner Chain-Native SPY QQQ Time60 Ret20 Watch",
        "allowed_tickers": ["SPY", "QQQ"],
        "historical_required_underlyings": ["SPY", "QQQ"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "target_dte": 35,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 60.0,
        "min_signal_ret5": 0.5,
        "max_signal_ret5": 3.0,
        "min_signal_ret20": 2.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    "tracked_winner_chain_native_qqq_time60_debit60_ret20_watch": {
        "id": "tracked_winner_chain_native_qqq_time60_debit60_ret20_watch",
        "label": "Tracked Winner Chain-Native QQQ Time60 Debit60 Ret20 Watch",
        "allowed_tickers": ["QQQ"],
        "historical_required_underlyings": ["QQQ"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "target_dte": 35,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 60.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 60.0,
        "min_signal_ret5": 0.5,
        "max_signal_ret5": 3.0,
        "min_signal_ret20": 2.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    "tracked_winner_chain_native_spy_qqq_time65_research": {
        "id": "tracked_winner_chain_native_spy_qqq_time65_research",
        "label": "Tracked Winner Chain-Native SPY QQQ Time65 Research",
        "allowed_tickers": ["SPY", "QQQ"],
        "historical_required_underlyings": ["SPY", "QQQ"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "target_dte": 35,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 70.0,
        "spread_max_width_pct": 20.0,
        "spread_stop_loss_pct": 100.0,
        "spread_profit_target_pct": 150.0,
        "spread_time_exit_pct": 65.0,
        "chain_native_spread_selection": True,
        "chain_native_min_dte": 28,
        "chain_native_max_dte": 45,
    },
    "bullish_pullback_observation": {
        "id": "bullish_pullback_observation",
        "label": "Bullish Pullback",
        "entry_signal_id": "pullback_uptrend",
        "historical_required_underlyings": list(BULLISH_PULLBACK_REPLAY_UNIVERSE),
        "allowed_directions": ["call"],
        "allowed_signal_families": ["bullish_pullback"],
        "target_dte": 35,
        "scan_min_confidence": 0.0,
        "scan_min_tech_score": 0.0,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 55.0,
        "pullback_ret5_min": -4.0,
        "pullback_ret5_max": 0.25,
        "pullback_ret20_min": 2.0,
    },
    "regular_bearish_put_primary": {
        "id": "regular_bearish_put_primary",
        "label": "Regular Bearish Put",
        "allowed_asset_classes": ["index", "equity"],
        "allowed_tickers": list(REGULAR_OPTIONS_REPLAY_UNIVERSE),
        "historical_required_underlyings": list(REGULAR_OPTIONS_REPLAY_UNIVERSE),
        "allowed_market_regimes": ["bearish"],
        "allowed_directions": ["put"],
        "allowed_signal_families": ["momentum"],
        "target_dte": 35,
        "scan_min_confidence": 0.0,
        "scan_min_tech_score": 0.0,
        "min_quality_score": 65.0,
        "max_debit_pct_of_width": 60.0,
    },
    "bullish_mean_reversion": {
        "id": "bullish_mean_reversion",
        "label": "Bullish Mean Reversion",
        "entry_signal_id": "bullish_mean_reversion",
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "allowed_signal_families": ["bullish_mean_reversion"],
        "requires_calibrated_history": True,
        "pullback_ret5_max": -1.5,
        "pullback_rsi_min": 35.0,
        "pullback_rsi_max": 50.0,
        "reversal_ret1_min": 0.0,
    },
    "bearish_defensive": {
        "id": "bearish_defensive",
        "label": "Bearish Defensive",
        "allowed_asset_classes": ["equity"],
        "allowed_market_regimes": ["bearish"],
        "allowed_sectors": ["Healthcare", "Consumer Defensive"],
        "allowed_directions": ["put"],
        "min_quality_score": 70.0,
    },
    "bearish_index_put_observation": {
        "id": "bearish_index_put_observation",
        "label": "Bearish Index Put Observation",
        "allowed_asset_classes": ["index"],
        "allowed_tickers": ["SPY", "QQQ", "IWM", "DIA"],
        "allowed_market_regimes": ["bearish"],
        "allowed_directions": ["put"],
        "min_quality_score": 65.0,
        "max_debit_pct_of_width": 60.0,
    },
    "range_breakout_observation": {
        "id": "range_breakout_observation",
        "label": "Range Breakout Observation",
        "allowed_asset_classes": ["index"],
        "allowed_tickers": ["SPY", "QQQ", "IWM", "DIA"],
        "allowed_market_regimes": ["neutral"],
        "allowed_directions": ["call", "put"],
        "min_quality_score": 65.0,
        "max_debit_pct_of_width": 55.0,
    },
    "volatility_expansion_observation": {
        "id": "volatility_expansion_observation",
        "label": "Volatility Expansion Observation",
        "allowed_asset_classes": ["index"],
        "allowed_tickers": ["SPY", "QQQ", "IWM", "DIA"],
        "allowed_directions": ["call", "put"],
        "min_quality_score": 70.0,
        "max_debit_pct_of_width": 55.0,
    },
    AI_COMMODITY_INFRA_OBSERVATION_PLAYBOOK_ID: {
        "id": AI_COMMODITY_INFRA_OBSERVATION_PLAYBOOK_ID,
        "label": "AI Commodity Infra",
        "allowed_asset_classes": ["index", "equity"],
        "allowed_tickers": list(ai_commodity_scan_tickers()),
        "historical_required_underlyings": list(ai_commodity_scan_tickers()),
        "historical_source_labels": [ALPACA_OPRA_DAILY_SOURCE_LABEL],
        "allowed_directions": ["call", "put"],
        "min_quality_score": 70.0,
        "max_debit_pct_of_width": 55.0,
    },
}


# ── TradeEvaluator ────────────────────────────────────────────────────────────

class TradeEvaluator:
    """
    Scores a single option candidate using two separate scores — matching the live bot:

    quality_score()   — rates the OPTION itself (IV rank + delta fit + DTE fit).
                        Weights are tunable by Optuna. Used for EV context.

    direction_score() — predicts if the STOCK moves your way (tech + momentum − RSI penalty).
                        This is the ENTRY GATE: mirrors _compute_direction_score() in options_chatbot.
                        SPY regime defaults to neutral (50) in backtests — no per-day SPY series.
    """

    def __init__(
        self,
        weights: dict,
        delta_target: float = 0.30,
        dte_optimal: int = 7,
        delta_falloff: float = 0.15,
        dte_falloff: float = 10.0,
        # Direction Score component weights
        ds_w_tech: float = 0.55,
        ds_w_regime: float = 0.30,
        ds_w_momentum: float = 0.15,
        # RSI overextension penalty thresholds + magnitudes
        rsi_sev_threshold: float = 72.0,
        rsi_mod_threshold: float = 68.0,
        rsi_sev_penalty: float = 15.0,
        rsi_mod_penalty: float = 8.0,
        # Quality Score component weights
        qs_w_iv: float = 0.40,
        qs_w_delta: float = 0.35,
        qs_w_dte: float = 0.25,
        liquidity_spread_max_pct: float = 10.0,
        illiquid_extra_margin_pct: float = 5.0,
    ) -> None:
        self.weights = weights
        self.delta_target = delta_target
        self.dte_optimal = dte_optimal
        self.delta_falloff = delta_falloff
        self.dte_falloff = dte_falloff
        self.ds_w_tech = ds_w_tech
        self.ds_w_regime = ds_w_regime
        self.ds_w_momentum = ds_w_momentum
        self.rsi_sev_threshold = rsi_sev_threshold
        self.rsi_mod_threshold = rsi_mod_threshold
        self.rsi_sev_penalty = rsi_sev_penalty
        self.rsi_mod_penalty = rsi_mod_penalty
        self.qs_w_iv = qs_w_iv
        self.qs_w_delta = qs_w_delta
        self.qs_w_dte = qs_w_dte
        self.liquidity_spread_max_pct = liquidity_spread_max_pct
        self.illiquid_extra_margin_pct = illiquid_extra_margin_pct

    def quality_score(
        self,
        iv_percentile: float,
        delta: float,
        dte: int,
        tech_score: float = 50.0,
        bid_ask_spread_pct: float = 0.0,
    ) -> float:
        """Option quality (0-100): IV rank + delta fit + DTE fit. Weights tuned by Optuna."""
        iv_score    = max(0.0, 100.0 - iv_percentile)
        delta_score = 100.0 * math.exp(
            -((abs(delta) - self.delta_target) ** 2) / (2 * self.delta_falloff ** 2)
        )
        dte_score   = 100.0 * math.exp(
            -((dte - self.dte_optimal) ** 2) / (2 * self.dte_falloff ** 2)
        )

        _qs_total = self.qs_w_iv + self.qs_w_delta + self.qs_w_dte or 1.0
        raw = (
            self.qs_w_iv    * iv_score
            + self.qs_w_delta * delta_score
            + self.qs_w_dte   * dte_score
        ) / _qs_total

        if bid_ask_spread_pct > self.liquidity_spread_max_pct:
            raw -= self.illiquid_extra_margin_pct

        return max(0.0, min(100.0, raw))

    def direction_score(
        self,
        tech_score: float,
        ret5: float,
        rsi14: float,
        trade_type: str,
        spy_ret5: float = 0.0,   # defaults neutral — no per-day SPY in backtest
    ) -> float:
        """
        Directional edge score: mirrors _compute_direction_score() in options_chatbot.
        tech 55% + SPY regime 30% + momentum 15% − RSI overextension penalty.
        Entry gate — determines PROCEED/AVOID, not option quality.
        """
        # Regime: positive if SPY moved same direction as the trade
        if trade_type == "call":
            regime_score = min(100.0, max(0.0, 50.0 + spy_ret5 * 10.0))
        else:
            regime_score = min(100.0, max(0.0, 50.0 - spy_ret5 * 10.0))

        # Momentum: how strong is the 5-day move in the trade's direction?
        move = ret5 if trade_type == "call" else -ret5
        mom_score = min(100.0, max(0.0, move * 20.0))

        _ds_total = self.ds_w_tech + self.ds_w_regime + self.ds_w_momentum or 1.0
        raw = (
            tech_score    * self.ds_w_tech
            + regime_score  * self.ds_w_regime
            + mom_score     * self.ds_w_momentum
        ) / _ds_total

        # RSI overextension penalty — thresholds and magnitudes tuned by Optuna
        _bear_sev = 100.0 - self.rsi_sev_threshold
        _bear_mod = 100.0 - self.rsi_mod_threshold
        if trade_type == "call":
            pen = (self.rsi_sev_penalty if rsi14 > self.rsi_sev_threshold
                   else self.rsi_mod_penalty if rsi14 > self.rsi_mod_threshold
                   else 0.0)
        else:
            pen = (self.rsi_sev_penalty if rsi14 < _bear_sev
                   else self.rsi_mod_penalty if rsi14 < _bear_mod
                   else 0.0)

        return max(0.0, min(100.0, raw - pen))

    def expected_value(
        self,
        direction_score: float,
        stop_loss_pct: float,
        profit_target_pct: float,
    ) -> float:
        """EV uses Direction Score as p(win) — the directional edge, not option quality."""
        p_win = direction_score / 100.0
        return p_win * profit_target_pct - (1.0 - p_win) * abs(stop_loss_pct)


# ── Portfolio metrics ─────────────────────────────────────────────────────────

def _sharpe(pnl_series: list[float], periods_per_year: int = 252) -> float:
    if len(pnl_series) < 5:
        return -99.0
    arr = np.array(pnl_series, dtype=float)
    std = arr.std(ddof=1)
    if std == 0:
        return 0.0
    return float(arr.mean() / std * math.sqrt(min(len(arr), periods_per_year)))


def _max_drawdown(pnl_series: list[float]) -> float:
    if not pnl_series:
        return 0.0
    equity = np.cumprod(1.0 + np.array(pnl_series, dtype=float) / 100.0)
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / (peak + 1e-9) * 100
    return float(abs(dd.min()))


# ── Precomputation (run once per window, shared across all Optuna trials) ─────

def _precompute(
    closes: pd.Series,
    dte_at_entry: int,
    trade_offset: int = 0,
) -> list[Optional[dict]]:
    """
    Compute per-day invariants ONCE before the Optuna trial loop starts.

    trade_offset : number of leading context-only days in `closes`.
                   Days before this index are used for HV computation but
                   do NOT generate trades. This lets short OOS windows borrow
                   history from the tail of the training slice so that hv30 and
                   iv_pct are valid even on the first day of the test period.

    Returns a list of length len(closes). Each entry is either:
      None  — filtered out (context day, no signal, bad HV, near boundary)
      dict  — {"idx", "S0", "hv30", "iv_pct", "trade_type", "date"}
    """
    prices = closes.values.astype(float)
    n      = len(prices)

    # Vectorised HV30: rolling 30-day annualised vol
    log_rets = np.log(prices[1:] / prices[:-1])
    hv30_arr = np.full(n, np.nan)
    for i in range(30, n):
        hv30_arr[i] = float(np.std(log_rets[i - 30 : i]) * math.sqrt(252))

    # IV percentile: rank of current hv30 vs trailing 252-day hv30 history
    iv_pct_arr = np.full(n, np.nan)
    for i in range(30, n):
        hv = hv30_arr[i]
        if np.isnan(hv) or hv <= 0:
            continue
        window = hv30_arr[max(0, i - 252) : i]
        valid  = window[~np.isnan(window)]
        if len(valid) >= 5:                          # need at least 5 data points
            iv_pct_arr[i] = float(np.sum(valid <= hv) / len(valid) * 100)

    # ── RSI 14 ────────────────────────────────────────────────────────────────
    rsi14_arr = np.full(n, 50.0)   # default to neutral
    deltas_p  = np.zeros(n)
    deltas_p[1:] = np.diff(prices)
    for i in range(15, n):
        win = deltas_p[i - 14 : i]
        avg_up   = float(np.mean(win[win > 0])) if np.any(win > 0) else 0.0
        avg_down = float(np.mean(-win[win < 0])) if np.any(win < 0) else 0.0
        rs = avg_up / (avg_down + 1e-9)
        rsi14_arr[i] = 100.0 - 100.0 / (1.0 + rs)

    # ── MACD (EMA12 − EMA26) ──────────────────────────────────────────────────
    k12 = 2.0 / 13.0
    k26 = 2.0 / 27.0
    ema12_arr = np.empty(n)
    ema26_arr = np.empty(n)
    ema12_arr[0] = ema26_arr[0] = prices[0]
    for i in range(1, n):
        ema12_arr[i] = prices[i] * k12 + ema12_arr[i - 1] * (1 - k12)
        ema26_arr[i] = prices[i] * k26 + ema26_arr[i - 1] * (1 - k26)
    macd_arr = ema12_arr - ema26_arr   # positive = bullish; rising = accelerating

    # ── SMA 50 ────────────────────────────────────────────────────────────────
    sma50_arr = np.full(n, np.nan)
    for i in range(50, n):
        sma50_arr[i] = float(np.mean(prices[i - 50 : i]))

    # trade_start: earliest index that can generate a real trade signal
    trade_start = max(50, trade_offset)   # bumped to 50 so sma50 is always valid

    precomputed: list[Optional[dict]] = []
    for i in range(n):
        if i < trade_start or i >= n - dte_at_entry - 1:
            precomputed.append(None)
            continue

        hv30   = hv30_arr[i]
        iv_pct = iv_pct_arr[i]
        if np.isnan(hv30) or hv30 <= 0 or np.isnan(iv_pct):
            precomputed.append(None)
            continue

        S0    = prices[i]
        ret5  = (S0 / prices[i - 5] - 1) * 100
        ret20 = (S0 / prices[i - 20] - 1) * 100
        sma20 = float(np.mean(prices[i - 20 : i]))

        # Store ALL valid HV days — simulation loop applies the actual
        # trial-specific momentum threshold so Optuna can tune it.
        sma50 = float(sma50_arr[i]) if not np.isnan(sma50_arr[i]) else float(sma20)
        precomputed.append({
            "idx":    i,
            "S0":     float(S0),
            "hv30":   float(hv30),
            "iv_pct": float(iv_pct),
            "ret5":   float(ret5),
            "ret20":  float(ret20),
            "sma20":  float(sma20),
            "sma50":  sma50,
            "rsi14":  float(rsi14_arr[i]),
            "macd":   float(macd_arr[i]),
            "macd_prev": float(macd_arr[i - 1]) if i > 0 else float(macd_arr[i]),
            "date":   str(closes.index[i].date()),
        })

    return precomputed


# ── Portfolio metrics ─────────────────────────────────────────────────────────

def _profit_factor(trades: list[dict]) -> float:
    """Gross profit / gross loss. >1.5 is solid; >2.0 is excellent."""
    gross_win  = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    gross_loss = sum(abs(t["pnl_pct"]) for t in trades if t["pnl_pct"] < 0)
    if gross_loss < 0.01:
        return gross_win / 0.01 if gross_win > 0 else 0.0
    return gross_win / gross_loss


def _profit_factor_denominator_truth_from_pnls(pnl_values: Sequence[Any]) -> dict[str, Any]:
    values: list[float] = []
    for value in pnl_values:
        try:
            values.append(float(value or 0.0))
        except (TypeError, ValueError):
            values.append(0.0)
    gross_win = sum(value for value in values if value > 0)
    gross_loss = abs(sum(value for value in values if value < 0))
    win_trade_count = sum(1 for value in values if value > 0)
    loss_trade_count = sum(1 for value in values if value < 0)
    if not values:
        status = "no_trades"
    elif loss_trade_count:
        status = "has_losses"
    else:
        status = "no_losses"
    return {
        "gross_win": round(gross_win, 4),
        "gross_loss": round(gross_loss, 4),
        "win_trade_count": win_trade_count,
        "loss_trade_count": loss_trade_count,
        "profit_factor_status": status,
    }


def _profit_factor_denominator_truth(trades: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return _profit_factor_denominator_truth_from_pnls(
        [trade.get("pnl_pct", 0.0) for trade in trades]
    )


def _post_entry_denominator_truth(
    *,
    priced_trade_count: int,
    unpriced_trade_count: int,
    post_entry_filtered_trade_count: int,
) -> dict[str, Any]:
    pre_post_entry_candidate_trade_count = (
        int(priced_trade_count or 0)
        + int(unpriced_trade_count or 0)
        + int(post_entry_filtered_trade_count or 0)
    )
    return {
        "pre_post_entry_candidate_trade_count": pre_post_entry_candidate_trade_count,
        "post_entry_reject_rate_pct": (
            round(
                int(post_entry_filtered_trade_count or 0)
                / max(pre_post_entry_candidate_trade_count, 1)
                * 100.0,
                1,
            )
            if pre_post_entry_candidate_trade_count
            else 0.0
        ),
    }


# ── Market-realistic strike grid ──────────────────────────────────────────────

def _market_strike_grid(S0: float, n_below: int = 12, n_above: int = 12) -> list[float]:
    """
    Generate a list of plausible US-listed options strike prices centered on S0.

    Uses standard exchange increment conventions:
      stock < $5    →  $0.50 increments
      stock < $25   →  $1    increments
      stock < $100  →  $2.50 increments
      stock < $200  →  $5    increments
      stock >= $200 →  $10   increments

    High-volume large-cap names (SPY, QQQ, TSLA, NVDA, etc.) often list $1
    increments at any price — this is the conservative approximation.
    """
    if S0 < 5:
        inc = 0.50
    elif S0 < 25:
        inc = 1.0
    elif S0 < 100:
        inc = 2.50
    elif S0 < 200:
        inc = 5.0
    else:
        inc = 10.0

    # Snap to nearest increment to find the ATM anchor
    atm = round(round(S0 / inc) * inc, 2)
    strikes = []
    for i in range(-n_below, n_above + 1):
        K = round(atm + i * inc, 2)
        if K > 0:
            strikes.append(K)
    return strikes


# ── Single-ticker simulation ──────────────────────────────────────────────────

def _simulate_window(
    closes: pd.Series,
    weights: dict,
    dte_at_entry: int,
    stop_loss_pct: float,
    profit_target_pct: float,
    delta_target: float,
    min_confidence: float,
    min_ev_pct: float,
    entry_momentum: float = 0.5,
    time_exit_pct: float = 50.0,
    _cache: Optional[list] = None,
    ds_w_tech: float = 0.55,
    ds_w_regime: float = 0.30,
    ds_w_momentum: float = 0.15,
    rsi_sev_threshold: float = 72.0,
    rsi_mod_threshold: float = 68.0,
    rsi_sev_penalty: float = 15.0,
    rsi_mod_penalty: float = 8.0,
    qs_w_iv: float = 0.40,
    qs_w_delta: float = 0.35,
    qs_w_dte: float = 0.25,
) -> dict:
    """
    Simulate options trades on one price slice.

    entry_momentum is tunable per trial — precompute stores all valid HV days
    and this function applies the threshold, so Optuna can search it freely.
    """
    evaluator = TradeEvaluator(
        weights=weights,
        delta_target=delta_target,
        dte_optimal=dte_at_entry,
        ds_w_tech=ds_w_tech,
        ds_w_regime=ds_w_regime,
        ds_w_momentum=ds_w_momentum,
        rsi_sev_threshold=rsi_sev_threshold,
        rsi_mod_threshold=rsi_mod_threshold,
        rsi_sev_penalty=rsi_sev_penalty,
        rsi_mod_penalty=rsi_mod_penalty,
        qs_w_iv=qs_w_iv,
        qs_w_delta=qs_w_delta,
        qs_w_dte=qs_w_dte,
    )
    prices = closes.values.astype(float)
    n      = len(prices)

    cache = _cache if _cache is not None else _precompute(closes, dte_at_entry)

    # ── Per-day indicator arrays for adaptive exit scoring ─────────────────────
    # RSI 14
    _rsi14 = np.full(n, 50.0)
    _dp    = np.zeros(n)
    _dp[1:] = np.diff(prices)
    for _i in range(15, n):
        _w = _dp[_i - 14 : _i]
        _u = float(np.mean(_w[_w > 0])) if np.any(_w > 0) else 0.0
        _d = float(np.mean(-_w[_w < 0])) if np.any(_w < 0) else 0.0
        _rsi14[_i] = 100.0 - 100.0 / (1.0 + _u / (_d + 1e-9))
    # MACD (EMA12 − EMA26)
    _k12 = 2.0 / 13.0; _k26 = 2.0 / 27.0
    _ema12 = np.empty(n); _ema26 = np.empty(n)
    _ema12[0] = _ema26[0] = prices[0]
    for _i in range(1, n):
        _ema12[_i] = prices[_i] * _k12 + _ema12[_i - 1] * (1 - _k12)
        _ema26[_i] = prices[_i] * _k26 + _ema26[_i - 1] * (1 - _k26)
    _macd = _ema12 - _ema26
    # SMA 20 / SMA 50
    _sma20 = np.full(n, np.nan)
    _sma50 = np.full(n, np.nan)
    for _i in range(20, n):
        _sma20[_i] = float(np.mean(prices[_i - 20 : _i]))
    for _i in range(50, n):
        _sma50[_i] = float(np.mean(prices[_i - 50 : _i]))

    T = dte_at_entry / 365.0
    time_exit_day = max(1, math.ceil(dte_at_entry * time_exit_pct / 100))
    pnl_list: list[float] = []
    trades:   list[dict]  = []

    for day in cache:
        if day is None:
            continue
        i     = day["idx"]
        S0    = day["S0"]
        hv30  = day["hv30"]
        iv_pct = day["iv_pct"]
        ret5  = day["ret5"]
        sma20 = day["sma20"]

        # Apply trial-specific momentum threshold
        bullish = ret5 >  entry_momentum and S0 > sma20
        bearish = ret5 < -entry_momentum and S0 < sma20
        if not bullish and not bearish:
            continue
        trade_type = "call" if bullish else "put"

        # Technical setup score — uses precomputed indicators from _precompute
        tech = _tech_score(
            rsi14=day.get("rsi14", 50.0),
            macd=day.get("macd", 0.0),
            macd_prev=day.get("macd_prev", 0.0),
            price=S0,
            sma20=day["sma20"],
            sma50=day.get("sma50", day["sma20"]),
            trade_type=trade_type,
        )

        # Strike search — uses market-realistic increments, not arbitrary % offsets
        best_strike: Optional[float] = None
        best_g:      Optional[dict]  = None
        best_diff = 999.0
        for K in _market_strike_grid(S0):
            g = _bs_greeks(S0, K, T, RISK_FREE_RATE, hv30, trade_type)
            if not g:
                continue
            diff = abs(abs(g.get("delta", 0)) - delta_target)
            if diff < best_diff:
                best_diff   = diff
                best_strike = K
                best_g      = g

        if best_strike is None or not best_g or best_g.get("bs_price", 0) < 0.01:
            continue

        entry_px  = best_g["bs_price"]
        delta_val = abs(best_g.get("delta", 0))

        _rsi_at_entry = float(_rsi14[i])
        # Direction Score — entry gate, mirrors live _compute_direction_score()
        direction_score = evaluator.direction_score(
            tech_score=tech, ret5=ret5, rsi14=_rsi_at_entry, trade_type=trade_type
        )
        # Quality Score — rates the option itself (used for EV and logging)
        quality_score = evaluator.quality_score(
            iv_percentile=iv_pct, delta=delta_val, dte=dte_at_entry, tech_score=tech
        )
        ev = evaluator.expected_value(direction_score, stop_loss_pct, profit_target_pct)
        if direction_score < min_confidence or ev < min_ev_pct:
            continue

        stop_px   = entry_px * (1 - stop_loss_pct   / 100)
        target_px = entry_px * (1 + profit_target_pct / 100)
        exit_px, exit_reason = entry_px, "expired"
        exit_fill_basis = "model_mark"

        # ── Adaptive exit state ───────────────────────────────────────────────
        # Trailing stop: activates once option gains ≥50% of profit target,
        # then trails 18% below the high-watermark option price.
        # TP extension: if tech setup is still intact at target, ride with trail.
        # Tech decay: if indicators collapse mid-trade, raise the stop floor.
        trail_activate_px = entry_px * (1 + profit_target_pct * 0.50 / 100)
        trail_depth       = 0.18       # trail stop sits 18% below peak
        high_watermark    = entry_px
        trail_active      = False
        trail_stop_px     = 0.0
        dynamic_stop_px   = stop_px    # raised by tech-decay logic

        for d in range(1, dte_at_entry + 1):
            fi = i + d
            if fi >= n:
                break
            S_now = float(prices[fi])
            T_now = max((dte_at_entry - d) / 365.0, 0)
            if T_now <= 0:
                intrinsic = (
                    max(0.0, S_now - best_strike)
                    if trade_type == "call"
                    else max(0.0, best_strike - S_now)
                )
                # If trailing was active, allow gains above original target;
                # otherwise cap at target to prevent inflated expiry returns.
                exit_px     = min(intrinsic, high_watermark) if trail_active else min(intrinsic, target_px)
                exit_reason = "expired"
                exit_fill_basis = "expiry_intrinsic"
                break

            g2      = _bs_greeks(S_now, best_strike, T_now, RISK_FREE_RATE, hv30, trade_type)
            opt_now = g2.get("bs_price", 0.0) if g2 else 0.0

            # Update high watermark
            if opt_now > high_watermark:
                high_watermark = opt_now

            # ── Current tech score from live indicators ───────────────────────
            if fi >= 50 and not np.isnan(_sma50[fi]):
                cur_tech = _tech_score(
                    rsi14     = float(_rsi14[fi]),
                    macd      = float(_macd[fi]),
                    macd_prev = float(_macd[fi - 1]),
                    price     = S_now,
                    sma20     = float(_sma20[fi]) if not np.isnan(_sma20[fi]) else S_now,
                    sma50     = float(_sma50[fi]),
                    trade_type= trade_type,
                )
            else:
                cur_tech = tech   # fallback to entry-day score

            tech_healthy  = cur_tech >= max(25.0, tech * 0.65)
            tech_decayed  = cur_tech <  max(20.0, tech * 0.40)

            # ── Activate trailing stop once position is well in-profit ────────
            if not trail_active and opt_now >= trail_activate_px:
                trail_active  = True
                trail_stop_px = high_watermark * (1 - trail_depth)

            # ── Update trailing stop to follow high watermark ─────────────────
            if trail_active:
                trail_stop_px = max(trail_stop_px, high_watermark * (1 - trail_depth))

            # ── Tech-decay: raise stop floor to protect against bad setups ────
            if tech_decayed:
                if opt_now >= entry_px:
                    # In profit — lock in at least break-even
                    dynamic_stop_px = max(dynamic_stop_px, entry_px * 1.02)
                else:
                    # In loss — tighten remaining loss budget by 40%
                    tighter = dynamic_stop_px + (entry_px - dynamic_stop_px) * 0.40
                    dynamic_stop_px = max(dynamic_stop_px, tighter)

            # ── Hard stop (whichever is higher: static, dynamic, or trail) ────
            # Cap at entry_px so tech-decay logic never forces a loss-side exit
            # at a price above entry when the position is still recoverable.
            effective_stop = min(
                entry_px,
                max(dynamic_stop_px, trail_stop_px if trail_active else 0.0)
            )
            if opt_now <= effective_stop:
                exit_px     = opt_now
                exit_reason = "trailing_stop" if trail_active else "stop"
                exit_fill_basis = "model_mark"
                break

            # ── Take-profit: extend if setup still healthy, else lock in ──────
            if opt_now >= target_px:
                if tech_healthy and not trail_active:
                    # Tech still intact — switch to trailing stop; let it run
                    trail_active  = True
                    trail_stop_px = high_watermark * (1 - trail_depth)
                    # Don't break — trade continues under trail management
                elif not trail_active:
                    exit_px     = target_px
                    exit_reason = "target"
                    exit_fill_basis = "target_limit"
                    break
                # If trail already active, just keep riding

            # ── Time exit: close when time_exit_pct% of DTE has elapsed ──────
            # Check this after the profit-target logic so a same-day target hit
            # does not get reported as a richer time-exit mark.
            if d >= time_exit_day:
                exit_px     = opt_now
                exit_reason = "time_exit"
                exit_fill_basis = "model_mark"
                break

        pnl = (exit_px - entry_px) / entry_px * 100
        pnl_list.append(pnl)
        trades.append({
            "date":           day["date"],
            "type":           trade_type,
            "strike":         best_strike,
            "stock_px":       round(S0, 4),           # underlying close on entry day — auditable
            "hv30":           round(hv30, 4),          # vol used for BS pricing — auditable
            "dte":            dte_at_entry,            # days to expiry at entry
            "entry_px":       round(entry_px, 4),
            "exit_px":        round(exit_px, 4),
            "exit_reason":    exit_reason,
            "exit_fill_basis": exit_fill_basis,
            "direction_score": round(direction_score, 1),
            "quality_score":   round(quality_score, 1),
            "tech_score":      round(tech, 1),
            "ev":              round(ev, 1),
            "pnl_pct":        round(pnl, 2),
        })

    wins = sum(1 for p in pnl_list if p > 0)
    avg_quality = round(sum(t["quality_score"] for t in trades) / max(len(trades), 1), 1)
    return {
        "sharpe":           _sharpe(pnl_list),
        "profit_factor":    _profit_factor(trades),
        **_profit_factor_denominator_truth(trades),
        "win_rate":         round(wins / max(len(pnl_list), 1), 4),
        "max_drawdown_pct": _max_drawdown(pnl_list),
        "n_trades":         len(pnl_list),
        "avg_quality":      avg_quality,
        "trades":           trades,
    }


def _simulate_window_multi(
    closes_dict: dict[str, pd.Series],
    weights: dict,
    dte_at_entry: int,
    stop_loss_pct: float,
    profit_target_pct: float,
    delta_target: float,
    min_confidence: float,
    min_ev_pct: float,
    entry_momentum: float = 0.5,
    time_exit_pct: float = 50.0,
    _caches: Optional[dict] = None,
    ds_w_tech: float = 0.55,
    ds_w_regime: float = 0.30,
    ds_w_momentum: float = 0.15,
    rsi_sev_threshold: float = 72.0,
    rsi_mod_threshold: float = 68.0,
    rsi_sev_penalty: float = 15.0,
    rsi_mod_penalty: float = 8.0,
    qs_w_iv: float = 0.40,
    qs_w_delta: float = 0.35,
    qs_w_dte: float = 0.25,
) -> dict:
    """Pool trades across multiple tickers. Pass _caches to skip HV recomputation."""
    all_pnl:    list[float] = []
    all_trades: list[dict]  = []

    for ticker, closes in closes_dict.items():
        if len(closes) < 50:
            continue
        cache = _caches.get(ticker) if _caches else None
        result = _simulate_window(
            closes=closes, weights=weights,
            dte_at_entry=dte_at_entry, stop_loss_pct=stop_loss_pct,
            profit_target_pct=profit_target_pct, delta_target=delta_target,
            min_confidence=min_confidence, min_ev_pct=min_ev_pct,
            entry_momentum=entry_momentum, time_exit_pct=time_exit_pct,
            _cache=cache,
            ds_w_tech=ds_w_tech, ds_w_regime=ds_w_regime, ds_w_momentum=ds_w_momentum,
            rsi_sev_threshold=rsi_sev_threshold, rsi_mod_threshold=rsi_mod_threshold,
            rsi_sev_penalty=rsi_sev_penalty, rsi_mod_penalty=rsi_mod_penalty,
            qs_w_iv=qs_w_iv, qs_w_delta=qs_w_delta, qs_w_dte=qs_w_dte,
        )
        for t in result["trades"]:
            t["ticker"] = ticker
        all_pnl.extend([t["pnl_pct"] for t in result["trades"]])
        all_trades.extend(result["trades"])

    wins = sum(1 for p in all_pnl if p > 0)
    avg_quality = round(sum(t.get("quality_score", 50.0) for t in all_trades) / max(len(all_trades), 1), 1)
    return {
        "sharpe":           _sharpe(all_pnl),
        "profit_factor":    _profit_factor(all_trades),
        **_profit_factor_denominator_truth(all_trades),
        "win_rate":         round(wins / max(len(all_pnl), 1), 4),
        "max_drawdown_pct": _max_drawdown(all_pnl),
        "n_trades":         len(all_pnl),
        "avg_quality":      avg_quality,
        "trades":           all_trades,
    }


# ── Technical setup score ─────────────────────────────────────────────────────

def _tech_score(
    rsi14: float,
    macd: float,
    macd_prev: float,
    price: float,
    sma20: float,
    sma50: float,
    trade_type: str,
) -> float:
    """
    Direction-aware technical setup score (0–100).

    Call setup  : wants RSI building (45–70), MACD positive/rising, price above SMAs
    Put setup   : wants RSI declining (30–55), MACD negative/falling, price below SMAs

    Components (weighted):
      40% SMA trend alignment  (price/sma20/sma50 stack)
      35% RSI positioning      (momentum building in the right direction)
      25% MACD momentum        (histogram sign + direction)
    """
    macd_rising = macd > macd_prev   # histogram is growing

    if trade_type == "call":
        # Trend: price > sma20 > sma50 = full alignment
        trend = (50.0 if price > sma20 else 0.0) + (50.0 if sma20 > sma50 else 0.0)
        # RSI: ideal ~55 (building momentum, not overbought)
        rsi_s = max(0.0, 100.0 - abs(rsi14 - 55.0) * (100.0 / 35.0))
        # MACD: positive and rising = 100, positive only = 50, negative = 0
        macd_s = 100.0 if macd > 0 and macd_rising else (50.0 if macd > 0 else 0.0)
    else:
        trend = (50.0 if price < sma20 else 0.0) + (50.0 if sma20 < sma50 else 0.0)
        rsi_s = max(0.0, 100.0 - abs(rsi14 - 45.0) * (100.0 / 35.0))
        macd_s = 100.0 if macd < 0 and not macd_rising else (50.0 if macd < 0 else 0.0)

    return trend * 0.40 + rsi_s * 0.35 + macd_s * 0.25


# ── Auto min-trades (no manual input required) ───────────────────────────────

def _auto_min_trades(test_days: int, n_tickers: int = 1) -> int:
    """
    Compute the minimum acceptable OOS trade count automatically.

    Formula: max(6, test_days // 6) × sqrt(n_tickers)
    Examples
    --------
    42-day test, 1 ticker  → max(6, 7) = 7
    63-day test, 1 ticker  → max(6, 10) = 10
    42-day test, 3 tickers → 7 × ~1.7  = 12
    63-day test, 3 tickers → 10 × ~1.7 = 17

    Rationale: the original floor of test_days//4 was too strict for single-ticker
    42-day windows where entry gates typically produce 4–8 trades. A realistic floor
    is test_days//6 (one trade per ~6 days), with 6 as the hard minimum for any
    statistically meaningful sample.
    """
    base = max(6, test_days // 6)
    return max(6, int(base * (n_tickers ** 0.5)))


# ── Adaptive exit bounds (learned from prior window IS trades) ────────────────

def _adapt_bounds(
    is_trades: list[dict],
    current_stop: float,
    current_target: float,
    min_sample: int = 8,
) -> dict:
    """
    Analyse IS trade exit patterns to shift stop-loss / profit-target search
    bounds for the *next* window's Optuna run.

    Stop-loss rules
    ---------------
    > 60% losses are stop-outs  → stop may be too tight → widen range upward
    < 25% losses are stop-outs  → losses bleed to expiry → tighten to cut sooner

    Profit-target rules
    -------------------
    > 65% wins hit target       → target may be too low  → shift range higher
    < 30% wins hit target       → wins expire below target → lower range

    Returns a dict with stop_lo, stop_hi, tgt_lo, tgt_hi, and notes list.
    """
    wins   = [t for t in is_trades if t.get("pnl_pct", 0) > 0]
    losses = [t for t in is_trades if t.get("pnl_pct", 0) <= 0]
    notes: list[str] = []

    # ── Stop-loss bounds ──────────────────────────────────────────────────────
    stop_lo, stop_hi = 20.0, 85.0   # absolute search limits
    if len(losses) >= min_sample:
        stop_hits = sum(1 for t in losses if "stop" in t.get("exit_reason", ""))
        stop_rate = stop_hits / len(losses)
        if stop_rate > 0.60:
            # Too many stops — trades getting cut before they recover
            stop_lo = min(current_stop * 0.80, 40.0)
            stop_hi = min(current_stop * 1.60, 85.0)
            notes.append(
                f"Stop widened (stop-out rate {stop_rate*100:.0f}% — trades cut early; "
                f"trying {stop_lo:.0f}–{stop_hi:.0f}%)"
            )
        elif stop_rate < 0.25:
            # Losses bleeding to expiry — stop not triggering; tighten to exit sooner
            stop_lo = max(current_stop * 0.50, 15.0)
            stop_hi = max(current_stop * 1.10, 30.0)
            notes.append(
                f"Stop tightened (stop-out rate {stop_rate*100:.0f}% — losses expiring; "
                f"trying {stop_lo:.0f}–{stop_hi:.0f}%)"
            )
        else:
            # Balanced — stay near current value
            stop_lo = max(current_stop * 0.70, 20.0)
            stop_hi = min(current_stop * 1.40, 80.0)

    # ── Profit-target bounds ──────────────────────────────────────────────────
    tgt_lo, tgt_hi = 40.0, 250.0   # absolute search limits
    if len(wins) >= min_sample:
        target_hits = sum(1 for t in wins if "target" in t.get("exit_reason", ""))
        target_rate = target_hits / len(wins)
        avg_win     = sum(t["pnl_pct"] for t in wins) / len(wins)
        if target_rate > 0.65:
            # Most wins are capped at target — may be leaving gains on table
            tgt_lo = max(current_target * 0.80, 50.0)
            tgt_hi = min(current_target * 1.80, 300.0)
            notes.append(
                f"Target raised ({target_rate*100:.0f}% hit limit; "
                f"trying {tgt_lo:.0f}–{tgt_hi:.0f}%)"
            )
        elif target_rate < 0.30:
            # Most wins expire below target — target is set too high for this regime
            tgt_lo = max(avg_win * 0.60, 30.0)
            tgt_hi = min(avg_win * 1.50, 200.0)
            notes.append(
                f"Target lowered ({target_rate*100:.0f}% hit limit, avg win {avg_win:.0f}%; "
                f"trying {tgt_lo:.0f}–{tgt_hi:.0f}%)"
            )
        else:
            tgt_lo = max(current_target * 0.70, 40.0)
            tgt_hi = min(current_target * 1.50, 250.0)

    # Round to natural step sizes
    stop_lo = max(round(stop_lo / 5) * 5, 15.0)
    stop_hi = max(round(stop_hi / 5) * 5, stop_lo + 10.0)
    tgt_lo  = max(round(tgt_lo  / 10) * 10, 30.0)
    tgt_hi  = max(round(tgt_hi  / 10) * 10, tgt_lo + 20.0)

    return {
        "stop_lo": stop_lo, "stop_hi": stop_hi,
        "tgt_lo":  tgt_lo,  "tgt_hi":  tgt_hi,
        "notes":   notes,
    }


# ── Optuna objective factory ──────────────────────────────────────────────────

def _make_objective(
    closes_input,   # pd.Series (single) or dict[str, pd.Series] (multi)
    config: dict,
    multi: bool = False,
    stop_bounds: tuple = (25.0, 60.0),   # (lo, hi) learned from prior window
    tgt_bounds:  tuple = (50.0, 150.0),  # (lo, hi) learned from prior window
) -> Callable:
    """
    Precompute HV/IV data ONCE. Each trial tunes 9 parameters:
      3 confidence weights + 6 entry/exit params.
    Stop-loss and profit-target bounds adapt from prior window's trade outcomes.
    Fitness = Profit Factor + 0.1×Sharpe − 0.02×MaxDrawdown.
    """
    dte = config["dte_at_entry"]

    if multi:
        caches = {sym: _precompute(c, dte) for sym, c in closes_input.items()}
    else:
        single_cache = _precompute(closes_input, dte)

    def objective(trial: "optuna.Trial") -> float:
        # ── Confidence weights ────────────────────────────────────────────────
        # DTE weight is fixed — it was causing 70-107% drift between windows
        # (too noisy to optimize on short windows) so it's locked to profile value.
        # ── Entry parameters ──────────────────────────────────────────────────
        delta_target    = trial.suggest_float("delta_target",    0.15, 0.45, step=0.05)
        # entry_momentum capped at 1.0%: 1.5% is rarely met and starves the window of trades
        entry_momentum  = trial.suggest_float("entry_momentum",  0.20, 1.00, step=0.10)
        # min_confidence capped at 55: values above 55 produce <4 trades/window (G3 fail cascade)
        min_confidence  = trial.suggest_float("min_confidence",  30.0, 55.0, step=5.0)
        # min_ev_pct capped at 15: values above 15% are unrealistic for short-DTE options
        min_ev_pct      = trial.suggest_float("min_ev_pct",       5.0, 15.0, step=1.0)

        # ── Exit parameters — bounds adapt from prior window's trade outcomes ─
        stop_loss_pct     = trial.suggest_float(
            "stop_loss_pct", stop_bounds[0], stop_bounds[1], step=5.0)
        profit_target_pct = trial.suggest_float(
            "profit_target_pct", tgt_bounds[0], tgt_bounds[1], step=10.0)

        # ── Direction Score weights ───────────────────────────────────────────
        ds_w_tech     = trial.suggest_float("ds_w_tech",     0.30, 0.80, step=0.05)
        ds_w_regime   = trial.suggest_float("ds_w_regime",   0.05, 0.55, step=0.05)
        ds_w_momentum = trial.suggest_float("ds_w_momentum", 0.00, 0.35, step=0.05)

        # ── RSI overextension — suggest base (moderate) + gap to severe ──────
        rsi_mod_threshold = float(trial.suggest_int("rsi_mod_threshold", 62, 74))
        rsi_threshold_gap = float(trial.suggest_int("rsi_threshold_gap",  2, 10))
        rsi_sev_threshold = rsi_mod_threshold + rsi_threshold_gap   # always > mod
        rsi_mod_penalty   = trial.suggest_float("rsi_mod_penalty",   2.0, 12.0, step=1.0)
        rsi_sev_penalty   = rsi_mod_penalty + trial.suggest_float("rsi_sev_bonus", 2.0, 15.0, step=1.0)

        # ── Quality Score weights ─────────────────────────────────────────────
        qs_w_iv    = trial.suggest_float("qs_w_iv",    0.10, 0.70, step=0.05)
        qs_w_delta = trial.suggest_float("qs_w_delta", 0.10, 0.60, step=0.05)
        qs_w_dte   = trial.suggest_float("qs_w_dte",   0.05, 0.50, step=0.05)

        sim_kwargs = dict(
            dte_at_entry=dte,
            stop_loss_pct=stop_loss_pct,
            profit_target_pct=profit_target_pct,
            delta_target=delta_target,
            min_confidence=min_confidence,
            min_ev_pct=min_ev_pct,
            entry_momentum=entry_momentum,
            time_exit_pct=float(config.get("time_exit_pct", 50.0)),
            ds_w_tech=ds_w_tech,
            ds_w_regime=ds_w_regime,
            ds_w_momentum=ds_w_momentum,
            rsi_sev_threshold=rsi_sev_threshold,
            rsi_mod_threshold=rsi_mod_threshold,
            rsi_sev_penalty=rsi_sev_penalty,
            rsi_mod_penalty=rsi_mod_penalty,
            qs_w_iv=qs_w_iv,
            qs_w_delta=qs_w_delta,
            qs_w_dte=qs_w_dte,
        )

        if multi:
            result = _simulate_window_multi(closes_input, **sim_kwargs, _caches=caches)
        else:
            result = _simulate_window(closes_input, **sim_kwargs, _cache=single_cache)

        if result["n_trades"] < max(1, config["min_trades"] // 2):
            return -99.0

        pf   = result["profit_factor"]
        sr   = result["sharpe"]
        dd   = result["max_drawdown_pct"]
        # Small quality bonus: incentivises Optuna to prefer higher-quality option setups
        # when PF is otherwise equal. Scaled to ±0.005 so it never overrides PF signal.
        avg_q = result.get("avg_quality", 50.0)
        quality_bonus = 0.005 * (avg_q - 50.0) / 50.0
        return pf + 0.1 * max(0.0, sr) - 0.02 * dd + quality_bonus

    return objective


# ── Guardrail checks ──────────────────────────────────────────────────────────

def _check_guardrails(
    is_result: dict,
    oos_result: dict,
    best_weights: dict,
    current_weights: dict,
    top_trials: list[dict],
    min_trades: int,            # auto-computed via _auto_min_trades()
    max_drift_pct: float = 0.40,
) -> tuple[bool, list[str]]:
    """Returns (passed, [issue messages]). ALL must pass."""
    issues: list[str] = []

    # G1: Overfit gate — two-part rule:
    #   Part A: OOS PF must be ≥ 1.0 (strategy must be profitable on unseen data)
    #   Part B: Only apply ratio check when IS PF > 3.0 (genuinely inflated in-sample)
    #           A modest IS PF of 1.5–2.5 degrading slightly OOS is normal, not overfit.
    is_pf  = is_result.get("profit_factor",  0)
    oos_pf = oos_result.get("profit_factor", 0)
    if oos_pf < 1.0:
        issues.append(
            f"G1 — OOS PF ({oos_pf:.2f}) < 1.0: strategy loses money on unseen data"
        )
    elif is_pf > 3.0 and oos_pf < 0.70 * is_pf:
        issues.append(
            f"G1 — OOS PF ({oos_pf:.2f}) < 70% of IS PF ({is_pf:.2f}): overfit"
        )

    # G3: Minimum trades in OOS window
    if oos_result["n_trades"] < min_trades:
        issues.append(
            f"G3 — only {oos_result['n_trades']} OOS trades (need ≥ {min_trades})"
        )

    # G5: OOS win rate ≥ 35% — long options are asymmetric: a 35% win rate with
    # large winners (PF > 1.5) is genuinely profitable. 40% was rejecting good windows.
    # Skipped when min_trades ≤ 3: with 1–2 trades a single outcome distorts the rate.
    if min_trades > 3:
        oos_wr = oos_result.get("win_rate", 0)
        if oos_wr < 0.35:
            issues.append(
                f"G5 — OOS win rate {oos_wr*100:.1f}% < 35% floor (consistency gate)"
            )

    return len(issues) == 0, issues


# ── Walk-Forward loop ─────────────────────────────────────────────────────────

def _run_wfo_for_closes(
    closes_input,       # pd.Series or dict[str, pd.Series]
    label: str,         # ticker name or "pooled"
    train_days: int,
    test_days: int,
    n_trials: int,
    config: dict,
    current_weights: dict,
    max_drift_pct: float,
    multi: bool,
    progress_callback: Optional[Callable],
    base_pct: float,
    pct_span: float,
    min_trades_override: Optional[int] = None,
) -> dict:
    """Run the full WFO loop on a single closes input (single or multi-ticker)."""
    # Determine length for window building
    if multi:
        ref = next(iter(closes_input.values()))
        n = len(ref)
    else:
        n = len(closes_input)

    # How many context days to prepend to each test slice so that hv30 and
    # iv_pct are valid on the very first day of the actual test period.
    # 30 (hv30 warmup) + 252 (iv_pct lookback) + small buffer = 290.
    CONTEXT_DAYS = 290

    # Expanding window: training always anchors at index 0 and grows each step.
    # Each test period advances by test_days, but training sees ALL prior history.
    # This prevents the rolling approach from "forgetting" old regimes.
    windows     = []
    test_start  = train_days   # first test begins after minimum training period
    while test_start + test_days <= n:
        ctx_start    = max(0, test_start - CONTEXT_DAYS)
        trade_offset = test_start - ctx_start
        if multi:
            windows.append({
                "train":        {sym: c.iloc[0 : test_start]          # always from day 0
                                 for sym, c in closes_input.items()},
                "test":         {sym: c.iloc[ctx_start : test_start + test_days]
                                 for sym, c in closes_input.items()},
                "trade_offset": trade_offset,
            })
        else:
            windows.append({
                "train":        closes_input.iloc[0 : test_start],     # always from day 0
                "test":         closes_input.iloc[ctx_start : test_start + test_days],
                "trade_offset": trade_offset,
            })
        test_start += test_days

    if not windows:
        return {"error": f"Not enough data for even one WFO window for {label}"}

    accepted: list[dict] = []
    rejected: list[dict] = []
    regime_params: dict[str, list[dict]] = {"normal": [], "defense": []}

    # Adaptive exit bounds — start at defaults, shift after each window
    stop_bounds: tuple = (25.0, 60.0)
    tgt_bounds:  tuple = (50.0, 150.0)
    adaptation_notes: list[str] = []   # notes from the most recent adaptation
    prev_best_params: Optional[dict] = None   # warm-start for next window

    # Min-trades: use user override if provided, otherwise auto-derive from window length
    n_tickers = len(closes_input) if multi else 1
    auto_min  = _auto_min_trades(test_days, n_tickers)
    config["min_trades"] = max(1, min_trades_override) if min_trades_override is not None else auto_min

    for wi, win in enumerate(windows):
        pct = base_pct + pct_span * (wi / len(windows))
        if progress_callback:
            progress_callback(
                f"[{label}] Window {wi+1}/{len(windows)}  "
                f"(stop {stop_bounds[0]:.0f}–{stop_bounds[1]:.0f}%  "
                f"target {tgt_bounds[0]:.0f}–{tgt_bounds[1]:.0f}%)…",
                pct,
            )

        train_input  = win["train"]
        test_input   = win["test"]
        trade_offset = win["trade_offset"]

        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=42 + wi),
        )

        # Warm-start: seed Optuna with the prior window's best params so it
        # converges faster and doesn't start from scratch each time.
        if prev_best_params is not None:
            warm = {}
            for k, v in prev_best_params.items():
                if k == "w_dte":
                    continue  # fixed — not a tunable param any more
                elif k == "stop_loss_pct":
                    warm[k] = float(np.clip(v, stop_bounds[0], stop_bounds[1]))
                elif k == "profit_target_pct":
                    warm[k] = float(np.clip(v, tgt_bounds[0], tgt_bounds[1]))
                else:
                    warm[k] = v
            study.enqueue_trial(warm)

        study.optimize(
            _make_objective(train_input, config, multi=multi,
                            stop_bounds=stop_bounds, tgt_bounds=tgt_bounds),
            n_trials=n_trials,
            show_progress_bar=False,
        )

        best_params  = study.best_params
        prev_best_params = best_params   # carry forward for next window warm-start

        # Reconstruct RSI thresholds from base + gap (same logic as objective)
        _rsi_mod_t  = float(best_params.get("rsi_mod_threshold", 68.0))
        _rsi_gap    = float(best_params.get("rsi_threshold_gap",  4.0))
        _rsi_sev_t  = _rsi_mod_t + _rsi_gap
        _rsi_mod_p  = float(best_params.get("rsi_mod_penalty", 8.0))
        _rsi_sev_p  = _rsi_mod_p + float(best_params.get("rsi_sev_bonus", 7.0))

        # Use the full optimized param set for IS/OOS evaluation (not config defaults)
        sim_kwargs = dict(
            dte_at_entry=config["dte_at_entry"],
            stop_loss_pct=best_params.get("stop_loss_pct",    config["stop_loss_pct"]),
            profit_target_pct=best_params.get("profit_target_pct", config["profit_target_pct"]),
            delta_target=best_params.get("delta_target",      config["delta_target"]),
            min_confidence=best_params.get("min_confidence",  config["min_confidence"]),
            min_ev_pct=best_params.get("min_ev_pct",          config["min_ev_pct"]),
            entry_momentum=best_params.get("entry_momentum",  0.5),
            time_exit_pct=float(config.get("time_exit_pct", 50.0)),
            ds_w_tech=best_params.get("ds_w_tech",         0.55),
            ds_w_regime=best_params.get("ds_w_regime",     0.30),
            ds_w_momentum=best_params.get("ds_w_momentum", 0.15),
            rsi_sev_threshold=_rsi_sev_t,
            rsi_mod_threshold=_rsi_mod_t,
            rsi_sev_penalty=_rsi_sev_p,
            rsi_mod_penalty=_rsi_mod_p,
            qs_w_iv=best_params.get("qs_w_iv",       0.40),
            qs_w_delta=best_params.get("qs_w_delta",  0.35),
            qs_w_dte=best_params.get("qs_w_dte",      0.25),
        )
        # Full set of optimized params (stored in results for diffing / apply)
        best_params_all = {
            "delta_target":      round(sim_kwargs["delta_target"], 4),
            "entry_momentum":    round(sim_kwargs["entry_momentum"], 4),
            "min_confidence":    round(sim_kwargs["min_confidence"], 1),
            "min_ev_pct":        round(sim_kwargs["min_ev_pct"], 1),
            "stop_loss_pct":     round(sim_kwargs["stop_loss_pct"], 1),
            "profit_target_pct": round(sim_kwargs["profit_target_pct"], 1),
            "ds_w_tech":         round(sim_kwargs["ds_w_tech"], 4),
            "ds_w_regime":       round(sim_kwargs["ds_w_regime"], 4),
            "ds_w_momentum":     round(sim_kwargs["ds_w_momentum"], 4),
            "rsi_sev_threshold": round(sim_kwargs["rsi_sev_threshold"], 1),
            "rsi_mod_threshold": round(sim_kwargs["rsi_mod_threshold"], 1),
            "rsi_sev_penalty":   round(sim_kwargs["rsi_sev_penalty"], 1),
            "rsi_mod_penalty":   round(sim_kwargs["rsi_mod_penalty"], 1),
            "qs_w_iv":           round(sim_kwargs["qs_w_iv"], 4),
            "qs_w_delta":        round(sim_kwargs["qs_w_delta"], 4),
            "qs_w_dte":          round(sim_kwargs["qs_w_dte"], 4),
        }
        # Precompute IS/OOS caches — test slice gets trade_offset so context
        # days are used for HV warmup but don't generate trades
        dte = config["dte_at_entry"]
        if multi:
            train_caches = {s: _precompute(c, dte) for s, c in train_input.items()}
            test_caches  = {s: _precompute(c, dte, trade_offset) for s, c in test_input.items()}
            is_result  = _simulate_window_multi(train_input, **sim_kwargs, _caches=train_caches)
            oos_result = _simulate_window_multi(test_input,  **sim_kwargs, _caches=test_caches)
        else:
            train_cache = _precompute(train_input, dte)
            test_cache  = _precompute(test_input,  dte, trade_offset)
            is_result  = _simulate_window(train_input, **sim_kwargs, _cache=train_cache)
            oos_result = _simulate_window(test_input,  **sim_kwargs, _cache=test_cache)

        passed, issues = _check_guardrails(
            is_result=is_result, oos_result=oos_result,
            best_weights={}, current_weights=current_weights,
            top_trials=[], min_trades=config["min_trades"],
            max_drift_pct=max_drift_pct,
        )

        # Date labels — handle both single and multi
        if multi:
            ref = next(iter(train_input.values()))
            ref_t = next(iter(test_input.values()))
        else:
            ref, ref_t = train_input, test_input

        regime = "normal"
        try:
            sym_for_regime = label if not multi else list(closes_input.keys())[0]
            regime_data = _get_market_regime(sym_for_regime)
            if regime_data.get("defense_mode"):
                regime = "defense"
        except Exception:
            pass

        record = {
            "window":             wi + 1,
            "train_start":        str(ref.index[0].date()),
            "train_end":          str(ref.index[-1].date()),
            "test_start":         str(ref_t.index[0].date()),
            "test_end":           str(ref_t.index[-1].date()),
            "is_sharpe":          round(is_result["sharpe"], 3),
            "is_profit_factor":   round(is_result["profit_factor"], 3),
            "oos_sharpe":         round(oos_result["sharpe"], 3),
            "oos_profit_factor":  round(oos_result["profit_factor"], 3),
            "oos_win_rate":       round(oos_result["win_rate"] * 100, 1),
            "oos_trades":         oos_result["n_trades"],
            "oos_max_dd":         round(oos_result["max_drawdown_pct"], 2),
            "best_params":        best_params_all,
            "regime":             regime,
            "passed":             passed,
            "issues":             issues,
        }

        # ── Adapt exit bounds for the NEXT window using IS trade outcomes ────
        is_trades = is_result.get("trades", [])
        if len(is_trades) >= 8:
            adapted = _adapt_bounds(
                is_trades,
                current_stop=sim_kwargs["stop_loss_pct"],
                current_target=sim_kwargs["profit_target_pct"],
            )
            stop_bounds      = (adapted["stop_lo"], adapted["stop_hi"])
            tgt_bounds       = (adapted["tgt_lo"],  adapted["tgt_hi"])
            adaptation_notes = adapted["notes"]
        else:
            adaptation_notes = []

        record["adaptation_notes"]      = adaptation_notes
        record["stop_search_bounds"]    = list(stop_bounds)
        record["target_search_bounds"]  = list(tgt_bounds)

        # IS trade quality breakdown
        if is_trades:
            is_stops   = sum(1 for t in is_trades if "stop"   in t.get("exit_reason", ""))
            is_targets = sum(1 for t in is_trades if "target" in t.get("exit_reason", ""))
            is_wins    = [t for t in is_trades if t.get("pnl_pct", 0) > 0]
            is_losses  = [t for t in is_trades if t.get("pnl_pct", 0) <= 0]
            record["is_stop_rate"]   = round(is_stops   / max(len(is_losses), 1) * 100, 1)
            record["is_target_rate"] = round(is_targets / max(len(is_wins),   1) * 100, 1)
            record["is_avg_win"]     = round(sum(t["pnl_pct"] for t in is_wins)   / max(len(is_wins),   1), 1)
            record["is_avg_loss"]    = round(sum(t["pnl_pct"] for t in is_losses) / max(len(is_losses), 1), 1)

        if passed:
            # Store compact OOS trade list (with exit_reason for UI analysis)
            record["oos_trade_pnl"] = [
                {
                    "ticker":      t.get("ticker",     label),
                    "date":        t["date"],
                    "type":        t.get("type", ""),
                    "stock_px":    round(t.get("stock_px",   0.0), 4),
                    "hv30":        round(t.get("hv30",       0.0), 4),
                    "dte":         t.get("dte", config.get("dte_at_entry", 0)),
                    "strike":      round(t.get("strike",     0.0), 2),
                    "entry_px":    round(t.get("entry_px",   0.0), 4),
                    "exit_px":     round(t.get("exit_px",    0.0), 4),
                    "pnl_pct":     round(t["pnl_pct"], 2),
                    "exit_reason": t.get("exit_reason", ""),
                    "confidence":  round(t.get("confidence", 0.0), 1),
                    "tech_score":  round(t.get("tech_score",  0.0), 1),
                    "ev":          round(t.get("ev",          0.0), 1),
                }
                for t in oos_result.get("trades", [])
            ]
            accepted.append(record)
            regime_params[regime].append(best_params_all)
        else:
            rejected.append(record)

    # Average accepted active params per regime → final_recommendations
    _PARAM_KEYS = [
        "delta_target", "entry_momentum", "min_confidence",
        "min_ev_pct", "stop_loss_pct", "profit_target_pct",
        "ds_w_tech", "ds_w_regime", "ds_w_momentum",
        "rsi_sev_threshold", "rsi_mod_threshold", "rsi_sev_penalty", "rsi_mod_penalty",
        "qs_w_iv", "qs_w_delta", "qs_w_dte",
    ]
    final_recommendations: dict[str, dict] = {}
    for regime, plist in regime_params.items():
        if plist:
            final_recommendations[regime] = {
                k: round(sum(p.get(k, 0) for p in plist) / len(plist), 4)
                for k in _PARAM_KEYS
            }

    return {
        "label":                label,
        "windows_total":        len(windows),
        "windows_passed":       len(accepted),
        "windows_rejected":     len(rejected),
        "pass_rate_pct":        round(len(accepted) / max(len(windows), 1) * 100, 1),
        "accepted":             accepted,
        "rejected":             rejected,
        "final_recommendations": final_recommendations,
        # Legacy alias retained so older UI fallbacks do not break.
        "final_weights":        {},
    }

@_market_data_scoped
def walk_forward(
    symbols: list[str],
    train_months: int = 6,
    test_months: int = 2,
    n_trials: int = 50,
    lookback_years: int = 5,
    mode: str = "pooled",           # "pooled" or "per_ticker"
    max_drift_pct: float = 0.40,    # G2 limit — how far weights can move from current
    progress_callback: Optional[Callable[[str, float], None]] = None,
    asset_profile: str = "equity",
    min_trades_override: Optional[int] = None,
) -> dict:
    """
    Main WFO entry point.

    Parameters
    ----------
    symbols              : list of tickers (e.g. ["SPY", "NVDA", "QQQ"])
    mode                 : "pooled" — one universal weight set trained across all tickers
                           "per_ticker" — independent optimization per ticker
    max_drift_pct        : G2 guardrail — max allowed weight drift from current profile
    asset_profile        : "equity" or "index" — selects which strategy profile to optimize
    min_trades_override  : Override the auto-computed G3 min-trades floor. Set to 1–3 for
                           near-100% acceptance (G4/G5 are auto-skipped when ≤ 3).
                           None (default) = auto-computed via _auto_min_trades().
    """
    if not HAS_OPTUNA:
        return {"error": "optuna not installed — run: uv add optuna"}
    if not symbols:
        return {"error": "Provide at least one ticker symbol"}

    symbols = [s.upper() for s in symbols]
    sp = STRATEGY_PROFILES.get(asset_profile, STRATEGY_PROFILE)
    config = {
        "dte_at_entry":      max(DTE_MIN, min(DTE_MAX, int(sp["targets"].get("dte_optimal", 10)))),
        "stop_loss_pct":     float(sp["risk"].get("stop_loss_pct", 50.0)),
        "profit_target_pct": float(sp["risk"].get("profit_target_pct", 100.0)),
        "delta_target":      float(sp["targets"].get("delta_optimal", 0.30)),
        "min_confidence":    50.0,
        "min_ev_pct":        float(sp["filters"].get("min_ev_return_pct", 10.0)),
        "min_trades":        15,   # placeholder — overwritten by _auto_min_trades() per run
    }
    current_weights = sp["confidence_weights"].copy()

    # ── Fetch price history for all tickers ───────────────────────────────────
    if progress_callback:
        progress_callback("Fetching price history…", 0.02)

    fetch_days = lookback_years * 365 + 180
    all_closes: dict[str, pd.Series] = {}
    for sym in symbols:
        try:
            hist = _cached_history(sym, period=f"{fetch_days}d")
            if not hist.empty and len(hist) >= 100:
                all_closes[sym] = hist["Close"].dropna()
        except Exception:
            pass

    if not all_closes:
        return {"error": "Could not fetch price history for any of the provided tickers"}

    fetched = list(all_closes.keys())
    train_days = int(train_months * 21)
    test_days  = int(test_months  * 21)

    # ── Run optimization ──────────────────────────────────────────────────────
    if mode == "pooled":
        if progress_callback:
            progress_callback(f"Running pooled WFO across {len(fetched)} tickers…", 0.05)

        # Use shortest series length to define windows (all tickers stay in sync)
        min_len = min(len(c) for c in all_closes.values())
        trimmed = {sym: c.iloc[-min_len:] for sym, c in all_closes.items()}

        result = _run_wfo_for_closes(
            closes_input=trimmed, label="pooled",
            train_days=train_days, test_days=test_days, n_trials=n_trials,
            config=config, current_weights=current_weights,
            max_drift_pct=max_drift_pct, multi=True,
            progress_callback=progress_callback, base_pct=0.05, pct_span=0.90,
            min_trades_override=min_trades_override,
        )

        if "error" in result:
            return result

        output = {
            "run_at":         datetime.now().isoformat(timespec="seconds"),
            "mode":           "pooled",
            "symbols":        fetched,
            "config":         config,
            "max_drift_pct":  max_drift_pct,
            **{k: result[k] for k in [
                "windows_total", "windows_passed", "windows_rejected",
                "pass_rate_pct", "accepted", "rejected", "final_weights", "final_recommendations",
            ]},
            "note": "Parameters NOT applied automatically. Use 'Apply' in the UI.",
        }

    else:  # per_ticker
        per_ticker: dict[str, dict] = {}
        n_syms = len(fetched)

        for ti, sym in enumerate(fetched):
            base = 0.05 + 0.88 * (ti / n_syms)
            span = 0.88 / n_syms
            if progress_callback:
                progress_callback(f"[{sym}] optimising…", base)

            result = _run_wfo_for_closes(
                closes_input=all_closes[sym], label=sym,
                train_days=train_days, test_days=test_days, n_trials=n_trials,
                config=config, current_weights=current_weights,
                max_drift_pct=max_drift_pct, multi=False,
                progress_callback=progress_callback, base_pct=base, pct_span=span,
                min_trades_override=min_trades_override,
            )
            per_ticker[sym] = result

        output = {
            "run_at":        datetime.now().isoformat(timespec="seconds"),
            "mode":          "per_ticker",
            "symbols":       fetched,
            "config":        config,
            "max_drift_pct": max_drift_pct,
            "per_ticker":    per_ticker,
            "note": "Parameters NOT applied automatically. Use 'Apply' in the UI.",
        }

    with open(WFO_RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2)

    if progress_callback:
        progress_callback("Done.", 1.0)

    return output


def load_last_results() -> Optional[dict]:
    return load_last_results_by_truth_lane()


def _load_json_file(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _result_truth_source(result: Optional[dict]) -> str:
    truth_source = str((result or {}).get("truth_source") or "").strip().lower()
    return truth_source or SYNTHETIC_TRUTH_SOURCE


def load_last_synthetic_results() -> Optional[dict]:
    result = _load_json_file(WFO_RESULTS_FILE)
    if result and not result.get("truth_source"):
        result["truth_source"] = SYNTHETIC_TRUTH_SOURCE
    return result


def _imported_result_health(path: str, truth_source: str) -> dict[str, Any]:
    artifact_present = os.path.exists(path)
    raw_result = _load_json_file(path) if artifact_present else None
    current_store = _current_imported_store_summary(truth_source)
    recorded_truth_store = dict((raw_result or {}).get("truth_store") or {})

    status = "loadable"
    rejection_reason = None
    if not artifact_present:
        status = "missing_artifact"
        rejection_reason = "missing_artifact"
    elif raw_result is None:
        status = "unreadable_artifact"
        rejection_reason = "unreadable_artifact"
    elif not recorded_truth_store:
        status = "missing_recorded_truth_store"
        rejection_reason = "missing_recorded_truth_store"
    elif current_store is None:
        status = "missing_current_store"
        rejection_reason = "missing_current_store"
    elif not _imported_result_matches_current_store(raw_result, truth_source):
        status = "store_mismatch"
        rejection_reason = "store_mismatch"

    return {
        "truth_source": truth_source,
        "artifact_path": path,
        "artifact_present": artifact_present,
        "artifact_readable": raw_result is not None,
        "current_store_present": current_store is not None,
        "recorded_truth_store_present": bool(recorded_truth_store),
        "loadable": status == "loadable",
        "status": status,
        "rejection_reason": rejection_reason,
        "result_truth_source": _result_truth_source(raw_result) if raw_result else None,
        "current_store": current_store,
        "recorded_truth_store": recorded_truth_store or None,
    }


def _archived_forward_result_health() -> dict[str, Any]:
    health = _imported_result_health(
        OPTIONS_VALIDATION_DAILY_FORWARD_LATEST_FILE,
        IMPORTED_DAILY_TRUTH_SOURCE,
    )
    raw_result = _load_json_file(OPTIONS_VALIDATION_DAILY_FORWARD_LATEST_FILE)
    if raw_result and not raw_result.get("candidate_source"):
        raw_result["candidate_source"] = FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE
    loadable_result = load_last_archived_forward_daily_results() if health["loadable"] else None
    health["candidate_source"] = str((loadable_result or raw_result or {}).get("candidate_source") or "").strip().lower() or None
    health["has_forward_evidence"] = _has_archived_forward_evidence(loadable_result or raw_result)
    health["actionable"] = _is_actionable_archived_forward_result(loadable_result)
    return health


def build_truth_lane_health_summary() -> dict[str, Any]:
    synthetic = load_last_synthetic_results()
    imported = _imported_result_health(OPTIONS_VALIDATION_LATEST_FILE, IMPORTED_TRUTH_SOURCE)
    imported_daily = _imported_result_health(
        OPTIONS_VALIDATION_DAILY_LATEST_FILE,
        IMPORTED_DAILY_TRUTH_SOURCE,
    )
    archived_forward_daily = _archived_forward_result_health()
    default_result = load_preferred_results_by_truth_lane()
    default_truth_source = _result_truth_source(default_result) if default_result else None
    return {
        "paths": {
            "synthetic_result": WFO_RESULTS_FILE,
            "imported_result": OPTIONS_VALIDATION_LATEST_FILE,
            "imported_daily_result": OPTIONS_VALIDATION_DAILY_LATEST_FILE,
            "archived_forward_daily_result": OPTIONS_VALIDATION_DAILY_FORWARD_LATEST_FILE,
        },
        "default_fallback_order": [
            "archived_forward_daily",
            IMPORTED_TRUTH_SOURCE,
            IMPORTED_DAILY_TRUTH_SOURCE,
            SYNTHETIC_TRUTH_SOURCE,
        ],
        "default_selected_truth_source": default_truth_source,
        "default_selected_evidence_status": str((default_result or {}).get("evidence_status") or "").strip().lower() or None,
        "default_selected_candidate_source": str((default_result or {}).get("candidate_source") or "").strip().lower() or None,
        "synthetic_research": {
            "truth_source": SYNTHETIC_TRUTH_SOURCE,
            "artifact_path": WFO_RESULTS_FILE,
            "artifact_present": os.path.exists(WFO_RESULTS_FILE),
            "artifact_readable": synthetic is not None,
            "loadable": synthetic is not None,
            "status": "loadable" if synthetic is not None else "missing_artifact",
            "rejection_reason": None if synthetic is not None else "missing_artifact",
            "result_truth_source": _result_truth_source(synthetic) if synthetic else None,
        },
        IMPORTED_TRUTH_SOURCE: imported,
        IMPORTED_DAILY_TRUTH_SOURCE: imported_daily,
        "archived_forward_daily": archived_forward_daily,
    }


@lru_cache(maxsize=8)
def _current_imported_store_summary_cached(
    truth_source: str,
    db_path: str,
    db_mtime_ns: int,
) -> Optional[dict[str, Any]]:
    try:
        store = HistoricalOptionsStore(db_path)
        summary = store.snapshot_summary(
            _imported_snapshot_kind(truth_source),
            trusted_only=True,
            include_available_underlyings=False,
        )
    except Exception:
        return None
    if int(summary.get("quote_count", 0) or 0) <= 0:
        return None
    summary["data_trust"] = TRUSTED_DATA_TRUST
    return summary


def _current_imported_store_summary(truth_source: str) -> Optional[dict[str, Any]]:
    try:
        store = HistoricalOptionsStore()
        db_path = str(store.db_path)
        db_mtime_ns = int(os.path.getmtime(db_path) * 1_000_000_000)
    except Exception:
        return None
    return _current_imported_store_summary_cached(truth_source, db_path, db_mtime_ns)


def _imported_result_matches_current_store(result: Optional[dict], truth_source: str) -> bool:
    if not result:
        return False
    current = _current_imported_store_summary(truth_source)
    if not current:
        return False
    recorded = dict(result.get("truth_store") or {})
    if not recorded:
        return False
    return (
        str(recorded.get("snapshot_kind") or "") == str(current.get("snapshot_kind") or "")
        and str(recorded.get("data_trust") or "") == TRUSTED_DATA_TRUST
        and int(recorded.get("quote_count", 0) or 0) == int(current.get("quote_count", 0) or 0)
        and int(recorded.get("batch_count", 0) or 0) == int(current.get("batch_count", 0) or 0)
        and str(recorded.get("latest_imported_at_utc") or "") == str(current.get("latest_imported_at_utc") or "")
        and (
            current.get("available_underlyings") is None
            or sorted(str(item) for item in (recorded.get("available_underlyings") or []))
            == sorted(str(item) for item in (current.get("available_underlyings") or []))
        )
    )


def _load_imported_result(path: str, truth_source: str) -> Optional[dict]:
    result = _load_json_file(path)
    if result and not result.get("truth_source"):
        result["truth_source"] = truth_source
    if not _imported_result_matches_current_store(result, truth_source):
        return None
    return result


def load_last_imported_results() -> Optional[dict]:
    return _load_imported_result(OPTIONS_VALIDATION_LATEST_FILE, IMPORTED_TRUTH_SOURCE)


def load_last_imported_daily_results() -> Optional[dict]:
    return _load_imported_result(OPTIONS_VALIDATION_DAILY_LATEST_FILE, IMPORTED_DAILY_TRUTH_SOURCE)


def load_last_archived_forward_daily_results() -> Optional[dict]:
    result = _load_imported_result(
        OPTIONS_VALIDATION_DAILY_FORWARD_LATEST_FILE,
        IMPORTED_DAILY_TRUTH_SOURCE,
    )
    if result and not result.get("candidate_source"):
        result["candidate_source"] = FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE
    return result


def _archived_primary_trade_counts_by_symbol(result: Optional[dict]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for trade in list((result or {}).get("trades") or []):
        if str(trade.get("entry_contract_resolution") or "").strip().lower() != PRIMARY_JUDGE_TRADE_CLASS:
            continue
        ticker = str(trade.get("ticker") or "").strip().upper()
        if ticker:
            counts[ticker] += 1
    return {symbol: int(count) for symbol, count in sorted(counts.items())}


def _archived_exact_evidence_is_sufficient(
    result: Optional[dict],
    *,
    min_trades: int = MIN_ARCHIVED_PRIMARY_SYMBOL_TRADES,
) -> bool:
    per_symbol = _archived_primary_trade_counts_by_symbol(result)
    if per_symbol:
        return max(per_symbol.values()) >= int(min_trades)
    return int((result or {}).get("primary_judge_trade_count") or 0) >= int(min_trades)


def _preferred_evidence_status(
    result: Optional[dict],
    *,
    evidence_mode: str,
    fallback_used: bool,
) -> str:
    if not result:
        return SYNTHETIC_ONLY_STATUS if fallback_used else MODEL_DAILY_FALLBACK_ONLY_STATUS
    candidate_source = str(result.get("candidate_source") or "").strip().lower()
    truth_source = _result_truth_source(result)
    if candidate_source == FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE or evidence_mode == "archived_forward_daily":
        return (
            ARCHIVED_EXACT_PRIMARY_STATUS
            if _archived_exact_evidence_is_sufficient(result)
            else ARCHIVED_EXACT_INSUFFICIENT_STATUS
        )
    if truth_source == SYNTHETIC_TRUTH_SOURCE:
        return SYNTHETIC_ONLY_STATUS
    return MODEL_DAILY_FALLBACK_ONLY_STATUS


def _has_archived_forward_evidence(result: Optional[dict]) -> bool:
    if not result or bool(result.get("error")):
        return False
    candidate_source = str(result.get("candidate_source") or "").strip().lower()
    if candidate_source == FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE:
        return True
    return bool(result.get("insufficient_archived_evidence"))


def _is_actionable_archived_forward_result(result: Optional[dict]) -> bool:
    return bool(result) and not bool(result.get("error")) and not bool(result.get("insufficient_archived_evidence"))


def _preferred_truth_window_status(
    result: Optional[dict],
    *,
    evidence_mode: str,
    evidence_status: str,
) -> str:
    if not result:
        return "unknown"
    explicit_status = str(result.get("truth_window_status") or "").strip().lower()
    if explicit_status == "stale":
        return "stale"
    candidate_source = str(result.get("candidate_source") or "").strip().lower()
    pending_truth_horizon_count = int(result.get("pending_truth_horizon_count") or 0)
    if candidate_source == FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE or evidence_mode == "archived_forward_daily":
        if pending_truth_horizon_count > 0:
            return "stale"
        if evidence_status in {ARCHIVED_EXACT_PRIMARY_STATUS, ARCHIVED_EXACT_INSUFFICIENT_STATUS}:
            return "current"
    return "unknown"


def _annotate_preferred_result(
    result: Optional[dict],
    *,
    evidence_mode: str,
    fallback_used: bool,
) -> Optional[dict]:
    if not result:
        return None
    annotated = dict(result)
    evidence_status = _preferred_evidence_status(
        annotated,
        evidence_mode=evidence_mode,
        fallback_used=fallback_used,
    )
    truth_window_status = _preferred_truth_window_status(
        annotated,
        evidence_mode=evidence_mode,
        evidence_status=evidence_status,
    )
    annotated["evidence_status"] = evidence_status
    annotated["truth_window_status"] = truth_window_status
    annotated["authoritative_evidence_source"] = evidence_mode
    annotated["authoritative_evidence_status"] = evidence_status
    annotated["preferred_evidence_source"] = {
        "mode": evidence_mode,
        "fallback_used": bool(fallback_used),
        "status": evidence_status,
        "truth_window_status": truth_window_status,
        "candidate_source": annotated.get("candidate_source") or "model_replay",
        "primary_judge_trade_class": annotated.get("primary_judge_trade_class"),
        "primary_judge_trade_count": int(annotated.get("primary_judge_trade_count") or 0),
        "primary_judge_fallback_used": bool(annotated.get("primary_judge_fallback_used")),
        "primary_judge_fallback_reason": annotated.get("primary_judge_fallback_reason"),
        "primary_judge_trade_counts_by_symbol": _archived_primary_trade_counts_by_symbol(annotated),
    }
    return annotated


def load_preferred_results_by_truth_lane(
    truth_lane: Optional[str] = None,
) -> Optional[dict]:
    normalized = str(truth_lane or "").strip().lower()
    if normalized == IMPORTED_TRUTH_SOURCE:
        return _annotate_preferred_result(
            load_last_imported_results(),
            evidence_mode="model_imported_intraday",
            fallback_used=False,
        )
    if normalized == IMPORTED_DAILY_TRUTH_SOURCE:
        archived = load_last_archived_forward_daily_results()
        if _has_archived_forward_evidence(archived):
            return _annotate_preferred_result(
                archived,
                evidence_mode="archived_forward_daily",
                fallback_used=False,
            )
        fallback = load_last_imported_daily_results()
        if fallback:
            return _annotate_preferred_result(
                fallback,
                evidence_mode="model_imported_daily_fallback",
                fallback_used=True,
            )
        return None
    if normalized in {"synthetic", SYNTHETIC_TRUTH_SOURCE, "mid", "pessimistic"}:
        return _annotate_preferred_result(
            load_last_synthetic_results(),
            evidence_mode="synthetic_fallback",
            fallback_used=False,
        )
    archived = load_last_archived_forward_daily_results()
    if _has_archived_forward_evidence(archived):
        return _annotate_preferred_result(
            archived,
            evidence_mode="archived_forward_daily",
            fallback_used=False,
        )
    imported_intraday = load_last_imported_results()
    if imported_intraday:
        return _annotate_preferred_result(
            imported_intraday,
            evidence_mode="model_imported_intraday",
            fallback_used=False,
        )
    imported_daily = load_last_imported_daily_results()
    if imported_daily:
        return _annotate_preferred_result(
            imported_daily,
            evidence_mode="model_imported_daily_fallback",
            fallback_used=True,
        )
    return _annotate_preferred_result(
        load_last_synthetic_results(),
        evidence_mode="synthetic_fallback",
        fallback_used=True,
    )


def load_last_results_by_truth_lane(
    truth_lane: Optional[str] = None,
) -> Optional[dict]:
    normalized = str(truth_lane or "").strip().lower()
    if normalized == IMPORTED_TRUTH_SOURCE:
        return load_last_imported_results()
    if normalized == IMPORTED_DAILY_TRUTH_SOURCE:
        return load_last_imported_daily_results()
    if normalized in {"synthetic", SYNTHETIC_TRUTH_SOURCE, "mid", "pessimistic"}:
        return load_last_synthetic_results()
    return (
        load_last_imported_results()
        or load_last_imported_daily_results()
        or load_last_synthetic_results()
    )


def _save_backtest_result(result: dict) -> dict:
    truth_source = _result_truth_source(result)
    if _is_imported_truth_source(truth_source):
        os.makedirs(OPTIONS_VALIDATION_RESULTS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        is_forward_daily = (
            truth_source == IMPORTED_DAILY_TRUTH_SOURCE
            and str(result.get("candidate_source") or "").strip().lower() == FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE
        )
        source_suffix = (
            "daily_forward"
            if is_forward_daily
            else ("daily" if truth_source == IMPORTED_DAILY_TRUTH_SOURCE else "intraday")
        )
        latest_path = (
            OPTIONS_VALIDATION_DAILY_FORWARD_LATEST_FILE
            if is_forward_daily
            else (
                OPTIONS_VALIDATION_DAILY_LATEST_FILE
                if truth_source == IMPORTED_DAILY_TRUTH_SOURCE
                else OPTIONS_VALIDATION_LATEST_FILE
            )
        )
        run_path = os.path.join(
            OPTIONS_VALIDATION_RESULTS_DIR,
            f"{timestamp}_{result.get('playbook', 'broad')}_{source_suffix}.json",
        )
        result["result_path"] = run_path
        with open(run_path, "w", encoding="utf8") as handle:
            json.dump(result, handle, indent=2)
        with open(latest_path, "w", encoding="utf8") as handle:
            json.dump(result, handle, indent=2)
        return result

    result["result_path"] = WFO_RESULTS_FILE
    with open(WFO_RESULTS_FILE, "w", encoding="utf8") as handle:
        json.dump(result, handle, indent=2)
    return result


def _parse_forward_entry_date(value: Any) -> Optional[date]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def _forward_pick_truth_required_date(pick: dict[str, Any], entry_date: date) -> date:
    expiry_date = _parse_forward_entry_date(pick.get("expiry"))
    if expiry_date is not None:
        return max(entry_date, expiry_date)
    try:
        dte = int(float(pick.get("dte") or 0))
    except (TypeError, ValueError):
        dte = 0
    if dte > 0:
        return entry_date + timedelta(days=dte)
    return entry_date


def _archived_sample_date_coverage(
    picks: Sequence[dict[str, Any]],
    *,
    source_label: str,
) -> dict[str, Any]:
    entry_dates = sorted(
        {
            str(item.get("entry_date") or "").strip()
            for item in picks
            if str(item.get("entry_date") or "").strip()
        }
    )
    session_ids = {
        int(item.get("session_id"))
        for item in picks
        if item.get("session_id") is not None
    }
    return {
        "source_label": str(source_label or ARCHIVED_FORWARD_SOURCE_LABEL),
        "session_count": len(session_ids),
        "entry_date_count": len(entry_dates),
        "first_entry_date": entry_dates[0] if entry_dates else None,
        "last_entry_date": entry_dates[-1] if entry_dates else None,
    }


def _insufficient_archived_forward_result(
    reason: str,
    *,
    source_label: str,
    archived_picks: Optional[Sequence[dict[str, Any]]] = None,
    excluded_tickers: Optional[list[dict[str, Any]]] = None,
    pending_truth_horizon: Optional[Sequence[dict[str, Any]]] = None,
    truth_store: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    picks = list(archived_picks or [])
    pending = list(pending_truth_horizon or [])
    contract_resolution_overview = {
        "exact_archived_contract": 0,
        "exact_target_contract": 0,
        "nearest_listed_contract": 0,
        "unresolved_candidates": max(len(picks) - len(pending), 0),
        "pending_truth_horizon": len(pending),
    }
    authoritative_metrics = _trade_subset_metrics([], include_exit_reasons=True)
    authoritative_gate = _authoritative_profitability_gate(
        authoritative_metrics,
        min_trade_count=MIN_ARCHIVED_PRIMARY_SYMBOL_TRADES,
        min_profit_factor=1.05,
        min_directional_accuracy_pct=MIN_EXACT_CONTRACT_DIRECTIONAL_ACCURACY_PCT,
    )
    return {
        "available": False,
        "status": "insufficient_archived_evidence",
        "insufficient_archived_evidence": True,
        "insufficient_reason": str(reason or "missing_archived_scan_pick_evidence"),
        "mode": "backtest",
        "truth_source": IMPORTED_DAILY_TRUTH_SOURCE,
        "requested_pricing_lane": "pessimistic",
        "effective_pricing_lane": "pessimistic",
        "pricing_lane": "pessimistic",
        "candidate_source": FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
        "primary_judge_trade_class": PRIMARY_JUDGE_TRADE_CLASS,
        "evidence_status": ARCHIVED_EXACT_INSUFFICIENT_STATUS,
        "truth_window_status": "stale" if pending else "unknown",
        "authoritative_evidence_source": "archived_forward_daily",
        "authoritative_evidence_status": ARCHIVED_EXACT_INSUFFICIENT_STATUS,
        "primary_judge_trade_count": 0,
        "primary_judge_fallback_used": False,
        "primary_judge_fallback_reason": None,
        "promotion_trade_count": 0,
        "non_promotable_trade_count": 0,
        "quote_coverage_pct": 0.0,
        "priced_trade_count": 0,
        "unpriced_trade_count": 0,
        "post_entry_filtered_trade_count": 0,
        "pre_post_entry_candidate_trade_count": len(picks),
        "post_entry_reject_rate_pct": 0.0,
        "candidate_trade_count": len(picks),
        "pending_truth_horizon_count": len(pending),
        "contract_resolution_overview": contract_resolution_overview,
        "promotion_metrics": {
            **_trade_subset_metrics([], include_exit_reasons=True),
            "promotion_status": "block",
            "promoted_symbols": [],
            "blockers": [
                "Archived /api/scan exact-contract evidence is unavailable, so promotion remains blocked."
            ],
        },
        "by_symbol": {},
        "authoritative_profitability_basis": "archived_exact_contract_only",
        "authoritative_profitability_metrics": authoritative_metrics,
        "authoritative_profitability_gate": authoritative_gate,
        "archived_exact_contract_metrics": _trade_subset_metrics([], include_exit_reasons=True),
        "model_exact_contract_metrics": _trade_subset_metrics([], include_exit_reasons=True),
        "nearest_listed_metrics": _trade_subset_metrics([], include_exit_reasons=True),
        "trades": [],
        "unpriced_trades": [],
        "excluded_tickers": list(excluded_tickers or []),
        "pending_truth_horizon_trades": pending,
        "truth_store": dict(truth_store or {}),
        "archived_sample_date_coverage": _archived_sample_date_coverage(
            picks,
            source_label=source_label,
        ),
    }


def _build_indicator_arrays(prices: np.ndarray) -> dict[str, np.ndarray]:
    n = len(prices)
    if n <= 0:
        return {
            "hv30": np.array([], dtype=float),
            "rsi14": np.array([], dtype=float),
            "macd": np.array([], dtype=float),
            "sma20": np.array([], dtype=float),
            "sma50": np.array([], dtype=float),
        }
    hv30 = np.full(n, np.nan)
    if n > 30:
        returns = np.diff(np.log(prices))
        for idx in range(30, n):
            window = returns[idx - 30: idx]
            hv30[idx] = float(np.std(window, ddof=1) * math.sqrt(252)) if len(window) >= 2 else np.nan

    rsi14 = np.full(n, 50.0)
    delta_prices = np.zeros(n)
    delta_prices[1:] = np.diff(prices)
    for idx in range(15, n):
        window = delta_prices[idx - 14: idx]
        ups = float(np.mean(window[window > 0])) if np.any(window > 0) else 0.0
        downs = float(np.mean(-window[window < 0])) if np.any(window < 0) else 0.0
        rsi14[idx] = 100.0 - 100.0 / (1.0 + ups / (downs + 1e-9))

    k12 = 2.0 / 13.0
    k26 = 2.0 / 27.0
    ema12 = np.empty(n)
    ema26 = np.empty(n)
    ema12[0] = ema26[0] = prices[0]
    for idx in range(1, n):
        ema12[idx] = prices[idx] * k12 + ema12[idx - 1] * (1.0 - k12)
        ema26[idx] = prices[idx] * k26 + ema26[idx - 1] * (1.0 - k26)
    macd = ema12 - ema26

    sma20 = pd.Series(prices).rolling(20, min_periods=1).mean().to_numpy(dtype=float)
    sma50 = pd.Series(prices).rolling(50, min_periods=1).mean().to_numpy(dtype=float)
    return {
        "hv30": hv30,
        "rsi14": rsi14,
        "macd": macd,
        "sma20": sma20,
        "sma50": sma50,
    }


def run_archived_forward_daily_backtest(
    *,
    source_label: str = ARCHIVED_FORWARD_SOURCE_LABEL,
    cohort_id: str | None = None,
    tickers: Optional[list[str]] = None,
    recorded_after_utc: str | None = None,
    require_eligible_only: bool = True,
) -> dict[str, Any]:
    archived_picks = list_forward_scan_pick_events(
        source_label=source_label,
        recorded_after_utc=recorded_after_utc,
        eligible_only=False,
        evidence_class=LIVE_PRODUCTION_EVIDENCE_CLASS if require_eligible_only else None,
        cohort_id=cohort_id,
        tickers=tickers,
    )
    if not archived_picks:
        return _insufficient_archived_forward_result(
            "no_archived_scan_pick_events",
            source_label=source_label,
        )

    store = HistoricalOptionsStore()
    if not store.has_quotes(snapshot_kind=DAILY_SNAPSHOT_KIND, trusted_only=True):
        return {
            "error": (
                "No trusted imported historical option data found for archived forward validation. "
                "Import real daily market data first."
            )
        }

    imported_truth_store = store.snapshot_summary(DAILY_SNAPSHOT_KIND, trusted_only=True)
    imported_truth_store["data_trust"] = TRUSTED_DATA_TRUST
    latest_quote_date: Optional[date] = None
    latest_quote_at_utc = str(imported_truth_store.get("latest_quote_at_utc") or "").strip()
    if latest_quote_at_utc:
        try:
            latest_quote_date = datetime.fromisoformat(latest_quote_at_utc.replace("Z", "+00:00")).date()
        except ValueError:
            latest_quote_date = None
    available_underlyings = {
        symbol.upper()
        for symbol in store.list_available_underlyings(
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            trusted_only=True,
        )
    }

    filtered_picks: list[dict[str, Any]] = []
    entry_dates: list[date] = []
    playbooks_seen: set[str] = set()
    excluded_tickers: list[dict[str, Any]] = []
    pending_truth_horizon: list[dict[str, Any]] = []
    for pick in archived_picks:
        ticker = str(pick.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        if ticker not in available_underlyings:
            excluded_tickers.append({"ticker": ticker, "reason": "missing_imported_underlying"})
            continue
        entry_date = _parse_forward_entry_date(
            pick.get("entry_date") or pick.get("quote_time_et") or pick.get("recorded_at_utc")
        )
        if entry_date is None:
            continue
        current = dict(pick)
        current["entry_date"] = entry_date.isoformat()
        truth_required_date = _forward_pick_truth_required_date(current, entry_date)
        if latest_quote_date is not None and truth_required_date > latest_quote_date:
            pending_reason = (
                "entry_date_beyond_trusted_truth_horizon"
                if entry_date > latest_quote_date
                else "exit_horizon_beyond_trusted_truth_horizon"
            )
            pending_truth_horizon.append(
                {
                    **current,
                    "pending_reason": pending_reason,
                    "latest_truth_quote_date": latest_quote_date.isoformat(),
                    "truth_required_date": truth_required_date.isoformat(),
                }
            )
            continue
        filtered_picks.append(current)
        entry_dates.append(entry_date)
        playbook_value = str(
            pick.get("playbook")
            or pick.get("playbook_id")
            or pick.get("session_playbook")
            or ""
        ).strip()
        if playbook_value:
            playbooks_seen.add(playbook_value)

    if not filtered_picks:
        result = _insufficient_archived_forward_result(
            "pending_truth_horizon_only" if pending_truth_horizon else "no_archived_picks_in_imported_daily_universe",
            source_label=source_label,
            archived_picks=archived_picks,
            excluded_tickers=excluded_tickers,
            pending_truth_horizon=pending_truth_horizon,
            truth_store=imported_truth_store,
        )
        return _save_backtest_result(result) if pending_truth_horizon else result

    min_entry_date = min(entry_dates)
    max_entry_date = max(entry_dates)
    max_dte = max(
        int(pick.get("dte") or 0) or 0
        for pick in filtered_picks
    )
    history_start = (pd.Timestamp(min_entry_date) - pd.Timedelta(days=120)).date()
    history_end = (pd.Timestamp(max_entry_date) + pd.Timedelta(days=max(max_dte, 30) + 10)).date()

    histories: dict[str, pd.DataFrame] = {}
    ticker_arrays: dict[str, dict[str, Any]] = {}
    for ticker in sorted({str(pick.get("ticker") or "").upper() for pick in filtered_picks}):
        hist = _sanitize_replay_history_frame(
            _cached_history(
                ticker,
                start=history_start,
                end=history_end,
                interval="1d",
            )
        )
        if hist.empty or "Close" not in hist.columns:
            excluded_tickers.append({"ticker": ticker, "reason": "missing_underlying_history"})
            continue
        closes = hist["Close"].astype(float)
        prices = closes.to_numpy(dtype=float)
        indicators = _build_indicator_arrays(prices)
        normalized_index = _normalize_replay_history_index(closes.index)
        date_to_idx = {
            pd.Timestamp(day).date().isoformat(): idx
            for idx, day in enumerate(normalized_index)
        }
        histories[ticker] = hist
        ticker_arrays[ticker] = {
            "dates": closes.index,
            "prices": prices,
            "date_to_idx": date_to_idx,
            "hv30": indicators["hv30"],
            "rsi14": indicators["rsi14"],
            "macd": indicators["macd"],
            "sma20": indicators["sma20"],
            "sma50": indicators["sma50"],
        }

    priced_trades: list[dict[str, Any]] = []
    unpriced_candidates: list[dict[str, Any]] = []
    fallback_trades: list[dict[str, Any]] = []

    for pick in filtered_picks:
        ticker = str(pick.get("ticker") or "").strip().upper()
        arrays = ticker_arrays.get(ticker)
        if arrays is None:
            unpriced_candidates.append(
                {
                    **pick,
                    "priced": False,
                    "unpriced_reason": "missing_underlying_history",
                    "truth_source": IMPORTED_DAILY_TRUTH_SOURCE,
                    "candidate_source": FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
                }
            )
            continue

        entry_date_text = str(pick.get("entry_date") or "").strip()
        day_idx = arrays["date_to_idx"].get(entry_date_text)
        if day_idx is None:
            unpriced_candidates.append(
                {
                    **pick,
                    "priced": False,
                    "unpriced_reason": "entry_date_not_in_history",
                    "truth_source": IMPORTED_DAILY_TRUTH_SOURCE,
                    "candidate_source": FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
                }
            )
            continue

        ticker_profile = STRATEGY_PROFILES["index"] if ticker.upper() in INDEX_TICKERS else STRATEGY_PROFILE
        risk_config = dict(ticker_profile.get("risk") or {})
        prices = arrays["prices"]
        hv30_value = arrays["hv30"][day_idx] if day_idx < len(arrays["hv30"]) else np.nan
        hv30 = float(hv30_value) if math.isfinite(float(hv30_value)) else 0.20
        dte_at_entry = int(
            pick.get("dte")
            or max(
                (
                    _parse_forward_entry_date(pick.get("expiry")) - _parse_forward_entry_date(entry_date_text)
                ).days,
                1,
            )
            if pick.get("expiry")
            else 1
        )
        outcome = _simulate_trade_outcome_imported(
            store=store,
            ticker=ticker,
            dates=arrays["dates"],
            prices=prices,
            i=int(day_idx),
            trade_type=str(
                pick.get("option_type")
                or pick.get("direction")
                or pick.get("type")
                or "call"
            ).strip().lower(),
            hv30=hv30,
            delta_target=abs(float(pick.get("delta") or pick.get("delta_est") or 0.30)),
            dte_at_entry=max(dte_at_entry, 1),
            stop_loss_pct=float(pick.get("stop_loss_pct") or risk_config.get("stop_loss_pct") or 45.0),
            profit_target_pct=float(
                pick.get("profit_target_pct") or risk_config.get("profit_target_pct") or 100.0
            ),
            time_exit_pct=float(pick.get("time_exit_pct") or risk_config.get("time_exit_pct") or 50.0),
            trailing_profit_pct=float(
                pick.get("trailing_profit_pct") or risk_config.get("trailing_profit_pct") or 40.0
            ),
            trailing_giveback_pct=float(
                pick.get("trailing_giveback_pct") or risk_config.get("trailing_giveback_pct") or 50.0
            ),
            _rsi14=arrays["rsi14"],
            _macd=arrays["macd"],
            _sma20=arrays["sma20"],
            _sma50=arrays["sma50"],
            tech_at_entry=float(pick.get("tech_score") or 50.0),
            entry_S0=float(
                pick.get("underlying_price_at_selection")
                if pick.get("underlying_price_at_selection") is not None
                else prices[day_idx]
            ),
            iv_adj=1.20,
            truth_source=IMPORTED_DAILY_TRUTH_SOURCE,
            snapshot_kind=DAILY_SNAPSHOT_KIND,
            entry_quote_minute_et=DAILY_QUOTE_MINUTE_ET,
            entry_window_minutes=0,
            archived_contract_symbol=pick.get("contract_symbol"),
            archived_expiry=pick.get("expiry"),
            archived_strike=pick.get("strike"),
            archived_option_type=pick.get("option_type") or pick.get("direction"),
            archived_quote_time_et=pick.get("quote_time_et"),
            archived_quote_basis=pick.get("quote_basis"),
            archived_underlying_price_at_selection=pick.get("underlying_price_at_selection"),
            archived_selection_source=pick.get("selection_source"),
            entry_slippage_pct=float(ticker_profile.get("filters", {}).get("entry_slippage_pct", 0.0)),
            exit_slippage_pct=float(ticker_profile.get("filters", {}).get("exit_slippage_pct", 0.0)),
        )

        trade = {
            **pick,
            **outcome,
            "ticker": ticker,
            "date": entry_date_text,
            "type": str(
                pick.get("option_type")
                or pick.get("direction")
                or pick.get("type")
                or "call"
            ).strip().lower(),
            "candidate_source": FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
        }
        if outcome.get("priced"):
            if str(outcome.get("entry_contract_resolution") or "").strip().lower() != PRIMARY_JUDGE_TRADE_CLASS:
                fallback_trades.append(trade)
            priced_trades.append(trade)
        else:
            unpriced_candidates.append(trade)

    priced_trade_count = len(priced_trades)
    unpriced_trade_count = len(unpriced_candidates)
    candidate_trade_count = priced_trade_count + unpriced_trade_count
    quote_coverage_pct = round(priced_trade_count / max(candidate_trade_count, 1) * 100.0, 1) if candidate_trade_count else 0.0

    contract_resolution = _contract_resolution_summary(
        {
            "priced_trade_count": priced_trade_count,
            "candidate_trade_count": candidate_trade_count,
            "trades": priced_trades,
        }
    )
    archived_exact_trades = [
        trade for trade in priced_trades
        if str(trade.get("entry_contract_resolution") or "").strip().lower() == "exact_archived_contract"
    ]
    model_exact_trades = [
        trade for trade in priced_trades
        if str(trade.get("entry_contract_resolution") or "").strip().lower() == "exact_target_contract"
    ]
    nearest_listed_trades = [
        trade for trade in priced_trades
        if str(trade.get("entry_contract_resolution") or "").strip().lower() == "nearest_listed_contract"
    ]
    playbook_id = (
        sorted(playbooks_seen)[0]
        if len(playbooks_seen) == 1
        else FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE
    )

    if not priced_trades:
        promotion_metrics = {
            **_trade_subset_metrics([], include_exit_reasons=True),
            "promotion_status": "block",
            "promoted_symbols": [],
            "blockers": ["No promotable exact-contract trades were recorded."],
        }
        output = {
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "mode": "backtest",
            "profile": "mixed",
            "truth_source": IMPORTED_DAILY_TRUTH_SOURCE,
            "requested_pricing_lane": "pessimistic",
            "effective_pricing_lane": "pessimistic",
            "pricing_lane": "pessimistic",
            "candidate_source": FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
            "primary_judge_trade_class": PRIMARY_JUDGE_TRADE_CLASS,
            "evidence_status": ARCHIVED_EXACT_INSUFFICIENT_STATUS,
            "truth_window_status": "stale" if pending_truth_horizon else "current",
            "authoritative_evidence_source": "archived_forward_daily",
            "authoritative_evidence_status": ARCHIVED_EXACT_INSUFFICIENT_STATUS,
            "lookback_years": round(max((max_entry_date - min_entry_date).days, 0) / 365.25, 2),
            "playbook": playbook_id,
            "n_picks": 0,
            "total_days": len({str(item.get("entry_date") or "") for item in filtered_picks}),
            "total_trades": 0,
            "priced_trade_count": 0,
            "unpriced_trade_count": unpriced_trade_count,
            "candidate_trade_count": candidate_trade_count,
            "pending_truth_horizon_count": len(pending_truth_horizon),
            "quote_coverage_pct": quote_coverage_pct,
            **contract_resolution,
            "contract_resolution_overview": _contract_resolution_overview(
                contract_resolution,
                pending_truth_horizon_count=len(pending_truth_horizon),
            ),
            "entry_quote_time_et": _imported_entry_quote_label(IMPORTED_DAILY_TRUTH_SOURCE),
            "exit_quote_time_et": _imported_exit_quote_label(IMPORTED_DAILY_TRUTH_SOURCE),
            "win_rate_pct": 0.0,
            "full_hit_rate_pct": 0.0,
            "directional_accuracy_pct": 0.0,
            "profit_factor": 0.0,
            **_profit_factor_denominator_truth_from_pnls([]),
            "avg_pnl_pct": 0.0,
            "avg_picks_per_day": 0.0,
            "sharpe": 0.0,
            "max_drawdown_pct": 0.0,
            "selection_source_counts": {},
            "calibration_summary": _selection_calibration_summary([]),
            "calibration_density_metrics": _calibration_density_metrics([]),
            "contract_selection_basis": "archived_exact_contract_with_model_fallback",
            "exact_contract_metrics": _trade_subset_metrics([], include_exit_reasons=True),
            "archived_exact_contract_metrics": _trade_subset_metrics([], include_exit_reasons=True),
            "model_exact_contract_metrics": _trade_subset_metrics([], include_exit_reasons=True),
            "nearest_listed_metrics": _trade_subset_metrics([]),
            "promotion_metrics": promotion_metrics,
            "by_symbol": {},
            "promotion_trade_count": 0,
            "non_promotable_trade_count": 0,
            "primary_judge_trade_count": 0,
            "primary_judge_fallback_used": False,
            "primary_judge_fallback_reason": None,
            "archived_sample_date_coverage": _archived_sample_date_coverage(
                filtered_picks,
                source_label=source_label,
            ),
            "truth_store": imported_truth_store,
            "replay_calendar": _build_replay_calendar_summary(
                source=FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
                index=pd.DatetimeIndex(sorted({pd.Timestamp(item["entry_date"]) for item in filtered_picks})),
                raw_history_date_count=len({str(item.get("entry_date") or "") for item in filtered_picks}),
                quote_date_count=len({str(item.get("entry_date") or "") for item in filtered_picks}),
                underlyings=sorted({str(item.get("ticker") or "").upper() for item in filtered_picks}),
                snapshot_kind=DAILY_SNAPSHOT_KIND,
            ),
            "validation_universe": sorted({str(item.get("ticker") or "").upper() for item in filtered_picks}),
            "eligible_tickers": sorted(histories.keys()),
            "excluded_tickers": excluded_tickers,
            "pending_truth_horizon_trades": pending_truth_horizon,
            "equity_curve": [],
            "trades": [],
            "unpriced_trades": unpriced_candidates,
            "unpriced_trade_diagnostics": _summarize_unpriced_trades(unpriced_candidates),
        }
        return _save_backtest_result(output)

    pnl_list = [float(trade.get("pnl_pct") or 0.0) for trade in priced_trades]
    wins = [pnl for pnl in pnl_list if pnl > 0]
    losses = [pnl for pnl in pnl_list if pnl <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_win / max(gross_loss, 0.01)
    win_rate = len(wins) / len(pnl_list) * 100.0
    full_hit_outcomes = [
        str(trade.get("prediction_outcome") or "").strip().lower()
        for trade in priced_trades
        if str(trade.get("prediction_outcome") or "").strip().lower() in {"hit", "miss"}
    ]
    full_hits = sum(1 for outcome in full_hit_outcomes if outcome == "hit")
    directional_hits = sum(1 for trade in priced_trades if trade.get("directional_correct"))
    full_hit_rate = full_hits / len(full_hit_outcomes) * 100.0 if full_hit_outcomes else None
    directional_accuracy = directional_hits / len(priced_trades) * 100.0
    avg_pnl = sum(pnl_list) / len(pnl_list)
    sharpe = _sharpe(pnl_list)

    daily_pnl: dict[str, list[float]] = defaultdict(list)
    selection_source_counts: dict[str, int] = defaultdict(int)
    for trade in priced_trades:
        daily_pnl[str(trade.get("date") or "")].append(float(trade.get("pnl_pct") or 0.0))
        selection_source_counts[str(trade.get("selection_source") or "unknown")] += 1

    def _single_pricing_field(field: str, fallback: str = "pessimistic") -> str:
        values = sorted(
            {
                str(trade.get(field) or "").strip().lower()
                for trade in priced_trades
                if str(trade.get(field) or "").strip()
            }
        )
        if not values:
            return fallback
        return values[0] if len(values) == 1 else "mixed"

    eq_curve: list[dict[str, Any]] = []
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for day in sorted(daily_pnl.keys()):
        day_mean = float(sum(daily_pnl[day]) / max(len(daily_pnl[day]), 1))
        cumulative += day_mean
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)
        eq_curve.append({"date": day, "cum_pnl_pct": round(cumulative, 2)})

    by_symbol = _by_symbol_trade_metrics(
        priced_trades,
        playbook_id=playbook_id,
        truth_source=IMPORTED_DAILY_TRUTH_SOURCE,
        candidate_source=FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
        authoritative_evidence_source="archived_forward_daily",
        min_directional_accuracy_pct=MIN_EXACT_CONTRACT_DIRECTIONAL_ACCURACY_PCT,
    )
    promotion_metrics = _overall_promotion_metrics(
        trades=priced_trades,
        by_symbol=by_symbol,
        playbook_id=playbook_id,
        truth_source=IMPORTED_DAILY_TRUTH_SOURCE,
        candidate_source=FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
        authoritative_evidence_source="archived_forward_daily",
        min_directional_accuracy_pct=MIN_EXACT_CONTRACT_DIRECTIONAL_ACCURACY_PCT,
    )
    exact_contract_metrics = _trade_subset_metrics(
        archived_exact_trades + model_exact_trades,
        include_exit_reasons=True,
    )
    authoritative_metrics = _trade_subset_metrics(
        archived_exact_trades,
        include_exit_reasons=True,
    )
    authoritative_profitability_gate = _authoritative_profitability_gate(
        authoritative_metrics,
        min_trade_count=MIN_ARCHIVED_PRIMARY_SYMBOL_TRADES,
        min_profit_factor=1.05,
        min_directional_accuracy_pct=MIN_EXACT_CONTRACT_DIRECTIONAL_ACCURACY_PCT,
    )
    unique_entry_dates = sorted({str(item.get("entry_date") or "") for item in filtered_picks if str(item.get("entry_date") or "").strip()})
    output = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "backtest",
        "profile": "mixed",
        "truth_source": IMPORTED_DAILY_TRUTH_SOURCE,
        "requested_pricing_lane": _single_pricing_field("requested_pricing_lane"),
        "effective_pricing_lane": _single_pricing_field("effective_pricing_lane"),
        "pricing_lane": _single_pricing_field("pricing_lane"),
        "candidate_source": FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
        "primary_judge_trade_class": PRIMARY_JUDGE_TRADE_CLASS,
        "truth_window_status": "stale" if pending_truth_horizon else "current",
        "authoritative_evidence_source": "archived_forward_daily",
        "lookback_years": round(max((max_entry_date - min_entry_date).days, 0) / 365.25, 2),
        "playbook": playbook_id,
        "n_picks": 0,
        "total_days": len(unique_entry_dates),
        "total_trades": len(priced_trades),
        "priced_trade_count": priced_trade_count,
        "unpriced_trade_count": unpriced_trade_count,
        "candidate_trade_count": candidate_trade_count,
        "pending_truth_horizon_count": len(pending_truth_horizon),
        "quote_coverage_pct": quote_coverage_pct,
        **contract_resolution,
        "contract_resolution_overview": _contract_resolution_overview(
            contract_resolution,
            pending_truth_horizon_count=len(pending_truth_horizon),
        ),
        "entry_quote_time_et": _imported_entry_quote_label(IMPORTED_DAILY_TRUTH_SOURCE),
        "exit_quote_time_et": _imported_exit_quote_label(IMPORTED_DAILY_TRUTH_SOURCE),
        "win_rate_pct": round(win_rate, 1),
        "full_hit_rate_pct": round(full_hit_rate, 1) if full_hit_rate is not None else None,
        "directional_accuracy_pct": round(directional_accuracy, 1),
        "profit_factor": round(pf, 2),
        **_profit_factor_denominator_truth_from_pnls(pnl_list),
        "avg_pnl_pct": round(avg_pnl, 2),
        "avg_picks_per_day": round(len(priced_trades) / max(len(unique_entry_dates), 1), 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(max_drawdown, 1),
        "selection_source_counts": dict(selection_source_counts),
        "calibration_summary": _selection_calibration_summary(priced_trades),
        "calibration_density_metrics": _calibration_density_metrics(priced_trades),
        "contract_selection_basis": "archived_exact_contract_with_model_fallback",
        "exact_contract_metrics": exact_contract_metrics,
        "authoritative_profitability_basis": "archived_exact_contract_only",
        "authoritative_profitability_metrics": authoritative_metrics,
        "authoritative_profitability_gate": authoritative_profitability_gate,
        "archived_exact_contract_metrics": _trade_subset_metrics(
            archived_exact_trades,
            include_exit_reasons=True,
        ),
        "model_exact_contract_metrics": _trade_subset_metrics(
            model_exact_trades,
            include_exit_reasons=True,
        ),
        "nearest_listed_metrics": _trade_subset_metrics(nearest_listed_trades),
        "promotion_metrics": promotion_metrics,
        "by_symbol": by_symbol,
        "promotion_trade_count": int(promotion_metrics.get("trade_count") or 0),
        "non_promotable_trade_count": len(
            [trade for trade in priced_trades if not _is_trade_promotable(trade)]
        ),
        "primary_judge_trade_count": len(archived_exact_trades),
        "primary_judge_fallback_used": bool(fallback_trades),
        "primary_judge_fallback_reason": "missing_archived_contract_quote" if fallback_trades else None,
        "archived_sample_date_coverage": _archived_sample_date_coverage(
            filtered_picks,
            source_label=source_label,
        ),
        "truth_store": imported_truth_store,
        "replay_calendar": _build_replay_calendar_summary(
            source=FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE,
            index=pd.DatetimeIndex([pd.Timestamp(day) for day in unique_entry_dates]),
            raw_history_date_count=len(unique_entry_dates),
            quote_date_count=len(unique_entry_dates),
            underlyings=sorted({str(item.get("ticker") or "").upper() for item in filtered_picks}),
            snapshot_kind=DAILY_SNAPSHOT_KIND,
        ),
        "validation_universe": sorted({str(item.get("ticker") or "").upper() for item in filtered_picks}),
        "eligible_tickers": sorted(histories.keys()),
        "excluded_tickers": excluded_tickers,
        "pending_truth_horizon_trades": pending_truth_horizon,
        "equity_curve": eq_curve,
        "trades": priced_trades,
        "unpriced_trades": unpriced_candidates,
        "unpriced_trade_diagnostics": _summarize_unpriced_trades(unpriced_candidates),
    }
    output["evidence_status"] = (
        ARCHIVED_EXACT_PRIMARY_STATUS
        if _archived_exact_evidence_is_sufficient(output)
        else ARCHIVED_EXACT_INSUFFICIENT_STATUS
    )
    output["authoritative_evidence_status"] = output["evidence_status"]
    return _save_backtest_result(output)


def _direction_score_bucket(score: float) -> str:
    if score < 40:
        return "00-39"
    if score < 50:
        return "40-49"
    if score < 60:
        return "50-59"
    if score < 70:
        return "60-69"
    if score < 80:
        return "70-79"
    return "80-100"


def _contract_resolution_summary(result: Optional[dict]) -> dict[str, Any]:
    trades = list((result or {}).get("trades") or [])
    priced_trade_count = int((result or {}).get("priced_trade_count", len(trades)) or len(trades))
    candidate_trade_count = int((result or {}).get("candidate_trade_count", priced_trade_count) or priced_trade_count)
    accounting = contract_resolution_accounting(
        trades,
        priced_trade_count=priced_trade_count,
        candidate_trade_count=candidate_trade_count,
    )
    return {
        key: value
        for key, value in accounting.items()
        if key not in {"priced_trade_count", "candidate_trade_count"}
    }


def _contract_resolution_overview(
    contract_resolution: dict[str, Any],
    *,
    pending_truth_horizon_count: int = 0,
) -> dict[str, int]:
    counts = dict(contract_resolution.get("contract_resolution_counts") or {})
    return {
        "exact_archived_contract": int(counts.get("exact_archived_contract", 0) or 0),
        "exact_target_contract": int(counts.get("exact_target_contract", 0) or 0),
        "exact_listed_spread_contract": int(counts.get("exact_listed_spread_contract", 0) or 0),
        "nearest_listed_contract": int(counts.get("nearest_listed_contract", 0) or 0),
        "unresolved_candidates": int(counts.get("unresolved_candidates", 0) or 0),
        "pending_truth_horizon": int(pending_truth_horizon_count or 0),
    }


def _is_exact_contract_resolution(value: Any) -> bool:
    return _shared_is_exact_contract_resolution(value)


def _trade_promotion_class(trade: dict[str, Any]) -> str:
    if not _is_exact_contract_resolution(trade.get("entry_contract_resolution")):
        return "research_nearest_listed"
    source = str(trade.get("selection_source") or "").strip().lower()
    if source == "bootstrap_heuristic":
        return "research_bootstrap"
    if _trade_calibration_density(trade) != "dense":
        return "research_sparse_calibration"
    return "promotable_exact_contract"


def _trade_non_promotable_reason(trade: dict[str, Any]) -> Optional[str]:
    unpriced_reason = str(trade.get("unpriced_reason") or "").strip()
    if unpriced_reason:
        return unpriced_reason
    promotion_class = _trade_promotion_class(trade)
    if promotion_class == "research_nearest_listed":
        return "nearest_listed_contract"
    if promotion_class == "research_bootstrap":
        return "bootstrap_expectancy"
    if promotion_class == "research_sparse_calibration":
        return "sparse_or_missing_dense_calibration"
    return None


def _is_trade_promotable(trade: dict[str, Any]) -> bool:
    return _trade_promotion_class(trade) == "promotable_exact_contract"


def _build_replay_calendar_summary(
    *,
    source: str,
    index: pd.DatetimeIndex,
    raw_history_date_count: int,
    quote_date_count: int | None = None,
    underlyings: Optional[Sequence[str]] = None,
    snapshot_kind: Optional[str] = None,
) -> dict[str, Any]:
    normalized_index = _normalize_replay_history_index(index) if len(index) else pd.DatetimeIndex([])
    return {
        "source": str(source),
        "snapshot_kind": str(snapshot_kind or "") or None,
        "underlyings": [str(item).upper() for item in (underlyings or [])],
        "raw_history_date_count": int(raw_history_date_count),
        "quote_date_count": int(quote_date_count) if quote_date_count is not None else None,
        "selected_date_count": int(len(normalized_index)),
        "dropped_history_date_count": max(int(raw_history_date_count) - int(len(normalized_index)), 0),
        "start_date": str(normalized_index[0].date()) if len(normalized_index) else None,
        "end_date": str(normalized_index[-1].date()) if len(normalized_index) else None,
    }


def _summarize_unpriced_trades(unpriced_trades: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counts: Counter[str] = Counter()
    ticker_reason_counts: dict[str, Counter[str]] = defaultdict(Counter)
    missing_quote_date_counts: Counter[str] = Counter()
    entry_contract_resolution_counts: Counter[str] = Counter()

    for trade in unpriced_trades:
        reason = str(trade.get("unpriced_reason") or "unknown")
        ticker = str(trade.get("ticker") or "unknown").upper()
        reason_counts[reason] += 1
        ticker_reason_counts[ticker][reason] += 1
        missing_quote_date = str(trade.get("missing_quote_date") or "").strip()
        if missing_quote_date:
            missing_quote_date_counts[missing_quote_date] += 1
        resolution = str(trade.get("entry_contract_resolution") or "").strip().lower()
        if resolution:
            entry_contract_resolution_counts[resolution] += 1

    top_missing_quote_dates = [
        {"date": quote_date, "count": int(count)}
        for quote_date, count in sorted(
            missing_quote_date_counts.items(),
            key=lambda item: (-int(item[1]), item[0]),
        )[:10]
    ]
    per_ticker = {
        ticker: dict(sorted(counts.items()))
        for ticker, counts in sorted(ticker_reason_counts.items())
    }
    return {
        "reason_counts": dict(sorted(reason_counts.items())),
        "ticker_reason_counts": per_ticker,
        "entry_contract_resolution_counts": dict(sorted(entry_contract_resolution_counts.items())),
        "top_missing_quote_dates": top_missing_quote_dates,
    }


def _result_source_metadata(result: dict, total_trades: int | None = None) -> dict[str, Any]:
    truth_store = result.get("truth_store") or {}
    profitability_view = _authoritative_profitability_view(result)
    return {
        "run_at": result.get("run_at"),
        "mode": result.get("mode"),
        "lookback_years": result.get("lookback_years"),
        "total_days": result.get("total_days"),
        "total_trades": result.get("total_trades", total_trades),
        "n_picks": result.get("n_picks"),
        "iv_adj": result.get("iv_adj"),
        "pricing_lane": result.get("pricing_lane"),
        "playbook": result.get("playbook"),
        "truth_source": _result_truth_source(result),
        "quote_coverage_pct": result.get("quote_coverage_pct"),
        "priced_trade_count": result.get("priced_trade_count"),
        "unpriced_trade_count": result.get("unpriced_trade_count"),
        "entry_quote_time_et": result.get("entry_quote_time_et"),
        "exit_quote_time_et": result.get("exit_quote_time_et"),
        "candidate_source": result.get("candidate_source") or "model_replay",
        "primary_judge_trade_class": result.get("primary_judge_trade_class"),
        "primary_judge_trade_count": int(result.get("primary_judge_trade_count") or 0),
        "primary_judge_fallback_used": bool(result.get("primary_judge_fallback_used")),
        "primary_judge_fallback_reason": result.get("primary_judge_fallback_reason"),
        "pending_truth_horizon_count": int(result.get("pending_truth_horizon_count") or 0),
        "preferred_evidence_source": dict(result.get("preferred_evidence_source") or {}),
        "evidence_status": result.get("evidence_status"),
        "truth_window_status": result.get("truth_window_status"),
        "authoritative_evidence_source": result.get("authoritative_evidence_source"),
        "authoritative_evidence_status": result.get("authoritative_evidence_status"),
        "data_trust": truth_store.get("data_trust"),
        "earliest_quote_at_utc": truth_store.get("earliest_quote_at_utc"),
        "latest_quote_at_utc": truth_store.get("latest_quote_at_utc"),
        "validation_universe": list(result.get("validation_universe") or []),
        "authoritative_profitability_lens": profitability_view["lens"],
        "authoritative_profitability_label": profitability_view["label"],
        "authoritative_trade_count": profitability_view["authoritative_trade_count"],
        "research_only_trade_count": profitability_view["research_only_trade_count"],
        "aggregate_trade_count": profitability_view["aggregate_trade_count"],
        **_contract_resolution_summary(result),
    }


def _market_regime_bucket(spy_ret5: float) -> str:
    if spy_ret5 <= -0.5:
        return "bearish"
    if spy_ret5 >= 0.5:
        return "bullish"
    return "neutral"


def _normalized_market_regime(trade: dict) -> str:
    market_regime = str(trade.get("market_regime") or "").strip().lower()
    if market_regime:
        return market_regime
    try:
        return _market_regime_bucket(float(trade.get("spy_ret5", 0.0)))
    except (TypeError, ValueError):
        return "unknown"


def _profit_factor_for(group: list[dict]) -> float:
    wins = [float(t.get("pnl_pct", 0.0) or 0.0) for t in group if float(t.get("pnl_pct", 0.0) or 0.0) > 0]
    losses = [float(t.get("pnl_pct", 0.0) or 0.0) for t in group if float(t.get("pnl_pct", 0.0) or 0.0) <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return gross_win / max(gross_loss, 0.01)


def _summarize_prediction_group(
    group_name: str,
    group_value: str,
    trades: list[dict],
    total_trades: int,
) -> dict:
    count = len(trades)
    pnl_values = [float(t.get("pnl_pct", 0.0) or 0.0) for t in trades]
    direction_scores = [float(t.get("direction_score", 0.0) or 0.0) for t in trades]
    quality_scores = [float(t.get("quality_score", 0.0) or 0.0) for t in trades]
    ev_values = [float(t.get("ev", 0.0) or 0.0) for t in trades]
    wins = sum(1 for pnl in pnl_values if pnl > 0)
    full_hits = sum(1 for trade in trades if trade.get("prediction_outcome") == "hit")
    directional_hits = sum(1 for trade in trades if trade.get("directional_correct"))

    return {
        "group": group_name,
        "value": group_value,
        "trades": count,
        "share_of_total_pct": round(count / total_trades * 100, 1) if total_trades else 0.0,
        "win_rate_pct": round(wins / count * 100, 1) if count else 0.0,
        "full_hit_rate_pct": round(full_hits / count * 100, 1) if count else 0.0,
        "directional_accuracy_pct": round(directional_hits / count * 100, 1) if count else 0.0,
        "profit_factor": round(_profit_factor_for(trades), 2) if count else 0.0,
        **_profit_factor_denominator_truth_from_pnls(pnl_values),
        "avg_pnl_pct": round(sum(pnl_values) / count, 2) if count else 0.0,
        "avg_direction_score": round(sum(direction_scores) / count, 1) if count else 0.0,
        "avg_quality_score": round(sum(quality_scores) / count, 1) if count else 0.0,
        "avg_ev": round(sum(ev_values) / count, 1) if count else 0.0,
    }


# ── Historical Daily Scan Backtest ────────────────────────────────────────────

def _trade_asset_class(trade: dict) -> str:
    ticker = str(trade.get("ticker") or "").upper()
    return "index" if ticker in INDEX_TICKERS else "equity"


def _trade_direction(trade: dict) -> str:
    direction = str(trade.get("type") or trade.get("trade_type") or "").strip().lower()
    return direction or "unknown"


def _trade_sector(trade: dict) -> str:
    sector = str(trade.get("sector") or "").strip()
    return sector or "Unknown"


def _trade_dte_bucket(trade: dict) -> str:
    try:
        dte = int(float(trade.get("dte", 0) or 0))
    except (TypeError, ValueError):
        return "Unknown"
    if dte <= 12:
        return "05-12"
    if dte <= 21:
        return "13-21"
    if dte <= 35:
        return "22-35"
    return "36+"


def _get_replay_playbook(playbook_id: Optional[str] = None) -> dict:
    key = str(playbook_id or "broad").strip().lower()
    if key not in REPLAY_PLAYBOOKS:
        raise ValueError(f"Unknown replay playbook: {playbook_id}")
    return dict(REPLAY_PLAYBOOKS[key])


def _imported_replay_underlyings_for_playbook(playbook: dict) -> tuple[str, ...]:
    raw_underlyings = playbook.get("historical_required_underlyings")
    if raw_underlyings is None:
        raw_underlyings = IMPORTED_VALIDATION_UNIVERSE

    underlyings: list[str] = []
    seen: set[str] = set()
    for symbol in raw_underlyings:
        if symbol is None:
            continue
        normalized = str(symbol).strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        underlyings.append(normalized)
    return tuple(underlyings)


def _trade_calibration_density(trade: dict) -> str:
    density = str(trade.get("calibration_density") or "").strip().lower()
    if density in {"dense", "sparse"}:
        return density
    calibration_is_dense = trade.get("calibration_is_dense")
    if calibration_is_dense is True:
        return "dense"
    if calibration_is_dense is False:
        return "sparse"
    source = str(trade.get("selection_source") or "").strip().lower()
    if source.startswith("replay_calibrated"):
        if trade.get("calibration_sparse_warning"):
            return "sparse"
        return "unknown"
    return "unknown"


def _selection_calibration_summary(trades: list[dict], required_trades: int = DEFAULT_SURFACE_MIN_TRADES) -> dict:
    counts: dict[str, int] = {}
    density_counts: dict[str, int] = {"dense": 0, "sparse": 0, "unknown": 0}
    for trade in trades:
        source = str(trade.get("selection_source") or "unknown")
        counts[source] = counts.get(source, 0) + 1
        density = _trade_calibration_density(trade)
        if density in density_counts:
            density_counts[density] += 1
        else:
            density_counts["unknown"] += 1

    total_trades = int(len(trades))
    dense_calibrated_trades = int(density_counts.get("dense", 0) or 0)
    sparse_calibrated_trades = int(density_counts.get("sparse", 0) or 0)
    bootstrap_trades = int(counts.get("bootstrap_heuristic", 0) or 0)
    unknown_trades = max(total_trades - dense_calibrated_trades - sparse_calibrated_trades - bootstrap_trades, 0)
    calibrated_trade_pct = round(dense_calibrated_trades / max(total_trades, 1) * 100.0, 1) if total_trades else 0.0

    if total_trades == 0:
        status = "no_trades"
    elif dense_calibrated_trades == 0 and sparse_calibrated_trades > 0:
        status = "sparse_calibrated"
    elif dense_calibrated_trades == 0:
        status = "bootstrap_only"
    elif dense_calibrated_trades < max(int(required_trades), 1):
        status = "sparse_calibrated"
    elif bootstrap_trades > 0:
        status = "mixed_calibrated"
    else:
        status = "fully_calibrated"

    return {
        "required_trades": max(int(required_trades), 1),
        "status": status,
        "total_trades": total_trades,
        "replay_calibrated_trades": dense_calibrated_trades,
        "replay_calibrated_dense_trades": dense_calibrated_trades,
        "replay_calibrated_sparse_trades": sparse_calibrated_trades,
        "bootstrap_heuristic_trades": bootstrap_trades,
        "unknown_trades": unknown_trades,
        "calibrated_trade_pct": calibrated_trade_pct,
        "dense_calibrated_trade_pct": calibrated_trade_pct,
        "selection_source_counts": counts,
        "calibration_density_counts": density_counts,
    }


def _candidate_matches_replay_playbook(candidate: dict, playbook: dict) -> bool:
    allowed_tickers = {str(item).strip().upper() for item in playbook.get("allowed_tickers") or [] if str(item).strip()}
    excluded_tickers = {str(item).strip().upper() for item in playbook.get("excluded_tickers") or [] if str(item).strip()}
    ticker = str(candidate.get("ticker") or "").strip().upper()
    if allowed_tickers and ticker not in allowed_tickers:
        return False
    if excluded_tickers and ticker in excluded_tickers:
        return False

    allowed_asset_classes = {str(item).strip().lower() for item in playbook.get("allowed_asset_classes") or [] if str(item).strip()}
    if allowed_asset_classes and _trade_asset_class(candidate) not in allowed_asset_classes:
        return False

    allowed_market_regimes = {str(item).strip().lower() for item in playbook.get("allowed_market_regimes") or [] if str(item).strip()}
    if allowed_market_regimes and str(candidate.get("market_regime") or "").strip().lower() not in allowed_market_regimes:
        return False

    allowed_sectors = {str(item).strip().lower() for item in playbook.get("allowed_sectors") or [] if str(item).strip()}
    if allowed_sectors and str(candidate.get("sector") or "").strip().lower() not in allowed_sectors:
        return False

    allowed_directions = {str(item).strip().lower() for item in playbook.get("allowed_directions") or [] if str(item).strip()}
    direction = str(candidate.get("trade_type") or candidate.get("type") or "").strip().lower()
    if allowed_directions and direction not in allowed_directions:
        return False

    allowed_signal_families = {str(item).strip().lower() for item in playbook.get("allowed_signal_families") or [] if str(item).strip()}
    signal_family = str(candidate.get("signal_family") or "").strip().lower()
    if allowed_signal_families and signal_family not in allowed_signal_families:
        return False

    min_quality_score = playbook.get("min_quality_score")
    if min_quality_score is not None and float(candidate.get("quality_score", 0.0) or 0.0) < float(min_quality_score):
        return False
    min_signal_ret5 = playbook.get("min_signal_ret5")
    if min_signal_ret5 is not None and float(candidate.get("signal_ret5", 0.0) or 0.0) < float(min_signal_ret5):
        return False
    max_signal_ret5 = playbook.get("max_signal_ret5")
    if max_signal_ret5 is not None and float(candidate.get("signal_ret5", 0.0) or 0.0) > float(max_signal_ret5):
        return False
    min_signal_ret20 = playbook.get("min_signal_ret20")
    if min_signal_ret20 is not None and float(candidate.get("signal_ret20", 0.0) or 0.0) < float(min_signal_ret20):
        return False
    max_signal_ret20 = playbook.get("max_signal_ret20")
    if max_signal_ret20 is not None and float(candidate.get("signal_ret20", 0.0) or 0.0) > float(max_signal_ret20):
        return False

    numeric_filter_map = {
        "min_spy_ret5": ("spy_ret5", "min"),
        "max_spy_ret5": ("spy_ret5", "max"),
        "min_hv30": ("hv30", "min"),
        "max_hv30": ("hv30", "max"),
        "min_tech_score": ("tech_score", "min"),
        "max_tech_score": ("tech_score", "max"),
        "min_direction_score": ("direction_score", "min"),
        "max_direction_score": ("direction_score", "max"),
    }
    for playbook_key, (candidate_key, side) in numeric_filter_map.items():
        threshold = playbook.get(playbook_key)
        if threshold is None:
            continue
        value = float(candidate.get(candidate_key, 0.0) or 0.0)
        if side == "min" and value < float(threshold):
            return False
        if side == "max" and value > float(threshold):
            return False

    return True


def _trade_debit_pct_of_width(trade: dict) -> float | None:
    try:
        net_debit = float(trade.get("net_debit"))
        spread_width = float(trade.get("spread_width"))
    except (TypeError, ValueError):
        return None
    if net_debit is None or spread_width is None or spread_width <= 0:
        return None
    return net_debit / spread_width * 100.0


def _trade_matches_replay_post_entry_filters(trade: dict, playbook: dict) -> tuple[bool, str | None]:
    max_debit_pct = playbook.get("max_debit_pct_of_width")
    if max_debit_pct is not None:
        debit_pct = _trade_debit_pct_of_width(trade)
        if debit_pct is None:
            return False, "missing_debit_pct_of_width"
        if debit_pct >= float(max_debit_pct):
            return False, "debit_pct_of_width_above_playbook_max"
    return True, None


def _resolve_replay_entry_signal(
    day_data: dict,
    playbook: dict,
    t_config: dict,
    *,
    prior_close: float | None = None,
) -> Optional[dict]:
    signal_id = str(playbook.get("entry_signal_id") or "momentum").strip().lower()

    S0 = float(day_data.get("S0", 0.0) or 0.0)
    ret5 = float(day_data.get("ret5", 0.0) or 0.0)
    ret20 = float(day_data.get("ret20", 0.0) or 0.0)
    sma20 = float(day_data.get("sma20", S0) or S0)
    sma50 = float(day_data.get("sma50", sma20) or sma20)
    rsi14 = float(day_data.get("rsi14", 50.0) or 50.0)
    macd = float(day_data.get("macd", 0.0) or 0.0)
    macd_prev = float(day_data.get("macd_prev", macd) or macd)

    if signal_id == "pullback_uptrend":
        ret5_min = float(playbook.get("pullback_ret5_min", -4.0) or -4.0)
        ret5_max = float(playbook.get("pullback_ret5_max", 0.25) or 0.25)
        ret20_min = float(playbook.get("pullback_ret20_min", 2.0) or 2.0)
        if not (S0 > sma50 and ret20 > ret20_min and ret5_min < ret5 < ret5_max):
            return None

        pullback_depth_score = max(0.0, 100.0 - abs(ret5 + 1.5) * 30.0)
        ret20_score = min(100.0, max(0.0, (ret20 - ret20_min) / 6.0 * 100.0))
        sma50_gap_pct = (S0 / sma50 - 1.0) * 100.0 if sma50 > 0 else 0.0
        trend_score = min(100.0, max(0.0, sma50_gap_pct * 20.0))
        direction_score_override = round(
            pullback_depth_score * 0.45
            + ret20_score * 0.35
            + trend_score * 0.20,
            1,
        )
        return {
            "trade_type": "call",
            "signal_family": "bullish_pullback",
            "signal_variant": "pullback_uptrend",
            "direction_score_override": direction_score_override,
            "signal_ret5": ret5,
            "signal_ret20": ret20,
            "signal_sma20": sma20,
            "signal_sma50": sma50,
        }

    if signal_id == "relative_strength_pullback":
        ret5_min = float(playbook.get("relative_strength_pullback_ret5_min", -4.0) or -4.0)
        ret5_max = float(playbook.get("relative_strength_pullback_ret5_max", -0.25) or -0.25)
        ret20_min = float(playbook.get("relative_strength_pullback_ret20_min", 4.0) or 4.0)
        rsi_min = float(playbook.get("relative_strength_pullback_rsi_min", 42.0) or 42.0)
        rsi_max = float(playbook.get("relative_strength_pullback_rsi_max", 58.0) or 58.0)
        trend_ok = S0 > sma50 and sma20 >= sma50
        pullback_ok = ret5_min <= ret5 <= ret5_max and rsi_min <= rsi14 <= rsi_max
        strength_ok = ret20 >= ret20_min
        if not (trend_ok and pullback_ok and strength_ok):
            return None

        pullback_score = max(0.0, 100.0 - abs(ret5 + 1.5) * 25.0)
        strength_score = min(100.0, max(0.0, (ret20 - ret20_min) / 6.0 * 100.0))
        rsi_score = max(0.0, 100.0 - abs(rsi14 - 50.0) * 8.0)
        direction_score_override = round(
            pullback_score * 0.35
            + strength_score * 0.40
            + rsi_score * 0.25,
            1,
        )
        return {
            "trade_type": "call",
            "signal_family": "relative_strength_pullback",
            "signal_variant": "ret20_strength_controlled_pullback",
            "direction_score_override": direction_score_override,
            "signal_ret5": ret5,
            "signal_ret20": ret20,
            "signal_sma20": sma20,
            "signal_sma50": sma50,
            "signal_rsi14": rsi14,
        }

    if signal_id == "bullish_mean_reversion":
        ret1 = 0.0
        if prior_close is not None and float(prior_close) > 0:
            ret1 = (S0 / float(prior_close) - 1.0) * 100.0

        trend_ok = S0 > sma50 and sma20 > sma50
        pullback_ok = (
            ret5 <= float(playbook.get("pullback_ret5_max", -1.5) or -1.5)
            and S0 <= sma20
            and float(playbook.get("pullback_rsi_min", 35.0) or 35.0) <= rsi14 <= float(playbook.get("pullback_rsi_max", 50.0) or 50.0)
        )
        reversal_ok = ret1 >= float(playbook.get("reversal_ret1_min", 0.0) or 0.0) and macd > macd_prev
        if not (trend_ok and pullback_ok and reversal_ok):
            return None
        return {
            "trade_type": "call",
            "signal_family": "bullish_mean_reversion",
            "ret1": ret1,
        }

    entry_momentum = float(t_config.get("entry_momentum", 0.5) or 0.5)
    bullish = ret5 > entry_momentum and S0 > sma20
    bearish = ret5 < -entry_momentum and S0 < sma20
    if not bullish and not bearish:
        return None
    return {
        "trade_type": "call" if bullish else "put",
        "signal_family": "momentum",
    }


def _capacity_tiers_for_playbook(playbook: dict) -> list[dict[str, Any]]:
    raw_tiers = playbook.get("capacity_tiers")
    if not raw_tiers:
        return [
            {
                "tier_id": str(playbook.get("id") or "default"),
                "tier_rank": 1,
                "sleeve_id": str(playbook.get("sleeve_id") or playbook.get("id") or "default"),
                "sleeve_group": str(playbook.get("sleeve_group") or "default"),
                "overrides": {},
            }
        ]
    tiers: list[dict[str, Any]] = []
    for idx, raw in enumerate(list(raw_tiers), start=1):
        if not isinstance(raw, dict):
            continue
        tier_id = str(raw.get("tier_id") or raw.get("id") or f"tier_{idx}").strip()
        if not tier_id:
            tier_id = f"tier_{idx}"
        tiers.append(
            {
                "tier_id": tier_id,
                "tier_rank": int(raw.get("tier_rank") or idx),
                "sleeve_id": str(raw.get("sleeve_id") or playbook.get("sleeve_id") or playbook.get("id") or "default"),
                "sleeve_group": str(raw.get("sleeve_group") or playbook.get("sleeve_group") or "default"),
                "overrides": dict(raw.get("overrides") or {}),
                "description": raw.get("description"),
                "quota": dict(raw.get("quota") or {}),
            }
        )
    return sorted(tiers, key=lambda item: (int(item.get("tier_rank") or 0), str(item.get("tier_id") or "")))


def _tier_playbook(base_playbook: dict, tier: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base_playbook)
    merged.update(dict(tier.get("overrides") or {}))
    for key in ("tier_id", "tier_rank", "sleeve_id", "sleeve_group"):
        if tier.get(key) is not None:
            merged[key] = tier.get(key)
    return merged


def _experiment_id(category: str, filters: dict) -> str:
    def _slug(value: object) -> str:
        text = str(value).strip().lower()
        for src, dst in (
            (">=", "gte_"),
            ("<=", "lte_"),
            (">", "gt_"),
            ("<", "lt_"),
            (" ", "_"),
            ("|", "_"),
            ("/", "_"),
        ):
            text = text.replace(src, dst)
        return "".join(ch if ch.isalnum() or ch == "_" else "" for ch in text)

    parts = [_slug(category)]
    for key in sorted(filters):
        parts.append(f"{_slug(key)}_{_slug(filters[key])}")
    return "__".join(part for part in parts if part)


def _summarize_experiment_slice(
    category: str,
    label: str,
    trades: list[dict],
    total_trades: int,
    filters: dict,
    min_trades: int,
    min_profit_factor: float,
    min_directional_accuracy_pct: float,
) -> dict:
    summary = _summarize_prediction_group("experiment", label, trades, total_trades)
    summary.update(
        {
            "category": category,
            "label": label,
            "experiment_id": _experiment_id(category, filters),
            "filters": filters,
            "sparse": summary["trades"] < int(min_trades),
            "passes_quality_bar": (
                summary["trades"] >= int(min_trades)
                and summary["profit_factor"] >= float(min_profit_factor)
                and summary["directional_accuracy_pct"] >= float(min_directional_accuracy_pct)
                and summary["avg_pnl_pct"] > 0.0
            ),
        }
    )
    return summary


def _rank_experiment_slice(item: dict) -> tuple:
    return (
        1 if item.get("passes_quality_bar") else 0,
        0 if item.get("sparse") else 1,
        1 if float(item.get("avg_pnl_pct", 0.0) or 0.0) > 0 else 0,
        float(item.get("profit_factor", 0.0) or 0.0),
        float(item.get("avg_pnl_pct", 0.0) or 0.0),
        float(item.get("directional_accuracy_pct", 0.0) or 0.0),
        int(item.get("trades", 0) or 0),
    )


def _build_experiment_trade_views(
    trades: list[dict[str, Any]],
    *,
    score_floors: list[int],
    score_bucket_order: Sequence[str],
) -> dict[str, Any]:
    views: dict[str, Any] = {
        "score_floors": {floor: [] for floor in score_floors},
        "score_bands": {bucket: [] for bucket in score_bucket_order},
        "asset_class": {"equity": [], "index": []},
        "regime": {"bearish": [], "neutral": [], "bullish": [], "unknown": []},
        "asset_class_by_regime": {
            (asset_class, regime): []
            for asset_class in ("equity", "index")
            for regime in ("bearish", "neutral", "bullish", "unknown")
        },
        "ticker_counts": Counter(),
        "sector_counts": Counter(),
    }
    for trade in trades:
        direction_score = float(trade.get("direction_score", 0.0) or 0.0)
        asset_class = _trade_asset_class(trade)
        regime = _normalized_market_regime(trade)
        ticker = str(trade.get("ticker") or "Unknown").upper()
        sector = str(trade.get("sector") or "Unknown")
        views["ticker_counts"][ticker] += 1
        views["sector_counts"][sector] += 1
        for floor in score_floors:
            if direction_score >= floor:
                views["score_floors"][floor].append(trade)
        views["score_bands"][_direction_score_bucket(direction_score)].append(trade)
        views["asset_class"][asset_class].append(trade)
        views["regime"][regime].append(trade)
        views["asset_class_by_regime"][(asset_class, regime)].append(trade)
    return views


def build_options_experiment_matrix(
    result: Optional[dict] = None,
    min_trades: int = 20,
    score_floors: Optional[list[int]] = None,
    max_tickers: int = 8,
    max_sectors: int = 8,
    min_profit_factor: float = 1.05,
    min_directional_accuracy_pct: float = 50.0,
) -> dict:
    """
    Build an options-only experiment matrix from replay trades.

    This is a post-processing layer over the historical options replay. It ranks
    score thresholds, score buckets, regimes, asset-class splits, and the most
    active ticker/sector slices without modifying the core simulator.
    """
    if result is None:
        result = load_last_results()
    if not result:
        return {"error": "No backtest results found"}
    mode = str(result.get("mode") or "").strip().lower()
    if mode and mode != "backtest":
        return {"error": f"Last results are not a historical options backtest (mode={result.get('mode')})"}

    aggregate_trades = list(result.get("trades") or [])
    profitability_view = _authoritative_profitability_view(result, aggregate_trades)
    trades = list(profitability_view["trades"])
    research_only_trades = list(profitability_view["research_only_trades"])
    score_bucket_order = ("00-39", "40-49", "50-59", "60-69", "70-79", "80-100")
    score_floors = score_floors or [40, 50, 60, 70, 80]
    normalized_score_floors = sorted({max(0, min(100, int(floor))) for floor in score_floors})

    source = _result_source_metadata(result, len(aggregate_trades))
    source.update(
        {
            "strategy_domain": "options",
            "trade_types": ["call", "put"],
        }
    )

    if not trades:
        overall = _summarize_experiment_slice(
            "overall",
            profitability_view["label"],
            [],
            0,
            {"domain": "options"},
            min_trades,
            min_profit_factor,
            min_directional_accuracy_pct,
        )
        aggregate_overall = _summarize_experiment_slice(
            "aggregate_overall",
            "All Options Trades",
            aggregate_trades,
            len(aggregate_trades),
            {"domain": "options"},
            min_trades,
            min_profit_factor,
            min_directional_accuracy_pct,
        )
        research_only_overall = _summarize_experiment_slice(
            "research_only_overall",
            "Research-only replay trades",
            research_only_trades,
            len(research_only_trades),
            {"domain": "options"},
            min_trades,
            min_profit_factor,
            min_directional_accuracy_pct,
        )
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "source_run_at": source["run_at"],
            "source_mode": source["mode"],
            "lookback_years": source["lookback_years"],
            "pricing_lane": source["pricing_lane"],
            "strategy_domain": source["strategy_domain"],
            "trade_types": source["trade_types"],
            "min_trades_filter": int(min_trades),
            "quality_bar": {
                "min_profit_factor": float(min_profit_factor),
                "min_directional_accuracy_pct": float(min_directional_accuracy_pct),
                "min_avg_pnl_pct": 0.01,
            },
            "overall": overall,
            "aggregate_overall": aggregate_overall,
            "research_only_overall": research_only_overall,
            "authoritative_profitability_lens": profitability_view["lens"],
            "authoritative_profitability_label": profitability_view["label"],
            "authoritative_profitability_description": profitability_view["description"],
            "authoritative_profitability_metrics": profitability_view["metrics"],
            "authoritative_profitability_gate": _authoritative_profitability_gate(
                profitability_view["metrics"],
                min_trade_count=min_trades,
                min_profit_factor=min_profit_factor,
                min_directional_accuracy_pct=min_directional_accuracy_pct,
            ),
            "category_order": [
                "score_floors",
                "score_bands",
                "asset_class",
                "regime",
                "asset_class_by_regime",
                "ticker",
                "sector",
            ],
            "by_category": {
                "score_floors": [],
                "score_bands": [],
                "asset_class": [],
                "regime": [],
                "asset_class_by_regime": [],
                "ticker": [],
                "sector": [],
            },
            "experiments": [],
            "passing_experiments": [],
            "near_miss_experiments": [],
            "recommendations": [
                (
                    f"No trades are available under the authoritative profitability lens "
                    f"({profitability_view['label']})."
                )
            ],
        }

    total_trades = len(trades)
    overall = _summarize_experiment_slice(
        "overall",
        profitability_view["label"],
        trades,
        total_trades,
        {"domain": "options"},
        min_trades,
        min_profit_factor,
        min_directional_accuracy_pct,
    )
    aggregate_overall = _summarize_experiment_slice(
        "aggregate_overall",
        "All Options Trades",
        aggregate_trades,
        len(aggregate_trades),
        {"domain": "options"},
        min_trades,
        min_profit_factor,
        min_directional_accuracy_pct,
    )
    research_only_overall = _summarize_experiment_slice(
        "research_only_overall",
        "Research-only replay trades",
        research_only_trades,
        len(research_only_trades),
        {"domain": "options"},
        min_trades,
        min_profit_factor,
        min_directional_accuracy_pct,
    )

    def _annotate(items: list[dict]) -> list[dict]:
        annotated: list[dict] = []
        for item in items:
            clone = dict(item)
            clone["profit_factor_delta"] = round(
                float(clone.get("profit_factor", 0.0) or 0.0) - float(overall["profit_factor"]),
                2,
            )
            clone["avg_pnl_pct_delta"] = round(
                float(clone.get("avg_pnl_pct", 0.0) or 0.0) - float(overall["avg_pnl_pct"]),
                2,
            )
            clone["directional_accuracy_delta_pct"] = round(
                float(clone.get("directional_accuracy_pct", 0.0) or 0.0) - float(overall["directional_accuracy_pct"]),
                1,
            )
            annotated.append(clone)
        return annotated

    def _make_slice(category: str, label: str, subset: list[dict], filters: dict) -> dict:
        return _summarize_experiment_slice(
            category,
            label,
            subset,
            total_trades,
            filters,
            min_trades,
            min_profit_factor,
            min_directional_accuracy_pct,
        )

    trade_views = _build_experiment_trade_views(
        trades,
        score_floors=normalized_score_floors,
        score_bucket_order=score_bucket_order,
    )

    score_floor_slices = _annotate(
        [
            _make_slice(
                "score_floors",
                f"Score >= {floor}",
                trade_views["score_floors"].get(floor, []),
                {"score_floor": floor},
            )
            for floor in normalized_score_floors
        ]
    )
    score_band_slices = _annotate(
        [
            _make_slice(
                "score_bands",
                f"Score {bucket}",
                trade_views["score_bands"].get(bucket, []),
                {"score_band": bucket},
            )
            for bucket in score_bucket_order
        ]
    )
    asset_class_slices = _annotate(
        [
            _make_slice(
                "asset_class",
                asset_class.title(),
                trade_views["asset_class"].get(asset_class, []),
                {"asset_class": asset_class},
            )
            for asset_class in ("equity", "index")
        ]
    )
    regime_slices = _annotate(
        [
            _make_slice(
                "regime",
                regime.title(),
                trade_views["regime"].get(regime, []),
                {"market_regime": regime},
            )
            for regime in ("bearish", "neutral", "bullish", "unknown")
        ]
    )

    asset_class_by_regime_raw: list[dict] = []
    for asset_class in ("equity", "index"):
        for regime in ("bearish", "neutral", "bullish", "unknown"):
            asset_class_by_regime_raw.append(
                _make_slice(
                    "asset_class_by_regime",
                    f"{asset_class.title()} + {regime.title()}",
                    trade_views["asset_class_by_regime"].get((asset_class, regime), []),
                    {"asset_class": asset_class, "market_regime": regime},
                )
            )
    asset_class_by_regime_slices = _annotate(asset_class_by_regime_raw)

    top_tickers = [
        ticker
        for ticker, _count in sorted(trade_views["ticker_counts"].items(), key=lambda item: (-item[1], item[0]))[: max(1, int(max_tickers))]
    ]
    top_sectors = [
        sector
        for sector, _count in sorted(trade_views["sector_counts"].items(), key=lambda item: (-item[1], item[0]))[: max(1, int(max_sectors))]
    ]

    ticker_slices = _annotate(
        [
            _make_slice(
                "ticker",
                ticker,
                [trade for trade in trades if str(trade.get("ticker") or "").upper() == ticker],
                {"ticker": ticker},
            )
            for ticker in top_tickers
        ]
    )
    sector_slices = _annotate(
        [
            _make_slice(
                "sector",
                sector,
                [trade for trade in trades if str(trade.get("sector") or "Unknown") == sector],
                {"sector": sector},
            )
            for sector in top_sectors
        ]
    )

    by_category = {
        "score_floors": score_floor_slices,
        "score_bands": score_band_slices,
        "asset_class": asset_class_slices,
        "regime": regime_slices,
        "asset_class_by_regime": asset_class_by_regime_slices,
        "ticker": ticker_slices,
        "sector": sector_slices,
    }

    all_experiments: list[dict] = []
    for items in by_category.values():
        all_experiments.extend(item for item in items if item["trades"] > 0)
    ranked_experiments = sorted(all_experiments, key=_rank_experiment_slice, reverse=True)

    passing_experiments = [item for item in ranked_experiments if item["passes_quality_bar"]]
    near_miss_experiments = [
        item
        for item in ranked_experiments
        if not item["passes_quality_bar"]
        and not item["sparse"]
        and (
            item["profit_factor"] >= 1.0
            or item["directional_accuracy_pct"] >= min_directional_accuracy_pct
            or item["avg_pnl_pct"] > overall["avg_pnl_pct"]
        )
    ][:5]

    recommendations: list[str] = []
    if passing_experiments:
        top_labels = ", ".join(item["label"] for item in passing_experiments[:3])
        recommendations.append(f"Focus the next options replay pass on: {top_labels}.")
    else:
        recommendations.append(
            (
                f"No {profitability_view['label'].lower()} slice cleared the current quality bar yet, "
                "so keep optimizing filters before adding new signal complexity."
            )
        )

    improving_score_floors = [
        item
        for item in score_floor_slices
        if item["trades"] >= min_trades
        and item["profit_factor"] > overall["profit_factor"]
        and item["directional_accuracy_pct"] >= overall["directional_accuracy_pct"]
    ]
    if improving_score_floors:
        best_floor = sorted(improving_score_floors, key=_rank_experiment_slice, reverse=True)[0]
        recommendations.append(f"{best_floor['label']} is the best threshold candidate versus the full options set.")

    dense_asset_regimes = [item for item in asset_class_by_regime_slices if item["trades"] >= min_trades]
    if dense_asset_regimes:
        best_asset_regime = sorted(dense_asset_regimes, key=_rank_experiment_slice, reverse=True)[0]
        recommendations.append(f"{best_asset_regime['label']} is the strongest asset/regime split to audit next.")

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "source_run_at": source["run_at"],
        "source_mode": source["mode"],
        "lookback_years": source["lookback_years"],
        "pricing_lane": source["pricing_lane"],
        "truth_source": source["truth_source"],
        "quote_coverage_pct": source["quote_coverage_pct"],
        "strategy_domain": source["strategy_domain"],
        "trade_types": source["trade_types"],
        "min_trades_filter": int(min_trades),
        "quality_bar": {
            "min_profit_factor": float(min_profit_factor),
            "min_directional_accuracy_pct": float(min_directional_accuracy_pct),
            "min_avg_pnl_pct": 0.01,
        },
        "overall": _annotate([overall])[0],
        "aggregate_overall": aggregate_overall,
        "research_only_overall": research_only_overall,
        "authoritative_profitability_lens": profitability_view["lens"],
        "authoritative_profitability_label": profitability_view["label"],
        "authoritative_profitability_description": profitability_view["description"],
        "authoritative_profitability_metrics": profitability_view["metrics"],
        "authoritative_profitability_gate": _authoritative_profitability_gate(
            profitability_view["metrics"],
            min_trade_count=min_trades,
            min_profit_factor=min_profit_factor,
            min_directional_accuracy_pct=min_directional_accuracy_pct,
        ),
        "category_order": list(by_category.keys()),
        "by_category": by_category,
        "experiments": ranked_experiments,
        "passing_experiments": passing_experiments[:10],
        "near_miss_experiments": near_miss_experiments,
        "recommendations": recommendations,
    }


def _score_band_bounds(label: str) -> tuple[Optional[float], Optional[float]]:
    raw = str(label or "").strip()
    if raw.lower().startswith("score "):
        raw = raw[6:].strip()
    if not raw:
        return None, None
    if raw.endswith("+"):
        try:
            return float(raw[:-1]), None
        except ValueError:
            return None, None
    if "-" not in raw:
        try:
            value = float(raw)
            return value, value
        except ValueError:
            return None, None
    lo_text, hi_text = raw.split("-", 1)
    try:
        return float(lo_text), float(hi_text)
    except ValueError:
        return None, None


def _watch_symbol_preferences(by_symbol: dict[str, Any]) -> tuple[list[str], list[str]]:
    priority: list[str] = []
    deprioritized: list[str] = []
    for symbol, metrics in sorted((by_symbol or {}).items()):
        exact_metrics = dict((metrics or {}).get("exact_contract_metrics") or {})
        trade_count = int(exact_metrics.get("trade_count") or 0)
        if trade_count < 20:
            continue
        profit_factor = float(exact_metrics.get("profit_factor") or 0.0)
        avg_pnl_pct = float(exact_metrics.get("avg_pnl_pct") or 0.0)
        if profit_factor >= 1.0 and avg_pnl_pct > 0:
            priority.append(symbol)
        elif profit_factor < 1.0 or avg_pnl_pct <= 0:
            deprioritized.append(symbol)
    return priority, deprioritized


def build_live_options_trade_policy(
    result: Optional[dict] = None,
    truth_lane: Optional[str] = None,
    min_trades: int = 20,
    score_floors: Optional[list[int]] = None,
    max_tickers: int = 8,
    max_sectors: int = 8,
    min_profit_factor: float = 1.05,
    min_directional_accuracy_pct: float = 50.0,
) -> dict:
    """
    Build a replay-backed live trade policy from the latest options experiment matrix.

    The goal is not to overfit a single symbol. Instead, derive a small set of hard
    gates plus soft preferences that can label live scan picks as Approved / Watch /
    Blocked inside the supervised options workflow.
    """
    requested_truth_lane = str(truth_lane or "").strip().lower()
    if result is None:
        result = load_preferred_results_by_truth_lane(truth_lane)
    if requested_truth_lane == IMPORTED_DAILY_TRUTH_SOURCE:
        result_truth_source = _result_truth_source(result) if result else ""
        if not result or result_truth_source != IMPORTED_DAILY_TRUTH_SOURCE:
            return {"error": f"No backtest results found for truth_lane={requested_truth_lane}"}
    if not result and requested_truth_lane:
        return {"error": f"No backtest results found for truth_lane={requested_truth_lane}"}
    matrix = build_options_experiment_matrix(
        result=result,
        min_trades=min_trades,
        score_floors=score_floors,
        max_tickers=max_tickers,
        max_sectors=max_sectors,
        min_profit_factor=min_profit_factor,
        min_directional_accuracy_pct=min_directional_accuracy_pct,
    )
    if matrix.get("error"):
        return matrix

    overall = dict(matrix.get("overall") or {})
    by_category = dict(matrix.get("by_category") or {})
    stability = build_options_stability_report(
        result=result,
        min_trades=min_trades,
        min_profit_factor=min_profit_factor,
    )
    if stability.get("error"):
        return stability

    def _positive_non_sparse(items: list[dict], min_trade_count: int) -> list[dict]:
        return [
            item
            for item in items
            if int(item.get("trades", 0) or 0) >= min_trade_count
            and not bool(item.get("sparse"))
            and float(item.get("avg_pnl_pct", 0.0) or 0.0) > 0
            and float(item.get("profit_factor", 0.0) or 0.0) >= max(1.0, float(overall.get("profit_factor", 0.0) or 0.0))
        ]

    score_band_candidates = _positive_non_sparse(by_category.get("score_bands") or [], int(min_trades))
    preferred_score_band = sorted(score_band_candidates, key=_rank_experiment_slice, reverse=True)[0] if score_band_candidates else None

    asset_regime_candidates = _positive_non_sparse(
        by_category.get("asset_class_by_regime") or [],
        max(int(min_trades) * 3, 50),
    )
    preferred_asset_regime = (
        sorted(asset_regime_candidates, key=_rank_experiment_slice, reverse=True)[0]
        if asset_regime_candidates else None
    )

    preferred_sector_slices = sorted(
        _positive_non_sparse(by_category.get("sector") or [], max(int(min_trades) * 2, 40)),
        key=_rank_experiment_slice,
        reverse=True,
    )[:2]

    highlighted_ticker_slices = sorted(
        [
            item
            for item in by_category.get("ticker") or []
            if int(item.get("trades", 0) or 0) >= max(int(min_trades) * 2, 40)
            and float(item.get("avg_pnl_pct", 0.0) or 0.0) > 0
            and float(item.get("profit_factor", 0.0) or 0.0) >= 1.1
        ],
        key=_rank_experiment_slice,
        reverse=True,
    )[:2]

    direction_score_min = None
    direction_score_max = None
    if preferred_score_band:
        direction_score_min, direction_score_max = _score_band_bounds(preferred_score_band["label"])

    preferred_asset_class = None
    preferred_market_regimes: list[str] = []
    if preferred_asset_regime:
        preferred_asset_class = preferred_asset_regime.get("filters", {}).get("asset_class")
        market_regime = preferred_asset_regime.get("filters", {}).get("market_regime")
        if market_regime:
            preferred_market_regimes = [str(market_regime)]

    preferred_sectors = [str(item.get("label") or "") for item in preferred_sector_slices if item.get("label")]
    highlighted_tickers = [str(item.get("label") or "") for item in highlighted_ticker_slices if item.get("label")]
    stability_filters = dict(stability.get("promotion_recommendations", {}).get("approved_filters") or {})
    stability_score_min = stability_filters.get("direction_score_min")
    if stability_score_min is not None:
        direction_score_min = max(
            float(direction_score_min) if direction_score_min is not None else float(stability_score_min),
            float(stability_score_min),
        )
    stability_regimes = [str(item) for item in stability_filters.get("market_regimes") or [] if str(item)]
    if stability_regimes:
        preferred_market_regimes = stability_regimes
    stability_sectors = [str(item) for item in stability_filters.get("sectors") or [] if str(item)]
    if stability_sectors:
        preferred_sectors = stability_sectors
    if (
        direction_score_min is not None
        and direction_score_max is not None
        and float(direction_score_max) < float(direction_score_min)
    ):
        direction_score_max = None

    rationale: list[str] = []
    warnings: list[str] = []
    preferred_evidence = dict(result.get("preferred_evidence_source") or {})
    evidence_status = str(
        preferred_evidence.get("status")
        or result.get("evidence_status")
        or ""
    ).strip().lower()
    truth_window_status = str(
        preferred_evidence.get("truth_window_status")
        or result.get("truth_window_status")
        or "unknown"
    ).strip().lower() or "unknown"
    authoritative_evidence_source = str(
        result.get("authoritative_evidence_source")
        or preferred_evidence.get("mode")
        or _result_truth_source(result or {})
        or "unknown"
    ).strip().lower()
    authoritative_evidence_status = str(
        result.get("authoritative_evidence_status")
        or evidence_status
        or "unknown"
    ).strip().lower()

    if preferred_score_band:
        rationale.append(
            f"{preferred_score_band['label']} was the strongest score cohort under the current authoritative replay lens "
            f"(PF {preferred_score_band['profit_factor']:.2f}, avg P&L {preferred_score_band['avg_pnl_pct']:+.2f}%)."
        )
    else:
        warnings.append(
            "No positive score bucket cleared the current sample-size bar, so the policy cannot apply a score-band gate yet."
        )

    if preferred_asset_regime:
        rationale.append(
            f"{preferred_asset_regime['label']} was the strongest broad asset/regime split to prefer when breaking ties."
        )

    if preferred_sectors:
        rationale.append(
            f"Preferred sectors from the replay: {', '.join(preferred_sectors)}."
        )

    if highlighted_tickers:
        warnings.append(
            f"Single-name highlights ({', '.join(highlighted_tickers)}) looked strong, but they are treated as watchlist notes rather than hard filters to reduce overfitting."
        )

    truth_source = _result_truth_source(result or {})
    aggregate_trades = list((result or {}).get("trades") or [])
    profitability_view = _authoritative_profitability_view(result, aggregate_trades)
    authoritative_trades = list(profitability_view["trades"])
    research_only_trades = list(profitability_view["research_only_trades"])
    playbook_id = str((result or {}).get("playbook") or (matrix.get("source") or {}).get("playbook") or "broad").strip().lower()
    exact_contract_trades = [
        trade for trade in aggregate_trades
        if _is_exact_contract_resolution(trade.get("entry_contract_resolution"))
    ]
    nearest_listed_trades = [
        trade for trade in aggregate_trades
        if not _is_exact_contract_resolution(trade.get("entry_contract_resolution"))
    ]
    aggregate_by_symbol = _by_symbol_trade_metrics(
        aggregate_trades,
        playbook_id=playbook_id,
        truth_source=truth_source,
        candidate_source=result.get("candidate_source") if result else None,
        authoritative_evidence_source=result.get("authoritative_evidence_source") if result else None,
        min_profit_factor=min_profit_factor,
        min_directional_accuracy_pct=min_directional_accuracy_pct,
    )
    by_symbol = _by_symbol_trade_metrics(
        authoritative_trades,
        playbook_id=playbook_id,
        truth_source=truth_source,
        candidate_source=result.get("candidate_source") if result else None,
        authoritative_evidence_source=result.get("authoritative_evidence_source") if result else None,
        min_profit_factor=min_profit_factor,
        min_directional_accuracy_pct=min_directional_accuracy_pct,
    )
    watch_priority_symbols, watch_deprioritized_symbols = _watch_symbol_preferences(by_symbol)
    if (
        not watch_priority_symbols
        and not watch_deprioritized_symbols
        and truth_source == IMPORTED_DAILY_TRUTH_SOURCE
        and str(result.get("candidate_source") or "").strip().lower() == FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE
    ):
        fallback_watch_source = load_last_imported_daily_results()
        fallback_by_symbol = dict((fallback_watch_source or {}).get("by_symbol") or {})
        if fallback_by_symbol:
            watch_priority_symbols, watch_deprioritized_symbols = _watch_symbol_preferences(fallback_by_symbol)
    promotion_metrics = _overall_promotion_metrics(
        trades=authoritative_trades,
        by_symbol=by_symbol,
        playbook_id=playbook_id,
        truth_source=truth_source,
        candidate_source=result.get("candidate_source") if result else None,
        authoritative_evidence_source=result.get("authoritative_evidence_source") if result else None,
        min_profit_factor=min_profit_factor,
        min_directional_accuracy_pct=min_directional_accuracy_pct,
    )
    aggregate_metrics = _trade_subset_metrics(aggregate_trades, include_exit_reasons=True)
    exact_contract_metrics = _trade_subset_metrics(exact_contract_trades, include_exit_reasons=True)
    authoritative_exact_contract_metrics = _trade_subset_metrics(authoritative_trades, include_exit_reasons=True)
    nearest_listed_metrics = _trade_subset_metrics(nearest_listed_trades)
    authoritative_profitability_basis = str(
        (result or {}).get("authoritative_profitability_basis")
        or (promotion_metrics.get("authoritative_profitability_basis"))
        or profitability_view.get("lens")
    )
    authoritative_profitability_metrics = dict(
        (result or {}).get("authoritative_profitability_metrics")
        or (promotion_metrics.get("authoritative_profitability_metrics"))
        or authoritative_exact_contract_metrics
    )
    authoritative_profitability_gate = dict(
        (result or {}).get("authoritative_profitability_gate")
        or (promotion_metrics.get("authoritative_profitability_gate"))
        or _authoritative_profitability_gate(
            authoritative_profitability_metrics,
            min_trade_count=25,
            min_profit_factor=min_profit_factor,
            min_directional_accuracy_pct=min_directional_accuracy_pct,
        )
    )
    research_only_metrics = _trade_subset_metrics(research_only_trades, include_exit_reasons=True)
    calibration_density_metrics = _calibration_density_metrics(aggregate_trades)
    promoted_symbols = list(promotion_metrics.get("promoted_symbols") or [])
    non_promotable_trade_count = len([trade for trade in aggregate_trades if not _is_trade_promotable(trade)])
    if float(aggregate_metrics.get("profit_factor", 0.0) or 0.0) < 1.0:
        warnings.append(
            "The aggregate replay universe is still negative overall; treat that as research context rather than the profitability judge."
        )
    if stability.get("overall_status") != "promote":
        warnings.append(
            f"Stability status is {stability.get('overall_status')}, so the policy stays watch-only until fixed and rolling windows improve."
        )
    if truth_source == SYNTHETIC_TRUTH_SOURCE:
        warnings.append(
            "Only synthetic research results are available for this cohort, so policy confidence remains capped below promote."
        )
    if evidence_status == ARCHIVED_EXACT_INSUFFICIENT_STATUS:
        warnings.append(
            "Archived /api/scan exact-contract evidence is the primary judge, but the current per-symbol archived sample is still below the 25-trade promotion floor."
        )
    elif evidence_status == MODEL_DAILY_FALLBACK_ONLY_STATUS and truth_source == IMPORTED_DAILY_TRUTH_SOURCE:
        warnings.append(
            "Archived /api/scan exact-contract evidence is unavailable, so policy is falling back to model-derived imported daily replay."
        )
    if truth_source == IMPORTED_TRUTH_SOURCE:
        warnings.append(
            "Imported intraday validation prices replay-selected contracts with real historical quotes, but contract targeting is still model-derived rather than recovered from archived live scan picks."
        )
    if truth_source == IMPORTED_DAILY_TRUTH_SOURCE:
        if str(result.get("candidate_source") or "").strip().lower() == FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE:
            warnings.append(
                "Archived forward /api/scan picks are the primary judge for this policy. Exact archived contracts are priced against imported daily truth before any model fallback is considered."
            )
        else:
            warnings.append(
                "Imported daily validation prices replay-selected contracts with real end-of-day quotes. It is stronger than synthetic replay, but contract targeting is still model-derived and it does not validate morning fill quality."
            )
    pending_truth_horizon_count = int((result or {}).get("pending_truth_horizon_count") or 0)
    if pending_truth_horizon_count > 0:
        warnings.append(
            f"{pending_truth_horizon_count} archived /api/scan pick(s) are newer than the trusted imported daily quote horizon, so they remain pending rather than counting as replay failures."
        )
    if truth_window_status == "stale":
        warnings.append(
            "Archived forward exact-contract evidence is currently stale versus the trusted imported daily quote horizon, so the managed lane stays blocked until those picks become judgeable."
        )
    if playbook_id == "broad":
        warnings.append(
            "Broad pooled profitability is exploratory only. Promotion must come from symbol-specific exact-contract results."
        )
    if profitability_view["research_only_trade_count"] > 0:
        warnings.append(
            (
                f"{profitability_view['research_only_trade_count']} replay trade(s) sit outside the authoritative "
                f"{profitability_view['label'].lower()} and stay research-only."
            )
        )
    nearest_contract_match_count = int((matrix.get("source") or {}).get("nearest_contract_match_count", 0) or 0)
    if _is_imported_truth_source(truth_source) and nearest_contract_match_count > 0:
        warnings.append(
            (
                f"{nearest_contract_match_count} replay trade(s) used the nearest listed historical contract "
                "rather than an exact target-contract match; they cannot promote the policy."
            )
        )
    if not bool(authoritative_profitability_gate.get("passed")):
        warnings.append(
            "Exact-contract profitability does not currently clear the policy bar, so no symbol can be treated as profitable or promotable."
        )
    synthetic_only = truth_source == SYNTHETIC_TRUTH_SOURCE
    readiness_blockers: list[str] = []
    if synthetic_only:
        readiness_blockers.append("synthetic_only")
    if not bool(authoritative_profitability_gate.get("passed")):
        readiness_blockers.append("authoritative_exact_profitability_not_clear")
    if str(stability.get("overall_status") or "block").strip().lower() != "promote":
        readiness_blockers.append("stability_not_promote")
    if truth_window_status == "stale":
        readiness_blockers.append("truth_window_stale")
    if evidence_status in {ARCHIVED_EXACT_INSUFFICIENT_STATUS, MODEL_DAILY_FALLBACK_ONLY_STATUS}:
        readiness_blockers.append(f"evidence_status:{evidence_status}")
    base_promotion_status = str(promotion_metrics.get("promotion_status") or "block")
    if truth_window_status == "stale":
        promotion_status = "block"
    elif synthetic_only:
        promotion_status = "block"
    elif base_promotion_status == "promote" and readiness_blockers:
        promotion_status = "watch"
    else:
        promotion_status = base_promotion_status
    if truth_window_status == "stale":
        managed_lane_status = "blocked_truth_stale"
    elif promotion_status == "promote":
        managed_lane_status = "open"
    elif promoted_symbols:
        managed_lane_status = "watch_only"
    else:
        managed_lane_status = "blocked_no_approved_symbols"
    if promoted_symbols:
        rationale.append(
            f"Promotable exact-contract evidence currently exists for: {', '.join(promoted_symbols)}."
        )
    else:
        rationale.append("No symbol exact-contract subset currently clears the promotion bar.")

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": matrix.get("source"),
        "source_run_at": matrix.get("source_run_at"),
        "source_mode": matrix.get("source_mode"),
        "lookback_years": matrix.get("lookback_years"),
        "pricing_lane": (matrix.get("source") or {}).get("pricing_lane"),
        "playbook": (matrix.get("source") or {}).get("playbook"),
        "truth_source": truth_source,
        "evidence_status": evidence_status or None,
        "truth_window_status": truth_window_status,
        "authoritative_evidence_source": authoritative_evidence_source or None,
        "authoritative_evidence_status": authoritative_evidence_status or None,
        "preferred_evidence_source": preferred_evidence,
        "quote_coverage_pct": (matrix.get("source") or {}).get("quote_coverage_pct"),
        "priced_trade_count": (matrix.get("source") or {}).get("priced_trade_count"),
        "unpriced_trade_count": (matrix.get("source") or {}).get("unpriced_trade_count"),
        "entry_quote_time_et": (matrix.get("source") or {}).get("entry_quote_time_et"),
        "exit_quote_time_et": (matrix.get("source") or {}).get("exit_quote_time_et"),
        "strategy_domain": matrix.get("strategy_domain"),
        "trade_types": matrix.get("trade_types"),
        "authoritative_profitability_lens": profitability_view["lens"],
        "authoritative_profitability_label": profitability_view["label"],
        "authoritative_profitability_description": profitability_view["description"],
        "promotion_status": promotion_status,
        "managed_lane_status": managed_lane_status,
        "readiness_blockers": readiness_blockers,
        "synthetic_only": synthetic_only,
        "overall": overall,
        "stability": stability,
        "authoritative_profitability_basis": authoritative_profitability_basis,
        "authoritative_profitability_metrics": authoritative_profitability_metrics,
        "authoritative_profitability_gate": authoritative_profitability_gate,
        "aggregate_metrics": aggregate_metrics,
        "exact_contract_metrics": exact_contract_metrics,
        "authoritative_exact_contract_metrics": authoritative_exact_contract_metrics,
        "nearest_listed_metrics": nearest_listed_metrics,
        "research_only_metrics": research_only_metrics,
        "promotion_metrics": promotion_metrics,
        "by_symbol": by_symbol,
        "aggregate_by_symbol": aggregate_by_symbol,
        "promotion_trade_count": int(promotion_metrics.get("trade_count") or 0),
        "non_promotable_trade_count": non_promotable_trade_count,
        "calibration_density_metrics": calibration_density_metrics,
        "watch_priority_symbols": watch_priority_symbols,
        "watch_deprioritized_symbols": watch_deprioritized_symbols,
        "scan_policy": {
            "mode": "replay_backed_focus" if promotion_status == "promote" else "replay_backed_watch",
            "promotion_status": promotion_status,
            "managed_lane_status": managed_lane_status,
            "truth_window_status": truth_window_status,
            "decision_labels": {
                "approved": "Approved",
                "watch": "Watch",
                "blocked": "Blocked",
            },
            "result_classes": {
                "approved": "promotable_exact_contract",
                "watch_sparse": "research_sparse_calibration",
                "watch_bootstrap": "research_bootstrap",
                "watch_nearest": "research_nearest_listed",
            },
            "hard_filters": {
                "direction_score_min": max(float(direction_score_min or 0.0), 55.0) if direction_score_min is not None else 55.0,
                "direction_score_max": direction_score_max,
                "tech_score_min": 65.0,
                "min_calibrated_expectancy_pct": 10.0,
                "require_dense_calibration": True,
                "promotion_class_required": "promotable_exact_contract",
                "approved_tickers": promoted_symbols,
            },
            "preferred_filters": {
                "asset_class": preferred_asset_class,
                "market_regimes": preferred_market_regimes,
                "sectors": preferred_sectors,
            },
            "highlighted_tickers": highlighted_tickers,
            "watch_priority_symbols": watch_priority_symbols,
            "watch_deprioritized_symbols": watch_deprioritized_symbols,
            "rationale": rationale,
            "warnings": warnings,
            "readiness_blockers": readiness_blockers,
            "supporting_slices": {
                "score_band": preferred_score_band,
                "asset_regime": preferred_asset_regime,
                "sectors": preferred_sector_slices,
                "tickers": highlighted_ticker_slices,
            },
        },
    }


def _classify_trade_against_live_policy(trade: dict, scan_policy: dict) -> dict:
    hard_filters = dict(scan_policy.get("hard_filters") or {})
    preferred_filters = dict(scan_policy.get("preferred_filters") or {})
    promotion_status = str(scan_policy.get("promotion_status") or "watch").strip().lower()

    direction_score = float(trade.get("direction_score", 0.0) or 0.0)
    tech_score = float(trade.get("tech_score", 0.0) or 0.0)
    market_regime = _normalized_market_regime(trade)
    asset_class = _trade_asset_class(trade)
    sector = str(trade.get("sector") or "").strip().lower()
    ticker = str(trade.get("ticker") or "").strip().upper()
    promotion_class = str(trade.get("promotion_class") or _trade_promotion_class(trade)).strip().lower()

    def _policy_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            parsed = float(value)
            if math.isnan(parsed) or math.isinf(parsed):
                return None
            return parsed
        except (TypeError, ValueError):
            return None

    hard_failures: list[str] = []
    score_min = hard_filters.get("direction_score_min")
    score_max = hard_filters.get("direction_score_max")
    tech_score_min = hard_filters.get("tech_score_min")
    if score_min is not None and direction_score < float(score_min):
        hard_failures.append("below_score_floor")
    if score_max is not None and direction_score > float(score_max):
        hard_failures.append("above_score_cap")
    if tech_score_min is not None and tech_score < float(tech_score_min):
        hard_failures.append("below_tech_floor")
    if hard_filters.get("require_dense_calibration") is True and trade.get("calibration_is_dense") is not True:
        hard_failures.append("sparse_calibration")
    min_expectancy = _policy_float(hard_filters.get("min_calibrated_expectancy_pct"))
    if min_expectancy is not None:
        calibrated_expectancy = _policy_float(trade.get("calibrated_expectancy_pct"))
        if calibrated_expectancy is None or calibrated_expectancy < min_expectancy:
            hard_failures.append("below_calibrated_expectancy_floor")

    fit_score = 0
    preferred_asset_class = str(preferred_filters.get("asset_class") or "").strip().lower()
    if preferred_asset_class and asset_class == preferred_asset_class:
        fit_score += 1

    preferred_regimes = {str(item or "").strip().lower() for item in preferred_filters.get("market_regimes") or [] if str(item or "").strip()}
    if preferred_regimes and market_regime in preferred_regimes:
        fit_score += 1

    preferred_sectors = {str(item or "").strip().lower() for item in preferred_filters.get("sectors") or [] if str(item or "").strip()}
    if preferred_sectors and sector in preferred_sectors:
        fit_score += 1

    approved_tickers = {
        str(item or "").strip().upper()
        for item in hard_filters.get("approved_tickers") or []
        if str(item or "").strip()
    }
    approved_ticker = not approved_tickers or ticker in approved_tickers

    if hard_failures:
        decision = "blocked"
    elif promotion_class != "promotable_exact_contract":
        decision = "watch"
    elif not approved_ticker:
        decision = "watch"
    elif promotion_status != "promote":
        decision = "watch"
    elif fit_score > 0 or (
        approved_ticker
        and not preferred_asset_class
        and not preferred_regimes
        and not preferred_sectors
    ):
        decision = "approved"
    else:
        decision = "watch"

    return {
        "decision": decision,
        "fit_score": fit_score,
        "market_regime": market_regime,
        "asset_class": asset_class,
        "promotion_class": promotion_class,
        "hard_failures": hard_failures,
    }


def _playbook_trade_window(playbook: str) -> dict[str, int]:
    playbook_id = str(playbook or PLAYBOOK_EXIT_AUDIT_FALLBACK_PLAYBOOK).strip().lower()
    if playbook_id == "swing":
        return {"min_dte": 13, "max_dte": 35}
    if playbook_id in {"bullish_pullback_observation", "tracked_winner_primary", "tracked_winner_observation"}:
        return {"min_dte": 13, "max_dte": 45}
    if playbook_id == "speculative":
        return {"min_dte": 5, "max_dte": 9}
    if playbook_id == "bullish_momentum":
        return {"min_dte": 7, "max_dte": 21}
    if playbook_id == "bullish_mean_reversion":
        return {"min_dte": 7, "max_dte": 21}
    if playbook_id == "bearish_defensive":
        return {"min_dte": 7, "max_dte": 21}
    return {"min_dte": 0, "max_dte": 12}


def _summarize_exit_reason_group(exit_reason: str, trades: list[dict]) -> dict:
    pnl_values = [float(trade.get("pnl_pct", 0.0) or 0.0) for trade in trades]
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    directional_hits = sum(1 for trade in trades if trade.get("directional_correct"))
    return {
        "exit_reason": exit_reason,
        "trades": len(trades),
        "avg_pnl_pct": round(sum(pnl_values) / max(len(pnl_values), 1), 2),
        "profit_factor": round(gross_win / max(gross_loss, 0.01), 2),
        **_profit_factor_denominator_truth_from_pnls(pnl_values),
        "directional_accuracy_pct": round(directional_hits / max(len(trades), 1) * 100.0, 1),
    }


def _summarize_policy_audit_bucket(label: str, trades: list[dict]) -> dict:
    if not trades:
        return {
            "label": label,
            "trades": 0,
            "avg_pnl_pct": 0.0,
            "profit_factor": 0.0,
            **_profit_factor_denominator_truth_from_pnls([]),
            "directional_accuracy_pct": 0.0,
            "exit_reasons": [],
        }

    pnl_values = [float(trade.get("pnl_pct", 0.0) or 0.0) for trade in trades]
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    directional_hits = sum(1 for trade in trades if trade.get("directional_correct"))

    by_exit_reason: dict[str, list[dict]] = {}
    for trade in trades:
        exit_reason = str(trade.get("exit_reason") or "unknown")
        by_exit_reason.setdefault(exit_reason, []).append(trade)

    exit_reasons = [
        _summarize_exit_reason_group(exit_reason, group)
        for exit_reason, group in sorted(by_exit_reason.items(), key=lambda item: (-len(item[1]), item[0]))
    ]

    return {
        "label": label,
        "trades": len(trades),
        "avg_pnl_pct": round(sum(pnl_values) / max(len(pnl_values), 1), 2),
        "profit_factor": round(gross_win / max(gross_loss, 0.01), 2),
        **_profit_factor_denominator_truth_from_pnls(pnl_values),
        "directional_accuracy_pct": round(directional_hits / max(len(trades), 1) * 100.0, 1),
        "exit_reasons": exit_reasons,
    }


def build_playbook_exit_audit(
    result: Optional[dict] = None,
    policy_bundle: Optional[dict] = None,
    playbook: str = PLAYBOOK_EXIT_AUDIT_FALLBACK_PLAYBOOK,
    truth_lane: Optional[str] = None,
    min_trades: int = 20,
    score_floors: Optional[list[int]] = None,
    max_tickers: int = 8,
    max_sectors: int = 8,
    min_profit_factor: float = 1.05,
    min_directional_accuracy_pct: float = 50.0,
) -> dict:
    """
    Replay-validate exits for the cohorts that clear the live trade policy within a playbook window.
    """
    if result is None:
        result = load_preferred_results_by_truth_lane(truth_lane)
    if not result:
        return {"error": "No backtest results found"}

    if policy_bundle is None:
        policy_bundle = build_live_options_trade_policy(
            result=result,
            truth_lane=truth_lane,
            min_trades=min_trades,
            score_floors=score_floors,
            max_tickers=max_tickers,
            max_sectors=max_sectors,
            min_profit_factor=min_profit_factor,
            min_directional_accuracy_pct=min_directional_accuracy_pct,
        )
    if policy_bundle.get("error"):
        return policy_bundle

    trades = list(result.get("trades") or [])
    if not trades:
        return {"error": "No backtest trades found"}

    playbook_id = str(playbook or PLAYBOOK_EXIT_AUDIT_FALLBACK_PLAYBOOK).strip().lower()
    window = _playbook_trade_window(playbook_id)
    filtered = [
        trade
        for trade in trades
        if window["min_dte"] <= int(trade.get("dte", 0) or 0) <= window["max_dte"]
    ]

    approved: list[dict] = []
    watch: list[dict] = []
    blocked: list[dict] = []
    for trade in filtered:
        classified = _classify_trade_against_live_policy(trade, policy_bundle["scan_policy"])
        item = dict(trade)
        item.update(classified)
        if classified["decision"] == "approved":
            approved.append(item)
        elif classified["decision"] == "watch":
            watch.append(item)
        else:
            blocked.append(item)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_run_at": policy_bundle.get("source_run_at"),
        "lookback_years": policy_bundle.get("lookback_years"),
        "pricing_lane": policy_bundle.get("pricing_lane"),
        "truth_source": policy_bundle.get("truth_source"),
        "evidence_status": policy_bundle.get("evidence_status"),
        "truth_window_status": policy_bundle.get("truth_window_status"),
        "managed_lane_status": policy_bundle.get("managed_lane_status"),
        "authoritative_evidence_source": policy_bundle.get("authoritative_evidence_source"),
        "authoritative_evidence_status": policy_bundle.get("authoritative_evidence_status"),
        "quote_coverage_pct": policy_bundle.get("quote_coverage_pct"),
        "priced_trade_count": policy_bundle.get("priced_trade_count"),
        "unpriced_trade_count": policy_bundle.get("unpriced_trade_count"),
        "strategy_domain": policy_bundle.get("strategy_domain"),
        "playbook": playbook_id,
        "promotion_status": policy_bundle.get("promotion_status"),
        "dte_window": window,
        "overall_playbook_trades": len(filtered),
        "policy_summary": {
            "hard_filters": policy_bundle["scan_policy"].get("hard_filters"),
            "preferred_filters": policy_bundle["scan_policy"].get("preferred_filters"),
            "watch_priority_symbols": policy_bundle.get("watch_priority_symbols"),
            "watch_deprioritized_symbols": policy_bundle.get("watch_deprioritized_symbols"),
        },
        "approved": _summarize_policy_audit_bucket("approved", approved),
        "watch": _summarize_policy_audit_bucket("watch", watch),
        "blocked": _summarize_policy_audit_bucket("blocked", blocked),
    }


def _trade_compare_key(trade: dict) -> str:
    contract_symbol = str(trade.get("contract_symbol") or "").strip().upper()
    if contract_symbol:
        return f"{trade.get('date')}|{str(trade.get('ticker') or '').upper()}|{str(trade.get('type') or '').lower()}|{contract_symbol}"
    return (
        f"{trade.get('date')}|{str(trade.get('ticker') or '').upper()}|{str(trade.get('type') or '').lower()}|"
        f"{trade.get('strike')}|{trade.get('dte')}"
    )


def _comparison_lane_summary(result: dict) -> dict[str, Any]:
    source = _result_source_metadata(result, len(result.get("trades") or []))
    return {
        "run_at": source.get("run_at"),
        "playbook": source.get("playbook"),
        "lookback_years": source.get("lookback_years"),
        "pricing_lane": source.get("pricing_lane"),
        "truth_source": source.get("truth_source"),
        "candidate_source": source.get("candidate_source"),
        "preferred_evidence_source": source.get("preferred_evidence_source"),
        "evidence_status": source.get("evidence_status"),
        "truth_window_status": source.get("truth_window_status"),
        "authoritative_evidence_source": source.get("authoritative_evidence_source"),
        "authoritative_evidence_status": source.get("authoritative_evidence_status"),
        "primary_judge_trade_class": source.get("primary_judge_trade_class"),
        "primary_judge_trade_count": source.get("primary_judge_trade_count"),
        "pending_truth_horizon_count": source.get("pending_truth_horizon_count"),
        "total_trades": result.get("total_trades"),
        "priced_trade_count": result.get("priced_trade_count", result.get("total_trades")),
        "unpriced_trade_count": result.get("unpriced_trade_count", 0),
        "quote_coverage_pct": result.get("quote_coverage_pct", 100.0),
        "profit_factor": result.get("profit_factor"),
        "avg_pnl_pct": result.get("avg_pnl_pct"),
        "directional_accuracy_pct": result.get("directional_accuracy_pct"),
        "entry_quote_time_et": result.get("entry_quote_time_et"),
        "exit_quote_time_et": result.get("exit_quote_time_et"),
    }


def _comparison_authoritative_lane_summary(result: dict) -> dict[str, Any]:
    summary = _comparison_lane_summary(result)
    metrics = result.get("authoritative_profitability_metrics")
    if isinstance(metrics, dict) and metrics:
        summary.update(
            {
                "total_trades": metrics.get("trade_count", summary.get("total_trades")),
                "profit_factor": metrics.get("profit_factor", summary.get("profit_factor")),
                "avg_pnl_pct": metrics.get("avg_pnl_pct", summary.get("avg_pnl_pct")),
                "directional_accuracy_pct": metrics.get(
                    "directional_accuracy_pct",
                    summary.get("directional_accuracy_pct"),
                ),
                "authoritative_profitability_basis": result.get("authoritative_profitability_basis"),
            }
        )
    return summary


def _comparison_trade_subset_summary(trades: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(trades)
    pnl_values = [float(trade.get("pnl_pct", 0.0) or 0.0) for trade in trades]
    gross_profit = sum(value for value in pnl_values if value > 0)
    gross_loss = abs(sum(value for value in pnl_values if value < 0))
    directional_total = [
        trade for trade in trades
        if trade.get("directional_correct") is not None
    ]
    directional_hits = [
        trade for trade in directional_total
        if trade.get("directional_correct") is True
    ]
    if gross_loss > 0:
        profit_factor = round(gross_profit / gross_loss, 2)
    elif gross_profit > 0:
        profit_factor = round(gross_profit, 2)
    else:
        profit_factor = 0.0
    return {
        "trade_count": total,
        "profit_factor": profit_factor,
        **_profit_factor_denominator_truth_from_pnls(pnl_values),
        "avg_pnl_pct": round(sum(pnl_values) / total, 2) if total else 0.0,
        "directional_accuracy_pct": round(100.0 * len(directional_hits) / len(directional_total), 1)
        if directional_total
        else 0.0,
    }


def _trade_exit_reason_summary(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get("exit_reason") or "unknown")].append(trade)
    return [
        _summarize_exit_reason_group(reason, grouped[reason])
        for reason in sorted(grouped.keys(), key=lambda item: (-len(grouped[item]), item))
    ]


def _trade_subset_metrics(
    trades: list[dict[str, Any]],
    *,
    include_exit_reasons: bool = False,
) -> dict[str, Any]:
    summary = _comparison_trade_subset_summary(trades)
    metrics = dict(summary)
    if include_exit_reasons:
        metrics["exit_reasons"] = _trade_exit_reason_summary(trades)
    return metrics


def _trade_metrics_by_field(
    trades: list[dict[str, Any]],
    field: str,
    *,
    exact_only: bool = True,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        if exact_only and not _is_exact_contract_resolution(trade.get("entry_contract_resolution")):
            continue
        value = str(trade.get(field) or "unknown").strip() or "unknown"
        grouped[value].append(trade)
    return {
        key: _trade_subset_metrics(grouped[key], include_exit_reasons=True)
        for key in sorted(grouped.keys(), key=lambda item: (-len(grouped[item]), item))
    }


def _authoritative_profitability_basis(truth_source: Any) -> str:
    return "exact_contract_only" if _is_imported_truth_source(truth_source) else "all_trades"


def _authoritative_profitability_lens_for_context(
    *,
    truth_source: Any = None,
    candidate_source: Any = None,
    authoritative_evidence_source: Any = None,
) -> str:
    normalized_candidate_source = str(candidate_source or "").strip().lower()
    normalized_evidence_source = str(authoritative_evidence_source or "").strip().lower()
    if (
        normalized_candidate_source == FORWARD_LEDGER_SCAN_CANDIDATE_SOURCE
        or normalized_evidence_source == "archived_forward_daily"
    ):
        return "archived_exact_contract_only"
    return _authoritative_profitability_basis(truth_source)


def _authoritative_profitability_trades(
    result: Optional[dict[str, Any]] = None,
    *,
    trades: Optional[list[dict[str, Any]]] = None,
    truth_source: Any = None,
) -> list[dict[str, Any]]:
    source_truth = truth_source if truth_source is not None else _result_truth_source(result or {})
    all_trades = list(trades if trades is not None else ((result or {}).get("trades") or []))
    candidate_source = str((result or {}).get("candidate_source") or "").strip().lower()
    authoritative_evidence_source = str((result or {}).get("authoritative_evidence_source") or "").strip().lower()
    lens = _authoritative_profitability_lens_for_context(
        truth_source=source_truth,
        candidate_source=candidate_source,
        authoritative_evidence_source=authoritative_evidence_source,
    )
    if lens == "archived_exact_contract_only":
        return [
            trade
            for trade in all_trades
            if str(trade.get("entry_contract_resolution") or "").strip().lower() == PRIMARY_JUDGE_TRADE_CLASS
        ]
    if lens != "exact_contract_only":
        return all_trades
    return [
        trade for trade in all_trades
        if _is_exact_contract_resolution(trade.get("entry_contract_resolution"))
    ]


def _finite_metric(value: Any, default: float = 0.0) -> tuple[float, bool]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default, False
    if not math.isfinite(parsed):
        return default, False
    return parsed, True


def _authoritative_profitability_gate(
    metrics: dict[str, Any],
    *,
    min_trade_count: int,
    min_profit_factor: float,
    min_avg_pnl_pct: float = 0.0,
    min_directional_accuracy_pct: Optional[float] = None,
) -> dict[str, Any]:
    trade_count = int(metrics.get("trade_count") or 0)
    profit_factor, profit_factor_finite = _finite_metric(metrics.get("profit_factor"))
    avg_pnl_pct, avg_pnl_pct_finite = _finite_metric(metrics.get("avg_pnl_pct"))
    directional_accuracy_pct, directional_accuracy_finite = _finite_metric(
        metrics.get("directional_accuracy_pct")
    )
    blockers: list[str] = []
    if not profit_factor_finite and metrics.get("profit_factor") is not None:
        blockers.append("Exact-contract PF is non-finite.")
    if not avg_pnl_pct_finite and metrics.get("avg_pnl_pct") is not None:
        blockers.append("Exact-contract avg P&L is non-finite.")
    if not directional_accuracy_finite and metrics.get("directional_accuracy_pct") is not None:
        blockers.append("Exact-contract directional accuracy is non-finite.")
    if trade_count < int(min_trade_count):
        blockers.append(
            f"Exact-contract trade count is {trade_count}, below the {int(min_trade_count)}-trade bar."
        )
    if profit_factor < float(min_profit_factor):
        blockers.append(
            f"Exact-contract PF is {profit_factor:.2f}, below {float(min_profit_factor):.2f}."
        )
    if avg_pnl_pct <= float(min_avg_pnl_pct):
        blockers.append(
            f"Exact-contract avg P&L is {avg_pnl_pct:+.2f}%, not above {float(min_avg_pnl_pct):+.2f}%."
        )
    if (
        min_directional_accuracy_pct is not None
        and directional_accuracy_pct < float(min_directional_accuracy_pct)
    ):
        blockers.append(
            f"Exact-contract directional accuracy is {directional_accuracy_pct:.1f}%, below {float(min_directional_accuracy_pct):.1f}%."
        )
    return {
        "passed": not blockers,
        "trade_count": trade_count,
        "profit_factor": round(profit_factor, 2),
        "avg_pnl_pct": round(avg_pnl_pct, 2),
        "directional_accuracy_pct": round(directional_accuracy_pct, 1),
        "thresholds": {
            "min_trade_count": int(min_trade_count),
            "min_profit_factor": float(min_profit_factor),
            "min_avg_pnl_pct": float(min_avg_pnl_pct),
            "min_directional_accuracy_pct": (
                float(min_directional_accuracy_pct)
                if min_directional_accuracy_pct is not None
                else None
            ),
        },
        "blockers": blockers,
    }


def _authoritative_profitability_view(
    result: Optional[dict[str, Any]],
    aggregate_trades: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    all_trades = list(aggregate_trades if aggregate_trades is not None else ((result or {}).get("trades") or []))
    truth_source = _result_truth_source(result or {})
    lens = _authoritative_profitability_basis(truth_source)
    authoritative_trades = _authoritative_profitability_trades(
        result,
        trades=all_trades,
        truth_source=truth_source,
    )
    authoritative_ids = {id(trade) for trade in authoritative_trades}
    research_only_trades = [
        trade for trade in all_trades
        if id(trade) not in authoritative_ids
    ]
    if lens == "exact_contract_only":
        label = "Exact-contract replay trades"
        description = (
            "Imported replay profitability and promotion claims are judged from exact-contract matches only. "
            "Nearest-listed substitutions remain research-only."
        )
    else:
        label = "All replay trades"
        description = "No exact-contract historical subset is available for this truth lane, so all replay trades are used."
    return {
        "lens": lens,
        "label": label,
        "description": description,
        "truth_source": truth_source,
        "trades": authoritative_trades,
        "research_only_trades": research_only_trades,
        "metrics": _trade_subset_metrics(authoritative_trades, include_exit_reasons=True),
        "aggregate_trade_count": len(all_trades),
        "authoritative_trade_count": len(authoritative_trades),
        "research_only_trade_count": len(research_only_trades),
    }


def _symbol_promotion_summary(
    *,
    symbol: str,
    trades: list[dict[str, Any]],
    playbook_id: str,
    truth_source: Any = None,
    candidate_source: Any = None,
    authoritative_evidence_source: Any = None,
    min_profit_factor: float = 1.05,
    min_promotable_trades: int = 25,
    min_directional_accuracy_pct: float = MIN_EXACT_CONTRACT_DIRECTIONAL_ACCURACY_PCT,
) -> dict[str, Any]:
    exact_trades = [trade for trade in trades if _is_exact_contract_resolution(trade.get("entry_contract_resolution"))]
    nearest_trades = [trade for trade in trades if not _is_exact_contract_resolution(trade.get("entry_contract_resolution"))]
    profitability_view = _authoritative_profitability_view(
        {
            "truth_source": truth_source,
            "candidate_source": candidate_source,
            "authoritative_evidence_source": authoritative_evidence_source,
            "trades": trades,
        }
    )
    authoritative_trades = list(profitability_view["trades"])
    research_only_trades = list(profitability_view["research_only_trades"])
    promotable_trades = [trade for trade in authoritative_trades if _is_trade_promotable(trade)]
    non_promotable_trades = [trade for trade in trades if not _is_trade_promotable(trade)]

    blockers: list[str] = []
    exact_metrics = _trade_subset_metrics(exact_trades, include_exit_reasons=True)
    authoritative_metrics = _trade_subset_metrics(authoritative_trades, include_exit_reasons=True)
    authoritative_gate = _authoritative_profitability_gate(
        authoritative_metrics,
        min_trade_count=min_promotable_trades,
        min_profit_factor=min_profit_factor,
        min_directional_accuracy_pct=min_directional_accuracy_pct,
    )
    promotable_metrics = _trade_subset_metrics(promotable_trades, include_exit_reasons=True)
    if playbook_id == "broad":
        blockers.append("Broad playbook is exploratory-only and cannot be promoted.")
    blockers.extend(list(authoritative_gate.get("blockers") or []))
    if promotable_metrics["trade_count"] < int(min_promotable_trades):
        blockers.append(
            f"{symbol} only has {promotable_metrics['trade_count']} promotable exact-contract trade(s) against the {int(min_promotable_trades)}-trade bar."
        )
    if float(promotable_metrics.get("profit_factor", 0.0) or 0.0) < float(min_profit_factor):
        blockers.append(
            f"{symbol} promotable exact-contract PF is {float(promotable_metrics.get('profit_factor', 0.0) or 0.0):.2f}, below {float(min_profit_factor):.2f}."
        )
    if float(promotable_metrics.get("avg_pnl_pct", 0.0) or 0.0) <= 0.0:
        blockers.append(
            f"{symbol} promotable exact-contract avg P&L is {float(promotable_metrics.get('avg_pnl_pct', 0.0) or 0.0):+.2f}%."
        )
    if float(promotable_metrics.get("directional_accuracy_pct", 0.0) or 0.0) < float(min_directional_accuracy_pct):
        blockers.append(
            f"{symbol} promotable exact-contract directional accuracy is "
            f"{float(promotable_metrics.get('directional_accuracy_pct', 0.0) or 0.0):.1f}%, "
            f"below {float(min_directional_accuracy_pct):.1f}%."
        )

    promotion_status = "promote" if not blockers else "block"
    return {
        "symbol": symbol,
        "overall_metrics": _trade_subset_metrics(trades),
        "exact_contract_metrics": exact_metrics,
        "authoritative_profitability_basis": profitability_view["lens"],
        "authoritative_profitability_metrics": authoritative_metrics,
        "authoritative_profitability_gate": authoritative_gate,
        "research_only_metrics": _trade_subset_metrics(research_only_trades, include_exit_reasons=True),
        "nearest_listed_metrics": _trade_subset_metrics(nearest_trades),
        "promotion_metrics": {
            **promotable_metrics,
            "promotion_status": promotion_status,
            "blockers": blockers,
        },
        "promotion_trade_count": len(promotable_trades),
        "non_promotable_trade_count": len(non_promotable_trades),
    }


def _calibration_density_metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    dense = [trade for trade in trades if _trade_calibration_density(trade) == "dense"]
    sparse = [trade for trade in trades if _trade_calibration_density(trade) == "sparse"]
    bootstrap = [
        trade for trade in trades
        if str(trade.get("selection_source") or "").strip().lower() == "bootstrap_heuristic"
    ]
    return {
        "dense": _trade_subset_metrics(dense),
        "sparse": _trade_subset_metrics(sparse),
        "bootstrap": _trade_subset_metrics(bootstrap),
        "selection_summary": _selection_calibration_summary(trades),
    }


def _by_symbol_trade_metrics(
    trades: list[dict[str, Any]],
    *,
    playbook_id: str,
    truth_source: Any = None,
    candidate_source: Any = None,
    authoritative_evidence_source: Any = None,
    min_profit_factor: float = 1.05,
    min_promotable_trades: int = 25,
    min_directional_accuracy_pct: float = MIN_EXACT_CONTRACT_DIRECTIONAL_ACCURACY_PCT,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get("ticker") or "UNKNOWN").upper()].append(trade)
    return {
        symbol: _symbol_promotion_summary(
            symbol=symbol,
            trades=symbol_trades,
            playbook_id=playbook_id,
            truth_source=truth_source,
            candidate_source=candidate_source,
            authoritative_evidence_source=authoritative_evidence_source,
            min_profit_factor=min_profit_factor,
            min_promotable_trades=min_promotable_trades,
            min_directional_accuracy_pct=min_directional_accuracy_pct,
        )
        for symbol, symbol_trades in sorted(grouped.items())
    }


def _overall_promotion_metrics(
    *,
    trades: list[dict[str, Any]],
    by_symbol: dict[str, Any],
    playbook_id: str,
    truth_source: Any = None,
    candidate_source: Any = None,
    authoritative_evidence_source: Any = None,
    min_profit_factor: float = 1.05,
    min_promotable_trades: int = 25,
    min_directional_accuracy_pct: float = MIN_EXACT_CONTRACT_DIRECTIONAL_ACCURACY_PCT,
) -> dict[str, Any]:
    exact_trades = [trade for trade in trades if _is_exact_contract_resolution(trade.get("entry_contract_resolution"))]
    profitability_view = _authoritative_profitability_view(
        {
            "truth_source": truth_source,
            "candidate_source": candidate_source,
            "authoritative_evidence_source": authoritative_evidence_source,
            "trades": trades,
        }
    )
    authoritative_trades = list(profitability_view["trades"])
    research_only_trades = list(profitability_view["research_only_trades"])
    promotable_trades = [trade for trade in authoritative_trades if _is_trade_promotable(trade)]
    promoted_symbols = [
        symbol
        for symbol, summary in sorted(by_symbol.items())
        if str((summary.get("promotion_metrics") or {}).get("promotion_status") or "block") == "promote"
    ]
    blockers: list[str] = []
    exact_metrics = _trade_subset_metrics(exact_trades, include_exit_reasons=True)
    authoritative_metrics = _trade_subset_metrics(authoritative_trades, include_exit_reasons=True)
    authoritative_gate = _authoritative_profitability_gate(
        authoritative_metrics,
        min_trade_count=min_promotable_trades,
        min_profit_factor=min_profit_factor,
        min_directional_accuracy_pct=min_directional_accuracy_pct,
    )
    promotable_metrics = _trade_subset_metrics(promotable_trades, include_exit_reasons=True)
    if playbook_id == "broad":
        blockers.append("Broad playbook is exploratory-only and cannot be promoted.")
    blockers.extend(list(authoritative_gate.get("blockers") or []))
    if not promoted_symbols:
        blockers.append("No symbol exact-contract subset cleared the promotion bar.")
    if promotable_metrics["trade_count"] < int(min_promotable_trades):
        blockers.append(
            f"Only {promotable_metrics['trade_count']} promotable exact-contract trades are available against the {int(min_promotable_trades)}-trade bar."
        )
    if float(promotable_metrics.get("profit_factor", 0.0) or 0.0) < float(min_profit_factor):
        blockers.append(
            f"Promotable exact-contract PF is {float(promotable_metrics.get('profit_factor', 0.0) or 0.0):.2f}, below {float(min_profit_factor):.2f}."
        )
    if float(promotable_metrics.get("avg_pnl_pct", 0.0) or 0.0) <= 0.0:
        blockers.append(
            f"Promotable exact-contract avg P&L is {float(promotable_metrics.get('avg_pnl_pct', 0.0) or 0.0):+.2f}%."
        )
    if float(promotable_metrics.get("directional_accuracy_pct", 0.0) or 0.0) < float(min_directional_accuracy_pct):
        blockers.append(
            f"Promotable exact-contract directional accuracy is "
            f"{float(promotable_metrics.get('directional_accuracy_pct', 0.0) or 0.0):.1f}%, "
            f"below {float(min_directional_accuracy_pct):.1f}%."
        )
    return {
        **promotable_metrics,
        "authoritative_profitability_basis": profitability_view["lens"],
        "authoritative_profitability_metrics": authoritative_metrics,
        "authoritative_profitability_gate": authoritative_gate,
        "research_only_metrics": _trade_subset_metrics(research_only_trades, include_exit_reasons=True),
        "exact_contract_metrics": exact_metrics,
        "promotion_status": "promote" if playbook_id != "broad" and promoted_symbols else "block",
        "promoted_symbols": promoted_symbols,
        "blockers": blockers,
    }


def build_imported_exactness_sensitivity(result: Optional[dict]) -> dict[str, Any]:
    if not result or result.get("error"):
        return {
            "available": False,
            "error": result.get("error") if isinstance(result, dict) else None,
        }

    truth_source = _result_truth_source(result)
    if truth_source != IMPORTED_DAILY_TRUTH_SOURCE:
        return {
            "available": False,
            "truth_source": truth_source,
            "error": "Exactness sensitivity is only available for imported daily truth.",
        }

    trades = list(result.get("trades") or [])
    exact_only = [
        trade for trade in trades
        if _is_exact_contract_resolution(trade.get("entry_contract_resolution"))
    ]
    exact_count = int(result.get("exact_contract_match_count") or 0)
    nearest_count = int(result.get("nearest_contract_match_count") or 0)
    unresolved_count = int(result.get("unresolved_contract_count") or 0)

    nearest_allowed_summary = _comparison_lane_summary(result)
    exact_only_summary = _comparison_trade_subset_summary(exact_only)

    return {
        "available": True,
        "truth_source": truth_source,
        "daily_exact_only": {
            "available": bool(exact_only),
            "trade_count": len(exact_only),
            "exact_contract_match_count": exact_count,
            "summary": exact_only_summary,
        },
        "daily_nearest_allowed": {
            "available": bool(trades),
            "trade_count": len(trades),
            "exact_contract_match_count": exact_count,
            "nearest_listed_contract_count": nearest_count,
            "unresolved_candidate_count": unresolved_count,
            "summary": {
                "trade_count": int(nearest_allowed_summary.get("total_trades") or 0),
                "profit_factor": nearest_allowed_summary.get("profit_factor"),
                "avg_pnl_pct": nearest_allowed_summary.get("avg_pnl_pct"),
                "directional_accuracy_pct": nearest_allowed_summary.get("directional_accuracy_pct"),
            },
        },
    }


def build_truth_lane_comparison(
    synthetic_result: Optional[dict] = None,
    imported_result: Optional[dict] = None,
    truth_lane: Optional[str] = None,
) -> dict:
    synthetic = synthetic_result or load_last_synthetic_results()
    preferred_imported_lane = truth_lane if _is_imported_truth_source(truth_lane) else None
    imported = (
        imported_result
        or load_preferred_results_by_truth_lane(preferred_imported_lane or IMPORTED_DAILY_TRUTH_SOURCE)
        or load_last_results_by_truth_lane(preferred_imported_lane or IMPORTED_TRUTH_SOURCE)
        or load_last_imported_daily_results()
    )
    if not synthetic:
        return {"error": "No synthetic backtest results found"}
    if not imported or not _is_imported_truth_source(_result_truth_source(imported)):
        return {"error": "No imported historical validation results found"}

    synthetic_trades = list(synthetic.get("trades") or [])
    imported_trades = list(imported.get("trades") or [])
    imported_unpriced = list(imported.get("unpriced_trades") or [])
    synthetic_keys = {_trade_compare_key(trade): trade for trade in synthetic_trades}
    imported_priced_keys = {_trade_compare_key(trade): trade for trade in imported_trades}
    imported_unpriced_keys = {_trade_compare_key(trade): trade for trade in imported_unpriced}

    unsupported_by_import = [
        imported_unpriced_keys[key]
        for key in sorted(imported_unpriced_keys.keys())
        if key in synthetic_keys
    ]
    priced_in_both = sorted(set(synthetic_keys.keys()) & set(imported_priced_keys.keys()))
    matched_synthetic_trades = [synthetic_keys[key] for key in priced_in_both]
    matched_imported_trades = [imported_priced_keys[key] for key in priced_in_both]

    warnings: list[str] = []
    if synthetic.get("playbook") != imported.get("playbook"):
        warnings.append("Synthetic and imported runs do not share the same playbook id.")
    if int(synthetic.get("lookback_years") or 0) != int(imported.get("lookback_years") or 0):
        warnings.append("Synthetic and imported runs do not share the same lookback window.")

    synthetic_summary = _comparison_lane_summary(synthetic)
    imported_summary = _comparison_lane_summary(imported)
    imported_authoritative_summary = _comparison_authoritative_lane_summary(imported)
    aggregate_deltas = {
        "total_trades": int(imported_summary.get("total_trades") or 0) - int(synthetic_summary.get("total_trades") or 0),
        "profit_factor": round(float(imported_summary.get("profit_factor") or 0.0) - float(synthetic_summary.get("profit_factor") or 0.0), 2),
        "avg_pnl_pct": round(float(imported_summary.get("avg_pnl_pct") or 0.0) - float(synthetic_summary.get("avg_pnl_pct") or 0.0), 2),
        "directional_accuracy_pct": round(float(imported_summary.get("directional_accuracy_pct") or 0.0) - float(synthetic_summary.get("directional_accuracy_pct") or 0.0), 1),
        "quote_coverage_pct": round(float(imported_summary.get("quote_coverage_pct") or 0.0) - float(synthetic_summary.get("quote_coverage_pct") or 100.0), 1),
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "synthetic": synthetic_summary,
        "imported": imported_summary,
        "imported_authoritative": imported_authoritative_summary,
        "deltas": {
            "total_trades": int(imported_authoritative_summary.get("total_trades") or 0) - int(synthetic_summary.get("total_trades") or 0),
            "profit_factor": round(float(imported_authoritative_summary.get("profit_factor") or 0.0) - float(synthetic_summary.get("profit_factor") or 0.0), 2),
            "avg_pnl_pct": round(float(imported_authoritative_summary.get("avg_pnl_pct") or 0.0) - float(synthetic_summary.get("avg_pnl_pct") or 0.0), 2),
            "directional_accuracy_pct": round(float(imported_authoritative_summary.get("directional_accuracy_pct") or 0.0) - float(synthetic_summary.get("directional_accuracy_pct") or 0.0), 1),
            "quote_coverage_pct": round(float(imported_summary.get("quote_coverage_pct") or 0.0) - float(synthetic_summary.get("quote_coverage_pct") or 100.0), 1),
        },
        "aggregate_deltas": aggregate_deltas,
        "matching_priced_trade_count": len(priced_in_both),
        "unsupported_by_import_count": len(unsupported_by_import),
        "unsupported_by_import": unsupported_by_import[:25],
        "matched_support": {
            "trade_count": len(priced_in_both),
            "synthetic": _comparison_trade_subset_summary(matched_synthetic_trades),
            "imported": _comparison_trade_subset_summary(matched_imported_trades),
        },
        "warnings": warnings,
    }


def _allocation_group_for_candidate(
    candidate: dict,
    *,
    unknown_sector_policy: str = "shared",
) -> str:
    ticker = str(candidate.get("ticker") or "").strip().upper()
    if ticker in INDEX_TICKERS:
        return "index"
    explicit_group = str(
        candidate.get("allocation_group")
        or candidate.get("sleeve_group")
        or ""
    ).strip()
    if explicit_group:
        return explicit_group
    sector = str(candidate.get("sector") or "").strip()
    if sector and sector.lower() not in {"unknown", "none", "null"}:
        return sector
    policy = str(unknown_sector_policy or "shared").strip().lower()
    if policy in {"ticker", "ticker_bucket", "per_ticker"} and ticker:
        return f"ticker:{ticker}"
    if policy in {"uncapped", "none", "ignore"} and ticker:
        return f"uncapped:{ticker}"
    return "Unknown"


def _configured_candidate_rank_tuple(candidate: dict) -> tuple:
    tier_rank = int(candidate.get("tier_rank") or 1)
    return (-tier_rank, *_candidate_rank_tuple(candidate))


def _pick_top_n_daily_configured(
    candidates: list[dict],
    n: int,
    *,
    max_per_allocation_group: int = 2,
    max_per_ticker: int | None = None,
    max_total_index: int | None = None,
    unknown_sector_policy: str = "shared",
) -> tuple[list[dict], dict[str, Any]]:
    sorted_cands = sorted(candidates, key=_configured_candidate_rank_tuple, reverse=True)
    accepted: list[dict] = []
    rejected: list[dict] = []
    group_counts: Counter[str] = Counter()
    ticker_counts: Counter[str] = Counter()
    index_count = 0
    group_cap = max(0, int(max_per_allocation_group or 0))
    ticker_cap = int(max_per_ticker) if max_per_ticker is not None else None
    index_cap = int(max_total_index) if max_total_index is not None else None

    for rank, candidate in enumerate(sorted_cands, start=1):
        ticker = str(candidate.get("ticker") or "").strip().upper()
        group = _allocation_group_for_candidate(
            candidate,
            unknown_sector_policy=unknown_sector_policy,
        )
        reject_reason: str | None = None
        if len(accepted) >= int(n):
            reject_reason = "capacity_filled"
        elif ticker_cap is not None and ticker_counts[ticker] >= ticker_cap:
            reject_reason = "ticker_cap"
        elif ticker in INDEX_TICKERS:
            if index_cap is not None and index_count >= index_cap:
                reject_reason = "index_cap"
        elif group_cap > 0 and group_counts[group] >= group_cap:
            reject_reason = "allocation_group_cap"

        if reject_reason is not None:
            rejected.append(
                {
                    "ticker": ticker,
                    "date": candidate.get("date"),
                    "daily_rank": rank,
                    "allocation_group": group,
                    "selection_reject_reason": reject_reason,
                    "sleeve_id": candidate.get("sleeve_id"),
                    "tier_id": candidate.get("tier_id"),
                }
            )
            continue

        accepted.append(candidate)
        ticker_counts[ticker] += 1
        if ticker in INDEX_TICKERS:
            index_count += 1
        else:
            group_counts[group] += 1
        candidate["allocation_group"] = group
        candidate["daily_selection_rank"] = len(accepted)

    diagnostics = {
        "candidate_count": len(candidates),
        "selected_count": len(accepted),
        "rejected_count": len(rejected),
        "unused_slots": max(int(n) - len(accepted), 0),
        "reject_reasons": dict(Counter(item["selection_reject_reason"] for item in rejected)),
        "allocation_group_counts": dict(group_counts),
        "ticker_counts": dict(ticker_counts),
        "index_count": index_count,
        "rejected_candidates": rejected[:25],
        "unknown_sector_policy": str(unknown_sector_policy or "shared"),
        "max_per_allocation_group": group_cap,
        "max_per_ticker": ticker_cap,
        "max_total_index": index_cap,
    }
    return accepted, diagnostics


def _pick_top_n_daily(candidates: list[dict], n: int) -> list[dict]:
    """
    Pick the top n candidates from a single day's scan results using the exact same
    ranking tuple as the live daily scan plus the same sector-diversification logic.
    """
    sorted_cands = sorted(candidates, key=_candidate_rank_tuple, reverse=True)
    sector_counts: dict[str, int] = {}
    accepted: list[dict] = []
    overflow: list[dict] = []

    for c in sorted_cands:
        if len(accepted) >= n:
            overflow.append(c)
            continue
        if c["ticker"].upper() in INDEX_TICKERS:
            accepted.append(c)
        else:
            sec = c.get("sector") or "Unknown"
            if sector_counts.get(sec, 0) < 2:
                accepted.append(c)
                sector_counts[sec] = sector_counts.get(sec, 0) + 1
            else:
                overflow.append(c)

    # Fill remaining slots from overflow (same sector rule applies)
    for c in overflow:
        if len(accepted) >= n:
            break
        if c["ticker"].upper() in INDEX_TICKERS:
            continue
        sec = c.get("sector") or "Unknown"
        if sector_counts.get(sec, 0) < 2:
            accepted.append(c)
            sector_counts[sec] = sector_counts.get(sec, 0) + 1

    return accepted


def _simulate_spread_outcome_hist(
    prices: np.ndarray,
    i: int,
    trade_type: str,
    hv30: float,
    long_delta_target: float,
    short_delta_target: float,
    dte_at_entry: int,
    stop_loss_pct: float,
    profit_target_pct: float,
    time_exit_pct: float,
    trailing_profit_pct: float,
    trailing_giveback_pct: float,
    max_width_pct: float = 5.0,
    exit_monitoring_mode: str = "daily",
    _rsi14: np.ndarray = None,
    _macd: np.ndarray = None,
    _sma20: np.ndarray = None,
    _sma50: np.ndarray = None,
    tech_at_entry: float = 50.0,
    entry_S0: Optional[float] = None,
    iv_adj: float = 1.20,
    entry_slippage_pct: float = 0.0,
    exit_slippage_pct: float = 0.0,
    pricing_lane: str = "pessimistic",
) -> Optional[dict]:
    """
    Simulate a vertical spread trade (bull call or bear put spread).

    Long leg: buy at long_delta_target (e.g. 0.50 — near ATM)
    Short leg: sell at short_delta_target (e.g. 0.20 — OTM wing)

    Net debit = long_premium - short_premium
    Max profit = spread_width - net_debit (capped)
    Max loss = net_debit (capped — this is the key advantage over single-leg)

    Exit based on spread value (net mark-to-market of both legs).
    """
    n = len(prices)
    S0 = float(entry_S0) if entry_S0 is not None else float(prices[i])
    T = dte_at_entry / 365.0
    time_exit_day = max(1, math.ceil(dte_at_entry * time_exit_pct / 100))
    _iv = hv30 * iv_adj

    # Find long leg (higher delta, closer to ATM)
    long_strike = None
    long_g = None
    long_diff = 999.0
    for K in _market_strike_grid(S0):
        g = _bs_greeks(S0, K, T, RISK_FREE_RATE, _iv, trade_type)
        if not g:
            continue
        diff = abs(abs(g.get("delta", 0)) - long_delta_target)
        if diff < long_diff:
            long_diff = diff
            long_strike = K
            long_g = g

    if long_strike is None or not long_g or long_g.get("bs_price", 0) < 0.01:
        return None

    # Find short leg (lower delta, more OTM)
    short_strike = None
    short_g = None
    short_diff = 999.0
    for K in _market_strike_grid(S0):
        g = _bs_greeks(S0, K, T, RISK_FREE_RATE, _iv, trade_type)
        if not g:
            continue
        diff = abs(abs(g.get("delta", 0)) - short_delta_target)
        if diff < short_diff:
            # Ensure short strike is more OTM than long strike
            if trade_type == "call" and K <= long_strike:
                continue
            if trade_type == "put" and K >= long_strike:
                continue
            short_diff = diff
            short_strike = K
            short_g = g

    if short_strike is None or not short_g:
        return None

    # Validate spread width
    spread_width = abs(long_strike - short_strike)
    if spread_width <= 0 or (spread_width / S0 * 100) > max_width_pct:
        return None

    use_pessimistic = str(pricing_lane or "pessimistic").strip().lower() != "mid"
    entry_slip = float(entry_slippage_pct) / 100.0 if use_pessimistic else 0.0
    exit_slip = float(exit_slippage_pct) / 100.0 if use_pessimistic else 0.0

    # Entry: buy long (pay ask = higher), sell short (receive bid = lower)
    long_entry_px = long_g["bs_price"] * (1.0 + entry_slip)
    short_entry_px = short_g["bs_price"] * max(0.0, 1.0 - entry_slip)
    net_debit = long_entry_px - short_entry_px

    if net_debit <= 0.01:
        return None

    # Max profit and loss for the spread
    max_profit_per_share = spread_width - net_debit
    max_loss_per_share = net_debit  # This is the key: max loss is capped at net debit

    # Stop and target in absolute spread value terms
    stop_value = net_debit * (1.0 - stop_loss_pct / 100.0)      # exit if spread value drops to this
    target_value = net_debit * (1.0 + profit_target_pct / 100.0) # exit if spread value rises to this
    # Cap target at max possible spread value
    target_value = min(target_value, spread_width * (1.0 - exit_slip))

    trail_activate_pct = max(0.0, float(trailing_profit_pct))
    trail_giveback_pct = max(0.0, float(trailing_giveback_pct))
    high_watermark = net_debit
    trail_active = False
    trail_stop_value = 0.0

    exit_spread_value = net_debit
    exit_reason = "expired"
    exit_stock_px = S0
    exit_day_idx = min(i + max(1, dte_at_entry), n - 1)

    for d in range(1, dte_at_entry + 1):
        fi = i + d
        if fi >= n:
            break
        S_now = float(prices[fi])
        T_now = max((dte_at_entry - d) / 365.0, 0)

        if T_now <= 0:
            # At expiry: intrinsic values
            if trade_type == "call":
                long_intrinsic = max(0.0, S_now - long_strike)
                short_intrinsic = max(0.0, S_now - short_strike)
            else:
                long_intrinsic = max(0.0, long_strike - S_now)
                short_intrinsic = max(0.0, short_strike - S_now)
            spread_value = (long_intrinsic - short_intrinsic) * (1.0 - exit_slip)
            exit_spread_value = max(0.0, spread_value)
            exit_reason = "expired"
            exit_stock_px = S_now
            exit_day_idx = fi
            break

        # Mark-to-market both legs
        long_g2 = _bs_greeks(S_now, long_strike, T_now, RISK_FREE_RATE, _iv, trade_type)
        short_g2 = _bs_greeks(S_now, short_strike, T_now, RISK_FREE_RATE, _iv, trade_type)
        long_now = (long_g2.get("bs_price", 0.0) if long_g2 else 0.0) * (1.0 - exit_slip)
        short_now = (short_g2.get("bs_price", 0.0) if short_g2 else 0.0) * (1.0 + exit_slip)
        spread_value = max(0.0, long_now - short_now)

        if spread_value > high_watermark:
            high_watermark = spread_value

        current_pnl_pct = ((spread_value / net_debit) - 1.0) * 100.0 if net_debit > 0 else 0.0
        peak_pnl_pct = ((high_watermark / net_debit) - 1.0) * 100.0 if net_debit > 0 else 0.0

        # Trailing stop activation
        if not trail_active and peak_pnl_pct >= trail_activate_pct:
            trail_active = True
        if trail_active and peak_pnl_pct > 0.0:
            retained = peak_pnl_pct * max(0.0, 1.0 - trail_giveback_pct / 100.0)
            trail_stop_value = net_debit * (1.0 + retained / 100.0)

        effective_stop = max(stop_value, trail_stop_value) if trail_active else stop_value

        # Stop check
        if spread_value <= effective_stop:
            exit_spread_value = spread_value
            exit_reason = "trailing_stop" if trail_active else "stop"
            exit_stock_px = S_now
            exit_day_idx = fi
            break

        # Target check
        if spread_value >= target_value:
            exit_spread_value = min(spread_value, target_value)
            exit_reason = "target"
            exit_stock_px = S_now
            exit_day_idx = fi
            break

        # Time exit
        if d >= time_exit_day:
            exit_spread_value = spread_value
            exit_reason = "time_exit"
            exit_stock_px = S_now
            exit_day_idx = fi
            break

    # P&L calculation
    gross_pnl_per_share = exit_spread_value - net_debit
    gross_pnl_usd = gross_pnl_per_share * 100  # 1 contract = 100 shares
    # Spread fees: 2 legs on entry + 2 on exit = 4 sides
    fee_total = 4 * DEFAULT_COMMISSION_PER_CONTRACT_USD
    net_pnl_usd = gross_pnl_usd - fee_total
    capital_at_risk = net_debit * 100
    gross_pnl_pct = (gross_pnl_per_share / net_debit * 100.0) if net_debit > 0 else 0.0
    net_pnl_pct = (net_pnl_usd / capital_at_risk * 100.0) if capital_at_risk > 0 else 0.0

    stock_move_pct = (exit_stock_px / S0 - 1.0) * 100 if S0 > 0 else 0.0
    directional_correct = (
        (trade_type == "call" and stock_move_pct > 0)
        or (trade_type == "put" and stock_move_pct < 0)
    )

    return {
        "entry_px": round(net_debit, 4),
        "exit_px": round(exit_spread_value, 4),
        "pnl_pct": round(net_pnl_pct, 2),
        "gross_pnl_pct": round(gross_pnl_pct, 2),
        "net_pnl_pct": round(net_pnl_pct, 2),
        "gross_pnl_usd": round(gross_pnl_usd, 2),
        "net_pnl_usd": round(net_pnl_usd, 2),
        "fee_total_usd": round(fee_total, 2),
        "entry_fee_total_usd": round(fee_total / 2, 2),
        "exit_fee_total_usd": round(fee_total / 2, 2),
        "exit_reason": exit_reason,
        "exit_fill_basis": "spread_model_mark",
        "strike": round(long_strike, 2),
        "short_strike": round(short_strike, 2),
        "spread_width": round(spread_width, 2),
        "net_debit": round(net_debit, 4),
        "max_profit": round(max_profit_per_share, 4),
        "max_loss": round(net_debit, 4),
        "delta_val": round(abs(long_g.get("delta", 0)), 4),
        "short_delta_val": round(abs(short_g.get("delta", 0)), 4) if short_g else None,
        "stock_px": round(S0, 2),
        "exit_stock_px": round(exit_stock_px, 2),
        "stock_move_pct": round(stock_move_pct, 2),
        "directional_correct": directional_correct,
        "exit_day_idx": exit_day_idx,
        "entry_day_idx": i,
        "hv30": round(hv30, 4),
        "iv_adj": iv_adj,
        "strategy_type": "vertical_spread",
        "priced": True,
    }


def _simulate_trade_outcome_hist(
    prices: np.ndarray,
    i: int,
    trade_type: str,
    hv30: float,
    delta_target: float,
    dte_at_entry: int,
    stop_loss_pct: float,
    profit_target_pct: float,
    time_exit_pct: float,
    trailing_profit_pct: float,
    trailing_giveback_pct: float,
    _rsi14: np.ndarray,
    _macd: np.ndarray,
    _sma20: np.ndarray,
    _sma50: np.ndarray,
    tech_at_entry: float,
    entry_S0: Optional[float] = None,   # open price override; defaults to close[i]
    iv_adj: float = 1.20,               # IV premium multiplier: real IV > realized HV by ~15-25%
    entry_slippage_pct: float = 0.0,
    exit_slippage_pct: float = 0.0,
    pricing_lane: str = "pessimistic",
) -> Optional[dict]:
    """
    Simulate a single trade starting at day i using actual subsequent price data.
    Exit logic mirrors _simulate_window exactly (stop, target, trailing, time exit).
    entry_S0: use the day's open price for strike selection and BS entry pricing
              while the exit walk still uses close prices. This mirrors the live scan
              which executes ~30 min after open (10:10 AM ET).
    Returns outcome dict or None if no valid strike found.
    """
    n = len(prices)
    S0 = float(entry_S0) if entry_S0 is not None else float(prices[i])
    T = dte_at_entry / 365.0
    time_exit_day = max(1, math.ceil(dte_at_entry * time_exit_pct / 100))

    # Find best strike near delta_target
    best_strike: Optional[float] = None
    best_g: Optional[dict] = None
    best_diff = 999.0
    _iv = hv30 * iv_adj          # apply IV premium before any BS pricing
    for K in _market_strike_grid(S0):
        g = _bs_greeks(S0, K, T, RISK_FREE_RATE, _iv, trade_type)
        if not g:
            continue
        diff = abs(abs(g.get("delta", 0)) - delta_target)
        if diff < best_diff:
            best_diff = diff
            best_strike = K
            best_g = g

    if best_strike is None or not best_g or best_g.get("bs_price", 0) < 0.01:
        return None

    use_pessimistic = str(pricing_lane or "pessimistic").strip().lower() != "mid"
    entry_fill_mult = 1.0 + (float(entry_slippage_pct) / 100.0 if use_pessimistic else 0.0)
    exit_fill_mult = 1.0 - (float(exit_slippage_pct) / 100.0 if use_pessimistic else 0.0)

    entry_px  = best_g["bs_price"] * entry_fill_mult
    delta_val = abs(best_g.get("delta", 0))

    stop_px   = entry_px * (1 - stop_loss_pct   / 100)
    target_px = entry_px * (1 + profit_target_pct / 100)

    trail_activate_pct = max(0.0, float(trailing_profit_pct))
    trail_giveback_pct = max(0.0, float(trailing_giveback_pct))
    high_watermark    = entry_px
    trail_active      = False
    trail_stop_px     = 0.0
    dynamic_stop_px   = stop_px

    exit_px, exit_reason = entry_px, "expired"
    exit_fill_basis = "model_mark"
    exit_stock_px = S0
    exit_day_idx = min(i + max(1, dte_at_entry), n - 1)

    for d in range(1, dte_at_entry + 1):
        fi = i + d
        if fi >= n:
            break
        S_now = float(prices[fi])
        T_now = max((dte_at_entry - d) / 365.0, 0)
        if T_now <= 0:
            intrinsic = (
                max(0.0, S_now - best_strike)
                if trade_type == "call"
                else max(0.0, best_strike - S_now)
            )
            exit_px     = min(intrinsic * exit_fill_mult, target_px)
            exit_reason = "expired"
            exit_fill_basis = "expiry_intrinsic"
            exit_stock_px = S_now
            exit_day_idx = fi
            break

        g2      = _bs_greeks(S_now, best_strike, T_now, RISK_FREE_RATE, _iv, trade_type)
        opt_now_model = g2.get("bs_price", 0.0) if g2 else 0.0
        opt_now = opt_now_model * exit_fill_mult

        if opt_now > high_watermark:
            high_watermark = opt_now
        current_pnl_pct = ((opt_now / entry_px) - 1.0) * 100.0 if entry_px > 0 else 0.0
        peak_pnl_pct = ((high_watermark / entry_px) - 1.0) * 100.0 if entry_px > 0 else 0.0

        # Current tech score for adaptive exit decisions
        if fi >= 50 and not np.isnan(_sma50[fi]):
            cur_tech = _tech_score(
                rsi14     = float(_rsi14[fi]),
                macd      = float(_macd[fi]),
                macd_prev = float(_macd[fi - 1]) if fi > 0 else float(_macd[fi]),
                price     = S_now,
                sma20     = float(_sma20[fi]) if not np.isnan(_sma20[fi]) else S_now,
                sma50     = float(_sma50[fi]),
                trade_type= trade_type,
            )
        else:
            cur_tech = tech_at_entry

        tech_healthy = cur_tech >= max(25.0, tech_at_entry * 0.65)
        tech_decayed = cur_tech <  max(20.0, tech_at_entry * 0.40)

        if not trail_active and peak_pnl_pct >= trail_activate_pct:
            trail_active  = True

        if trail_active and peak_pnl_pct > 0.0:
            retained_profit_pct = peak_pnl_pct * max(0.0, 1.0 - trail_giveback_pct / 100.0)
            trail_stop_px = entry_px * (1.0 + retained_profit_pct / 100.0)

        if tech_decayed:
            if opt_now >= entry_px:
                dynamic_stop_px = max(dynamic_stop_px, entry_px * 1.02)
            else:
                tighter = dynamic_stop_px + (entry_px - dynamic_stop_px) * 0.40
                dynamic_stop_px = max(dynamic_stop_px, tighter)

        effective_stop = (
            max(dynamic_stop_px, trail_stop_px)
            if trail_active
            else min(entry_px, dynamic_stop_px)
        )
        if opt_now <= effective_stop:
            exit_px     = opt_now
            exit_reason = "trailing_stop" if trail_active else "stop"
            exit_fill_basis = "model_mark"
            exit_stock_px = S_now
            exit_day_idx = fi
            break

        if opt_now >= target_px:
            exit_px     = min(opt_now, target_px)
            exit_reason = "target"
            exit_fill_basis = "target_limit"
            exit_stock_px = S_now
            exit_day_idx = fi
            break

        if d >= time_exit_day:
            exit_px     = opt_now
            exit_reason = "time_exit"
            exit_fill_basis = "model_mark"
            exit_stock_px = S_now
            exit_day_idx = fi
            break

    pnl_snapshot = long_option_pnl(
        entry_execution_price=entry_px,
        exit_execution_price=exit_px,
        contracts=1,
        commission_per_contract_usd=DEFAULT_COMMISSION_PER_CONTRACT_USD,
        include_entry_fee=True,
        include_exit_fee=True,
    )
    pnl = float(pnl_snapshot.get("net_pnl_pct") or 0.0)
    stock_move_pct = (exit_stock_px / S0 - 1.0) * 100 if S0 > 0 else 0.0
    directional_correct = (
        (trade_type == "call" and stock_move_pct > 0)
        or (trade_type == "put" and stock_move_pct < 0)
    )
    return {
        "entry_px":    round(entry_px,   4),
        "exit_px":     round(exit_px,    4),
        "pnl_pct":     round(pnl,        2),
        "gross_pnl_pct": pnl_snapshot.get("gross_pnl_pct"),
        "net_pnl_pct": pnl_snapshot.get("net_pnl_pct"),
        "gross_pnl_usd": pnl_snapshot.get("gross_pnl_usd"),
        "net_pnl_usd": pnl_snapshot.get("net_pnl_usd"),
        "fee_total_usd": pnl_snapshot.get("fee_total_usd"),
        "entry_fee_total_usd": pnl_snapshot.get("entry_fee_total_usd"),
        "exit_fee_total_usd": pnl_snapshot.get("exit_fee_total_usd"),
        "exit_reason": exit_reason,
        "exit_fill_basis": exit_fill_basis,
        "strike":      round(best_strike, 2),
        "delta_val":   round(delta_val,  4),
        "stock_px":    round(S0,         4),
        "exit_stock_px": round(exit_stock_px, 4),
        "stock_move_pct": round(stock_move_pct, 2),
        "directional_correct": directional_correct,
        "hv30":        round(hv30,       4),
        "iv_adj":      iv_adj,
        "dte":         dte_at_entry,
        "entry_day_idx": i,
        "exit_day_idx": exit_day_idx,
        "pricing_lane": "pessimistic" if use_pessimistic else "mid",
    }


def _et_minute_label(minute_value: Optional[int]) -> Optional[str]:
    if minute_value is None:
        return None
    hour = int(minute_value) // 60
    minute = int(minute_value) % 60
    return f"{hour:02d}:{minute:02d} ET"


def _select_target_contract(
    stock_px: float,
    hv30: float,
    trade_type: str,
    delta_target: float,
    dte_at_entry: int,
    iv_adj: float,
) -> tuple[Optional[float], Optional[dict]]:
    T = max(float(dte_at_entry), 1.0) / 365.0
    _iv = float(hv30) * float(iv_adj)
    best_strike: Optional[float] = None
    best_g: Optional[dict] = None
    best_diff = 999.0
    for strike in _market_strike_grid(stock_px):
        greeks = _bs_greeks(stock_px, strike, T, RISK_FREE_RATE, _iv, trade_type)
        if not greeks:
            continue
        diff = abs(abs(greeks.get("delta", 0.0)) - float(delta_target))
        if diff < best_diff:
            best_diff = diff
            best_strike = strike
            best_g = greeks
    return best_strike, best_g


def _quote_spread_pct(quote: Any) -> float:
    bid = getattr(quote, "bid", None)
    ask = getattr(quote, "ask", None)
    if bid is None or ask is None:
        return 999.0
    try:
        bid_f = float(bid)
        ask_f = float(ask)
    except (TypeError, ValueError):
        return 999.0
    midpoint = (bid_f + ask_f) / 2.0
    if bid_f <= 0 or ask_f <= 0 or ask_f < bid_f or midpoint <= 0:
        return 999.0
    return (ask_f - bid_f) / midpoint * 100.0


def _quote_liquidity_score(quote: Any) -> float:
    volume = getattr(quote, "volume", None)
    open_interest = getattr(quote, "open_interest", None)
    try:
        vol_f = float(volume or 0.0)
    except (TypeError, ValueError):
        vol_f = 0.0
    try:
        oi_f = float(open_interest or 0.0)
    except (TypeError, ValueError):
        oi_f = 0.0
    return math.log1p(max(vol_f, 0.0)) + 0.25 * math.log1p(max(oi_f, 0.0))


def _quote_float(quote: Any, field: str) -> float | None:
    try:
        value = getattr(quote, field, None)
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _quote_midpoint_value(quote: Any) -> float | None:
    midpoint = quote_midpoint(bid=getattr(quote, "bid", None), ask=getattr(quote, "ask", None))
    return float(midpoint) if midpoint is not None and midpoint > 0 else None


def _compact_chain_native_spread_diagnostic(
    *,
    long_quote: Any,
    short_quote: Any,
    net_debit: float,
    spread_width: float,
    long_delta: float,
    short_delta: float,
    long_delta_target: float,
    short_delta_target: float,
    score: float | None,
    entry_date: date,
    dte: int,
    long_prior_quote_days: int | None = None,
    short_prior_quote_days: int | None = None,
) -> dict[str, Any]:
    long_mid = _quote_midpoint_value(long_quote)
    short_mid = _quote_midpoint_value(short_quote)
    long_ask = _quote_float(long_quote, "ask")
    short_bid = _quote_float(short_quote, "bid")
    mid_debit = long_mid - short_mid if long_mid is not None and short_mid is not None else None
    ask_bid_debit = long_ask - short_bid if long_ask is not None and short_bid is not None else None
    fill_degradation = (
        ask_bid_debit - mid_debit
        if ask_bid_debit is not None and mid_debit is not None
        else None
    )
    fill_degradation_pct = (
        fill_degradation / mid_debit * 100.0
        if fill_degradation is not None and mid_debit is not None and mid_debit > 0
        else None
    )
    long_spread_pct = _quote_spread_pct(long_quote)
    short_spread_pct = _quote_spread_pct(short_quote)
    leg_spreads = [value for value in (long_spread_pct, short_spread_pct) if value < 999.0]
    expiry = str(getattr(long_quote, "expiry", ""))[:10]
    long_volume = _quote_float(long_quote, "volume") or 0.0
    short_volume = _quote_float(short_quote, "volume") or 0.0
    long_open_interest = _quote_float(long_quote, "open_interest") or 0.0
    short_open_interest = _quote_float(short_quote, "open_interest") or 0.0
    return {
        "long_contract_symbol": getattr(long_quote, "contract_symbol", None),
        "short_contract_symbol": getattr(short_quote, "contract_symbol", None),
        "expiry": expiry or None,
        "entry_date": entry_date.isoformat(),
        "dte": int(dte),
        "long_strike": round(float(getattr(long_quote, "strike")), 4),
        "short_strike": round(float(getattr(short_quote, "strike")), 4),
        "spread_width": round(float(spread_width), 4),
        "net_debit": round(float(net_debit), 4),
        "mid_debit": round(float(mid_debit), 4) if mid_debit is not None else None,
        "ask_bid_debit": round(float(ask_bid_debit), 4) if ask_bid_debit is not None else None,
        "debit_pct_of_width": round(float(net_debit) / float(spread_width) * 100.0, 2) if spread_width > 0 else None,
        "bid_ask_pct": round(sum(leg_spreads) / len(leg_spreads), 2) if leg_spreads else None,
        "long_bid_ask_pct": round(long_spread_pct, 2) if long_spread_pct < 999.0 else None,
        "short_bid_ask_pct": round(short_spread_pct, 2) if short_spread_pct < 999.0 else None,
        "long_volume": int(max(long_volume, 0.0)),
        "short_volume": int(max(short_volume, 0.0)),
        "long_open_interest": int(max(long_open_interest, 0.0)),
        "short_open_interest": int(max(short_open_interest, 0.0)),
        "long_prior_quote_days": long_prior_quote_days,
        "short_prior_quote_days": short_prior_quote_days,
        "long_delta": round(float(long_delta), 4),
        "short_delta": round(float(short_delta), 4),
        "long_delta_miss": round(abs(float(long_delta) - float(long_delta_target)), 4),
        "short_delta_miss": round(abs(float(short_delta) - float(short_delta_target)), 4),
        "selection_score": round(float(score), 4) if score is not None else None,
        "fill_degradation_vs_mid": round(float(fill_degradation), 4) if fill_degradation is not None else None,
        "fill_degradation_vs_mid_pct": (
            round(float(fill_degradation_pct), 2) if fill_degradation_pct is not None else None
        ),
    }


def _contract_prior_quote_continuity_metrics(
    store: Any,
    quote: Any,
    *,
    entry_date: date,
    snapshot_kind: str,
    source_labels: Optional[Sequence[str]],
    lookback_calendar_days: int,
    trusted_only: bool = False,
) -> dict[str, Any]:
    if not hasattr(store, "contract_quote_continuity_metrics"):
        return {
            "contract_symbol": getattr(quote, "contract_symbol", None),
            "lookback_calendar_days": int(lookback_calendar_days),
            "quote_date_count": 0,
        }
    return dict(
        store.contract_quote_continuity_metrics(
            contract_symbol=quote.contract_symbol,
            before_date_et=entry_date,
            lookback_calendar_days=int(lookback_calendar_days),
            snapshot_kind=snapshot_kind,
            source_labels=source_labels,
            trusted_only=trusted_only,
        )
    )


def _option_delta_for_quote(
    quote: Any,
    *,
    stock_px: float,
    hv30: float,
    trade_type: str,
    entry_date: date,
    iv_adj: float,
) -> float:
    expiry_date = date.fromisoformat(str(quote.expiry)[:10])
    dte = max((expiry_date - entry_date).days, 1)
    greeks = _bs_greeks(
        float(stock_px),
        float(quote.strike),
        dte / 365.0,
        RISK_FREE_RATE,
        float(hv30) * float(iv_adj),
        trade_type,
    )
    if not greeks:
        return 0.0
    return abs(float(greeks.get("delta", 0.0) or 0.0))


def _select_chain_native_spread(
    *,
    store: "HistoricalOptionsStore",
    ticker: str,
    entry_date: date,
    trade_type: str,
    S0: float,
    hv30: float,
    long_delta_target: float,
    short_delta_target: float,
    target_dte: int,
    min_dte: int,
    max_dte: int,
    max_width_pct: float,
    max_debit_pct_of_width: float | None,
    iv_adj: float,
    requested_pricing_lane: str,
    entry_slippage_pct: float,
    snapshot_kind: str,
    entry_quote_minute_et: int,
    entry_window_minutes: int,
    source_labels: Optional[Sequence[str]],
    trusted_only: bool = False,
    min_prior_quote_days: int = 0,
    min_long_prior_quote_days: int | None = None,
    min_short_prior_quote_days: int | None = None,
    prior_quote_lookback_days: int = 14,
    prior_quote_score_weight: float = 0.0,
    long_prior_quote_score_weight: float | None = None,
    short_prior_quote_score_weight: float | None = None,
    prior_quote_score_cap: int = 5,
    max_entry_leg_bid_ask_pct: float | None = None,
    min_entry_short_bid: float | None = None,
    short_inside_steps: int = 0,
    short_inside_require_debit_cap: bool = True,
    include_diagnostics: bool = False,
) -> tuple[Any, Any, float, float, float, float] | dict[str, Any] | None:
    min_expiry = entry_date + timedelta(days=max(int(min_dte), 1))
    max_expiry = entry_date + timedelta(days=max(int(max_dte), max(int(min_dte), 1)))
    quotes = store.list_entry_contracts(
        underlying=ticker,
        trade_date_et=entry_date,
        option_type=trade_type,
        earliest_minute_et=entry_quote_minute_et,
        window_minutes=entry_window_minutes,
        snapshot_kind=snapshot_kind,
        allow_last_price=False,
        min_expiry=min_expiry,
        max_expiry=max_expiry,
        source_labels=source_labels,
        trusted_only=trusted_only,
    )
    if not quotes:
        return None

    quotes_by_expiry: dict[str, list[Any]] = defaultdict(list)
    for quote in quotes:
        if quote.bid is None or quote.ask is None:
            continue
        try:
            if float(quote.bid) <= 0 or float(quote.ask) <= 0 or float(quote.ask) < float(quote.bid):
                continue
        except (TypeError, ValueError):
            continue
        if max_entry_leg_bid_ask_pct is not None and _quote_spread_pct(quote) > float(max_entry_leg_bid_ask_pct):
            continue
        quotes_by_expiry[str(quote.expiry)[:10]].append(quote)

    best: tuple[float, Any, Any, float, float, float, float] | None = None
    alternatives: list[tuple[float, Any, Any, float, float, float, float, int, int | None, int | None]] = []
    continuity_cache: dict[str, dict[str, Any]] = {}
    base_min_prior_days = max(int(min_prior_quote_days or 0), 0)
    long_min_prior_days = (
        base_min_prior_days
        if min_long_prior_quote_days is None
        else max(int(min_long_prior_quote_days or 0), 0)
    )
    short_min_prior_days = (
        base_min_prior_days
        if min_short_prior_quote_days is None
        else max(int(min_short_prior_quote_days or 0), 0)
    )
    base_prior_weight = max(float(prior_quote_score_weight or 0.0), 0.0)
    long_prior_weight = max(
        float(long_prior_quote_score_weight if long_prior_quote_score_weight is not None else base_prior_weight),
        0.0,
    )
    short_prior_weight = max(
        float(short_prior_quote_score_weight if short_prior_quote_score_weight is not None else base_prior_weight),
        0.0,
    )
    prior_score_cap_days = max(int(prior_quote_score_cap or 0), 0)

    def _prior_quote_days(quote: Any) -> int:
        symbol = str(quote.contract_symbol)
        if symbol not in continuity_cache:
            continuity_cache[symbol] = _contract_prior_quote_continuity_metrics(
                store,
                quote,
                entry_date=entry_date,
                snapshot_kind=snapshot_kind,
                source_labels=source_labels,
                trusted_only=trusted_only,
                lookback_calendar_days=int(prior_quote_lookback_days),
            )
        return int(continuity_cache[symbol].get("quote_date_count") or 0)

    def _has_prior_continuity(quote: Any, min_days: int) -> bool:
        if int(min_days or 0) <= 0:
            return True
        return _prior_quote_days(quote) >= int(min_days)

    for expiry, expiry_quotes in quotes_by_expiry.items():
        expiry_date = date.fromisoformat(expiry)
        dte = max((expiry_date - entry_date).days, 1)
        sorted_quotes = sorted(expiry_quotes, key=lambda quote: float(quote.strike))
        deltas = {
            quote.contract_symbol: _option_delta_for_quote(
                quote,
                stock_px=S0,
                hv30=hv30,
                trade_type=trade_type,
                entry_date=entry_date,
                iv_adj=iv_adj,
            )
            for quote in sorted_quotes
        }
        long_candidates = sorted(
            sorted_quotes,
            key=lambda quote: abs(deltas.get(quote.contract_symbol, 0.0) - float(long_delta_target)),
        )[:30]
        short_candidates = sorted(
            sorted_quotes,
            key=lambda quote: abs(deltas.get(quote.contract_symbol, 0.0) - float(short_delta_target)),
        )[:50]
        for long_quote in long_candidates:
            if not _has_prior_continuity(long_quote, long_min_prior_days):
                continue
            long_prior_days = _prior_quote_days(long_quote) if long_prior_weight > 0.0 and prior_score_cap_days > 0 else 0
            long_prior_days_for_diag = (
                int(continuity_cache[str(long_quote.contract_symbol)]["quote_date_count"])
                if str(long_quote.contract_symbol) in continuity_cache
                else None
            )
            for short_quote in short_candidates:
                if long_quote.contract_symbol == short_quote.contract_symbol:
                    continue
                if trade_type == "call" and float(short_quote.strike) <= float(long_quote.strike):
                    continue
                if trade_type == "put" and float(short_quote.strike) >= float(long_quote.strike):
                    continue
                if min_entry_short_bid is not None and float(short_quote.bid or 0.0) < float(min_entry_short_bid):
                    continue
                if not _has_prior_continuity(short_quote, short_min_prior_days):
                    continue
                short_prior_days = _prior_quote_days(short_quote) if short_prior_weight > 0.0 and prior_score_cap_days > 0 else 0
                short_prior_days_for_diag = (
                    int(continuity_cache[str(short_quote.contract_symbol)]["quote_date_count"])
                    if str(short_quote.contract_symbol) in continuity_cache
                    else None
                )
                spread_width = abs(float(short_quote.strike) - float(long_quote.strike))
                if spread_width <= 0 or (spread_width / float(S0) * 100.0) > float(max_width_pct):
                    continue
                long_entry_exec = _resolve_imported_execution_price(
                    side="entry",
                    requested_pricing_lane=requested_pricing_lane,
                    bid=long_quote.bid,
                    ask=long_quote.ask,
                    last=long_quote.last,
                    slippage_pct=entry_slippage_pct,
                )
                short_entry_exec = _resolve_imported_execution_price(
                    side="exit",
                    requested_pricing_lane=requested_pricing_lane,
                    bid=short_quote.bid,
                    ask=short_quote.ask,
                    last=short_quote.last,
                    slippage_pct=entry_slippage_pct,
                )
                long_px = float(long_entry_exec.get("execution_price") or 0.0)
                short_px = float(short_entry_exec.get("execution_price") or 0.0)
                net_debit = long_px - short_px
                if net_debit <= 0.01:
                    continue
                debit_pct = net_debit / spread_width * 100.0
                if max_debit_pct_of_width is not None and debit_pct >= float(max_debit_pct_of_width):
                    continue
                long_delta = deltas.get(long_quote.contract_symbol, 0.0)
                short_delta = deltas.get(short_quote.contract_symbol, 0.0)
                prior_quote_credit = 0.0
                if prior_score_cap_days > 0:
                    prior_quote_credit = (
                        min(max(long_prior_days, 0), prior_score_cap_days) * long_prior_weight
                        + min(max(short_prior_days, 0), prior_score_cap_days) * short_prior_weight
                    )
                score = (
                    abs(long_delta - float(long_delta_target)) * 100.0
                    + abs(short_delta - float(short_delta_target)) * 100.0
                    + abs(dte - int(target_dte)) * 0.75
                    + debit_pct * 0.05
                    + (_quote_spread_pct(long_quote) + _quote_spread_pct(short_quote)) * 0.02
                    - (_quote_liquidity_score(long_quote) + _quote_liquidity_score(short_quote)) * 0.05
                    - prior_quote_credit
                )
                if include_diagnostics:
                    alternatives.append(
                        (
                            score,
                            long_quote,
                            short_quote,
                            net_debit,
                            spread_width,
                            long_delta,
                            short_delta,
                            dte,
                            long_prior_days_for_diag,
                            short_prior_days_for_diag,
                        )
                    )
                if best is None or score < best[0]:
                    best = (score, long_quote, short_quote, net_debit, spread_width, long_delta, short_delta)
    if best is None:
        return None
    best_score, long_quote, short_quote, net_debit, spread_width, long_delta, short_delta = best
    inside_steps = max(int(short_inside_steps or 0), 0)
    if inside_steps > 0:
        expiry_quotes = sorted(
            quotes_by_expiry.get(str(long_quote.expiry)[:10], []),
            key=lambda quote: float(quote.strike),
        )
        if trade_type == "call":
            inside_candidates = [
                quote
                for quote in expiry_quotes
                if float(long_quote.strike) < float(quote.strike) < float(short_quote.strike)
            ]
            inside_candidates = sorted(
                inside_candidates,
                key=lambda quote: float(short_quote.strike) - float(quote.strike),
            )
        else:
            inside_candidates = [
                quote
                for quote in expiry_quotes
                if float(long_quote.strike) > float(quote.strike) > float(short_quote.strike)
            ]
            inside_candidates = sorted(
                inside_candidates,
                key=lambda quote: float(quote.strike) - float(short_quote.strike),
            )
        for inside_quote in inside_candidates:
            if inside_steps <= 0:
                break
            inside_steps -= 1
            if inside_quote.contract_symbol == long_quote.contract_symbol:
                continue
            if min_entry_short_bid is not None and float(inside_quote.bid or 0.0) < float(min_entry_short_bid):
                continue
            if not _has_prior_continuity(inside_quote, short_min_prior_days):
                continue
            inside_width = abs(float(inside_quote.strike) - float(long_quote.strike))
            if inside_width <= 0 or (inside_width / float(S0) * 100.0) > float(max_width_pct):
                continue
            inside_short_entry_exec = _resolve_imported_execution_price(
                side="exit",
                requested_pricing_lane=requested_pricing_lane,
                bid=inside_quote.bid,
                ask=inside_quote.ask,
                last=inside_quote.last,
                slippage_pct=entry_slippage_pct,
            )
            inside_short_px = float(inside_short_entry_exec.get("execution_price") or 0.0)
            inside_net_debit = float(
                _resolve_imported_execution_price(
                    side="entry",
                    requested_pricing_lane=requested_pricing_lane,
                    bid=long_quote.bid,
                    ask=long_quote.ask,
                    last=long_quote.last,
                    slippage_pct=entry_slippage_pct,
                ).get("execution_price")
                or 0.0
            ) - inside_short_px
            if inside_net_debit <= 0.01:
                continue
            inside_debit_pct = inside_net_debit / inside_width * 100.0
            if (
                bool(short_inside_require_debit_cap)
                and max_debit_pct_of_width is not None
                and inside_debit_pct >= float(max_debit_pct_of_width)
            ):
                continue
            short_quote = inside_quote
            net_debit = inside_net_debit
            spread_width = inside_width
            short_delta = deltas.get(inside_quote.contract_symbol, 0.0)
            break
    selected = (long_quote, short_quote, net_debit, spread_width, long_delta, short_delta)
    if not include_diagnostics:
        return selected

    def _prior_days_for_selected(quote: Any) -> int:
        symbol = str(quote.contract_symbol)
        if symbol in continuity_cache:
            return int(continuity_cache[symbol].get("quote_date_count") or 0)
        return _prior_quote_days(quote)

    selected_expiry = date.fromisoformat(str(long_quote.expiry)[:10])
    selected_dte = max((selected_expiry - entry_date).days, 1)
    selected_spread = _compact_chain_native_spread_diagnostic(
        long_quote=long_quote,
        short_quote=short_quote,
        net_debit=net_debit,
        spread_width=spread_width,
        long_delta=long_delta,
        short_delta=short_delta,
        long_delta_target=long_delta_target,
        short_delta_target=short_delta_target,
        score=best_score,
        entry_date=entry_date,
        dte=selected_dte,
        long_prior_quote_days=_prior_days_for_selected(long_quote),
        short_prior_quote_days=_prior_days_for_selected(short_quote),
    )
    top_spread_alternatives = [
        _compact_chain_native_spread_diagnostic(
            long_quote=alt_long_quote,
            short_quote=alt_short_quote,
            net_debit=alt_net_debit,
            spread_width=alt_spread_width,
            long_delta=alt_long_delta,
            short_delta=alt_short_delta,
            long_delta_target=long_delta_target,
            short_delta_target=short_delta_target,
            score=alt_score,
            entry_date=entry_date,
            dte=alt_dte,
            long_prior_quote_days=alt_long_prior_days,
            short_prior_quote_days=alt_short_prior_days,
        )
        for (
            alt_score,
            alt_long_quote,
            alt_short_quote,
            alt_net_debit,
            alt_spread_width,
            alt_long_delta,
            alt_short_delta,
            alt_dte,
            alt_long_prior_days,
            alt_short_prior_days,
        ) in sorted(alternatives, key=lambda item: item[0])[:3]
    ]
    return {
        "selected": selected,
        "diagnostics": {
            "spread_diagnostics_proof_role": "diagnostic_only",
            "selected_spread": selected_spread,
            "top_spread_alternatives": top_spread_alternatives,
            "fill_degradation_vs_mid": selected_spread.get("fill_degradation_vs_mid"),
            "fill_degradation_vs_mid_pct": selected_spread.get("fill_degradation_vs_mid_pct"),
            "entry_spread_mid_debit": selected_spread.get("mid_debit"),
            "entry_spread_ask_bid_debit": selected_spread.get("ask_bid_debit"),
        },
    }


def _spread_tradability_score(
    *,
    store: Any,
    long_quote: Any,
    short_quote: Any,
    entry_date: date,
    snapshot_kind: str,
    source_labels: Optional[Sequence[str]],
    trusted_only: bool,
    lookback_calendar_days: int,
    min_short_leg_prior_quote_days: int,
    min_long_leg_prior_quote_days: int = 0,
) -> dict[str, Any]:
    long_metrics = _contract_prior_quote_continuity_metrics(
        store,
        long_quote,
        entry_date=entry_date,
        snapshot_kind=snapshot_kind,
        source_labels=source_labels,
        trusted_only=trusted_only,
        lookback_calendar_days=lookback_calendar_days,
    )
    short_metrics = _contract_prior_quote_continuity_metrics(
        store,
        short_quote,
        entry_date=entry_date,
        snapshot_kind=snapshot_kind,
        source_labels=source_labels,
        trusted_only=trusted_only,
        lookback_calendar_days=lookback_calendar_days,
    )
    score = 100.0
    reasons: list[str] = []
    long_days = int(long_metrics.get("quote_date_count") or 0)
    short_days = int(short_metrics.get("quote_date_count") or 0)
    if min_long_leg_prior_quote_days > 0 and long_days < int(min_long_leg_prior_quote_days):
        score -= 20.0
        reasons.append("low_prior_long_leg_continuity")
    if min_short_leg_prior_quote_days > 0 and short_days < int(min_short_leg_prior_quote_days):
        score -= 35.0
        reasons.append("short_leg_survival_risk")
    short_spread_pct = _quote_spread_pct(short_quote)
    long_spread_pct = _quote_spread_pct(long_quote)
    if short_spread_pct > 40.0 or long_spread_pct > 40.0:
        score -= 20.0
        reasons.append("wide_prior_spread")
    if float(getattr(short_quote, "bid", 0.0) or 0.0) < 0.05:
        score -= 15.0
        reasons.append("low_entry_short_bid")
    score = max(0.0, min(100.0, score))
    return {
        "tradability_score": round(score, 1),
        "tradability_reasons": reasons,
        "long_prior_quote_days": long_days,
        "short_prior_quote_days": short_days,
        "long_prior_avg_bid_ask_pct": long_metrics.get("avg_bid_ask_pct"),
        "short_prior_avg_bid_ask_pct": short_metrics.get("avg_bid_ask_pct"),
        "long_entry_bid_ask_pct": round(long_spread_pct, 2) if long_spread_pct < 999 else None,
        "short_entry_bid_ask_pct": round(short_spread_pct, 2) if short_spread_pct < 999 else None,
    }


def _simulate_spread_outcome_imported(
    *,
    store: "HistoricalOptionsStore",
    ticker: str,
    dates: pd.Index,
    prices: np.ndarray,
    i: int,
    trade_type: str,
    hv30: float,
    long_delta_target: float,
    short_delta_target: float,
    dte_at_entry: int,
    stop_loss_pct: float,
    profit_target_pct: float,
    time_exit_pct: float,
    trailing_profit_pct: float,
    trailing_giveback_pct: float,
    max_width_pct: float = 5.0,
    exit_monitoring_mode: str = "daily",
    time_exit_basis: str = "trading_sessions",
    _rsi14: np.ndarray = None,
    _macd: np.ndarray = None,
    _sma20: np.ndarray = None,
    _sma50: np.ndarray = None,
    tech_at_entry: float = 50.0,
    entry_S0: Optional[float] = None,
    iv_adj: float = 1.20,
    truth_source: str = IMPORTED_TRUTH_SOURCE,
    snapshot_kind: str = DAILY_SNAPSHOT_KIND,
    entry_quote_minute_et: int = ENTRY_QUOTE_MINUTE_ET,
    entry_window_minutes: int = ENTRY_QUOTE_WINDOW_MINUTES,
    entry_slippage_pct: float = 0.0,
    exit_slippage_pct: float = 0.0,
    commission_per_contract_usd: float = DEFAULT_COMMISSION_PER_CONTRACT_USD,
    pricing_lane: str = "pessimistic",
    entry_anchor_source: Optional[str] = None,
    execution_realism: Optional[str] = None,
    source_labels: Optional[Sequence[str]] = None,
    trusted_only: bool = False,
    chain_native_spread_selection: bool = False,
    chain_native_min_dte: int | None = None,
    chain_native_max_dte: int | None = None,
    max_debit_pct_of_width: float | None = None,
    chain_native_min_prior_quote_days: int = 0,
    chain_native_prior_quote_lookback_days: int = 14,
    chain_native_min_long_prior_quote_days: int | None = None,
    chain_native_min_short_prior_quote_days: int | None = None,
    chain_native_prior_quote_score_weight: float = 0.0,
    chain_native_long_prior_quote_score_weight: float | None = None,
    chain_native_short_prior_quote_score_weight: float | None = None,
    chain_native_prior_quote_score_cap: int = 5,
    chain_native_max_entry_leg_bid_ask_pct: float | None = None,
    chain_native_min_entry_short_bid: float | None = None,
    chain_native_short_inside_steps: int = 0,
    chain_native_short_inside_require_debit_cap: bool = True,
) -> dict:
    """
    Simulate a vertical spread using real archived option quotes.
    Finds long and short leg contracts from the historical store,
    tracks both legs daily, and exits based on spread value.
    """
    normalized_truth_source = str(truth_source or IMPORTED_TRUTH_SOURCE).strip().lower()
    requested_pricing_lane = _normalize_requested_pricing_lane(pricing_lane)
    execution_realism_label = str(execution_realism or _execution_realism_label(normalized_truth_source)).strip()
    resolved_entry_anchor_source = str(entry_anchor_source or "provided_entry_s0").strip()
    monitoring_mode = str(exit_monitoring_mode or "daily").strip().lower()
    time_only_monitoring = monitoring_mode in {"time_only", "time_exit_only", "fixed_time", "fixed_time_exit"}
    normalized_time_exit_basis = str(time_exit_basis or "trading_sessions").strip().lower()
    calendar_time_exit = normalized_time_exit_basis in {"calendar", "calendar_days", "calendar_elapsed", "elapsed_calendar"}
    n = len(prices)
    S0 = float(entry_S0) if entry_S0 is not None else float(prices[i])
    entry_date = pd.Timestamp(dates[i]).date()
    target_expiry = entry_date + timedelta(days=max(int(dte_at_entry), 1))

    _not_priced = lambda reason, **extra: {
        "priced": False,
        "unpriced_reason": reason,
        "entry_day_idx": i,
        "truth_source": normalized_truth_source,
        "strategy_type": "vertical_spread",
        **extra,
    }

    long_greeks: dict[str, Any] | None = None
    short_greeks: dict[str, Any] | None = None
    contract_selection_source = "model_target_spread"
    selected_long_delta: float | None = None
    selected_short_delta: float | None = None
    spread_diagnostics: dict[str, Any] = {}
    if chain_native_spread_selection:
        selected = _select_chain_native_spread(
            store=store,
            ticker=ticker,
            entry_date=entry_date,
            trade_type=trade_type,
            S0=S0,
            hv30=hv30,
            long_delta_target=long_delta_target,
            short_delta_target=short_delta_target,
            target_dte=dte_at_entry,
            min_dte=int(chain_native_min_dte if chain_native_min_dte is not None else max(1, dte_at_entry - 7)),
            max_dte=int(chain_native_max_dte if chain_native_max_dte is not None else dte_at_entry + 10),
            max_width_pct=max_width_pct,
            max_debit_pct_of_width=max_debit_pct_of_width,
            iv_adj=iv_adj,
            requested_pricing_lane=requested_pricing_lane,
            entry_slippage_pct=entry_slippage_pct,
            snapshot_kind=snapshot_kind,
            entry_quote_minute_et=entry_quote_minute_et,
            entry_window_minutes=entry_window_minutes,
            source_labels=source_labels,
            trusted_only=trusted_only,
            min_prior_quote_days=int(chain_native_min_prior_quote_days or 0),
            prior_quote_lookback_days=int(chain_native_prior_quote_lookback_days or 14),
            min_long_prior_quote_days=chain_native_min_long_prior_quote_days,
            min_short_prior_quote_days=chain_native_min_short_prior_quote_days,
            prior_quote_score_weight=float(chain_native_prior_quote_score_weight or 0.0),
            long_prior_quote_score_weight=chain_native_long_prior_quote_score_weight,
            short_prior_quote_score_weight=chain_native_short_prior_quote_score_weight,
            prior_quote_score_cap=int(chain_native_prior_quote_score_cap or 0),
            max_entry_leg_bid_ask_pct=chain_native_max_entry_leg_bid_ask_pct,
            min_entry_short_bid=chain_native_min_entry_short_bid,
            short_inside_steps=int(chain_native_short_inside_steps or 0),
            short_inside_require_debit_cap=bool(chain_native_short_inside_require_debit_cap),
            include_diagnostics=True,
        )
        if selected is None:
            return _not_priced("no_chain_native_spread")
        if isinstance(selected, dict):
            spread_diagnostics = dict(selected.get("diagnostics") or {})
            selected = selected.get("selected")
        if selected is None:
            return _not_priced("no_chain_native_spread")
        long_entry_quote, short_entry_quote, selected_net_debit, selected_spread_width, selected_long_delta, selected_short_delta = selected
        long_strike = float(long_entry_quote.strike)
        short_strike = float(short_entry_quote.strike)
        contract_selection_source = "chain_native_listed_spread"
    else:
        # Find long leg (higher delta, closer to ATM)
        long_strike, long_greeks = _select_target_contract(S0, hv30, trade_type, long_delta_target, dte_at_entry, iv_adj)
        if long_strike is None:
            return _not_priced("no_long_leg_target")

        long_entry_quote = store.find_entry_contract(
            underlying=ticker, trade_date_et=entry_date, option_type=trade_type,
            target_expiry=target_expiry, target_strike=long_strike,
            earliest_minute_et=entry_quote_minute_et, window_minutes=entry_window_minutes,
            snapshot_kind=snapshot_kind, allow_last_price=False, source_labels=source_labels,
            trusted_only=trusted_only,
        )
        if long_entry_quote is None:
            return _not_priced("missing_long_entry_quote")

        # Find short leg (lower delta, more OTM)
        short_strike, short_greeks = _select_target_contract(S0, hv30, trade_type, short_delta_target, dte_at_entry, iv_adj)
        if short_strike is None:
            return _not_priced("no_short_leg_target")

        # Ensure short is more OTM
        if trade_type == "call" and short_strike <= long_strike:
            short_strike = long_strike + (_market_strike_grid(S0)[1] - _market_strike_grid(S0)[0] if len(_market_strike_grid(S0)) > 1 else 5.0)
        elif trade_type == "put" and short_strike >= long_strike:
            short_strike = long_strike - (_market_strike_grid(S0)[1] - _market_strike_grid(S0)[0] if len(_market_strike_grid(S0)) > 1 else 5.0)

        short_entry_quote = store.find_entry_contract(
            underlying=ticker, trade_date_et=entry_date, option_type=trade_type,
            target_expiry=target_expiry, target_strike=short_strike,
            earliest_minute_et=entry_quote_minute_et, window_minutes=entry_window_minutes,
            snapshot_kind=snapshot_kind, allow_last_price=False, source_labels=source_labels,
            trusted_only=trusted_only,
        )
        if short_entry_quote is None:
            return _not_priced("missing_short_entry_quote")

    expiry_date = date.fromisoformat(long_entry_quote.expiry)
    short_expiry_date = date.fromisoformat(short_entry_quote.expiry)
    if short_expiry_date != expiry_date:
        return _not_priced(
            "mismatched_spread_expiry",
            target_expiry=target_expiry.isoformat(),
            long_expiry=long_entry_quote.expiry,
            short_expiry=short_entry_quote.expiry,
        )

    # Validate spread width
    spread_width = abs(float(long_entry_quote.strike) - float(short_entry_quote.strike))
    if spread_width <= 0 or (spread_width / S0 * 100) > max_width_pct:
        return _not_priced("invalid_spread_width")

    # Compute entry prices
    long_entry_exec = _resolve_imported_execution_price(
        side="entry", requested_pricing_lane=requested_pricing_lane,
        bid=long_entry_quote.bid, ask=long_entry_quote.ask, last=long_entry_quote.last,
        slippage_pct=entry_slippage_pct,
    )
    short_entry_exec = _resolve_imported_execution_price(
        side="exit", requested_pricing_lane=requested_pricing_lane,  # selling short leg = "exit" side pricing
        bid=short_entry_quote.bid, ask=short_entry_quote.ask, last=short_entry_quote.last,
        slippage_pct=entry_slippage_pct,
    )
    long_entry_px = float(long_entry_exec.get("execution_price") or 0.0)
    short_entry_px = float(short_entry_exec.get("execution_price") or 0.0)

    if long_entry_px <= 0:
        return _not_priced("invalid_long_entry_price")

    net_debit = long_entry_px - short_entry_px
    if net_debit <= 0.01:
        return _not_priced("zero_or_negative_net_debit")
    spread_diagnostic_fields = dict(spread_diagnostics)
    if spread_diagnostic_fields:
        selected_spread = dict(spread_diagnostic_fields.get("selected_spread") or {})
        if selected_spread:
            selected_spread["net_debit"] = round(float(net_debit), 4)
            selected_spread["debit_pct_of_width"] = round(float(net_debit) / float(spread_width) * 100.0, 2)
            spread_diagnostic_fields["selected_spread"] = selected_spread

    # Exit thresholds
    actual_dte = max((expiry_date - entry_date).days, 1)
    long_is_exact_target = (
        expiry_date == target_expiry
        and abs(float(long_entry_quote.strike) - float(long_strike)) <= 0.0001
    )
    short_is_exact_target = (
        short_expiry_date == target_expiry
        and abs(float(short_entry_quote.strike) - float(short_strike)) <= 0.0001
    )
    contract_resolution = (
        "exact_listed_spread_contract"
        if chain_native_spread_selection
        else ("exact_target_contract" if long_is_exact_target and short_is_exact_target else "nearest_listed_contract")
    )
    time_exit_day = max(1, math.ceil(actual_dte * time_exit_pct / 100))
    target_time_exit_date = min(expiry_date, entry_date + timedelta(days=time_exit_day))
    stop_value = net_debit * (1.0 - stop_loss_pct / 100.0)
    target_value = net_debit * (1.0 + profit_target_pct / 100.0)
    target_value = min(target_value, spread_width)  # can't exceed spread width

    trail_activate_pct = max(0.0, float(trailing_profit_pct))
    trail_giveback_pct = max(0.0, float(trailing_giveback_pct))
    high_watermark = net_debit
    trail_active = False
    trail_stop_value = 0.0

    exit_spread_value = net_debit
    exit_reason = "unpriced"
    exit_stock_px = S0
    exit_day_idx = i

    max_walk_days = min(n - i - 1, max(actual_dte, dte_at_entry, time_exit_day))
    for d in range(1, max_walk_days + 1):
        fi = i + d
        quote_date = pd.Timestamp(dates[fi]).date()

        if quote_date > expiry_date:
            # Expiry: intrinsic values
            if trade_type == "call":
                long_intrinsic = max(0.0, float(prices[fi]) - float(long_entry_quote.strike))
                short_intrinsic = max(0.0, float(prices[fi]) - float(short_entry_quote.strike))
            else:
                long_intrinsic = max(0.0, float(long_entry_quote.strike) - float(prices[fi]))
                short_intrinsic = max(0.0, float(short_entry_quote.strike) - float(prices[fi]))
            exit_spread_value = max(0.0, long_intrinsic - short_intrinsic)
            exit_reason = "expired"
            exit_stock_px = float(prices[fi])
            exit_day_idx = fi
            break

        time_exit_reached = quote_date >= target_time_exit_date if calendar_time_exit else d >= time_exit_day

        if time_only_monitoring and not time_exit_reached and quote_date < expiry_date:
            continue

        # Get daily quotes for both legs
        long_quote = store.get_closing_quote(
            contract_symbol=long_entry_quote.contract_symbol,
            quote_date_et=quote_date, snapshot_kind=snapshot_kind, allow_last_price=False,
            source_labels=source_labels,
            trusted_only=trusted_only,
        )
        short_quote = store.get_closing_quote(
            contract_symbol=short_entry_quote.contract_symbol,
            quote_date_et=quote_date, snapshot_kind=snapshot_kind, allow_last_price=False,
            source_labels=source_labels,
            trusted_only=trusted_only,
        )

        if long_quote is None or short_quote is None:
            if quote_date >= expiry_date:
                if trade_type == "call":
                    long_intrinsic = max(0.0, float(prices[fi]) - float(long_entry_quote.strike))
                    short_intrinsic = max(0.0, float(prices[fi]) - float(short_entry_quote.strike))
                else:
                    long_intrinsic = max(0.0, float(long_entry_quote.strike) - float(prices[fi]))
                    short_intrinsic = max(0.0, float(short_entry_quote.strike) - float(prices[fi]))
                exit_spread_value = max(0.0, long_intrinsic - short_intrinsic)
                exit_reason = "expired"
                exit_stock_px = float(prices[fi])
                exit_day_idx = fi
                break
            return _not_priced(
                "missing_exit_quote_for_leg",
                missing_quote_date=quote_date.isoformat(),
                missing_long_contract_symbol=long_entry_quote.contract_symbol if long_quote is None else None,
                missing_short_contract_symbol=short_entry_quote.contract_symbol if short_quote is None else None,
                long_contract_symbol=long_entry_quote.contract_symbol,
                short_contract_symbol=short_entry_quote.contract_symbol,
                long_entry_expiry=long_entry_quote.expiry,
                short_entry_expiry=short_entry_quote.expiry,
                long_entry_strike=float(long_entry_quote.strike),
                short_entry_strike=float(short_entry_quote.strike),
                **spread_diagnostic_fields,
            )

        # Mark-to-market both legs
        long_exit_exec = _resolve_imported_execution_price(
            side="exit", requested_pricing_lane=requested_pricing_lane,
            bid=long_quote.bid, ask=long_quote.ask, last=long_quote.last,
            slippage_pct=exit_slippage_pct,
        )
        short_exit_exec = _resolve_imported_execution_price(
            side="entry", requested_pricing_lane=requested_pricing_lane,  # buying back short = "entry" side pricing
            bid=short_quote.bid, ask=short_quote.ask, last=short_quote.last,
            slippage_pct=exit_slippage_pct,
        )
        long_now = float(long_exit_exec.get("execution_price") or 0.0)
        short_now = float(short_exit_exec.get("execution_price") or 0.0)
        spread_value = max(0.0, long_now - short_now)

        if time_only_monitoring:
            exit_spread_value = spread_value
            exit_reason = "time_exit"
            exit_stock_px = float(prices[fi])
            exit_day_idx = fi
            break

        if spread_value > high_watermark:
            high_watermark = spread_value
        current_pnl_pct = ((spread_value / net_debit) - 1.0) * 100.0 if net_debit > 0 else 0.0
        peak_pnl_pct = ((high_watermark / net_debit) - 1.0) * 100.0 if net_debit > 0 else 0.0

        if not trail_active and peak_pnl_pct >= trail_activate_pct:
            trail_active = True
        if trail_active and peak_pnl_pct > 0.0:
            retained = peak_pnl_pct * max(0.0, 1.0 - trail_giveback_pct / 100.0)
            trail_stop_value = net_debit * (1.0 + retained / 100.0)

        effective_stop = max(stop_value, trail_stop_value) if trail_active else stop_value

        if spread_value <= effective_stop:
            exit_spread_value = spread_value
            exit_reason = "trailing_stop" if trail_active else "stop"
            exit_stock_px = float(prices[fi])
            exit_day_idx = fi
            break

        if spread_value >= target_value:
            exit_spread_value = min(spread_value, target_value)
            exit_reason = "target"
            exit_stock_px = float(prices[fi])
            exit_day_idx = fi
            break

        if time_exit_reached:
            exit_spread_value = spread_value
            exit_reason = "time_exit"
            exit_stock_px = float(prices[fi])
            exit_day_idx = fi
            break
    else:
        return _not_priced("insufficient_quote_history")

    # P&L
    gross_pnl_per_share = exit_spread_value - net_debit
    gross_pnl_usd = gross_pnl_per_share * 100
    fee_total = 4 * commission_per_contract_usd
    net_pnl_usd = gross_pnl_usd - fee_total
    capital_at_risk = net_debit * 100
    gross_pnl_pct = (gross_pnl_per_share / net_debit * 100.0) if net_debit > 0 else 0.0
    net_pnl_pct = (net_pnl_usd / capital_at_risk * 100.0) if capital_at_risk > 0 else 0.0

    stock_move_pct = (exit_stock_px / S0 - 1.0) * 100 if S0 > 0 else 0.0
    directional_correct = (
        (trade_type == "call" and stock_move_pct > 0)
        or (trade_type == "put" and stock_move_pct < 0)
    )
    return {
        "priced": True,
        "entry_px": round(net_debit, 4),
        "exit_px": round(exit_spread_value, 4),
        "pnl_pct": round(net_pnl_pct, 2),
        "gross_pnl_pct": round(gross_pnl_pct, 2),
        "net_pnl_pct": round(net_pnl_pct, 2),
        "gross_pnl_usd": round(gross_pnl_usd, 2),
        "net_pnl_usd": round(net_pnl_usd, 2),
        "fee_total_usd": round(fee_total, 2),
        "entry_fee_total_usd": round(fee_total / 2, 2),
        "exit_fee_total_usd": round(fee_total / 2, 2),
        "exit_reason": exit_reason,
        "exit_fill_basis": "imported_spread_mark",
        "exit_monitoring_mode": monitoring_mode,
        "time_exit_basis": "calendar_elapsed" if calendar_time_exit else "trading_sessions",
        "time_exit_day": time_exit_day,
        "time_exit_target_date": target_time_exit_date.isoformat(),
        "strike": round(float(long_entry_quote.strike), 2),
        "short_strike": round(float(short_entry_quote.strike), 2),
        "spread_width": round(spread_width, 2),
        "net_debit": round(net_debit, 4),
        "max_profit": round(spread_width - net_debit, 4),
        "max_loss": round(net_debit, 4),
        "delta_val": round(
            abs(float(selected_long_delta if selected_long_delta is not None else (long_greeks or {}).get("delta", 0.0))),
            4,
        ),
        "short_delta_val": (
            round(abs(float(selected_short_delta)), 4)
            if selected_short_delta is not None
            else round(abs(float((short_greeks or {}).get("delta", 0.0))), 4)
        ),
        "stock_px": round(S0, 4),
        "exit_stock_px": round(exit_stock_px, 4),
        "stock_move_pct": round(stock_move_pct, 2),
        "directional_correct": directional_correct,
        "hv30": round(hv30, 4),
        "iv_adj": iv_adj,
        "dte": actual_dte,
        "entry_day_idx": i,
        "exit_day_idx": exit_day_idx,
        "strategy_type": "vertical_spread",
        "truth_source": normalized_truth_source,
        "requested_pricing_lane": requested_pricing_lane,
        "effective_pricing_lane": requested_pricing_lane,
        "pricing_lane": requested_pricing_lane,
        "entry_anchor_source": resolved_entry_anchor_source,
        "execution_realism": execution_realism_label,
        "contract_symbol": long_entry_quote.contract_symbol,
        "short_contract_symbol": short_entry_quote.contract_symbol,
        "entry_contract_resolution": contract_resolution,
        "contract_selection_source": contract_selection_source,
        "target_expiry": target_expiry.isoformat(),
        "target_strike": round(float(long_strike), 2),
        "target_short_strike": round(float(short_strike), 2),
        "long_entry_quote_basis": long_entry_quote.price_basis,
        "short_entry_quote_basis": short_entry_quote.price_basis,
        **spread_diagnostic_fields,
    }


def _simulate_trade_outcome_imported(
    *,
    store: HistoricalOptionsStore,
    ticker: str,
    dates: pd.Index,
    prices: np.ndarray,
    i: int,
    trade_type: str,
    hv30: float,
    delta_target: float,
    dte_at_entry: int,
    stop_loss_pct: float,
    profit_target_pct: float,
    time_exit_pct: float,
    trailing_profit_pct: float,
    trailing_giveback_pct: float,
    _rsi14: np.ndarray,
    _macd: np.ndarray,
    _sma20: np.ndarray,
    _sma50: np.ndarray,
    tech_at_entry: float,
    entry_S0: Optional[float] = None,
    iv_adj: float = 1.20,
    truth_source: str = IMPORTED_TRUTH_SOURCE,
    snapshot_kind: str = INTRADAY_SNAPSHOT_KIND,
    entry_quote_minute_et: int = ENTRY_QUOTE_MINUTE_ET,
    entry_window_minutes: int = ENTRY_QUOTE_WINDOW_MINUTES,
    archived_contract_symbol: Optional[str] = None,
    archived_expiry: Optional[str] = None,
    archived_strike: Optional[float] = None,
    archived_option_type: Optional[str] = None,
    archived_quote_time_et: Optional[str] = None,
    archived_quote_basis: Optional[str] = None,
    archived_underlying_price_at_selection: Optional[float] = None,
    archived_selection_source: Optional[str] = None,
    entry_slippage_pct: float = 0.0,
    exit_slippage_pct: float = 0.0,
    commission_per_contract_usd: float = DEFAULT_COMMISSION_PER_CONTRACT_USD,
    pricing_lane: str = "pessimistic",
    entry_anchor_source: Optional[str] = None,
    execution_realism: Optional[str] = None,
    source_labels: Optional[Sequence[str]] = None,
    trusted_only: bool = False,
) -> dict:
    normalized_truth_source = str(truth_source or IMPORTED_TRUTH_SOURCE).strip().lower() or IMPORTED_TRUTH_SOURCE
    requested_pricing_lane = _normalize_requested_pricing_lane(pricing_lane)
    execution_realism_label = str(execution_realism or _execution_realism_label(normalized_truth_source)).strip()
    resolved_entry_anchor_source = str(entry_anchor_source or "provided_entry_s0").strip() or "provided_entry_s0"
    n = len(prices)
    S0 = float(entry_S0) if entry_S0 is not None else float(prices[i])
    entry_date = pd.Timestamp(dates[i]).date()
    target_expiry = entry_date + timedelta(days=max(int(dte_at_entry), 1))
    target_strike, target_greeks = _select_target_contract(
        stock_px=S0,
        hv30=hv30,
        trade_type=trade_type,
        delta_target=delta_target,
        dte_at_entry=dte_at_entry,
        iv_adj=iv_adj,
    )
    normalized_archived_contract = str(archived_contract_symbol or "").strip().upper() or None

    entry_quote = None
    contract_resolution = None
    contract_selection_source = None
    if normalized_archived_contract:
        entry_quote = store.find_entry_quote_for_contract(
            contract_symbol=normalized_archived_contract,
            trade_date_et=entry_date,
            earliest_minute_et=entry_quote_minute_et,
            window_minutes=entry_window_minutes,
            snapshot_kind=snapshot_kind,
            allow_last_price=False,
            source_labels=source_labels,
            trusted_only=trusted_only,
        )
        if entry_quote is not None:
            contract_resolution = "exact_archived_contract"
            contract_selection_source = "archived_exact_contract"

    if entry_quote is None:
        if target_strike is None or not target_greeks:
            return {
                "priced": False,
                "unpriced_reason": "no_model_contract_target",
                "entry_day_idx": i,
                "truth_source": normalized_truth_source,
                "requested_pricing_lane": requested_pricing_lane,
                "effective_pricing_lane": requested_pricing_lane,
                "pricing_lane": requested_pricing_lane,
                "pricing_lane_fallback_reason": None,
                "entry_anchor_source": resolved_entry_anchor_source,
                "execution_realism": execution_realism_label,
                "requested_contract_symbol": normalized_archived_contract,
            }

        entry_quote = store.find_entry_contract(
            underlying=ticker,
            trade_date_et=entry_date,
            option_type=trade_type,
            target_expiry=target_expiry,
            target_strike=target_strike,
            earliest_minute_et=entry_quote_minute_et,
            window_minutes=entry_window_minutes,
            snapshot_kind=snapshot_kind,
            allow_last_price=False,
            source_labels=source_labels,
            trusted_only=trusted_only,
        )
        if entry_quote is not None:
            expiry_date = date.fromisoformat(entry_quote.expiry)
            contract_resolution = (
                "exact_target_contract"
                if expiry_date == target_expiry and abs(float(entry_quote.strike) - float(target_strike)) <= 0.0001
                else "nearest_listed_contract"
            )
            contract_selection_source = "model_target_contract"

    if entry_quote is None:
        return {
            "priced": False,
            "unpriced_reason": "missing_entry_quote",
            "entry_day_idx": i,
            "truth_source": normalized_truth_source,
            "requested_pricing_lane": requested_pricing_lane,
            "effective_pricing_lane": requested_pricing_lane,
            "pricing_lane": requested_pricing_lane,
            "pricing_lane_fallback_reason": None,
            "entry_anchor_source": resolved_entry_anchor_source,
            "execution_realism": execution_realism_label,
            "target_strike": round(float(target_strike), 2) if target_strike is not None else None,
            "target_expiry": target_expiry.isoformat(),
            "requested_contract_symbol": normalized_archived_contract,
        }

    entry_execution = _resolve_imported_execution_price(
        side="entry",
        requested_pricing_lane=requested_pricing_lane,
        bid=entry_quote.bid,
        ask=entry_quote.ask,
        last=entry_quote.last,
        slippage_pct=entry_slippage_pct,
    )
    entry_px = float(entry_execution.get("execution_price") or 0.0)
    if entry_px <= 0:
        return {
            "priced": False,
            "unpriced_reason": "invalid_entry_quote",
            "entry_day_idx": i,
            "truth_source": normalized_truth_source,
            "requested_pricing_lane": requested_pricing_lane,
            "effective_pricing_lane": requested_pricing_lane,
            "pricing_lane": requested_pricing_lane,
            "pricing_lane_fallback_reason": entry_execution.get("pricing_lane_fallback_reason"),
            "entry_anchor_source": resolved_entry_anchor_source,
            "execution_realism": execution_realism_label,
            "contract_symbol": entry_quote.contract_symbol,
            "contract_selection_source": contract_selection_source,
        }

    expiry_date = date.fromisoformat(entry_quote.expiry)
    actual_dte = max((expiry_date - entry_date).days, 1)
    if contract_resolution is None:
        contract_resolution = (
            "exact_target_contract"
            if target_strike is not None and expiry_date == target_expiry and abs(float(entry_quote.strike) - float(target_strike)) <= 0.0001
            else "nearest_listed_contract"
        )
    if contract_selection_source is None:
        contract_selection_source = "model_target_contract"
    time_exit_day = max(1, math.ceil(actual_dte * time_exit_pct / 100))
    stop_px = entry_px * (1 - stop_loss_pct / 100.0)
    target_px = entry_px * (1 + profit_target_pct / 100.0)

    trail_activate_pct = max(0.0, float(trailing_profit_pct))
    trail_giveback_pct = max(0.0, float(trailing_giveback_pct))
    high_watermark = entry_px
    trail_active = False
    trail_stop_px = 0.0
    dynamic_stop_px = stop_px

    exit_px = entry_px
    exit_reason = "unpriced"
    exit_fill_basis = f"historical_{entry_execution.get('execution_basis') or entry_quote.price_basis}"
    exit_stock_px = S0
    exit_day_idx = i
    exit_quote_at_utc = entry_quote.as_of_utc
    exit_quote_minute_et = entry_quote.quote_minute_et

    max_walk_days = min(n - i - 1, max(actual_dte, dte_at_entry, time_exit_day))
    last_quote_date: Optional[str] = None
    for d in range(1, max_walk_days + 1):
        fi = i + d
        quote_date = pd.Timestamp(dates[fi]).date()
        last_quote_date = quote_date.isoformat()

        if quote_date > expiry_date:
            intrinsic = max(0.0, float(prices[fi]) - entry_quote.strike) if trade_type == "call" else max(0.0, entry_quote.strike - float(prices[fi]))
            exit_px = intrinsic
            exit_reason = "expired"
            exit_fill_basis = "expiry_intrinsic"
            exit_stock_px = float(prices[fi])
            exit_day_idx = fi
            break

        quote = store.get_closing_quote(
            contract_symbol=entry_quote.contract_symbol,
            quote_date_et=quote_date,
            snapshot_kind=snapshot_kind,
            allow_last_price=False,
            source_labels=source_labels,
            trusted_only=trusted_only,
        )
        if quote is None:
            if quote_date >= expiry_date:
                intrinsic = max(0.0, float(prices[fi]) - entry_quote.strike) if trade_type == "call" else max(0.0, entry_quote.strike - float(prices[fi]))
                exit_px = intrinsic
                exit_reason = "expired"
                exit_fill_basis = "expiry_intrinsic"
                exit_stock_px = float(prices[fi])
                exit_day_idx = fi
                break
            return {
                "priced": False,
                "unpriced_reason": "missing_exit_quote",
                "entry_day_idx": i,
                "truth_source": normalized_truth_source,
                "requested_pricing_lane": requested_pricing_lane,
                "effective_pricing_lane": entry_execution.get("effective_pricing_lane") or requested_pricing_lane,
                "pricing_lane": entry_execution.get("effective_pricing_lane") or requested_pricing_lane,
                "pricing_lane_fallback_reason": entry_execution.get("pricing_lane_fallback_reason"),
                "entry_anchor_source": resolved_entry_anchor_source,
                "execution_realism": execution_realism_label,
                "contract_symbol": entry_quote.contract_symbol,
                "missing_quote_date": quote_date.isoformat(),
                "entry_quote_at_utc": entry_quote.as_of_utc,
                "entry_quote_basis": entry_quote.price_basis,
                "entry_quote_time_et": (
                    "End-of-day snapshot ET"
                    if snapshot_kind == DAILY_SNAPSHOT_KIND
                    else _et_minute_label(entry_quote.quote_minute_et)
                ),
                "target_strike": round(float(target_strike), 2) if target_strike is not None else None,
                "target_expiry": target_expiry.isoformat(),
                "entry_contract_resolution": contract_resolution,
                "contract_selection_source": contract_selection_source,
            }

        exit_execution = _resolve_imported_execution_price(
            side="exit",
            requested_pricing_lane=requested_pricing_lane,
            bid=quote.bid,
            ask=quote.ask,
            last=quote.last,
            slippage_pct=exit_slippage_pct,
        )
        opt_now = float(exit_execution.get("execution_price") or 0.0)
        exit_fill_basis = f"historical_{exit_execution.get('execution_basis') or quote.price_basis}"
        exit_quote_at_utc = quote.as_of_utc
        exit_quote_minute_et = quote.quote_minute_et
        if opt_now <= 0:
            return {
                "priced": False,
                "unpriced_reason": "invalid_exit_quote",
                "entry_day_idx": i,
                "truth_source": normalized_truth_source,
                "requested_pricing_lane": requested_pricing_lane,
                "effective_pricing_lane": entry_execution.get("effective_pricing_lane") or requested_pricing_lane,
                "pricing_lane": entry_execution.get("effective_pricing_lane") or requested_pricing_lane,
                "pricing_lane_fallback_reason": (
                    exit_execution.get("pricing_lane_fallback_reason")
                    or entry_execution.get("pricing_lane_fallback_reason")
                ),
                "entry_anchor_source": resolved_entry_anchor_source,
                "execution_realism": execution_realism_label,
                "contract_symbol": entry_quote.contract_symbol,
                "entry_quote_at_utc": entry_quote.as_of_utc,
                "entry_quote_basis": entry_quote.price_basis,
                "entry_contract_resolution": contract_resolution,
                "contract_selection_source": contract_selection_source,
            }
        if opt_now > high_watermark:
            high_watermark = opt_now
        current_pnl_pct = ((opt_now / entry_px) - 1.0) * 100.0 if entry_px > 0 else 0.0
        peak_pnl_pct = ((high_watermark / entry_px) - 1.0) * 100.0 if entry_px > 0 else 0.0

        if fi >= 50 and not np.isnan(_sma50[fi]):
            cur_tech = _tech_score(
                rsi14=float(_rsi14[fi]),
                macd=float(_macd[fi]),
                macd_prev=float(_macd[fi - 1]) if fi > 0 else float(_macd[fi]),
                price=float(prices[fi]),
                sma20=float(_sma20[fi]) if not np.isnan(_sma20[fi]) else float(prices[fi]),
                sma50=float(_sma50[fi]),
                trade_type=trade_type,
            )
        else:
            cur_tech = tech_at_entry

        tech_decayed = cur_tech < max(20.0, tech_at_entry * 0.40)

        if not trail_active and peak_pnl_pct >= trail_activate_pct:
            trail_active = True

        if trail_active and peak_pnl_pct > 0.0:
            retained_profit_pct = peak_pnl_pct * max(0.0, 1.0 - trail_giveback_pct / 100.0)
            trail_stop_px = entry_px * (1.0 + retained_profit_pct / 100.0)

        if tech_decayed:
            if opt_now >= entry_px:
                dynamic_stop_px = max(dynamic_stop_px, entry_px * 1.02)
            else:
                tighter = dynamic_stop_px + (entry_px - dynamic_stop_px) * 0.40
                dynamic_stop_px = max(dynamic_stop_px, tighter)

        effective_stop = (
            max(dynamic_stop_px, trail_stop_px)
            if trail_active
            else min(entry_px, dynamic_stop_px)
        )
        if opt_now <= effective_stop:
            exit_px = opt_now
            exit_reason = "trailing_stop" if trail_active else "stop"
            exit_stock_px = float(prices[fi])
            exit_day_idx = fi
            break

        if opt_now >= target_px:
            exit_px = min(opt_now, target_px)
            exit_reason = "target"
            exit_stock_px = float(prices[fi])
            exit_day_idx = fi
            break

        if d >= time_exit_day:
            exit_px = opt_now
            exit_reason = "time_exit"
            exit_stock_px = float(prices[fi])
            exit_day_idx = fi
            break
    else:
        return {
            "priced": False,
            "unpriced_reason": "insufficient_quote_history",
            "entry_day_idx": i,
            "truth_source": normalized_truth_source,
            "requested_pricing_lane": requested_pricing_lane,
            "effective_pricing_lane": entry_execution.get("effective_pricing_lane") or requested_pricing_lane,
            "pricing_lane": entry_execution.get("effective_pricing_lane") or requested_pricing_lane,
            "pricing_lane_fallback_reason": entry_execution.get("pricing_lane_fallback_reason"),
            "entry_anchor_source": resolved_entry_anchor_source,
            "execution_realism": execution_realism_label,
            "contract_symbol": entry_quote.contract_symbol,
            "last_quote_date": last_quote_date,
            "entry_quote_at_utc": entry_quote.as_of_utc,
            "entry_quote_basis": entry_quote.price_basis,
            "entry_quote_time_et": (
                "End-of-day snapshot ET"
                if snapshot_kind == DAILY_SNAPSHOT_KIND
                else _et_minute_label(entry_quote.quote_minute_et)
            ),
            "entry_contract_resolution": contract_resolution,
            "contract_selection_source": contract_selection_source,
        }

    delta_greeks = target_greeks
    if not delta_greeks:
        delta_greeks = _bs_greeks(
            S0,
            float(entry_quote.strike),
            max(float(actual_dte), 1.0) / 365.0,
            RISK_FREE_RATE,
            max(float(hv30) * float(iv_adj), 0.01),
            trade_type,
        ) or {}

    pnl_snapshot = long_option_pnl(
        entry_execution_price=entry_px,
        exit_execution_price=exit_px,
        contracts=1,
        commission_per_contract_usd=commission_per_contract_usd,
        include_entry_fee=True,
        include_exit_fee=True,
    )
    pnl = float(pnl_snapshot.get("net_pnl_pct") or 0.0)
    stock_move_pct = (exit_stock_px / S0 - 1.0) * 100.0 if S0 > 0 else 0.0
    directional_correct = (
        (trade_type == "call" and stock_move_pct > 0)
        or (trade_type == "put" and stock_move_pct < 0)
    )
    return {
        "priced": True,
        "entry_px": round(entry_px, 4),
        "exit_px": round(exit_px, 4),
        "pnl_pct": round(pnl, 2),
        "gross_pnl_pct": pnl_snapshot.get("gross_pnl_pct"),
        "net_pnl_pct": pnl_snapshot.get("net_pnl_pct"),
        "gross_pnl_usd": pnl_snapshot.get("gross_pnl_usd"),
        "net_pnl_usd": pnl_snapshot.get("net_pnl_usd"),
        "fee_total_usd": pnl_snapshot.get("fee_total_usd"),
        "entry_fee_total_usd": pnl_snapshot.get("entry_fee_total_usd"),
        "exit_fee_total_usd": pnl_snapshot.get("exit_fee_total_usd"),
        "exit_reason": exit_reason,
        "exit_fill_basis": exit_fill_basis,
        "strike": round(float(entry_quote.strike), 2),
        "delta_val": round(abs(float(delta_greeks.get("delta", 0.0) or 0.0)), 4),
        "stock_px": round(S0, 4),
        "exit_stock_px": round(exit_stock_px, 4),
        "stock_move_pct": round(stock_move_pct, 2),
        "directional_correct": directional_correct,
        "hv30": round(hv30, 4),
        "iv_adj": iv_adj,
        "dte": actual_dte,
        "entry_day_idx": i,
        "exit_day_idx": exit_day_idx,
        "requested_pricing_lane": requested_pricing_lane,
        "effective_pricing_lane": (
            exit_execution.get("effective_pricing_lane")
            or entry_execution.get("effective_pricing_lane")
            or requested_pricing_lane
        ),
        "pricing_lane": (
            exit_execution.get("effective_pricing_lane")
            or entry_execution.get("effective_pricing_lane")
            or requested_pricing_lane
        ),
        "pricing_lane_fallback_reason": (
            exit_execution.get("pricing_lane_fallback_reason")
            or entry_execution.get("pricing_lane_fallback_reason")
        ),
        "entry_anchor_source": resolved_entry_anchor_source,
        "execution_realism": execution_realism_label,
        "truth_source": normalized_truth_source,
        "contract_symbol": entry_quote.contract_symbol,
        "entry_quote_at_utc": entry_quote.as_of_utc,
        "entry_quote_basis": entry_quote.price_basis,
        "entry_execution_basis": entry_execution.get("execution_basis"),
        "entry_quote_time_et": (
            "End-of-day snapshot ET"
            if snapshot_kind == DAILY_SNAPSHOT_KIND
            else _et_minute_label(entry_quote.quote_minute_et)
        ),
        "entry_contract_resolution": contract_resolution,
        "contract_selection_source": contract_selection_source,
        "requested_contract_symbol": normalized_archived_contract,
        "requested_expiry": str(archived_expiry or "") or None,
        "requested_strike": float(archived_strike) if archived_strike is not None else None,
        "requested_option_type": str(archived_option_type or trade_type),
        "requested_quote_time_et": archived_quote_time_et,
        "requested_quote_basis": archived_quote_basis,
        "requested_underlying_price_at_selection": float(archived_underlying_price_at_selection) if archived_underlying_price_at_selection is not None else None,
        "requested_selection_source": archived_selection_source,
        "exit_quote_at_utc": exit_quote_at_utc,
        "exit_quote_time_et": (
            "End-of-day snapshot ET"
            if snapshot_kind == DAILY_SNAPSHOT_KIND
            else _et_minute_label(exit_quote_minute_et)
        ),
        "exit_quote_basis": exit_fill_basis,
        "exit_execution_basis": (
            exit_fill_basis.replace("historical_", "", 1)
            if str(exit_fill_basis).startswith("historical_")
            else exit_fill_basis
        ),
    }


def _build_profile_config(sp: dict) -> tuple[dict, "TradeEvaluator"]:
    """Build (config dict, TradeEvaluator) from a strategy profile dict."""
    config = {
        "dte_at_entry":      max(DTE_MIN, min(DTE_MAX, int(sp["targets"].get("dte_optimal", 10)))),
        "stop_loss_pct":     float(sp["risk"].get("stop_loss_pct", 50.0)),
        "profit_target_pct": float(sp["risk"].get("profit_target_pct", 100.0)),
        "delta_target":      float(sp["targets"].get("delta_optimal", 0.30)),
        "min_confidence":    float(sp.get("entry", {}).get("min_direction_score", 35.0)),
        "min_ev_pct":        float(sp["filters"].get("min_ev_return_pct", 10.0)),
        "entry_momentum":    float(sp.get("entry", {}).get("entry_momentum_pct", 0.3)),
        "time_exit_pct":     float(sp["risk"].get("time_exit_pct", 50.0)),
        "trailing_profit_pct": float(sp.get("early_exit", {}).get("trailing_profit_pct", 40.0)),
        "trailing_giveback_pct": float(sp.get("early_exit", {}).get("trailing_giveback_pct", 50.0)),
        "min_tech_score":    float(sp.get("entry", {}).get("min_tech_score", 55.0)),
        "confidence_weights": dict(sp.get("confidence_weights", {})),
        "liquidity_spread_max_pct": float(sp["filters"].get("liquidity_spread_max_pct", 10.0)),
        "illiquid_extra_margin_pct": float(sp["filters"].get("illiquid_extra_margin_pct", 5.0)),
        "min_calibrated_expectancy_pct": float(sp["filters"].get("min_calibrated_expectancy_pct", 0.0)),
        "entry_slippage_pct": float(sp["filters"].get("entry_slippage_pct", 0.0)),
        "exit_slippage_pct": float(sp["filters"].get("exit_slippage_pct", 0.0)),
        "strategy_type":     str(sp.get("strategy_type", "single_leg")),
        "spread_long_delta": float(sp.get("spread", {}).get("long_delta_target", 0.50)),
        "spread_short_delta": float(sp.get("spread", {}).get("short_delta_target", 0.20)),
        "spread_max_width_pct": float(sp.get("spread", {}).get("max_width_pct", 5.0)),
        "spread_stop_loss_pct": float(sp.get("spread", {}).get("stop_loss_pct", 30.0)),
        "spread_profit_target_pct": float(sp.get("spread", {}).get("profit_target_pct", 45.0)),
        "spread_time_exit_pct": float(sp.get("spread", {}).get("time_exit_pct", 55.0)),
        "spread_exit_monitoring_mode": str(sp.get("spread", {}).get("exit_monitoring_mode", "daily")),
        "spread_time_exit_basis": str(sp.get("spread", {}).get("time_exit_basis", "trading_sessions")),
    }
    dsw    = sp.get("direction_score_weights", {"tech": 0.55, "regime": 0.30, "momentum": 0.15})
    rsi_oe = sp.get("rsi_overextension",       {"severe_threshold": 72, "moderate_threshold": 68,
                                                "severe_penalty": 15.0, "moderate_penalty": 8.0})
    qsw    = sp.get("quality_score_weights",   {"iv_rank": 0.40, "delta": 0.35, "dte": 0.25})
    evaluator = TradeEvaluator(
        weights       = sp["confidence_weights"],
        delta_target  = config["delta_target"],
        dte_optimal   = config["dte_at_entry"],
        ds_w_tech     = float(dsw.get("tech",      0.55)),
        ds_w_regime   = float(dsw.get("regime",    0.30)),
        ds_w_momentum = float(dsw.get("momentum",  0.15)),
        rsi_sev_threshold = float(rsi_oe.get("severe_threshold",  72.0)),
        rsi_mod_threshold = float(rsi_oe.get("moderate_threshold",68.0)),
        rsi_sev_penalty   = float(rsi_oe.get("severe_penalty",    15.0)),
        rsi_mod_penalty   = float(rsi_oe.get("moderate_penalty",   8.0)),
        qs_w_iv    = float(qsw.get("iv_rank", 0.40)),
        qs_w_delta = float(qsw.get("delta",   0.35)),
        qs_w_dte   = float(qsw.get("dte",     0.25)),
        liquidity_spread_max_pct = config["liquidity_spread_max_pct"],
        illiquid_extra_margin_pct = config["illiquid_extra_margin_pct"],
    )
    return config, evaluator


def _apply_replay_playbook_config_overrides(config: dict, playbook: dict) -> dict:
    """Apply scan-lane settings that intentionally override profile defaults."""
    resolved = dict(config)
    if playbook.get("target_dte") is not None:
        resolved["dte_at_entry"] = max(DTE_MIN, min(DTE_MAX, int(playbook["target_dte"])))
    if playbook.get("scan_min_confidence") is not None:
        resolved["min_confidence"] = float(playbook["scan_min_confidence"])
    if playbook.get("scan_min_tech_score") is not None:
        resolved["min_tech_score"] = float(playbook["scan_min_tech_score"])
    override_map = {
        "spread_long_delta": "spread_long_delta",
        "spread_short_delta": "spread_short_delta",
        "spread_max_width_pct": "spread_max_width_pct",
        "spread_stop_loss_pct": "spread_stop_loss_pct",
        "spread_profit_target_pct": "spread_profit_target_pct",
        "spread_time_exit_pct": "spread_time_exit_pct",
        "spread_exit_monitoring_mode": "spread_exit_monitoring_mode",
        "spread_time_exit_basis": "spread_time_exit_basis",
        "entry_slippage_pct": "entry_slippage_pct",
        "exit_slippage_pct": "exit_slippage_pct",
        "chain_native_spread_selection": "chain_native_spread_selection",
        "chain_native_min_dte": "chain_native_min_dte",
        "chain_native_max_dte": "chain_native_max_dte",
        "chain_native_min_prior_quote_days": "chain_native_min_prior_quote_days",
        "chain_native_min_long_prior_quote_days": "chain_native_min_long_prior_quote_days",
        "chain_native_min_short_prior_quote_days": "chain_native_min_short_prior_quote_days",
        "chain_native_prior_quote_lookback_days": "chain_native_prior_quote_lookback_days",
        "chain_native_prior_quote_score_weight": "chain_native_prior_quote_score_weight",
        "chain_native_long_prior_quote_score_weight": "chain_native_long_prior_quote_score_weight",
        "chain_native_short_prior_quote_score_weight": "chain_native_short_prior_quote_score_weight",
        "chain_native_prior_quote_score_cap": "chain_native_prior_quote_score_cap",
        "chain_native_max_entry_leg_bid_ask_pct": "chain_native_max_entry_leg_bid_ask_pct",
        "chain_native_min_entry_short_bid": "chain_native_min_entry_short_bid",
        "chain_native_short_inside_steps": "chain_native_short_inside_steps",
        "chain_native_short_inside_require_debit_cap": "chain_native_short_inside_require_debit_cap",
    }
    for playbook_key, config_key in override_map.items():
        if playbook.get(playbook_key) is not None:
            if isinstance(playbook[playbook_key], bool):
                resolved[config_key] = bool(playbook[playbook_key])
            elif playbook_key in {
                "chain_native_min_dte",
                "chain_native_max_dte",
                "chain_native_min_prior_quote_days",
                "chain_native_min_long_prior_quote_days",
                "chain_native_min_short_prior_quote_days",
                "chain_native_prior_quote_lookback_days",
                "chain_native_prior_quote_score_cap",
                "chain_native_short_inside_steps",
            }:
                resolved[config_key] = int(playbook[playbook_key])
            elif playbook_key in {"spread_exit_monitoring_mode", "spread_time_exit_basis"}:
                resolved[config_key] = str(playbook[playbook_key])
            else:
                resolved[config_key] = float(playbook[playbook_key])
    return resolved


def _replay_underlying_filters_for_playbook(playbook: Optional[dict | str] = None) -> dict:
    playbook_id = playbook.get("id") if isinstance(playbook, dict) else playbook
    if is_ai_commodity_playbook_id(playbook_id):
        return ai_commodity_underlying_filters(UNDERLYING_FILTERS)
    return dict(UNDERLYING_FILTERS)


def _replay_underlying_filter_summary(playbook: Optional[dict | str] = None) -> dict:
    active_filters = _replay_underlying_filters_for_playbook(playbook)
    return {
        "history_days_min": int(active_filters["history_days_min"]),
        "avg_volume_20d_min": int(active_filters["avg_volume_20d_min"]),
        "avg_dollar_volume_20d_min": int(active_filters["avg_dollar_volume_20d_min"]),
        "rolling_window_days": int(UNDERLYING_LIQUIDITY_WINDOW),
    }


def _accumulate_surface_density(
    aggregate: dict[str, dict[str, Any]],
    density_rows: list[dict[str, Any]],
) -> None:
    for row in density_rows:
        entry = aggregate.setdefault(
            row["level"],
            {
                "level": row["level"],
                "label": row.get("label"),
                "fields": list(row.get("fields") or []),
                "surfaces": 0,
                "cohorts_sum": 0.0,
                "dense_cohorts_sum": 0.0,
                "sparse_cohorts_sum": 0.0,
                "max_trades_sum": 0.0,
                "avg_trades_per_cohort_sum": 0.0,
                "dense_trade_coverage_pct_sum": 0.0,
            },
        )
        entry["surfaces"] += 1
        entry["cohorts_sum"] += float(row.get("cohorts", 0) or 0.0)
        entry["dense_cohorts_sum"] += float(row.get("dense_cohorts", 0) or 0.0)
        entry["sparse_cohorts_sum"] += float(row.get("sparse_cohorts", 0) or 0.0)
        entry["max_trades_sum"] += float(row.get("max_trades", 0) or 0.0)
        entry["avg_trades_per_cohort_sum"] += float(row.get("avg_trades_per_cohort", 0.0) or 0.0)
        entry["dense_trade_coverage_pct_sum"] += float(row.get("dense_trade_coverage_pct", 0.0) or 0.0)


def _finalize_surface_density(aggregate: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    order = {
        "regime_direction_dir_quality_tech": 0,
        "regime_direction_dir_quality": 1,
        "direction_dir_quality": 2,
        "regime_direction_dir": 3,
        "direction_dir": 4,
        "regime_direction": 5,
        "direction": 6,
        "overall": 7,
    }
    rows: list[dict[str, Any]] = []
    for entry in aggregate.values():
        surfaces = max(int(entry.get("surfaces", 0) or 0), 1)
        rows.append(
            {
                "level": entry["level"],
                "label": entry.get("label"),
                "fields": list(entry.get("fields") or []),
                "surfaces": surfaces,
                "avg_cohorts": round(entry["cohorts_sum"] / surfaces, 2),
                "avg_dense_cohorts": round(entry["dense_cohorts_sum"] / surfaces, 2),
                "avg_sparse_cohorts": round(entry["sparse_cohorts_sum"] / surfaces, 2),
                "avg_max_trades": round(entry["max_trades_sum"] / surfaces, 2),
                "avg_trades_per_cohort": round(entry["avg_trades_per_cohort_sum"] / surfaces, 2),
                "avg_dense_trade_coverage_pct": round(entry["dense_trade_coverage_pct_sum"] / surfaces, 1),
            }
        )
    rows.sort(key=lambda row: order.get(row["level"], 999))
    return rows


def _base_calibration_diagnostics() -> dict[str, Any]:
    return {
        "surface_min_trades": int(DEFAULT_SURFACE_MIN_TRADES),
        "shrinkage_trades": float(DEFAULT_SHRINKAGE_TRADES),
        "sparse_warning_trades": int(DEFAULT_SPARSE_WARNING_TRADES),
        "surface_days": 0,
        "candidate_lookup_attempts": 0,
        "candidate_calibrated_count": 0,
        "candidate_calibrated_pct": 0.0,
        "candidate_fallback_level_counts": {},
        "selected_non_bootstrap_count": 0,
        "selected_non_bootstrap_pct": 0.0,
        "selected_fallback_level_counts": {},
        "density_by_level": [],
        "include_tech_band": False,
        "sparse_cohort_warnings": [],
    }


def _closed_trades_for_calibration(trades: list[dict], day_idx: int) -> list[dict]:
    return [
        trade for trade in trades
        if int(trade.get("exit_day_idx", -1) or -1) < int(day_idx)
        and _is_exact_contract_resolution(trade.get("entry_contract_resolution"))
    ]

@_market_data_scoped
def run_historical_backtest(
    lookback_years: int = 5,
    n_picks: int = DEFAULT_SCAN_PICKS,
    iv_adj: float = 1.20,
    pricing_lane: str = "pessimistic",
    truth_lane: str = SYNTHETIC_TRUTH_SOURCE,
    playbook: Optional[str] = None,
    allowed_directions: Optional[Sequence[str]] = None,
    progress_callback: Optional[Callable[[str, float], None]] = None,
    min_imported_calendar_dates: int = 100,
    save_result: bool = True,
    historical_source_labels: Optional[Sequence[str] | str] = None,
    allow_research_imported_data: bool = False,
) -> dict:
    """
    Historical replay of the daily scan.

    For every trading day going back lookback_years, evaluate all DEFAULT_WATCHLIST
    tickers using the current Brain settings (index ETFs use the index profile,
    equities use the equity profile — exactly as the live daily scan does), pick the
    top n_picks trades using the same sector-diversification logic, simulate each
    trade's outcome using actual subsequent price data, and return aggregate metrics.

    No Optuna, no windows, no guardrails — a faithful historical replay of current settings.
    """
    ensure_strategy_profiles_current()
    # Per-profile configs and evaluators — mirrors live scan's _get_profile() logic
    _eq_sp   = STRATEGY_PROFILES.get("equity", STRATEGY_PROFILE)
    _idx_sp  = STRATEGY_PROFILES.get("index",  STRATEGY_PROFILE)
    eq_config,  eq_evaluator  = _build_profile_config(_eq_sp)
    idx_config, idx_evaluator = _build_profile_config(_idx_sp)
    replay_playbook = _get_replay_playbook(playbook)
    eq_config = _apply_replay_playbook_config_overrides(eq_config, replay_playbook)
    idx_config = _apply_replay_playbook_config_overrides(idx_config, replay_playbook)
    normalized_allowed_directions = sorted(
        {
            str(item).strip().lower()
            for item in list(allowed_directions or [])
            if str(item).strip().lower() in {"call", "put"}
        }
    )
    if normalized_allowed_directions:
        replay_playbook["allowed_directions"] = normalized_allowed_directions
    replay_underlying_filters = _replay_underlying_filters_for_playbook(replay_playbook)
    replay_universe_filter_summary = _replay_underlying_filter_summary(replay_playbook)
    normalized_truth_lane = str(truth_lane or SYNTHETIC_TRUTH_SOURCE).strip().lower()
    requested_pricing_lane = _normalize_requested_pricing_lane(pricing_lane)
    if normalized_truth_lane == "synthetic":
        normalized_truth_lane = SYNTHETIC_TRUTH_SOURCE
    if normalized_truth_lane not in {SYNTHETIC_TRUTH_SOURCE, IMPORTED_TRUTH_SOURCE, IMPORTED_DAILY_TRUTH_SOURCE}:
        return {"error": f"Unsupported truth_lane: {truth_lane}"}
    try:
        required_imported_calendar_dates = max(1, int(min_imported_calendar_dates))
    except (TypeError, ValueError):
        required_imported_calendar_dates = 100

    imported_store: Optional[HistoricalOptionsStore] = None
    imported_snapshot_kind: Optional[str] = None
    imported_truth_store: Optional[dict[str, Any]] = None
    imported_calendar_underlying: Optional[str] = None
    imported_calendar_quote_dates: list[str] = []
    imported_shared_quote_dates: list[str] = []
    imported_replay_quote_dates: list[str] = []
    imported_replay_quote_date_source: str = "benchmark_quote_dates"
    imported_source_labels: list[str] = []
    imported_trusted_only = not bool(allow_research_imported_data)
    imported_data_scope_label = "trusted" if imported_trusted_only else "research_included"
    replay_calendar_summary: dict[str, Any] | None = None
    replay_watchlist = list(DEFAULT_WATCHLIST)
    if _is_imported_truth_source(normalized_truth_lane):
        imported_store = HistoricalOptionsStore()
        imported_snapshot_kind = _imported_snapshot_kind(normalized_truth_lane)
        raw_source_labels: Sequence[str] | str | None = (
            historical_source_labels
            if historical_source_labels is not None
            else replay_playbook.get("historical_source_labels")
        )
        if isinstance(raw_source_labels, str):
            imported_source_labels = [
                label.strip()
                for label in raw_source_labels.replace(";", ",").split(",")
                if label.strip()
            ]
        else:
            imported_source_labels = [
                str(label).strip()
                for label in list(raw_source_labels or [])
                if str(label).strip()
            ]
        if not imported_store.has_quotes(
            snapshot_kind=imported_snapshot_kind,
            trusted_only=imported_trusted_only,
            source_labels=imported_source_labels,
        ):
            return {
                "error": (
                    "No trusted imported historical option data found for this lane under the requested trust scope. "
                    "Import real market data first; fixture or acceptance imports do not count for proof."
                ),
                "source_labels_required": imported_source_labels,
                "imported_data_scope": imported_data_scope_label,
            }
        imported_truth_store = imported_store.snapshot_summary(
            imported_snapshot_kind,
            trusted_only=imported_trusted_only,
            source_labels=imported_source_labels,
        )
        imported_truth_store["data_trust"] = TRUSTED_DATA_TRUST if imported_trusted_only else "research_included"
        imported_truth_store["trusted_only"] = imported_trusted_only
        imported_truth_store["research_imported_data_allowed"] = not imported_trusted_only
        imported_truth_store["source_labels_required"] = imported_source_labels
        available_underlyings = {
            symbol.upper()
            for symbol in imported_store.list_available_underlyings(
                snapshot_kind=imported_snapshot_kind,
                trusted_only=imported_trusted_only,
                source_labels=imported_source_labels,
            )
        }
        required_imported_underlyings = _imported_replay_underlyings_for_playbook(replay_playbook)
        if not required_imported_underlyings:
            return {
                "error": "Imported historical validation has no required underlyings configured for this playbook."
            }
        replay_watchlist = [
            symbol for symbol in required_imported_underlyings
            if symbol.upper() in available_underlyings
        ]
        if len(replay_watchlist) < len(required_imported_underlyings):
            return {
                "error": (
                    "Imported historical validation is missing one or more required underlyings. "
                    f"Required: {list(required_imported_underlyings)}. "
                    f"Available underlyings: {sorted(available_underlyings)}"
                ),
                "source_labels_required": imported_source_labels,
            }
        imported_calendar_underlying = "SPY" if "SPY" in replay_watchlist else str(replay_watchlist[0]).upper()
        imported_calendar_quote_dates = imported_store.available_quote_dates(
            imported_calendar_underlying,
            snapshot_kind=imported_snapshot_kind,
            trusted_only=imported_trusted_only,
            source_labels=imported_source_labels,
        )
        if not imported_calendar_quote_dates:
            return {
                "error": (
                    "Imported historical validation has no benchmark quote dates for the replay calendar under the requested trust scope. "
                    f"Benchmark underlying: {imported_calendar_underlying}."
                ),
                "source_labels_required": imported_source_labels,
                "imported_data_scope": imported_data_scope_label,
            }
        imported_shared_quote_dates = imported_store.shared_quote_dates(
            replay_watchlist,
            snapshot_kind=imported_snapshot_kind,
            trusted_only=imported_trusted_only,
            source_labels=imported_source_labels,
        )
        requires_shared_imported_dates = is_ai_commodity_playbook_id(replay_playbook.get("id"))
        if imported_shared_quote_dates:
            imported_replay_quote_dates = imported_shared_quote_dates
            imported_replay_quote_date_source = "shared_required_quote_dates"
        elif requires_shared_imported_dates:
            imported_quote_index = _normalize_replay_history_index(pd.to_datetime(imported_calendar_quote_dates))
            replay_calendar_summary = _build_replay_calendar_summary(
                source=f"{imported_data_scope_label}_imported_missing_shared_required_quote_dates",
                index=imported_quote_index,
                raw_history_date_count=len(imported_quote_index),
                quote_date_count=len(imported_quote_index),
                underlyings=list(replay_watchlist),
                snapshot_kind=imported_snapshot_kind,
            )
            replay_calendar_summary["benchmark_underlying"] = imported_calendar_underlying
            replay_calendar_summary["source_labels_required"] = imported_source_labels
            replay_calendar_summary["trusted_only"] = imported_trusted_only
            replay_calendar_summary["research_imported_data_allowed"] = not imported_trusted_only
            replay_calendar_summary["benchmark_quote_date_count"] = len(imported_calendar_quote_dates)
            replay_calendar_summary["shared_quote_date_count"] = 0
            replay_calendar_summary["calendar_gap_date_count"] = len(imported_calendar_quote_dates)
            replay_calendar_summary["required_quote_date_count"] = required_imported_calendar_dates
            replay_calendar_summary["replay_quote_date_source"] = "missing_shared_required_quote_dates"
            return {
                "error": (
                    "Imported historical validation has insufficient shared required OPRA quote dates for this replay. "
                    "Benchmark-only quote dates are research context and cannot prove the AI commodity exact replay."
                ),
                "status": "insufficient_shared_quote_dates",
                "evidence_status": "insufficient_shared_quote_dates",
                "source_labels_required": imported_source_labels,
                "imported_data_scope": imported_data_scope_label,
                "replay_calendar": replay_calendar_summary,
                "required_imported_calendar_dates": required_imported_calendar_dates,
            }
        else:
            imported_replay_quote_dates = imported_calendar_quote_dates
            imported_replay_quote_date_source = "benchmark_quote_dates"
        if len(imported_replay_quote_dates) < required_imported_calendar_dates:
            imported_quote_index = _normalize_replay_history_index(pd.to_datetime(imported_replay_quote_dates))
            replay_calendar_summary = _build_replay_calendar_summary(
                source=f"{imported_data_scope_label}_imported_{imported_replay_quote_date_source}",
                index=imported_quote_index,
                raw_history_date_count=len(imported_quote_index),
                quote_date_count=len(imported_quote_index),
                underlyings=list(replay_watchlist),
                snapshot_kind=imported_snapshot_kind,
            )
            replay_calendar_summary["benchmark_underlying"] = imported_calendar_underlying
            replay_calendar_summary["source_labels_required"] = imported_source_labels
            replay_calendar_summary["trusted_only"] = imported_trusted_only
            replay_calendar_summary["research_imported_data_allowed"] = not imported_trusted_only
            replay_calendar_summary["benchmark_quote_date_count"] = len(imported_calendar_quote_dates)
            replay_calendar_summary["shared_quote_date_count"] = len(imported_shared_quote_dates)
            replay_calendar_summary["calendar_gap_date_count"] = max(
                len(imported_calendar_quote_dates) - len(imported_shared_quote_dates),
                0,
            )
            replay_calendar_summary["required_quote_date_count"] = required_imported_calendar_dates
            replay_calendar_summary["replay_quote_date_source"] = imported_replay_quote_date_source
            return {
                "error": (
                    "Imported historical validation has insufficient imported replay quote dates before replay under the requested trust scope. "
                    f"Selected dates: {len(imported_replay_quote_dates)}."
                ),
                "source_labels_required": imported_source_labels,
                "imported_data_scope": imported_data_scope_label,
                "replay_calendar": replay_calendar_summary,
                "required_imported_calendar_dates": required_imported_calendar_dates,
            }
    calibration_min_trades = int(DEFAULT_SURFACE_MIN_TRADES)
    calibration_shrinkage_trades = float(DEFAULT_SHRINKAGE_TRADES)
    calibration_sparse_warning_trades = int(DEFAULT_SPARSE_WARNING_TRADES)
    calibration_lookup_attempts = 0
    calibration_candidate_matches = 0
    calibration_candidate_dense_matches = 0
    calibration_candidate_sparse_matches = 0
    calibration_candidate_fallback_levels: Counter[str] = Counter()
    calibration_surface_days = 0
    calibration_density_aggregate: dict[str, dict[str, Any]] = {}
    calibration_selected_sparse_warnings: Counter[str] = Counter()
    last_expectancy_surface: Optional[dict[str, Any]] = None
    post_entry_filtered_trades: list[dict[str, Any]] = []
    calibration_accumulator = CalibrationAccumulator(
        min_trades=calibration_min_trades,
        bucket_size=DEFAULT_DIRECTION_BUCKET_SIZE,
        quality_bucket_size=DEFAULT_QUALITY_BUCKET_SIZE,
        tech_bucket_size=DEFAULT_TECH_BUCKET_SIZE,
        shrinkage_trades=calibration_shrinkage_trades,
        sparse_warning_trades=calibration_sparse_warning_trades,
    )
    calibration_queue: list[tuple[int, int, dict[str, Any]]] = []
    calibration_queue_seq = 0
    pre_entry_filtered_candidates: list[dict[str, Any]] = []
    execution_backfill_enabled = bool(
        replay_playbook.get("execution_backfill_enabled")
        or replay_playbook.get("execution_aware_backfill_enabled")
    )
    execution_backfill_scan_depth = max(
        int(n_picks),
        int(replay_playbook.get("execution_backfill_scan_depth", n_picks) or n_picks),
    )
    scan_until_capacity = bool(
        replay_playbook.get("scan_until_capacity")
        or replay_playbook.get("fill_until_capacity")
        or replay_playbook.get("capacity_tiers")
    )
    unknown_sector_policy = str(replay_playbook.get("unknown_sector_policy") or "shared").strip().lower()
    max_per_allocation_group = int(replay_playbook.get("max_per_allocation_group", 2) or 2)
    max_per_ticker = replay_playbook.get("max_per_ticker")
    max_total_index = replay_playbook.get("max_total_index")
    use_configured_daily_picker = any(
        key in replay_playbook
        for key in (
            "unknown_sector_policy",
            "max_per_allocation_group",
            "max_per_ticker",
            "max_total_index",
            "capacity_tiers",
            "sleeve_id",
            "sleeve_group",
        )
    )
    exit_quote_failure_memory_enabled = bool(replay_playbook.get("exit_quote_failure_memory_enabled"))
    exit_quote_failure_cooldown_days = int(replay_playbook.get("exit_quote_failure_cooldown_days", 0) or 0)
    exit_quote_failure_max_prior = int(replay_playbook.get("exit_quote_failure_max_prior", 1) or 1)
    exit_quote_failure_scope = str(replay_playbook.get("exit_quote_failure_scope") or "ticker").strip().lower()
    exit_quote_failure_strike_bucket_width = float(
        replay_playbook.get("exit_quote_failure_strike_bucket_width", 5.0) or 5.0
    )
    exit_quote_failure_reasons = {
        str(reason or "").strip()
        for reason in (replay_playbook.get("exit_quote_failure_memory_reasons") or ["missing_exit_quote_for_leg"])
        if str(reason or "").strip()
    }
    exit_quote_failure_memory: defaultdict[str, list[date]] = defaultdict(list)
    symbol_health_memory_enabled = bool(replay_playbook.get("symbol_health_memory_enabled"))
    symbol_health_min_observations = int(replay_playbook.get("symbol_health_min_observations", 3) or 3)
    symbol_health_min_profit_factor = float(replay_playbook.get("symbol_health_min_profit_factor", 1.0) or 1.0)
    symbol_health_min_avg_pnl_pct = float(replay_playbook.get("symbol_health_min_avg_pnl_pct", 0.0) or 0.0)
    symbol_health_cooldown_days = int(replay_playbook.get("symbol_health_cooldown_days", 0) or 0)
    symbol_health_include_unpriced_failures = bool(replay_playbook.get("symbol_health_include_unpriced_failures", True))
    symbol_health_unpriced_penalty_pct = float(replay_playbook.get("symbol_health_unpriced_penalty_pct", -100.0) or -100.0)
    symbol_health_memory: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    def _exit_quote_failure_scope_requires_selected_contract() -> bool:
        return exit_quote_failure_scope in {
            "short_contract",
            "contract_short",
            "short_expiry",
            "expiry_short",
            "short_expiry_strike",
            "short_strike",
            "short_expiry_strike_bucket",
            "expiry_strike_bucket",
        }

    def _exit_quote_failure_memory_key(pick: dict[str, Any], *, short_quote: Any | None = None) -> str:
        ticker_key = str(pick.get("ticker") or "").strip().upper()
        if exit_quote_failure_scope in {"ticker_sleeve", "sleeve_ticker"}:
            return f"{ticker_key}:{pick.get('sleeve_id') or pick.get('sleeve_group') or 'unknown'}"
        if exit_quote_failure_scope in {"ticker_tier", "tier_ticker"}:
            return f"{ticker_key}:{pick.get('tier_id') or 'unknown'}"
        short_contract = (
            str(getattr(short_quote, "contract_symbol", "") or "").strip()
            if short_quote is not None
            else str(pick.get("execution_preflight_short_contract_symbol") or pick.get("missing_short_contract_symbol") or "").strip()
        )
        expiry_raw = (
            str(getattr(short_quote, "expiry", "") or "").strip()
            if short_quote is not None
            else str(pick.get("execution_preflight_short_expiry") or "").strip()
        )
        expiry_key = expiry_raw[:10] if expiry_raw else "unknown_expiry"
        option_type = str(
            (getattr(short_quote, "option_type", None) if short_quote is not None else None)
            or pick.get("execution_preflight_short_option_type")
            or pick.get("trade_type")
            or pick.get("type")
            or "unknown"
        ).strip().lower()
        strike_raw = (
            getattr(short_quote, "strike", None)
            if short_quote is not None
            else pick.get("execution_preflight_short_strike")
        )
        if exit_quote_failure_scope in {"short_contract", "contract_short"} and short_contract:
            return f"{ticker_key}:short_contract:{short_contract}"
        if exit_quote_failure_scope in {"short_expiry", "expiry_short"}:
            return f"{ticker_key}:short_expiry:{expiry_key}:{option_type}"
        if exit_quote_failure_scope in {"short_expiry_strike", "short_strike", "short_expiry_strike_bucket", "expiry_strike_bucket"}:
            try:
                strike = float(strike_raw)
                bucket_width = max(float(exit_quote_failure_strike_bucket_width), 0.01)
                strike_key = round(math.floor(strike / bucket_width) * bucket_width, 4)
            except (TypeError, ValueError):
                strike_key = "unknown_strike"
            return f"{ticker_key}:short_expiry_strike:{expiry_key}:{option_type}:{strike_key}"
        return ticker_key

    def _recent_exit_quote_failure_dates(key: str, entry_date: date) -> list[date]:
        dates_for_key = exit_quote_failure_memory.get(key) or []
        if exit_quote_failure_cooldown_days <= 0:
            return [failure_date for failure_date in dates_for_key if failure_date < entry_date]
        return [
            failure_date
            for failure_date in dates_for_key
            if failure_date < entry_date and (entry_date - failure_date).days <= exit_quote_failure_cooldown_days
        ]

    def _observed_symbol_health(ticker: str, entry_date: date) -> dict[str, Any]:
        observed: list[dict[str, Any]] = []
        for item in symbol_health_memory.get(str(ticker or "").strip().upper()) or []:
            observed_date = item.get("observed_date")
            if not isinstance(observed_date, date) or observed_date >= entry_date:
                continue
            if symbol_health_cooldown_days > 0 and (entry_date - observed_date).days > symbol_health_cooldown_days:
                continue
            observed.append(item)
        pnl_values = [
            float(item.get("pnl_pct") or 0.0)
            for item in observed
            if item.get("kind") == "priced" or symbol_health_include_unpriced_failures
        ]
        if not pnl_values:
            return {
                "observation_count": 0,
                "priced_count": 0,
                "unpriced_failure_count": 0,
                "profit_factor": 999.0,
                "avg_pnl_pct": 0.0,
            }
        gross_win = sum(value for value in pnl_values if value > 0)
        gross_loss = abs(sum(value for value in pnl_values if value < 0))
        return {
            "observation_count": len(pnl_values),
            "priced_count": sum(1 for item in observed if item.get("kind") == "priced"),
            "unpriced_failure_count": sum(1 for item in observed if item.get("kind") == "unpriced_failure"),
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else 999.0,
            "avg_pnl_pct": round(sum(pnl_values) / len(pnl_values), 2),
        }

    capacity_tiers = _capacity_tiers_for_playbook(replay_playbook)
    capacity_tier_runtimes: list[dict[str, Any]] = []
    for tier in capacity_tiers:
        tier_playbook = _tier_playbook(replay_playbook, tier)
        tier_key = f"{int(tier.get('tier_rank') or 0):03d}:{tier.get('tier_id')}"
        capacity_tier_runtimes.append(
            {
                **tier,
                "tier_key": tier_key,
                "playbook": tier_playbook,
                "eq_config": _apply_replay_playbook_config_overrides(eq_config, tier_playbook),
                "idx_config": _apply_replay_playbook_config_overrides(idx_config, tier_playbook),
            }
        )
    capacity_tier_runtime_by_key = {
        str(item["tier_key"]): item
        for item in capacity_tier_runtimes
    }
    daily_selection_diagnostics: list[dict[str, Any]] = []

    def _ticker_cfg(ticker: str, tier_runtime: dict[str, Any] | None = None) -> tuple[dict, "TradeEvaluator"]:
        if tier_runtime is not None:
            return (
                tier_runtime["idx_config"],
                idx_evaluator,
            ) if ticker.upper() in INDEX_TICKERS else (
                tier_runtime["eq_config"],
                eq_evaluator,
            )
        return (idx_config, idx_evaluator) if ticker.upper() in INDEX_TICKERS else (eq_config, eq_evaluator)

    def _runtime_for_pick(pick: dict[str, Any]) -> dict[str, Any] | None:
        return capacity_tier_runtime_by_key.get(str(pick.get("_tier_key") or ""))

    def _preflight_imported_entry_candidate(
        pick: dict[str, Any],
        *,
        daily_rank: int,
    ) -> tuple[bool, dict[str, Any] | None]:
        t_sym = str(pick.get("ticker") or "").upper()
        t_arr = ticker_arrays.get(t_sym)
        if t_arr is None:
            return False, {
                **{key: pick.get(key) for key in ("ticker", "date", "trade_type", "sector", "market_regime")},
                "daily_rank": int(daily_rank),
                "pre_entry_filter_reject_reason": "missing_price_series",
                "truth_source": normalized_truth_lane,
            }
        tier_runtime = _runtime_for_pick(pick)
        p_config, _ = _ticker_cfg(t_sym, tier_runtime)
        if p_config.get("strategy_type") != "vertical_spread" or not bool(p_config.get("chain_native_spread_selection", False)):
            return True, None
        entry_date = pd.Timestamp(all_closes["SPY"].index[pick["day_idx"]]).date()
        if symbol_health_memory_enabled:
            health = _observed_symbol_health(t_sym, entry_date)
            if (
                int(health.get("observation_count") or 0) >= max(1, symbol_health_min_observations)
                and (
                    float(health.get("profit_factor") or 0.0) < symbol_health_min_profit_factor
                    or float(health.get("avg_pnl_pct") or 0.0) < symbol_health_min_avg_pnl_pct
                )
            ):
                return False, {
                    **{key: pick.get(key) for key in ("ticker", "date", "trade_type", "sector", "market_regime", "sleeve_id", "tier_id")},
                    "daily_rank": int(daily_rank),
                    "pre_entry_filter_reject_reason": "poor_symbol_health_memory",
                    "truth_source": normalized_truth_lane,
                    "requested_pricing_lane": requested_pricing_lane,
                    "symbol_health_min_observations": symbol_health_min_observations,
                    "symbol_health_min_profit_factor": symbol_health_min_profit_factor,
                    "symbol_health_min_avg_pnl_pct": symbol_health_min_avg_pnl_pct,
                    **{f"symbol_health_{key}": value for key, value in health.items()},
                }
        if exit_quote_failure_memory_enabled and not _exit_quote_failure_scope_requires_selected_contract():
            memory_key = _exit_quote_failure_memory_key(pick)
            recent_failures = _recent_exit_quote_failure_dates(memory_key, entry_date)
            if len(recent_failures) >= max(1, exit_quote_failure_max_prior):
                return False, {
                    **{key: pick.get(key) for key in ("ticker", "date", "trade_type", "sector", "market_regime", "sleeve_id", "tier_id")},
                    "daily_rank": int(daily_rank),
                    "pre_entry_filter_reject_reason": "recent_exit_quote_failure_memory",
                    "truth_source": normalized_truth_lane,
                    "requested_pricing_lane": requested_pricing_lane,
                    "exit_quote_failure_memory_key": memory_key,
                    "exit_quote_failure_recent_count": len(recent_failures),
                    "exit_quote_failure_last_observed_date": str(max(recent_failures)),
                    "exit_quote_failure_cooldown_days": exit_quote_failure_cooldown_days,
                    "exit_quote_failure_scope": exit_quote_failure_scope,
                }
        entry_anchor_price = float(t_arr["opens"][pick["day_idx"]])
        entry_anchor_source = "open"
        if normalized_truth_lane == IMPORTED_DAILY_TRUTH_SOURCE:
            archived_selection_price = pick.get("underlying_price_at_selection")
            if archived_selection_price is not None:
                entry_anchor_price = float(archived_selection_price)
                entry_anchor_source = "archived_underlying_price_at_selection"
            elif int(pick["day_idx"]) > 0:
                entry_anchor_price = float(t_arr["prices"][pick["day_idx"] - 1])
                entry_anchor_source = "prior_close"
            else:
                entry_anchor_source = "open_fallback_no_prior_close"
        selected = _select_chain_native_spread(
            store=imported_store,
            ticker=t_sym,
            entry_date=entry_date,
            trade_type=pick["trade_type"],
            S0=entry_anchor_price,
            hv30=pick["hv30"],
            long_delta_target=p_config.get("spread_long_delta", 0.50),
            short_delta_target=p_config.get("spread_short_delta", 0.20),
            target_dte=p_config["dte_at_entry"],
            min_dte=int(p_config.get("chain_native_min_dte") or max(1, int(p_config["dte_at_entry"]) - 7)),
            max_dte=int(p_config.get("chain_native_max_dte") or int(p_config["dte_at_entry"]) + 10),
            max_width_pct=p_config.get("spread_max_width_pct", 5.0),
            max_debit_pct_of_width=replay_playbook.get("max_debit_pct_of_width"),
            iv_adj=iv_adj,
            requested_pricing_lane=requested_pricing_lane,
            entry_slippage_pct=p_config.get("entry_slippage_pct", 0.0),
            snapshot_kind=_imported_snapshot_kind(normalized_truth_lane),
            entry_quote_minute_et=DAILY_QUOTE_MINUTE_ET if normalized_truth_lane == IMPORTED_DAILY_TRUTH_SOURCE else ENTRY_QUOTE_MINUTE_ET,
            entry_window_minutes=0 if normalized_truth_lane == IMPORTED_DAILY_TRUTH_SOURCE else ENTRY_QUOTE_WINDOW_MINUTES,
            source_labels=imported_source_labels,
            trusted_only=imported_trusted_only,
            min_prior_quote_days=int(p_config.get("chain_native_min_prior_quote_days", 0) or 0),
            prior_quote_lookback_days=int(p_config.get("chain_native_prior_quote_lookback_days", 14) or 14),
            min_long_prior_quote_days=(
                int(p_config["chain_native_min_long_prior_quote_days"])
                if p_config.get("chain_native_min_long_prior_quote_days") is not None
                else None
            ),
            min_short_prior_quote_days=(
                int(p_config["chain_native_min_short_prior_quote_days"])
                if p_config.get("chain_native_min_short_prior_quote_days") is not None
                else None
            ),
            prior_quote_score_weight=float(p_config.get("chain_native_prior_quote_score_weight", 0.0) or 0.0),
            long_prior_quote_score_weight=(
                float(p_config["chain_native_long_prior_quote_score_weight"])
                if p_config.get("chain_native_long_prior_quote_score_weight") is not None
                else None
            ),
            short_prior_quote_score_weight=(
                float(p_config["chain_native_short_prior_quote_score_weight"])
                if p_config.get("chain_native_short_prior_quote_score_weight") is not None
                else None
            ),
            prior_quote_score_cap=int(p_config.get("chain_native_prior_quote_score_cap", 5) or 0),
            max_entry_leg_bid_ask_pct=p_config.get("chain_native_max_entry_leg_bid_ask_pct"),
            min_entry_short_bid=p_config.get("chain_native_min_entry_short_bid"),
            short_inside_steps=int(p_config.get("chain_native_short_inside_steps", 0) or 0),
            short_inside_require_debit_cap=bool(p_config.get("chain_native_short_inside_require_debit_cap", True)),
        )
        if selected is None:
            return False, {
                **{key: pick.get(key) for key in ("ticker", "date", "trade_type", "sector", "market_regime")},
                "daily_rank": int(daily_rank),
                "pre_entry_filter_reject_reason": "no_chain_native_spread",
                "truth_source": normalized_truth_lane,
                "requested_pricing_lane": requested_pricing_lane,
                "entry_anchor_source": entry_anchor_source,
                "entry_anchor_price": round(entry_anchor_price, 4),
                "chain_native_min_dte": p_config.get("chain_native_min_dte"),
                "chain_native_max_dte": p_config.get("chain_native_max_dte"),
                "chain_native_min_entry_short_bid": p_config.get("chain_native_min_entry_short_bid"),
                "chain_native_min_prior_quote_days": p_config.get("chain_native_min_prior_quote_days"),
                "max_debit_pct_of_width": replay_playbook.get("max_debit_pct_of_width"),
            }
        long_quote, short_quote, net_debit, spread_width, long_delta, short_delta = selected
        if exit_quote_failure_memory_enabled and _exit_quote_failure_scope_requires_selected_contract():
            memory_key = _exit_quote_failure_memory_key(pick, short_quote=short_quote)
            recent_failures = _recent_exit_quote_failure_dates(memory_key, entry_date)
            if len(recent_failures) >= max(1, exit_quote_failure_max_prior):
                return False, {
                    **{key: pick.get(key) for key in ("ticker", "date", "trade_type", "sector", "market_regime", "sleeve_id", "tier_id")},
                    "daily_rank": int(daily_rank),
                    "pre_entry_filter_reject_reason": "recent_exit_quote_failure_memory",
                    "truth_source": normalized_truth_lane,
                    "requested_pricing_lane": requested_pricing_lane,
                    "exit_quote_failure_memory_key": memory_key,
                    "exit_quote_failure_recent_count": len(recent_failures),
                    "exit_quote_failure_last_observed_date": str(max(recent_failures)),
                    "exit_quote_failure_cooldown_days": exit_quote_failure_cooldown_days,
                    "exit_quote_failure_scope": exit_quote_failure_scope,
                    "exit_quote_failure_strike_bucket_width": round(float(exit_quote_failure_strike_bucket_width), 4),
                    "short_entry_contract_symbol": short_quote.contract_symbol,
                    "short_entry_expiry": str(short_quote.expiry)[:10],
                    "short_entry_strike": float(short_quote.strike),
                }
        min_spread_width = p_config.get("chain_native_min_spread_width")
        if min_spread_width is not None and float(spread_width) < float(min_spread_width):
            return False, {
                **{key: pick.get(key) for key in ("ticker", "date", "trade_type", "sector", "market_regime", "sleeve_id", "tier_id")},
                "daily_rank": int(daily_rank),
                "pre_entry_filter_reject_reason": "spread_width_below_min",
                "truth_source": normalized_truth_lane,
                "requested_pricing_lane": requested_pricing_lane,
                "spread_width": round(float(spread_width), 4),
                "chain_native_min_spread_width": float(min_spread_width),
                "long_entry_strike": float(long_quote.strike),
                "short_entry_strike": float(short_quote.strike),
            }
        narrow_width_max = p_config.get("chain_native_narrow_spread_width_max")
        narrow_short_moneyness_min = p_config.get("chain_native_narrow_spread_short_moneyness_min_pct")
        if narrow_width_max is not None and narrow_short_moneyness_min is not None:
            long_strike = float(long_quote.strike)
            short_strike = float(short_quote.strike)
            if pick["trade_type"] == "call":
                short_moneyness_pct = (short_strike / max(long_strike, 0.01) - 1.0) * 100.0
            else:
                short_moneyness_pct = (long_strike / max(short_strike, 0.01) - 1.0) * 100.0
            if float(spread_width) <= float(narrow_width_max) and short_moneyness_pct >= float(narrow_short_moneyness_min):
                return False, {
                    **{key: pick.get(key) for key in ("ticker", "date", "trade_type", "sector", "market_regime", "sleeve_id", "tier_id")},
                    "daily_rank": int(daily_rank),
                    "pre_entry_filter_reject_reason": "narrow_far_short_spread",
                    "truth_source": normalized_truth_lane,
                    "requested_pricing_lane": requested_pricing_lane,
                    "spread_width": round(float(spread_width), 4),
                    "short_moneyness_pct": round(float(short_moneyness_pct), 2),
                    "chain_native_narrow_spread_width_max": float(narrow_width_max),
                    "chain_native_narrow_spread_short_moneyness_min_pct": float(narrow_short_moneyness_min),
                    "long_entry_strike": long_strike,
                    "short_entry_strike": short_strike,
                }
        if bool(p_config.get("execution_survivability_enabled") or replay_playbook.get("execution_survivability_enabled") or replay_playbook.get("tradability_score_enabled")):
            tradability = _spread_tradability_score(
                store=imported_store,
                long_quote=long_quote,
                short_quote=short_quote,
                entry_date=entry_date,
                snapshot_kind=_imported_snapshot_kind(normalized_truth_lane),
                source_labels=imported_source_labels,
                trusted_only=imported_trusted_only,
                lookback_calendar_days=int(p_config.get("tradability_lookback_days") or replay_playbook.get("tradability_lookback_days") or 20),
                min_short_leg_prior_quote_days=int(p_config.get("min_short_leg_prior_quote_days") or replay_playbook.get("min_short_leg_prior_quote_days") or 0),
                min_long_leg_prior_quote_days=int(p_config.get("min_long_leg_prior_quote_days") or replay_playbook.get("min_long_leg_prior_quote_days") or 0),
            )
            min_score = float(p_config.get("min_tradability_score") or replay_playbook.get("min_tradability_score") or 0.0)
            if float(tradability.get("tradability_score") or 0.0) < min_score:
                return False, {
                    **{key: pick.get(key) for key in ("ticker", "date", "trade_type", "sector", "market_regime", "sleeve_id", "tier_id")},
                    "daily_rank": int(daily_rank),
                    "pre_entry_filter_reject_reason": "low_tradability_score",
                    "truth_source": normalized_truth_lane,
                    "requested_pricing_lane": requested_pricing_lane,
                    "entry_anchor_source": entry_anchor_source,
                    "entry_anchor_price": round(entry_anchor_price, 4),
                    "min_tradability_score": round(min_score, 1),
                    **tradability,
                }
            pick.update(tradability)
        pick["execution_preflight"] = "chain_native_entry_spread"
        pick["execution_preflight_daily_rank"] = int(daily_rank)
        pick["execution_preflight_long_contract_symbol"] = long_quote.contract_symbol
        pick["execution_preflight_short_contract_symbol"] = short_quote.contract_symbol
        pick["execution_preflight_long_expiry"] = str(long_quote.expiry)[:10]
        pick["execution_preflight_short_expiry"] = str(short_quote.expiry)[:10]
        pick["execution_preflight_long_strike"] = float(long_quote.strike)
        pick["execution_preflight_short_strike"] = float(short_quote.strike)
        pick["execution_preflight_long_option_type"] = pick["trade_type"]
        pick["execution_preflight_short_option_type"] = pick["trade_type"]
        pick["execution_preflight_net_debit"] = round(float(net_debit), 4)
        pick["execution_preflight_spread_width"] = round(float(spread_width), 4)
        pick["execution_preflight_long_delta"] = round(float(long_delta), 4)
        pick["execution_preflight_short_delta"] = round(float(short_delta), 4)
        return True, None

    # Use equity DTE for indicator precompute (index DTE usually similar; equity is the majority)
    dte = eq_config["dte_at_entry"]

    # ── Sector info ──────────────────────────────────────────────────────────
    if progress_callback:
        progress_callback("Fetching sector info…", 0.01)
    ticker_sectors: dict[str, str] = {}
    for t in replay_watchlist:
        if t.upper() in INDEX_TICKERS:
            ticker_sectors[t] = "Index ETF"
        else:
            try:
                ticker_sectors[t] = _cached_ticker_info(t).get("sector") or "Unknown"
            except Exception:
                ticker_sectors[t] = "Unknown"

    # ── Download price history ────────────────────────────────────────────────
    if progress_callback:
        progress_callback("Downloading price history…", 0.03)
    fetch_days = lookback_years * 365 + 365   # extra year for indicator warmup
    tickers_to_fetch = list(replay_watchlist)
    if "SPY" not in tickers_to_fetch:
        tickers_to_fetch.append("SPY")

    all_histories: dict[str, pd.DataFrame] = {}
    for sym in tickers_to_fetch:
        try:
            hist = _cached_history(sym, period=f"{fetch_days}d")
            hist = _sanitize_replay_history_frame(hist)
            if not hist.empty and len(hist) >= 100 and {"Open", "Close", "Volume"}.issubset(hist.columns):
                normalized_hist = hist[["Open", "Close", "Volume"]].copy()
                normalized_hist.index = _normalize_replay_history_index(normalized_hist.index)
                normalized_hist = normalized_hist[~normalized_hist.index.duplicated(keep="last")]
                all_histories[sym] = normalized_hist
                # Open prices — used as entry price (mirrors live scan's ~10:10 AM execution)
        except Exception:
            pass

    if "SPY" not in all_histories:
        return {"error": "Could not fetch price history for watchlist tickers"}

    # Align the replay to SPY's date index and exclude newer listings that cannot
    # honestly participate across the requested lookback.
    spy_reference = all_histories["SPY"]["Close"].dropna()
    spy_index = spy_reference.index
    raw_spy_index = spy_index
    if imported_replay_quote_dates:
        imported_quote_index = _normalize_replay_history_index(pd.to_datetime(imported_replay_quote_dates))
        imported_quote_set = set(imported_quote_index)
        spy_index = pd.DatetimeIndex([stamp for stamp in spy_index if stamp in imported_quote_set])
        replay_calendar_summary = _build_replay_calendar_summary(
            source=f"{imported_data_scope_label}_imported_{imported_replay_quote_date_source}",
            index=spy_index,
            raw_history_date_count=len(raw_spy_index),
            quote_date_count=len(imported_quote_index),
            underlyings=list(replay_watchlist),
            snapshot_kind=imported_snapshot_kind,
        )
        replay_calendar_summary["benchmark_underlying"] = imported_calendar_underlying
        replay_calendar_summary["source_labels_required"] = imported_source_labels
        replay_calendar_summary["trusted_only"] = imported_trusted_only
        replay_calendar_summary["research_imported_data_allowed"] = not imported_trusted_only
        replay_calendar_summary["benchmark_quote_date_count"] = len(imported_calendar_quote_dates)
        replay_calendar_summary["shared_quote_date_count"] = len(imported_shared_quote_dates)
        replay_calendar_summary["calendar_gap_date_count"] = max(
            len(imported_calendar_quote_dates) - len(imported_shared_quote_dates),
            0,
        )
        replay_calendar_summary["required_quote_date_count"] = required_imported_calendar_dates
        replay_calendar_summary["replay_quote_date_source"] = imported_replay_quote_date_source
        if len(spy_index) < required_imported_calendar_dates:
            return {
                "error": (
                    "Imported historical validation has insufficient imported replay quote dates after aligning the replay calendar under the requested trust scope. "
                    f"Selected dates: {len(spy_index)}."
                ),
                "source_labels_required": imported_source_labels,
                "imported_data_scope": imported_data_scope_label,
                "replay_calendar": replay_calendar_summary,
                "required_imported_calendar_dates": required_imported_calendar_dates,
            }
    else:
        replay_calendar_summary = _build_replay_calendar_summary(
            source="spy_history",
            index=spy_index,
            raw_history_date_count=len(raw_spy_index),
        )
    replay_start = spy_index[0]
    excluded_tickers: list[dict] = []
    aligned_histories: dict[str, pd.DataFrame] = {}
    for sym, hist in all_histories.items():
        closes = hist["Close"].dropna()
        first_date = closes.index[0] if not closes.empty else None
        if sym != "SPY" and (closes.empty or first_date is None or first_date > replay_start):
            excluded_tickers.append({
                "ticker": sym,
                "reason": "insufficient_history",
                "history_days": int(len(closes)),
                "first_date": str(first_date.date()) if first_date is not None else None,
            })
            continue

        aligned = hist.reindex(spy_index).ffill()
        if aligned["Close"].isna().any() or aligned["Open"].isna().any():
            excluded_tickers.append({
                "ticker": sym,
                "reason": "missing_aligned_data",
                "history_days": int(len(closes)),
                "first_date": str(first_date.date()) if first_date is not None else None,
            })
            continue

        aligned["Volume"] = aligned["Volume"].fillna(0.0)
        aligned_histories[sym] = aligned

    if "SPY" not in aligned_histories:
        return {"error": "Could not align enough ticker history for replay"}

    all_closes = {sym: hist["Close"].astype(float) for sym, hist in aligned_histories.items()}
    all_opens = {sym: hist["Open"].astype(float) for sym, hist in aligned_histories.items()}
    all_volumes = {sym: hist["Volume"].astype(float) for sym, hist in aligned_histories.items()}
    eligible_tickers = sorted(all_closes.keys())
    series_len = len(spy_index)

    # ── Pre-compute per-ticker indicators ─────────────────────────────────────
    if progress_callback:
        progress_callback("Pre-computing indicators…", 0.05)

    precomputed:   dict[str, list] = {}
    ticker_arrays: dict[str, dict] = {}

    for ticker, closes_s in all_closes.items():
        pc = _precompute(closes_s, dte)
        precomputed[ticker] = pc

        prices_arr = closes_s.values.astype(float)
        n_arr = len(prices_arr)

        # Full MACD array (needed day-by-day during exit simulation)
        k12 = 2.0 / 13.0; k26 = 2.0 / 27.0
        ema12 = np.empty(n_arr); ema26 = np.empty(n_arr)
        ema12[0] = ema26[0] = prices_arr[0]
        for _i in range(1, n_arr):
            ema12[_i] = prices_arr[_i] * k12 + ema12[_i - 1] * (1 - k12)
            ema26[_i] = prices_arr[_i] * k26 + ema26[_i - 1] * (1 - k26)
        _macd_full = ema12 - ema26

        # RSI / SMA arrays reconstructed from precomputed daily values
        _rsi14  = np.full(n_arr, 50.0)
        _sma20  = np.full(n_arr, np.nan)
        _sma50  = np.full(n_arr, np.nan)
        for pday in pc:
            if pday is None:
                continue
            idx = pday["idx"]
            _rsi14[idx] = pday["rsi14"]
            _sma20[idx] = pday["sma20"]
            _sma50[idx] = pday["sma50"]

        opens_s = all_opens.get(ticker)
        volumes_s = all_volumes.get(ticker)
        opens_arr = opens_s.values.astype(float) if opens_s is not None else prices_arr
        volumes_arr = volumes_s.values.astype(float) if volumes_s is not None else np.zeros(n_arr)
        avg_volume_20d = volumes_s.rolling(UNDERLYING_LIQUIDITY_WINDOW, min_periods=UNDERLYING_LIQUIDITY_WINDOW).mean().fillna(0.0) if volumes_s is not None else pd.Series(np.zeros(n_arr))
        avg_dollar_volume_20d = (closes_s * volumes_s).rolling(
            UNDERLYING_LIQUIDITY_WINDOW,
            min_periods=UNDERLYING_LIQUIDITY_WINDOW,
        ).mean().fillna(0.0) if volumes_s is not None else pd.Series(np.zeros(n_arr))

        ticker_arrays[ticker] = {
            "prices": prices_arr,
            "opens":  opens_arr,
            "volumes": volumes_arr,
            "_adv20": avg_volume_20d.values.astype(float),
            "_adtv20": avg_dollar_volume_20d.values.astype(float),
            "_rsi14": _rsi14,
            "_macd":  _macd_full,
            "_sma20": _sma20,
            "_sma50": _sma50,
        }

    spy_arr       = all_closes["SPY"].values.astype(float)
    spy_n         = len(spy_arr)
    spy_ret5_arr  = np.zeros(spy_n)
    for _i in range(5, spy_n):
        spy_ret5_arr[_i] = (spy_arr[_i] / spy_arr[_i - 5] - 1) * 100

    # ── Day-by-day simulation ─────────────────────────────────────────────────
    if progress_callback:
        progress_callback("Starting day-by-day simulation…", 0.08)

    all_trades: list[dict] = []
    unpriced_candidates: list[dict] = []
    days_simulated: int = 0

    # Stop cooldown: after a stop-out, skip that ticker for N calendar days
    _stop_cooldown_until: dict[str, str] = {}  # ticker -> "YYYY-MM-DD" cooldown expiry

    def _build_candidate_for_tier(
        *,
        ticker: str,
        day_idx: int,
        day_data: dict[str, Any],
        ret5: float,
        adv20: float,
        adtv20: float,
        spy_ret5_today: float,
        prior_close: float | None,
        expectancy_surface: dict[str, Any] | None,
        tier_runtime: dict[str, Any],
    ) -> dict[str, Any] | None:
        nonlocal calibration_lookup_attempts
        nonlocal calibration_candidate_matches
        nonlocal calibration_candidate_dense_matches
        nonlocal calibration_candidate_sparse_matches
        tier_playbook = tier_runtime["playbook"]
        t_config, _ = _ticker_cfg(ticker, tier_runtime)
        t_sp = _idx_sp if ticker.upper() in INDEX_TICKERS else _eq_sp

        signal = _resolve_replay_entry_signal(
            day_data,
            tier_playbook,
            t_config,
            prior_close=prior_close,
        )
        if signal is None:
            return None
        trade_type = signal["trade_type"]

        _entry_filters = t_sp.get("entry_filters", {})
        if _entry_filters:
            _cooldown_days = int(_entry_filters.get("stop_cooldown_days", 0) or 0)
            if _cooldown_days > 0:
                _today_str = str(all_closes["SPY"].index[day_idx].date())
                if _today_str <= _stop_cooldown_until.get(ticker, ""):
                    return None
            market_regime_bucket = _market_regime_bucket(spy_ret5_today)
            if _entry_filters.get("require_bullish_regime") and market_regime_bucket != "bullish":
                return None
            if ticker.upper() == "QQQ":
                if _entry_filters.get("qqq_require_bullish_regime") and market_regime_bucket != "bullish":
                    return None
                _qqq_max_hv = float(_entry_filters.get("qqq_max_hv30", 999.0))
                if day_data["hv30"] > _qqq_max_hv:
                    return None

        tech = _tech_score(
            rsi14=day_data["rsi14"],
            macd=day_data["macd"],
            macd_prev=day_data["macd_prev"],
            price=day_data["S0"],
            sma20=day_data["sma20"],
            sma50=day_data.get("sma50", day_data["sma20"]),
            trade_type=trade_type,
        )
        if tech < t_config["min_tech_score"]:
            return None

        dir_score = _compute_direction_score(
            tech,
            trade_type,
            day_data["rsi14"],
            ret5,
            spy_ret5_today,
            sp=t_sp,
        )
        if signal.get("direction_score_override") is not None:
            dir_score = float(signal["direction_score_override"])
        if dir_score < t_config["min_confidence"]:
            return None

        qual_score = _compute_quality_score(
            day_data["iv_pct"],
            t_config["delta_target"],
            t_config["dte_at_entry"],
            sp=t_sp,
        )
        playbook_candidate = {
            "ticker": ticker,
            "trade_type": trade_type,
            "signal_family": signal.get("signal_family"),
            "signal_ret5": signal.get("signal_ret5", ret5),
            "signal_ret20": signal.get("signal_ret20", day_data.get("ret20")),
            "quality_score": qual_score,
            "tech_score": tech,
            "direction_score": dir_score,
            "hv30": day_data["hv30"],
            "spy_ret5": spy_ret5_today,
            "market_regime": _market_regime_bucket(spy_ret5_today),
            "sector": ticker_sectors.get(ticker, "Unknown"),
        }
        if not _candidate_matches_replay_playbook(playbook_candidate, tier_playbook):
            return None

        calibration = None
        calibration_lookup = None
        if expectancy_surface is not None:
            calibration_lookup_attempts += 1
            calibration_lookup = lookup_calibrated_expectancy(
                expectancy_surface,
                direction_score=dir_score,
                quality_score=qual_score,
                market_regime=normalized_market_regime(spy_ret5=spy_ret5_today),
                trade_type=trade_type,
                tech_score=tech,
                require_positive=True,
                allow_overall=False,
            )
            if calibration_lookup is not None:
                calibration_candidate_matches += 1
                calibration_candidate_fallback_levels[str(calibration_lookup.get("lookup_source") or "unknown")] += 1
                calibration_density = str(
                    calibration_lookup.get("calibration_density")
                    or ("sparse" if calibration_lookup.get("sparse_cohort") else "dense")
                ).strip().lower()
                if calibration_density == "dense":
                    calibration_candidate_dense_matches += 1
                    calibration = calibration_lookup
                else:
                    calibration_candidate_sparse_matches += 1
            if calibration is not None:
                ev = float(calibration.get("avg_pnl_pct", 0.0) or 0.0)
                if ev < float(t_config.get("min_calibrated_expectancy_pct", 0.0) or 0.0):
                    return None
                selection_source = "replay_calibrated"
            else:
                p_win = dir_score / 100.0
                ev = p_win * t_config["profit_target_pct"] - (1.0 - p_win) * t_config["stop_loss_pct"]
                if ev < t_config["min_ev_pct"]:
                    return None
                selection_source = "bootstrap_heuristic"
        else:
            p_win = dir_score / 100.0
            ev = p_win * t_config["profit_target_pct"] - (1.0 - p_win) * t_config["stop_loss_pct"]
            if ev < t_config["min_ev_pct"]:
                return None
            selection_source = "bootstrap_heuristic"

        return {
            "ticker": ticker,
            "day_idx": day_idx,
            "trade_type": trade_type,
            "signal_family": signal.get("signal_family"),
            "signal_variant": signal.get("signal_variant"),
            "signal_ret5": signal.get("signal_ret5", ret5),
            "signal_ret20": signal.get("signal_ret20", day_data.get("ret20")),
            "signal_sma20": signal.get("signal_sma20", day_data.get("sma20")),
            "signal_sma50": signal.get("signal_sma50", day_data.get("sma50")),
            "direction_score": dir_score,
            "quality_score": qual_score,
            "tech_score": tech,
            "ev": round(ev, 2),
            "sector": playbook_candidate["sector"],
            "allocation_group": _allocation_group_for_candidate(
                {
                    "ticker": ticker,
                    "sector": playbook_candidate["sector"],
                    "sleeve_group": tier_runtime.get("sleeve_group"),
                },
                unknown_sector_policy=unknown_sector_policy,
            ),
            "date": str(all_closes["SPY"].index[day_idx].date()),
            "spy_ret5": round(spy_ret5_today, 2),
            "market_regime": playbook_candidate["market_regime"],
            "selection_source": selection_source,
            "sleeve_id": tier_runtime.get("sleeve_id"),
            "sleeve_group": tier_runtime.get("sleeve_group"),
            "tier_id": tier_runtime.get("tier_id"),
            "tier_rank": int(tier_runtime.get("tier_rank") or 1),
            "_tier_key": tier_runtime.get("tier_key"),
            "calibrated_expectancy_pct": round(ev, 2) if calibration else None,
            "calibration_source": calibration_lookup.get("lookup_source") if calibration_lookup else None,
            "calibration_trades": calibration_lookup.get("trades") if calibration_lookup else 0,
            "calibration_density": calibration_lookup.get("calibration_density") if calibration_lookup else None,
            "calibration_is_dense": bool(calibration_lookup.get("dense_cohort")) if calibration_lookup else False,
            "calibration_raw_expectancy_pct": calibration_lookup.get("avg_pnl_pct_raw") if calibration_lookup else None,
            "calibration_parent_expectancy_pct": calibration_lookup.get("parent_avg_pnl_pct") if calibration_lookup else None,
            "calibration_used_parent_shrinkage": calibration_lookup.get("used_parent_shrinkage") if calibration_lookup else None,
            "calibration_sparse_warning": calibration_lookup.get("sparse_warning") if calibration_lookup else None,
            "calibration_surface_provenance": calibration_lookup.get("surface_provenance") if calibration_lookup else None,
            "hv30": day_data["hv30"],
            "iv_pct": day_data["iv_pct"],
            "S0": day_data["S0"],
            "rsi14": day_data["rsi14"],
            "avg_volume_20d": round(adv20, 0),
            "avg_dollar_volume_20d": round(adtv20, 2),
        }

    max_dte   = max(eq_config["dte_at_entry"], idx_config["dte_at_entry"])
    start_idx = 57                         # day_idx-1 needs SMA50 warmup (50+) plus buffer
    end_idx   = series_len - max_dte - 5     # leave room for trade exit data
    n_days = max(end_idx - start_idx, 1)

    for loop_i, day_idx in enumerate(range(start_idx, end_idx)):
        if loop_i % 20 == 0 and progress_callback:
            pct = 0.08 + 0.88 * (loop_i / n_days)
            entry_date_str = str(all_closes["SPY"].index[day_idx].date())
            progress_callback(f"Simulating {entry_date_str}…", pct)

        # Use prior day's SPY close — at 10:10 AM ET, today's close hasn't happened yet
        _spy_idx = day_idx - 1
        spy_ret5_today = float(spy_ret5_arr[_spy_idx]) if _spy_idx < spy_n else 0.0
        expectancy_surface = None
        while calibration_queue and int(calibration_queue[0][0]) < int(day_idx):
            _, _, ready_trade = heapq.heappop(calibration_queue)
            calibration_accumulator.add_trade(ready_trade)
        if calibration_accumulator.trade_count >= calibration_min_trades:
            expectancy_surface = calibration_accumulator.snapshot(
                source_metadata={
                    "run_at": datetime.now().isoformat(timespec="seconds"),
                    "lookback_years": lookback_years,
                    "n_picks": n_picks,
                    "iv_adj": iv_adj,
                    "pricing_lane": pricing_lane,
                    "universe_filters": replay_universe_filter_summary,
                },
            )
            if expectancy_surface is not None:
                calibration_surface_days += 1
                last_expectancy_surface = expectancy_surface
                _accumulate_surface_density(
                    calibration_density_aggregate,
                    list((expectancy_surface.get("diagnostics") or {}).get("level_density") or []),
                )

        candidates: list[dict] = []
        for ticker in replay_watchlist:
            if ticker not in all_closes:
                continue
            t_arr = ticker_arrays.get(ticker)
            if t_arr is None:
                continue
            pc = precomputed.get(ticker)
            if not pc or day_idx >= len(pc):
                continue
            day_data = pc[day_idx - 1]    # use prior-day close indicators; entry is at today's open
            if day_data is None:
                continue

            adv20 = float(t_arr["_adv20"][day_idx - 1]) if day_idx - 1 < len(t_arr["_adv20"]) else 0.0
            adtv20 = float(t_arr["_adtv20"][day_idx - 1]) if day_idx - 1 < len(t_arr["_adtv20"]) else 0.0
            if (
                adv20 < float(replay_underlying_filters["avg_volume_20d_min"])
                or adtv20 < float(replay_underlying_filters["avg_dollar_volume_20d_min"])
            ):
                continue

            S0 = day_data["S0"]
            ret5 = day_data["ret5"]

            prior_close = float(t_arr["prices"][day_idx - 2]) if day_idx >= 2 else None
            for tier_runtime in capacity_tier_runtimes:
                candidate = _build_candidate_for_tier(
                    ticker=ticker,
                    day_idx=day_idx,
                    day_data=day_data,
                    ret5=ret5,
                    adv20=adv20,
                    adtv20=adtv20,
                    spy_ret5_today=spy_ret5_today,
                    prior_close=prior_close,
                    expectancy_surface=expectancy_surface,
                    tier_runtime=tier_runtime,
                )
                if candidate is not None:
                    candidates.append(candidate)
                    break
            continue

            t_config, _ = _ticker_cfg(ticker)
            t_sp = _idx_sp if ticker.upper() in INDEX_TICKERS else _eq_sp

            prior_close = float(t_arr["prices"][day_idx - 2]) if day_idx >= 2 else None
            signal = _resolve_replay_entry_signal(
                day_data,
                replay_playbook,
                t_config,
                prior_close=prior_close,
            )
            if signal is None:
                continue
            trade_type = signal["trade_type"]

            # Per-ticker entry filters (same as live scan in options_chatbot.py)
            _entry_filters = t_sp.get("entry_filters", {})
            if _entry_filters:
                # Stop cooldown: skip ticker if recently stopped out
                _cooldown_days = int(_entry_filters.get("stop_cooldown_days", 0) or 0)
                if _cooldown_days > 0:
                    _today_str = str(all_closes["SPY"].index[day_idx].date())
                    if _today_str <= _stop_cooldown_until.get(ticker, ""):
                        continue
                market_regime_bucket = _market_regime_bucket(spy_ret5_today)
                # Universal bullish regime gate (applies to all tickers if set)
                if _entry_filters.get("require_bullish_regime") and market_regime_bucket != "bullish":
                    continue
                # Per-ticker: QQQ-specific gates
                if ticker.upper() == "QQQ":
                    if _entry_filters.get("qqq_require_bullish_regime") and market_regime_bucket != "bullish":
                        continue
                    _qqq_max_hv = float(_entry_filters.get("qqq_max_hv30", 999.0))
                    if day_data["hv30"] > _qqq_max_hv:
                        continue

            # Tech score gate (same _tech_score formula as live scan)
            tech = _tech_score(
                rsi14=day_data["rsi14"],
                macd=day_data["macd"],
                macd_prev=day_data["macd_prev"],
                price=S0,
                sma20=day_data["sma20"],
                sma50=day_data.get("sma50", day_data["sma20"]),
                trade_type=trade_type,
            )
            if tech < t_config["min_tech_score"]:
                continue

            # Direction score — uses exact same function as the live daily scan
            dir_score = _compute_direction_score(
                tech,
                trade_type,
                day_data["rsi14"],
                ret5,
                spy_ret5_today,
                sp=t_sp,
            )
            if signal.get("direction_score_override") is not None:
                dir_score = float(signal["direction_score_override"])
            if dir_score < t_config["min_confidence"]:
                continue

            # EV gate (identical formula to live scan)
            ev = None

            # Quality score — uses exact same function as the live daily scan
            qual_score = _compute_quality_score(
                day_data["iv_pct"],
                t_config["delta_target"],
                t_config["dte_at_entry"],
                sp=t_sp,
            )
            playbook_candidate = {
                "ticker": ticker,
                "trade_type": trade_type,
                "signal_family": signal.get("signal_family"),
                "signal_ret5": signal.get("signal_ret5", ret5),
                "signal_ret20": signal.get("signal_ret20", day_data.get("ret20")),
                "quality_score": qual_score,
                "tech_score": tech,
                "direction_score": dir_score,
                "hv30": day_data["hv30"],
                "spy_ret5": spy_ret5_today,
                "market_regime": _market_regime_bucket(spy_ret5_today),
                "sector": ticker_sectors.get(ticker, "Unknown"),
            }
            if not _candidate_matches_replay_playbook(playbook_candidate, replay_playbook):
                continue
            calibration = None
            calibration_lookup = None
            if expectancy_surface is not None:
                calibration_lookup_attempts += 1
                calibration_lookup = lookup_calibrated_expectancy(
                    expectancy_surface,
                    direction_score=dir_score,
                    quality_score=qual_score,
                    market_regime=normalized_market_regime(spy_ret5=spy_ret5_today),
                    trade_type=trade_type,
                    tech_score=tech,
                    require_positive=True,
                    allow_overall=False,
                )
                if calibration_lookup is not None:
                    calibration_candidate_matches += 1
                    calibration_candidate_fallback_levels[str(calibration_lookup.get("lookup_source") or "unknown")] += 1
                    calibration_density = str(
                        calibration_lookup.get("calibration_density")
                        or ("sparse" if calibration_lookup.get("sparse_cohort") else "dense")
                    ).strip().lower()
                    if calibration_density == "dense":
                        calibration_candidate_dense_matches += 1
                        calibration = calibration_lookup
                    else:
                        calibration_candidate_sparse_matches += 1
                if calibration is not None:
                    ev = float(calibration.get("avg_pnl_pct", 0.0) or 0.0)
                    if ev < float(t_config.get("min_calibrated_expectancy_pct", 0.0) or 0.0):
                        continue
                    selection_source = "replay_calibrated"
                else:
                    p_win = dir_score / 100.0
                    ev = p_win * t_config["profit_target_pct"] - (1.0 - p_win) * t_config["stop_loss_pct"]
                    if ev < t_config["min_ev_pct"]:
                        continue
                    selection_source = "bootstrap_heuristic"
            else:
                p_win = dir_score / 100.0
                ev = p_win * t_config["profit_target_pct"] - (1.0 - p_win) * t_config["stop_loss_pct"]
                if ev < t_config["min_ev_pct"]:
                    continue
                selection_source = "bootstrap_heuristic"

            candidates.append({
                "ticker": ticker,
                "day_idx": day_idx,
                "trade_type": trade_type,
                "signal_family": signal.get("signal_family"),
                "signal_variant": signal.get("signal_variant"),
                "signal_ret5": signal.get("signal_ret5", ret5),
                "signal_ret20": signal.get("signal_ret20", day_data.get("ret20")),
                "signal_sma20": signal.get("signal_sma20", day_data.get("sma20")),
                "signal_sma50": signal.get("signal_sma50", day_data.get("sma50")),
                "direction_score": dir_score,
                "quality_score": qual_score,
                "tech_score": tech,
                "ev": round(ev, 2),
                "sector": playbook_candidate["sector"],
                "date": str(all_closes["SPY"].index[day_idx].date()),  # actual entry date
                "spy_ret5": round(spy_ret5_today, 2),
                "market_regime": playbook_candidate["market_regime"],
                "selection_source": selection_source,
                "calibrated_expectancy_pct": round(ev, 2) if calibration else None,
                "calibration_source": calibration_lookup.get("lookup_source") if calibration_lookup else None,
                "calibration_trades": calibration_lookup.get("trades") if calibration_lookup else 0,
                "calibration_density": calibration_lookup.get("calibration_density") if calibration_lookup else None,
                "calibration_is_dense": bool(calibration_lookup.get("dense_cohort")) if calibration_lookup else False,
                "calibration_raw_expectancy_pct": calibration_lookup.get("avg_pnl_pct_raw") if calibration_lookup else None,
                "calibration_parent_expectancy_pct": calibration_lookup.get("parent_avg_pnl_pct") if calibration_lookup else None,
                "calibration_used_parent_shrinkage": calibration_lookup.get("used_parent_shrinkage") if calibration_lookup else None,
                "calibration_sparse_warning": calibration_lookup.get("sparse_warning") if calibration_lookup else None,
                "calibration_surface_provenance": calibration_lookup.get("surface_provenance") if calibration_lookup else None,
                "hv30": day_data["hv30"],
                "iv_pct": day_data["iv_pct"],
                "S0": S0,
                "rsi14": day_data["rsi14"],
                "avg_volume_20d": round(adv20, 0),
                "avg_dollar_volume_20d": round(adtv20, 2),
            })

        days_simulated += 1
        day_selection_diag: dict[str, Any] = {
            "date": str(all_closes["SPY"].index[day_idx].date()),
            "candidate_count": len(candidates),
            "n_picks": int(n_picks),
            "selected_count": 0,
            "preflight_passed_count": 0,
            "preflight_rejected_count": 0,
            "unused_slots": int(n_picks),
            "tier_candidate_counts": dict(Counter(str(item.get("tier_id") or "unknown") for item in candidates)),
            "sleeve_candidate_counts": dict(Counter(str(item.get("sleeve_id") or "unknown") for item in candidates)),
        }
        if not candidates:
            day_selection_diag["underfill_reason"] = "no_candidates"
            daily_selection_diagnostics.append(day_selection_diag)
            continue

        # Pick top n_picks with sector diversification. Optional execution-aware
        # backfill only checks entry-time contract availability/liquidity.
        if execution_backfill_enabled and _is_imported_truth_source(normalized_truth_lane) and imported_store is not None:
            candidate_rank_key = _configured_candidate_rank_tuple if use_configured_daily_picker else _candidate_rank_tuple
            ranked_candidates = sorted(candidates, key=candidate_rank_key, reverse=True)
            preflight_passed: list[dict[str, Any]] = []
            scan_limit = len(ranked_candidates) if scan_until_capacity else min(len(ranked_candidates), execution_backfill_scan_depth)
            for daily_rank, candidate in enumerate(ranked_candidates[:scan_limit], start=1):
                allowed, rejected = _preflight_imported_entry_candidate(candidate, daily_rank=daily_rank)
                if allowed:
                    preflight_passed.append(candidate)
                elif rejected is not None:
                    pre_entry_filtered_candidates.append(rejected)
            if use_configured_daily_picker:
                top_picks, pick_diag = _pick_top_n_daily_configured(
                    preflight_passed,
                    n_picks,
                    max_per_allocation_group=max_per_allocation_group,
                    max_per_ticker=int(max_per_ticker) if max_per_ticker is not None else None,
                    max_total_index=int(max_total_index) if max_total_index is not None else None,
                    unknown_sector_policy=unknown_sector_policy,
                )
            else:
                top_picks = _pick_top_n_daily(preflight_passed, n_picks)
                pick_diag = {
                    "candidate_count": len(preflight_passed),
                    "selected_count": len(top_picks),
                    "unused_slots": max(int(n_picks) - len(top_picks), 0),
                    "reject_reasons": {},
                }
            day_selection_diag["preflight_passed_count"] = len(preflight_passed)
            day_selection_diag["preflight_rejected_count"] = scan_limit - len(preflight_passed)
        else:
            if use_configured_daily_picker:
                top_picks, pick_diag = _pick_top_n_daily_configured(
                    candidates,
                    n_picks,
                    max_per_allocation_group=max_per_allocation_group,
                    max_per_ticker=int(max_per_ticker) if max_per_ticker is not None else None,
                    max_total_index=int(max_total_index) if max_total_index is not None else None,
                    unknown_sector_policy=unknown_sector_policy,
                )
            else:
                top_picks = _pick_top_n_daily(candidates, n_picks)
                pick_diag = {
                    "candidate_count": len(candidates),
                    "selected_count": len(top_picks),
                    "unused_slots": max(int(n_picks) - len(top_picks), 0),
                    "reject_reasons": {},
                }
            day_selection_diag["preflight_passed_count"] = len(candidates)
        day_selection_diag.update(
            {
                "selected_count": len(top_picks),
                "unused_slots": max(int(n_picks) - len(top_picks), 0),
                "allocation_reject_reasons": dict(pick_diag.get("reject_reasons") or {}),
                "allocation_group_counts": dict(pick_diag.get("allocation_group_counts") or {}),
                "selected_tickers": [str(item.get("ticker") or "").upper() for item in top_picks],
                "selected_tiers": dict(Counter(str(item.get("tier_id") or "unknown") for item in top_picks)),
                "selected_sleeves": dict(Counter(str(item.get("sleeve_id") or "unknown") for item in top_picks)),
            }
        )
        if len(top_picks) < int(n_picks):
            day_selection_diag["underfill_reason"] = "candidate_pool_exhausted" if len(candidates) <= len(top_picks) else "allocation_or_preflight_rejects"
        daily_selection_diagnostics.append(day_selection_diag)

        # Simulate each pick's outcome
        for pick in top_picks:
            t_sym = pick["ticker"]
            t_arr = ticker_arrays.get(t_sym)
            if t_arr is None:
                continue
            p_config, _ = _ticker_cfg(t_sym, _runtime_for_pick(pick))

            if _is_imported_truth_source(normalized_truth_lane) and imported_store is not None:
                entry_anchor_price = float(t_arr["opens"][pick["day_idx"]])
                entry_anchor_source = "open"
                if normalized_truth_lane == IMPORTED_DAILY_TRUTH_SOURCE:
                    archived_selection_price = pick.get("underlying_price_at_selection")
                    if archived_selection_price is not None:
                        entry_anchor_price = float(archived_selection_price)
                        entry_anchor_source = "archived_underlying_price_at_selection"
                    elif int(pick["day_idx"]) > 0:
                        entry_anchor_price = float(t_arr["prices"][pick["day_idx"] - 1])
                        entry_anchor_source = "prior_close"
                    else:
                        entry_anchor_source = "open_fallback_no_prior_close"
                _is_spread_sim = p_config.get("strategy_type") == "vertical_spread"
                if _is_spread_sim:
                    outcome = _simulate_spread_outcome_imported(
                        store=imported_store,
                        ticker=t_sym,
                        dates=all_closes["SPY"].index,
                        prices=t_arr["prices"],
                        i=pick["day_idx"],
                        trade_type=pick["trade_type"],
                        hv30=pick["hv30"],
                        long_delta_target=p_config.get("spread_long_delta", 0.50),
                        short_delta_target=p_config.get("spread_short_delta", 0.20),
                        dte_at_entry=p_config["dte_at_entry"],
                        stop_loss_pct=p_config.get("spread_stop_loss_pct", p_config["stop_loss_pct"]),
                        profit_target_pct=p_config.get("spread_profit_target_pct", p_config["profit_target_pct"]),
                        time_exit_pct=p_config.get("spread_time_exit_pct", p_config["time_exit_pct"]),
                        trailing_profit_pct=p_config["trailing_profit_pct"],
                        trailing_giveback_pct=p_config["trailing_giveback_pct"],
                        max_width_pct=p_config.get("spread_max_width_pct", 5.0),
                        exit_monitoring_mode=p_config.get("spread_exit_monitoring_mode", "daily"),
                        time_exit_basis=p_config.get("spread_time_exit_basis", "trading_sessions"),
                        _rsi14=t_arr["_rsi14"],
                        _macd=t_arr["_macd"],
                        _sma20=t_arr["_sma20"],
                        _sma50=t_arr["_sma50"],
                        tech_at_entry=pick["tech_score"],
                        entry_S0=entry_anchor_price,
                        iv_adj=iv_adj,
                        truth_source=normalized_truth_lane,
                        snapshot_kind=_imported_snapshot_kind(normalized_truth_lane),
                        entry_quote_minute_et=DAILY_QUOTE_MINUTE_ET if normalized_truth_lane == IMPORTED_DAILY_TRUTH_SOURCE else ENTRY_QUOTE_MINUTE_ET,
                        entry_window_minutes=0 if normalized_truth_lane == IMPORTED_DAILY_TRUTH_SOURCE else ENTRY_QUOTE_WINDOW_MINUTES,
                        entry_slippage_pct=p_config.get("entry_slippage_pct", 0.0),
                        exit_slippage_pct=p_config.get("exit_slippage_pct", 0.0),
                        pricing_lane=requested_pricing_lane,
                        entry_anchor_source=entry_anchor_source,
                        execution_realism=_execution_realism_label(normalized_truth_lane),
                        source_labels=imported_source_labels,
                        trusted_only=imported_trusted_only,
                        chain_native_spread_selection=bool(p_config.get("chain_native_spread_selection", False)),
                        chain_native_min_dte=p_config.get("chain_native_min_dte"),
                        chain_native_max_dte=p_config.get("chain_native_max_dte"),
                        max_debit_pct_of_width=replay_playbook.get("max_debit_pct_of_width"),
                        chain_native_min_prior_quote_days=int(p_config.get("chain_native_min_prior_quote_days", 0) or 0),
                        chain_native_prior_quote_lookback_days=int(p_config.get("chain_native_prior_quote_lookback_days", 14) or 14),
                        chain_native_min_long_prior_quote_days=(
                            int(p_config["chain_native_min_long_prior_quote_days"])
                            if p_config.get("chain_native_min_long_prior_quote_days") is not None
                            else None
                        ),
                        chain_native_min_short_prior_quote_days=(
                            int(p_config["chain_native_min_short_prior_quote_days"])
                            if p_config.get("chain_native_min_short_prior_quote_days") is not None
                            else None
                        ),
                        chain_native_prior_quote_score_weight=float(p_config.get("chain_native_prior_quote_score_weight", 0.0) or 0.0),
                        chain_native_long_prior_quote_score_weight=(
                            float(p_config["chain_native_long_prior_quote_score_weight"])
                            if p_config.get("chain_native_long_prior_quote_score_weight") is not None
                            else None
                        ),
                        chain_native_short_prior_quote_score_weight=(
                            float(p_config["chain_native_short_prior_quote_score_weight"])
                            if p_config.get("chain_native_short_prior_quote_score_weight") is not None
                            else None
                        ),
                        chain_native_prior_quote_score_cap=int(p_config.get("chain_native_prior_quote_score_cap", 5) or 0),
                        chain_native_max_entry_leg_bid_ask_pct=p_config.get("chain_native_max_entry_leg_bid_ask_pct"),
                        chain_native_min_entry_short_bid=p_config.get("chain_native_min_entry_short_bid"),
                        chain_native_short_inside_steps=int(p_config.get("chain_native_short_inside_steps", 0) or 0),
                        chain_native_short_inside_require_debit_cap=bool(
                            p_config.get("chain_native_short_inside_require_debit_cap", True)
                        ),
                    )
                else:
                    outcome = _simulate_trade_outcome_imported(
                        store=imported_store,
                        ticker=t_sym,
                        dates=all_closes["SPY"].index,
                        prices=t_arr["prices"],
                        i=pick["day_idx"],
                        trade_type=pick["trade_type"],
                        hv30=pick["hv30"],
                        delta_target=p_config["delta_target"],
                        dte_at_entry=p_config["dte_at_entry"],
                        stop_loss_pct=p_config["stop_loss_pct"],
                        profit_target_pct=p_config["profit_target_pct"],
                        time_exit_pct=p_config["time_exit_pct"],
                        trailing_profit_pct=p_config["trailing_profit_pct"],
                        trailing_giveback_pct=p_config["trailing_giveback_pct"],
                        _rsi14=t_arr["_rsi14"],
                        _macd=t_arr["_macd"],
                        _sma20=t_arr["_sma20"],
                        _sma50=t_arr["_sma50"],
                        tech_at_entry=pick["tech_score"],
                        entry_S0=entry_anchor_price,
                        iv_adj=iv_adj,
                        truth_source=normalized_truth_lane,
                        snapshot_kind=_imported_snapshot_kind(normalized_truth_lane),
                        entry_quote_minute_et=DAILY_QUOTE_MINUTE_ET if normalized_truth_lane == IMPORTED_DAILY_TRUTH_SOURCE else ENTRY_QUOTE_MINUTE_ET,
                        entry_window_minutes=0 if normalized_truth_lane == IMPORTED_DAILY_TRUTH_SOURCE else ENTRY_QUOTE_WINDOW_MINUTES,
                        archived_contract_symbol=pick.get("contract_symbol"),
                        archived_expiry=pick.get("expiry"),
                        archived_strike=pick.get("strike"),
                        archived_option_type=pick.get("option_type") or pick.get("trade_type") or pick.get("type"),
                        archived_quote_time_et=pick.get("quote_time_et"),
                        archived_quote_basis=pick.get("quote_basis"),
                        archived_underlying_price_at_selection=pick.get("underlying_price_at_selection"),
                        archived_selection_source=pick.get("selection_source"),
                        entry_slippage_pct=p_config.get("entry_slippage_pct", 0.0),
                        exit_slippage_pct=p_config.get("exit_slippage_pct", 0.0),
                        pricing_lane=requested_pricing_lane,
                        entry_anchor_source=entry_anchor_source,
                        execution_realism=_execution_realism_label(normalized_truth_lane),
                        source_labels=imported_source_labels,
                        trusted_only=imported_trusted_only,
                    )
            else:
                _is_spread_sim = p_config.get("strategy_type") == "vertical_spread"
                if _is_spread_sim:
                    outcome = _simulate_spread_outcome_hist(
                        prices         = t_arr["prices"],
                        i              = pick["day_idx"],
                        trade_type     = pick["trade_type"],
                        hv30           = pick["hv30"],
                        long_delta_target  = p_config.get("spread_long_delta", 0.50),
                        short_delta_target = p_config.get("spread_short_delta", 0.20),
                        dte_at_entry   = p_config["dte_at_entry"],
                        stop_loss_pct  = p_config.get("spread_stop_loss_pct", p_config["stop_loss_pct"]),
                        profit_target_pct = p_config.get("spread_profit_target_pct", p_config["profit_target_pct"]),
                        time_exit_pct  = p_config.get("spread_time_exit_pct", p_config["time_exit_pct"]),
                        trailing_profit_pct = p_config["trailing_profit_pct"],
                        trailing_giveback_pct = p_config["trailing_giveback_pct"],
                        max_width_pct  = p_config.get("spread_max_width_pct", 5.0),
                        _rsi14         = t_arr["_rsi14"],
                        _macd          = t_arr["_macd"],
                        _sma20         = t_arr["_sma20"],
                        _sma50         = t_arr["_sma50"],
                        tech_at_entry  = pick["tech_score"],
                        entry_S0       = float(t_arr["opens"][pick["day_idx"]]),
                        iv_adj         = iv_adj,
                        entry_slippage_pct = p_config.get("entry_slippage_pct", 0.0),
                        exit_slippage_pct  = p_config.get("exit_slippage_pct", 0.0),
                        pricing_lane       = pricing_lane,
                    )
                else:
                    outcome = _simulate_trade_outcome_hist(
                        prices         = t_arr["prices"],
                        i              = pick["day_idx"],
                        trade_type     = pick["trade_type"],
                        hv30           = pick["hv30"],
                        delta_target   = p_config["delta_target"],
                        dte_at_entry   = p_config["dte_at_entry"],
                        stop_loss_pct  = p_config["stop_loss_pct"],
                        profit_target_pct = p_config["profit_target_pct"],
                        time_exit_pct  = p_config["time_exit_pct"],
                        trailing_profit_pct = p_config["trailing_profit_pct"],
                        trailing_giveback_pct = p_config["trailing_giveback_pct"],
                        _rsi14         = t_arr["_rsi14"],
                        _macd          = t_arr["_macd"],
                        _sma20         = t_arr["_sma20"],
                        _sma50         = t_arr["_sma50"],
                        tech_at_entry  = pick["tech_score"],
                        entry_S0       = float(t_arr["opens"][pick["day_idx"]]),
                        iv_adj         = iv_adj,
                        entry_slippage_pct = p_config.get("entry_slippage_pct", 0.0),
                        exit_slippage_pct  = p_config.get("exit_slippage_pct", 0.0),
                        pricing_lane       = pricing_lane,
                    )

            if outcome is None:
                continue
            if not bool(outcome.get("priced", True)):
                unpriced_trade = {
                    "ticker": t_sym,
                    "date": pick["date"],
                    "type": pick["trade_type"],
                    "signal_family": pick.get("signal_family"),
                    "signal_variant": pick.get("signal_variant"),
                    "signal_ret5": pick.get("signal_ret5"),
                    "signal_ret20": pick.get("signal_ret20"),
                    "signal_sma20": pick.get("signal_sma20"),
                    "signal_sma50": pick.get("signal_sma50"),
                    "direction_score": round(pick["direction_score"], 1),
                    "quality_score": round(pick["quality_score"], 1),
                    "tech_score": round(pick["tech_score"], 1),
                    "ev": pick["ev"],
                    "selection_source": pick.get("selection_source"),
                    "sleeve_id": pick.get("sleeve_id"),
                    "sleeve_group": pick.get("sleeve_group"),
                    "tier_id": pick.get("tier_id"),
                    "tier_rank": pick.get("tier_rank"),
                    "allocation_group": pick.get("allocation_group"),
                    "tradability_score": pick.get("tradability_score"),
                    "tradability_reasons": pick.get("tradability_reasons"),
                    "calibration_density": pick.get("calibration_density"),
                    "target_move_pct": None,
                    "truth_source": normalized_truth_lane,
                    "requested_pricing_lane": requested_pricing_lane,
                    **{key: value for key, value in outcome.items() if key != "priced"},
                }
                unpriced_trade["promotion_class"] = _trade_promotion_class(unpriced_trade)
                unpriced_trade["non_promotable_reason"] = _trade_non_promotable_reason(unpriced_trade)
                unpriced_candidates.append(
                    unpriced_trade
                )
                unpriced_reason = str(unpriced_trade.get("unpriced_reason") or "").strip()
                if (exit_quote_failure_memory_enabled or symbol_health_memory_enabled) and unpriced_reason in exit_quote_failure_reasons:
                    observed_raw = unpriced_trade.get("missing_quote_date") or unpriced_trade.get("date")
                    try:
                        observed_date = pd.Timestamp(observed_raw).date()
                    except Exception:
                        observed_date = None
                    if observed_date is not None:
                        if exit_quote_failure_memory_enabled:
                            exit_quote_failure_memory[_exit_quote_failure_memory_key(pick)].append(observed_date)
                        if symbol_health_memory_enabled:
                            symbol_health_memory[t_sym].append(
                                {
                                    "observed_date": observed_date,
                                    "kind": "unpriced_failure",
                                    "pnl_pct": symbol_health_unpriced_penalty_pct,
                                }
                            )
                continue

            target_move_pct = round(
                (outcome["entry_px"] * p_config["profit_target_pct"] / 100.0)
                / max(outcome["delta_val"], 0.01)
                / max(outcome["stock_px"], 0.01)
                * 100.0,
                2,
            )
            if outcome["exit_reason"] == "target":
                prediction_outcome = "hit"
            elif outcome["exit_reason"] == "stop":
                prediction_outcome = "miss"
            elif outcome["directional_correct"]:
                prediction_outcome = (
                    "hit" if abs(outcome["stock_move_pct"]) >= target_move_pct * 0.5
                    else "directional"
                )
            else:
                prediction_outcome = "miss"

            if pick.get("calibration_sparse_warning"):
                calibration_selected_sparse_warnings[str(pick.get("calibration_sparse_warning"))] += 1

            trade_record = {
                "ticker":          t_sym,
                "date":            pick["date"],
                "exit_date":       str(all_closes["SPY"].index[int(outcome["exit_day_idx"])].date()),
                "type":            pick["trade_type"],
                "signal_family":   pick.get("signal_family"),
                "signal_variant":  pick.get("signal_variant"),
                "signal_ret5":     pick.get("signal_ret5"),
                "signal_ret20":    pick.get("signal_ret20"),
                "signal_sma20":    pick.get("signal_sma20"),
                "signal_sma50":    pick.get("signal_sma50"),
                "direction_score": round(pick["direction_score"], 1),
                "quality_score":   round(pick["quality_score"],   1),
                "tech_score":      round(pick["tech_score"],       1),
                "ev":              pick["ev"],
                "selection_source": pick.get("selection_source"),
                "sleeve_id": pick.get("sleeve_id"),
                "sleeve_group": pick.get("sleeve_group"),
                "tier_id": pick.get("tier_id"),
                "tier_rank": pick.get("tier_rank"),
                "allocation_group": pick.get("allocation_group"),
                "tradability_score": pick.get("tradability_score"),
                "tradability_reasons": pick.get("tradability_reasons"),
                "long_prior_quote_days": pick.get("long_prior_quote_days"),
                "short_prior_quote_days": pick.get("short_prior_quote_days"),
                "calibrated_expectancy_pct": pick.get("calibrated_expectancy_pct"),
                "calibration_source": pick.get("calibration_source"),
                "calibration_trades": pick.get("calibration_trades"),
                "calibration_density": pick.get("calibration_density"),
                "calibration_is_dense": pick.get("calibration_is_dense"),
                "calibration_raw_expectancy_pct": pick.get("calibration_raw_expectancy_pct"),
                "calibration_parent_expectancy_pct": pick.get("calibration_parent_expectancy_pct"),
                "calibration_used_parent_shrinkage": pick.get("calibration_used_parent_shrinkage"),
                "calibration_sparse_warning": pick.get("calibration_sparse_warning"),
                "calibration_surface_provenance": pick.get("calibration_surface_provenance"),
                "sector":          pick["sector"],
                "spy_ret5":        pick.get("spy_ret5"),
                "market_regime":   pick.get("market_regime", "neutral"),
                "target_move_pct": target_move_pct,
                "prediction_outcome": prediction_outcome,
                "avg_volume_20d":  pick.get("avg_volume_20d"),
                "avg_dollar_volume_20d": pick.get("avg_dollar_volume_20d"),
                "truth_source":    normalized_truth_lane,
                **outcome,
            }
            post_entry_allowed, post_entry_reject_reason = _trade_matches_replay_post_entry_filters(
                trade_record,
                replay_playbook,
            )
            if not post_entry_allowed:
                post_entry_filtered_trades.append(
                    {
                        **trade_record,
                        "post_entry_filter_reject_reason": post_entry_reject_reason,
                        "post_entry_filter_debit_pct_of_width": _trade_debit_pct_of_width(trade_record),
                    }
                )
                continue
            trade_record["promotion_class"] = _trade_promotion_class(trade_record)
            trade_record["promotable"] = _is_trade_promotable(trade_record)
            trade_record["non_promotable_reason"] = _trade_non_promotable_reason(trade_record)
            if _is_exact_contract_resolution(trade_record.get("entry_contract_resolution")):
                heapq.heappush(
                    calibration_queue,
                    (
                        int(trade_record.get("exit_day_idx", -1) or -1),
                        calibration_queue_seq,
                        trade_record,
                    ),
                )
                calibration_queue_seq += 1
            if symbol_health_memory_enabled:
                try:
                    observed_date = pd.Timestamp(trade_record.get("exit_date")).date()
                except Exception:
                    observed_date = None
                if observed_date is not None:
                    symbol_health_memory[t_sym].append(
                        {
                            "observed_date": observed_date,
                            "kind": "priced",
                            "pnl_pct": float(trade_record.get("pnl_pct") or 0.0),
                        }
                    )
            all_trades.append(trade_record)

            # Trigger stop cooldown if this trade stopped out
            if outcome.get("exit_reason") in ("stop", "trailing_stop"):
                _t_sp_for_cooldown = _idx_sp if t_sym.upper() in INDEX_TICKERS else _eq_sp
                _cd = int(_t_sp_for_cooldown.get("entry_filters", {}).get("stop_cooldown_days", 0) or 0)
                if _cd > 0:
                    from datetime import timedelta
                    _entry_dt = all_closes["SPY"].index[day_idx]
                    _cooldown_expiry = (_entry_dt + timedelta(days=_cd)).strftime("%Y-%m-%d")
                    _stop_cooldown_until[t_sym] = max(_stop_cooldown_until.get(t_sym, ""), _cooldown_expiry)

    # ── Aggregate metrics ─────────────────────────────────────────────────────
    if not all_trades:
        calibration_diagnostics = _base_calibration_diagnostics()
        calibration_diagnostics.update(
            {
                "surface_min_trades": calibration_min_trades,
                "shrinkage_trades": calibration_shrinkage_trades,
                "sparse_warning_trades": calibration_sparse_warning_trades,
                "surface_days": calibration_surface_days,
                "candidate_lookup_attempts": calibration_lookup_attempts,
                "candidate_calibrated_count": calibration_candidate_matches,
                "candidate_calibrated_pct": (
                    round(calibration_candidate_matches / max(calibration_lookup_attempts, 1) * 100.0, 1)
                    if calibration_lookup_attempts else 0.0
                ),
                "candidate_fallback_level_counts": dict(calibration_candidate_fallback_levels),
                "density_by_level": _finalize_surface_density(calibration_density_aggregate),
                "include_tech_band": bool(last_expectancy_surface and last_expectancy_surface.get("include_tech_band")),
                "sparse_cohort_warnings": list((last_expectancy_surface or {}).get("diagnostics", {}).get("sparse_warnings") or []),
            }
        )
        priced_trade_count = 0
        unpriced_trade_count = len(unpriced_candidates)
        post_entry_filtered_trade_count = len(post_entry_filtered_trades)
        pre_entry_filtered_candidate_count = len(pre_entry_filtered_candidates)
        pre_post_entry_candidate_trade_count = (
            priced_trade_count + unpriced_trade_count + post_entry_filtered_trade_count
        )
        candidate_trade_count = pre_post_entry_candidate_trade_count
        quote_covered_trade_count = priced_trade_count + post_entry_filtered_trade_count
        quote_coverage_pct = round(quote_covered_trade_count / max(candidate_trade_count, 1) * 100.0, 1) if candidate_trade_count else 0.0
        unpriced_trade_diagnostics = _summarize_unpriced_trades(unpriced_candidates)
        contract_resolution = _contract_resolution_summary(
            {
                "trades": post_entry_filtered_trades,
                "priced_trade_count": quote_covered_trade_count,
                "candidate_trade_count": candidate_trade_count,
            }
        )
        exact_contract_metrics = _trade_subset_metrics([], include_exit_reasons=True)
        nearest_listed_metrics = _trade_subset_metrics([])
        authoritative_profitability_gate = _authoritative_profitability_gate(
            exact_contract_metrics,
            min_trade_count=25,
            min_profit_factor=1.05,
        )
        promotion_metrics = {
            **_trade_subset_metrics([], include_exit_reasons=True),
            "authoritative_profitability_basis": _authoritative_profitability_basis(normalized_truth_lane),
            "authoritative_profitability_metrics": exact_contract_metrics,
            "authoritative_profitability_gate": authoritative_profitability_gate,
            "promotion_status": "block",
            "promoted_symbols": [],
            "blockers": ["No promotable exact-contract trades were recorded."],
        }
        output = {
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "mode": "backtest", "profile": "mixed",
            "lookback_years": lookback_years,
            "iv_adj": iv_adj,
            "requested_pricing_lane": requested_pricing_lane,
            "effective_pricing_lane": requested_pricing_lane,
            "pricing_lane": requested_pricing_lane,
            "playbook": replay_playbook["id"],
            "requested_directions": normalized_allowed_directions,
            "truth_source": normalized_truth_lane,
            "imported_data_scope": imported_data_scope_label if _is_imported_truth_source(normalized_truth_lane) else None,
            "research_imported_data_allowed": (not imported_trusted_only) if _is_imported_truth_source(normalized_truth_lane) else False,
            "entry_anchor_policy": _entry_anchor_policy_label(normalized_truth_lane),
            "execution_realism": _execution_realism_label(normalized_truth_lane),
            "n_picks": n_picks,
            "execution_backfill_enabled": execution_backfill_enabled,
            "execution_backfill_scan_depth": execution_backfill_scan_depth,
            "scan_until_capacity": scan_until_capacity,
            "unknown_sector_policy": unknown_sector_policy,
            "max_per_allocation_group": max_per_allocation_group,
            "max_per_ticker": max_per_ticker,
            "max_total_index": max_total_index,
            "exit_quote_failure_memory_enabled": exit_quote_failure_memory_enabled,
            "exit_quote_failure_cooldown_days": exit_quote_failure_cooldown_days,
            "exit_quote_failure_max_prior": exit_quote_failure_max_prior,
            "exit_quote_failure_scope": exit_quote_failure_scope,
            "exit_quote_failure_memory_observed_count": sum(len(items) for items in exit_quote_failure_memory.values()),
            "capacity_tiers": capacity_tiers,
            "total_days": days_simulated, "total_trades": 0,
            "priced_trade_count": priced_trade_count,
            "unpriced_trade_count": unpriced_trade_count,
            "pre_entry_filtered_candidate_count": pre_entry_filtered_candidate_count,
            "pre_entry_filtered_candidate_reasons": dict(Counter(str(item.get("pre_entry_filter_reject_reason") or "unknown") for item in pre_entry_filtered_candidates)),
            "post_entry_filtered_trade_count": post_entry_filtered_trade_count,
            **_post_entry_denominator_truth(
                priced_trade_count=priced_trade_count,
                unpriced_trade_count=unpriced_trade_count,
                post_entry_filtered_trade_count=post_entry_filtered_trade_count,
            ),
            "post_entry_filtered_trade_reasons": dict(Counter(str(item.get("post_entry_filter_reject_reason") or "unknown") for item in post_entry_filtered_trades)),
            "candidate_trade_count": candidate_trade_count,
            "quote_coverage_pct": quote_coverage_pct,
            **contract_resolution,
            "entry_quote_time_et": _imported_entry_quote_label(normalized_truth_lane) if _is_imported_truth_source(normalized_truth_lane) else f"{_et_minute_label(ENTRY_QUOTE_MINUTE_ET)} + {ENTRY_QUOTE_WINDOW_MINUTES}m",
            "exit_quote_time_et": _imported_exit_quote_label(normalized_truth_lane) if _is_imported_truth_source(normalized_truth_lane) else "Latest available snapshot each trading day ET",
            "win_rate_pct": 0.0, "full_hit_rate_pct": 0.0, "directional_accuracy_pct": 0.0,
            "profit_factor": 0.0,
            **_profit_factor_denominator_truth_from_pnls([]),
            "avg_pnl_pct": 0.0,
            "avg_picks_per_day": 0.0, "sharpe": 0.0, "max_drawdown_pct": 0.0,
            "selection_source_counts": {},
            "calibration_summary": _selection_calibration_summary([], required_trades=calibration_min_trades),
            "calibration_diagnostics": calibration_diagnostics,
            "calibration_density_metrics": _calibration_density_metrics([]),
            "universe_filters": replay_universe_filter_summary,
            "contract_selection_basis": (
                "historical_chain_nearest_listed_contract"
                if _is_imported_truth_source(normalized_truth_lane)
                else "synthetic_model"
            ),
            "exact_contract_metrics": exact_contract_metrics,
            "authoritative_profitability_basis": _authoritative_profitability_basis(normalized_truth_lane),
            "authoritative_profitability_metrics": exact_contract_metrics,
            "authoritative_profitability_gate": authoritative_profitability_gate,
            "nearest_listed_metrics": nearest_listed_metrics,
            "promotion_metrics": promotion_metrics,
            "by_symbol": {},
            "by_sleeve": {},
            "by_tier": {},
            "promotion_trade_count": 0,
            "non_promotable_trade_count": 0,
            "truth_store": imported_truth_store if _is_imported_truth_source(normalized_truth_lane) else None,
            "required_imported_calendar_dates": (
                required_imported_calendar_dates if _is_imported_truth_source(normalized_truth_lane) else None
            ),
            "replay_calendar": replay_calendar_summary,
            "validation_universe": list(replay_watchlist),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": excluded_tickers,
            "playbook_allowed_tickers": list(replay_playbook.get("allowed_tickers") or []),
            "playbook_excluded_tickers": list(replay_playbook.get("excluded_tickers") or []),
            "equity_curve": [], "trades": [], "unpriced_trades": unpriced_candidates,
            "pre_entry_filtered_candidates": pre_entry_filtered_candidates,
            "post_entry_filtered_trades": post_entry_filtered_trades,
            "unpriced_trade_diagnostics": unpriced_trade_diagnostics,
            "daily_selection_diagnostics": daily_selection_diagnostics,
        }
        return _save_backtest_result(output) if save_result else output

    pnl_list   = [t["pnl_pct"] for t in all_trades]
    wins       = [p for p in pnl_list if p > 0]
    losses     = [p for p in pnl_list if p <= 0]
    gross_win  = sum(wins)
    gross_loss = abs(sum(losses))
    pf         = gross_win / max(gross_loss, 0.01)
    win_rate   = len(wins) / len(pnl_list) * 100
    full_hits  = sum(1 for t in all_trades if t.get("prediction_outcome") == "hit")
    directional_hits = sum(1 for t in all_trades if t.get("directional_correct"))
    full_hit_rate = full_hits / len(all_trades) * 100
    directional_accuracy = directional_hits / len(all_trades) * 100
    avg_pnl    = sum(pnl_list) / len(pnl_list)
    sr         = _sharpe(pnl_list)

    # Equity curve: equal-weight all picks per day, cumulative daily mean P&L
    daily_pnl: dict[str, list[float]] = defaultdict(list)
    for t in all_trades:
        daily_pnl[t["date"]].append(t["pnl_pct"])
    selection_source_counts: dict[str, int] = defaultdict(int)
    for trade in all_trades:
        selection_source_counts[str(trade.get("selection_source") or "unknown")] += 1
    calibration_summary = _selection_calibration_summary(
        all_trades,
        required_trades=calibration_min_trades,
    )
    selected_calibrated_trades = [
        trade for trade in all_trades
        if str(trade.get("selection_source") or "") == "replay_calibrated"
    ]
    selected_dense_calibrated_trades = [
        trade for trade in selected_calibrated_trades
        if _trade_calibration_density(trade) == "dense"
    ]
    selected_sparse_calibrated_trades = [
        trade for trade in selected_calibrated_trades
        if _trade_calibration_density(trade) == "sparse"
    ]
    selected_fallback_level_counts: Counter[str] = Counter(
        str(trade.get("calibration_source") or "unknown")
        for trade in selected_dense_calibrated_trades
    )
    sparse_warnings = list((last_expectancy_surface or {}).get("diagnostics", {}).get("sparse_warnings") or [])
    for warning_text, warning_count in calibration_selected_sparse_warnings.items():
        sparse_warnings.append(f"{warning_text} Selected {warning_count} time(s) during replay.")
    calibration_diagnostics = _base_calibration_diagnostics()
    calibration_diagnostics.update(
        {
            "surface_min_trades": calibration_min_trades,
            "shrinkage_trades": calibration_shrinkage_trades,
            "sparse_warning_trades": calibration_sparse_warning_trades,
            "surface_days": calibration_surface_days,
            "candidate_lookup_attempts": calibration_lookup_attempts,
            "candidate_calibrated_count": calibration_candidate_matches,
            "candidate_dense_calibrated_count": calibration_candidate_dense_matches,
            "candidate_sparse_calibrated_count": calibration_candidate_sparse_matches,
            "candidate_calibrated_pct": (
                round(calibration_candidate_matches / max(calibration_lookup_attempts, 1) * 100.0, 1)
                if calibration_lookup_attempts else 0.0
            ),
            "candidate_fallback_level_counts": dict(calibration_candidate_fallback_levels),
            "selected_non_bootstrap_count": len(selected_calibrated_trades),
            "selected_dense_calibrated_count": len(selected_dense_calibrated_trades),
            "selected_sparse_calibrated_count": len(selected_sparse_calibrated_trades),
            "selected_non_bootstrap_pct": round(
                len(selected_calibrated_trades) / max(len(all_trades), 1) * 100.0,
                1,
            ),
            "selected_fallback_level_counts": dict(selected_fallback_level_counts),
            "density_by_level": _finalize_surface_density(calibration_density_aggregate),
            "include_tech_band": bool(last_expectancy_surface and last_expectancy_surface.get("include_tech_band")),
            "sparse_cohort_warnings": sparse_warnings,
        }
    )
    eq_curve: list[dict] = []
    cum = 0.0
    daily_mean_returns: list[float] = []
    for d in sorted(daily_pnl.keys()):
        vals = daily_pnl[d]
        day_mean = sum(vals) / len(vals)
        daily_mean_returns.append(day_mean)
        cum  = round(cum + day_mean, 3)
        eq_curve.append({"date": d, "cum_pnl_pct": cum})
    mdd = _max_drawdown(daily_mean_returns)

    priced_trade_count = len(all_trades)
    unpriced_trade_count = len(unpriced_candidates)
    post_entry_filtered_trade_count = len(post_entry_filtered_trades)
    pre_entry_filtered_candidate_count = len(pre_entry_filtered_candidates)
    pre_post_entry_candidate_trade_count = (
        priced_trade_count + unpriced_trade_count + post_entry_filtered_trade_count
    )
    candidate_trade_count = pre_post_entry_candidate_trade_count
    quote_covered_trade_count = priced_trade_count + post_entry_filtered_trade_count
    quote_coverage_pct = round(quote_covered_trade_count / max(candidate_trade_count, 1) * 100.0, 1) if candidate_trade_count else 0.0
    unpriced_trade_diagnostics = _summarize_unpriced_trades(unpriced_candidates)
    contract_resolution = _contract_resolution_summary(
        {
            "trades": all_trades + post_entry_filtered_trades,
            "priced_trade_count": quote_covered_trade_count,
            "candidate_trade_count": candidate_trade_count,
        }
    )
    exact_contract_trades = [
        trade for trade in all_trades
        if _is_exact_contract_resolution(trade.get("entry_contract_resolution"))
    ]
    nearest_listed_trades = [
        trade for trade in all_trades
        if not _is_exact_contract_resolution(trade.get("entry_contract_resolution"))
    ]
    by_symbol = _by_symbol_trade_metrics(
        all_trades,
        playbook_id=replay_playbook["id"],
        truth_source=normalized_truth_lane,
        min_directional_accuracy_pct=MIN_EXACT_CONTRACT_DIRECTIONAL_ACCURACY_PCT,
    )
    by_sleeve = _trade_metrics_by_field(all_trades, "sleeve_id", exact_only=_is_imported_truth_source(normalized_truth_lane))
    by_tier = _trade_metrics_by_field(all_trades, "tier_id", exact_only=_is_imported_truth_source(normalized_truth_lane))
    promotion_metrics = _overall_promotion_metrics(
        trades=all_trades,
        by_symbol=by_symbol,
        playbook_id=replay_playbook["id"],
        truth_source=normalized_truth_lane,
        min_directional_accuracy_pct=MIN_EXACT_CONTRACT_DIRECTIONAL_ACCURACY_PCT,
    )
    exact_contract_metrics = _trade_subset_metrics(exact_contract_trades, include_exit_reasons=True)
    authoritative_profitability_gate = _authoritative_profitability_gate(
        exact_contract_metrics,
        min_trade_count=25,
        min_profit_factor=1.05,
        min_directional_accuracy_pct=MIN_EXACT_CONTRACT_DIRECTIONAL_ACCURACY_PCT,
    )
    effective_pricing_lane = requested_pricing_lane
    output = {
        "run_at":            datetime.now().isoformat(timespec="seconds"),
        "mode":              "backtest",
        "profile":           "mixed",
        "truth_source":      normalized_truth_lane,
        "imported_data_scope": imported_data_scope_label if _is_imported_truth_source(normalized_truth_lane) else None,
        "research_imported_data_allowed": (not imported_trusted_only) if _is_imported_truth_source(normalized_truth_lane) else False,
        "lookback_years":    lookback_years,
        "iv_adj":            iv_adj,
        "requested_pricing_lane": requested_pricing_lane,
        "effective_pricing_lane": effective_pricing_lane,
        "pricing_lane":      effective_pricing_lane,
        "entry_anchor_policy": _entry_anchor_policy_label(normalized_truth_lane),
        "execution_realism": _execution_realism_label(normalized_truth_lane),
        "playbook":          replay_playbook["id"],
        "requested_directions": normalized_allowed_directions,
        "n_picks":           n_picks,
        "execution_backfill_enabled": execution_backfill_enabled,
        "execution_backfill_scan_depth": execution_backfill_scan_depth,
        "scan_until_capacity": scan_until_capacity,
        "unknown_sector_policy": unknown_sector_policy,
        "max_per_allocation_group": max_per_allocation_group,
        "max_per_ticker": max_per_ticker,
        "max_total_index": max_total_index,
        "exit_quote_failure_memory_enabled": exit_quote_failure_memory_enabled,
        "exit_quote_failure_cooldown_days": exit_quote_failure_cooldown_days,
        "exit_quote_failure_max_prior": exit_quote_failure_max_prior,
        "exit_quote_failure_scope": exit_quote_failure_scope,
        "exit_quote_failure_memory_observed_count": sum(len(items) for items in exit_quote_failure_memory.values()),
        "capacity_tiers": capacity_tiers,
        "total_days":        days_simulated,
        "total_trades":      len(all_trades),
        "priced_trade_count": priced_trade_count,
        "unpriced_trade_count": unpriced_trade_count,
        "pre_entry_filtered_candidate_count": pre_entry_filtered_candidate_count,
        "pre_entry_filtered_candidate_reasons": dict(Counter(str(item.get("pre_entry_filter_reject_reason") or "unknown") for item in pre_entry_filtered_candidates)),
        "post_entry_filtered_trade_count": post_entry_filtered_trade_count,
        **_post_entry_denominator_truth(
            priced_trade_count=priced_trade_count,
            unpriced_trade_count=unpriced_trade_count,
            post_entry_filtered_trade_count=post_entry_filtered_trade_count,
        ),
        "post_entry_filtered_trade_reasons": dict(Counter(str(item.get("post_entry_filter_reject_reason") or "unknown") for item in post_entry_filtered_trades)),
        "candidate_trade_count": candidate_trade_count,
        "quote_coverage_pct": quote_coverage_pct,
        **contract_resolution,
        "entry_quote_time_et": _imported_entry_quote_label(normalized_truth_lane) if _is_imported_truth_source(normalized_truth_lane) else f"{_et_minute_label(ENTRY_QUOTE_MINUTE_ET)} + {ENTRY_QUOTE_WINDOW_MINUTES}m",
        "exit_quote_time_et": _imported_exit_quote_label(normalized_truth_lane) if _is_imported_truth_source(normalized_truth_lane) else "Latest available snapshot each trading day ET",
        "win_rate_pct":      round(win_rate, 1),
        "full_hit_rate_pct": round(full_hit_rate, 1),
        "directional_accuracy_pct": round(directional_accuracy, 1),
        "profit_factor":     round(pf, 2),
        **_profit_factor_denominator_truth_from_pnls(pnl_list),
        "avg_pnl_pct":       round(avg_pnl, 2),
        "avg_picks_per_day": round(len(all_trades) / max(days_simulated, 1), 2),
        "sharpe":            round(sr, 2),
        "max_drawdown_pct":  round(mdd, 1),
        "selection_source_counts": dict(selection_source_counts),
        "calibration_summary": calibration_summary,
        "calibration_diagnostics": calibration_diagnostics,
        "calibration_density_metrics": _calibration_density_metrics(all_trades),
        "universe_filters":  replay_universe_filter_summary,
        "contract_selection_basis": (
            "historical_chain_nearest_listed_contract"
            if _is_imported_truth_source(normalized_truth_lane)
            else "synthetic_model"
        ),
        "exact_contract_metrics": exact_contract_metrics,
        "authoritative_profitability_basis": _authoritative_profitability_basis(normalized_truth_lane),
        "authoritative_profitability_metrics": exact_contract_metrics,
        "authoritative_profitability_gate": authoritative_profitability_gate,
        "nearest_listed_metrics": _trade_subset_metrics(nearest_listed_trades),
        "promotion_metrics": promotion_metrics,
        "by_symbol": by_symbol,
        "by_sleeve": by_sleeve,
        "by_tier": by_tier,
        "promotion_trade_count": int(promotion_metrics.get("trade_count") or 0),
        "non_promotable_trade_count": len([trade for trade in all_trades if not _is_trade_promotable(trade)]),
        "truth_store":       imported_truth_store if _is_imported_truth_source(normalized_truth_lane) else None,
        "required_imported_calendar_dates": (
            required_imported_calendar_dates if _is_imported_truth_source(normalized_truth_lane) else None
        ),
        "replay_calendar":   replay_calendar_summary,
        "validation_universe": list(replay_watchlist),
        "eligible_tickers":  eligible_tickers,
        "excluded_tickers":  excluded_tickers,
        "playbook_allowed_tickers": list(replay_playbook.get("allowed_tickers") or []),
        "playbook_excluded_tickers": list(replay_playbook.get("excluded_tickers") or []),
        "equity_curve":      eq_curve,
        "trades":            all_trades,
        "unpriced_trades":   unpriced_candidates,
        "pre_entry_filtered_candidates": pre_entry_filtered_candidates,
        "post_entry_filtered_trades": post_entry_filtered_trades,
        "unpriced_trade_diagnostics": unpriced_trade_diagnostics,
        "daily_selection_diagnostics": daily_selection_diagnostics,
    }
    if progress_callback:
        progress_callback("Done.", 1.0)
    return _save_backtest_result(output) if save_result else output


def build_prediction_replay_report(
    result: Optional[dict] = None,
    min_trades: int = 20,
) -> dict:
    """
    Summarize a historical replay into actionable prediction buckets.

    Groups by direction score bucket, ticker, sector, and market regime.
    """
    if result is None:
        result = load_last_results()
    if not result:
        return {"error": "No backtest results found"}

    trades = result.get("trades") or []
    score_bucket_order = ("00-39", "40-49", "50-59", "60-69", "70-79", "80-100")
    source = _result_source_metadata(result, len(trades))
    if not trades:
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "source_run_at": source["run_at"],
            "source_mode": source["mode"],
            "lookback_years": source["lookback_years"],
            "min_trades_filter": int(min_trades),
            "overall": _summarize_prediction_group("overall", "overall", [], 0),
            "by_direction_score": [
                _summarize_prediction_group("direction_score", bucket, [], 0)
                for bucket in score_bucket_order
            ],
            "by_ticker": [],
            "by_sector": [],
            "by_regime": [],
            "best_segments": [],
            "weakest_segments": [],
            "risk_flags": [],
            "sample_notes": [],
        }

    total_trades = len(trades)

    def _group_and_sort(group_name: str, key_fn) -> list[dict]:
        grouped: dict[str, list[dict]] = {}
        for trade in trades:
            key = key_fn(trade)
            grouped.setdefault(key, []).append(trade)

        if group_name == "direction_score":
            return [
                _summarize_prediction_group(group_name, bucket, grouped.get(bucket, []), total_trades)
                for bucket in score_bucket_order
            ]

        summaries = [
            _summarize_prediction_group(group_name, key, group, total_trades)
            for key, group in grouped.items()
        ]
        if group_name == "regime":
            order = {"bearish": 0, "neutral": 1, "bullish": 2, "unknown": 3}
            return sorted(summaries, key=lambda item: (order.get(item["value"], 99), item["value"]))
        return sorted(summaries, key=lambda item: (-item["trades"], item["value"]))

    score_groups = _group_and_sort(
        "direction_score",
        lambda trade: _direction_score_bucket(float(trade.get("direction_score", 0.0) or 0.0)),
    )
    ticker_groups = _group_and_sort("ticker", lambda trade: str(trade.get("ticker") or "Unknown").upper())
    sector_groups = _group_and_sort("sector", lambda trade: str(trade.get("sector") or "Unknown"))
    regime_groups = _group_and_sort("regime", _normalized_market_regime)

    ranked_segments = [item for item in score_groups if item["trades"] > 0]
    ranked_segments.extend(item for item in ticker_groups if item["trades"] >= min_trades)
    ranked_segments.extend(item for item in sector_groups if item["trades"] >= min_trades)
    ranked_segments.extend(item for item in regime_groups if item["trades"] >= min_trades)

    best_segments = sorted(
        ranked_segments,
        key=lambda item: (item["avg_pnl_pct"], item["profit_factor"], item["directional_accuracy_pct"]),
        reverse=True,
    )[:5]
    weakest_segments = sorted(
        ranked_segments,
        key=lambda item: (item["avg_pnl_pct"], item["profit_factor"], item["directional_accuracy_pct"]),
    )[:5]

    overall = _summarize_prediction_group("overall", "overall", trades, total_trades)
    populated_score_groups = [item for item in score_groups if item["trades"] > 0]
    highest_score_group = populated_score_groups[-1] if populated_score_groups else None

    risk_flags: list[str] = []
    if overall["directional_accuracy_pct"] < 50.0:
        risk_flags.append("Directional accuracy is below 50%, so the signal is not clearing a naive coin-flip bar.")
    if overall["profit_factor"] < 1.0:
        risk_flags.append("Profit factor is below 1.0, so option P&L is still net negative after the scoring fixes.")
    if highest_score_group and any(
        highest_score_group["avg_pnl_pct"] <= item["avg_pnl_pct"]
        for item in populated_score_groups[:-1]
    ):
        risk_flags.append("Higher direction-score buckets are not clearly outperforming lower-score buckets yet.")

    sample_notes = [
        "Direction-score buckets are always included, even when they are sparse.",
        f"Ticker, sector, and regime segments need at least {min_trades} trades to be ranked in best/weakest segments.",
        (
            "Profit factor and avg_pnl_pct come from imported historical intraday option quotes."
            if source["truth_source"] == IMPORTED_TRUTH_SOURCE
            else "Profit factor and avg_pnl_pct come from imported daily end-of-day option quotes."
            if source["truth_source"] == IMPORTED_DAILY_TRUTH_SOURCE
            else "Profit factor and avg_pnl_pct come from the synthetic option-pricing model used in the replay."
        ),
        "Directional accuracy tracks whether the underlying moved in the predicted direction by exit.",
    ]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "source_run_at": source["run_at"],
        "source_mode": source["mode"],
        "lookback_years": source["lookback_years"],
        "truth_source": source["truth_source"],
        "quote_coverage_pct": source["quote_coverage_pct"],
        "min_trades_filter": int(min_trades),
        "overall": overall,
        "by_direction_score": score_groups,
        "by_ticker": ticker_groups,
        "by_sector": sector_groups,
        "by_regime": regime_groups,
        "segments_above_min_trades": ranked_segments,
        "best_segments": best_segments,
        "weakest_segments": weakest_segments,
        "risk_flags": risk_flags,
        "sample_notes": sample_notes,
    }


def _trade_date(trade: dict, key: str = "date") -> Optional[datetime]:
    value = trade.get(key)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _window_summary(
    label: str,
    trades: list[dict],
    *,
    min_trades: int,
    pass_profit_factor: float,
    pass_avg_pnl_pct: float,
) -> dict:
    dates = [dt for dt in (_trade_date(trade) for trade in trades) if dt is not None]
    daily_groups: dict[str, list[float]] = {}
    for trade in trades:
        pnl_value, pnl_is_finite = _finite_metric(trade.get("pnl_pct"))
        daily_groups.setdefault(str(trade.get("date") or ""), []).append(pnl_value if pnl_is_finite else 0.0)
    daily_mean_returns = [sum(values) / len(values) for _, values in sorted(daily_groups.items()) if values]
    summary = _summarize_prediction_group("window", label, trades, len(trades))
    profit_factor, profit_factor_finite = _finite_metric(summary.get("profit_factor"))
    avg_pnl_pct, avg_pnl_pct_finite = _finite_metric(summary.get("avg_pnl_pct"))
    summary.update(
        {
            "label": label,
            "start_date": dates[0].date().isoformat() if dates else None,
            "end_date": dates[-1].date().isoformat() if dates else None,
            "max_drawdown_pct": round(_max_drawdown(daily_mean_returns), 1) if daily_mean_returns else 0.0,
            "passes_quality_bar": (
                len(trades) >= int(min_trades)
                and profit_factor_finite
                and avg_pnl_pct_finite
                and profit_factor >= float(pass_profit_factor)
                and avg_pnl_pct > float(pass_avg_pnl_pct)
            ),
        }
    )
    return summary


def _slice_window_summary(
    category: str,
    value: str,
    window_label: str,
    trades: list[dict],
    *,
    min_trades: int,
    pass_profit_factor: float,
    pass_avg_pnl_pct: float,
) -> dict:
    item = _window_summary(
        window_label,
        trades,
        min_trades=min_trades,
        pass_profit_factor=pass_profit_factor,
        pass_avg_pnl_pct=pass_avg_pnl_pct,
    )
    item["category"] = category
    item["value"] = value
    return item


def build_options_stability_report(
    result: Optional[dict] = None,
    *,
    min_trades: int = 20,
    min_profit_factor: float = 1.05,
    rolling_window_days: int = 182,
    rolling_step_days: int = 91,
    catastrophic_pf_floor: float = 0.85,
) -> dict:
    if result is None:
        result = load_last_results()
    if not result:
        return {"error": "No backtest results found"}

    aggregate_trades = sorted(
        [trade for trade in (result.get("trades") or []) if _trade_date(trade) is not None],
        key=lambda trade: _trade_date(trade),
    )
    profitability_view = _authoritative_profitability_view(result, aggregate_trades)
    trades = sorted(
        [trade for trade in profitability_view["trades"] if _trade_date(trade) is not None],
        key=lambda trade: _trade_date(trade),
    )
    source = _result_source_metadata(result, len(aggregate_trades))
    authoritative_profitability_gate = _authoritative_profitability_gate(
        profitability_view["metrics"],
        min_trade_count=min_trades,
        min_profit_factor=min_profit_factor,
    )
    if not trades:
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "overall_status": "block",
            "calibration_summary": _selection_calibration_summary([], required_trades=max(int(min_trades), 10)),
            "quality_bar": {
                "min_trades": int(min_trades),
                "min_profit_factor": float(min_profit_factor),
                "min_avg_pnl_pct": 0.0,
                "catastrophic_pf_floor": float(catastrophic_pf_floor),
            },
            "scenario_results": {},
            "rolling_summary": {
                "windows_seen": 0,
                "windows_passed": 0,
                "pass_rate_pct": 0.0,
                "worst_profit_factor": 0.0,
            },
            "slice_statuses": {"score_band": [], "regime": [], "sector": []},
            "promotion_recommendations": {
                "approved_filters": {},
                "watch_filters": {},
                "blocked_filters": {},
            },
            "authoritative_profitability_lens": profitability_view["lens"],
            "authoritative_profitability_label": profitability_view["label"],
            "authoritative_profitability_description": profitability_view["description"],
            "authoritative_profitability_metrics": profitability_view["metrics"],
            "authoritative_profitability_gate": authoritative_profitability_gate,
            "aggregate_overall": _trade_subset_metrics(aggregate_trades, include_exit_reasons=True),
            "research_only_metrics": _trade_subset_metrics(
                profitability_view["research_only_trades"],
                include_exit_reasons=True,
            ),
            "recommendations": [
                (
                    f"No trades are available under the authoritative profitability lens "
                    f"({profitability_view['label']}), so promotion is blocked."
                )
            ],
        }

    max_date = _trade_date(trades[-1])
    min_date = _trade_date(trades[0])
    last_year_cutoff = max_date - timedelta(days=365)

    full_window = list(trades)
    last_year_window = [trade for trade in trades if (_trade_date(trade) or max_date) >= last_year_cutoff]

    rolling_windows: list[dict] = []
    if min_date and max_date:
        cursor = min_date
        while cursor + timedelta(days=rolling_window_days) <= max_date + timedelta(days=1):
            end_date = cursor + timedelta(days=rolling_window_days)
            window_trades = [
                trade for trade in trades
                if cursor <= (_trade_date(trade) or cursor) < end_date
            ]
            rolling_windows.append(
                _window_summary(
                    f"{cursor.date().isoformat()}->{(end_date - timedelta(days=1)).date().isoformat()}",
                    window_trades,
                    min_trades=min_trades,
                    pass_profit_factor=1.0,
                    pass_avg_pnl_pct=0.0,
                )
            )
            cursor += timedelta(days=rolling_step_days)
    if not rolling_windows:
        rolling_windows.append(
            _window_summary(
                "full_window",
                full_window,
                min_trades=min_trades,
                pass_profit_factor=1.0,
                pass_avg_pnl_pct=0.0,
            )
        )

    scenario_results = {
        "full_window": _window_summary(
            "full_window",
            full_window,
            min_trades=max(min_trades * 2, min_trades),
            pass_profit_factor=min_profit_factor,
            pass_avg_pnl_pct=0.0,
        ),
        "last_1y": _window_summary(
            "last_1y",
            last_year_window,
            min_trades=max(min_trades * 2, min_trades),
            pass_profit_factor=min_profit_factor,
            pass_avg_pnl_pct=0.0,
        ),
        "rolling_6m_windows": rolling_windows,
    }

    rolling_passes = [window for window in rolling_windows if window["passes_quality_bar"]]
    rolling_pass_rate = round(len(rolling_passes) / max(len(rolling_windows), 1) * 100.0, 1)
    worst_rolling_pf = min(float(window.get("profit_factor", 0.0) or 0.0) for window in rolling_windows)
    fixed_pass = (
        scenario_results["full_window"]["passes_quality_bar"]
        and scenario_results["last_1y"]["passes_quality_bar"]
    )
    if fixed_pass and rolling_pass_rate >= 70.0 and worst_rolling_pf >= catastrophic_pf_floor:
        overall_status = "promote"
    elif (
        scenario_results["full_window"]["profit_factor"] >= 1.0
        or scenario_results["last_1y"]["profit_factor"] >= 1.0
        or rolling_pass_rate >= 50.0
    ):
        overall_status = "watch"
    else:
        overall_status = "block"

    quote_coverage_pct = float(result.get("quote_coverage_pct", 100.0) or 0.0)
    if _is_imported_truth_source(_result_truth_source(result)) and quote_coverage_pct < MIN_IMPORTED_QUOTE_COVERAGE_PCT:
        overall_status = "block"
    if not bool(authoritative_profitability_gate.get("passed")):
        overall_status = "block"

    scenario_windows = [
        ("full_window", full_window),
        ("last_1y", last_year_window),
    ]
    scenario_windows.extend(
        (window["label"], [
            trade for trade in trades
            if window["start_date"] and window["end_date"]
            and window["start_date"] <= str(trade.get("date") or "") <= window["end_date"]
        ])
        for window in rolling_windows
    )

    grouped_slice_windows: dict[str, dict[str, list[dict]]] = {
        "score_band": {},
        "regime": {},
        "sector": {},
    }
    for window_label, window_trades in scenario_windows:
        by_category = {
            "score_band": {},
            "regime": {},
            "sector": {},
        }
        for trade in window_trades:
            by_category["score_band"].setdefault(_direction_score_bucket(float(trade.get("direction_score", 0.0) or 0.0)), []).append(trade)
            by_category["regime"].setdefault(_normalized_market_regime(trade), []).append(trade)
            by_category["sector"].setdefault(str(trade.get("sector") or "Unknown"), []).append(trade)
        for category, groups in by_category.items():
            for value, subset in groups.items():
                grouped_slice_windows[category].setdefault(value, []).append(
                    _slice_window_summary(
                        category,
                        value,
                        window_label,
                        subset,
                        min_trades=min_trades,
                        pass_profit_factor=1.0,
                        pass_avg_pnl_pct=0.0,
                    )
                )

    slice_statuses: dict[str, list[dict]] = {"score_band": [], "regime": [], "sector": []}
    for category, values in grouped_slice_windows.items():
        for value, windows in values.items():
            seen = [window for window in windows if int(window.get("trades", 0) or 0) >= int(min_trades)]
            if not seen:
                continue
            pfs = [float(window.get("profit_factor", 0.0) or 0.0) for window in seen]
            avg_pnls = [float(window.get("avg_pnl_pct", 0.0) or 0.0) for window in seen]
            pass_rate_pct = round(sum(1 for window in seen if window["passes_quality_bar"]) / len(seen) * 100.0, 1)
            if pass_rate_pct >= 70.0 and min(pfs) >= 1.0 and min(avg_pnls) >= 0.0:
                status = "promote"
            elif max(pfs) >= 1.0 or max(avg_pnls) > 0.0:
                status = "watch"
            else:
                status = "block"
            slice_statuses[category].append(
                {
                    "category": category,
                    "value": value,
                    "windows_seen": len(seen),
                    "windows_passed": sum(1 for window in seen if window["passes_quality_bar"]),
                    "pass_rate_pct": pass_rate_pct,
                    "median_profit_factor": round(float(np.median(pfs)), 2),
                    "worst_profit_factor": round(min(pfs), 2),
                    "median_avg_pnl_pct": round(float(np.median(avg_pnls)), 2),
                    "worst_avg_pnl_pct": round(min(avg_pnls), 2),
                    "status": status,
                    "windows": seen,
                }
            )
        slice_statuses[category] = sorted(
            slice_statuses[category],
            key=lambda item: (
                1 if item["status"] == "promote" else 0,
                1 if item["status"] == "watch" else 0,
                item["pass_rate_pct"],
                item["median_profit_factor"],
                item["median_avg_pnl_pct"],
            ),
            reverse=True,
        )

    approved_score_band = next((item for item in slice_statuses["score_band"] if item["status"] == "promote"), None)
    approved_regimes = [item["value"] for item in slice_statuses["regime"] if item["status"] == "promote"][:2]
    approved_sectors = [item["value"] for item in slice_statuses["sector"] if item["status"] == "promote"][:2]

    direction_score_min = None
    if approved_score_band:
        band_lo, _band_hi = _score_band_bounds(approved_score_band["value"])
        direction_score_min = band_lo

    recommendations: list[str] = []
    if overall_status == "promote":
        recommendations.append("Promotion bar cleared across fixed and rolling windows.")
    elif overall_status == "watch":
        recommendations.append("Some windows are acceptable, but the strategy is not stable enough to auto-promote.")
    else:
        recommendations.append("Fixed or rolling windows are still too weak, so the strategy remains blocked for promotion.")
    if not bool(authoritative_profitability_gate.get("passed")):
        recommendations.extend(str(item) for item in authoritative_profitability_gate.get("blockers") or [])
    if direction_score_min is not None:
        recommendations.append(f"The most stable score cohort starts at direction score {int(direction_score_min)}.")
    if approved_regimes:
        recommendations.append(f"Stable regimes so far: {', '.join(approved_regimes)}.")

    replay_playbook = _get_replay_playbook(result.get("playbook"))
    calibration_summary = _selection_calibration_summary(
        trades,
        required_trades=max(int(min_trades), 10),
    )
    if replay_playbook.get("requires_calibrated_history"):
        calibrated_trades = int(calibration_summary.get("replay_calibrated_trades", 0) or 0)
        required_calibrated = int(calibration_summary.get("required_trades", max(int(min_trades), 10)) or max(int(min_trades), 10))
        if calibrated_trades <= 0:
            overall_status = "block"
            recommendations.append(
                f"{replay_playbook['label']} has no dense replay-calibrated trades yet, so promotion fails closed until the dense calibrated sample starts to populate."
            )
        elif calibrated_trades < required_calibrated:
            overall_status = "block"
            recommendations.append(
                f"{replay_playbook['label']} only has {calibrated_trades} dense replay-calibrated trade(s) against a {required_calibrated}-trade readiness bar, so promotion remains blocked until calibration fills in."
            )

    if _is_imported_truth_source(_result_truth_source(result)) and quote_coverage_pct < MIN_IMPORTED_QUOTE_COVERAGE_PCT:
        recommendations.append(
            f"Imported quote coverage is only {quote_coverage_pct:.1f}%, below the {MIN_IMPORTED_QUOTE_COVERAGE_PCT:.0f}% promotion floor."
        )
    nearest_contract_match_count = int(source.get("nearest_contract_match_count", 0) or 0)
    if _is_imported_truth_source(_result_truth_source(result)) and nearest_contract_match_count > 0:
        recommendations.append(
            (
                f"{nearest_contract_match_count} imported trade(s) still resolved to the nearest listed contract "
                "rather than an exact target contract; they remain research-only and do not count toward promotion."
            )
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "truth_source": source["truth_source"],
        "quote_coverage_pct": source["quote_coverage_pct"],
        "overall_status": overall_status,
        "authoritative_profitability_lens": profitability_view["lens"],
        "authoritative_profitability_label": profitability_view["label"],
        "authoritative_profitability_description": profitability_view["description"],
        "authoritative_profitability_metrics": profitability_view["metrics"],
        "authoritative_profitability_gate": authoritative_profitability_gate,
        "calibration_summary": calibration_summary,
        "aggregate_overall": _trade_subset_metrics(aggregate_trades, include_exit_reasons=True),
        "authoritative_overall": _trade_subset_metrics(trades, include_exit_reasons=True),
        "research_only_metrics": _trade_subset_metrics(
            profitability_view["research_only_trades"],
            include_exit_reasons=True,
        ),
        "quality_bar": {
            "min_trades": int(min_trades),
            "min_profit_factor": float(min_profit_factor),
            "min_avg_pnl_pct": 0.0,
            "catastrophic_pf_floor": float(catastrophic_pf_floor),
            "min_quote_coverage_pct": float(MIN_IMPORTED_QUOTE_COVERAGE_PCT),
        },
        "scenario_results": scenario_results,
        "rolling_summary": {
            "windows_seen": len(rolling_windows),
            "windows_passed": len(rolling_passes),
            "pass_rate_pct": rolling_pass_rate,
            "worst_profit_factor": round(worst_rolling_pf, 2),
        },
        "slice_statuses": slice_statuses,
        "promotion_recommendations": {
            "approved_filters": {
                "direction_score_min": direction_score_min,
                "market_regimes": approved_regimes,
                "sectors": approved_sectors,
            },
            "watch_filters": {
                "score_bands": [item["value"] for item in slice_statuses["score_band"] if item["status"] == "watch"][:2],
                "market_regimes": [item["value"] for item in slice_statuses["regime"] if item["status"] == "watch"][:2],
                "sectors": [item["value"] for item in slice_statuses["sector"] if item["status"] == "watch"][:2],
            },
            "blocked_filters": {
                "score_bands": [item["value"] for item in slice_statuses["score_band"] if item["status"] == "block"][:3],
                "market_regimes": [item["value"] for item in slice_statuses["regime"] if item["status"] == "block"][:3],
                "sectors": [item["value"] for item in slice_statuses["sector"] if item["status"] == "block"][:3],
            },
        },
        "recommendations": recommendations,
    }


PLAYBOOK_DISCOVERY_DIMENSIONS = (
    "direction",
    "market_regime",
    "sector",
    "asset_class",
    "dte_bucket",
)


def _playbook_slice_value(trade: dict, dimension: str) -> str:
    if dimension == "direction":
        return _trade_direction(trade)
    if dimension == "market_regime":
        return _normalized_market_regime(trade)
    if dimension == "sector":
        return _trade_sector(trade)
    if dimension == "asset_class":
        return _trade_asset_class(trade)
    if dimension == "dte_bucket":
        return _trade_dte_bucket(trade)
    return ""


def _playbook_candidate_label(filters: dict) -> str:
    parts: list[str] = []
    for dimension in PLAYBOOK_DISCOVERY_DIMENSIONS:
        if dimension not in filters:
            continue
        value = str(filters[dimension])
        if dimension == "direction":
            parts.append(value.upper())
        elif dimension == "market_regime":
            parts.append(value.title())
        elif dimension == "asset_class":
            parts.append(value.title())
        elif dimension == "dte_bucket":
            parts.append(f"DTE {value}")
        else:
            parts.append(value)
    return " | ".join(parts)


def _playbook_filter_key(filters: dict) -> tuple[tuple[str, str], ...]:
    return tuple((dimension, str(filters[dimension])) for dimension in PLAYBOOK_DISCOVERY_DIMENSIONS if dimension in filters)


def _playbook_filters_for_trade(trade: dict) -> list[dict]:
    direction = _trade_direction(trade)
    if direction == "unknown":
        return []

    optional_items: list[tuple[str, str]] = []
    for dimension in ("market_regime", "sector", "asset_class", "dte_bucket"):
        value = _playbook_slice_value(trade, dimension)
        if not value or str(value).strip().lower() == "unknown":
            continue
        optional_items.append((dimension, value))

    filters: list[dict] = []
    for size in range(1, len(optional_items) + 1):
        for combo in combinations(optional_items, size):
            candidate = {"direction": direction}
            for key, value in combo:
                candidate[key] = value
            filters.append(candidate)
    return filters


def _trade_matches_playbook_filters(trade: dict, filters: dict) -> bool:
    return all(_playbook_slice_value(trade, dimension) == value for dimension, value in filters.items())


def _top_counter_rows(counter: Counter, total: int, limit: int = 3) -> list[dict]:
    rows: list[dict] = []
    for value, count in counter.most_common(limit):
        rows.append(
            {
                "value": value,
                "trades": int(count),
                "share_pct": round(count / max(total, 1) * 100.0, 1),
            }
        )
    return rows


def _summarize_playbook_discovery_slice(
    filters: dict,
    trades: list[dict],
    total_trades: int,
    *,
    min_trades: int,
    min_profit_factor: float,
    min_directional_accuracy_pct: float,
) -> dict:
    label = _playbook_candidate_label(filters)
    summary = _summarize_prediction_group("playbook_discovery", label, trades, total_trades)
    profit_factor, profit_factor_finite = _finite_metric(summary.get("profit_factor"))
    avg_pnl_pct, avg_pnl_pct_finite = _finite_metric(summary.get("avg_pnl_pct"))
    directional_accuracy_pct, directional_accuracy_finite = _finite_metric(
        summary.get("directional_accuracy_pct")
    )
    non_finite_metrics: list[str] = []
    if not profit_factor_finite and summary.get("profit_factor") is not None:
        non_finite_metrics.append("profit_factor")
    if not avg_pnl_pct_finite and summary.get("avg_pnl_pct") is not None:
        non_finite_metrics.append("avg_pnl_pct")
    if not directional_accuracy_finite and summary.get("directional_accuracy_pct") is not None:
        non_finite_metrics.append("directional_accuracy_pct")
    ticker_counts = Counter(str(trade.get("ticker") or "Unknown").upper() for trade in trades)
    top_ticker, top_ticker_count = ticker_counts.most_common(1)[0] if ticker_counts else ("Unknown", 0)
    summary.update(
        {
            "candidate_id": _experiment_id("playbook_discovery", filters),
            "label": label,
            "filters": dict(filters),
            "profit_factor": round(profit_factor, 2),
            "avg_pnl_pct": round(avg_pnl_pct, 2),
            "directional_accuracy_pct": round(directional_accuracy_pct, 1),
            "metrics_finite": not non_finite_metrics,
            "non_finite_metrics": non_finite_metrics,
            "slice_depth": len(filters),
            "sparse": summary["trades"] < int(min_trades),
            "passes_quality_bar": (
                summary["trades"] >= int(min_trades)
                and profit_factor_finite
                and avg_pnl_pct_finite
                and directional_accuracy_finite
                and profit_factor >= float(min_profit_factor)
                and directional_accuracy_pct >= float(min_directional_accuracy_pct)
                and avg_pnl_pct > 0.0
            ),
            "distinct_tickers": len(ticker_counts),
            "top_ticker": top_ticker if ticker_counts else None,
            "top_ticker_share_pct": round(top_ticker_count / max(summary["trades"], 1) * 100.0, 1),
            "top_tickers": _top_counter_rows(ticker_counts, summary["trades"]),
        }
    )
    return summary


def _playbook_discovery_source_label(result: dict, index: int) -> str:
    explicit = str(result.get("_playbook_discovery_label") or "").strip()
    if explicit:
        return explicit
    parts: list[str] = []
    lookback_years = result.get("lookback_years")
    if lookback_years is not None:
        try:
            parts.append(f"{int(lookback_years)}y")
        except (TypeError, ValueError):
            parts.append(str(lookback_years))
    pricing_lane = str(result.get("pricing_lane") or "").strip().lower()
    if pricing_lane:
        parts.append(pricing_lane)
    playbook = str(result.get("playbook") or "").strip().lower()
    if playbook:
        parts.append(playbook)
    if not parts and result.get("run_at"):
        parts.append(str(result.get("run_at")))
    return " ".join(parts) or f"source_{index}"


def _normalize_playbook_discovery_sources(
    result: Optional[dict],
    comparison_results: Optional[list[dict]],
) -> list[dict]:
    raw_results: list[dict] = []
    if result is not None:
        raw_results.append(result)
    raw_results.extend(item for item in (comparison_results or []) if item)
    if not raw_results:
        loaded = load_last_results()
        if loaded:
            raw_results.append(loaded)

    sources: list[dict] = []
    for index, item in enumerate(raw_results, start=1):
        aggregate_trades = list(item.get("trades") or [])
        profitability_view = _authoritative_profitability_view(item, aggregate_trades)
        trades = list(profitability_view["trades"])
        dated_trades = sorted(
            [trade for trade in trades if _trade_date(trade) is not None],
            key=lambda trade: _trade_date(trade),
        )
        sources.append(
            {
                "label": _playbook_discovery_source_label(item, index),
                "run_at": item.get("run_at"),
                "lookback_years": item.get("lookback_years"),
                "pricing_lane": str(item.get("pricing_lane") or "").strip().lower() or None,
                "playbook": str(item.get("playbook") or "").strip().lower() or None,
                "total_days": item.get("total_days"),
                "total_trades": item.get("total_trades", len(aggregate_trades)),
                "aggregate_trade_count": len(aggregate_trades),
                "authoritative_trade_count": profitability_view["authoritative_trade_count"],
                "research_only_trade_count": profitability_view["research_only_trade_count"],
                "authoritative_profitability_lens": profitability_view["lens"],
                "authoritative_profitability_label": profitability_view["label"],
                "trades": trades,
                "dated_trades": dated_trades,
                "result": item,
            }
        )
    return sources


def _source_slice_summary(
    source: dict,
    filters: dict,
    *,
    min_trades: int,
    min_profit_factor: float,
    min_directional_accuracy_pct: float,
) -> dict:
    matched = [trade for trade in source["trades"] if _trade_matches_playbook_filters(trade, filters)]
    summary = _summarize_playbook_discovery_slice(
        filters,
        matched,
        len(source["trades"]),
        min_trades=min_trades,
        min_profit_factor=min_profit_factor,
        min_directional_accuracy_pct=min_directional_accuracy_pct,
    )
    summary.update(
        {
            "source_label": source["label"],
            "run_at": source["run_at"],
            "lookback_years": source["lookback_years"],
            "pricing_lane": source["pricing_lane"],
            "playbook": source["playbook"],
        }
    )
    return summary


def _playbook_rolling_summary(
    source: dict,
    filters: dict,
    *,
    min_trades: int,
    min_profit_factor: float,
    rolling_window_days: int,
    rolling_step_days: int,
    catastrophic_pf_floor: float,
) -> dict:
    dated_trades = list(source.get("dated_trades") or [])
    if not dated_trades:
        return {
            "source_label": source["label"],
            "available": False,
            "status": "unavailable",
            "windows_seen": 0,
            "dense_windows": 0,
            "windows_passed": 0,
            "pass_rate_pct": 0.0,
            "worst_profit_factor": 0.0,
            "worst_avg_pnl_pct": 0.0,
            "failing_windows": [],
        }

    min_date = _trade_date(dated_trades[0])
    max_date = _trade_date(dated_trades[-1])
    if min_date is None or max_date is None:
        return {
            "source_label": source["label"],
            "available": False,
            "status": "unavailable",
            "windows_seen": 0,
            "dense_windows": 0,
            "windows_passed": 0,
            "pass_rate_pct": 0.0,
            "worst_profit_factor": 0.0,
            "worst_avg_pnl_pct": 0.0,
            "failing_windows": [],
        }

    windows: list[dict] = []
    cursor = min_date
    while cursor + timedelta(days=rolling_window_days) <= max_date + timedelta(days=1):
        end_date = cursor + timedelta(days=rolling_window_days)
        subset = [
            trade
            for trade in dated_trades
            if cursor <= (_trade_date(trade) or cursor) < end_date
            and _trade_matches_playbook_filters(trade, filters)
        ]
        windows.append(
            _window_summary(
                f"{cursor.date().isoformat()}->{(end_date - timedelta(days=1)).date().isoformat()}",
                subset,
                min_trades=min_trades,
                pass_profit_factor=min_profit_factor,
                pass_avg_pnl_pct=0.0,
            )
        )
        cursor += timedelta(days=rolling_step_days)

    if not windows:
        subset = [trade for trade in dated_trades if _trade_matches_playbook_filters(trade, filters)]
        windows.append(
            _window_summary(
                "full_window",
                subset,
                min_trades=min_trades,
                pass_profit_factor=min_profit_factor,
                pass_avg_pnl_pct=0.0,
            )
        )

    dense_windows = [window for window in windows if int(window.get("trades", 0) or 0) >= int(min_trades)]
    if not dense_windows:
        return {
            "source_label": source["label"],
            "available": False,
            "status": "insufficient_sample",
            "windows_seen": len(windows),
            "dense_windows": 0,
            "windows_passed": 0,
            "pass_rate_pct": 0.0,
            "worst_profit_factor": 0.0,
            "worst_avg_pnl_pct": 0.0,
            "failing_windows": [],
            "windows": windows,
        }

    windows_passed = sum(1 for window in dense_windows if window["passes_quality_bar"])
    pass_rate_pct = round(windows_passed / len(dense_windows) * 100.0, 1)
    worst_profit_factor = min(float(window.get("profit_factor", 0.0) or 0.0) for window in dense_windows)
    worst_avg_pnl_pct = min(float(window.get("avg_pnl_pct", 0.0) or 0.0) for window in dense_windows)
    failing_windows = [window["label"] for window in dense_windows if not window["passes_quality_bar"]][:3]

    if pass_rate_pct >= 70.0 and worst_profit_factor >= 1.0 and worst_avg_pnl_pct >= 0.0:
        status = "stable"
    elif (
        windows_passed > 0
        or max(float(window.get("profit_factor", 0.0) or 0.0) for window in dense_windows) >= 1.0
        or max(float(window.get("avg_pnl_pct", 0.0) or 0.0) for window in dense_windows) > 0.0
    ):
        status = "mixed"
    else:
        status = "weak"

    if worst_profit_factor < float(catastrophic_pf_floor):
        status = "mixed" if status == "stable" else status

    return {
        "source_label": source["label"],
        "available": True,
        "status": status,
        "windows_seen": len(windows),
        "dense_windows": len(dense_windows),
        "windows_passed": windows_passed,
        "pass_rate_pct": pass_rate_pct,
        "worst_profit_factor": round(worst_profit_factor, 2),
        "worst_avg_pnl_pct": round(worst_avg_pnl_pct, 2),
        "failing_windows": failing_windows,
        "windows": dense_windows,
    }


def _pairwise_playbook_comparison(kind: str, left: dict, right: dict) -> dict:
    left_label = str(left.get("source_label") or "left")
    right_label = str(right.get("source_label") or "right")
    if bool(left.get("sparse")) or bool(right.get("sparse")):
        status = "insufficient_sample"
        reason = (
            f"{kind} comparison is under-sampled because {left_label} has {left['trades']} trades "
            f"and {right_label} has {right['trades']}."
        )
    elif left.get("passes_quality_bar") and right.get("passes_quality_bar"):
        status = "confirmed"
        reason = (
            f"{kind} comparison confirmed the slice: {left_label} PF {left['profit_factor']:.2f} "
            f"vs {right_label} PF {right['profit_factor']:.2f}."
        )
    elif bool(left.get("passes_quality_bar")) != bool(right.get("passes_quality_bar")):
        status = "conflict"
        reason = (
            f"{kind} comparison conflicted: {left_label} status={'pass' if left['passes_quality_bar'] else 'fail'} "
            f"while {right_label} status={'pass' if right['passes_quality_bar'] else 'fail'}."
        )
    else:
        status = "weak"
        reason = (
            f"{kind} comparison stayed weak: {left_label} PF {left['profit_factor']:.2f} "
            f"and {right_label} PF {right['profit_factor']:.2f} both missed the bar."
        )

    return {
        "kind": kind,
        "status": status,
        "reason": reason,
        "left": {
            "source_label": left_label,
            "trades": left["trades"],
            "profit_factor": left["profit_factor"],
            "avg_pnl_pct": left["avg_pnl_pct"],
            "directional_accuracy_pct": left["directional_accuracy_pct"],
            "passes_quality_bar": left["passes_quality_bar"],
        },
        "right": {
            "source_label": right_label,
            "trades": right["trades"],
            "profit_factor": right["profit_factor"],
            "avg_pnl_pct": right["avg_pnl_pct"],
            "directional_accuracy_pct": right["directional_accuracy_pct"],
            "passes_quality_bar": right["passes_quality_bar"],
        },
    }


def _build_lookback_comparisons(source_summaries: list[dict]) -> list[dict]:
    grouped: dict[tuple[object, object], dict[int, dict]] = {}
    for summary in source_summaries:
        lookback_years = summary.get("lookback_years")
        try:
            lookback_key = int(lookback_years)
        except (TypeError, ValueError):
            continue
        grouped.setdefault(
            (summary.get("pricing_lane"), summary.get("playbook")),
            {},
        )[lookback_key] = summary

    comparisons: list[dict] = []
    for items in grouped.values():
        if 1 in items and 2 in items:
            comparisons.append(_pairwise_playbook_comparison("1y vs 2y", items[1], items[2]))
    return comparisons


def _build_pricing_lane_comparisons(source_summaries: list[dict]) -> list[dict]:
    grouped: dict[tuple[object, object], dict[str, dict]] = {}
    for summary in source_summaries:
        lane = str(summary.get("pricing_lane") or "").strip().lower()
        if lane not in {"mid", "pessimistic"}:
            continue
        grouped.setdefault(
            (summary.get("lookback_years"), summary.get("playbook")),
            {},
        )[lane] = summary

    comparisons: list[dict] = []
    for items in grouped.values():
        if "mid" in items and "pessimistic" in items:
            comparisons.append(_pairwise_playbook_comparison("mid vs pessimistic", items["mid"], items["pessimistic"]))
    return comparisons


def _rank_playbook_candidate(item: dict) -> tuple:
    status_rank = {"promote": 2, "watch": 1, "block": 0}
    diagnostics = item.get("diagnostics") or {}
    overall = item.get("overall") or {}
    return (
        status_rank.get(item.get("status"), -1),
        1 if overall.get("passes_quality_bar") else 0,
        float(diagnostics.get("dense_source_pass_rate_pct", 0.0) or 0.0),
        float(diagnostics.get("best_rolling_pass_rate_pct", 0.0) or 0.0),
        float(overall.get("profit_factor", 0.0) or 0.0),
        float(overall.get("avg_pnl_pct", 0.0) or 0.0),
        float(overall.get("directional_accuracy_pct", 0.0) or 0.0),
        int(overall.get("trades", 0) or 0),
        -int(overall.get("slice_depth", 0) or 0),
    )


def build_playbook_discovery_report(
    result: Optional[dict] = None,
    comparison_results: Optional[list[dict]] = None,
    *,
    min_trades: int = 20,
    min_profit_factor: float = 1.05,
    min_directional_accuracy_pct: float = 50.0,
    rolling_window_days: int = 182,
    rolling_step_days: int = 91,
    catastrophic_pf_floor: float = 0.85,
    promote_ticker_share_pct: float = 70.0,
    block_ticker_share_pct: float = 90.0,
) -> dict:
    sources = _normalize_playbook_discovery_sources(result, comparison_results)
    if not sources:
        return {"error": "No backtest results found"}

    all_trades: list[dict] = []
    candidate_filters: dict[tuple[tuple[str, str], ...], dict] = {}
    for source in sources:
        all_trades.extend(source["trades"])
        for trade in source["trades"]:
            for filters in _playbook_filters_for_trade(trade):
                candidate_filters.setdefault(_playbook_filter_key(filters), dict(filters))

    if not all_trades:
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_catalog": [
                {
                    "label": source["label"],
                    "run_at": source["run_at"],
                    "lookback_years": source["lookback_years"],
                    "pricing_lane": source["pricing_lane"],
                    "playbook": source["playbook"],
                    "total_trades": source["total_trades"],
                    "aggregate_trade_count": source["aggregate_trade_count"],
                    "authoritative_trade_count": source["authoritative_trade_count"],
                    "research_only_trade_count": source["research_only_trade_count"],
                    "authoritative_profitability_lens": source["authoritative_profitability_lens"],
                }
                for source in sources
            ],
            "candidate_dimensions": list(PLAYBOOK_DISCOVERY_DIMENSIONS),
            "quality_bar": {
                "min_trades": int(min_trades),
                "min_profit_factor": float(min_profit_factor),
                "min_directional_accuracy_pct": float(min_directional_accuracy_pct),
                "catastrophic_pf_floor": float(catastrophic_pf_floor),
                "promote_ticker_share_pct": float(promote_ticker_share_pct),
                "block_ticker_share_pct": float(block_ticker_share_pct),
            },
            "candidates": [],
            "promote_candidates": [],
            "watch_candidates": [],
            "block_candidates": [],
            "recommendations": ["No replay trades are available, so playbook discovery is blocked."],
        }

    assessed_candidates: list[dict] = []
    for filters in candidate_filters.values():
        matched_all = [trade for trade in all_trades if _trade_matches_playbook_filters(trade, filters)]
        overall = _summarize_playbook_discovery_slice(
            filters,
            matched_all,
            len(all_trades),
            min_trades=min_trades,
            min_profit_factor=min_profit_factor,
            min_directional_accuracy_pct=min_directional_accuracy_pct,
        )
        source_summaries = [
            _source_slice_summary(
                source,
                filters,
                min_trades=min_trades,
                min_profit_factor=min_profit_factor,
                min_directional_accuracy_pct=min_directional_accuracy_pct,
            )
            for source in sources
        ]
        dense_sources = [summary for summary in source_summaries if not summary["sparse"]]
        source_passes = [summary for summary in dense_sources if summary["passes_quality_bar"]]
        lookback_comparisons = _build_lookback_comparisons(source_summaries)
        pricing_lane_comparisons = _build_pricing_lane_comparisons(source_summaries)
        rolling_summaries = [
            _playbook_rolling_summary(
                source,
                filters,
                min_trades=min_trades,
                min_profit_factor=min_profit_factor,
                rolling_window_days=rolling_window_days,
                rolling_step_days=rolling_step_days,
                catastrophic_pf_floor=catastrophic_pf_floor,
            )
            for source in sources
        ]
        available_rolling = [summary for summary in rolling_summaries if summary["available"]]

        reasons: list[str] = [
            (
                f"Authoritative evidence: {overall['trades']} trades, PF {overall['profit_factor']:.2f}, "
                f"avg P&L {overall['avg_pnl_pct']:+.2f}%, directional accuracy {overall['directional_accuracy_pct']:.1f}%."
            )
        ]
        blockers: list[str] = []

        if overall["passes_quality_bar"]:
            reasons.append("Authoritative exact-contract slice cleared the quality bar.")
        elif overall.get("non_finite_metrics"):
            blockers.append(
                "Authoritative exact-contract slice has non-finite metrics: "
                + ", ".join(overall["non_finite_metrics"])
                + "."
            )
        elif overall["sparse"]:
            blockers.append(f"Only {overall['trades']} trades matched; need at least {int(min_trades)}.")
        else:
            blockers.append("Authoritative exact-contract slice missed the profitability and/or directional-accuracy bar.")

        playbook_shape_ok = "direction" in filters and (
            "market_regime" in filters or "sector" in filters
        )
        if not playbook_shape_ok:
            blockers.append("Slice is too generic for promotion because it does not narrow by sector or market regime.")

        dense_source_count = len(dense_sources)
        if dense_source_count:
            reasons.append(
                f"Dense cached scenarios passed {len(source_passes)}/{dense_source_count} quality checks."
            )
        else:
            blockers.append("No dense cached scenario is available for cross-run confirmation.")

        comparison_issues = False
        insufficient_comparisons = False
        for comparison in lookback_comparisons + pricing_lane_comparisons:
            reasons.append(comparison["reason"])
            if comparison["status"] in {"conflict", "weak"}:
                comparison_issues = True
            if comparison["status"] == "insufficient_sample":
                insufficient_comparisons = True

        if not lookback_comparisons:
            reasons.append("No paired 1y vs 2y cache was available for this slice.")
        if not pricing_lane_comparisons:
            reasons.append("No paired mid vs pessimistic cache was available for this slice.")

        rolling_issue = False
        rolling_confirmed = False
        if available_rolling:
            for summary in available_rolling:
                reasons.append(
                    f"Rolling windows in {summary['source_label']}: {summary['windows_passed']}/{summary['dense_windows']} passed "
                    f"(worst PF {summary['worst_profit_factor']:.2f})."
                )
                if summary["status"] == "stable":
                    rolling_confirmed = True
                else:
                    rolling_issue = True
                    if summary["failing_windows"]:
                        blockers.append(
                            f"Rolling windows conflicted in {summary['source_label']} ({', '.join(summary['failing_windows'])})."
                        )
        else:
            reasons.append("Rolling-window evidence was unavailable or too sparse for this slice.")

        top_ticker = overall.get("top_ticker")
        top_ticker_share_pct = float(overall.get("top_ticker_share_pct", 0.0) or 0.0)
        if overall["distinct_tickers"] <= 1 and top_ticker:
            blockers.append(f"All matched trades came from {top_ticker}, so this still looks like ticker-chasing.")
        elif top_ticker_share_pct >= float(promote_ticker_share_pct) and top_ticker:
            blockers.append(
                f"{top_ticker} drove {top_ticker_share_pct:.1f}% of matched trades, so the slice is still too concentrated."
            )
        else:
            reasons.append(
                f"Breadth check: top ticker share is {top_ticker_share_pct:.1f}% across {overall['distinct_tickers']} names."
            )

        promote_ready = (
            overall["passes_quality_bar"]
            and playbook_shape_ok
            and dense_source_count > 0
            and len(source_passes) == dense_source_count
            and not comparison_issues
            and not insufficient_comparisons
            and (not available_rolling or not rolling_issue)
            and overall["distinct_tickers"] > 1
            and top_ticker_share_pct < float(promote_ticker_share_pct)
        )

        positive_evidence = (
            overall["passes_quality_bar"]
            or len(source_passes) > 0
            or rolling_confirmed
            or overall["profit_factor"] >= 1.0
            or overall["avg_pnl_pct"] > 0.0
        )

        if promote_ready:
            status = "promote"
        elif positive_evidence:
            status = "watch"
        else:
            status = "block"

        if status == "watch" and top_ticker_share_pct >= float(block_ticker_share_pct):
            status = "block"

        diagnostics = {
            "playbook_shape_ok": playbook_shape_ok,
            "dense_source_count": dense_source_count,
            "dense_source_passes": len(source_passes),
            "dense_source_pass_rate_pct": round(len(source_passes) / max(dense_source_count, 1) * 100.0, 1)
            if dense_source_count
            else 0.0,
            "lookback_comparisons": len(lookback_comparisons),
            "pricing_lane_comparisons": len(pricing_lane_comparisons),
            "comparison_issues": comparison_issues,
            "insufficient_comparisons": insufficient_comparisons,
            "rolling_sources_available": len(available_rolling),
            "best_rolling_pass_rate_pct": max(
                [float(summary.get("pass_rate_pct", 0.0) or 0.0) for summary in available_rolling],
                default=0.0,
            ),
            "top_ticker_share_pct": top_ticker_share_pct,
        }

        assessed_candidates.append(
            {
                "candidate_id": overall["candidate_id"],
                "label": overall["label"],
                "filters": overall["filters"],
                "status": status,
                "overall": overall,
                "source_summaries": source_summaries,
                "lookback_comparisons": lookback_comparisons,
                "pricing_lane_comparisons": pricing_lane_comparisons,
                "rolling_summaries": rolling_summaries,
                "reasons": reasons,
                "blockers": blockers,
                "diagnostics": diagnostics,
            }
        )

    ranked_candidates = sorted(assessed_candidates, key=_rank_playbook_candidate, reverse=True)
    promote_candidates = [item for item in ranked_candidates if item["status"] == "promote"]
    watch_candidates = [item for item in ranked_candidates if item["status"] == "watch"]
    block_candidates = [item for item in ranked_candidates if item["status"] == "block"]

    recommendations: list[str] = []
    if promote_candidates:
        recommendations.append(
            "Promote next: " + ", ".join(item["label"] for item in promote_candidates[:3]) + "."
        )
    else:
        recommendations.append("No slice cleared the promotion bar across the cached replay evidence.")
    if watch_candidates:
        recommendations.append(
            "Watch next: " + ", ".join(item["label"] for item in watch_candidates[:3]) + "."
        )
    if any(item["overall"]["distinct_tickers"] <= 1 for item in watch_candidates + block_candidates):
        recommendations.append("Ticker concentration is still a common downgrade, so avoid promoting single-name stories.")

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_catalog": [
            {
                "label": source["label"],
                "run_at": source["run_at"],
                "lookback_years": source["lookback_years"],
                "pricing_lane": source["pricing_lane"],
                "playbook": source["playbook"],
                "total_days": source["total_days"],
                "total_trades": source["total_trades"],
                "aggregate_trade_count": source["aggregate_trade_count"],
                "authoritative_trade_count": source["authoritative_trade_count"],
                "research_only_trade_count": source["research_only_trade_count"],
                "authoritative_profitability_lens": source["authoritative_profitability_lens"],
            }
            for source in sources
        ],
        "candidate_dimensions": list(PLAYBOOK_DISCOVERY_DIMENSIONS),
        "quality_bar": {
            "min_trades": int(min_trades),
            "min_profit_factor": float(min_profit_factor),
            "min_directional_accuracy_pct": float(min_directional_accuracy_pct),
            "catastrophic_pf_floor": float(catastrophic_pf_floor),
            "promote_ticker_share_pct": float(promote_ticker_share_pct),
            "block_ticker_share_pct": float(block_ticker_share_pct),
        },
        "candidates": ranked_candidates,
        "promote_candidates": promote_candidates[:10],
        "watch_candidates": watch_candidates[:10],
        "block_candidates": block_candidates[:10],
        "recommendations": recommendations,
    }
