from __future__ import annotations

import copy
import inspect
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from ai_commodity_universe import (
    ai_commodity_conditional_options_tickers,
    ai_commodity_core_options_tickers,
    ai_commodity_data_ready_tickers,
    ai_commodity_scan_tickers,
)
from lane_universe_manifest import lane_universe_symbols
from wfo_optimizer import (
    IMPORTED_DAILY_TRUTH_SOURCE,
    _classify_trade_against_live_policy,
    build_live_options_trade_policy,
    build_playbook_exit_audit,
    load_preferred_results_by_truth_lane,
)


_ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parent
LIVE_SCAN_TRUTH_LANE = IMPORTED_DAILY_TRUTH_SOURCE
SCAN_FUNNEL_DROP_KEYS = (
    "min_history",
    "history_or_liquidity",
    "signal_index",
    "momentum",
    "tech_score",
    "direction_score",
    "direction_filter",
    "stop_cooldown",
    "ticker_regime_filter",
    "ticker_vol_filter",
    "earnings",
    "option_liquidity",
    "iv_crush_penalty",
    "ev_floor",
    "guardrails",
    "exceptions",
)

SPECULATIVE_ALLOWED_TICKERS = ("SPY", "QQQ")
EXECUTABLE_OPRA_PAPER_CANDIDATE_LABEL = "executable_opra_paper_candidate"
SPECULATIVE_COHORT_ID = "speculative_short_dte"
SPECULATIVE_COHORT_ROLE = "candidate"
TRACKED_WINNER_PRIMARY_COHORT_ID = "tracked_winner_primary"
TRACKED_WINNER_PRIMARY_COHORT_ROLE = "candidate"
QUALITY90_DEBIT55_CANARY_COHORT_ID = "quality90_debit55_canary"
QUALITY90_DEBIT55_CANARY_COHORT_ROLE = "candidate"
TRACKED_WINNER_OBSERVATION_COHORT_ID = "tracked_winner_observation"
TRACKED_WINNER_OBSERVATION_COHORT_ROLE = "candidate"
BEARISH_INDEX_PUT_OBSERVATION_COHORT_ID = "bearish_index_put_observation"
BEARISH_INDEX_PUT_OBSERVATION_COHORT_ROLE = "candidate"
RANGE_BREAKOUT_OBSERVATION_COHORT_ID = "range_breakout_observation"
RANGE_BREAKOUT_OBSERVATION_COHORT_ROLE = "candidate"
VOLATILITY_EXPANSION_OBSERVATION_COHORT_ID = "volatility_expansion_observation"
VOLATILITY_EXPANSION_OBSERVATION_COHORT_ROLE = "candidate"
AI_COMMODITY_INFRA_OBSERVATION_COHORT_ID = "ai_commodity_infra_observation"
AI_COMMODITY_INFRA_OBSERVATION_COHORT_ROLE = "candidate"
BULLISH_PULLBACK_OBSERVATION_COHORT_ID = "bullish_pullback_observation"
BULLISH_PULLBACK_OBSERVATION_COHORT_ROLE = "primary"
REGULAR_BEARISH_PUT_PRIMARY_COHORT_ID = "regular_bearish_put_primary"
REGULAR_BEARISH_PUT_PRIMARY_COHORT_ROLE = "candidate"
INDEX_LANE_TICKERS = ("SPY", "QQQ", "IWM", "DIA")
TRACKED_WINNER_TICKERS = ("SPY", "GOOGL", "XLK", "DIA")
_DEFAULT_BULLISH_PULLBACK_HISTORICAL_READY_TICKERS = ("SPY", "QQQ")
_DEFAULT_BULLISH_PULLBACK_SCAN_TICKERS = (
    "SPY", "QQQ", "IWM", "DIA", "XLK",
    "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META",
    "AMD", "NFLX", "JPM", "TSLA",
    "DIS", "T",
    "GS", "BAC", "V", "C",
    "UNH", "LLY", "JNJ", "ABBV", "PFE",
    "XOM", "CVX", "OXY", "COP", "SLB",
    "MCD", "NKE", "SBUX",
    "WMT", "KO", "COST", "PG", "PM",
    "CAT", "BA", "DE", "LMT", "RTX",
    "FCX", "NEM", "CLF", "AA", "LIN",
    "AMT", "PLD", "SPG", "WELL", "EQR",
    "COIN", "MSTR", "PLTR", "ARM", "SMCI",
)
BULLISH_PULLBACK_HISTORICAL_READY_TICKERS = tuple(
    lane_universe_symbols(
        BULLISH_PULLBACK_OBSERVATION_COHORT_ID,
        tiers=["historical_ready"],
        fallback=_DEFAULT_BULLISH_PULLBACK_HISTORICAL_READY_TICKERS,
    )
)
BULLISH_PULLBACK_SCAN_TICKERS = tuple(
    lane_universe_symbols(
        BULLISH_PULLBACK_OBSERVATION_COHORT_ID,
        fallback=_DEFAULT_BULLISH_PULLBACK_SCAN_TICKERS,
    )
)
BULLISH_PULLBACK_EXPANSION_TICKERS = tuple(
    ticker for ticker in BULLISH_PULLBACK_SCAN_TICKERS if ticker not in set(BULLISH_PULLBACK_HISTORICAL_READY_TICKERS)
)
BULLISH_PULLBACK_ALL_TICKERS = BULLISH_PULLBACK_SCAN_TICKERS
BULLISH_PULLBACK_PROFIT_REPAIR_KEEP_TICKERS = (
    "IWM",
    "AAPL",
    "GOOGL",
    "UNH",
    "LLY",
    "JNJ",
    "XOM",
    "CVX",
    "COP",
    "NEM",
)
AI_COMMODITY_INFRA_TICKERS = tuple(ai_commodity_scan_tickers())
AI_COMMODITY_INFRA_CORE_TICKERS = tuple(ai_commodity_core_options_tickers())
AI_COMMODITY_INFRA_CONDITIONAL_TICKERS = tuple(ai_commodity_conditional_options_tickers())
AI_COMMODITY_INFRA_READINESS_PATH = ROOT / "data" / "profitability-lab" / "paid-data-readiness" / "latest.json"
DEFAULT_SCAN_PLAYBOOK_ID = "bullish_pullback_observation"


SCAN_PLAYBOOKS: dict[str, dict[str, Any]] = {
    "short_term": {
        "id": "short_term",
        "label": "Short-Term",
        "description": "Tighter 1-2 week options holds with smaller suggested size.",
        "target_dte": 7,
        "max_new_positions_per_day": 2,
        "max_sector_open_positions": 1,
        "max_regime_open_positions": 2,
        "block_same_ticker": True,
        "calibration_playbook": "broad",
        "max_concurrent_positions": 3,
        "max_correlated_index_positions": 1,
        "daily_loss_limit_pct": 2.0,
        "weekly_loss_limit_pct": 5.0,
        "max_position_cost_risk_pct": 10.0,
        "max_portfolio_cost_risk_pct": 25.0,
        "profitability_repair_excluded_tickers": ["XLK", "IWM", "DIA", "SPY", "SLB", "NVDA"],
        "profitability_repair_max_debit_pct_of_width": 45.0,
        "max_fill_degradation_vs_mid_pct": 20.0,
        "max_worst_leg_bid_ask_spread_pct": 20.0,
    },
    "swing": {
        "id": "swing",
        "label": "Swing",
        "description": "Longer 3-5 week options holds with room for fewer but fuller positions.",
        "target_dte": 21,
        "max_new_positions_per_day": 3,
        "max_sector_open_positions": 2,
        "max_regime_open_positions": 2,
        "block_same_ticker": True,
        "calibration_playbook": "broad",
        "max_concurrent_positions": 3,
        "max_correlated_index_positions": 1,
        "daily_loss_limit_pct": 2.0,
        "weekly_loss_limit_pct": 5.0,
        "max_position_cost_risk_pct": 12.0,
        "max_portfolio_cost_risk_pct": 30.0,
        "profitability_repair_excluded_tickers": ["IWM", "XLK", "SLB", "DIA", "NFLX"],
        "profitability_repair_max_debit_pct_of_width": 45.0,
        "max_fill_degradation_vs_mid_pct": 20.0,
        "max_worst_leg_bid_ask_spread_pct": 20.0,
    },
    "speculative": {
        "id": "speculative",
        "label": "Speculative",
        "description": "Starter-size 5 DTE SPY/QQQ ideas for high-convexity setups.",
        "target_dte": 5,
        "max_new_positions_per_day": 1,
        "max_sector_open_positions": 1,
        "max_regime_open_positions": 1,
        "block_same_ticker": True,
        "allowed_asset_classes": ["index"],
        "allowed_tickers": list(SPECULATIVE_ALLOWED_TICKERS),
        "min_quality_score": 70.0,
        "calibration_playbook": "broad",
        "max_concurrent_positions": 1,
        "max_correlated_index_positions": 1,
        "daily_loss_limit_pct": 1.0,
        "weekly_loss_limit_pct": 2.5,
        "max_position_cost_risk_pct": 5.0,
        "max_portfolio_cost_risk_pct": 10.0,
        "require_speculative_flag": True,
        "forced_size_tier": "starter",
        "forced_cohort_id": SPECULATIVE_COHORT_ID,
        "forced_cohort_role": SPECULATIVE_COHORT_ROLE,
    },
    "bullish_momentum": {
        "id": "bullish_momentum",
        "label": "Bullish Momentum",
        "description": "Bullish equity calls in confirmed bullish tape, kept separate so promotion can depend on replay-backed calibration.",
        "target_dte": 14,
        "max_new_positions_per_day": 2,
        "max_sector_open_positions": 1,
        "max_regime_open_positions": 2,
        "block_same_ticker": True,
        "allowed_asset_classes": ["equity"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "min_quality_score": 70.0,
        "calibration_playbook": "bullish_momentum",
        "max_concurrent_positions": 3,
        "max_correlated_index_positions": 1,
        "daily_loss_limit_pct": 2.0,
        "weekly_loss_limit_pct": 5.0,
        "max_position_cost_risk_pct": 10.0,
        "max_portfolio_cost_risk_pct": 25.0,
        "profitability_repair_excluded_tickers": ["NVDA", "TSLA", "COIN"],
        "profitability_repair_max_debit_pct_of_width": 45.0,
        "max_fill_degradation_vs_mid_pct": 20.0,
        "max_worst_leg_bid_ask_spread_pct": 20.0,
    },
    "bearish_defensive": {
        "id": "bearish_defensive",
        "label": "Bearish Defensive",
        "description": "Selective bearish puts on defensive equities when the broader market regime is already risk-off.",
        "target_dte": 14,
        "max_new_positions_per_day": 1,
        "max_sector_open_positions": 1,
        "max_regime_open_positions": 1,
        "block_same_ticker": True,
        "allowed_asset_classes": ["equity"],
        "allowed_market_regimes": ["bearish"],
        "allowed_sectors": ["Healthcare", "Consumer Defensive"],
        "allowed_directions": ["put"],
        "min_quality_score": 70.0,
        "calibration_playbook": "bearish_defensive",
        "max_concurrent_positions": 3,
        "max_correlated_index_positions": 1,
        "daily_loss_limit_pct": 2.0,
        "weekly_loss_limit_pct": 5.0,
        "max_position_cost_risk_pct": 10.0,
        "max_portfolio_cost_risk_pct": 25.0,
    },
    "tracked_winner_primary": {
        "id": "tracked_winner_primary",
        "label": "Tracked Winner Primary",
        "description": "Secondary shape-guidance lane cloned from the current profitable tracked book: bullish call verticals on the winning symbol set with debit below 40% of spread width.",
        "lane_role": "secondary_shape_guidance",
        "promotion_basis": "closed_forward_alpaca_opra_required",
        "target_dte": 35,
        "max_new_positions_per_day": 2,
        "max_scan_picks_per_ticker": 1,
        "max_sector_open_positions": 2,
        "max_regime_open_positions": 3,
        "block_same_ticker": True,
        "allowed_asset_classes": ["index", "equity"],
        "allowed_tickers": list(TRACKED_WINNER_TICKERS),
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "scan_allowed_directions": ["call"],
        "allowed_strategy_types": ["vertical_spread"],
        "max_debit_pct_of_width": 40.0,
        "calibration_playbook": "broad",
        "max_concurrent_positions": 5,
        "max_correlated_index_positions": 3,
        "daily_loss_limit_pct": 2.0,
        "weekly_loss_limit_pct": 5.0,
        "max_position_cost_risk_pct": 10.0,
        "max_portfolio_cost_risk_pct": 30.0,
        "forced_cohort_id": TRACKED_WINNER_PRIMARY_COHORT_ID,
        "forced_cohort_role": TRACKED_WINNER_PRIMARY_COHORT_ROLE,
        "winner_profile": {
            "source": "tracked_positions_assumed_closed_positive",
            "preferred_tickers": list(TRACKED_WINNER_TICKERS),
            "preferred_direction": "call",
            "preferred_strategy_type": "vertical_spread",
            "preferred_market_regime": "bullish",
            "max_debit_pct_of_width": 40.0,
        },
    },
    "bullish_pullback_observation": {
        "id": "bullish_pullback_observation",
        "label": "Bullish Pullback Primary",
        "description": "Primary broad liquid-universe bullish call vertical lane for controlled pullbacks in established uptrends.",
        "lane_role": "primary_profit_candidate",
        "proof_yardstick_playbook": "quality90_debit55_canary",
        "promotion_basis": "closed_forward_alpaca_opra_required",
        "target_dte": 35,
        "max_new_positions_per_day": 1,
        "max_scan_picks_per_ticker": 1,
        "max_sector_open_positions": 2,
        "max_regime_open_positions": 2,
        "block_same_ticker": True,
        "allowed_asset_classes": ["index", "equity"],
        "allowed_tickers": list(BULLISH_PULLBACK_SCAN_TICKERS),
        "scan_tickers": list(BULLISH_PULLBACK_SCAN_TICKERS),
        "primary_tickers": list(BULLISH_PULLBACK_SCAN_TICKERS),
        "expansion_tickers": list(BULLISH_PULLBACK_EXPANSION_TICKERS),
        "historical_data_ready_tickers": list(BULLISH_PULLBACK_HISTORICAL_READY_TICKERS),
        "historical_data_source": "data/alpaca-options-strategy-lab/alpaca_options_strategy_lab_20260521T042849Z.json",
        "historical_data_readiness_status": "broad_live_opra_scan_enabled_spy_qqq_historical_ready",
        "data_readiness_gates": {
            "min_closed_exact_trades": 50,
            "min_oos_exact_trades": 20,
            "min_profit_factor": 1.15,
            "requires_positive_oos_expectancy": True,
            "requires_multiple_months_and_expiration_cycles": True,
            "promotion_basis": "exact_bid_ask_only",
        },
        "allowed_directions": ["call"],
        "scan_allowed_directions": ["call"],
        "allowed_strategy_types": ["vertical_spread"],
        "signal_variant": "pullback_uptrend",
        "scan_min_confidence": 0.0,
        "scan_min_tech_score": 0.0,
        "min_quality_score": 0.0,
        "max_debit_pct_of_width": 55.0,
        "profitability_repair_allowed_tickers": list(BULLISH_PULLBACK_PROFIT_REPAIR_KEEP_TICKERS),
        "profitability_repair_min_ret5": -2.0,
        "profitability_repair_max_debit_pct_of_width": 45.0,
        "max_fill_degradation_vs_mid_pct": 20.0,
        "max_worst_leg_bid_ask_spread_pct": 20.0,
        "calibration_playbook": "broad",
        "max_concurrent_positions": 2,
        "max_correlated_index_positions": 2,
        "daily_loss_limit_pct": 1.0,
        "weekly_loss_limit_pct": 2.5,
        "max_position_cost_risk_pct": 5.0,
        "max_portfolio_cost_risk_pct": 10.0,
        "forced_size_tier": "starter",
        "forced_cohort_id": BULLISH_PULLBACK_OBSERVATION_COHORT_ID,
        "forced_cohort_role": BULLISH_PULLBACK_OBSERVATION_COHORT_ROLE,
        "required_candidate_execution_label": "executable_opra_paper_candidate",
    },
    "bearish_index_put_observation": {
        "id": "bearish_index_put_observation",
        "label": "Bearish Index Put Observation",
        "description": "SPY/QQQ/IWM/DIA bear put verticals for confirmed weak broad-market regimes.",
        "target_dte": 14,
        "max_new_positions_per_day": 1,
        "max_scan_picks_per_ticker": 1,
        "max_sector_open_positions": 1,
        "max_regime_open_positions": 2,
        "block_same_ticker": True,
        "allowed_asset_classes": ["index"],
        "allowed_tickers": list(INDEX_LANE_TICKERS),
        "allowed_market_regimes": ["bearish"],
        "allowed_directions": ["put"],
        "allowed_strategy_types": ["vertical_spread"],
        "min_quality_score": 65.0,
        "max_debit_pct_of_width": 60.0,
        "calibration_playbook": "broad",
        "max_concurrent_positions": 2,
        "max_correlated_index_positions": 2,
        "daily_loss_limit_pct": 1.0,
        "weekly_loss_limit_pct": 2.5,
        "max_position_cost_risk_pct": 5.0,
        "max_portfolio_cost_risk_pct": 12.0,
        "forced_size_tier": "starter",
        "forced_cohort_id": BEARISH_INDEX_PUT_OBSERVATION_COHORT_ID,
        "forced_cohort_role": BEARISH_INDEX_PUT_OBSERVATION_COHORT_ROLE,
    },
    "regular_bearish_put_primary": {
        "id": "regular_bearish_put_primary",
        "label": "Regular Bearish Put Primary",
        "description": "Broad liquid-universe bear put vertical lane for confirmed weak market regimes.",
        "lane_role": "research_profit_candidate",
        "promotion_basis": "closed_forward_alpaca_opra_required",
        "target_dte": 35,
        "max_new_positions_per_day": 1,
        "max_scan_picks_per_ticker": 1,
        "max_sector_open_positions": 2,
        "max_regime_open_positions": 2,
        "block_same_ticker": True,
        "allowed_asset_classes": ["index", "equity"],
        "allowed_tickers": list(BULLISH_PULLBACK_SCAN_TICKERS),
        "scan_tickers": list(BULLISH_PULLBACK_SCAN_TICKERS),
        "allowed_market_regimes": ["bearish"],
        "allowed_directions": ["put"],
        "scan_allowed_directions": ["put"],
        "allowed_strategy_types": ["vertical_spread"],
        "min_quality_score": 65.0,
        "max_debit_pct_of_width": 60.0,
        "calibration_playbook": "regular_bearish_put_primary",
        "max_concurrent_positions": 2,
        "max_correlated_index_positions": 2,
        "daily_loss_limit_pct": 1.0,
        "weekly_loss_limit_pct": 2.5,
        "max_position_cost_risk_pct": 5.0,
        "max_portfolio_cost_risk_pct": 10.0,
        "forced_size_tier": "starter",
        "forced_cohort_id": REGULAR_BEARISH_PUT_PRIMARY_COHORT_ID,
        "forced_cohort_role": REGULAR_BEARISH_PUT_PRIMARY_COHORT_ROLE,
        "required_candidate_execution_label": "executable_opra_paper_candidate",
    },
    "range_breakout_observation": {
        "id": "range_breakout_observation",
        "label": "Range Breakout Observation",
        "description": "Directional verticals that appear after neutral broad-market tape.",
        "target_dte": 14,
        "max_new_positions_per_day": 1,
        "max_scan_picks_per_ticker": 1,
        "max_sector_open_positions": 1,
        "max_regime_open_positions": 1,
        "block_same_ticker": True,
        "allowed_asset_classes": ["index"],
        "allowed_tickers": list(INDEX_LANE_TICKERS),
        "allowed_market_regimes": ["neutral"],
        "allowed_directions": ["call", "put"],
        "allowed_strategy_types": ["vertical_spread"],
        "min_quality_score": 65.0,
        "max_debit_pct_of_width": 55.0,
        "calibration_playbook": "broad",
        "max_concurrent_positions": 2,
        "max_correlated_index_positions": 2,
        "daily_loss_limit_pct": 1.0,
        "weekly_loss_limit_pct": 2.5,
        "max_position_cost_risk_pct": 5.0,
        "max_portfolio_cost_risk_pct": 12.0,
        "forced_size_tier": "starter",
        "forced_cohort_id": RANGE_BREAKOUT_OBSERVATION_COHORT_ID,
        "forced_cohort_role": RANGE_BREAKOUT_OBSERVATION_COHORT_ROLE,
    },
    "volatility_expansion_observation": {
        "id": "volatility_expansion_observation",
        "label": "Volatility Expansion Observation",
        "description": "Index verticals for either-direction expansion when the normal bullish lane is not enough coverage.",
        "target_dte": 14,
        "max_new_positions_per_day": 1,
        "max_scan_picks_per_ticker": 1,
        "max_sector_open_positions": 1,
        "max_regime_open_positions": 2,
        "block_same_ticker": True,
        "allowed_asset_classes": ["index"],
        "allowed_tickers": list(INDEX_LANE_TICKERS),
        "allowed_directions": ["call", "put"],
        "allowed_strategy_types": ["vertical_spread"],
        "min_quality_score": 70.0,
        "max_debit_pct_of_width": 55.0,
        "calibration_playbook": "broad",
        "max_concurrent_positions": 2,
        "max_correlated_index_positions": 2,
        "daily_loss_limit_pct": 1.0,
        "weekly_loss_limit_pct": 2.5,
        "max_position_cost_risk_pct": 5.0,
        "max_portfolio_cost_risk_pct": 12.0,
        "forced_size_tier": "starter",
        "forced_cohort_id": VOLATILITY_EXPANSION_OBSERVATION_COHORT_ID,
        "forced_cohort_role": VOLATILITY_EXPANSION_OBSERVATION_COHORT_ROLE,
    },
    "ai_commodity_infra_observation": {
        "id": "ai_commodity_infra_observation",
        "label": "AI Commodity Infra",
        "description": "Liquid AI power, grid, copper, silver, lithium, and uranium proxies with either-side directional verticals.",
        "target_dte": 35,
        "max_new_positions_per_day": 1,
        "max_scan_picks_per_ticker": 1,
        "max_sector_open_positions": 1,
        "max_regime_open_positions": 2,
        "block_same_ticker": True,
        "allowed_asset_classes": ["index", "equity"],
        "allowed_tickers": list(AI_COMMODITY_INFRA_TICKERS),
        "scan_tickers": list(AI_COMMODITY_INFRA_TICKERS),
        "core_tickers": list(AI_COMMODITY_INFRA_CORE_TICKERS),
        "conditional_tickers": list(AI_COMMODITY_INFRA_CONDITIONAL_TICKERS),
        "allowed_directions": ["call", "put"],
        "allowed_strategy_types": ["vertical_spread"],
        "min_quality_score": 70.0,
        "max_debit_pct_of_width": 55.0,
        "calibration_playbook": "broad",
        "max_concurrent_positions": 2,
        "max_correlated_index_positions": 1,
        "daily_loss_limit_pct": 1.0,
        "weekly_loss_limit_pct": 2.5,
        "max_position_cost_risk_pct": 5.0,
        "max_portfolio_cost_risk_pct": 12.0,
        "forced_size_tier": "starter",
        "forced_cohort_id": AI_COMMODITY_INFRA_OBSERVATION_COHORT_ID,
        "forced_cohort_role": AI_COMMODITY_INFRA_OBSERVATION_COHORT_ROLE,
        "required_candidate_execution_label": EXECUTABLE_OPRA_PAPER_CANDIDATE_LABEL,
        "conditional_required_candidate_execution_label": EXECUTABLE_OPRA_PAPER_CANDIDATE_LABEL,
        "theme_tags": ["ai_power", "grid", "copper", "silver", "lithium", "uranium"],
    },
    "quality90_debit55_canary": {
        "id": "quality90_debit55_canary",
        "label": "Quality90 Debit55 Canary",
        "description": "SPY/QQQ bullish call spread canary: quality score at least 90 and debit below 55% of spread width.",
        "lane_role": "proof_control_yardstick",
        "promotion_basis": "closed_forward_alpaca_opra_required",
        "target_dte": 14,
        "max_new_positions_per_day": 1,
        "max_scan_picks_per_ticker": 1,
        "max_sector_open_positions": 1,
        "max_regime_open_positions": 1,
        "block_same_ticker": True,
        "allowed_asset_classes": ["index"],
        "allowed_tickers": list(SPECULATIVE_ALLOWED_TICKERS),
        "scan_tickers": list(SPECULATIVE_ALLOWED_TICKERS),
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "scan_allowed_directions": ["call"],
        "allowed_strategy_types": ["vertical_spread"],
        "min_quality_score": 90.0,
        "max_debit_pct_of_width": 55.0,
        "calibration_playbook": "bullish_index_calls_quality90_debit55",
        "max_concurrent_positions": 1,
        "max_correlated_index_positions": 1,
        "daily_loss_limit_pct": 1.0,
        "weekly_loss_limit_pct": 2.5,
        "max_position_cost_risk_pct": 5.0,
        "max_portfolio_cost_risk_pct": 10.0,
        "forced_size_tier": "starter",
        "forced_cohort_id": QUALITY90_DEBIT55_CANARY_COHORT_ID,
        "forced_cohort_role": QUALITY90_DEBIT55_CANARY_COHORT_ROLE,
        "required_candidate_execution_label": "executable_opra_paper_candidate",
    },
    "tracked_winner_observation": {
        "id": "tracked_winner_observation",
        "label": "Tracked Winner Observation",
        "description": "Lane shaped by the current profitable tracked positions: bullish call verticals with debit below 40% of spread width.",
        "target_dte": 35,
        "max_new_positions_per_day": 2,
        "max_scan_picks_per_ticker": 1,
        "max_sector_open_positions": 2,
        "max_regime_open_positions": 3,
        "block_same_ticker": True,
        "allowed_asset_classes": ["index", "equity"],
        "allowed_tickers": ["SPY", "GOOGL", "XLK", "DIA"],
        "allowed_market_regimes": ["bullish"],
        "allowed_directions": ["call"],
        "allowed_strategy_types": ["vertical_spread"],
        "max_debit_pct_of_width": 40.0,
        "calibration_playbook": "broad",
        "max_concurrent_positions": 5,
        "max_correlated_index_positions": 3,
        "daily_loss_limit_pct": 2.0,
        "weekly_loss_limit_pct": 5.0,
        "max_position_cost_risk_pct": 10.0,
        "max_portfolio_cost_risk_pct": 30.0,
        "forced_size_tier": "starter",
        "forced_cohort_id": TRACKED_WINNER_OBSERVATION_COHORT_ID,
        "forced_cohort_role": TRACKED_WINNER_OBSERVATION_COHORT_ROLE,
    },
}


_LANE_PRIORITIES = {
    "bullish_pullback_observation": 10,
    "tracked_winner_primary": 20,
    "short_term": 30,
    "swing": 35,
    "bullish_momentum": 40,
    "bearish_defensive": 45,
    "regular_bearish_put_primary": 46,
    "tracked_winner_observation": 80,
    "quality90_debit55_canary": 90,
    "bearish_index_put_observation": 95,
    "range_breakout_observation": 100,
    "volatility_expansion_observation": 105,
    "ai_commodity_infra_observation": 108,
    "speculative": 110,
}
for _playbook_id, _playbook in SCAN_PLAYBOOKS.items():
    _playbook.setdefault("lane_priority", _LANE_PRIORITIES.get(_playbook_id, 100))


def _load_ai_commodity_readiness(path: Path = AI_COMMODITY_INFRA_READINESS_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {
            "source": str(path),
            "available_underlyings": [],
            "status": "missing_readiness_artifact",
        }
    if not isinstance(payload, dict):
        return {
            "source": str(path),
            "available_underlyings": [],
            "status": "invalid_readiness_artifact",
        }
    return {
        "source": str(path),
        "available_underlyings": [
            str(symbol or "").strip().upper()
            for symbol in payload.get("available_underlyings") or []
            if str(symbol or "").strip()
        ],
        "status": str(payload.get("status") or "unknown"),
        "generated_at": payload.get("generated_at"),
    }


def _enrich_ai_commodity_playbook_with_readiness(playbook: dict[str, Any]) -> dict[str, Any]:
    if str(playbook.get("id") or "") != AI_COMMODITY_INFRA_OBSERVATION_COHORT_ID:
        return playbook
    readiness = _load_ai_commodity_readiness()
    data_ready = ai_commodity_data_ready_tickers(readiness.get("available_underlyings") or [])
    ready_set = set(data_ready)
    core_ready = [symbol for symbol in AI_COMMODITY_INFRA_CORE_TICKERS if symbol in ready_set]
    conditional_ready = [symbol for symbol in AI_COMMODITY_INFRA_CONDITIONAL_TICKERS if symbol in ready_set]
    missing = [symbol for symbol in AI_COMMODITY_INFRA_TICKERS if symbol not in ready_set]
    enriched = dict(playbook)
    enriched.update(
        {
            "historical_data_source": readiness.get("source"),
            "historical_data_readiness_status": readiness.get("status"),
            "historical_data_readiness_generated_at": readiness.get("generated_at"),
            "historical_data_ready_tickers": data_ready,
            "historical_core_ready_tickers": core_ready,
            "historical_conditional_ready_tickers": conditional_ready,
            "historical_missing_tickers": missing,
            "historical_core_ready_count": len(core_ready),
            "historical_core_required_count": len(AI_COMMODITY_INFRA_CORE_TICKERS),
            "historical_scan_ready_count": len(data_ready),
            "historical_scan_required_count": len(AI_COMMODITY_INFRA_TICKERS),
        }
    )
    return enriched


def get_scan_playbook(playbook_id: Optional[str] = None) -> dict[str, Any]:
    key = str(playbook_id or DEFAULT_SCAN_PLAYBOOK_ID).strip().lower()
    if key not in SCAN_PLAYBOOKS:
        available = ", ".join(sorted(SCAN_PLAYBOOKS))
        raise ValueError(f"Unknown scan playbook '{playbook_id}'. Available playbooks: {available}")
    return _enrich_ai_commodity_playbook_with_readiness(dict(SCAN_PLAYBOOKS[key]))


def get_scan_playbooks() -> list[dict[str, Any]]:
    playbooks = [get_scan_playbook(playbook_id) for playbook_id in SCAN_PLAYBOOKS]
    return sorted(
        playbooks,
        key=lambda playbook: (
            int(playbook.get("lane_priority", 100) or 100),
            str(playbook.get("label") or playbook.get("id") or ""),
        ),
    )


def _callable_accepts_keyword(func: Callable[..., Any], keyword: str) -> bool:
    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False
    if keyword in parameters:
        return True
    return any(param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values())


def _scan_allowed_directions_for_playbook(playbook: dict[str, Any]) -> list[str]:
    raw_values = playbook.get("scan_allowed_directions")
    if raw_values is None:
        raw_values = playbook.get("allowed_directions")
    if isinstance(raw_values, str):
        values = [item.strip() for item in raw_values.split(",") if item.strip()]
    else:
        values = list(raw_values or [])
    return sorted(_normalized_label_set(values))


def _scan_symbols_for_playbook(playbook: dict[str, Any]) -> list[str]:
    raw_values = playbook.get("scan_tickers")
    if raw_values is None:
        raw_values = playbook.get("allowed_tickers") or []
    if isinstance(raw_values, str):
        values = [item.strip().upper() for item in raw_values.split(",") if item.strip()]
    else:
        values = [str(item or "").strip().upper() for item in raw_values or [] if str(item or "").strip()]
    return list(dict.fromkeys(values))


def _data_readiness_diagnostics_for_playbook(playbook: dict[str, Any]) -> dict[str, Any]:
    scan_tickers = _scan_symbols_for_playbook(playbook)
    allowed_tickers = [
        str(item or "").strip().upper()
        for item in list(playbook.get("allowed_tickers") or [])
        if str(item or "").strip()
    ]
    expansion_tickers = [
        str(item or "").strip().upper()
        for item in list(playbook.get("expansion_tickers") or [])
        if str(item or "").strip()
    ]
    ready_tickers = [
        str(item or "").strip().upper()
        for item in list(playbook.get("historical_data_ready_tickers") or [])
        if str(item or "").strip()
    ]
    ready_set = set(ready_tickers)
    promoted_set = set(scan_tickers or allowed_tickers)
    research_only = []
    for ticker in expansion_tickers:
        if ticker in promoted_set and ticker in ready_set:
            continue
        research_only.append(
            {
                "ticker": ticker,
                "status": "research_only",
                "reason": "missing_exact_bid_ask_readiness_or_profitability_proof",
                "required_gates": copy.deepcopy(playbook.get("data_readiness_gates") or {}),
            }
        )
    return {
        "status": playbook.get("historical_data_readiness_status") or "not_required",
        "historical_data_source": playbook.get("historical_data_source"),
        "scan_tickers": scan_tickers,
        "allowed_tickers": allowed_tickers,
        "historical_data_ready_tickers": ready_tickers,
        "expansion_tickers": expansion_tickers,
        "research_only_tickers": research_only,
        "required_gates": copy.deepcopy(playbook.get("data_readiness_gates") or {}),
    }


def scan_pick_market_regime(pick: dict[str, Any]) -> str:
    try:
        spy_ret5 = float(pick.get("spy_ret5", 0.0) or 0.0)
    except (TypeError, ValueError):
        return "unknown"
    if spy_ret5 <= -0.5:
        return "bearish"
    if spy_ret5 >= 0.5:
        return "bullish"
    return "neutral"


def _normalized_label_set(values: list[Any]) -> set[str]:
    labels: set[str] = set()
    for value in values or []:
        text = str(value or "").strip().lower()
        if text:
            labels.add(text)
    return labels


def _normalized_scan_drop_counts(value: Optional[dict[str, Any]]) -> dict[str, int]:
    payload = dict(value or {})
    normalized = {key: 0 for key in SCAN_FUNNEL_DROP_KEYS}
    for key in SCAN_FUNNEL_DROP_KEYS:
        normalized[key] = int(payload.get(key) or 0)
    return normalized


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _et_date(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=_ET)
    return value.astimezone(_ET)


def _candidate_rank_tuple(pick: dict[str, Any]) -> tuple[float, float, float, float, float, float]:
    calibrated = pick.get("calibrated_expectancy_pct")
    promotable_exact = str(pick.get("promotion_class") or "").strip().lower() == "promotable_exact_contract"
    calibrated_value = (
        float(calibrated or 0.0)
        if calibrated is not None and promotable_exact and bool(pick.get("calibration_is_dense"))
        else -9999.0
    )
    return (
        1 if promotable_exact else 0,
        1 if bool(pick.get("calibration_is_dense")) else 0,
        calibrated_value,
        float(pick.get("direction_score", 0.0) or 0.0),
        float(pick.get("quality_score", 0.0) or 0.0),
        float(pick.get("tech_score", 0.0) or 0.0),
    )


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp_tier(value: int) -> int:
    return max(1, min(int(value), 5))


def _candidate_profit_id(symbol: str, direction: str, cohort_id: str) -> str:
    normalized_symbol = str(symbol or "").strip().upper()
    normalized_direction = str(direction or "").strip().lower()
    return f"{normalized_symbol}__{normalized_direction}__{str(cohort_id or '').strip()}"


def _bid_ask_spread_pct(pick: dict[str, Any]) -> float | None:
    bid = _safe_float(pick.get("bid"))
    ask = _safe_float(pick.get("ask"))
    mid = (
        _safe_float(pick.get("mid"))
        or _safe_float(pick.get("premium"))
        or _safe_float(pick.get("est_premium"))
    )
    if bid is None or ask is None or mid is None or mid <= 0 or ask < bid:
        return None
    return ((ask - bid) / mid) * 100.0


def _derive_convexity_profile(pick: dict[str, Any]) -> dict[str, Any]:
    dte = _safe_int(pick.get("dte"))
    delta_value = _safe_float(pick.get("delta"))
    if delta_value is None:
        delta_value = _safe_float(pick.get("delta_est"))
    delta = abs(delta_value) if delta_value is not None else None
    iv_pct = _safe_float(pick.get("iv_percentile"))
    if iv_pct is None:
        iv_pct = _safe_float(pick.get("iv_pct"))
    premium = (
        _safe_float(pick.get("premium"))
        or _safe_float(pick.get("est_premium"))
        or _safe_float(pick.get("mid"))
    )
    spread_pct = _bid_ask_spread_pct(pick)
    quote_freshness = str(pick.get("quote_freshness_status") or "").strip().lower()

    risk_tier = 1
    upside_tier = 1
    reasons: list[str] = []

    if dte is not None:
        if dte <= 5:
            risk_tier += 2
            upside_tier += 2
            reasons.append("5 DTE or less sharply increases gamma and theta sensitivity.")
        elif dte <= 7:
            risk_tier += 1
            upside_tier += 1

    if delta is not None:
        if delta <= 0.2:
            risk_tier += 2
            upside_tier += 2
            reasons.append("Low delta makes the contract lower-probability but more convex.")
        elif delta <= 0.35:
            risk_tier += 1
            upside_tier += 1
        elif delta >= 0.55:
            risk_tier -= 1

    if premium is not None:
        if premium <= 1.0:
            risk_tier += 1
            upside_tier += 1
            reasons.append("Lower premium increases all-or-nothing risk and percentage payoff potential.")
        elif premium >= 4.0:
            upside_tier -= 1

    if iv_pct is not None and iv_pct >= 70.0:
        risk_tier += 1
        reasons.append("Elevated IV raises the chance of vol-compression drag.")

    if spread_pct is not None and spread_pct >= 10.0:
        risk_tier += 1
        reasons.append("Wide bid/ask spread adds execution risk.")

    if quote_freshness and quote_freshness not in {"fresh", "live"}:
        risk_tier += 1
        reasons.append("Quote freshness is not marked fresh.")

    risk_tier = _clamp_tier(risk_tier)
    upside_tier = _clamp_tier(upside_tier)
    speculative_flag = risk_tier >= 4 and upside_tier >= 4
    if speculative_flag:
        convexity_class = "speculative"
    elif risk_tier >= 3 or upside_tier >= 3:
        convexity_class = "aggressive"
    else:
        convexity_class = "core"

    return {
        "risk_tier": risk_tier,
        "upside_tier": upside_tier,
        "speculative_flag": speculative_flag,
        "speculative_reason": reasons,
        "convexity_class": convexity_class,
    }


def _watch_symbol_rank(pick: dict[str, Any], policy: Optional[dict[str, Any]]) -> int:
    if not policy:
        return 0
    decision = str(
        pick.get("managed_lane_decision")
        or pick.get("trade_policy_decision")
        or "watch"
    ).strip().lower()
    if decision != "watch":
        return 0
    ticker = str(pick.get("ticker") or "").strip().upper()
    priority = {
        str(symbol or "").strip().upper()
        for symbol in policy.get("watch_priority_symbols")
        or (policy.get("scan_policy") or {}).get("watch_priority_symbols")
        or []
        if str(symbol or "").strip()
    }
    deprioritized = {
        str(symbol or "").strip().upper()
        for symbol in policy.get("watch_deprioritized_symbols")
        or (policy.get("scan_policy") or {}).get("watch_deprioritized_symbols")
        or []
        if str(symbol or "").strip()
    }
    if ticker in priority:
        return 1
    if ticker in deprioritized:
        return -1
    return 0


def _normalized_snapshot_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text or "unknown"


def _managed_pick_block_reason(pick: dict[str, Any], policy: Optional[dict[str, Any]]) -> Optional[str]:
    if not policy:
        return "policy_not_applied"
    if str(policy.get("truth_window_status") or "unknown").strip().lower() == "stale":
        return "truth_window_stale"
    promotion_class = str(pick.get("promotion_class") or "").strip().lower()
    if promotion_class != "promotable_exact_contract":
        return f"promotion_class:{promotion_class or 'unknown'}"
    selection_source = str(
        pick.get("selection_source")
        or pick.get("contract_selection_source")
        or ""
    ).strip().lower()
    if selection_source != "live_chain_exact_contract":
        return f"selection_source:{selection_source or 'unknown'}"
    options_snapshot_status = _normalized_snapshot_status(pick.get("options_snapshot_status"))
    if options_snapshot_status != "fresh":
        return f"options_snapshot_status:{options_snapshot_status}"
    option_chain_status = _normalized_snapshot_status(pick.get("option_chain_status"))
    if option_chain_status != "fresh":
        return f"option_chain_status:{option_chain_status}"
    if str(pick.get("guardrail_decision") or "clear").strip().lower() == "blocked":
        return "guardrail_decision:blocked"
    approved_tickers = {
        str(symbol or "").strip().upper()
        for symbol in ((policy.get("scan_policy") or {}).get("hard_filters") or {}).get("approved_tickers") or []
        if str(symbol or "").strip()
    }
    ticker = str(pick.get("ticker") or "").strip().upper()
    if approved_tickers and ticker not in approved_tickers:
        return "approved_symbol_scope"
    trade_policy_decision = str(pick.get("trade_policy_decision") or "watch").strip().lower()
    # During evidence-building (no approved symbols yet), candidates that
    # pass all quality checks above are surfaced for supervised use.
    # Hard-filter failures (decision="blocked") are still rejected.
    managed_lane_status = str(
        policy.get("managed_lane_status") or ""
    ).strip().lower()
    if (
        managed_lane_status == "blocked_no_approved_symbols"
        and trade_policy_decision == "watch"
    ):
        return None
    if trade_policy_decision != "approved":
        return f"trade_policy_decision:{trade_policy_decision or 'unknown'}"
    return None


def _annotate_managed_pick(pick: dict[str, Any], policy: Optional[dict[str, Any]]) -> dict[str, Any]:
    annotated = dict(pick)
    annotated["options_snapshot_status"] = _normalized_snapshot_status(
        annotated.get("options_snapshot_status")
    )
    annotated["option_chain_status"] = _normalized_snapshot_status(
        annotated.get("option_chain_status")
    )
    block_reason = _managed_pick_block_reason(annotated, policy)
    guardrail_decision = str(annotated.get("guardrail_decision") or "clear").strip().lower()
    managed_eligible = block_reason is None
    if managed_eligible:
        managed_lane_decision = "approved"
    elif guardrail_decision == "blocked":
        managed_lane_decision = "blocked"
    else:
        managed_lane_decision = "watch"
    annotated["managed_eligible"] = managed_eligible
    annotated["managed_block_reason"] = block_reason
    annotated["managed_lane_decision"] = managed_lane_decision
    return annotated


CORRELATED_INDEXES = {"SPY", "QQQ", "IWM", "DIA"}


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _record_source(record: dict[str, Any]) -> dict[str, Any]:
    source = record.get("source_pick_snapshot")
    return dict(source) if isinstance(source, dict) else {}


def _nested_mapping(record: dict[str, Any], key: str) -> dict[str, Any]:
    value = record.get(key)
    return value if isinstance(value, dict) else {}


def _pick_execution_basis(record: dict[str, Any]) -> str:
    entry_quote_snapshot = _nested_mapping(record, "entry_quote_snapshot")
    return str(
        record.get("entry_execution_basis")
        or entry_quote_snapshot.get("entry_execution_basis")
        or record.get("intended_limit_basis")
        or record.get("attempted_limit_basis")
        or ""
    ).strip().lower()


def _pick_candidate_execution_label(record: dict[str, Any]) -> str:
    return str(
        record.get("candidate_execution_label")
        or record.get("execution_candidate_label")
        or ""
    ).strip().lower()


def _execution_basis_is_ask_bid_style(value: Any) -> bool:
    return str(value or "").strip().lower() in {"ask", "spread_ask_bid"}


def _candidate_label_is_opra_executable(value: Any) -> bool:
    return str(value or "").strip().lower() == EXECUTABLE_OPRA_PAPER_CANDIDATE_LABEL


def _debit_provenance_flags(
    *,
    debit_source: str,
    context: dict[str, Any],
    fallback_context: dict[str, Any],
    intrinsically_ask_bid_style: bool = False,
) -> tuple[bool, bool, str | None, str | None]:
    basis = _pick_execution_basis(context) or _pick_execution_basis(fallback_context)
    label = _pick_candidate_execution_label(context) or _pick_candidate_execution_label(fallback_context)
    is_ask_bid_style = bool(intrinsically_ask_bid_style or _execution_basis_is_ask_bid_style(basis))
    is_opra_executable = _candidate_label_is_opra_executable(label)
    if debit_source.endswith("entry_execution_price") and not basis and not label:
        is_ask_bid_style = False
        is_opra_executable = False
    return is_ask_bid_style, is_opra_executable, basis or None, label or None


def vertical_spread_signature(record: dict[str, Any]) -> tuple[Any, ...] | None:
    source = _record_source(record)
    strategy_type = str(
        record.get("strategy_type")
        or source.get("strategy_type")
        or ""
    ).strip().lower()
    short_strike = _safe_float(record.get("short_strike") if record.get("short_strike") is not None else source.get("short_strike"))
    short_contract_symbol = str(
        record.get("short_contract_symbol")
        or source.get("short_contract_symbol")
        or ""
    ).strip().upper()
    if strategy_type != "vertical_spread" and short_strike is None and not short_contract_symbol:
        return None

    ticker = str(record.get("ticker") or source.get("ticker") or "").strip().upper()
    direction = str(record.get("direction") or record.get("type") or source.get("direction") or source.get("type") or "").strip().lower()
    expiry = str(record.get("expiry") or source.get("expiry") or "").strip()[:10]
    strike = _safe_float(
        record.get("strike")
        if record.get("strike") is not None
        else source.get("strike")
        if source.get("strike") is not None
        else source.get("strike_est")
    )
    if not ticker or not direction or not expiry or strike is None:
        return None
    return (
        ticker,
        direction,
        expiry,
        strike,
        short_strike,
    )


def _position_cost_risk_usd(record: dict[str, Any]) -> float | None:
    source = _record_source(record)
    price = _safe_float(
        record.get("entry_execution_price")
        if record.get("entry_execution_price") is not None
        else record.get("entry_option_price")
        if record.get("entry_option_price") is not None
        else source.get("entry_execution_price")
        if source.get("entry_execution_price") is not None
        else source.get("premium")
    )
    try:
        contracts = int(record.get("contracts") or source.get("contracts") or 1)
    except (TypeError, ValueError):
        contracts = 1
    if price is None or price <= 0 or contracts <= 0:
        return None
    return round(price * contracts * 100.0, 2)


def _debit_for_width(record: dict[str, Any]) -> tuple[float | None, str | None, bool, bool, str | None, str | None]:
    source = _record_source(record)
    record_liquidity = record.get("spread_liquidity") if isinstance(record.get("spread_liquidity"), dict) else {}
    source_liquidity = source.get("spread_liquidity") if isinstance(source.get("spread_liquidity"), dict) else {}
    candidates = [
        ("entry_execution_price", record.get("entry_execution_price"), record, False),
        ("spread_entry_debit", record.get("spread_entry_debit"), record, True),
        ("spread_liquidity.spread_entry_debit", record_liquidity.get("spread_entry_debit"), record, True),
        ("source_pick_snapshot.entry_execution_price", source.get("entry_execution_price"), source, False),
        ("source_pick_snapshot.spread_entry_debit", source.get("spread_entry_debit"), source, True),
        ("source_pick_snapshot.spread_liquidity.spread_entry_debit", source_liquidity.get("spread_entry_debit"), source, True),
        ("net_debit", record.get("net_debit"), record, False),
        ("spread_mid_debit", record.get("spread_mid_debit"), record, False),
        ("spread_liquidity.spread_mid_debit", record_liquidity.get("spread_mid_debit"), record, False),
        ("source_pick_snapshot.net_debit", source.get("net_debit"), source, False),
        ("source_pick_snapshot.spread_mid_debit", source.get("spread_mid_debit"), source, False),
        ("source_pick_snapshot.spread_liquidity.spread_mid_debit", source_liquidity.get("spread_mid_debit"), source, False),
    ]
    for source_name, value, context, intrinsically_ask_bid_style in candidates:
        debit = _safe_float(value)
        if debit is not None:
            if source_name.endswith("net_debit") or "spread_mid_debit" in source_name:
                return debit, source_name, False, False, None, None
            is_ask_bid_style, is_opra_executable, basis, label = _debit_provenance_flags(
                debit_source=source_name,
                context=context,
                fallback_context=record,
                intrinsically_ask_bid_style=intrinsically_ask_bid_style,
            )
            return debit, source_name, is_ask_bid_style, is_opra_executable, basis, label
    return None, None, False, False, None, None


def _debit_pct_of_width(record: dict[str, Any]) -> float | None:
    source = _record_source(record)
    debit, _, _, _, _, _ = _debit_for_width(record)
    spread_width = _safe_float(
        record.get("spread_width")
        if record.get("spread_width") is not None
        else source.get("spread_width")
    )
    if debit is None or spread_width is None or spread_width <= 0:
        return None
    return round(debit / spread_width * 100.0, 2)


def _fill_degradation_vs_mid_pct(record: dict[str, Any]) -> float | None:
    source = _record_source(record)
    record_liquidity = _nested_mapping(record, "spread_liquidity")
    source_liquidity = _nested_mapping(source, "spread_liquidity")
    explicit = _safe_float(
        record.get("fill_degradation_vs_mid_pct")
        if record.get("fill_degradation_vs_mid_pct") is not None
        else source.get("fill_degradation_vs_mid_pct")
    )
    if explicit is not None:
        return explicit
    entry_debit = _safe_float(
        record_liquidity.get("spread_entry_debit")
        if record_liquidity.get("spread_entry_debit") is not None
        else source_liquidity.get("spread_entry_debit")
        if source_liquidity.get("spread_entry_debit") is not None
        else record.get("spread_entry_debit")
        if record.get("spread_entry_debit") is not None
        else source.get("spread_entry_debit")
    )
    mid_debit = _safe_float(
        record_liquidity.get("spread_mid_debit")
        if record_liquidity.get("spread_mid_debit") is not None
        else source_liquidity.get("spread_mid_debit")
        if source_liquidity.get("spread_mid_debit") is not None
        else record.get("spread_mid_debit")
        if record.get("spread_mid_debit") is not None
        else source.get("spread_mid_debit")
    )
    if entry_debit is None or mid_debit is None or mid_debit <= 0:
        return None
    return round(max((entry_debit / mid_debit - 1.0) * 100.0, 0.0), 2)


def _worst_leg_bid_ask_spread_pct(record: dict[str, Any]) -> float | None:
    source = _record_source(record)
    record_liquidity = _nested_mapping(record, "spread_liquidity")
    source_liquidity = _nested_mapping(source, "spread_liquidity")
    explicit = _safe_float(
        record.get("worst_leg_bid_ask_spread_pct")
        if record.get("worst_leg_bid_ask_spread_pct") is not None
        else source.get("worst_leg_bid_ask_spread_pct")
        if source.get("worst_leg_bid_ask_spread_pct") is not None
        else record_liquidity.get("worst_leg_bid_ask_spread_pct")
        if record_liquidity.get("worst_leg_bid_ask_spread_pct") is not None
        else source_liquidity.get("worst_leg_bid_ask_spread_pct")
    )
    if explicit is not None:
        return explicit
    values: list[float] = []
    for liquidity in (record_liquidity, source_liquidity):
        for prefix in ("long", "short"):
            bid = _safe_float(liquidity.get(f"{prefix}_bid"))
            ask = _safe_float(liquidity.get(f"{prefix}_ask"))
            if bid is None or ask is None:
                continue
            mid = (bid + ask) / 2.0
            if mid > 0:
                values.append(max((ask - bid) / mid * 100.0, 0.0))
    return round(max(values), 2) if values else None


def _signal_ret5(record: dict[str, Any]) -> float | None:
    source = _record_source(record)
    return _safe_float(
        record.get("signal_ret5")
        if record.get("signal_ret5") is not None
        else source.get("signal_ret5")
        if source.get("signal_ret5") is not None
        else record.get("ret5")
        if record.get("ret5") is not None
        else source.get("ret5")
    )


def _tracked_winner_fit(record: dict[str, Any], playbook: dict[str, Any]) -> tuple[float, list[str]]:
    profile = playbook.get("winner_profile")
    if not isinstance(profile, dict):
        return 0.0, []

    score = 0.0
    reasons: list[str] = []
    ticker = str(record.get("ticker") or "").strip().upper()
    direction = str(record.get("direction") or record.get("type") or "").strip().lower()
    strategy_type = str(
        record.get("strategy_type")
        or ("vertical_spread" if record.get("short_strike") is not None else "")
    ).strip().lower()
    market_regime = str(record.get("market_regime") or scan_pick_market_regime(record)).strip().lower()
    preferred_tickers = {str(symbol).strip().upper() for symbol in profile.get("preferred_tickers") or []}

    if ticker in preferred_tickers:
        score += 25.0
        reasons.append("ticker_match")
    if direction == str(profile.get("preferred_direction") or "").strip().lower():
        score += 20.0
        reasons.append("direction_match")
    if strategy_type == str(profile.get("preferred_strategy_type") or "").strip().lower():
        score += 20.0
        reasons.append("strategy_match")
    if market_regime == str(profile.get("preferred_market_regime") or "").strip().lower():
        score += 15.0
        reasons.append("regime_match")

    debit_pct = _debit_pct_of_width(record)
    max_debit_pct = _safe_float(profile.get("max_debit_pct_of_width"))
    if debit_pct is not None and max_debit_pct is not None and debit_pct < max_debit_pct:
        score += 15.0
        reasons.append("debit_match")
        if 25.0 <= debit_pct <= max_debit_pct:
            score += 5.0
            reasons.append("tracked_debit_bucket")

    return round(score, 1), reasons


def _block_guardrail_pick(pick: dict[str, Any], reason: str) -> dict[str, Any]:
    blocked = dict(pick)
    reasons = list(blocked.get("guardrail_reasons") or [])
    if reason not in reasons:
        reasons.append(reason)
    blocked["guardrail_decision"] = "blocked"
    blocked["guardrail_reasons"] = reasons
    blocked["suggested_size_tier"] = "blocked"
    blocked["suggested_size_reason"] = "Do not add this trade while the current playbook guardrails are blocking it."
    return blocked


def load_open_position_context(positions_repository: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "available": True,
        "open_positions": 0,
        "opened_today": 0,
        "ticker_counts": {},
        "sector_counts": {},
        "regime_counts": {},
        "vertical_spread_signature_counts": {},
        "open_cost_risk_usd": 0.0,
        "warnings": [],
        "daily_realized_pnl_usd": 0.0,
        "weekly_realized_pnl_usd": 0.0,
        "correlated_index_count": 0,
    }
    if not getattr(positions_repository, "is_available", False):
        context["available"] = False
        context["warnings"].append("Tracked positions storage is unavailable, so portfolio guardrails cannot see live open exposure yet.")
        return context

    try:
        open_positions = positions_repository.list_positions("open")
        try:
            all_positions = positions_repository.list_positions(None)
        except Exception:
            all_positions = list(open_positions)
    except Exception as exc:
        context["available"] = False
        context["warnings"].append(f"Could not load tracked positions for guardrails: {exc}")
        return context

    ticker_counts: dict[str, int] = {}
    sector_counts: dict[str, int] = {}
    regime_counts: dict[str, int] = {}
    sector_direction_counts: dict[str, int] = {}
    vertical_spread_signature_counts: dict[str, int] = {}
    opened_today = 0
    correlated_index_count = 0
    open_cost_risk_usd = 0.0
    today_et = datetime.now(_ET).date()

    for position in list(all_positions or []):
        filled_at = _et_date(_parse_iso_datetime(position.get("filled_at")))
        if filled_at and filled_at.date() == today_et:
            opened_today += 1

    for position in open_positions:
        source_pick = dict(position.get("source_pick_snapshot") or {})
        ticker = str(position.get("ticker") or source_pick.get("ticker") or "").upper()
        sector = str(source_pick.get("sector") or "").strip()
        market_regime = str(source_pick.get("market_regime") or scan_pick_market_regime(source_pick)).strip().lower()
        pos_direction = str(source_pick.get("direction") or source_pick.get("type") or "").strip().lower()

        if ticker:
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
            if ticker in CORRELATED_INDEXES:
                correlated_index_count += 1
        if sector:
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        if market_regime and market_regime != "unknown":
            regime_counts[market_regime] = regime_counts.get(market_regime, 0) + 1
        if sector and pos_direction in {"call", "put"}:
            sd_key = f"{sector}|{pos_direction}"
            sector_direction_counts[sd_key] = sector_direction_counts.get(sd_key, 0) + 1
        spread_signature = vertical_spread_signature(dict(position))
        if spread_signature is not None:
            spread_key = repr(spread_signature)
            vertical_spread_signature_counts[spread_key] = vertical_spread_signature_counts.get(spread_key, 0) + 1
        cost_risk = _position_cost_risk_usd(dict(position))
        if cost_risk is not None:
            open_cost_risk_usd += cost_risk

    # Query realized P&L for daily/weekly loss limits
    daily_realized_pnl_usd = 0.0
    weekly_realized_pnl_usd = 0.0
    try:
        now_et = datetime.now(_ET)
        today_open = now_et.replace(hour=0, minute=0, second=0, microsecond=0)
        weekday = today_open.weekday()
        monday_open = today_open - timedelta(days=weekday)
        if hasattr(positions_repository, "get_realized_pnl_since"):
            daily_realized_pnl_usd = positions_repository.get_realized_pnl_since(today_open)
            weekly_realized_pnl_usd = positions_repository.get_realized_pnl_since(monday_open)
    except Exception:
        pass

    context.update(
        {
            "open_positions": len(open_positions),
            "opened_today": opened_today,
            "ticker_counts": ticker_counts,
            "sector_counts": sector_counts,
            "regime_counts": regime_counts,
            "sector_direction_counts": sector_direction_counts,
            "vertical_spread_signature_counts": vertical_spread_signature_counts,
            "open_cost_risk_usd": round(open_cost_risk_usd, 2),
            "daily_realized_pnl_usd": daily_realized_pnl_usd,
            "weekly_realized_pnl_usd": weekly_realized_pnl_usd,
            "correlated_index_count": correlated_index_count,
        }
    )
    return context


def annotate_pick_with_trade_policy(pick: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(pick)
    scan_policy = dict(policy.get("scan_policy") or {})
    preferred_filters = dict(scan_policy.get("preferred_filters") or {})
    hard_filters = dict(scan_policy.get("hard_filters") or {})
    classified = _classify_trade_against_live_policy(annotated, scan_policy)

    ticker = str(annotated.get("ticker") or "").upper()
    sector = str(annotated.get("sector") or "").strip()
    market_regime = str(classified.get("market_regime") or scan_pick_market_regime(annotated)).strip().lower()
    asset_class = str(classified.get("asset_class") or annotated.get("asset_class") or "").strip().lower()
    direction_score = float(annotated.get("direction_score", 0.0) or 0.0)
    promotion_status = str(scan_policy.get("promotion_status") or "watch").strip().lower()

    fit_reasons: list[str] = []
    direction_score_min = hard_filters.get("direction_score_min")
    direction_score_max = hard_filters.get("direction_score_max")
    if direction_score_min is not None and direction_score < float(direction_score_min):
        fit_reasons.append(f"Direction score {direction_score:.1f} is below the replay-backed floor of {float(direction_score_min):.1f}.")
    if direction_score_max is not None and direction_score > float(direction_score_max):
        fit_reasons.append(f"Direction score {direction_score:.1f} is above the replay-backed band cap of {float(direction_score_max):.1f}.")

    preferred_asset_class = str(preferred_filters.get("asset_class") or "").strip().lower()
    if preferred_asset_class and asset_class == preferred_asset_class:
        fit_reasons.append(f"Matches preferred asset class: {preferred_asset_class}.")

    preferred_market_regimes = _normalized_label_set(preferred_filters.get("market_regimes") or [])
    if preferred_market_regimes and market_regime in preferred_market_regimes:
        fit_reasons.append(f"Matches preferred market regime: {market_regime}.")

    preferred_sectors = _normalized_label_set(preferred_filters.get("sectors") or [])
    if preferred_sectors and sector.lower() in preferred_sectors:
        fit_reasons.append(f"Matches preferred sector: {sector}.")

    highlighted_tickers = _normalized_label_set(scan_policy.get("highlighted_tickers") or [])
    if ticker.lower() in highlighted_tickers:
        fit_reasons.append(f"{ticker} stood out in the replay, but single-name hits are treated as context rather than a hard filter.")

    promotion_class = str(classified.get("promotion_class") or annotated.get("promotion_class") or "").strip().lower()
    if promotion_class == "research_nearest_listed":
        fit_reasons.insert(0, "Research-only: replay profitability for this setup depends on nearest-listed contract substitution.")
    elif promotion_class == "research_sparse_calibration":
        fit_reasons.insert(0, "Research-only: replay calibration for this setup is still sparse and cannot approve trades.")
    elif promotion_class == "research_bootstrap":
        fit_reasons.insert(0, "Research-only: replay expectancy for this setup is still heuristic rather than dense empirical calibration.")

    if classified["decision"] == "watch" and promotion_status != "promote":
        fit_reasons.insert(0, f"Replay policy is still {promotion_status}-only, so qualifying trades stay on watch until stability improves.")
    elif classified["decision"] == "watch" and not fit_reasons:
        fit_reasons.append("Passes the replay-backed hard gate, but does not match the strongest preference slices.")

    annotated["market_regime"] = market_regime
    annotated["trade_policy_decision"] = classified["decision"]
    annotated["policy_fit_score"] = classified["fit_score"]
    annotated["policy_hard_failures"] = list(classified.get("hard_failures") or [])
    annotated["policy_fit_reasons"] = fit_reasons
    annotated["policy_promotion_status"] = promotion_status
    return annotated


def apply_trade_policy_to_scan(
    picks: list[dict[str, Any]],
    *,
    policy: dict[str, Any],
    include_blocked: bool = False,
) -> dict[str, Any]:
    decision_rank = {"approved": 2, "watch": 1, "blocked": 0}
    annotated = [annotate_pick_with_trade_policy(pick, policy) for pick in picks]
    counts = {"approved": 0, "watch": 0, "blocked": 0}
    for pick in annotated:
        decision = str(pick.get("trade_policy_decision") or "watch")
        counts[decision] = counts.get(decision, 0) + 1

    ranked = sorted(
        annotated,
        key=lambda pick: (
            decision_rank.get(str(pick.get("trade_policy_decision") or "watch"), 0),
            *_candidate_rank_tuple(pick),
            _watch_symbol_rank(pick, policy),
            float(pick.get("policy_fit_score", 0.0) or 0.0),
        ),
        reverse=True,
    )
    if not include_blocked:
        ranked = [pick for pick in ranked if pick.get("trade_policy_decision") != "blocked"]

    approved_picks = [pick for pick in ranked if pick.get("trade_policy_decision") == "approved"]
    watch_picks = [pick for pick in ranked if pick.get("trade_policy_decision") == "watch"]
    blocked_picks = [pick for pick in ranked if pick.get("trade_policy_decision") == "blocked"]

    return {
        "ranked_picks": ranked,
        "approved_picks": approved_picks,
        "watch_picks": watch_picks,
        "blocked_picks": blocked_picks,
        "candidate_count": len(annotated),
        "decision_counts": counts,
    }


def annotate_pick_with_guardrails(
    pick: dict[str, Any],
    *,
    playbook: dict[str, Any],
    exposure: dict[str, Any],
    enforce_portfolio_caps: bool = True,
) -> dict[str, Any]:
    annotated = dict(pick)
    ticker = str(annotated.get("ticker") or "").upper()
    sector = str(annotated.get("sector") or "").strip()
    market_regime = str(annotated.get("market_regime") or scan_pick_market_regime(annotated)).strip().lower()
    asset_class = str(annotated.get("asset_class") or "").strip().lower()
    direction = str(annotated.get("direction") or annotated.get("type") or "").strip().lower()
    candidate_execution_label = _pick_candidate_execution_label(annotated)
    quality_score = float(annotated.get("quality_score", 0.0) or 0.0)
    opened_today = int(exposure.get("opened_today", 0) or 0)
    ticker_counts = dict(exposure.get("ticker_counts") or {})
    sector_counts = dict(exposure.get("sector_counts") or {})
    regime_counts = dict(exposure.get("regime_counts") or {})
    vertical_spread_signature_counts = dict(exposure.get("vertical_spread_signature_counts") or {})
    playbook_id = str(playbook.get("id") or "").strip()
    is_ai_commodity_playbook = playbook_id == AI_COMMODITY_INFRA_OBSERVATION_COHORT_ID
    core_tickers = _normalized_label_set(playbook.get("core_tickers") or [])
    conditional_tickers = _normalized_label_set(playbook.get("conditional_tickers") or [])
    ai_commodity_bucket = ""
    if is_ai_commodity_playbook:
        if ticker.lower() in core_tickers:
            ai_commodity_bucket = "core_options"
        elif ticker.lower() in conditional_tickers:
            ai_commodity_bucket = "conditional_options"
        if ai_commodity_bucket:
            annotated["ai_commodity_bucket"] = ai_commodity_bucket

    blocked: list[str] = []
    cautions: list[str] = []
    annotated.update(_derive_convexity_profile(annotated))
    winner_fit_score, winner_fit_reasons = _tracked_winner_fit(annotated, playbook)
    if winner_fit_score:
        annotated["winner_profile_fit_score"] = winner_fit_score
        annotated["winner_profile_fit_reasons"] = winner_fit_reasons

    if enforce_portfolio_caps and not bool(exposure.get("available", True)):
        blocked.append("Portfolio guardrails failed closed because tracked-position storage is unavailable.")

    allowed_asset_classes = _normalized_label_set(playbook.get("allowed_asset_classes") or [])
    if allowed_asset_classes and asset_class not in allowed_asset_classes:
        blocked.append(f"{playbook['label']} only allows asset classes: {', '.join(sorted(allowed_asset_classes))}.")

    allowed_tickers = _normalized_label_set(playbook.get("allowed_tickers") or [])
    if allowed_tickers and ticker.lower() not in allowed_tickers:
        blocked.append(f"{playbook['label']} only runs on tickers: {', '.join(sorted(playbook.get('allowed_tickers') or []))}.")

    historical_data_ready_tickers = _normalized_label_set(playbook.get("historical_data_ready_tickers") or [])
    has_historical_readiness_context = bool(historical_data_ready_tickers) or is_ai_commodity_playbook
    if has_historical_readiness_context:
        annotated["historical_data_ready"] = ticker.lower() in historical_data_ready_tickers
        annotated["historical_data_source"] = playbook.get("historical_data_source")
        annotated["historical_data_readiness_status"] = playbook.get("historical_data_readiness_status")
        if ticker and not annotated["historical_data_ready"]:
            missing_history_reason = (
                f"{playbook['label']} has no trusted daily EOD option history loaded for {ticker} yet; "
                "treat this as discovery-only until Theta history is imported."
            )
            if is_ai_commodity_playbook and ai_commodity_bucket == "conditional_options":
                blocked.append(missing_history_reason)
            elif historical_data_ready_tickers:
                cautions.append(missing_history_reason)

    allowed_market_regimes = _normalized_label_set(playbook.get("allowed_market_regimes") or [])
    if allowed_market_regimes and market_regime not in allowed_market_regimes:
        blocked.append(f"{playbook['label']} only runs in {', '.join(sorted(allowed_market_regimes))} regimes.")

    allowed_sectors = _normalized_label_set(playbook.get("allowed_sectors") or [])
    if allowed_sectors and sector.lower() not in allowed_sectors:
        blocked.append(f"{playbook['label']} is restricted to sectors: {', '.join(sorted(playbook.get('allowed_sectors') or []))}.")

    allowed_directions = _normalized_label_set(playbook.get("allowed_directions") or [])
    if allowed_directions and direction not in allowed_directions:
        blocked.append(f"{playbook['label']} only allows directions: {', '.join(sorted(allowed_directions))}.")

    allowed_strategy_types = _normalized_label_set(playbook.get("allowed_strategy_types") or [])
    strategy_type = str(
        annotated.get("strategy_type")
        or ("vertical_spread" if annotated.get("short_strike") is not None else "")
    ).strip().lower()
    if allowed_strategy_types and strategy_type not in allowed_strategy_types:
        blocked.append(f"{playbook['label']} only allows strategies: {', '.join(sorted(allowed_strategy_types))}.")

    required_execution_label = str(playbook.get("required_candidate_execution_label") or "").strip().lower()
    if required_execution_label:
        annotated["required_candidate_execution_label"] = required_execution_label
        if candidate_execution_label != required_execution_label:
            blocked.append(
                f"{playbook['label']} requires {required_execution_label}; "
                f"candidate is {candidate_execution_label or 'unlabeled'}."
            )
    conditional_required_execution_label = str(
        playbook.get("conditional_required_candidate_execution_label") or ""
    ).strip().lower()
    if is_ai_commodity_playbook and ai_commodity_bucket == "conditional_options":
        annotated["conditional_required_candidate_execution_label"] = conditional_required_execution_label
        if conditional_required_execution_label and candidate_execution_label != conditional_required_execution_label:
            blocked.append(
                f"{playbook['label']} conditional tickers require {conditional_required_execution_label}; "
                f"candidate is {candidate_execution_label or 'unlabeled'}."
            )
    if is_ai_commodity_playbook:
        annotated["ai_commodity_diagnostics"] = {
            "bucket": ai_commodity_bucket or "unbucketed",
            "historical_data_ready": annotated.get("historical_data_ready"),
            "historical_data_readiness_status": playbook.get("historical_data_readiness_status"),
            "candidate_execution_label": candidate_execution_label or None,
            "required_candidate_execution_label": required_execution_label or None,
            "conditional_required_candidate_execution_label": conditional_required_execution_label or None,
        }

    min_quality_score = playbook.get("min_quality_score")
    if min_quality_score is not None and quality_score < float(min_quality_score):
        blocked.append(f"Quality score {quality_score:.1f} is below the {playbook['label']} minimum of {float(min_quality_score):.1f}.")

    max_debit_pct = playbook.get("max_debit_pct_of_width")
    if max_debit_pct is not None:
        (
            debit,
            debit_source,
            debit_source_is_ask_bid_style,
            debit_source_is_opra_executable,
            debit_source_execution_basis,
            debit_source_candidate_execution_label,
        ) = _debit_for_width(annotated)
        debit_pct = _debit_pct_of_width(annotated)
        annotated["debit_pct_of_width"] = debit_pct
        annotated["debit_pct_of_width_source"] = debit_source
        annotated["debit_pct_of_width_source_is_ask_bid_style"] = debit_source_is_ask_bid_style
        annotated["debit_pct_of_width_source_is_opra_executable"] = debit_source_is_opra_executable
        annotated["debit_pct_of_width_source_is_executable"] = debit_source_is_opra_executable
        annotated["debit_pct_of_width_source_execution_basis"] = debit_source_execution_basis
        annotated["debit_pct_of_width_source_candidate_execution_label"] = debit_source_candidate_execution_label
        if debit is not None:
            annotated["debit_pct_of_width_debit"] = debit
        if debit_pct is None:
            blocked.append(f"{playbook['label']} requires spread debit/width data before it can be tracked.")
        elif debit_pct >= float(max_debit_pct):
            blocked.append(
                f"Spread debit is {debit_pct:.1f}% of width, above the {playbook['label']} cap of {float(max_debit_pct):.1f}%."
            )

    repair_allowed_tickers = _normalized_label_set(playbook.get("profitability_repair_allowed_tickers") or [])
    if repair_allowed_tickers and ticker.lower() not in repair_allowed_tickers:
        blocked.append(
            f"{playbook['label']} profitability repair currently allows only: "
            f"{', '.join(sorted(playbook.get('profitability_repair_allowed_tickers') or []))}."
        )

    repair_excluded_tickers = _normalized_label_set(playbook.get("profitability_repair_excluded_tickers") or [])
    if repair_excluded_tickers and ticker.lower() in repair_excluded_tickers:
        blocked.append(f"{ticker} is quarantined for {playbook['label']} by the all-row profitability repair replay.")

    repair_max_debit_pct = playbook.get("profitability_repair_max_debit_pct_of_width")
    if repair_max_debit_pct is not None:
        repair_debit_pct = annotated.get("debit_pct_of_width")
        if repair_debit_pct is None:
            repair_debit_pct = _debit_pct_of_width(annotated)
            if repair_debit_pct is not None:
                annotated["debit_pct_of_width"] = repair_debit_pct
        if repair_debit_pct is not None and float(repair_debit_pct) > float(repair_max_debit_pct):
            blocked.append(
                f"Profitability repair blocks spread debit {float(repair_debit_pct):.1f}% of width "
                f"above {float(repair_max_debit_pct):.1f}%."
            )

    max_fill_degradation_pct = playbook.get("max_fill_degradation_vs_mid_pct")
    if max_fill_degradation_pct is not None:
        fill_degradation_pct = _fill_degradation_vs_mid_pct(annotated)
        if fill_degradation_pct is not None:
            annotated["fill_degradation_vs_mid_pct"] = fill_degradation_pct
            if fill_degradation_pct >= float(max_fill_degradation_pct):
                blocked.append(
                    f"Fill degradation versus midpoint is {fill_degradation_pct:.1f}%, "
                    f"above the repair cap of {float(max_fill_degradation_pct):.1f}%."
                )

    max_worst_leg_spread_pct = playbook.get("max_worst_leg_bid_ask_spread_pct")
    if max_worst_leg_spread_pct is not None:
        worst_leg_spread_pct = _worst_leg_bid_ask_spread_pct(annotated)
        if worst_leg_spread_pct is not None:
            annotated["worst_leg_bid_ask_spread_pct"] = worst_leg_spread_pct
            if worst_leg_spread_pct >= float(max_worst_leg_spread_pct):
                blocked.append(
                    f"Worst leg bid/ask spread is {worst_leg_spread_pct:.1f}%, "
                    f"above the repair cap of {float(max_worst_leg_spread_pct):.1f}%."
                )

    repair_min_ret5 = playbook.get("profitability_repair_min_ret5")
    if repair_min_ret5 is not None:
        entry_ret5 = _signal_ret5(annotated)
        if entry_ret5 is not None:
            annotated["profitability_repair_ret5"] = entry_ret5
            if entry_ret5 < float(repair_min_ret5):
                blocked.append(
                    f"Entry ret5 {entry_ret5:+.1f}% is below the {playbook['label']} repair floor "
                    f"of {float(repair_min_ret5):+.1f}%."
                )

    if playbook.get("require_speculative_flag") and not bool(annotated.get("speculative_flag")):
        blocked.append(f"{playbook['label']} only surfaces high-convexity setups rated speculative on the risk/upside scale.")

    if enforce_portfolio_caps and playbook.get("block_same_ticker") and ticker and int(ticker_counts.get(ticker, 0) or 0) > 0:
        blocked.append(f"An open tracked position already exists in {ticker}.")

    spread_signature = vertical_spread_signature(annotated)
    if (
        enforce_portfolio_caps
        and spread_signature is not None
        and int(vertical_spread_signature_counts.get(repr(spread_signature), 0) or 0) > 0
    ):
        blocked.append("An open tracked position already has this exact vertical spread.")

    correlation_size_mult = 1.0
    if enforce_portfolio_caps:
        max_new_positions_per_day = int(playbook.get("max_new_positions_per_day", 2) or 2)
        if opened_today >= max_new_positions_per_day:
            blocked.append(
                f"Playbook daily cap reached: {opened_today} new position(s) already opened today against a {max_new_positions_per_day}-position limit."
            )
        elif opened_today == max_new_positions_per_day - 1 and max_new_positions_per_day > 1:
            cautions.append("This trade would fill the last new-position slot for today in the current playbook.")

        max_sector_open_positions = int(playbook.get("max_sector_open_positions", 1) or 1)
        current_sector_count = int(sector_counts.get(sector, 0) or 0) if sector else 0
        if sector and current_sector_count >= max_sector_open_positions:
            blocked.append(f"Sector cap reached for {sector}: {current_sector_count} open position(s) against a {max_sector_open_positions}-position limit.")
        elif sector and current_sector_count == max_sector_open_positions - 1 and max_sector_open_positions > 1:
            cautions.append(f"{sector} is one trade away from the current sector cap.")

        max_regime_open_positions = int(playbook.get("max_regime_open_positions", 2) or 2)
        current_regime_count = int(regime_counts.get(market_regime, 0) or 0) if market_regime else 0
        if market_regime and market_regime != "unknown" and current_regime_count >= max_regime_open_positions:
            blocked.append(
                f"Regime cap reached for {market_regime}: {current_regime_count} open position(s) against a {max_regime_open_positions}-position limit."
            )
        elif (
            market_regime
            and market_regime != "unknown"
            and current_regime_count == max_regime_open_positions - 1
            and max_regime_open_positions > 1
        ):
            cautions.append(f"{market_regime.title()} regime exposure is near the current cap.")

        # --- Daily / weekly loss limits ---
        account_size = float(playbook.get("account_size") or 10_000)
        daily_loss_limit_pct = float(playbook.get("daily_loss_limit_pct", 2.0) or 2.0)
        weekly_loss_limit_pct = float(playbook.get("weekly_loss_limit_pct", 5.0) or 5.0)
        daily_realized_pnl = float(exposure.get("daily_realized_pnl_usd", 0.0) or 0.0)
        weekly_realized_pnl = float(exposure.get("weekly_realized_pnl_usd", 0.0) or 0.0)
        daily_limit_usd = account_size * daily_loss_limit_pct / 100.0
        weekly_limit_usd = account_size * weekly_loss_limit_pct / 100.0
        if daily_realized_pnl < 0 and abs(daily_realized_pnl) >= daily_limit_usd:
            blocked.append(f"Daily loss limit reached: ${abs(daily_realized_pnl):.2f} lost today against ${daily_limit_usd:.2f} cap ({daily_loss_limit_pct}%).")
        if weekly_realized_pnl < 0 and abs(weekly_realized_pnl) >= weekly_limit_usd:
            blocked.append(f"Weekly loss limit reached: ${abs(weekly_realized_pnl):.2f} lost this week against ${weekly_limit_usd:.2f} cap ({weekly_loss_limit_pct}%).")

        # --- Capital at risk ---
        cost_risk = _position_cost_risk_usd(annotated)
        open_cost_risk = float(exposure.get("open_cost_risk_usd", 0.0) or 0.0)
        max_position_cost_risk_pct = float(playbook.get("max_position_cost_risk_pct", 0.0) or 0.0)
        max_portfolio_cost_risk_pct = float(playbook.get("max_portfolio_cost_risk_pct", 0.0) or 0.0)
        if cost_risk is not None and max_position_cost_risk_pct > 0:
            position_cap_usd = account_size * max_position_cost_risk_pct / 100.0
            if cost_risk > position_cap_usd:
                blocked.append(
                    f"Position cost risk ${cost_risk:.2f} exceeds the playbook per-position cap ${position_cap_usd:.2f} ({max_position_cost_risk_pct}%)."
                )
        if cost_risk is not None and max_portfolio_cost_risk_pct > 0:
            portfolio_cap_usd = account_size * max_portfolio_cost_risk_pct / 100.0
            if open_cost_risk + cost_risk > portfolio_cap_usd:
                blocked.append(
                    f"Portfolio cost risk would be ${open_cost_risk + cost_risk:.2f}, above the playbook cap ${portfolio_cap_usd:.2f} ({max_portfolio_cost_risk_pct}%)."
                )

        # --- Max concurrent positions ---
        max_concurrent = int(playbook.get("max_concurrent_positions", 3) or 3)
        total_open = int(exposure.get("open_positions", 0) or 0)
        if total_open >= max_concurrent:
            blocked.append(f"Max concurrent positions ({max_concurrent}) reached: {total_open} position(s) currently open.")

        # --- Correlated index positions ---
        max_correlated = int(playbook.get("max_correlated_index_positions", 1) or 1)
        correlated_count = int(exposure.get("correlated_index_count", 0) or 0)
        if ticker in CORRELATED_INDEXES and correlated_count >= max_correlated:
            blocked.append(f"Correlated index limit ({max_correlated}) reached: {correlated_count} index position(s) already open across {', '.join(sorted(CORRELATED_INDEXES))}.")

        # Correlation guard: reduce size when same sector + same direction is already concentrated
        sector_direction_counts = dict(exposure.get("sector_direction_counts") or {})
        if sector and direction in {"call", "put"}:
            sd_key = f"{sector}|{direction}"
            same_sector_direction_count = int(sector_direction_counts.get(sd_key, 0) or 0)
            if same_sector_direction_count >= 2:
                correlation_size_mult = 0.5
                cautions.append(
                    f"Correlated exposure: {same_sector_direction_count} open {direction}(s) already in {sector}. "
                    f"Suggested size reduced by 50%."
                )
    annotated["correlation_size_mult"] = correlation_size_mult
    # Apply correlation adjustment to position size recommendation
    if correlation_size_mult < 1.0 and "position_size_mult" in annotated:
        annotated["position_size_mult"] = round(
            float(annotated.get("position_size_mult", 1.0)) * correlation_size_mult, 3
        )

    guardrail_decision = "blocked" if blocked else ("caution" if cautions else "clear")
    policy_decision = str(annotated.get("trade_policy_decision") or "").strip().lower()
    if guardrail_decision == "blocked":
        suggested_size_tier = "blocked"
        suggested_size_reason = "Do not add this trade while the current playbook guardrails are blocking it."
    elif str(playbook.get("forced_size_tier") or "").strip().lower() in {"starter", "half", "full"}:
        suggested_size_tier = str(playbook.get("forced_size_tier")).strip().lower()
        suggested_size_reason = "This playbook is intentionally capped at starter size while it builds separate forward evidence."
    elif policy_decision == "watch":
        suggested_size_tier = "starter"
        suggested_size_reason = "Watch-tier trades default to starter size until the cohort proves itself further."
    elif guardrail_decision == "caution":
        suggested_size_tier = "starter" if playbook["id"] == "short_term" else "half"
        suggested_size_reason = "Existing exposure is close to a playbook cap, so keep the new trade smaller."
    else:
        suggested_size_tier = "half" if playbook["id"] == "short_term" else "full"
        suggested_size_reason = "The trade cleared the current playbook and portfolio guardrails."

    annotated["playbook_id"] = playbook["id"]
    annotated["playbook_label"] = playbook["label"]
    annotated["guardrail_decision"] = guardrail_decision
    annotated["guardrail_reasons"] = blocked if blocked else cautions
    annotated["suggested_size_tier"] = suggested_size_tier
    annotated["suggested_size_reason"] = suggested_size_reason
    forced_cohort_id = str(playbook.get("forced_cohort_id") or "").strip()
    if forced_cohort_id and ticker and direction:
        forced_profit_candidate_id = _candidate_profit_id(ticker, direction, forced_cohort_id)
        annotated["profit_candidate_id"] = forced_profit_candidate_id
        annotated["policy_artifact_id"] = forced_profit_candidate_id
        annotated["cohort_id"] = forced_cohort_id
        annotated["cohort_role"] = str(playbook.get("forced_cohort_role") or "candidate").strip()
    return annotated


def apply_playbook_guardrails(
    picks: list[dict[str, Any]],
    *,
    playbook: dict[str, Any],
    positions_repository: Any,
    policy: Optional[dict[str, Any]] = None,
    include_blocked: bool = False,
    enforce_portfolio_caps: bool = True,
) -> dict[str, Any]:
    exposure = load_open_position_context(positions_repository)
    annotated = [
        annotate_pick_with_guardrails(
            pick,
            playbook=playbook,
            exposure=exposure,
            enforce_portfolio_caps=enforce_portfolio_caps,
        )
        for pick in picks
    ]
    preliminary_ranked = sorted(
        annotated,
        key=lambda pick: (
            float(pick.get("winner_profile_fit_score", 0.0) or 0.0),
            *_candidate_rank_tuple(pick),
        ),
        reverse=True,
    )
    seen_scan_spreads: set[str] = set()
    seen_scan_tickers: dict[str, int] = {}
    max_scan_picks_per_ticker = int(
        playbook.get(
            "max_scan_picks_per_ticker",
            1 if bool(playbook.get("block_same_ticker")) else len(preliminary_ranked) or 1,
        )
        or 1
    )
    batch_annotated_by_id: dict[int, dict[str, Any]] = {}
    for pick in preliminary_ranked:
        next_pick = pick
        ticker = str(pick.get("ticker") or "").strip().upper()
        if enforce_portfolio_caps and str(next_pick.get("guardrail_decision") or "clear") != "blocked":
            spread_signature = vertical_spread_signature(next_pick)
            spread_key = repr(spread_signature) if spread_signature is not None else None
            if spread_key and spread_key in seen_scan_spreads:
                next_pick = _block_guardrail_pick(next_pick, "This scan already selected the same exact vertical spread.")
            elif ticker and int(seen_scan_tickers.get(ticker, 0) or 0) >= max_scan_picks_per_ticker:
                next_pick = _block_guardrail_pick(next_pick, f"This scan already selected {ticker}; same-scan ticker cap is {max_scan_picks_per_ticker}.")
            else:
                if spread_key:
                    seen_scan_spreads.add(spread_key)
                if ticker:
                    seen_scan_tickers[ticker] = int(seen_scan_tickers.get(ticker, 0) or 0) + 1
        batch_annotated_by_id[id(pick)] = next_pick
    annotated = [batch_annotated_by_id.get(id(pick), pick) for pick in annotated]
    counts = {"clear": 0, "caution": 0, "blocked": 0}
    for pick in annotated:
        decision = str(pick.get("guardrail_decision") or "clear")
        counts[decision] = counts.get(decision, 0) + 1

    rank = {"clear": 2, "caution": 1, "blocked": 0}
    size_rank = {"full": 3, "half": 2, "starter": 1, "blocked": 0}
    all_ranked = sorted(
        annotated,
        key=lambda pick: (
            rank.get(str(pick.get("guardrail_decision") or "clear"), 0),
            size_rank.get(str(pick.get("suggested_size_tier") or "starter"), 0),
            float(pick.get("winner_profile_fit_score", 0.0) or 0.0),
            *_candidate_rank_tuple(pick),
            _watch_symbol_rank(pick, policy),
            float(pick.get("policy_fit_score", 0.0) or 0.0),
        ),
        reverse=True,
    )
    ranked = list(all_ranked)
    if include_blocked:
        ranked = sorted(
            ranked,
            key=lambda pick: (
                rank.get(str(pick.get("guardrail_decision") or "clear"), 0),
                size_rank.get(str(pick.get("suggested_size_tier") or "starter"), 0),
                float(pick.get("winner_profile_fit_score", 0.0) or 0.0),
                *_candidate_rank_tuple(pick),
                _watch_symbol_rank(pick, policy),
                float(pick.get("policy_fit_score", 0.0) or 0.0),
            ),
            reverse=True,
        )
    else:
        ranked = [pick for pick in ranked if pick.get("guardrail_decision") != "blocked"]

    exposure_snapshot = {
        "available": bool(exposure.get("available", True)),
        "open_positions": exposure["open_positions"],
        "opened_today": exposure["opened_today"],
        "ticker_counts": exposure["ticker_counts"],
        "sector_counts": exposure["sector_counts"],
        "regime_counts": exposure["regime_counts"],
        "sector_direction_counts": exposure.get("sector_direction_counts", {}),
        "vertical_spread_signature_counts": exposure.get("vertical_spread_signature_counts", {}),
        "open_cost_risk_usd": exposure.get("open_cost_risk_usd", 0.0),
        "warnings": exposure["warnings"],
        "portfolio_caps_enforced": bool(enforce_portfolio_caps),
    }

    return {
        "ranked_picks": ranked,
        "all_ranked_picks": all_ranked,
        "guardrail_counts": counts,
        "exposure_snapshot": exposure_snapshot,
    }


def _build_scan_funnel(
    *,
    raw_candidate_count: int,
    post_policy_visible_count: int,
    post_guardrail_visible_count: int,
    returned_count: int,
    policy_counts: Optional[dict[str, Any]] = None,
    guardrail_counts: Optional[dict[str, Any]] = None,
    policy_applied: bool,
    policy_fail_closed: bool,
    include_blocked_policy_picks: bool,
    include_blocked_guardrail_picks: bool,
    drop_counts: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    normalized_policy_counts = {
        "approved": int((policy_counts or {}).get("approved") or 0),
        "watch": int((policy_counts or {}).get("watch") or 0),
        "blocked": int((policy_counts or {}).get("blocked") or 0),
    }
    normalized_guardrail_counts = {
        "clear": int((guardrail_counts or {}).get("clear") or 0),
        "caution": int((guardrail_counts or {}).get("caution") or 0),
        "blocked": int((guardrail_counts or {}).get("blocked") or 0),
    }
    raw_candidates = max(int(raw_candidate_count or 0), 0)
    post_policy_visible = max(int(post_policy_visible_count or 0), 0)
    post_guardrails_visible = max(int(post_guardrail_visible_count or 0), 0)
    returned_picks = max(int(returned_count or 0), 0)
    normalized_drop_counts = _normalized_scan_drop_counts(drop_counts)
    normalized_drop_counts["guardrails"] += max(post_policy_visible - post_guardrails_visible, 0)
    return {
        "raw_candidates": raw_candidates,
        "post_policy_visible": post_policy_visible,
        "post_guardrails_visible": post_guardrails_visible,
        "returned_picks": returned_picks,
        "policy_filtered_out": max(raw_candidates - post_policy_visible, 0),
        "guardrail_filtered_out": max(post_policy_visible - post_guardrails_visible, 0),
        "final_trimmed": max(post_guardrails_visible - returned_picks, 0),
        "policy_counts": normalized_policy_counts,
        "guardrail_counts": normalized_guardrail_counts,
        "policy_applied": bool(policy_applied),
        "policy_fail_closed": bool(policy_fail_closed),
        "include_blocked_policy_picks": bool(include_blocked_policy_picks),
        "include_blocked_guardrail_picks": bool(include_blocked_guardrail_picks),
        "drop_counts": normalized_drop_counts,
    }


def run_supervised_scan(
    *,
    scan_func: Callable[..., list[dict[str, Any]]],
    positions_repository: Any,
    n_picks: int,
    watchlist_size: int,
    playbook_id: Optional[str] = None,
    use_recommended_policy: bool = False,
    include_blocked_policy_picks: bool = False,
    include_blocked_guardrail_picks: bool = False,
    truth_lane: Optional[str] = None,
    min_trades: int = 20,
    max_tickers: int = 8,
    max_sectors: int = 8,
    min_profit_factor: float = 1.05,
    min_directional_accuracy_pct: float = 50.0,
    enforce_portfolio_caps: bool = True,
) -> dict[str, Any]:
    playbook = get_scan_playbook(playbook_id)
    data_readiness_diagnostics = _data_readiness_diagnostics_for_playbook(playbook)
    scan_dte = int(playbook["target_dte"])
    playbook_scan_symbols = _scan_symbols_for_playbook(playbook)
    scan_pool_size = max(int(n_picks), int(watchlist_size), len(playbook_scan_symbols))
    scan_kwargs: dict[str, Any] = {
        "n_picks": scan_pool_size,
        "dte": scan_dte,
        "calibration_playbook": str(playbook.get("calibration_playbook") or "broad"),
        "positions_repository": positions_repository,
    }
    playbook_allowed_directions = _scan_allowed_directions_for_playbook(playbook)
    if playbook_allowed_directions and _callable_accepts_keyword(scan_func, "allowed_directions"):
        scan_kwargs["allowed_directions"] = playbook_allowed_directions
    if playbook_scan_symbols and _callable_accepts_keyword(scan_func, "symbols"):
        scan_kwargs["symbols"] = playbook_scan_symbols
    if playbook.get("signal_variant") and _callable_accepts_keyword(scan_func, "signal_variant"):
        scan_kwargs["signal_variant"] = str(playbook.get("signal_variant"))
    if playbook.get("scan_min_confidence") is not None and _callable_accepts_keyword(scan_func, "min_confidence"):
        scan_kwargs["min_confidence"] = float(playbook.get("scan_min_confidence"))
    if playbook.get("scan_min_tech_score") is not None and _callable_accepts_keyword(scan_func, "min_tech_score"):
        scan_kwargs["min_tech_score"] = float(playbook.get("scan_min_tech_score"))
    raw_picks = list(scan_func(**scan_kwargs))
    scan_drop_counts = _normalized_scan_drop_counts(getattr(scan_func, "_last_scan_drop_counts", None))
    scan_drop_reasons = dict(getattr(scan_func, "_last_scan_drop_reasons", {}) or {})
    candidate_count = len(raw_picks)

    policy = None
    policy_error = None
    policy_result = None
    ranked_for_guardrails = list(raw_picks)
    exit_audit = None
    exit_audit_error = None

    if use_recommended_policy:
        preferred_result = load_preferred_results_by_truth_lane(truth_lane or LIVE_SCAN_TRUTH_LANE)
        policy = build_live_options_trade_policy(
            result=preferred_result,
            truth_lane=truth_lane or LIVE_SCAN_TRUTH_LANE,
            min_trades=int(min_trades),
            max_tickers=int(max_tickers),
            max_sectors=int(max_sectors),
            min_profit_factor=float(min_profit_factor),
            min_directional_accuracy_pct=float(min_directional_accuracy_pct),
        )
        exit_audit = build_playbook_exit_audit(
            result=preferred_result,
            policy_bundle=policy,
            playbook=str(playbook.get("id") or DEFAULT_SCAN_PLAYBOOK_ID),
            truth_lane=truth_lane or LIVE_SCAN_TRUTH_LANE,
            min_trades=int(min_trades),
            max_tickers=int(max_tickers),
            max_sectors=int(max_sectors),
            min_profit_factor=float(min_profit_factor),
            min_directional_accuracy_pct=float(min_directional_accuracy_pct),
        )
        if exit_audit.get("error"):
            exit_audit_error = exit_audit.get("error")
            exit_audit = None
            scan_funnel = _build_scan_funnel(
                raw_candidate_count=candidate_count,
                post_policy_visible_count=0,
                post_guardrail_visible_count=0,
                returned_count=0,
                policy_counts={"approved": 0, "watch": 0, "blocked": candidate_count},
                guardrail_counts={"clear": 0, "caution": 0, "blocked": 0},
                policy_applied=False,
                policy_fail_closed=True,
                include_blocked_policy_picks=include_blocked_policy_picks,
                include_blocked_guardrail_picks=include_blocked_guardrail_picks,
                drop_counts=scan_drop_counts,
            )
            return {
                "picks": [],
                "watch_picks": [],
                "ranked_picks": [],
                "policy_applied": False,
                "policy_error": str(exit_audit_error),
                "policy_fail_closed": True,
                "policy": None,
                "playbook_exit_audit": None,
                "playbook_exit_audit_error": exit_audit_error,
                "policy_decision_counts": {"approved": 0, "watch": 0, "blocked": 0},
                "guardrail_decision_counts": {"clear": 0, "caution": 0, "blocked": 0},
                "exposure_snapshot": load_open_position_context(positions_repository),
                "candidate_count": candidate_count,
                "returned_count": 0,
                "scan_funnel": scan_funnel,
                "scan_drop_reasons": scan_drop_reasons,
                "data_readiness": data_readiness_diagnostics,
                "playbook": playbook,
                "playbooks": get_scan_playbooks(),
                "truth_lane": truth_lane or LIVE_SCAN_TRUTH_LANE,
                "truth_window_status": "unknown",
                "managed_lane_status": None,
                "authoritative_evidence_source": None,
                "authoritative_evidence_status": None,
                "watch_priority_symbols": [],
                "watch_deprioritized_symbols": [],
            }
        if policy.get("error"):
            policy_error = str(policy.get("error"))
            scan_funnel = _build_scan_funnel(
                raw_candidate_count=candidate_count,
                post_policy_visible_count=0,
                post_guardrail_visible_count=0,
                returned_count=0,
                policy_counts={"approved": 0, "watch": 0, "blocked": candidate_count},
                guardrail_counts={"clear": 0, "caution": 0, "blocked": 0},
                policy_applied=False,
                policy_fail_closed=True,
                include_blocked_policy_picks=include_blocked_policy_picks,
                include_blocked_guardrail_picks=include_blocked_guardrail_picks,
                drop_counts=scan_drop_counts,
            )
            return {
                "picks": [],
                "watch_picks": [],
                "ranked_picks": [],
                "policy_applied": False,
                "policy_error": policy_error,
                "policy_fail_closed": True,
                "policy": None,
                "playbook_exit_audit": exit_audit,
                "playbook_exit_audit_error": exit_audit_error,
                "policy_decision_counts": {"approved": 0, "watch": 0, "blocked": 0},
                "guardrail_decision_counts": {"clear": 0, "caution": 0, "blocked": 0},
                "exposure_snapshot": load_open_position_context(positions_repository),
                "candidate_count": candidate_count,
                "returned_count": 0,
                "scan_funnel": scan_funnel,
                "scan_drop_reasons": scan_drop_reasons,
                "data_readiness": data_readiness_diagnostics,
                "playbook": playbook,
                "playbooks": get_scan_playbooks(),
                "truth_lane": truth_lane or LIVE_SCAN_TRUTH_LANE,
                "truth_window_status": "unknown",
                "managed_lane_status": None,
                "authoritative_evidence_source": None,
                "authoritative_evidence_status": None,
                "watch_priority_symbols": [],
                "watch_deprioritized_symbols": [],
            }

        policy_result = apply_trade_policy_to_scan(
            raw_picks,
            policy=policy,
            include_blocked=include_blocked_policy_picks,
        )
        ranked_for_guardrails = list(policy_result["ranked_picks"])

    guardrail_result = apply_playbook_guardrails(
        ranked_for_guardrails,
        playbook=playbook,
        positions_repository=positions_repository,
        policy=policy,
        include_blocked=include_blocked_guardrail_picks,
        enforce_portfolio_caps=enforce_portfolio_caps,
    )
    ranked_picks = list(guardrail_result["ranked_picks"])
    candidate_audit_picks = list(guardrail_result.get("all_ranked_picks") or ranked_picks)
    truth_window_status = str((policy or {}).get("truth_window_status") or "unknown").strip().lower() or "unknown"
    managed_lane_status = (policy or {}).get("managed_lane_status")
    authoritative_evidence_source = (policy or {}).get("authoritative_evidence_source")
    authoritative_evidence_status = (policy or {}).get("authoritative_evidence_status")
    watch_priority_symbols = list((policy or {}).get("watch_priority_symbols") or [])
    watch_deprioritized_symbols = list((policy or {}).get("watch_deprioritized_symbols") or [])

    if use_recommended_policy and policy is not None:
        ranked_picks = [_annotate_managed_pick(pick, policy) for pick in ranked_picks]
        candidate_audit_picks = [_annotate_managed_pick(pick, policy) for pick in candidate_audit_picks]
        approved_picks = [
            pick for pick in ranked_picks
            if pick.get("managed_lane_decision") == "approved"
        ][: max(int(n_picks), 0)]
        watch_picks = sorted(
            [
                pick for pick in ranked_picks
                if pick.get("managed_lane_decision") == "watch"
            ],
            key=lambda pick: (
                _watch_symbol_rank(pick, policy),
                *_candidate_rank_tuple(pick),
                float(pick.get("policy_fit_score", 0.0) or 0.0),
            ),
            reverse=True,
        )
        final_picks = approved_picks
    else:
        ranked_picks = [_annotate_managed_pick(pick, None) for pick in ranked_picks]
        candidate_audit_picks = [_annotate_managed_pick(pick, None) for pick in candidate_audit_picks]
        final_picks = ranked_picks[: max(int(n_picks), 0)]
        watch_picks = []
    scan_funnel = _build_scan_funnel(
        raw_candidate_count=candidate_count,
        post_policy_visible_count=len(ranked_for_guardrails),
        post_guardrail_visible_count=len(ranked_picks),
        returned_count=len(final_picks),
        policy_counts=(policy_result or {}).get("decision_counts"),
        guardrail_counts=guardrail_result["guardrail_counts"],
        policy_applied=bool(use_recommended_policy and policy is not None),
        policy_fail_closed=False,
        include_blocked_policy_picks=include_blocked_policy_picks,
        include_blocked_guardrail_picks=include_blocked_guardrail_picks,
        drop_counts=scan_drop_counts,
    )

    return {
        "picks": final_picks,
        "watch_picks": watch_picks,
        "ranked_picks": ranked_picks,
        "candidate_audit_picks": candidate_audit_picks,
        "policy_applied": bool(use_recommended_policy and policy is not None),
        "policy_error": policy_error,
        "policy_fail_closed": False,
        "policy": policy,
        "playbook_exit_audit": exit_audit,
        "playbook_exit_audit_error": exit_audit_error,
        "policy_decision_counts": (policy_result or {}).get("decision_counts"),
        "guardrail_decision_counts": guardrail_result["guardrail_counts"],
        "exposure_snapshot": guardrail_result["exposure_snapshot"],
        "candidate_count": candidate_count,
        "returned_count": len(final_picks),
        "scan_funnel": scan_funnel,
        "scan_drop_reasons": scan_drop_reasons,
        "data_readiness": data_readiness_diagnostics,
        "playbook": playbook,
        "playbooks": get_scan_playbooks(),
        "truth_lane": truth_lane or LIVE_SCAN_TRUTH_LANE,
        "truth_window_status": truth_window_status,
        "managed_lane_status": managed_lane_status,
        "authoritative_evidence_source": authoritative_evidence_source,
        "authoritative_evidence_status": authoritative_evidence_status,
        "watch_priority_symbols": watch_priority_symbols,
        "watch_deprioritized_symbols": watch_deprioritized_symbols,
    }
