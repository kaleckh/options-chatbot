from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_env import load_local_env

load_local_env(ROOT)

os.environ["OPTIONS_MARKET_DATA_PROVIDER"] = "alpaca"
os.environ["HISTORICAL_OPTIONS_DB_PATH"] = str(ROOT / "data" / "options-validation" / "options_history.db")

import wfo_optimizer as wfo


OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "bullish-pullback-observation" / "sleeves"
UNIVERSE_PATH = ROOT / "data" / "options-lanes" / "universes" / "bullish_pullback_observation.json"


def _active_universe_symbols() -> list[str]:
    manifest = json.loads(UNIVERSE_PATH.read_text(encoding="utf8"))
    symbols: list[str] = []
    seen: set[str] = set()
    for tier in manifest.get("tiers") or []:
        if not bool(tier.get("scan_eligible", False)):
            continue
        for raw_symbol in tier.get("symbols") or []:
            symbol = str(raw_symbol or "").strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            symbols.append(symbol)
    return symbols


SLEEVE_GROUPS: dict[str, list[str]] = {
    "index_core": ["SPY", "QQQ", "IWM", "DIA", "XLK"],
    "liquid_core": ["SPY", "QQQ", "XLK", "DIA", "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "JPM", "XOM", "WMT"],
    "mega_cap_growth": ["AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "AMD", "NFLX", "TSLA"],
    "high_beta_growth": ["COIN", "MSTR", "PLTR", "ARM", "SMCI"],
    "financials_payments": ["JPM", "GS", "BAC", "V", "C"],
    "healthcare": ["UNH", "LLY", "JNJ", "ABBV", "PFE"],
    "energy": ["XOM", "CVX", "OXY", "COP", "SLB"],
    "consumer_retail": ["DIS", "MCD", "NKE", "SBUX", "WMT", "COST"],
    "defensive_bullish": ["WMT", "COST", "KO", "PG", "PM", "MCD", "UNH", "LLY", "JNJ", "ABBV"],
    "industrials_defense": ["CAT", "BA", "DE", "LMT", "RTX"],
    "materials_metals": ["FCX", "NEM", "CLF", "AA", "LIN"],
    "reits_rate_sensitive": ["AMT", "PLD", "SPG", "WELL", "EQR"],
    "telecom": ["T"],
    "winner_ticker_stack": ["CVX", "AAPL", "XOM", "COP", "NEM", "GOOGL", "IWM", "JNJ", "UNH", "WMT", "PM", "CAT", "XLK", "DIA"],
    "winner_clean_coverage": ["CVX", "AAPL", "XOM", "COP", "NEM", "PLD", "GOOGL", "IWM", "JNJ", "UNH", "LLY", "OXY"],
    "winner_high_confidence": ["CVX", "AAPL", "XOM", "COP", "NEM", "PLD", "GOOGL", "UNH", "OXY"],
    "winner_clean_plus_liquid": [
        "CVX",
        "AAPL",
        "XOM",
        "COP",
        "NEM",
        "PLD",
        "GOOGL",
        "IWM",
        "JNJ",
        "UNH",
        "LLY",
        "PM",
        "CAT",
        "XLK",
        "DIA",
    ],
    "winner_clean_plus_profitable": [
        "CVX",
        "AAPL",
        "XOM",
        "COP",
        "NEM",
        "PLD",
        "GOOGL",
        "IWM",
        "JNJ",
        "UNH",
        "LLY",
        "PM",
        "CAT",
        "XLK",
        "DIA",
        "WELL",
        "KO",
        "T",
    ],
    "winner_positive_expanded": [
        "CVX",
        "AAPL",
        "XOM",
        "PM",
        "QQQ",
        "CAT",
        "COP",
        "XLK",
        "WELL",
        "DIA",
        "KO",
        "NEM",
        "ARM",
        "PLD",
        "T",
        "GOOGL",
        "IWM",
        "JNJ",
        "UNH",
        "LLY",
        "WMT",
        "OXY",
    ],
}


BASE_OVERRIDES: dict[str, Any] = {
    "chain_native_spread_selection": True,
    "chain_native_min_dte": 28,
    "chain_native_max_dte": 45,
    "spread_stop_loss_pct": 120.0,
    "spread_time_exit_pct": 60.0,
    "max_debit_pct_of_width": 50.0,
    "pullback_ret20_min": 2.5,
    "pullback_ret5_min": -2.0,
    "pullback_ret5_max": 0.25,
    "scan_min_confidence": 65.0,
    "min_spy_ret5": -0.5,
    "chain_native_min_entry_short_bid": 0.05,
    "execution_backfill_enabled": True,
    "scan_until_capacity": True,
    "unknown_sector_policy": "ticker_bucket",
    "max_per_allocation_group": 2,
    "max_per_ticker": 1,
}


def _active_symbols(symbols: list[str]) -> list[str]:
    active = set(_active_universe_symbols())
    return [symbol for symbol in symbols if symbol in active]


def _tier(
    tier_id: str,
    *,
    rank: int,
    sleeve_id: str,
    symbols: list[str] | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = dict(overrides or {})
    if symbols is not None:
        resolved["allowed_tickers"] = _active_symbols(symbols)
    return {
        "tier_id": tier_id,
        "tier_rank": rank,
        "sleeve_id": sleeve_id,
        "sleeve_group": sleeve_id,
        "overrides": resolved,
    }


VARIANTS: list[dict[str, Any]] = [
    {
        "id": "sleeve_alpha_sectorfix",
        "description": "Current profitable alpha rules with the Unknown-sector capacity fix and no post-hoc exclusions.",
        "n_picks": 3,
        "overrides": {},
    },
    {
        "id": "sleeve_alpha_tiered_v1",
        "description": "Alpha sleeve with ordered relaxed capacity tiers.",
        "n_picks": 3,
        "overrides": {
            "capacity_tiers": [
                _tier("alpha_strict", rank=1, sleeve_id="alpha_pullback"),
                _tier(
                    "alpha_ret20_relaxed",
                    rank=2,
                    sleeve_id="alpha_pullback",
                    overrides={"pullback_ret20_min": 2.0},
                ),
                _tier(
                    "alpha_ret5_relaxed",
                    rank=3,
                    sleeve_id="alpha_pullback",
                    overrides={"pullback_ret20_min": 2.0, "pullback_ret5_min": -3.0, "pullback_ret5_max": 0.75},
                ),
                _tier(
                    "alpha_confidence_relaxed",
                    rank=4,
                    sleeve_id="alpha_pullback",
                    overrides={
                        "pullback_ret20_min": 2.0,
                        "pullback_ret5_min": -3.0,
                        "pullback_ret5_max": 0.75,
                        "scan_min_confidence": 60.0,
                    },
                ),
            ]
        },
    },
    {
        "id": "sleeve_liquid_core_refill",
        "description": "High-coverage liquid core bullish refill sleeve.",
        "n_picks": 3,
        "allowed": SLEEVE_GROUPS["liquid_core"],
        "overrides": {
            "sleeve_id": "liquid_core",
            "sleeve_group": "liquid_core",
            "pullback_ret20_min": 1.5,
            "pullback_ret5_min": -3.0,
            "pullback_ret5_max": 1.0,
            "scan_min_confidence": 60.0,
            "min_tradability_score": 60.0,
            "execution_survivability_enabled": True,
            "min_short_leg_prior_quote_days": 1,
        },
    },
    {
        "id": "sleeve_defensive_bullish",
        "description": "Defensive bullish refill sleeve.",
        "n_picks": 2,
        "allowed": SLEEVE_GROUPS["defensive_bullish"],
        "overrides": {
            "sleeve_id": "defensive_bullish",
            "sleeve_group": "defensive_bullish",
            "pullback_ret20_min": 1.5,
            "pullback_ret5_min": -3.0,
            "pullback_ret5_max": 0.75,
            "scan_min_confidence": 60.0,
            "min_spy_ret5": -1.0,
            "execution_survivability_enabled": True,
            "min_tradability_score": 65.0,
            "min_short_leg_prior_quote_days": 1,
        },
    },
    {
        "id": "sleeve_bearish_index_riskoff",
        "description": "Index-only bearish risk-off put-spread sleeve.",
        "n_picks": 2,
        "allowed": ["SPY", "QQQ", "IWM", "DIA"],
        "overrides": {
            "sleeve_id": "bearish_index",
            "sleeve_group": "bearish_index",
            "entry_signal_id": "momentum",
            "allowed_directions": ["put"],
            "allowed_signal_families": ["momentum"],
            "allowed_market_regimes": ["bearish"],
            "scan_min_confidence": 60.0,
            "max_debit_pct_of_width": 55.0,
            "execution_survivability_enabled": True,
            "min_tradability_score": 60.0,
        },
    },
    {
        "id": "sleeve_portfolio_v1_target3",
        "description": "Combined alpha, liquid core, defensive, and bearish-index sleeve portfolio with a 3-slot daily target.",
        "n_picks": 3,
        "overrides": {
            "capacity_tiers": [
                _tier("alpha_strict", rank=1, sleeve_id="alpha_pullback"),
                _tier(
                    "alpha_relaxed",
                    rank=2,
                    sleeve_id="alpha_pullback",
                    overrides={
                        "pullback_ret20_min": 2.0,
                        "pullback_ret5_min": -3.0,
                        "pullback_ret5_max": 0.75,
                        "scan_min_confidence": 60.0,
                    },
                ),
                _tier(
                    "liquid_core_refill",
                    rank=3,
                    sleeve_id="liquid_core",
                    symbols=SLEEVE_GROUPS["liquid_core"],
                    overrides={
                        "pullback_ret20_min": 1.5,
                        "pullback_ret5_min": -3.0,
                        "pullback_ret5_max": 1.0,
                        "scan_min_confidence": 60.0,
                        "min_tradability_score": 60.0,
                    },
                ),
                _tier(
                    "defensive_refill",
                    rank=4,
                    sleeve_id="defensive_bullish",
                    symbols=SLEEVE_GROUPS["defensive_bullish"],
                    overrides={
                        "pullback_ret20_min": 1.5,
                        "pullback_ret5_min": -3.0,
                        "pullback_ret5_max": 0.75,
                        "scan_min_confidence": 60.0,
                        "min_spy_ret5": -1.0,
                    },
                ),
                _tier(
                    "bearish_index_riskoff",
                    rank=5,
                    sleeve_id="bearish_index",
                    symbols=["SPY", "QQQ", "IWM", "DIA"],
                    overrides={
                        "entry_signal_id": "momentum",
                        "allowed_directions": ["put"],
                        "allowed_signal_families": ["momentum"],
                        "allowed_market_regimes": ["bearish"],
                        "scan_min_confidence": 60.0,
                        "max_debit_pct_of_width": 55.0,
                    },
                ),
            ],
            "execution_survivability_enabled": True,
            "min_tradability_score": 60.0,
            "min_short_leg_prior_quote_days": 1,
        },
    },
    {
        "id": "sleeve_profit_theme_stack_v1",
        "description": "Portfolio of the profitable theme sleeves from the broad sweep: energy, defensive, healthcare, liquid core, materials, and index core.",
        "n_picks": 4,
        "overrides": {
            "capacity_tiers": [
                _tier(
                    "energy_quality",
                    rank=1,
                    sleeve_id="energy",
                    symbols=SLEEVE_GROUPS["energy"],
                    overrides={
                        "pullback_ret20_min": 2.0,
                        "pullback_ret5_min": -3.0,
                        "pullback_ret5_max": 0.75,
                        "scan_min_confidence": 60.0,
                    },
                ),
                _tier(
                    "defensive_quality",
                    rank=2,
                    sleeve_id="defensive_bullish",
                    symbols=SLEEVE_GROUPS["defensive_bullish"],
                    overrides={
                        "pullback_ret20_min": 2.0,
                        "pullback_ret5_min": -3.0,
                        "pullback_ret5_max": 0.75,
                        "scan_min_confidence": 60.0,
                        "min_spy_ret5": -1.0,
                    },
                ),
                _tier(
                    "healthcare_quality",
                    rank=3,
                    sleeve_id="healthcare",
                    symbols=SLEEVE_GROUPS["healthcare"],
                    overrides={
                        "pullback_ret20_min": 2.0,
                        "pullback_ret5_min": -3.0,
                        "pullback_ret5_max": 0.75,
                        "scan_min_confidence": 60.0,
                        "min_spy_ret5": -1.0,
                    },
                ),
                _tier(
                    "liquid_core_quality",
                    rank=4,
                    sleeve_id="liquid_core",
                    symbols=SLEEVE_GROUPS["liquid_core"],
                    overrides={
                        "pullback_ret20_min": 2.0,
                        "pullback_ret5_min": -3.0,
                        "pullback_ret5_max": 0.75,
                        "scan_min_confidence": 60.0,
                    },
                ),
                _tier(
                    "materials_metals_quality",
                    rank=5,
                    sleeve_id="materials_metals",
                    symbols=SLEEVE_GROUPS["materials_metals"],
                    overrides={
                        "pullback_ret20_min": 2.0,
                        "pullback_ret5_min": -3.0,
                        "pullback_ret5_max": 0.75,
                        "scan_min_confidence": 60.0,
                    },
                ),
                _tier(
                    "index_core_quality",
                    rank=6,
                    sleeve_id="index_core",
                    symbols=SLEEVE_GROUPS["index_core"],
                    overrides={
                        "pullback_ret20_min": 2.0,
                        "pullback_ret5_min": -3.0,
                        "pullback_ret5_max": 0.75,
                        "scan_min_confidence": 60.0,
                    },
                ),
            ],
            "execution_survivability_enabled": True,
            "min_tradability_score": 60.0,
            "min_short_leg_prior_quote_days": 1,
            "max_per_allocation_group": 1,
            "max_per_ticker": 1,
            "max_total_index": 1,
        },
    },
]

_profit_theme_stack_survival_overrides = copy.deepcopy(VARIANTS[-1]["overrides"])
_profit_theme_stack_survival_overrides.update(
    {
        "chain_native_min_prior_quote_days": 5,
        "chain_native_prior_quote_lookback_days": 30,
        "min_tradability_score": 75.0,
        "min_short_leg_prior_quote_days": 5,
        "min_long_leg_prior_quote_days": 3,
    }
)
VARIANTS.append(
    {
        "id": "sleeve_profit_theme_stack_survival_v1",
        "description": "Profit theme stack with stricter prior exact-chain continuity to reduce short-leg exit quote misses.",
        "n_picks": 4,
        "overrides": _profit_theme_stack_survival_overrides,
    }
)

_profit_theme_stack_time40_overrides = copy.deepcopy(VARIANTS[-2]["overrides"])
_profit_theme_stack_time40_overrides.update({"spread_time_exit_pct": 40.0})
VARIANTS.append(
    {
        "id": "sleeve_profit_theme_stack_time40_v1",
        "description": "Profit theme stack with an earlier 40% DTE time exit.",
        "n_picks": 4,
        "overrides": _profit_theme_stack_time40_overrides,
    }
)

_profit_theme_stack_target120_overrides = copy.deepcopy(VARIANTS[-3]["overrides"])
_profit_theme_stack_target120_overrides.update({"spread_profit_target_pct": 120.0})
VARIANTS.append(
    {
        "id": "sleeve_profit_theme_stack_target120_v1",
        "description": "Profit theme stack with a lower 120% spread profit target.",
        "n_picks": 4,
        "overrides": _profit_theme_stack_target120_overrides,
    }
)

_profit_theme_stack_failure_memory_overrides = copy.deepcopy(
    next(row for row in VARIANTS if row["id"] == "sleeve_profit_theme_stack_v1")["overrides"]
)
_profit_theme_stack_failure_memory_overrides.update(
    {
        "exit_quote_failure_memory_enabled": True,
        "exit_quote_failure_cooldown_days": 45,
        "exit_quote_failure_max_prior": 1,
        "exit_quote_failure_scope": "ticker",
    }
)
VARIANTS.append(
    {
        "id": "sleeve_profit_theme_stack_failure_memory_v1",
        "description": "Profit theme stack with causal ticker-level cooldown after observed short-leg exit quote misses.",
        "n_picks": 4,
        "overrides": _profit_theme_stack_failure_memory_overrides,
    }
)

for _variant_id, _description, _extra_overrides in [
    (
        "sleeve_profit_theme_stack_short25_v1",
        "Profit theme stack with a closer 0.25-delta short leg target.",
        {"spread_short_delta": 0.25},
    ),
    (
        "sleeve_profit_theme_stack_short30_v1",
        "Profit theme stack with a closer 0.30-delta short leg target.",
        {"spread_short_delta": 0.30},
    ),
    (
        "sleeve_profit_theme_stack_shortbid10_v1",
        "Profit theme stack requiring at least a 0.10 entry bid on the short leg.",
        {"chain_native_min_entry_short_bid": 0.10},
    ),
    (
        "sleeve_profit_theme_stack_shortbid15_v1",
        "Profit theme stack requiring at least a 0.15 entry bid on the short leg.",
        {"chain_native_min_entry_short_bid": 0.15},
    ),
]:
    _overrides = copy.deepcopy(next(row for row in VARIANTS if row["id"] == "sleeve_profit_theme_stack_v1")["overrides"])
    _overrides.update(_extra_overrides)
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": 4,
            "overrides": _overrides,
        }
    )

for _variant_id, _description, _excluded in [
    (
        "sleeve_profit_theme_stack_excl_poor_exact_v1",
        "Profit theme stack excluding high-miss tickers with poor exact priced support.",
        ["SLB", "AMZN", "FCX", "ABBV", "AA"],
    ),
    (
        "sleeve_profit_theme_stack_excl_poor_plus_zero_v1",
        "Profit theme stack excluding poor-exact names plus zero-proof selected miss buckets.",
        ["SLB", "AMZN", "FCX", "ABBV", "AA", "PFE", "KO", "MCD", "PG", "CLF", "QQQ"],
    ),
    (
        "sleeve_profit_theme_stack_excl_poor_wide_v1",
        "Profit theme stack excluding poor-exact names plus META/NVDA one-off weak exact names.",
        ["SLB", "AMZN", "FCX", "ABBV", "AA", "META", "NVDA"],
    ),
]:
    _overrides = copy.deepcopy(next(row for row in VARIANTS if row["id"] == "sleeve_profit_theme_stack_v1")["overrides"])
    _overrides["excluded_tickers"] = _excluded
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": 4,
            "overrides": _overrides,
        }
    )

for _variant_id, _description, _extra_overrides in [
    (
        "sleeve_profit_theme_stack_narrow_filter_v1",
        "Profit theme stack backfilling narrow spreads with far short legs.",
        {
            "chain_native_narrow_spread_width_max": 5.0,
            "chain_native_narrow_spread_short_moneyness_min_pct": 7.0,
        },
    ),
    (
        "sleeve_profit_theme_stack_maxdte41_v1",
        "Profit theme stack with max chain-native DTE capped at 41.",
        {"chain_native_max_dte": 41},
    ),
    (
        "sleeve_profit_theme_stack_shortbid10_narrow_v1",
        "Profit theme stack with 0.10 short bid minimum plus narrow far-short spread backfill.",
        {
            "chain_native_min_entry_short_bid": 0.10,
            "chain_native_narrow_spread_width_max": 5.0,
            "chain_native_narrow_spread_short_moneyness_min_pct": 7.0,
        },
    ),
]:
    _overrides = copy.deepcopy(next(row for row in VARIANTS if row["id"] == "sleeve_profit_theme_stack_v1")["overrides"])
    _overrides.update(_extra_overrides)
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": 4,
            "overrides": _overrides,
        }
    )

for _variant_id, _description, _extra_overrides in [
    (
        "sleeve_profit_theme_stack_pluszero_shortbid10_v1",
        "Poor-plus-zero quarantine with at least a 0.10 entry bid on the short leg.",
        {"chain_native_min_entry_short_bid": 0.10},
    ),
    (
        "sleeve_profit_theme_stack_pluszero_shortbid15_v1",
        "Poor-plus-zero quarantine with at least a 0.15 entry bid on the short leg.",
        {"chain_native_min_entry_short_bid": 0.15},
    ),
    (
        "sleeve_profit_theme_stack_pluszero_maxdte41_v1",
        "Poor-plus-zero quarantine with max chain-native DTE capped at 41.",
        {"chain_native_max_dte": 41},
    ),
    (
        "sleeve_profit_theme_stack_pluszero_failure_memory_v1",
        "Poor-plus-zero quarantine with causal ticker-level cooldown after observed exit quote misses.",
        {
            "exit_quote_failure_memory_enabled": True,
            "exit_quote_failure_cooldown_days": 45,
            "exit_quote_failure_max_prior": 1,
            "exit_quote_failure_scope": "ticker",
        },
    ),
    (
        "sleeve_profit_theme_stack_pluszero_shortbid10_memory_v1",
        "Poor-plus-zero quarantine with 0.10 short bid minimum and causal exit quote failure memory.",
        {
            "chain_native_min_entry_short_bid": 0.10,
            "exit_quote_failure_memory_enabled": True,
            "exit_quote_failure_cooldown_days": 45,
            "exit_quote_failure_max_prior": 1,
            "exit_quote_failure_scope": "ticker",
        },
    ),
]:
    _base_plus_zero = next(row for row in VARIANTS if row["id"] == "sleeve_profit_theme_stack_excl_poor_plus_zero_v1")
    _overrides = copy.deepcopy(_base_plus_zero["overrides"])
    _overrides.update(_extra_overrides)
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": 4,
            "overrides": _overrides,
        }
    )

for _variant_id, _description, _base_id, _extra_overrides in [
    (
        "sleeve_profit_theme_stack_dynamic_health_v1",
        "Profit theme stack with causal symbol-health memory using observed exits and missing-exit failures.",
        "sleeve_profit_theme_stack_v1",
        {
            "symbol_health_memory_enabled": True,
            "symbol_health_min_observations": 3,
            "symbol_health_min_profit_factor": 1.0,
            "symbol_health_min_avg_pnl_pct": 0.0,
            "symbol_health_include_unpriced_failures": True,
            "symbol_health_unpriced_penalty_pct": -100.0,
        },
    ),
    (
        "sleeve_profit_theme_stack_pluszero_dynamic_health_v1",
        "Poor-plus-zero quarantine with causal symbol-health memory.",
        "sleeve_profit_theme_stack_excl_poor_plus_zero_v1",
        {
            "symbol_health_memory_enabled": True,
            "symbol_health_min_observations": 3,
            "symbol_health_min_profit_factor": 1.0,
            "symbol_health_min_avg_pnl_pct": 0.0,
            "symbol_health_include_unpriced_failures": True,
            "symbol_health_unpriced_penalty_pct": -100.0,
        },
    ),
    (
        "sleeve_profit_theme_stack_pluszero_maxdte41_dynamic_health_v1",
        "Poor-plus-zero max-DTE-41 sleeve with causal symbol-health memory.",
        "sleeve_profit_theme_stack_pluszero_maxdte41_v1",
        {
            "symbol_health_memory_enabled": True,
            "symbol_health_min_observations": 3,
            "symbol_health_min_profit_factor": 1.0,
            "symbol_health_min_avg_pnl_pct": 0.0,
            "symbol_health_include_unpriced_failures": True,
            "symbol_health_unpriced_penalty_pct": -100.0,
        },
    ),
]:
    _base = next(row for row in VARIANTS if row["id"] == _base_id)
    _overrides = copy.deepcopy(_base["overrides"])
    _overrides.update(_extra_overrides)
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": 4,
            "overrides": _overrides,
        }
    )

for _variant_id, _description, _base_id, _n_picks in [
    (
        "sleeve_profit_theme_stack_pluszero_maxdte41_target3_v1",
        "Poor-plus-zero max-DTE-41 sleeve with a 3-slot daily target.",
        "sleeve_profit_theme_stack_pluszero_maxdte41_v1",
        3,
    ),
    (
        "sleeve_profit_theme_stack_pluszero_maxdte41_target5_v1",
        "Poor-plus-zero max-DTE-41 sleeve with a 5-slot daily target.",
        "sleeve_profit_theme_stack_pluszero_maxdte41_v1",
        5,
    ),
]:
    _base = next(row for row in VARIANTS if row["id"] == _base_id)
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": _n_picks,
            "overrides": copy.deepcopy(_base["overrides"]),
        }
    )

for _variant_id, _description, _extra_overrides in [
    (
        "sleeve_profit_theme_stack_excl_wide_plus_zero_v1",
        "Profit theme stack excluding poor-exact, META/NVDA, and zero-proof miss buckets.",
        {
            "excluded_tickers": ["SLB", "AMZN", "FCX", "ABBV", "AA", "META", "NVDA", "PFE", "KO", "MCD", "PG", "CLF", "QQQ"],
        },
    ),
    (
        "sleeve_profit_theme_stack_excl_wide_plus_zero_maxdte41_v1",
        "Wide-plus-zero exclusion sleeve with max chain-native DTE capped at 41.",
        {
            "excluded_tickers": ["SLB", "AMZN", "FCX", "ABBV", "AA", "META", "NVDA", "PFE", "KO", "MCD", "PG", "CLF", "QQQ"],
            "chain_native_max_dte": 41,
        },
    ),
]:
    _overrides = copy.deepcopy(next(row for row in VARIANTS if row["id"] == "sleeve_profit_theme_stack_v1")["overrides"])
    _overrides.update(_extra_overrides)
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": 4,
            "overrides": _overrides,
        }
    )

VARIANTS.append(
    {
        "id": "sleeve_winner_ticker_stack_v1",
        "description": "Standalone stack of tickers with positive per-symbol exact replay support from the broad sweep.",
        "n_picks": 4,
        "allowed": SLEEVE_GROUPS["winner_ticker_stack"],
        "overrides": {
            "sleeve_id": "winner_ticker_stack",
            "sleeve_group": "winner_ticker_stack",
            "pullback_ret20_min": 2.0,
            "pullback_ret5_min": -3.0,
            "pullback_ret5_max": 0.75,
            "scan_min_confidence": 60.0,
            "execution_survivability_enabled": True,
            "min_tradability_score": 60.0,
            "min_short_leg_prior_quote_days": 1,
            "max_per_allocation_group": 2,
            "max_per_ticker": 1,
            "max_total_index": 1,
        },
    }
)

_winner_base_overrides = copy.deepcopy(next(row for row in VARIANTS if row["id"] == "sleeve_winner_ticker_stack_v1")["overrides"])
for _variant_id, _description, _allowed_group, _extra_overrides, _n_picks in [
    (
        "sleeve_winner_ticker_stack_maxdte41_v1",
        "Winner ticker stack with max chain-native DTE capped at 41.",
        "winner_ticker_stack",
        {"chain_native_max_dte": 41},
        4,
    ),
    (
        "sleeve_winner_ticker_stack_shortbid10_v1",
        "Winner ticker stack requiring at least a 0.10 entry bid on the short leg.",
        "winner_ticker_stack",
        {"chain_native_min_entry_short_bid": 0.10},
        4,
    ),
    (
        "sleeve_winner_ticker_stack_excl_low_pf_v1",
        "Winner ticker stack excluding the weaker positive symbols from holdout diagnostics.",
        "winner_ticker_stack",
        {"excluded_tickers": ["WMT", "JNJ", "UNH", "IWM"]},
        4,
    ),
    (
        "sleeve_winner_clean_coverage_v1",
        "Positive per-symbol stack limited to names with better exact coverage in the broad sweep.",
        "winner_clean_coverage",
        {},
        4,
    ),
    (
        "sleeve_winner_clean_coverage_shortbid10_v1",
        "Clean-coverage winner stack with at least a 0.10 entry bid on the short leg.",
        "winner_clean_coverage",
        {"chain_native_min_entry_short_bid": 0.10},
        4,
    ),
    (
        "sleeve_winner_high_confidence_v1",
        "Higher-confidence winner stack using only stronger coverage and profitability symbols.",
        "winner_high_confidence",
        {},
        3,
    ),
    (
        "sleeve_winner_positive_expanded_v1",
        "Expanded positive per-symbol stack to increase exact executable count while keeping negative names out.",
        "winner_positive_expanded",
        {},
        5,
    ),
    (
        "sleeve_winner_positive_expanded_maxdte41_v1",
        "Expanded positive per-symbol stack with max chain-native DTE capped at 41.",
        "winner_positive_expanded",
        {"chain_native_max_dte": 41},
        5,
    ),
]:
    _overrides = copy.deepcopy(_winner_base_overrides)
    _overrides.update(_extra_overrides)
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": _n_picks,
            "allowed": SLEEVE_GROUPS[_allowed_group],
            "overrides": _overrides,
        }
    )

_clean_base_overrides = copy.deepcopy(next(row for row in VARIANTS if row["id"] == "sleeve_winner_clean_coverage_v1")["overrides"])
for _variant_id, _description, _extra_overrides in [
    (
        "sleeve_winner_clean_coverage_no_oxy_v1",
        "Clean-coverage winner stack excluding OXY after poor exact holdout contribution.",
        {"excluded_tickers": ["OXY"]},
    ),
    (
        "sleeve_winner_clean_coverage_prior5_v1",
        "Clean-coverage winner stack requiring stronger recent exact-chain quote persistence.",
        {
            "chain_native_min_prior_quote_days": 5,
            "chain_native_prior_quote_lookback_days": 30,
            "min_short_leg_prior_quote_days": 5,
            "min_long_leg_prior_quote_days": 3,
            "min_tradability_score": 75.0,
        },
    ),
    (
        "sleeve_winner_clean_coverage_no_oxy_prior5_v1",
        "No-OXY clean-coverage stack with stronger recent exact-chain quote persistence.",
        {
            "excluded_tickers": ["OXY"],
            "chain_native_min_prior_quote_days": 5,
            "chain_native_prior_quote_lookback_days": 30,
            "min_short_leg_prior_quote_days": 5,
            "min_long_leg_prior_quote_days": 3,
            "min_tradability_score": 75.0,
        },
    ),
    (
        "sleeve_winner_clean_coverage_failure_memory_v1",
        "Clean-coverage winner stack with causal ticker-level cooldown after observed exit quote misses.",
        {
            "exit_quote_failure_memory_enabled": True,
            "exit_quote_failure_cooldown_days": 45,
            "exit_quote_failure_max_prior": 1,
            "exit_quote_failure_scope": "ticker",
        },
    ),
]:
    _overrides = copy.deepcopy(_clean_base_overrides)
    _overrides.update(_extra_overrides)
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": 4,
            "allowed": SLEEVE_GROUPS["winner_clean_coverage"],
            "overrides": _overrides,
        }
    )

for _variant_id, _description, _allowed_group, _extra_overrides, _n_picks in [
    (
        "sleeve_winner_clean_plus_liquid_target4_v1",
        "No-OXY clean-plus-liquid stack with the original 4-slot daily target.",
        "winner_clean_plus_liquid",
        {},
        4,
    ),
    (
        "sleeve_winner_clean_plus_liquid_v1",
        "No-OXY clean winner stack plus liquid high-PF refill names PM, CAT, XLK, and DIA.",
        "winner_clean_plus_liquid",
        {},
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_maxdte41_v1",
        "No-OXY clean-plus-liquid stack with max chain-native DTE capped at 41.",
        "winner_clean_plus_liquid",
        {"chain_native_max_dte": 41},
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_shortbid10_v1",
        "No-OXY clean-plus-liquid stack requiring at least a 0.10 entry bid on the short leg.",
        "winner_clean_plus_liquid",
        {"chain_native_min_entry_short_bid": 0.10},
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_maxdte41_shortbid10_v1",
        "No-OXY clean-plus-liquid stack with max DTE 41 and at least a 0.10 entry short-leg bid.",
        "winner_clean_plus_liquid",
        {"chain_native_max_dte": 41, "chain_native_min_entry_short_bid": 0.10},
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_v1",
        "No-OXY clean-plus-liquid stack excluding CAT as a coverage-risk diagnostic.",
        "winner_clean_plus_liquid",
        {"excluded_tickers": ["CAT"]},
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_v1",
        "No-OXY clean-plus-liquid stack excluding CAT and PM as coverage-risk diagnostics.",
        "winner_clean_plus_liquid",
        {"excluded_tickers": ["CAT", "PM"]},
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_trad70_v1",
        "No-CAT/no-PM clean-plus-liquid stack with a stricter tradability score threshold.",
        "winner_clean_plus_liquid",
        {"excluded_tickers": ["CAT", "PM"], "min_tradability_score": 70.0},
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_v1",
        "No-CAT/no-PM clean-plus-liquid stack requiring hard prior exact quote continuity on selected legs.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_shortdelta25_v1",
        "No-CAT/no-PM hard-prior stack with a closer 0.25-delta selected short leg.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "spread_short_delta": 0.25,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_shortdelta30_v1",
        "No-CAT/no-PM hard-prior stack with a closer 0.30-delta selected short leg.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "spread_short_delta": 0.30,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_shortscore075_v1",
        "No-CAT/no-PM hard-prior stack preferring short legs with broader recent quote continuity.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "chain_native_short_prior_quote_score_weight": 0.75,
            "chain_native_prior_quote_score_cap": 10,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_shortprior5_backfill15_v1",
        "No-CAT/no-PM hard-prior stack requiring stronger short-leg quote survival with deeper same-day backfill.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_long_prior_quote_days": 1,
            "chain_native_min_short_prior_quote_days": 5,
            "chain_native_prior_quote_lookback_days": 30,
            "execution_backfill_scan_depth": 15,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_shortinside1_v1",
        "No-CAT/no-PM hard-prior stack moving the selected short leg one listed strike closer when debit cap survives.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "chain_native_short_inside_steps": 1,
            "chain_native_short_inside_require_debit_cap": True,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly60_v1",
        "No-CAT/no-PM hard-prior stack with exact fixed 60% DTE time exits only.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "spread_exit_monitoring_mode": "time_only",
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly45_v1",
        "No-CAT/no-PM hard-prior stack with exact fixed 45% DTE time exits only.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "spread_exit_monitoring_mode": "time_only",
            "spread_time_exit_pct": 45.0,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly50_v1",
        "No-CAT/no-PM hard-prior stack with exact fixed 50% DTE time exits only.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "spread_exit_monitoring_mode": "time_only",
            "spread_time_exit_pct": 50.0,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly55_v1",
        "No-CAT/no-PM hard-prior stack with exact fixed 55% DTE time exits only.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "spread_exit_monitoring_mode": "time_only",
            "spread_time_exit_pct": 55.0,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly55_calendar_v1",
        "No-CAT/no-PM hard-prior stack with fixed 55% DTE exits measured by elapsed calendar days.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "spread_exit_monitoring_mode": "time_only",
            "spread_time_exit_pct": 55.0,
            "spread_time_exit_basis": "calendar_elapsed",
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly55_shortscore075_v1",
        "Fixed 55% DTE quoted-exit stack preferring selected short legs with broader recent quote continuity.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "chain_native_short_prior_quote_score_weight": 0.75,
            "chain_native_prior_quote_score_cap": 10,
            "spread_exit_monitoring_mode": "time_only",
            "spread_time_exit_pct": 55.0,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly55_shortprior5_backfill15_v1",
        "Fixed 55% DTE quoted-exit stack requiring stronger selected short-leg quote continuity with deeper same-day backfill.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_long_prior_quote_days": 1,
            "chain_native_min_short_prior_quote_days": 5,
            "chain_native_prior_quote_lookback_days": 30,
            "execution_backfill_scan_depth": 15,
            "spread_exit_monitoring_mode": "time_only",
            "spread_time_exit_pct": 55.0,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly55_shortinside1_v1",
        "Fixed 55% DTE quoted-exit stack moving the selected short leg one listed strike closer when debit cap survives.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "chain_native_short_inside_steps": 1,
            "chain_native_short_inside_require_debit_cap": True,
            "spread_exit_monitoring_mode": "time_only",
            "spread_time_exit_pct": 55.0,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly55_trad90_v1",
        "Fixed 55% DTE quoted-exit stack with stricter entry-time tradability skip/backfill.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "execution_survivability_enabled": True,
            "min_tradability_score": 90.0,
            "spread_exit_monitoring_mode": "time_only",
            "spread_time_exit_pct": 55.0,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly75_v1",
        "No-CAT/no-PM hard-prior stack with exact fixed 75% DTE time exits only.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "spread_exit_monitoring_mode": "time_only",
            "spread_time_exit_pct": 75.0,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly65_v1",
        "No-CAT/no-PM hard-prior stack with exact fixed 65% DTE time exits only.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "spread_exit_monitoring_mode": "time_only",
            "spread_time_exit_pct": 65.0,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timeonly70_v1",
        "No-CAT/no-PM hard-prior stack with exact fixed 70% DTE time exits only.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "spread_exit_monitoring_mode": "time_only",
            "spread_time_exit_pct": 70.0,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_shortprior2_v1",
        "No-CAT/no-PM stack requiring one prior quote day on longs and two on selected shorts.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_long_prior_quote_days": 1,
            "chain_native_min_short_prior_quote_days": 2,
            "chain_native_prior_quote_lookback_days": 30,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_shortprior3_v1",
        "No-CAT/no-PM stack requiring one prior quote day on longs and three on selected shorts.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_long_prior_quote_days": 1,
            "chain_native_min_short_prior_quote_days": 3,
            "chain_native_prior_quote_lookback_days": 30,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_shortscore_v1",
        "No-CAT/no-PM stack preferring selected short legs with more recent exact quote days.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "chain_native_short_prior_quote_score_weight": 1.0,
            "chain_native_prior_quote_score_cap": 5,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_shortprior2_score_v1",
        "No-CAT/no-PM stack requiring two prior short quote days and preferring higher short continuity.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "chain_native_min_long_prior_quote_days": 1,
            "chain_native_min_short_prior_quote_days": 2,
            "chain_native_prior_quote_lookback_days": 30,
            "chain_native_short_prior_quote_score_weight": 1.0,
            "chain_native_prior_quote_score_cap": 5,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_short_memory_v1",
        "No-CAT/no-PM stack with causal cooldown by short-leg expiry/strike bucket after observed exit quote misses.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "exit_quote_failure_memory_enabled": True,
            "exit_quote_failure_cooldown_days": 45,
            "exit_quote_failure_max_prior": 1,
            "exit_quote_failure_scope": "short_expiry_strike_bucket",
            "exit_quote_failure_strike_bucket_width": 5.0,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_short_memory10_v1",
        "No-CAT/no-PM stack with causal cooldown by wider short-leg expiry/strike bucket after observed exit quote misses.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT", "PM"],
            "exit_quote_failure_memory_enabled": True,
            "exit_quote_failure_cooldown_days": 45,
            "exit_quote_failure_max_prior": 1,
            "exit_quote_failure_scope": "short_expiry_strike_bucket",
            "exit_quote_failure_strike_bucket_width": 10.0,
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_failure_memory_v1",
        "No-OXY clean-plus-liquid no-CAT stack with causal ticker-level cooldown after observed exit quote misses.",
        "winner_clean_plus_liquid",
        {
            "excluded_tickers": ["CAT"],
            "exit_quote_failure_memory_enabled": True,
            "exit_quote_failure_cooldown_days": 45,
            "exit_quote_failure_max_prior": 1,
            "exit_quote_failure_scope": "ticker",
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_liquid_failure_memory_v1",
        "No-OXY clean-plus-liquid stack with causal ticker-level cooldown after observed exit quote misses.",
        "winner_clean_plus_liquid",
        {
            "exit_quote_failure_memory_enabled": True,
            "exit_quote_failure_cooldown_days": 45,
            "exit_quote_failure_max_prior": 1,
            "exit_quote_failure_scope": "ticker",
        },
        5,
    ),
    (
        "sleeve_winner_clean_plus_profitable_v1",
        "No-OXY clean winner stack plus selected profitable refill names from the expanded stack.",
        "winner_clean_plus_profitable",
        {},
        5,
    ),
    (
        "sleeve_winner_clean_plus_profitable_maxdte41_v1",
        "No-OXY clean-plus-profitable stack with max chain-native DTE capped at 41.",
        "winner_clean_plus_profitable",
        {"chain_native_max_dte": 41},
        5,
    ),
]:
    _overrides = copy.deepcopy(_clean_base_overrides)
    _overrides.update(_extra_overrides)
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": _n_picks,
            "allowed": SLEEVE_GROUPS[_allowed_group],
            "overrides": _overrides,
        }
    )

_winner_no_cat_pm_symbols = [
    symbol
    for symbol in SLEEVE_GROUPS["winner_clean_plus_liquid"]
    if symbol not in {"CAT", "PM"}
]
_winner_timecombo_base = copy.deepcopy(_clean_base_overrides)
_winner_timecombo_base.update(
    {
        "chain_native_min_prior_quote_days": 1,
        "chain_native_prior_quote_lookback_days": 30,
        "spread_exit_monitoring_mode": "time_only",
        "spread_time_exit_pct": 55.0,
    }
)
for _variant_id, _description, _capacity_tiers in [
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_aapl_googl_v1",
        "No-CAT/no-PM hard-prior stack using 55% DTE exits generally and 50% DTE exits for AAPL/GOOGL coverage.",
        [
            _tier(
                "time55_core",
                rank=1,
                sleeve_id="winner_time55_core",
                symbols=[symbol for symbol in _winner_no_cat_pm_symbols if symbol not in {"AAPL", "GOOGL"}],
            ),
            _tier(
                "time50_aapl_googl",
                rank=2,
                sleeve_id="winner_time50_mega",
                symbols=["AAPL", "GOOGL"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
        ],
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_aapl_googl_no_unh_xlk_v1",
        "No-CAT/no-PM hard-prior stack using 55%/50% exits while excluding unresolved UNH/XLK provider-risk names.",
        [
            _tier(
                "time55_core_no_unh_xlk",
                rank=1,
                sleeve_id="winner_time55_core",
                symbols=[
                    symbol
                    for symbol in _winner_no_cat_pm_symbols
                    if symbol not in {"AAPL", "GOOGL", "UNH", "XLK"}
                ],
            ),
            _tier(
                "time50_aapl_googl",
                rank=2,
                sleeve_id="winner_time50_mega",
                symbols=["AAPL", "GOOGL"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
        ],
    ),
    (
        "sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1",
        "No-CAT/no-PM hard-prior stack using 55% exits generally, 50% for AAPL/GOOGL, and 75% for UNH/XLK.",
        [
            _tier(
                "time55_core",
                rank=1,
                sleeve_id="winner_time55_core",
                symbols=[
                    symbol
                    for symbol in _winner_no_cat_pm_symbols
                    if symbol not in {"AAPL", "GOOGL", "UNH", "XLK"}
                ],
            ),
            _tier(
                "time50_aapl_googl",
                rank=2,
                sleeve_id="winner_time50_mega",
                symbols=["AAPL", "GOOGL"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
            _tier(
                "time75_unh_xlk",
                rank=3,
                sleeve_id="winner_time75_provider_risk",
                symbols=["UNH", "XLK"],
                overrides={"spread_time_exit_pct": 75.0},
            ),
        ],
    ),
]:
    _overrides = copy.deepcopy(_winner_timecombo_base)
    _overrides["capacity_tiers"] = _capacity_tiers
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": 5,
            "allowed": _winner_no_cat_pm_symbols,
            "overrides": _overrides,
        }
    )

for _variant_id, _description, _capacity_tiers in [
    (
        "sleeve_winner_cluster_exit_50_55_60_v1",
        "No-CAT/no-PM hard-prior stack using ticker-cluster fixed exits: 50% for AAPL/UNH/XLK, 55% for NEM/IWM/PLD, 60% for energy/GOOGL/JNJ/LLY.",
        [
            _tier(
                "time60_energy_health_growth",
                rank=1,
                sleeve_id="winner_time60_energy_health_growth",
                symbols=["COP", "CVX", "XOM", "GOOGL", "JNJ", "LLY"],
                overrides={"spread_time_exit_pct": 60.0},
            ),
            _tier(
                "time55_metals_index_reit",
                rank=2,
                sleeve_id="winner_time55_metals_index_reit",
                symbols=["NEM", "IWM", "PLD"],
                overrides={"spread_time_exit_pct": 55.0},
            ),
            _tier(
                "time50_mega_health_index",
                rank=3,
                sleeve_id="winner_time50_mega_health_index",
                symbols=["AAPL", "UNH", "XLK"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
        ],
    ),
    (
        "sleeve_winner_cluster_exit_50_55_60_no_pld_xlk_v1",
        "No-CAT/no-PM hard-prior stack using ticker-cluster fixed exits while excluding PLD/XLK provider-risk fillers.",
        [
            _tier(
                "time60_energy_health_growth",
                rank=1,
                sleeve_id="winner_time60_energy_health_growth",
                symbols=["COP", "CVX", "XOM", "GOOGL", "JNJ", "LLY"],
                overrides={"spread_time_exit_pct": 60.0},
            ),
            _tier(
                "time55_metals_index",
                rank=2,
                sleeve_id="winner_time55_metals_index",
                symbols=["NEM", "IWM"],
                overrides={"spread_time_exit_pct": 55.0},
            ),
            _tier(
                "time50_mega_health",
                rank=3,
                sleeve_id="winner_time50_mega_health",
                symbols=["AAPL", "UNH"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
        ],
    ),
    (
        "sleeve_winner_energy_metals_priority_v1",
        "Concentrated high-profit energy/metals sleeve: 60% DTE exits for COP/CVX/XOM and 55% DTE exits for NEM.",
        [
            _tier(
                "time60_energy",
                rank=1,
                sleeve_id="winner_time60_energy",
                symbols=["COP", "CVX", "XOM"],
                overrides={"spread_time_exit_pct": 60.0},
            ),
            _tier(
                "time55_nem",
                rank=2,
                sleeve_id="winner_time55_nem",
                symbols=["NEM"],
                overrides={"spread_time_exit_pct": 55.0},
            ),
        ],
    ),
]:
    _overrides = copy.deepcopy(_winner_timecombo_base)
    _overrides["capacity_tiers"] = _capacity_tiers
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": 5,
            "allowed": _winner_no_cat_pm_symbols,
            "overrides": _overrides,
        }
    )

for _variant_id, _description, _capacity_tiers in [
    (
        "sleeve_winner_cluster_exit_balanced_quoted_v1",
        "No-CAT/no-PM hard-prior quoted-exit cluster: 60% for energy/LLY, 55% for NEM/IWM/PLD/JNJ, 50% for AAPL/GOOGL/UNH/XLK.",
        [
            _tier(
                "time60_energy_lly",
                rank=1,
                sleeve_id="winner_time60_energy_lly",
                symbols=["COP", "CVX", "XOM", "LLY"],
                overrides={"spread_time_exit_pct": 60.0},
            ),
            _tier(
                "time55_metals_index_reit_jnj",
                rank=2,
                sleeve_id="winner_time55_metals_index_reit_jnj",
                symbols=["NEM", "IWM", "PLD", "JNJ"],
                overrides={"spread_time_exit_pct": 55.0},
            ),
            _tier(
                "time50_mega_health_index",
                rank=3,
                sleeve_id="winner_time50_mega_health_index",
                symbols=["AAPL", "GOOGL", "UNH", "XLK"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
        ],
    ),
    (
        "sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_v1",
        "No-CAT/no-PM hard-prior quoted-exit cluster excluding unresolved UNH/XLK while using 60% for energy/LLY, 55% for NEM/IWM/PLD/JNJ, and 50% for AAPL/GOOGL.",
        [
            _tier(
                "time60_energy_lly",
                rank=1,
                sleeve_id="winner_time60_energy_lly",
                symbols=["COP", "CVX", "XOM", "LLY"],
                overrides={"spread_time_exit_pct": 60.0},
            ),
            _tier(
                "time55_metals_index_reit_jnj",
                rank=2,
                sleeve_id="winner_time55_metals_index_reit_jnj",
                symbols=["NEM", "IWM", "PLD", "JNJ"],
                overrides={"spread_time_exit_pct": 55.0},
            ),
            _tier(
                "time50_mega",
                rank=3,
                sleeve_id="winner_time50_mega",
                symbols=["AAPL", "GOOGL"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
        ],
    ),
    (
        "sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_v1",
        "No-CAT/no-PM hard-prior quoted-exit cluster excluding UNH/XLK/PLD provider-risk fillers.",
        [
            _tier(
                "time60_energy_lly",
                rank=1,
                sleeve_id="winner_time60_energy_lly",
                symbols=["COP", "CVX", "XOM", "LLY"],
                overrides={"spread_time_exit_pct": 60.0},
            ),
            _tier(
                "time55_metals_index_jnj",
                rank=2,
                sleeve_id="winner_time55_metals_index_jnj",
                symbols=["NEM", "IWM", "JNJ"],
                overrides={"spread_time_exit_pct": 55.0},
            ),
            _tier(
                "time50_mega",
                rank=3,
                sleeve_id="winner_time50_mega",
                symbols=["AAPL", "GOOGL"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
        ],
    ),
    (
        "sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_jnj_v1",
        "No-CAT/no-PM hard-prior quoted-exit cluster excluding UNH/XLK/PLD/JNJ provider-risk or negative-exact fillers.",
        [
            _tier(
                "time60_energy_lly",
                rank=1,
                sleeve_id="winner_time60_energy_lly",
                symbols=["COP", "CVX", "XOM", "LLY"],
                overrides={"spread_time_exit_pct": 60.0},
            ),
            _tier(
                "time55_metals_index",
                rank=2,
                sleeve_id="winner_time55_metals_index",
                symbols=["NEM", "IWM"],
                overrides={"spread_time_exit_pct": 55.0},
            ),
            _tier(
                "time50_mega",
                rank=3,
                sleeve_id="winner_time50_mega",
                symbols=["AAPL", "GOOGL"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
        ],
    ),
    (
        "sleeve_winner_cluster_exit_balanced_quoted_no_unh_xlk_pld_jnj50_v1",
        "No-CAT/no-PM hard-prior quoted-exit cluster excluding UNH/XLK/PLD and moving JNJ to the earlier 50% DTE exit.",
        [
            _tier(
                "time60_energy_lly",
                rank=1,
                sleeve_id="winner_time60_energy_lly",
                symbols=["COP", "CVX", "XOM", "LLY"],
                overrides={"spread_time_exit_pct": 60.0},
            ),
            _tier(
                "time55_metals_index",
                rank=2,
                sleeve_id="winner_time55_metals_index",
                symbols=["NEM", "IWM"],
                overrides={"spread_time_exit_pct": 55.0},
            ),
            _tier(
                "time50_mega_jnj",
                rank=3,
                sleeve_id="winner_time50_mega_jnj",
                symbols=["AAPL", "GOOGL", "JNJ"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
        ],
    ),
]:
    _overrides = copy.deepcopy(_winner_timecombo_base)
    _overrides["capacity_tiers"] = _capacity_tiers
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": 5,
            "allowed": _winner_no_cat_pm_symbols,
            "overrides": _overrides,
        }
    )

_pf59_refill_overrides = {
    "chain_native_min_entry_short_bid": 0.10,
    "chain_native_short_prior_quote_score_weight": 0.75,
    "execution_survivability_enabled": True,
    "min_tradability_score": 70.0,
}

for _variant_id, _description, _capacity_tiers, _n_picks in [
    (
        "sleeve_pf59_s_ab_timecluster_v1",
        "All-59 refill stack: frozen high-PF 50/55/60 S tiers first, then PF>=1 A/B refill names under stricter execution gates.",
        [
            _tier(
                "s_time60_energy_health_growth",
                rank=1,
                sleeve_id="pf59_s_time60_energy_health_growth",
                symbols=["COP", "CVX", "XOM", "GOOGL", "JNJ", "LLY"],
                overrides={"spread_time_exit_pct": 60.0},
            ),
            _tier(
                "s_time55_metals_index",
                rank=2,
                sleeve_id="pf59_s_time55_metals_index",
                symbols=["NEM", "IWM"],
                overrides={"spread_time_exit_pct": 55.0},
            ),
            _tier(
                "s_time50_mega_health",
                rank=3,
                sleeve_id="pf59_s_time50_mega_health",
                symbols=["AAPL", "UNH"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
            _tier(
                "a_theme_confirmed_refill",
                rank=4,
                sleeve_id="pf59_a_theme_confirmed_refill",
                symbols=["WMT", "QQQ", "XLK", "DIA", "OXY"],
                overrides={**_pf59_refill_overrides, "spread_time_exit_pct": 55.0},
            ),
            _tier(
                "b_pf1_refill",
                rank=5,
                sleeve_id="pf59_b_pf1_refill",
                symbols=["PM", "PLD", "KO", "T", "CAT", "WELL", "ARM"],
                overrides={**_pf59_refill_overrides, "spread_time_exit_pct": 55.0, "min_tradability_score": 80.0},
            ),
        ],
        6,
    ),
    (
        "sleeve_pf59_s_a_energy_defensive_v1",
        "Pruned all-59 refill: frozen high-PF S tiers plus only the positive energy/defensive A refill block.",
        [
            _tier(
                "s_time60_energy_health_growth",
                rank=1,
                sleeve_id="pf59_s_time60_energy_health_growth",
                symbols=["COP", "CVX", "XOM", "GOOGL", "JNJ", "LLY"],
                overrides={"spread_time_exit_pct": 60.0},
            ),
            _tier(
                "s_time55_metals_index",
                rank=2,
                sleeve_id="pf59_s_time55_metals_index",
                symbols=["NEM", "IWM"],
                overrides={"spread_time_exit_pct": 55.0},
            ),
            _tier(
                "s_time50_mega_health",
                rank=3,
                sleeve_id="pf59_s_time50_mega_health",
                symbols=["AAPL", "UNH"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
            _tier(
                "a_theme_energy_defensive",
                rank=4,
                sleeve_id="pf59_a_theme_energy_defensive",
                symbols=sorted(set(SLEEVE_GROUPS["energy"] + SLEEVE_GROUPS["defensive_bullish"])),
                overrides={**_pf59_refill_overrides, "spread_time_exit_pct": 55.0},
            ),
        ],
        6,
    ),
    (
        "sleeve_pf59_s_themeA_no_ticker_bans_v1",
        "All-59 theme refill without new ticker PnL bans: frozen S tiers first, then PF>=1 theme sleeves under stricter execution gates.",
        [
            _tier(
                "s_time60_energy_health_growth",
                rank=1,
                sleeve_id="pf59_s_time60_energy_health_growth",
                symbols=["COP", "CVX", "XOM", "GOOGL", "JNJ", "LLY"],
                overrides={"spread_time_exit_pct": 60.0},
            ),
            _tier(
                "s_time55_metals_index",
                rank=2,
                sleeve_id="pf59_s_time55_metals_index",
                symbols=["NEM", "IWM"],
                overrides={"spread_time_exit_pct": 55.0},
            ),
            _tier(
                "s_time50_mega_health",
                rank=3,
                sleeve_id="pf59_s_time50_mega_health",
                symbols=["AAPL", "UNH"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
            _tier(
                "a_theme_energy_defensive",
                rank=4,
                sleeve_id="pf59_a_theme_energy_defensive",
                symbols=sorted(set(SLEEVE_GROUPS["energy"] + SLEEVE_GROUPS["defensive_bullish"])),
                overrides={**_pf59_refill_overrides, "spread_time_exit_pct": 55.0},
            ),
            _tier(
                "a_theme_liquid_health_metals_index",
                rank=5,
                sleeve_id="pf59_a_theme_liquid_health_metals_index",
                symbols=sorted(
                    set(
                        SLEEVE_GROUPS["liquid_core"]
                        + SLEEVE_GROUPS["healthcare"]
                        + SLEEVE_GROUPS["materials_metals"]
                        + SLEEVE_GROUPS["index_core"]
                    )
                ),
                overrides={**_pf59_refill_overrides, "spread_time_exit_pct": 55.0, "min_tradability_score": 80.0},
            ),
        ],
        6,
    ),
    (
        "sleeve_pf59_coverage_clean_v1",
        "High-coverage 100+ branch first, then coverage-aware A/B refill names with stricter short-bid and tradability gates.",
        [
            _tier(
                "coverage_time60_energy_lly",
                rank=1,
                sleeve_id="pf59_coverage_time60_energy_lly",
                symbols=["COP", "CVX", "XOM", "LLY"],
                overrides={"spread_time_exit_pct": 60.0},
            ),
            _tier(
                "coverage_time55_metals_index_jnj",
                rank=2,
                sleeve_id="pf59_coverage_time55_metals_index_jnj",
                symbols=["NEM", "IWM", "JNJ"],
                overrides={"spread_time_exit_pct": 55.0},
            ),
            _tier(
                "coverage_time50_mega",
                rank=3,
                sleeve_id="pf59_coverage_time50_mega",
                symbols=["AAPL", "GOOGL"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
            _tier(
                "coverage_a_refill",
                rank=4,
                sleeve_id="pf59_coverage_a_refill",
                symbols=["WMT", "QQQ", "DIA", "OXY"],
                overrides={**_pf59_refill_overrides, "spread_time_exit_pct": 55.0},
            ),
            _tier(
                "coverage_b_refill",
                rank=5,
                sleeve_id="pf59_coverage_b_refill",
                symbols=["XLK", "PM", "PLD", "KO", "T", "CAT", "WELL", "ARM"],
                overrides={**_pf59_refill_overrides, "spread_time_exit_pct": 55.0, "min_tradability_score": 80.0},
            ),
        ],
        6,
    ),
    (
        "sleeve_pf59_coverage_a_refill_v1",
        "Pruned high-coverage refill: high-coverage cluster plus only the positive A refill block.",
        [
            _tier(
                "coverage_time60_energy_lly",
                rank=1,
                sleeve_id="pf59_coverage_time60_energy_lly",
                symbols=["COP", "CVX", "XOM", "LLY"],
                overrides={"spread_time_exit_pct": 60.0},
            ),
            _tier(
                "coverage_time55_metals_index_jnj",
                rank=2,
                sleeve_id="pf59_coverage_time55_metals_index_jnj",
                symbols=["NEM", "IWM", "JNJ"],
                overrides={"spread_time_exit_pct": 55.0},
            ),
            _tier(
                "coverage_time50_mega",
                rank=3,
                sleeve_id="pf59_coverage_time50_mega",
                symbols=["AAPL", "GOOGL"],
                overrides={"spread_time_exit_pct": 50.0},
            ),
            _tier(
                "coverage_a_refill",
                rank=4,
                sleeve_id="pf59_coverage_a_refill",
                symbols=["WMT", "QQQ", "DIA", "OXY"],
                overrides={**_pf59_refill_overrides, "spread_time_exit_pct": 55.0},
            ),
        ],
        6,
    ),
]:
    _overrides = copy.deepcopy(_winner_timecombo_base)
    _overrides.update(
        {
            "capacity_tiers": _capacity_tiers,
            "max_per_allocation_group": 1,
            "max_per_ticker": 1,
            "max_total_index": 1,
        }
    )
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": _n_picks,
            "allowed": _active_universe_symbols(),
            "overrides": _overrides,
        }
    )


_next_keep_cluster_tiers = [
    _tier(
        "next_keep_time60_energy_lly",
        rank=1,
        sleeve_id="next_keep_time60_energy_lly",
        symbols=["COP", "CVX", "XOM", "LLY"],
        overrides={"spread_time_exit_pct": 60.0},
    ),
    _tier(
        "next_keep_time55_metals_index_jnj",
        rank=2,
        sleeve_id="next_keep_time55_metals_index_jnj",
        symbols=["NEM", "IWM", "JNJ"],
        overrides={"spread_time_exit_pct": 55.0},
    ),
    _tier(
        "next_keep_time50_mega_health",
        rank=3,
        sleeve_id="next_keep_time50_mega_health",
        symbols=["AAPL", "GOOGL", "UNH"],
        overrides={"spread_time_exit_pct": 50.0},
    ),
]
_next_refill_overrides = {
    "chain_native_min_entry_short_bid": 0.10,
    "chain_native_short_prior_quote_score_weight": 0.75,
    "chain_native_prior_quote_score_cap": 10,
    "execution_survivability_enabled": True,
    "min_tradability_score": 80.0,
}
_next_mixedexit_overrides = {
    "chain_native_min_entry_short_bid": 0.10,
    "chain_native_min_prior_quote_days": 1,
    "chain_native_prior_quote_lookback_days": 30,
    "chain_native_short_prior_quote_score_weight": 0.75,
    "chain_native_prior_quote_score_cap": 10,
    "execution_survivability_enabled": True,
    "min_tradability_score": 70.0,
    "min_short_leg_prior_quote_days": 1,
}
_next_high_beta_survival_overrides = {
    **_next_refill_overrides,
    "chain_native_min_prior_quote_days": 1,
    "chain_native_prior_quote_lookback_days": 30,
    "min_short_leg_prior_quote_days": 3,
    "min_long_leg_prior_quote_days": 1,
    "pullback_ret20_min": 2.0,
    "pullback_ret5_min": -2.0,
    "pullback_ret5_max": 0.25,
    "spread_exit_monitoring_mode": "time_only",
    "spread_time_exit_pct": 40.0,
    "max_signal_ret20": 25.0,
}
for _variant_id, _description, _capacity_tiers, _n_picks in [
    (
        "sleeve_next_index_refill_v1",
        "Frozen next-layer keep cluster plus QQQ/DIA/XLK index refill with stronger quote-survival filters.",
        _next_keep_cluster_tiers
        + [
            _tier(
                "next_index_refill",
                rank=4,
                sleeve_id="next_index_refill",
                symbols=["QQQ", "DIA", "XLK"],
                overrides={**_next_refill_overrides, "spread_time_exit_pct": 50.0},
            ),
        ],
        6,
    ),
    (
        "sleeve_next_defensive_refill_v1",
        "Frozen next-layer keep cluster plus WMT/PM defensive refill with stronger quote-survival filters.",
        _next_keep_cluster_tiers
        + [
            _tier(
                "next_defensive_refill",
                rank=4,
                sleeve_id="next_defensive_refill",
                symbols=["WMT", "PM"],
                overrides={**_next_refill_overrides, "spread_time_exit_pct": 55.0},
            ),
        ],
        6,
    ),
    (
        "sleeve_next_reit_industrial_refill_v1",
        "Frozen next-layer keep cluster plus PLD/CAT scout refill with stronger quote-survival filters.",
        _next_keep_cluster_tiers
        + [
            _tier(
                "next_reit_industrial_refill",
                rank=4,
                sleeve_id="next_reit_industrial_refill",
                symbols=["PLD", "CAT"],
                overrides={**_next_refill_overrides, "spread_time_exit_pct": 55.0},
            ),
        ],
        6,
    ),
    (
        "sleeve_next_move_bucket_refill_v1",
        "Frozen next-layer keep cluster plus the strongest move-bucket scouts, separated by causal lanes.",
        _next_keep_cluster_tiers
        + [
            _tier(
                "next_index_refill",
                rank=4,
                sleeve_id="next_index_refill",
                symbols=["QQQ", "DIA", "XLK"],
                overrides={**_next_refill_overrides, "spread_time_exit_pct": 50.0},
            ),
            _tier(
                "next_defensive_refill",
                rank=5,
                sleeve_id="next_defensive_refill",
                symbols=["WMT", "PM"],
                overrides={**_next_refill_overrides, "spread_time_exit_pct": 55.0},
            ),
            _tier(
                "next_reit_industrial_refill",
                rank=6,
                sleeve_id="next_reit_industrial_refill",
                symbols=["PLD", "CAT"],
                overrides={**_next_refill_overrides, "spread_time_exit_pct": 55.0},
            ),
        ],
        7,
    ),
]:
    _overrides = copy.deepcopy(_winner_timecombo_base)
    _overrides.update(
        {
            "capacity_tiers": _capacity_tiers,
            "max_per_allocation_group": 1,
            "max_per_ticker": 1,
            "max_total_index": 1,
        }
    )
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": _n_picks,
            "allowed": _active_universe_symbols(),
            "overrides": _overrides,
        }
    )

for _variant_id, _description, _symbols, _extra_overrides, _n_picks in [
    (
        "sleeve_next_index_move_bucket_baseline_v1",
        "QQQ/DIA/XLK move-bucket scout using the mixed-exit winner settings without IWM masking.",
        ["QQQ", "DIA", "XLK"],
        {"sleeve_id": "next_index_move_bucket", "sleeve_group": "next_index_move_bucket"},
        2,
    ),
    (
        "sleeve_next_index_move_bucket_coverage_v1",
        "QQQ/DIA/XLK move-bucket scout with only causal quote-survival filters added.",
        ["QQQ", "DIA", "XLK"],
        {
            **_next_mixedexit_overrides,
            "sleeve_id": "next_index_move_bucket_coverage",
            "sleeve_group": "next_index_move_bucket",
            "min_short_leg_prior_quote_days": 3,
        },
        2,
    ),
    (
        "sleeve_next_index_with_iwm_spy_control_v1",
        "SPY/IWM/QQQ/DIA/XLK control scout to separate IWM-driven index strength from move-bucket strength.",
        ["SPY", "IWM", "QQQ", "DIA", "XLK"],
        {
            **_next_mixedexit_overrides,
            "sleeve_id": "next_index_control",
            "sleeve_group": "next_index_control",
            "min_short_leg_prior_quote_days": 3,
            "max_total_index": 2,
        },
        3,
    ),
    (
        "sleeve_next_defensive_wmt_mixedexit_v1",
        "WMT-only defensive scout using mixed exits instead of the weak time-only refill shape.",
        ["WMT"],
        {
            **_next_mixedexit_overrides,
            "sleeve_id": "next_defensive_wmt_mixedexit",
            "sleeve_group": "next_defensive_refill",
        },
        1,
    ),
    (
        "sleeve_next_defensive_pm_mixedexit_v1",
        "PM-only defensive-income scout using mixed exits while missing exact exit quotes remain data-gated.",
        ["PM"],
        {
            **_next_mixedexit_overrides,
            "sleeve_id": "next_defensive_pm_mixedexit",
            "sleeve_group": "next_defensive_refill",
        },
        1,
    ),
    (
        "sleeve_next_reit_pld_mixedexit_v1",
        "PLD-only REIT scout using mixed exits after fixed-time cluster evidence turned negative.",
        ["PLD"],
        {
            **_next_mixedexit_overrides,
            "sleeve_id": "next_reit_pld_mixedexit",
            "sleeve_group": "next_reit_refill",
        },
        1,
    ),
    (
        "sleeve_next_industrial_cat_mixedexit_v1",
        "CAT-only industrial scout using mixed exits while lookup/backfill gaps remain data-gated.",
        ["CAT"],
        {
            **_next_mixedexit_overrides,
            "sleeve_id": "next_industrial_cat_mixedexit",
            "sleeve_group": "next_industrial_refill",
        },
        1,
    ),
    (
        "sleeve_next_high_beta_survival_v1",
        "NVDA/AMZN/TSLA bullish-pullback scout with fast exits and strict quote-survival filters.",
        ["NVDA", "AMZN", "TSLA"],
        {
            **_next_high_beta_survival_overrides,
            "sleeve_id": "next_high_beta_survival",
            "sleeve_group": "next_high_beta",
        },
        3,
    ),
    (
        "sleeve_next_high_beta_momentum_fast_v1",
        "NVDA/AMZN/TSLA bullish momentum scout with fast exits and strict quote-survival filters.",
        ["NVDA", "AMZN", "TSLA"],
        {
            **_next_high_beta_survival_overrides,
            "sleeve_id": "next_high_beta_momentum_fast",
            "sleeve_group": "next_high_beta",
            "entry_signal_id": "momentum",
            "allowed_signal_families": ["momentum"],
            "allowed_market_regimes": ["bullish"],
            "allowed_directions": ["call"],
            "min_quality_score": 65.0,
            "min_signal_ret5": 0.5,
            "max_signal_ret20": 35.0,
        },
        3,
    ),
    (
        "sleeve_next_high_beta_put_riskoff_v1",
        "NVDA/AMZN/TSLA bearish risk-off put scout with fast exits and strict quote-survival filters.",
        ["NVDA", "AMZN", "TSLA"],
        {
            **_next_high_beta_survival_overrides,
            "sleeve_id": "next_high_beta_put_riskoff",
            "sleeve_group": "next_high_beta",
            "entry_signal_id": "momentum",
            "allowed_signal_families": ["momentum"],
            "allowed_market_regimes": ["bearish"],
            "allowed_directions": ["put"],
            "min_quality_score": 65.0,
            "max_signal_ret5": -0.5,
            "max_signal_ret20": None,
        },
        3,
    ),
]:
    _overrides = copy.deepcopy(_clean_base_overrides)
    _overrides.update(_extra_overrides)
    VARIANTS.append(
        {
            "id": _variant_id,
            "description": _description,
            "n_picks": _n_picks,
            "allowed": _symbols,
            "overrides": _overrides,
        }
    )


def _theme_variants() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group_id, symbols in SLEEVE_GROUPS.items():
        active = _active_symbols(symbols)
        if not active:
            continue
        rows.append(
            {
                "id": f"sleeve_theme_{group_id}",
                "description": f"Standalone theme sleeve: {group_id}.",
                "n_picks": 2,
                "allowed": active,
                "overrides": {
                    "sleeve_id": group_id,
                    "sleeve_group": group_id,
                    "pullback_ret20_min": 2.0,
                    "pullback_ret5_min": -3.0,
                    "pullback_ret5_max": 0.75,
                    "scan_min_confidence": 60.0,
                    "execution_survivability_enabled": True,
                    "min_tradability_score": 60.0,
                    "min_short_leg_prior_quote_days": 1,
                },
            }
        )
    return rows


def _ticker_variants() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in _active_universe_symbols():
        rows.append(
            {
                "id": f"sleeve_ticker_{symbol.lower()}",
                "description": f"Per-symbol research sleeve: {symbol}.",
                "n_picks": 1,
                "allowed": [symbol],
                "overrides": {
                    "sleeve_id": f"ticker_{symbol}",
                    "sleeve_group": "per_symbol",
                    "pullback_ret20_min": 2.0,
                    "pullback_ret5_min": -3.0,
                    "pullback_ret5_max": 0.75,
                    "scan_min_confidence": 60.0,
                    "execution_survivability_enabled": True,
                    "min_tradability_score": 60.0,
                    "min_short_leg_prior_quote_days": 1,
                },
            }
        )
    return rows


def _build_playbook(variant: dict[str, Any]) -> dict[str, Any]:
    active = _active_universe_symbols()
    playbook = copy.deepcopy(wfo.REPLAY_PLAYBOOKS["bullish_pullback_observation"])
    playbook.update(BASE_OVERRIDES)
    playbook.update(variant.get("overrides") or {})
    allowed = variant.get("allowed")
    if allowed is not None:
        allowed_symbols = _active_symbols(list(allowed))
    else:
        allowed_symbols = active
    playbook["allowed_tickers"] = allowed_symbols
    playbook["historical_required_underlyings"] = allowed_symbols
    playbook["id"] = str(variant["id"])
    playbook["label"] = str(variant.get("description") or variant["id"])
    return playbook


def _summarize(result: dict[str, Any]) -> dict[str, Any]:
    metrics = result.get("exact_contract_metrics") or result.get("authoritative_profitability_metrics") or {}
    return {
        "result_path": result.get("result_path"),
        "candidate_trade_count": result.get("candidate_trade_count"),
        "priced_trade_count": result.get("priced_trade_count"),
        "unpriced_trade_count": result.get("unpriced_trade_count"),
        "quote_coverage_pct": result.get("quote_coverage_pct"),
        "avg_picks_per_day": result.get("avg_picks_per_day"),
        "exact_trade_count": metrics.get("trade_count"),
        "exact_profit_factor": metrics.get("profit_factor"),
        "exact_avg_pnl_pct": metrics.get("avg_pnl_pct"),
        "exact_directional_accuracy_pct": metrics.get("directional_accuracy_pct"),
        "by_sleeve": result.get("by_sleeve") or {},
        "by_tier": result.get("by_tier") or {},
        "pre_entry_filtered_candidate_count": result.get("pre_entry_filtered_candidate_count"),
        "pre_entry_filtered_candidate_reasons": result.get("pre_entry_filtered_candidate_reasons") or {},
    }


def run_variants(*, lookback_years: int, only: set[str] | None = None, include_themes: bool = False, include_tickers: bool = False) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    variants = list(VARIANTS)
    if include_themes:
        variants.extend(_theme_variants())
    if include_tickers:
        variants.extend(_ticker_variants())
    original_playbooks = copy.deepcopy(wfo.REPLAY_PLAYBOOKS)
    try:
        for variant in variants:
            if only and str(variant["id"]) not in only:
                continue
            playbook = _build_playbook(variant)
            wfo.REPLAY_PLAYBOOKS[str(playbook["id"]).lower()] = playbook
            result = wfo.run_historical_backtest(
                lookback_years=int(lookback_years),
                n_picks=int(variant.get("n_picks", 3)),
                pricing_lane="pessimistic",
                truth_lane=wfo.IMPORTED_TRUTH_SOURCE,
                playbook=playbook["id"],
                historical_source_labels="thetadata_opra_nbbo_1m",
                allow_research_imported_data=False,
                min_imported_calendar_dates=252,
                save_result=True,
            )
            rows.append(
                {
                    "variant_id": playbook["id"],
                    "description": variant.get("description"),
                    "n_picks": int(variant.get("n_picks", 3)),
                    "validation_universe_count": len(playbook.get("historical_required_underlyings") or []),
                    "cmcsa_active": "CMCSA" in set(playbook.get("historical_required_underlyings") or []),
                    **_summarize(result),
                }
            )
    finally:
        wfo.REPLAY_PLAYBOOKS.clear()
        wfo.REPLAY_PLAYBOOKS.update(original_playbooks)

    ranked = sorted(
        rows,
        key=lambda row: (
            float(row.get("exact_profit_factor") or 0.0),
            int(row.get("exact_trade_count") or 0),
            float(row.get("exact_avg_pnl_pct") or 0.0),
        ),
        reverse=True,
    )
    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "active_universe_count": len(_active_universe_symbols()),
        "cmcsa_active": "CMCSA" in set(_active_universe_symbols()),
        "rows": rows,
        "ranked": ranked,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"sleeve_round_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf8")
    report["output_path"] = str(out_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bullish pullback sleeve profitability variants.")
    parser.add_argument("--lookback-years", type=int, default=1)
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--include-themes", action="store_true")
    parser.add_argument("--include-tickers", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run_variants(
        lookback_years=args.lookback_years,
        only=set(args.only) if args.only else None,
        include_themes=bool(args.include_themes),
        include_tickers=bool(args.include_tickers),
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Wrote {report['output_path']}")
        for row in report["ranked"][:10]:
            print(
                row["variant_id"],
                "exact",
                row.get("exact_trade_count"),
                "pf",
                row.get("exact_profit_factor"),
                "avg",
                row.get("exact_avg_pnl_pct"),
                "coverage",
                row.get("quote_coverage_pct"),
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
