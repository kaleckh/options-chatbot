from __future__ import annotations

import argparse
import copy
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_env import load_local_env

load_local_env(ROOT)

os.environ["OPTIONS_MARKET_DATA_PROVIDER"] = "alpaca"
os.environ["HISTORICAL_OPTIONS_DB_PATH"] = str(ROOT / "data" / "options-validation" / "options_history.db")

import wfo_optimizer as wfo  # noqa: E402
from scripts import imported_intraday_robustness as robustness_runner  # noqa: E402
from scripts import run_bullish_pullback_sleeves as sleeve_runner  # noqa: E402
from scripts import run_lane_lab as lane_lab  # noqa: E402
from scripts import run_regular_options_multilane_portfolio as multilane  # noqa: E402
from scripts import run_side_aware_zero_bid_replay as zero_bid_replay  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-autoresearch" / "all-planned-sleeves"
OPTIONS_HISTORY_DB = ROOT / "data" / "options-validation" / "options_history.db"
TRUSTED_INTRADAY_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
BASE_CLEAN_LANE_IDS = {"bullish_pullback_core", "bullish_pullback_clean_exact_reference"}
TARGET_CLEAN_TRADES = 200
PORTFOLIO_CANDIDATE_MIN_EXACT_TRADES = 100
MIN_TRUSTED_INTRADAY_DATES_FOR_READINESS = 252
ZERO_BID_EXIT_RATE_MAX_PCT = 2.0
ZERO_BID_REPLAY_MIN_COMBINED_PF = 1.5

TRACKED_WINNER_UNIVERSE = ["SPY", "QQQ", "GOOGL", "DIA", "NVDA"]
RELATIVE_STRENGTH_TEST_UNIVERSE = [
    "QQQ",
    "DIA",
    "XLK",
    "NVDA",
    "AMZN",
    "TSLA",
    "WMT",
    "PM",
    "CAT",
    "PLD",
    "MSFT",
    "META",
    "AMD",
    "NFLX",
    "JPM",
    "GS",
    "BAC",
    "V",
    "C",
    "DIS",
    "COST",
    "PG",
    "BA",
    "DE",
    "LMT",
    "RTX",
    "FCX",
    "PLTR",
    "ARM",
    "SMCI",
]
REGULAR_SECTOR_ETF_UNIVERSE = ["XLE", "XLF", "KRE", "SMH"]

SLEEVE_VARIANTS: list[dict[str, Any]] = [
    {
        "lane_id": "etf_index_pullback_control",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_index_refill_v1",
        "description": "QQQ/DIA/XLK refill added to the frozen keep cluster.",
    },
    {
        "lane_id": "etf_index_pullback_control",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_index_move_bucket_baseline_v1",
        "description": "Standalone QQQ/DIA/XLK move-bucket baseline.",
    },
    {
        "lane_id": "etf_index_pullback_control",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_index_move_bucket_coverage_v1",
        "description": "Standalone QQQ/DIA/XLK move-bucket with quote-survival filters.",
    },
    {
        "lane_id": "etf_index_pullback_control",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_index_with_iwm_spy_control_v1",
        "description": "SPY/IWM/QQQ/DIA/XLK control for index-bucket overlap.",
    },
    {
        "lane_id": "iwm_small_cap_risk",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_ticker_iwm",
        "description": "IWM per-symbol bullish-pullback small-cap risk component.",
        "include_tickers": True,
    },
    {
        "lane_id": "defensive_refill_income",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_defensive_refill_v1",
        "description": "WMT/PM defensive refill added to the frozen keep cluster.",
    },
    {
        "lane_id": "defensive_refill_income",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_defensive_wmt_mixedexit_v1",
        "description": "WMT-only mixed-exit defensive scout.",
    },
    {
        "lane_id": "defensive_refill_income",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_defensive_pm_mixedexit_v1",
        "description": "PM-only mixed-exit defensive-income scout.",
    },
    {
        "lane_id": "reit_rate_sensitive",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_reit_industrial_refill_v1",
        "description": "PLD/CAT refill added to the frozen keep cluster.",
    },
    {
        "lane_id": "reit_rate_sensitive",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_reit_pld_mixedexit_v1",
        "description": "PLD-only mixed-exit REIT scout.",
    },
    {
        "lane_id": "industrial_scout",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_industrial_cat_mixedexit_v1",
        "description": "CAT-only mixed-exit industrial scout.",
    },
    {
        "lane_id": "high_beta_momentum_volatility",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_high_beta_survival_v1",
        "description": "NVDA/AMZN/TSLA bullish-pullback high-beta scout.",
    },
    {
        "lane_id": "high_beta_momentum_volatility",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_high_beta_momentum_fast_v1",
        "description": "NVDA/AMZN/TSLA high-beta momentum scout.",
    },
    {
        "lane_id": "high_beta_momentum_volatility",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_high_beta_put_riskoff_v1",
        "description": "NVDA/AMZN/TSLA bearish high-beta riskoff scout.",
    },
    {
        "lane_id": "move_bucket_combined_control",
        "runner": "bullish_sleeve",
        "variant_id": "sleeve_next_move_bucket_refill_v1",
        "description": "Combined ETF/index, defensive, and PLD/CAT move-bucket refill control.",
    },
]

GENERIC_TIME_EXIT = {
    "chain_native_spread_selection": True,
    "chain_native_min_dte": 21,
    "chain_native_max_dte": 45,
    "spread_exit_monitoring_mode": "time_only",
    "spread_time_exit_pct": 55.0,
    "max_debit_pct_of_width": 55.0,
}

WFO_VARIANTS: list[dict[str, Any]] = [
    {
        "lane_id": "bearish_put_debit_spread",
        "runner": "wfo_playbook",
        "variant_id": "regular_bearish_put_primary_chain_native_timeexit_all_sleeves",
        "base_playbook": "regular_bearish_put_primary",
        "n_picks": 5,
        "description": "Full regular bearish put primary chain-native time-exit replay.",
        "overrides": {**GENERIC_TIME_EXIT, "allowed_directions": ["put"], "max_debit_pct_of_width": 60.0},
    },
    {
        "lane_id": "bearish_index_put_observation",
        "runner": "wfo_playbook",
        "variant_id": "bearish_index_put_observation_chain_native_timeexit_all_sleeves",
        "base_playbook": "bearish_index_put_observation",
        "n_picks": 3,
        "description": "Index-only bearish put chain-native time-exit replay.",
        "overrides": {**GENERIC_TIME_EXIT, "allowed_directions": ["put"], "max_debit_pct_of_width": 60.0},
    },
    {
        "lane_id": "range_breakout_observation",
        "runner": "wfo_playbook",
        "variant_id": "range_breakout_observation_chain_native_call_timeexit_all_sleeves",
        "base_playbook": "range_breakout_observation",
        "n_picks": 3,
        "description": "Range-breakout call side chain-native time-exit replay.",
        "overrides": {**GENERIC_TIME_EXIT, "allowed_directions": ["call"]},
    },
    {
        "lane_id": "range_breakout_observation",
        "runner": "wfo_playbook",
        "variant_id": "range_breakout_observation_chain_native_put_timeexit_all_sleeves",
        "base_playbook": "range_breakout_observation",
        "n_picks": 3,
        "description": "Range-breakout put side chain-native time-exit replay.",
        "overrides": {**GENERIC_TIME_EXIT, "allowed_directions": ["put"]},
    },
    {
        "lane_id": "volatility_expansion_observation",
        "runner": "wfo_playbook",
        "variant_id": "volatility_expansion_observation_chain_native_call_timeexit_all_sleeves",
        "base_playbook": "volatility_expansion_observation",
        "n_picks": 3,
        "description": "Volatility-expansion call side chain-native time-exit replay.",
        "overrides": {**GENERIC_TIME_EXIT, "allowed_directions": ["call"]},
    },
    {
        "lane_id": "volatility_expansion_observation",
        "runner": "wfo_playbook",
        "variant_id": "volatility_expansion_observation_chain_native_put_timeexit_all_sleeves",
        "base_playbook": "volatility_expansion_observation",
        "n_picks": 3,
        "description": "Volatility-expansion put side chain-native time-exit replay.",
        "overrides": {**GENERIC_TIME_EXIT, "allowed_directions": ["put"]},
    },
    {
        "lane_id": "volatility_expansion_observation",
        "runner": "wfo_playbook",
        "variant_id": "volatility_expansion_observation_chain_native_call_fast35_all_sleeves",
        "base_playbook": "volatility_expansion_observation",
        "n_picks": 3,
        "description": "Volatility-expansion call side with faster 35% DTE time exit.",
        "overrides": {**GENERIC_TIME_EXIT, "allowed_directions": ["call"], "spread_time_exit_pct": 35.0},
    },
    {
        "lane_id": "bullish_mean_reversion",
        "runner": "wfo_playbook",
        "variant_id": "bullish_mean_reversion_chain_native_call_timeexit_all_sleeves",
        "base_playbook": "bullish_mean_reversion",
        "n_picks": 3,
        "description": "Bullish mean-reversion call side chain-native time-exit replay.",
        "overrides": {**GENERIC_TIME_EXIT, "allowed_directions": ["call"]},
    },
    {
        "lane_id": "bearish_defensive",
        "runner": "wfo_playbook",
        "variant_id": "bearish_defensive_chain_native_put_timeexit_all_sleeves",
        "base_playbook": "bearish_defensive",
        "n_picks": 3,
        "description": "Bearish defensive put side chain-native time-exit replay.",
        "overrides": {**GENERIC_TIME_EXIT, "allowed_directions": ["put"], "max_debit_pct_of_width": 60.0},
    },
    {
        "lane_id": "iwm_small_cap_risk",
        "runner": "wfo_playbook",
        "variant_id": "iwm_small_cap_risk_call_chain_native_timeexit_all_sleeves",
        "base_playbook": "bullish_pullback_observation",
        "n_picks": 1,
        "description": "IWM-only small-cap risk-on call debit-spread replay.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "allowed_tickers": ["IWM"],
            "historical_required_underlyings": ["IWM"],
            "allowed_directions": ["call"],
            "chain_native_max_dte": 35,
            "max_debit_pct_of_width": 45.0,
        },
    },
    {
        "lane_id": "iwm_small_cap_risk",
        "runner": "wfo_playbook",
        "variant_id": "iwm_small_cap_risk_put_chain_native_timeexit_all_sleeves",
        "base_playbook": "bearish_index_put_observation",
        "n_picks": 1,
        "description": "IWM-only small-cap risk-off put debit-spread replay.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "allowed_tickers": ["IWM"],
            "historical_required_underlyings": ["IWM"],
            "allowed_directions": ["put"],
            "chain_native_max_dte": 35,
            "max_debit_pct_of_width": 45.0,
        },
    },
    {
        "lane_id": "tlt_duration_shock",
        "runner": "wfo_playbook",
        "variant_id": "tlt_duration_shock_call_chain_native_timeexit_all_sleeves",
        "base_playbook": "volatility_expansion_observation",
        "n_picks": 1,
        "description": "TLT-only duration-shock call debit-spread replay.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "allowed_tickers": ["TLT"],
            "historical_required_underlyings": ["TLT"],
            "allowed_directions": ["call"],
            "chain_native_max_dte": 45,
            "max_debit_pct_of_width": 45.0,
        },
    },
    {
        "lane_id": "tlt_duration_shock",
        "runner": "wfo_playbook",
        "variant_id": "tlt_duration_shock_put_chain_native_timeexit_all_sleeves",
        "base_playbook": "volatility_expansion_observation",
        "n_picks": 1,
        "description": "TLT-only duration-shock put debit-spread replay.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "allowed_tickers": ["TLT"],
            "historical_required_underlyings": ["TLT"],
            "allowed_directions": ["put"],
            "chain_native_max_dte": 45,
            "max_debit_pct_of_width": 45.0,
        },
    },
    {
        "lane_id": "xle_energy_inflation",
        "runner": "wfo_playbook",
        "variant_id": "xle_energy_inflation_call_chain_native_timeexit_all_sleeves",
        "base_playbook": "volatility_expansion_observation",
        "n_picks": 1,
        "description": "XLE-only energy inflation-beta call debit-spread replay.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "allowed_tickers": ["XLE"],
            "historical_required_underlyings": ["XLE"],
            "allowed_directions": ["call"],
            "chain_native_max_dte": 35,
            "max_debit_pct_of_width": 42.0,
        },
    },
    {
        "lane_id": "xle_energy_inflation",
        "runner": "wfo_playbook",
        "variant_id": "xle_energy_inflation_put_chain_native_timeexit_all_sleeves",
        "base_playbook": "volatility_expansion_observation",
        "n_picks": 1,
        "description": "XLE-only energy inflation-beta put debit-spread replay.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "allowed_tickers": ["XLE"],
            "historical_required_underlyings": ["XLE"],
            "allowed_directions": ["put"],
            "chain_native_max_dte": 35,
            "max_debit_pct_of_width": 42.0,
        },
    },
    {
        "lane_id": "xlf_financials",
        "runner": "wfo_playbook",
        "variant_id": "xlf_financials_call_chain_native_timeexit_all_sleeves",
        "base_playbook": "volatility_expansion_observation",
        "n_picks": 1,
        "description": "XLF-only financials call debit-spread replay.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "allowed_tickers": ["XLF"],
            "historical_required_underlyings": ["XLF"],
            "allowed_directions": ["call"],
            "chain_native_max_dte": 45,
            "max_debit_pct_of_width": 45.0,
        },
    },
    {
        "lane_id": "xlf_financials",
        "runner": "wfo_playbook",
        "variant_id": "xlf_financials_put_chain_native_timeexit_all_sleeves",
        "base_playbook": "volatility_expansion_observation",
        "n_picks": 1,
        "description": "XLF-only financials put debit-spread replay.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "allowed_tickers": ["XLF"],
            "historical_required_underlyings": ["XLF"],
            "allowed_directions": ["put"],
            "chain_native_max_dte": 45,
            "max_debit_pct_of_width": 45.0,
        },
    },
    {
        "lane_id": "kre_regional_bank_observation",
        "runner": "wfo_playbook",
        "variant_id": "kre_regional_bank_call_chain_native_timeexit_all_sleeves",
        "base_playbook": "volatility_expansion_observation",
        "n_picks": 1,
        "description": "KRE-only regional-bank call debit-spread observation replay.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "allowed_tickers": ["KRE"],
            "historical_required_underlyings": ["KRE"],
            "allowed_directions": ["call"],
            "chain_native_max_dte": 45,
            "max_debit_pct_of_width": 45.0,
        },
    },
    {
        "lane_id": "kre_regional_bank_observation",
        "runner": "wfo_playbook",
        "variant_id": "kre_regional_bank_put_chain_native_timeexit_all_sleeves",
        "base_playbook": "volatility_expansion_observation",
        "n_picks": 1,
        "description": "KRE-only regional-bank put debit-spread observation replay.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "allowed_tickers": ["KRE"],
            "historical_required_underlyings": ["KRE"],
            "allowed_directions": ["put"],
            "chain_native_max_dte": 45,
            "max_debit_pct_of_width": 45.0,
        },
    },
    {
        "lane_id": "smh_semiconductor",
        "runner": "wfo_playbook",
        "variant_id": "smh_semiconductor_call_chain_native_timeexit_all_sleeves",
        "base_playbook": "bullish_pullback_observation",
        "n_picks": 1,
        "description": "SMH-only semiconductor momentum call debit-spread replay.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "allowed_tickers": ["SMH"],
            "historical_required_underlyings": ["SMH"],
            "allowed_directions": ["call"],
            "chain_native_max_dte": 35,
            "max_debit_pct_of_width": 45.0,
        },
    },
    {
        "lane_id": "sector_rotation_confirmation",
        "runner": "wfo_playbook",
        "variant_id": "sector_rotation_regular_etf_call_stack_v1",
        "base_playbook": "bullish_pullback_observation",
        "n_picks": 2,
        "description": "Regular sector ETF relative-strength call stack excluding GLD/commodity lane exposure.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "entry_signal_id": "relative_strength_pullback",
            "allowed_tickers": REGULAR_SECTOR_ETF_UNIVERSE,
            "historical_required_underlyings": REGULAR_SECTOR_ETF_UNIVERSE,
            "allowed_directions": ["call"],
            "allowed_signal_families": ["relative_strength_pullback"],
            "relative_strength_pullback_ret20_min": 2.0,
            "relative_strength_pullback_ret5_min": -4.0,
            "relative_strength_pullback_ret5_max": -0.25,
            "relative_strength_pullback_rsi_min": 42.0,
            "relative_strength_pullback_rsi_max": 60.0,
            "max_debit_pct_of_width": 45.0,
        },
    },
    {
        "lane_id": "tracked_winner_primary",
        "runner": "wfo_playbook",
        "variant_id": "tracked_winner_chain_native_qqq_time65_all_sleeves",
        "base_playbook": "tracked_winner_chain_native_qqq_time65_research",
        "n_picks": 5,
        "description": "Tracked-winner QQQ time65 replacement probe.",
        "overrides": {},
    },
    {
        "lane_id": "tracked_winner_primary",
        "runner": "wfo_playbook",
        "variant_id": "tracked_winner_chain_native_research_all_sleeves",
        "base_playbook": "tracked_winner_chain_native_research",
        "n_picks": 5,
        "description": "Tracked-winner no-XLK replacement probe.",
        "overrides": {},
    },
    {
        "lane_id": "tracked_winner_primary",
        "runner": "wfo_playbook",
        "variant_id": "tracked_winner_chain_native_no_spy_time65_all_sleeves",
        "base_playbook": "tracked_winner_chain_native_research",
        "n_picks": 5,
        "description": "Tracked-winner no-SPY repair with time65 exit.",
        "overrides": {
            "allowed_tickers": ["GOOGL", "DIA", "NVDA"],
            "historical_required_underlyings": ["GOOGL", "DIA", "NVDA"],
            "spread_time_exit_pct": 65.0,
        },
    },
    {
        "lane_id": "tracked_winner_primary",
        "runner": "wfo_playbook",
        "variant_id": "tracked_winner_chain_native_googl_nvda_time65_all_sleeves",
        "base_playbook": "tracked_winner_chain_native_qqq_time65_research",
        "n_picks": 5,
        "description": "Tracked-winner GOOGL/NVDA repair after weak index-basket readback.",
        "overrides": {
            "allowed_tickers": ["GOOGL", "NVDA"],
            "historical_required_underlyings": ["GOOGL", "NVDA"],
        },
    },
    {
        "lane_id": "tracked_winner_primary",
        "runner": "wfo_playbook",
        "variant_id": "tracked_winner_cheap_debit_continuity_v1",
        "base_playbook": "tracked_winner_chain_native_qqq_time65_research",
        "n_picks": 5,
        "description": "Tracked-winner repair with cheap debit, prior-quote continuity, and short-leg bid hygiene.",
        "overrides": {
            "allowed_tickers": TRACKED_WINNER_UNIVERSE,
            "historical_required_underlyings": TRACKED_WINNER_UNIVERSE,
            "max_debit_pct_of_width": 45.0,
            "spread_max_width_pct": 15.0,
            "chain_native_min_entry_short_bid": 0.10,
            "chain_native_min_prior_quote_days": 1,
            "chain_native_prior_quote_lookback_days": 30,
            "min_short_leg_prior_quote_days": 1,
            "spread_time_exit_pct": 65.0,
        },
    },
    {
        "lane_id": "liquidity_first_spread",
        "runner": "wfo_playbook",
        "variant_id": "tracked_winner_liquidity_first_contract_hygiene_v1",
        "base_playbook": "tracked_winner_chain_native_qqq_time65_research",
        "n_picks": 5,
        "description": "Tracked-winner liquidity-first causal contract hygiene probe using entry-time quote continuity and spread quality.",
        "overrides": {
            "allowed_tickers": TRACKED_WINNER_UNIVERSE,
            "historical_required_underlyings": TRACKED_WINNER_UNIVERSE,
            "max_debit_pct_of_width": 45.0,
            "spread_max_width_pct": 12.0,
            "spread_time_exit_pct": 65.0,
            "chain_native_max_entry_leg_bid_ask_pct": 30.0,
            "chain_native_min_entry_short_bid": 0.15,
            "chain_native_min_prior_quote_days": 2,
            "chain_native_min_short_prior_quote_days": 3,
            "chain_native_prior_quote_lookback_days": 30,
            "chain_native_prior_quote_score_weight": 0.5,
            "chain_native_short_prior_quote_score_weight": 1.5,
            "chain_native_prior_quote_score_cap": 8,
            "chain_native_short_inside_steps": 1,
            "execution_survivability_enabled": True,
            "tradability_lookback_days": 30,
            "min_tradability_score": 70.0,
            "min_long_leg_prior_quote_days": 1,
            "min_short_leg_prior_quote_days": 3,
        },
    },
    {
        "lane_id": "bearish_put_debit_spread",
        "runner": "wfo_playbook",
        "variant_id": "regular_bearish_put_index_narrow_timeexit_all_sleeves",
        "base_playbook": "regular_bearish_put_primary",
        "n_picks": 2,
        "description": "Narrowed SPY/QQQ bearish put repair after broad bearish coverage failure.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "allowed_tickers": ["SPY", "QQQ"],
            "historical_required_underlyings": ["SPY", "QQQ"],
            "allowed_directions": ["put"],
            "max_debit_pct_of_width": 60.0,
        },
    },
    {
        "lane_id": "relative_strength_pullback",
        "runner": "wfo_playbook",
        "variant_id": "relative_strength_pullback_ex_clean_universe_v1",
        "base_playbook": "bullish_pullback_observation",
        "n_picks": 5,
        "description": "Relative-strength pullback over symbols outside the current clean keep stack.",
        "overrides": {
            **GENERIC_TIME_EXIT,
            "entry_signal_id": "relative_strength_pullback",
            "allowed_tickers": RELATIVE_STRENGTH_TEST_UNIVERSE,
            "historical_required_underlyings": RELATIVE_STRENGTH_TEST_UNIVERSE,
            "allowed_directions": ["call"],
            "allowed_signal_families": ["relative_strength_pullback"],
            "relative_strength_pullback_ret20_min": 4.0,
            "relative_strength_pullback_ret5_min": -4.0,
            "relative_strength_pullback_ret5_max": -0.25,
            "relative_strength_pullback_rsi_min": 42.0,
            "relative_strength_pullback_rsi_max": 58.0,
            "max_debit_pct_of_width": 50.0,
        },
    },
]

IMPLEMENTED_PLANNED_VARIANTS = SLEEVE_VARIANTS + WFO_VARIANTS


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _metric_value(run: dict[str, Any], key: str) -> Any:
    metrics = run.get("authoritative_profitability_metrics") or run.get("exact_contract_metrics") or {}
    if key in metrics:
        return metrics.get(key)
    return run.get(key)


def _run_metrics(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_trade_count": int(run.get("candidate_trade_count") or 0),
        "priced_trade_count": int(run.get("priced_trade_count") or run.get("total_trades") or 0),
        "exact_trade_count": int(_metric_value(run, "trade_count") or run.get("exact_contract_match_count") or 0),
        "unpriced_trade_count": int(run.get("unpriced_trade_count") or 0),
        "quote_coverage_pct": round(float(run.get("quote_coverage_pct") or 0.0), 2),
        "profit_factor": round(float(_metric_value(run, "profit_factor") or 0.0), 2),
        "avg_pnl_pct": round(float(_metric_value(run, "avg_pnl_pct") or 0.0), 2),
        "win_rate_pct": round(float(_metric_value(run, "win_rate_pct") or 0.0), 2),
    }


def _variant_row(report: dict[str, Any], variant_id: str) -> dict[str, Any]:
    for row in report.get("rows") or report.get("variants") or []:
        if str(row.get("variant_id")) == variant_id:
            return row
    raise RuntimeError(f"Variant {variant_id} did not produce a result row.")


def _run_bullish_sleeve_variant(spec: dict[str, Any], *, lookback_years: int) -> Path:
    report = sleeve_runner.run_variants(
        lookback_years=lookback_years,
        only={str(spec["variant_id"])},
        include_themes=bool(spec.get("include_themes")),
        include_tickers=bool(spec.get("include_tickers")),
    )
    row = _variant_row(report, str(spec["variant_id"]))
    result_path = row.get("result_path")
    if not result_path:
        raise RuntimeError(f"{spec['variant_id']} did not write a replay artifact.")
    return Path(str(result_path)).resolve()


def _run_wfo_variant(spec: dict[str, Any], *, lookback_years: int) -> Path:
    original_playbooks = copy.deepcopy(wfo.REPLAY_PLAYBOOKS)
    try:
        playbook = _wfo_playbook_for_spec(spec)
        wfo.REPLAY_PLAYBOOKS[str(playbook["id"]).lower()] = playbook
        result = wfo.run_historical_backtest(
            lookback_years=int(lookback_years),
            n_picks=int(spec.get("n_picks", 3)),
            pricing_lane="pessimistic",
            truth_lane=wfo.IMPORTED_TRUTH_SOURCE,
            playbook=playbook["id"],
            historical_source_labels="thetadata_opra_nbbo_1m",
            allow_research_imported_data=False,
            min_imported_calendar_dates=252,
            save_result=True,
        )
    finally:
        wfo.REPLAY_PLAYBOOKS.clear()
        wfo.REPLAY_PLAYBOOKS.update(original_playbooks)
    result_path = result.get("result_path")
    if not result_path:
        raise RuntimeError(f"{spec['variant_id']} did not write a replay artifact.")
    return Path(str(result_path)).resolve()


def _run_variant(spec: dict[str, Any], *, lookback_years: int) -> Path:
    if spec["runner"] == "bullish_sleeve":
        return _run_bullish_sleeve_variant(spec, lookback_years=lookback_years)
    if spec["runner"] == "wfo_playbook":
        return _run_wfo_variant(spec, lookback_years=lookback_years)
    raise ValueError(f"Unsupported runner {spec['runner']!r}")


def _run_robustness(run_path: Path, output_dir: Path) -> tuple[dict[str, Any], Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run = _load_json(run_path)
    report = robustness_runner.build_intraday_robustness_report(
        run,
        train_days=50,
        test_days=20,
        min_exact_test_trades=5,
        slippage_values=[0.0, 1.0, 2.5, 5.0],
    )
    artifacts = robustness_runner.write_report(report, output_dir=output_dir)
    report["artifacts"] = artifacts
    return report, Path(artifacts["latest_playbook_json"])


def _robustness_summary(report: dict[str, Any]) -> dict[str, Any]:
    rolling = report.get("rolling_oos") or {}
    stress_rows = report.get("slippage_stress") or []
    stress_5 = {}
    for row in stress_rows:
        if abs(float(row.get("slippage_pct_per_side") or 0.0) - 5.0) < 0.001:
            stress_5 = row.get("metrics") or {}
            break
    return {
        "status": report.get("status"),
        "rolling_status": rolling.get("status"),
        "stress_5pct_per_side_profit_factor": round(float(stress_5.get("profit_factor") or 0.0), 2) if stress_5 else None,
    }


def _wfo_playbook_for_spec(spec: dict[str, Any]) -> dict[str, Any]:
    base_playbook_id = str(spec["base_playbook"])
    playbook = copy.deepcopy(wfo.REPLAY_PLAYBOOKS[base_playbook_id])
    playbook.update(copy.deepcopy(spec.get("overrides") or {}))
    playbook["id"] = str(spec["variant_id"])
    playbook["label"] = str(spec.get("description") or spec["variant_id"])
    return playbook


def _side_aware_risk_config(spec: dict[str, Any]) -> dict[str, float]:
    playbook = _wfo_playbook_for_spec(spec) if spec.get("runner") == "wfo_playbook" else {}
    return {
        "stop_loss_pct": float(playbook.get("spread_stop_loss_pct", playbook.get("stop_loss_pct", 200.0)) or 200.0),
        "profit_target_pct": float(playbook.get("spread_profit_target_pct", playbook.get("profit_target_pct", 150.0)) or 150.0),
        "time_exit_pct": float(playbook.get("spread_time_exit_pct", playbook.get("time_exit_pct", 75.0)) or 75.0),
        "trailing_profit_pct": float(playbook.get("trailing_profit_pct", 40.0) or 40.0),
        "trailing_giveback_pct": float(playbook.get("trailing_giveback_pct", 50.0) or 50.0),
    }


def _missing_exit_candidates(run: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        trade
        for trade in run.get("unpriced_trades") or []
        if str(trade.get("unpriced_reason") or trade.get("non_promotable_reason") or "") == "missing_exit_quote_for_leg"
    ]


def _should_run_side_aware_zero_bid(run: dict[str, Any], metrics: dict[str, Any], novelty: dict[str, Any]) -> tuple[bool, str]:
    missing_exit_count = len(_missing_exit_candidates(run))
    if missing_exit_count <= 0:
        return False, "no_missing_exit_quote_candidates"
    if int(novelty.get("gap_after_candidate") or 0) > 0:
        return False, "candidate_does_not_close_clean_count_gap"
    if float(metrics.get("profit_factor") or 0.0) < ZERO_BID_REPLAY_MIN_COMBINED_PF:
        return False, "priced_only_pf_below_zero_bid_probe_floor"
    if float(metrics.get("avg_pnl_pct") or 0.0) <= 0:
        return False, "priced_only_avg_not_positive"
    return True, "gap_closing_profitable_candidate_has_missing_exits"


def _compact_side_aware_zero_bid_report(
    report: dict[str, Any],
    *,
    artifact_path: Path,
    trigger_reason: str,
) -> dict[str, Any]:
    modes: dict[str, Any] = {}
    for mode_name, mode in (report.get("modes") or {}).items():
        combined_metrics = mode.get("combined_with_existing_metrics") or mode.get("combined_with_existing_lane_a_metrics") or {}
        combined_priced = int(mode.get("combined_priced_count") or mode.get("combined_lane_a_priced_count") or 0)
        zero_bid_priced = int(mode.get("zero_bid_priced_count") or 0)
        modes[str(mode_name)] = {
            "candidate_count": int(mode.get("candidate_count") or 0),
            "priced_count": int(mode.get("priced_count") or 0),
            "unpriced_count": int(mode.get("unpriced_count") or 0),
            "zero_bid_priced_count": zero_bid_priced,
            "zero_bid_exit_rate_pct": round(100.0 * zero_bid_priced / combined_priced, 2) if combined_priced else None,
            "side_aware_metrics": mode.get("side_aware_metrics") or {},
            "combined_with_existing_metrics": combined_metrics,
            "combined_priced_count": combined_priced,
            "combined_unpriced_count": int(mode.get("combined_unpriced_count") or mode.get("combined_lane_a_unpriced_count") or 0),
            "combined_quote_coverage_pct": mode.get("combined_quote_coverage_pct", mode.get("combined_lane_a_quote_coverage_pct")),
            "exit_reasons": mode.get("exit_reasons") or {},
            "unpriced_reasons": mode.get("unpriced_reasons") or {},
        }
    return {
        "status": "completed",
        "trigger_reason": trigger_reason,
        "artifact": str(artifact_path),
        "assumptions": report.get("assumptions") or {},
        "provider_stats": report.get("provider_stats") or {},
        "modes": modes,
    }


def _run_side_aware_zero_bid_if_needed(
    *,
    run_path: Path,
    run: dict[str, Any],
    spec: dict[str, Any],
    metrics: dict[str, Any],
    novelty: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    should_run, reason = _should_run_side_aware_zero_bid(run, metrics, novelty)
    candidate_count = len(_missing_exit_candidates(run))
    if not should_run:
        return {
            "status": "not_required",
            "reason": reason,
            "candidate_count": candidate_count,
        }
    risk = _side_aware_risk_config(spec)
    try:
        report = zero_bid_replay.run_replay(
            run_path.resolve(),
            db_path=zero_bid_replay.DEFAULT_HISTORICAL_OPTIONS_DB_PATH.resolve(),
            theta_url=zero_bid_replay.DEFAULT_THETA_URL,
            source_labels=[zero_bid_replay.DEFAULT_SOURCE_LABEL],
            timeout=30.0,
            modes=["conservative", "midpoint_zero_bid"],
            **risk,
        )
    except Exception as exc:
        return {
            "status": "error",
            "reason": reason,
            "candidate_count": candidate_count,
            "error": str(exc),
            "assumptions": risk,
        }
    artifact_path = output_dir / "side_aware_zero_bid_report.json"
    _write_json(artifact_path, report)
    return _compact_side_aware_zero_bid_report(report, artifact_path=artifact_path, trigger_reason=reason)


def _conservative_zero_bid_mode(side_aware: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(side_aware, dict) or side_aware.get("status") != "completed":
        return {}
    modes = side_aware.get("modes") or {}
    mode = modes.get("conservative")
    return mode if isinstance(mode, dict) else {}


def _source_by_lane_id(lane_id: str) -> dict[str, Any]:
    for source in multilane.LANE_SOURCES:
        if str(source.get("lane_id")) == lane_id:
            return source
    raise KeyError(lane_id)


def _normalized_rows_for_source(source: dict[str, Any], *, include_in_proof: bool = True) -> list[dict[str, Any]]:
    run_path = Path(source["artifact"])
    run = _load_json(run_path)
    lane = dict(source)
    lane["artifact"] = run_path
    lane["include_in_proof_portfolio"] = include_in_proof
    rows = []
    for trade in run.get("trades") or []:
        rows.append(multilane.normalize_trade(trade, lane, run))
    return rows


def base_clean_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lane_id in ("bullish_pullback_core", "bullish_pullback_clean_exact_reference"):
        rows.extend(_normalized_rows_for_source(_source_by_lane_id(lane_id), include_in_proof=True))
    return rows


def candidate_rows(run_path: Path, spec: dict[str, Any]) -> list[dict[str, Any]]:
    run = _load_json(run_path)
    lane = {
        "lane_id": str(spec["variant_id"]),
        "family": str(spec["lane_id"]),
        "artifact": run_path,
        "priority": 90,
        "include_in_proof_portfolio": True,
    }
    return [multilane.normalize_trade(trade, lane, run) for trade in run.get("trades") or []]


def incremental_report(base_rows: list[dict[str, Any]], candidate: list[dict[str, Any]], candidate_id: str) -> dict[str, Any]:
    base_selected = multilane.dedupe_portfolio_trades(base_rows)["selected_trades"]
    combined = multilane.dedupe_portfolio_trades(base_rows + candidate)
    selected = combined["selected_trades"]
    incremental = [row for row in selected if row.get("lane_id") == candidate_id and row.get("exact_priced")]
    metrics = multilane.metrics_for_trades(incremental)
    return {
        "base_clean_trade_count": multilane.metrics_for_trades(base_selected)["exact_trade_count"],
        "with_candidate_trade_count": multilane.metrics_for_trades(selected)["exact_trade_count"],
        "strict_new_trade_count": len(incremental),
        "gap_after_candidate": max(TARGET_CLEAN_TRADES - multilane.metrics_for_trades(selected)["exact_trade_count"], 0),
        "incremental_metrics": metrics,
        "suppressed_duplicate_trade_count": len(combined["suppressed_duplicates"]),
        "duplicate_group_count": combined["duplicate_group_count"],
    }


def worth_status(
    metrics: dict[str, Any],
    robustness: dict[str, Any],
    novelty: dict[str, Any],
    side_aware_zero_bid: dict[str, Any] | None = None,
) -> str:
    exact = int(metrics.get("exact_trade_count") or 0)
    pf = float(metrics.get("profit_factor") or 0.0)
    avg = float(metrics.get("avg_pnl_pct") or 0.0)
    coverage = float(metrics.get("quote_coverage_pct") or 0.0)
    unpriced = int(metrics.get("unpriced_trade_count") or 0)
    stress_pf = robustness.get("stress_5pct_per_side_profit_factor")
    rolling = str(robustness.get("rolling_status") or "").lower()
    novel = int(novelty.get("strict_new_trade_count") or 0)
    if exact == 0:
        return "no_current_candidates"
    if pf < 1.0 or avg <= 0:
        return "not_worth_current_shape"
    if exact < 25:
        return "thin_sample"
    if pf < 1.5:
        return "weak_positive_or_marginal"
    if side_aware_zero_bid and side_aware_zero_bid.get("status") == "error":
        return "repair_zero_bid_replay_before_counting"
    conservative = _conservative_zero_bid_mode(side_aware_zero_bid)
    if conservative:
        combined = conservative.get("combined_with_existing_metrics") or {}
        combined_pf = float(combined.get("profit_factor") or 0.0)
        combined_avg = float(combined.get("avg_pnl_pct") or 0.0)
        if int(conservative.get("unpriced_count") or 0) > 0:
            return "repair_zero_bid_replay_before_counting"
        if combined_pf < ZERO_BID_REPLAY_MIN_COMBINED_PF or combined_avg <= 0:
            return "not_worth_after_zero_bid_replay"
        zero_bid_rate = conservative.get("zero_bid_exit_rate_pct")
        if zero_bid_rate is None or float(zero_bid_rate) > ZERO_BID_EXIT_RATE_MAX_PCT:
            return "repair_zero_bid_exit_rate_before_counting"
    if coverage < 97.5 or unpriced > 0:
        return "repair_coverage_before_counting"
    if exact < PORTFOLIO_CANDIDATE_MIN_EXACT_TRADES:
        return "below_portfolio_candidate_exact_count"
    if stress_pf is not None and float(stress_pf) < 1.25:
        return "repair_stress_before_counting"
    if rolling and rolling != "passed":
        return "repair_oos_before_counting"
    if novel < 10:
        return "profitable_but_overlaps"
    if novel >= 43:
        return "candidate_to_close_200_gap"
    return "clean_but_too_small"


def _lane_lab_required_symbols() -> list[str]:
    symbols: set[str] = set()
    for lane in lane_lab.lane_definitions():
        if str(lane.get("id") or "") == "ai_commodity_infra_observation":
            continue
        symbols.update(str(symbol).strip().upper() for symbol in lane.get("required_symbols") or [] if str(symbol).strip())
    return sorted(symbols)


def _trusted_intraday_readiness_payload(
    symbols: Iterable[str],
    *,
    db_path: Path = OPTIONS_HISTORY_DB,
    source_label: str = TRUSTED_INTRADAY_SOURCE_LABEL,
    min_quote_dates: int = MIN_TRUSTED_INTRADAY_DATES_FOR_READINESS,
) -> dict[str, Any]:
    requested = sorted({str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()})
    if not requested:
        return {"status": "ready_for_exact_replay", "available_underlyings": [], "shared_required_quote_dates": {"count": 0}}
    health: dict[str, dict[str, Any]] = {}
    available: list[str] = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for symbol in requested:
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT q.quote_date_et) AS quote_date_count,
                       MIN(q.quote_date_et) AS first_quote_date,
                       MAX(q.quote_date_et) AS last_quote_date,
                       COUNT(*) AS row_count
                FROM option_quote_snapshots q INDEXED BY idx_option_quotes_underlying_date
                JOIN import_batches b ON b.id = q.source_batch_id
                WHERE q.underlying = ?
                  AND q.snapshot_kind = 'intraday'
                  AND b.data_trust = 'trusted'
                  AND b.source_label = ?
                """,
                (symbol, source_label),
            ).fetchone()
            quote_date_count = int((row["quote_date_count"] if row else 0) or 0)
            health[symbol] = {
                "quote_date_count": quote_date_count,
                "first_quote_date": row["first_quote_date"] if row else None,
                "last_quote_date": row["last_quote_date"] if row else None,
                "row_count": int((row["row_count"] if row else 0) or 0),
                "ready": quote_date_count >= int(min_quote_dates),
            }
            if quote_date_count >= int(min_quote_dates):
                available.append(symbol)
    shared_count = min((item["quote_date_count"] for item in health.values()), default=0)
    return {
        "status": "ready_for_exact_replay",
        "source": str(db_path),
        "source_label": source_label,
        "snapshot_kind": "intraday",
        "available_underlyings": available,
        "required_underlying_health": health,
        "shared_required_quote_dates": {"count": shared_count},
    }


def blocked_lane_lab_rows(implemented_lane_ids: set[str]) -> list[dict[str, Any]]:
    payload = lane_lab.build_lane_lab_report(
        readiness_payload=_trusted_intraday_readiness_payload(_lane_lab_required_symbols())
    )
    implemented_variants_by_lane_id: dict[str, list[str]] = defaultdict(list)
    for spec in IMPLEMENTED_PLANNED_VARIANTS:
        lane_id = str(spec["lane_id"])
        if lane_id in implemented_lane_ids:
            implemented_variants_by_lane_id[lane_id].append(str(spec["variant_id"]))
    rows = []
    for row in payload.get("lanes") or []:
        lane_id = str(row.get("id") or "")
        if lane_id == "ai_commodity_infra_observation":
            continue
        implemented_variant_ids = sorted(implemented_variants_by_lane_id.get(lane_id, []))
        blocked_row = {
            "lane_id": lane_id,
            "status": row.get("status"),
            "blockers": row.get("blockers") or [],
            "next_test": row.get("next_test"),
            "pass_fail": row.get("pass_fail"),
            "result": row.get("result"),
        }
        if implemented_variant_ids:
            blocked_row["implemented_variant_ids"] = implemented_variant_ids
            blocked_row["implementation_note"] = (
                "same_lane_id_replay_tested_but_lane_lab_spec_still_requires_"
                f"{row.get('status') or 'lane_lab_evidence'}"
            )
        rows.append(blocked_row)
    return rows


def run_all_planned_sleeves(
    *,
    lookback_years: int,
    output_dir: Path = OUTPUT_DIR,
    only: set[str] | None = None,
    skip_run: bool = False,
) -> dict[str, Any]:
    stamp = _utc_stamp()
    root = output_dir / stamp
    base_rows = base_clean_rows()
    base_count = multilane.metrics_for_trades(multilane.dedupe_portfolio_trades(base_rows)["selected_trades"])["exact_trade_count"]
    rows: list[dict[str, Any]] = []
    variants = [spec for spec in IMPLEMENTED_PLANNED_VARIANTS if not only or str(spec["variant_id"]) in only or str(spec["lane_id"]) in only]
    partial_selection = bool(only)
    for index, spec in enumerate(variants, start=1):
        variant_dir = root / f"v{index:02d}"
        try:
            if skip_run:
                raise RuntimeError("skip_run requires explicit run_path support; rerun without --skip-run for end-to-end execution.")
            run_path = _run_variant(spec, lookback_years=lookback_years)
            run = _load_json(run_path)
            robustness, robustness_path = _run_robustness(run_path, variant_dir / "robustness")
            run_metrics = _run_metrics(run)
            robustness_metrics = _robustness_summary(robustness)
            novelty = incremental_report(base_rows, candidate_rows(run_path, spec), str(spec["variant_id"]))
            side_aware_zero_bid = _run_side_aware_zero_bid_if_needed(
                run_path=run_path,
                run=run,
                spec=spec,
                metrics=run_metrics,
                novelty=novelty,
                output_dir=variant_dir / "side-aware-zero-bid",
            )
            row = {
                "lane_id": spec["lane_id"],
                "variant_id": spec["variant_id"],
                "runner": spec["runner"],
                "description": spec.get("description"),
                "run_path": str(run_path),
                "robustness_path": str(robustness_path),
                "standalone_metrics": run_metrics,
                "robustness": robustness_metrics,
                "novelty_vs_core_plus_clean_reference": novelty,
                "side_aware_zero_bid_replay": side_aware_zero_bid,
                "worth_status": worth_status(run_metrics, robustness_metrics, novelty, side_aware_zero_bid),
                "error": None,
            }
            _write_json(variant_dir / "row.json", row)
            rows.append(row)
        except Exception as exc:
            row = {
                "lane_id": spec["lane_id"],
                "variant_id": spec["variant_id"],
                "runner": spec["runner"],
                "description": spec.get("description"),
                "run_path": None,
                "robustness_path": None,
                "standalone_metrics": {},
                "robustness": {},
                "novelty_vs_core_plus_clean_reference": {},
                "worth_status": "run_failed",
                "error": str(exc),
            }
            _write_json(variant_dir / "row.json", row)
            rows.append(row)

    implemented_lane_ids = {str(spec["lane_id"]) for spec in IMPLEMENTED_PLANNED_VARIANTS}
    blocked_rows = blocked_lane_lab_rows(implemented_lane_ids)
    ranked = sorted(
        rows,
        key=lambda row: (
            int((row.get("novelty_vs_core_plus_clean_reference") or {}).get("strict_new_trade_count") or 0),
            float((row.get("standalone_metrics") or {}).get("profit_factor") or 0.0),
            float((row.get("robustness") or {}).get("stress_5pct_per_side_profit_factor") or 0.0),
        ),
        reverse=True,
    )
    failed_rows = [row for row in rows if row.get("error")]
    successful_rows = [row for row in rows if not row.get("error")]
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "experiment_batch": stamp,
        "goal": "Run every currently planned regular stock-options sleeve end-to-end where implementation exists.",
        "lookback_years": int(lookback_years),
        "base_clean_stack": {
            "lanes": sorted(BASE_CLEAN_LANE_IDS),
            "strict_deduped_trade_count": base_count,
            "gap_to_200": max(TARGET_CLEAN_TRADES - int(base_count), 0),
        },
        "implemented_variant_count": len(IMPLEMENTED_PLANNED_VARIANTS),
        "selected_variant_count": len(variants),
        "selection": sorted(only) if only else [],
        "tested_end_to_end_variant_count": len(successful_rows),
        "run_failed_count": len(failed_rows),
        "run_failed_variants": [
            {
                "lane_id": row.get("lane_id"),
                "variant_id": row.get("variant_id"),
                "runner": row.get("runner"),
                "error": row.get("error"),
            }
            for row in failed_rows
        ],
        "blocked_or_not_implemented_lane_count": len(blocked_rows),
        "variants": rows,
        "ranked_by_strict_new_count": ranked,
        "blocked_or_not_implemented_lanes": blocked_rows,
    }
    _write_json(root / "summary.json", report)
    output_dir.mkdir(parents=True, exist_ok=True)
    if partial_selection:
        _write_json(output_dir / "latest_partial.json", report)
    else:
        _write_json(output_dir / "latest.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run all planned regular stock-options sleeves end to end where implemented.")
    parser.add_argument("--lookback-years", type=int, default=1)
    parser.add_argument("--only", nargs="*", default=None, help="Variant ids or lane ids to run.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run_all_planned_sleeves(
        lookback_years=int(args.lookback_years),
        output_dir=args.output_dir,
        only=set(args.only) if args.only else None,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            json.dumps(
                {
                    "base_clean_stack": report.get("base_clean_stack"),
                    "implemented_variant_count": report.get("implemented_variant_count"),
                    "blocked_or_not_implemented_lane_count": report.get("blocked_or_not_implemented_lane_count"),
                    "top": (report.get("ranked_by_strict_new_count") or [])[:5],
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
