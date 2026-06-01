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


OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "bullish-pullback-observation" / "next-round"
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


BASE_OVERRIDES: dict[str, Any] = {
    "chain_native_spread_selection": True,
    "chain_native_min_dte": 28,
    "chain_native_max_dte": 45,
    "max_debit_pct_of_width": 55.0,
    "pullback_ret20_min": 4.0,
    "spread_stop_loss_pct": 120.0,
    "spread_time_exit_pct": 60.0,
}


VARIANTS: list[dict[str, Any]] = [
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50",
        "description": "Current best with a cheaper debit cap suggested by losing-window audit.",
        "overrides": {"max_debit_pct_of_width": 50.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_direction90",
        "description": "Current best requiring very high pullback direction score.",
        "overrides": {"scan_min_confidence": 90.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction70",
        "description": "Cheaper debit plus a moderate direction floor.",
        "overrides": {"max_debit_pct_of_width": 50.0, "scan_min_confidence": 70.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit45_direction70",
        "description": "Subagent-recommended stricter debit/width cap.",
        "overrides": {"max_debit_pct_of_width": 45.0, "scan_min_confidence": 70.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit45_direction70_npicks6",
        "description": "Stricter debit cap with one extra daily slot to recover trade count.",
        "overrides": {"max_debit_pct_of_width": 45.0, "scan_min_confidence": 70.0},
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit45_direction70_ret5min3",
        "description": "Stricter debit cap with deepest pullbacks removed.",
        "overrides": {"max_debit_pct_of_width": 45.0, "scan_min_confidence": 70.0, "pullback_ret5_min": -3.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction70_ret5min3",
        "description": "Single-axis debit relaxation from the current champion while keeping the ret5 floor.",
        "overrides": {"max_debit_pct_of_width": 50.0, "scan_min_confidence": 70.0, "pullback_ret5_min": -3.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit45_direction65_ret5min3",
        "description": "Single-axis direction relaxation from the current champion while keeping debit45 and ret5 floor.",
        "overrides": {"max_debit_pct_of_width": 45.0, "scan_min_confidence": 65.0, "pullback_ret5_min": -3.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction65_ret5min3",
        "description": "Combined mild relaxation to recover trade count after the single-axis tests.",
        "overrides": {"max_debit_pct_of_width": 50.0, "scan_min_confidence": 65.0, "pullback_ret5_min": -3.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction65_ret5min3_target120",
        "description": "Best count/OOS near-miss with earlier spread profit target.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -3.0,
            "spread_profit_target_pct": 120.0,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction65_ret5min3_dte29_45",
        "description": "Best count/OOS near-miss with a slightly higher minimum DTE.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -3.0,
            "chain_native_min_dte": 29,
            "chain_native_max_dte": 45,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction65_ret5min3_dte29_45_cont2",
        "description": "DTE29-45 near-miss with both legs requiring two prior valid quote dates in the last 14 calendar days.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -3.0,
            "chain_native_min_dte": 29,
            "chain_native_max_dte": 45,
            "chain_native_min_prior_quote_days": 2,
            "chain_native_prior_quote_lookback_days": 14,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction65_ret5min3_dte29_45_cont3",
        "description": "DTE29-45 near-miss with both legs requiring three prior valid quote dates in the last 14 calendar days.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -3.0,
            "chain_native_min_dte": 29,
            "chain_native_max_dte": 45,
            "chain_native_min_prior_quote_days": 3,
            "chain_native_prior_quote_lookback_days": 14,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_3_stop120_time60_debit50_direction70_ret5min3_spymin1_cont2",
        "description": "Higher-count SPY-filtered variant with a two-prior-quote continuity gate on both legs.",
        "overrides": {
            "pullback_ret20_min": 3.0,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "pullback_ret5_min": -3.0,
            "min_spy_ret5": -1.0,
            "chain_native_min_prior_quote_days": 2,
            "chain_native_prior_quote_lookback_days": 14,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction70_ret5min3_dte29_45",
        "description": "Debit50 champion variant with ret5 floor and slightly higher minimum DTE to avoid near-term weak slices.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "pullback_ret5_min": -3.0,
            "chain_native_min_dte": 29,
            "chain_native_max_dte": 45,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit45_direction70_ret5min3_target120",
        "description": "Current champion with a slightly earlier spread profit target to test winner capture without changing entries.",
        "overrides": {
            "max_debit_pct_of_width": 45.0,
            "scan_min_confidence": 70.0,
            "pullback_ret5_min": -3.0,
            "spread_profit_target_pct": 120.0,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_3_stop120_time60_debit50_direction70_ret5min3",
        "description": "Higher-count ret20=3 variant with debit/direction/ret5 safety gates.",
        "overrides": {
            "pullback_ret20_min": 3.0,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "pullback_ret5_min": -3.0,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_3_stop120_time60_debit50_direction70_ret5min3_spymin1",
        "description": "Higher-count ret20=3 safety-gated variant excluding hard bearish prior SPY 5-day regimes.",
        "overrides": {
            "pullback_ret20_min": 3.0,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "pullback_ret5_min": -3.0,
            "min_spy_ret5": -1.0,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_25_stop120_time60_debit50_direction70_ret5min3_spymin05",
        "description": "Looser trend gate plus prior-SPY neutral-or-better regime filter to recover count without bearish Q1 exposure.",
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "pullback_ret5_min": -3.0,
            "min_spy_ret5": -0.5,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_25_stop120_time60_debit50_direction70_ret5min2_spymin05",
        "description": "Looser trend/count variant with neutral-or-better SPY filter and shallower pullback depth.",
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_25_stop120_time60_debit50_direction65_ret5min2_spymin05",
        "description": "Best Jan-Feb shallower-pullback branch with a single-axis direction relaxation to recover count.",
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_25_stop120_time60_debit50_direction65_ret5min2_spymin05_cont2",
        "description": "Best Jan-Feb branch with a two-prior-quote continuity gate on both legs.",
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
            "chain_native_min_prior_quote_days": 2,
            "chain_native_prior_quote_lookback_days": 14,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_25_stop120_time60_debit50_direction65_ret5min2_spymin05_shortbid05",
        "description": "Best Jan-Feb branch requiring the short leg to have at least a nickel bid at entry.",
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
            "chain_native_min_entry_short_bid": 0.05,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_shortbid05_excl_provider4",
        "description": "Short-bid branch excluding symbols with repeated provider no-match exit coverage gaps.",
        "exclude_tickers": ["SLB", "PLD", "RTX", "WELL"],
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
            "chain_native_min_entry_short_bid": 0.05,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_shortbid05_excl_provider4_backfill15",
        "description": "Provider-gap exclusion plus entry-time chain-native preflight with ranked backfill to preserve executable volume.",
        "exclude_tickers": ["SLB", "PLD", "RTX", "WELL"],
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
            "chain_native_min_entry_short_bid": 0.05,
            "execution_backfill_enabled": True,
            "execution_backfill_scan_depth": 15,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_shortbid05_excl_oos_unpriced_plus3_backfill15",
        "description": "Short-bid branch excluding repeated OOS exact-strike no-match symbols, with entry-time preflight and ranked backfill.",
        "exclude_tickers": ["DIS", "TSLA", "C", "V", "SBUX", "BAC", "AMD", "IWM"],
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
            "chain_native_min_entry_short_bid": 0.05,
            "execution_backfill_enabled": True,
            "execution_backfill_scan_depth": 15,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_25_stop120_time45_debit50_direction65_ret5min2_spymin05_shortbid05",
        "description": "Best short-bid branch with earlier time exit to reduce weak time-exit damage.",
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
            "chain_native_min_entry_short_bid": 0.05,
            "spread_time_exit_pct": 45.0,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_25_stop120_time75_debit50_direction65_ret5min2_spymin05_shortbid05",
        "description": "Best short-bid branch with later time exit to test whether weak time exits recover with more time.",
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
            "chain_native_min_entry_short_bid": 0.05,
            "spread_time_exit_pct": 75.0,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_25_stop120_time60_target120_debit50_direction65_ret5min2_spymin05_shortbid05",
        "description": "Best short-bid branch with earlier profit target to capture winners before time decay.",
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
            "chain_native_min_entry_short_bid": 0.05,
            "spread_profit_target_pct": 120.0,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_25_stop100_time60_debit50_direction65_ret5min2_spymin05_shortbid05",
        "description": "Best short-bid branch with tighter stop to reduce large time-exit and trailing losses.",
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
            "chain_native_min_entry_short_bid": 0.05,
            "spread_stop_loss_pct": 100.0,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_25_stop120_time60_debit50_direction65_ret5min2_spymin05_shortbid10",
        "description": "Best Jan-Feb branch requiring the short leg to have at least a dime bid at entry.",
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
            "chain_native_min_entry_short_bid": 0.10,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_25_stop120_time60_debit50_direction65_ret5min2_spymin05_cont2_shortbid05",
        "description": "Best Jan-Feb branch combining two-prior-quote continuity with a nickel short-leg entry bid.",
        "overrides": {
            "pullback_ret20_min": 2.5,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 65.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
            "chain_native_min_prior_quote_days": 2,
            "chain_native_prior_quote_lookback_days": 14,
            "chain_native_min_entry_short_bid": 0.05,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_3_stop120_time60_debit50_direction70_ret5min2_spymin05",
        "description": "Ret20=3 variant with neutral-or-better SPY filter and shallower pullback depth.",
        "overrides": {
            "pullback_ret20_min": 3.0,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -0.5,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_3_stop120_time60_debit50_direction70_ret5min2_spymin1",
        "description": "Current 100+ trade SPY-filtered branch with shallower pullback depth to target the weak Jan-Feb slice.",
        "overrides": {
            "pullback_ret20_min": 3.0,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "pullback_ret5_min": -2.0,
            "min_spy_ret5": -1.0,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_3_stop120_time60_debit50_direction70_tech75",
        "description": "Higher-count ret20=3 variant with tech75 to attack the Q1 weak slice.",
        "overrides": {
            "pullback_ret20_min": 3.0,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "scan_min_tech_score": 75.0,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_3_stop120_time60_debit50_direction70_tech80",
        "description": "Higher-count ret20=3 variant with tech80 to test whether quality can fix Q1 while retaining count.",
        "overrides": {
            "pullback_ret20_min": 3.0,
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "scan_min_tech_score": 80.0,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction70_tech80",
        "description": "Best candidate with tech score >= 80 to attack weak Q1/tech 70-79 losses.",
        "overrides": {"max_debit_pct_of_width": 50.0, "scan_min_confidence": 70.0, "scan_min_tech_score": 80.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction70_tech75",
        "description": "Middle-ground tech score floor to retain more trades than tech80 while attacking Q1 losses.",
        "overrides": {"max_debit_pct_of_width": 50.0, "scan_min_confidence": 70.0, "scan_min_tech_score": 75.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction70_dte21_35",
        "description": "Best candidate with shorter listed-spread DTE window.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "chain_native_min_dte": 21,
            "chain_native_max_dte": 35,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction70_dte21_35_npicks6",
        "description": "Shorter DTE with one extra daily slot to recover count.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "chain_native_min_dte": 21,
            "chain_native_max_dte": 35,
        },
        "n_picks": 6,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction70_tech75_dte21_35",
        "description": "Middle-ground tech floor plus shorter DTE to target Q1 losses while preserving 100+ trades.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "scan_min_tech_score": 75.0,
            "chain_native_min_dte": 21,
            "chain_native_max_dte": 35,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time45_debit50_direction70",
        "description": "Best candidate with earlier time exit to test Q1 loss containment.",
        "overrides": {"max_debit_pct_of_width": 50.0, "scan_min_confidence": 70.0, "spread_time_exit_pct": 45.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time70_debit50_direction70",
        "description": "Neighboring longer time exit without switching to expiry-heavy long hold.",
        "overrides": {"max_debit_pct_of_width": 50.0, "scan_min_confidence": 70.0, "spread_time_exit_pct": 70.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop200_time75_debit50_direction70",
        "description": "Best candidate with longer no-stop-like hold that previously improved raw PF.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_goal_stop200_time75_shortbid10",
        "description": "Goal experiment: current stop200/time75 Lane A shape with a causal dime minimum short-leg entry bid.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
            "chain_native_min_entry_short_bid": 0.10,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_goal_stop200_time75_shortprior3_shortbid10_backfill",
        "description": "Goal experiment: short-leg survivability filter with ranked entry backfill to preserve count.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
            "chain_native_min_entry_short_bid": 0.10,
            "chain_native_min_short_prior_quote_days": 3,
            "chain_native_prior_quote_lookback_days": 30,
            "execution_backfill_enabled": True,
            "execution_backfill_scan_depth": 15,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_goal_stop200_time75_liquidity_score_replacement",
        "description": "Goal experiment: prefer liquid replacement spreads by scoring prior short-leg quote continuity before entry.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
            "chain_native_min_entry_short_bid": 0.10,
            "chain_native_prior_quote_lookback_days": 30,
            "chain_native_short_prior_quote_score_weight": 1.0,
            "chain_native_prior_quote_score_cap": 10,
            "execution_backfill_enabled": True,
            "execution_backfill_scan_depth": 15,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_goal_stop200_time75_tradability80",
        "description": "Goal experiment: current stop200/time75 shape with strict pre-entry spread tradability scoring.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
            "execution_survivability_enabled": True,
            "tradability_lookback_days": 30,
            "min_tradability_score": 80.0,
            "min_short_leg_prior_quote_days": 3,
            "min_long_leg_prior_quote_days": 1,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_goal_stop200_time75_shortbucket_memory45_backfill",
        "description": "Goal experiment: current stop200/time75 shape with causal short-leg expiry/strike cooldown after observed exit quote misses.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
            "exit_quote_failure_memory_enabled": True,
            "exit_quote_failure_cooldown_days": 45,
            "exit_quote_failure_max_prior": 1,
            "exit_quote_failure_scope": "short_expiry_strike_bucket",
            "exit_quote_failure_strike_bucket_width": 5.0,
            "execution_backfill_enabled": True,
            "execution_backfill_scan_depth": 25,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_goal_stop200_time75_symbol_health90_backfill",
        "description": "Goal experiment: current stop200/time75 shape with causal ticker health memory after priced losses or unpriced exit failures.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
            "symbol_health_memory_enabled": True,
            "symbol_health_min_observations": 3,
            "symbol_health_min_profit_factor": 1.0,
            "symbol_health_min_avg_pnl_pct": 0.0,
            "symbol_health_cooldown_days": 90,
            "symbol_health_include_unpriced_failures": True,
            "symbol_health_unpriced_penalty_pct": -100.0,
            "execution_backfill_enabled": True,
            "execution_backfill_scan_depth": 25,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_goal_stop200_time75_memory_combo_backfill",
        "description": "Goal experiment: current stop200/time75 shape with combined short-bucket exit-failure memory and ticker health memory.",
        "overrides": {
            "max_debit_pct_of_width": 50.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
            "exit_quote_failure_memory_enabled": True,
            "exit_quote_failure_cooldown_days": 45,
            "exit_quote_failure_max_prior": 1,
            "exit_quote_failure_scope": "short_expiry_strike_bucket",
            "exit_quote_failure_strike_bucket_width": 5.0,
            "symbol_health_memory_enabled": True,
            "symbol_health_min_observations": 3,
            "symbol_health_min_profit_factor": 1.0,
            "symbol_health_min_avg_pnl_pct": 0.0,
            "symbol_health_cooldown_days": 90,
            "symbol_health_include_unpriced_failures": True,
            "symbol_health_unpriced_penalty_pct": -100.0,
            "execution_backfill_enabled": True,
            "execution_backfill_scan_depth": 25,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_goal_debit33_shortprior3_backfill",
        "description": "Goal experiment: lower debit/width exposure after side-aware zero-bid replay showed high-debit spreads were structurally weak.",
        "overrides": {
            "max_debit_pct_of_width": 33.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
            "chain_native_min_entry_short_bid": 0.10,
            "chain_native_min_short_prior_quote_days": 3,
            "chain_native_prior_quote_lookback_days": 30,
            "execution_backfill_enabled": True,
            "execution_backfill_scan_depth": 20,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_goal_debit33_maxdte35_shortprior3_backfill",
        "description": "Goal experiment: lower debit/width plus shorter max DTE to reduce expiry-adjacent zero-bid exits.",
        "overrides": {
            "max_debit_pct_of_width": 33.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
            "chain_native_max_dte": 35,
            "chain_native_min_entry_short_bid": 0.10,
            "chain_native_min_short_prior_quote_days": 3,
            "chain_native_prior_quote_lookback_days": 30,
            "execution_backfill_enabled": True,
            "execution_backfill_scan_depth": 20,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_goal_bad_zero_ticker_exclusion_probe",
        "description": "Goal experiment: research-only probe excluding tickers with repeated conservative zero-bid failure rows.",
        "exclude_tickers": ["AA", "AMD", "AMZN", "ARM", "FCX", "GOOGL", "PLTR", "SMCI", "WELL"],
        "overrides": {
            "max_debit_pct_of_width": 33.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
            "chain_native_max_dte": 35,
            "chain_native_min_entry_short_bid": 0.10,
            "chain_native_min_short_prior_quote_days": 3,
            "chain_native_prior_quote_lookback_days": 30,
            "execution_backfill_enabled": True,
            "execution_backfill_scan_depth": 25,
        },
        "n_picks": 5,
    },
    {
        "id": "lane_a_goal_bad_zero_ticker_exclusion_npicks8",
        "description": "Goal experiment: replenish the economically cleaner bad-ticker exclusion lane with more daily slots.",
        "exclude_tickers": ["AA", "AMD", "AMZN", "ARM", "FCX", "GOOGL", "PLTR", "SMCI", "WELL"],
        "overrides": {
            "max_debit_pct_of_width": 33.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
            "chain_native_max_dte": 35,
            "chain_native_min_entry_short_bid": 0.10,
            "chain_native_min_short_prior_quote_days": 3,
            "chain_native_prior_quote_lookback_days": 30,
            "execution_backfill_enabled": True,
            "execution_backfill_scan_depth": 40,
        },
        "n_picks": 8,
    },
    {
        "id": "lane_a_goal_bad_zero_ticker_exclusion_debit40_npicks8",
        "description": "Goal experiment: slightly looser debit cap with bad-ticker exclusion and higher daily capacity.",
        "exclude_tickers": ["AA", "AMD", "AMZN", "ARM", "FCX", "GOOGL", "PLTR", "SMCI", "WELL"],
        "overrides": {
            "max_debit_pct_of_width": 40.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
            "chain_native_max_dte": 35,
            "chain_native_min_entry_short_bid": 0.10,
            "chain_native_min_short_prior_quote_days": 3,
            "chain_native_prior_quote_lookback_days": 30,
            "execution_backfill_enabled": True,
            "execution_backfill_scan_depth": 40,
        },
        "n_picks": 8,
    },
    {
        "id": "lane_a_goal_bad_zero_ticker_exclusion_debit45_npicks8",
        "description": "Goal experiment: test whether count can recover with a 45% debit cap while preserving conservative zero-bid PF.",
        "exclude_tickers": ["AA", "AMD", "AMZN", "ARM", "FCX", "GOOGL", "PLTR", "SMCI", "WELL"],
        "overrides": {
            "max_debit_pct_of_width": 45.0,
            "scan_min_confidence": 70.0,
            "spread_stop_loss_pct": 200.0,
            "spread_time_exit_pct": 75.0,
            "chain_native_max_dte": 35,
            "chain_native_min_entry_short_bid": 0.10,
            "chain_native_min_short_prior_quote_days": 3,
            "chain_native_prior_quote_lookback_days": 30,
            "execution_backfill_enabled": True,
            "execution_backfill_scan_depth": 40,
        },
        "n_picks": 8,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_debit50_direction85",
        "description": "Intermediate direction floor to test whether direction90 is too thin.",
        "overrides": {"max_debit_pct_of_width": 50.0, "scan_min_confidence": 85.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_ret5_tight",
        "description": "Current best with tighter pullback depth band.",
        "overrides": {"pullback_ret5_min": -2.5, "pullback_ret5_max": -0.5},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_3_stop120_time60",
        "description": "Slightly looser 20-day trend gate to test trade-count growth.",
        "overrides": {"pullback_ret20_min": 3.0},
        "n_picks": 5,
    },
    {
        "id": "lane_a_chain_native_ret20_4_stop120_time60_npicks3",
        "description": "Current best with fewer daily picks to test rank concentration.",
        "overrides": {},
        "n_picks": 3,
    },
]


def _trade_exit_reasons(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        str(item.get("exit_reason") or "unknown"): {
            "trades": item.get("trades"),
            "avg": item.get("avg_pnl_pct"),
            "pf": item.get("profit_factor"),
        }
        for item in list(metrics.get("exit_reasons") or [])
        if isinstance(item, dict)
    }


def _summarize(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("error"):
        return {"error": result.get("error")}
    matrix = wfo.build_options_experiment_matrix(
        result=result,
        min_trades=25,
        min_profit_factor=1.05,
        min_directional_accuracy_pct=50.0,
    )
    metrics = dict(matrix.get("authoritative_profitability_metrics") or {})
    gate = dict(matrix.get("authoritative_profitability_gate") or {})
    accounting = dict(result.get("exact_contract_accounting") or {})
    return {
        "result_path": result.get("result_path"),
        "candidate_trade_count": result.get("candidate_trade_count"),
        "priced_trade_count": result.get("priced_trade_count"),
        "unpriced_trade_count": result.get("unpriced_trade_count"),
        "pre_entry_filtered_candidate_count": result.get("pre_entry_filtered_candidate_count"),
        "pre_entry_filtered_candidate_reasons": result.get("pre_entry_filtered_candidate_reasons") or {},
        "execution_backfill_enabled": result.get("execution_backfill_enabled"),
        "execution_backfill_scan_depth": result.get("execution_backfill_scan_depth"),
        "quote_coverage_pct": result.get("quote_coverage_pct"),
        "reason_counts": result.get("unpriced_reason_counts") or {},
        "contract_resolution_counts": accounting.get("contract_resolution_counts") or {},
        "exact_trade_count": metrics.get("trade_count"),
        "exact_profit_factor": metrics.get("profit_factor"),
        "exact_avg_pnl_pct": metrics.get("avg_pnl_pct"),
        "exact_directional_accuracy_pct": metrics.get("directional_accuracy_pct"),
        "max_drawdown_pct": metrics.get("max_drawdown_pct"),
        "gate_passed": gate.get("passed"),
        "gate_blockers": gate.get("blockers") or [],
        "exit_reasons": _trade_exit_reasons(metrics),
    }


def _build_playbook(variant: dict[str, Any]) -> dict[str, Any]:
    playbook = copy.deepcopy(wfo.REPLAY_PLAYBOOKS["bullish_pullback_observation"])
    playbook.update(BASE_OVERRIDES)
    playbook.update(variant.get("overrides") or {})
    excluded = {
        str(symbol or "").strip().upper()
        for symbol in variant.get("exclude_tickers") or []
        if str(symbol or "").strip()
    }
    if excluded:
        allowed = [symbol for symbol in _active_universe_symbols() if symbol not in excluded]
        playbook["allowed_tickers"] = allowed
        playbook["historical_required_underlyings"] = allowed
        playbook["excluded_tickers"] = sorted(excluded)
    playbook["id"] = str(variant["id"])
    playbook["label"] = str(variant.get("description") or variant["id"])
    return playbook


def run_variants(*, lookback_years: int, only: set[str] | None = None) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict[str, Any]] = []
    original_playbooks = copy.deepcopy(wfo.REPLAY_PLAYBOOKS)
    try:
        for variant in VARIANTS:
            if only and str(variant["id"]) not in only:
                continue
            playbook = _build_playbook(variant)
            wfo.REPLAY_PLAYBOOKS[playbook["id"]] = playbook
            result = wfo.run_historical_backtest(
                lookback_years=int(lookback_years),
                n_picks=int(variant.get("n_picks", 5)),
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
                    "n_picks": int(variant.get("n_picks", 5)),
                    "excluded_tickers": playbook.get("excluded_tickers") or [],
                    "validation_universe_count": len(playbook.get("historical_required_underlyings") or []),
                    "overrides": {k: playbook.get(k) for k in sorted(BASE_OVERRIDES | (variant.get("overrides") or {}))},
                    **_summarize(result),
                }
            )
    finally:
        wfo.REPLAY_PLAYBOOKS.clear()
        wfo.REPLAY_PLAYBOOKS.update(original_playbooks)

    ranked = sorted(
        rows,
        key=lambda row: (
            bool(row.get("gate_passed")),
            float(row.get("exact_profit_factor") or 0.0),
            float(row.get("exact_avg_pnl_pct") or 0.0),
            int(row.get("exact_trade_count") or 0),
        ),
        reverse=True,
    )
    return {
        "generated_at": started_at,
        "source_policy": {
            "truth_lane": wfo.IMPORTED_TRUTH_SOURCE,
            "historical_source_labels": "thetadata_opra_nbbo_1m",
            "pricing_lane": "pessimistic",
            "allow_research_imported_data": False,
            "authoritative_profitability_basis": "exact_contract_only",
            "universe_path": str(UNIVERSE_PATH),
            "cmcsa_active": "CMCSA" in _active_universe_symbols(),
        },
        "variants": rows,
        "best": ranked[0] if ranked else None,
    }


def write_report(report: dict[str, Any], *, output_dir: Path = OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"next_round_{stamp}.json"
    latest = output_dir / "latest.json"
    serialized = json.dumps(report, indent=2)
    path.write_text(serialized, encoding="utf8")
    latest.write_text(serialized, encoding="utf8")
    return {"json": str(path), "latest_json": str(latest)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the next bounded bullish-pullback exact-contract variant round.")
    parser.add_argument("--lookback-years", type=int, default=1)
    parser.add_argument("--only", help="Comma-separated variant ids to run.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    only = {item.strip() for item in str(args.only or "").split(",") if item.strip()} or None
    report = run_variants(lookback_years=args.lookback_years, only=only)
    artifacts = write_report(report)
    payload = {"artifacts": artifacts, "report": report}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps({"artifacts": artifacts, "best": report.get("best")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
