from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from exact_contract_accounting import is_exact_contract_resolution, trade_contract_resolution

from ai_commodity_universe import (
    ai_commodity_scan_tickers,
)
from scripts.quote_evidence_readback import non_production_research_policy, quote_evidence_readback

DEFAULT_TRACKED_DB = ROOT / "data" / "tracked_positions.db"
DEFAULT_HISTORICAL_RUN = ROOT / "data" / "options-validation" / "runs" / "latest_daily.json"
DEFAULT_PAID_DATA_READINESS = ROOT / "data" / "profitability-lab" / "paid-data-readiness" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "lane-lab"
AI_COMMODITY_MIN_SHARED_QUOTE_DATES = 100


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.expanduser().resolve() == right.expanduser().resolve()
    except OSError:
        return left.expanduser() == right.expanduser()


def lane_lab_evidence_policy(
    *,
    tracked_db: Path,
    historical_run: Path,
    readiness_path: Path,
    readiness_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    readiness_quote = (
        readiness_payload.get("quote_evidence")
        if isinstance(readiness_payload, dict) and isinstance(readiness_payload.get("quote_evidence"), dict)
        else None
    )
    default_tracked_db = _same_path(Path(tracked_db), DEFAULT_TRACKED_DB)
    default_historical_run = _same_path(Path(historical_run), DEFAULT_HISTORICAL_RUN)
    quote_evidence = readiness_quote or quote_evidence_readback(
        snapshot_kind="daily_eod" if default_historical_run else None,
        source_label="historical_imported_daily" if default_historical_run else None,
        trusted_only=None,
    )
    policy = non_production_research_policy(
        record_class="lane_lab_research_readback",
        quote_evidence=quote_evidence,
    )
    policy.update(
        {
            "source_quality": "legacy_research_only"
            if default_tracked_db or default_historical_run
            else "explicit_research_inputs",
            "production_proof_eligible": False,
            "allowed_use": "lane_design_and_research_planning_only",
            "tracked_db_role": "legacy_paper_or_test_double" if default_tracked_db else "explicit_input",
            "historical_run_role": "legacy_daily_replay_artifact" if default_historical_run else "explicit_input",
            "readiness_source_role": "readiness_readback_not_row_proof",
            "legacy_default_sources": {
                "tracked_db": default_tracked_db,
                "historical_run": default_historical_run,
            },
            "source_paths": {
                "tracked_db": str(Path(tracked_db)),
                "historical_run": str(Path(historical_run)),
                "paid_data_readiness": str(Path(readiness_path)),
            },
        }
    )
    return policy


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def profit_factor(values: Iterable[float]) -> float:
    vals = [float(value) for value in values]
    gross_profit = sum(value for value in vals if value > 0)
    gross_loss = -sum(value for value in vals if value < 0)
    if gross_loss > 0:
        return round(gross_profit / gross_loss, 2)
    if gross_profit > 0:
        return 999.0
    return 0.0


def summarize_pnl_values(values: Iterable[float]) -> dict[str, Any]:
    vals = [float(value) for value in values]
    count = len(vals)
    winners = [value for value in vals if value > 0]
    losers = [value for value in vals if value < 0]
    return {
        "count": count,
        "winner_count": len(winners),
        "loser_count": len(losers),
        "win_rate_pct": round(len(winners) / count * 100.0, 1) if count else 0.0,
        "avg_pnl_pct": round(sum(vals) / count, 2) if count else 0.0,
        "profit_factor": profit_factor(vals),
        "best_pnl_pct": round(max(vals), 2) if vals else None,
        "worst_pnl_pct": round(min(vals), 2) if vals else None,
    }


def debit_pct(row: dict[str, Any]) -> float | None:
    explicit = row.get("debit_pct_of_width")
    if explicit is not None:
        return safe_num(explicit)
    width = safe_num(row.get("spread_width"))
    if width <= 0:
        return None
    return safe_num(row.get("net_debit")) / width * 100.0


def classify_debit_bucket(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 40:
        return "cheap_lt40"
    if value < 50:
        return "cheap_40_49"
    if value < 55:
        return "mid_50_54"
    if value < 75:
        return "high_55_74"
    return "expensive_75_plus"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf8"))


def _safe_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _position_pnl_pct(row: dict[str, Any]) -> float:
    return safe_num(row.get("net_pnl_pct", row.get("last_pnl_pct")))


def lane_definitions() -> list[dict[str, Any]]:
    return [
        {
            "id": "fill_discipline",
            "tier": 1,
            "priority": 1,
            "title": "Fill-Discipline Wrapper",
            "hypothesis": "Current signals become more trustworthy when only single-spread limit fills with bounded slippage are counted.",
            "structure": "Wrapper around existing approved/watch vertical candidates.",
            "test": "Log signal candidates and actual fillable candidates side-by-side; require two-sided leg quotes and spread_ask_bid execution.",
            "pass_fail": "Pass with 30 filled paper trades, average fill degradation under 10% of debit, positive net expectancy, and missed-fill rate under 40%.",
            "risks": ["May miss big winners.", "Paper fills remain optimistic without timestamped quotes."],
            "data_requirements": ["leg bid/ask", "quote timestamp", "spread mid", "attempted limit", "filled/not filled"],
            "evaluator": "current_paper_book_partial",
        },
        {
            "id": "liquidity_first_spread",
            "tier": 1,
            "priority": 2,
            "title": "Liquidity-First Spread Selection",
            "hypothesis": "For the same thesis, the most closable spread can beat the best-looking theoretical spread.",
            "structure": "Wrapper around current vertical candidates; rank contract alternatives by liquidity.",
            "test": "Persist top 3 spreads per candidate and paper selected liquidity-first spread versus current selected spread.",
            "pass_fail": "Pass with 40 opportunities, lower slippage/failed exits, and equal or better net expectancy.",
            "risks": ["Can sacrifice convexity.", "Can bias toward expensive ATM spreads."],
            "data_requirements": ["candidate spread alternatives", "OI", "volume", "bid/ask", "quote age"],
            "evaluator": "instrumentation_blocked",
        },
        {
            "id": "high_debit_control",
            "tier": 1,
            "priority": 3,
            "title": "High-Debit Avoidance Control",
            "hypothesis": "Expensive debit verticals above 55% of width underperform cheap debit verticals.",
            "structure": "Control lane for otherwise similar debit verticals.",
            "test": "Compare cheap debit buckets against high-debit buckets in historical replay and paper shadow logs.",
            "pass_fail": "Cheap buckets should beat high-debit buckets on avg P&L, PF, and drawdown over 25+ trades.",
            "risks": ["High-debit spreads may have higher win rate but worse payoff.", "Small samples can mislead."],
            "data_requirements": ["net_debit", "spread_width", "net_pnl_pct"],
            "evaluator": "historical_debit_control",
        },
        {
            "id": "gld_macro_breakout",
            "tier": 1,
            "priority": 4,
            "title": "GLD Real-Rate / Flight-to-Safety",
            "hypothesis": "Gold ETF breakouts create a non-equity beta lane distinct from current tech/index call exposure.",
            "structure": "GLD 30-45 DTE directional debit spreads, debit <= 40% width.",
            "test": "Daily-close breakout/breakdown paper log; no intraday chasing.",
            "pass_fail": "Pass with PF >= 1.20, positive avg net P&L, median loser below 45% debit.",
            "risks": ["Macro gaps.", "Wider options spreads away from front expiries."],
            "data_requirements": ["GLD option history", "GLD OHLCV", "IV rank", "DXY/TLT proxy"],
            "required_symbols": ["GLD"],
            "evaluator": "symbol_data_readiness",
        },
        {
            "id": "relative_strength_pullback",
            "tier": 1,
            "priority": 5,
            "title": "Relative Strength Pullback",
            "hypothesis": "Strong names outperforming SPY produce better entries after controlled pullbacks than after momentum chase.",
            "structure": "14-30 DTE calls or call spreads; score underlying move first.",
            "test": "Require 20-day relative strength vs SPY >= 4%, rising SMA50, RSI14 42-58, and 3-day pullback.",
            "pass_fail": "Pass with 40 trades, underlying win rate >= 55%, avg underlying return >= 0.8%, option expectancy > 8%.",
            "risks": ["Pullback can become trend failure.", "Overlaps current bullish style if filters are loose."],
            "data_requirements": ["relative strength", "RSI", "SMA20/50", "earnings calendar", "option chain"],
            "evaluator": "paper_log_pending",
        },
        {
            "id": "tlt_duration_shock",
            "tier": 2,
            "priority": 6,
            "title": "TLT Duration Shock / Rate-Reversal",
            "hypothesis": "Bond ETF options can diversify when equity call lanes are blocked.",
            "structure": "TLT 30-60 DTE debit spreads after rate-relief or rate-spike signals.",
            "test": "Split event-excluded and event-included cohorts; judge separately.",
            "pass_fail": "Pass if event-excluded cohort is positive with PF >= 1.10.",
            "risks": ["Slow movement decays spreads.", "Macro gaps through stops."],
            "data_requirements": ["TLT option history", "TNX/yield proxy", "macro calendar"],
            "required_symbols": ["TLT"],
            "evaluator": "symbol_data_readiness",
        },
        {
            "id": "iwm_small_cap_risk",
            "tier": 2,
            "priority": 7,
            "title": "IWM Small-Cap Risk-On/Risk-Off",
            "hypothesis": "IWM relative strength/weakness may create cleaner small-cap expansion or reversal trades.",
            "structure": "IWM 21-35 DTE call/put debit spreads, debit <= 45% width.",
            "test": "Take first qualifying signal per direction per week for 60 trading days.",
            "pass_fail": "Pass with 25 closed trades, PF >= 1.15, avg net P&L > 0, max drawdown < 4R.",
            "risks": ["Whipsaw.", "Index correlation during macro shocks."],
            "data_requirements": ["IWM option history", "IWM/SPY/RSP OHLCV", "VIX"],
            "required_symbols": ["IWM"],
            "evaluator": "symbol_data_readiness",
        },
        {
            "id": "volatility_compression_breakout",
            "tier": 2,
            "priority": 8,
            "title": "Volatility Compression Breakout",
            "hypothesis": "Low IV/HV compression can underprice directional expansion.",
            "structure": "21-45 DTE options or debit-spread pairs after volume-confirmed breakout.",
            "test": "Bollinger width in lowest 20% of 120 sessions, ATR compression, IV rank <= 45, 10-day breakout.",
            "pass_fail": "Pass if +1 ATR before -1 ATR at least 56% and option expectancy > 10%.",
            "risks": ["False breakouts.", "Theta bleed."],
            "data_requirements": ["OHLCV", "IV rank", "ATR", "Bollinger width", "option chain"],
            "evaluator": "paper_log_pending",
        },
        {
            "id": "bull_put_credit_spread",
            "tier": 2,
            "priority": 9,
            "title": "Bull Put Credit Spread",
            "hypothesis": "Defined-risk put credit spreads below support monetize bullish/neutral conditions better than buying upside.",
            "structure": "30-45 DTE short 20-30 delta put spread.",
            "test": "Support-based entries versus delta-only entries.",
            "pass_fail": "Pass with 40 trades, PF > 1.2, smoother drawdown than debit lanes.",
            "risks": ["Gap-down tail losses.", "Assignment near expiration."],
            "data_requirements": ["support levels", "credit spread quotes", "assignment/expiration handling"],
            "evaluator": "structure_instrumentation_pending",
        },
        {
            "id": "bearish_put_debit_spread",
            "tier": 2,
            "priority": 10,
            "title": "Bearish Put Debit Spread",
            "hypothesis": "Confirmed weak regimes deserve a bearish defined-risk lane rather than forcing bullish calls.",
            "structure": "21-45 DTE ATM/slightly ITM put debit spread.",
            "test": "Underlying below 20/50 DMA, RSI < 50, bearish SPY/QQQ confirmation.",
            "pass_fail": "Pass if win rate > 45% and average winner >= 1.25x average loser.",
            "risks": ["Late bearish entries.", "Snapback rallies."],
            "data_requirements": ["put spread history", "trend filters", "IV rank"],
            "evaluator": "paper_log_pending",
        },
        {
            "id": "post_event_vol_crush",
            "tier": 2,
            "priority": 11,
            "title": "Post-Event Vol-Crush",
            "hypothesis": "After event risk passes inside expected move, IV collapse favors premium-selling structures.",
            "structure": "7-21 DTE iron condor or credit spread after event.",
            "test": "Enter next session after earnings/FOMC/CPI/jobs if move stays inside expected range.",
            "pass_fail": "Pass with win rate > 58%, positive average R, and tail losses controlled.",
            "risks": ["Post-event drift continuation.", "Credit spread tail risk."],
            "data_requirements": ["event calendar", "expected move", "IV/HV", "credit spread quotes"],
            "evaluator": "event_data_blocked",
        },
        {
            "id": "iron_condor_range",
            "tier": 3,
            "priority": 12,
            "title": "Iron Condor Range",
            "hypothesis": "Range-bound regimes can outperform directional lanes through defined-risk premium selling.",
            "structure": "30-45 DTE index ETF iron condor, 15-20 delta short strikes.",
            "test": "ADX/range filter, realized vol below implied, no major event.",
            "pass_fail": "Pass if expectancy positive and drawdown tolerable versus credit collected.",
            "risks": ["Trend breakouts.", "Many small wins can hide tail risk."],
            "data_requirements": ["condor quotes", "ADX", "IV/HV", "event calendar"],
            "evaluator": "structure_instrumentation_pending",
        },
        {
            "id": "market_neutral_premium_control",
            "tier": 3,
            "priority": 13,
            "title": "Market-Neutral Premium Control",
            "hypothesis": "Some bullish-lane performance may be generic premium/regime behavior rather than direction.",
            "structure": "Neutral condors or balanced vertical pairs.",
            "test": "Compare neutral premium outcomes to directional lanes in low-trend regimes.",
            "pass_fail": "Useful if it clarifies whether direction matters; concerning if it beats directional lanes with lower drawdown.",
            "risks": ["Short-premium tail risk."],
            "data_requirements": ["neutral spread quotes", "regime labels"],
            "evaluator": "structure_instrumentation_pending",
        },
        {
            "id": "no_trade_opportunity_cost",
            "tier": 3,
            "priority": 14,
            "title": "No-Trade Opportunity Cost",
            "hypothesis": "Rejected near-misses should underperform accepted trades if filters help.",
            "structure": "Shadow log, no actual position.",
            "test": "Record every close reject by reason and simulated outcome.",
            "pass_fail": "Pass if near-misses underperform accepted trades or add volatility without expectancy.",
            "risks": ["Requires disciplined reject logging."],
            "data_requirements": ["rejected candidates", "rejection reasons", "shadow outcomes"],
            "evaluator": "instrumentation_blocked",
        },
        {
            "id": "random_approved_control",
            "tier": 3,
            "priority": 15,
            "title": "Random Approved Control",
            "hypothesis": "Real filters should beat constrained random selection from the same eligible universe.",
            "structure": "Shadow random verticals with comparable DTE/width/sizing.",
            "test": "Randomly select from eligible universe each trade day and compare to actual lane.",
            "pass_fail": "Pass if real lanes beat random on expectancy, drawdown, and consistency.",
            "risks": ["Needs enough samples.", "One-sided markets can flatter random controls."],
            "data_requirements": ["eligible universe snapshots", "random seed", "shadow pricing"],
            "evaluator": "instrumentation_blocked",
        },
        {
            "id": "inverse_signal_bearish_control",
            "tier": 3,
            "priority": 16,
            "title": "Inverse Signal Bearish Control",
            "hypothesis": "Opposite-side trades should underperform if bullish signals have directional value.",
            "structure": "Bearish put vertical when bullish signal would fire.",
            "test": "Same ticker, expiry window, and debit discipline where possible.",
            "pass_fail": "Pass as control if inverse expectancy is materially worse than bullish lane.",
            "risks": ["Downside volatility makes symmetry imperfect."],
            "data_requirements": ["same-day put chains", "shadow outcomes"],
            "evaluator": "instrumentation_blocked",
        },
        {
            "id": "risk_budget_sizing",
            "tier": 3,
            "priority": 17,
            "title": "Risk-Budget Sizing",
            "hypothesis": "Uniform sizing is less robust than volatility/debit/correlation-aware risk budgeting.",
            "structure": "Portfolio wrapper around accepted candidates.",
            "test": "Replay same trades with fixed current sizing versus risk-budget sizing.",
            "pass_fail": "Pass if similar expectancy with at least 25% lower max drawdown.",
            "risks": ["Can become too underpowered."],
            "data_requirements": ["account size", "open risk", "correlation buckets", "equity curve"],
            "evaluator": "portfolio_sim_pending",
        },
        {
            "id": "mechanical_profit_harvest",
            "tier": 3,
            "priority": 18,
            "title": "Mechanical Profit Harvest",
            "hypothesis": "Harvesting vertical winners earlier reduces giveback and improves realized expectancy.",
            "structure": "Exit wrapper around qualified bullish verticals.",
            "test": "Compare current exits to +45-60% debit harvest and harvest-plus-runner.",
            "pass_fail": "Pass if giveback falls and avg realized P&L rises without major PF deterioration.",
            "risks": ["Can cap strong trend winners."],
            "data_requirements": ["MFE/MAE", "intrahold marks", "close fills"],
            "evaluator": "exit_sim_pending",
        },
        {
            "id": "quote_deterioration_stop",
            "tier": 3,
            "priority": 19,
            "title": "Quote-Deterioration Stop",
            "hypothesis": "Quote/structure stops can reduce worst-decile losses before model stops trigger.",
            "structure": "Liquidity stop overlay.",
            "test": "Exit when spread bid collapses, bid/ask doubles, or a leg loses bid.",
            "pass_fail": "Pass if near-total losses fall without excessive false exits.",
            "risks": ["Bad quotes can force false exits."],
            "data_requirements": ["intra-position bid/ask history", "leg-level quotes"],
            "evaluator": "exit_sim_pending",
        },
        {
            "id": "portfolio_throttle",
            "tier": 3,
            "priority": 20,
            "title": "Portfolio Throttle",
            "hypothesis": "The book improves when duplicate beta theses are throttled.",
            "structure": "Portfolio selection wrapper.",
            "test": "Compare take-all eligible candidates versus one-per-bucket/day.",
            "pass_fail": "Pass if drawdown and clustered losses fall while preserving most net profit.",
            "risks": ["Can undertrade strong broad rallies."],
            "data_requirements": ["skipped trades", "exposure buckets", "portfolio equity curve"],
            "evaluator": "portfolio_sim_pending",
        },
        {
            "id": "sector_rotation_confirmation",
            "tier": 3,
            "priority": 21,
            "title": "Sector Rotation Confirmation",
            "hypothesis": "Sector inflow confirmation improves single-name entries.",
            "structure": "Sector ETF and component confirmation lane.",
            "test": "Trade leading sectors only; compare to same-day SPY/QQQ control.",
            "pass_fail": "Pass if it beats index controls by >= 0.4% avg underlying return.",
            "risks": ["Sector rotation can reverse abruptly."],
            "data_requirements": ["sector ETF OHLCV", "sector breadth", "component mapping"],
            "evaluator": "paper_log_pending",
        },
        {
            "id": "earnings_premium_avoidance",
            "tier": 3,
            "priority": 22,
            "title": "Earnings Premium Avoidance",
            "hypothesis": "Post-earnings reset beats entering near expensive pre-earnings IV.",
            "structure": "Shadow pre-earnings record plus post-earnings reset trade.",
            "test": "Compare would-have-entered pre-earnings against reset entries.",
            "pass_fail": "Pass if post-earnings reset expectancy exceeds pre-earnings shadow by >= 15 points.",
            "risks": ["May miss the gap move."],
            "data_requirements": ["earnings calendar", "front IV", "post-event quotes"],
            "evaluator": "event_data_blocked",
        },
        {
            "id": "rsi_trend_reclaim",
            "tier": 3,
            "priority": 23,
            "title": "RSI Trend Reclaim",
            "hypothesis": "RSI reclaim separates healthy pullbacks from weak bounces.",
            "structure": "Trend-pullback signal lane.",
            "test": "RSI below 45 then above 50, above rising SMA20/50, enter next open.",
            "pass_fail": "Pass if it beats simple trend entries by >= 0.5% average underlying return.",
            "risks": ["Whipsaws in chop."],
            "data_requirements": ["RSI", "SMA", "underlying returns", "option quotes"],
            "evaluator": "paper_log_pending",
        },
        {
            "id": "breadth_gated_index",
            "tier": 3,
            "priority": 24,
            "title": "Breadth-Gated Index",
            "hypothesis": "Index trades improve when breadth confirms the index move.",
            "structure": "SPY/QQQ directional lane gated by breadth.",
            "test": "Compare breadth-gated index days versus ungated index signals.",
            "pass_fail": "Pass if expectancy improves 20% and loser frequency drops 10%.",
            "risks": ["Mega-cap rallies can work despite weak breadth."],
            "data_requirements": ["breadth proxy", "RSP confirmation", "watchlist SMA status"],
            "evaluator": "breadth_data_blocked",
        },
        {
            "id": "monday_gap_fade",
            "tier": 3,
            "priority": 25,
            "title": "Monday Gap-Fade 0-3 DTE",
            "hypothesis": "Monday index gaps that fail to continue can partially retrace.",
            "structure": "0-3 DTE debit spread opposite failed gap.",
            "test": "Wait 15-30 minutes after Monday open; enter only failed continuation.",
            "pass_fail": "Pass if repeatable intraday gains survive spreads/slippage.",
            "risks": ["Trend days punish fades.", "0DTE execution quality matters."],
            "data_requirements": ["intraday OHLC", "opening range", "0DTE option quotes"],
            "evaluator": "intraday_data_blocked",
        },
        {
            "id": "opex_pin_risk",
            "tier": 3,
            "priority": 26,
            "title": "Month-End / OpEx Pin-Risk",
            "hypothesis": "OpEx/month-end high-OI pinning or flow behavior differs from normal trend lanes.",
            "structure": "0-5 DTE iron fly/condor pin setup or tagged drift trade.",
            "test": "Separate OpEx Friday, monthly OpEx week, and month-end.",
            "pass_fail": "Pass if OI filter improves win rate/drawdown versus baseline condors.",
            "risks": ["Pinning can break violently."],
            "data_requirements": ["open interest by strike", "intraday price", "expiration calendar"],
            "evaluator": "intraday_data_blocked",
        },
        {
            "id": "calendar_volatility",
            "tier": 3,
            "priority": 27,
            "title": "Call/Put Calendar Volatility",
            "hypothesis": "Calendars can profit when near-term movement is contained and term structure is favorable.",
            "structure": "Short 7-14 DTE, long 30-60 DTE same strike.",
            "test": "Index and single-name calendars separated; close before short expiration.",
            "pass_fail": "Pass if positive expectancy with lower directional dependence than verticals.",
            "risks": ["Sensitive to IV changes and strike placement."],
            "data_requirements": ["term structure", "calendar spread quotes", "pin/range behavior"],
            "evaluator": "structure_instrumentation_pending",
        },
        {
            "id": "pmcc_diagonal",
            "tier": 3,
            "priority": 28,
            "title": "Poor Man's Covered Call / Long Call Diagonal",
            "hypothesis": "Long call diagonals can smooth bullish exposure versus short-term verticals.",
            "structure": "Buy 90-180 DTE 70-80 delta call; sell 14-30 DTE 20-35 delta calls.",
            "test": "Judge 10-15 full campaigns, including rolls.",
            "pass_fail": "Pass if campaigns are smoother and avoid large drawdowns.",
            "risks": ["Roll complexity.", "Short calls can cap upside."],
            "data_requirements": ["diagonal quotes", "roll log", "earnings calendar"],
            "evaluator": "structure_instrumentation_pending",
        },
        {
            "id": "xle_energy_inflation",
            "tier": 3,
            "priority": 29,
            "title": "XLE Energy Inflation-Beta",
            "hypothesis": "Energy sector options diversify away from tech/index beta.",
            "structure": "XLE 21-35 DTE directional debit spreads, debit <= 42% width.",
            "test": "Trend-continuation and failed-breakout cohorts separated.",
            "pass_fail": "Pass if one side independently has PF >= 1.15 and combined avg net P&L > 0.",
            "risks": ["Commodity headline gaps.", "ETF spreads wider than SPY/QQQ."],
            "data_requirements": ["XLE option history", "crude proxy", "EIA/OPEC calendar"],
            "required_symbols": ["XLE"],
            "evaluator": "symbol_data_readiness",
        },
        {
            "id": "xlf_financials",
            "tier": 3,
            "priority": 30,
            "title": "XLF/KRE Financials Stress-Rebound",
            "hypothesis": "Financials provide a rate/credit-sensitive lane distinct from tech momentum.",
            "structure": "XLF call/put debit spreads.",
            "test": "Test XLF alone before adding regional-bank beta.",
            "pass_fail": "Pass only if XLF alone works.",
            "risks": ["Bank headlines.", "KRE liquidity."],
            "data_requirements": ["XLF option history", "bank breadth", "yield curve proxy"],
            "required_symbols": ["XLF"],
            "evaluator": "symbol_data_readiness",
        },
        {
            "id": "kre_regional_bank_observation",
            "tier": 3,
            "priority": 31,
            "title": "KRE Regional Bank Observation",
            "hypothesis": "Regional-bank beta may work differently from broad financials and needs separate liquidity proof.",
            "structure": "KRE observation lane before any promotion into XLF financials.",
            "test": "Graduate KRE only after standalone liquidity and spread survivability evidence.",
            "pass_fail": "Pass only if KRE independently has liquid, positive-expectancy exact replay evidence.",
            "risks": ["Regional bank headlines.", "Wide KRE option spreads."],
            "data_requirements": ["KRE option history", "regional-bank breadth", "yield curve proxy"],
            "required_symbols": ["KRE"],
            "evaluator": "symbol_data_readiness",
        },
        {
            "id": "smh_semiconductor",
            "tier": 3,
            "priority": 32,
            "title": "SMH Semiconductor Momentum",
            "hypothesis": "Semis may capture chip momentum without single-name concentration.",
            "structure": "SMH 21-35 DTE call debit spreads; puts only after underperformance.",
            "test": "Compare ETF lane against hypothetical NVDA/AMD single-name observation.",
            "pass_fail": "Pass if SMH beats single-name observation on risk-adjusted expectancy and PF >= 1.20.",
            "risks": ["Top-holding concentration.", "Tech correlation."],
            "data_requirements": ["SMH option history", "SOXX/QQQ OHLCV", "sector breadth"],
            "required_symbols": ["SMH"],
            "evaluator": "symbol_data_readiness",
        },
        {
            "id": "ai_commodity_infra_observation",
            "tier": 2,
            "priority": 33,
            "title": "AI Commodity / Power Infrastructure",
            "hypothesis": "AI data-centre growth may create tradable stress in power, grid, copper, silver, lithium, and uranium proxies, but the shortage narrative needs liquidity-first proof before promotion.",
            "structure": "Observation-only 21-35 DTE directional debit spreads on liquid ETFs and equities; calls or puts allowed so macro/commodity reversals can be measured instead of ignored.",
            "test": "Track the lane separately from broad tech/index signals; require option liquidity, debit <= 55% width, and tagged paper outcomes by sub-theme.",
            "pass_fail": "Pass with 40 tagged trades, PF >= 1.15, positive avg net P&L, and no single sub-theme providing more than 50% of net profit.",
            "risks": ["Crowded AI-power narrative.", "Commodity and rate shocks.", "Uneven ETF/miner options liquidity."],
            "data_requirements": ["AI commodity lane option history", "sub-theme tags", "commodity/power proxy OHLCV", "spread liquidity"],
            "required_symbols": list(ai_commodity_scan_tickers()),
            "full_scan_symbols": list(ai_commodity_scan_tickers()),
            "evaluator": "ai_commodity_data_readiness",
        },
    ]


def load_tracked_positions(db_path: Path = DEFAULT_TRACKED_DB) -> list[dict[str, Any]]:
    path = Path(db_path)
    if not path.exists() or path.stat().st_size == 0:
        return []
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM tracked_positions ORDER BY id").fetchall()
    return [dict(row) for row in rows]


def summarize_positions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    open_rows = [row for row in rows if str(row.get("status") or "").lower() == "open"]
    net_values = [_position_pnl_pct(row) for row in open_rows]
    entry_cost = sum(
        safe_num(row.get("entry_execution_price")) * 100.0 * max(safe_num(row.get("contracts")), 1.0)
        for row in open_rows
    )
    net_usd = sum(safe_num(row.get("net_pnl_usd")) for row in open_rows)
    by_ticker: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "entry_cost_usd": 0.0, "net_pnl_usd": 0.0, "sell": 0})
    debit_buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "net_pnl_pct_values": []})
    basis_counts: dict[str, int] = defaultdict(int)
    proof_counts: dict[str, int] = defaultdict(int)
    last_reviews = []
    for row in open_rows:
        ticker = str(row.get("ticker") or "UNKNOWN").upper()
        by_ticker[ticker]["count"] += 1
        by_ticker[ticker]["entry_cost_usd"] += safe_num(row.get("entry_execution_price")) * 100.0 * max(safe_num(row.get("contracts")), 1.0)
        by_ticker[ticker]["net_pnl_usd"] += safe_num(row.get("net_pnl_usd"))
        if str(row.get("last_recommendation") or "").upper() == "SELL":
            by_ticker[ticker]["sell"] += 1
        basis_counts[str(row.get("entry_execution_basis") or "unknown")] += 1
        proof_counts[str(row.get("proof_ineligibility_reason") or row.get("proof_class_reason") or "eligible")] += 1
        if row.get("last_reviewed_at"):
            last_reviews.append(str(row.get("last_reviewed_at")))
        snapshot = _safe_json(row.get("source_pick_snapshot"))
        bucket = classify_debit_bucket(debit_pct(snapshot))
        debit_buckets[bucket]["count"] += 1
        debit_buckets[bucket]["net_pnl_pct_values"].append(_position_pnl_pct(row))

    by_ticker_rows = []
    for ticker, item in sorted(by_ticker.items()):
        item_entry = safe_num(item["entry_cost_usd"])
        by_ticker_rows.append(
            {
                "ticker": ticker,
                "count": item["count"],
                "sell_count": item["sell"],
                "entry_cost_usd": round(item_entry, 2),
                "net_pnl_usd": round(item["net_pnl_usd"], 2),
                "net_return_pct": round(item["net_pnl_usd"] / item_entry * 100.0, 2) if item_entry else 0.0,
            }
        )
    by_ticker_rows.sort(key=lambda item: safe_num(item["net_pnl_usd"]), reverse=True)

    debit_bucket_rows = []
    for bucket, item in sorted(debit_buckets.items()):
        metrics = summarize_pnl_values(item["net_pnl_pct_values"])
        debit_bucket_rows.append({"bucket": bucket, **metrics})

    return {
        "open_count": len(open_rows),
        "open_position_count": len(open_rows),
        "position_count": len(open_rows),
        "closed_count": len(rows) - len(open_rows),
        "winner_count": sum(1 for value in net_values if value > 0),
        "winning_position_count": sum(1 for value in net_values if value > 0),
        "loser_count": sum(1 for value in net_values if value < 0),
        "losing_position_count": sum(1 for value in net_values if value < 0),
        "paper_pnl_pct_points": round(sum(net_values), 2),
        "total_pnl_pct_points": round(sum(net_values), 2),
        "open_net_pnl_pct_metrics": summarize_pnl_values(net_values),
        "entry_cost_usd": round(entry_cost, 2),
        "net_pnl_usd": round(net_usd, 2),
        "net_return_on_entry_cost_pct": round(net_usd / entry_cost * 100.0, 2) if entry_cost else 0.0,
        "sell_recommendation_count": sum(1 for row in open_rows if str(row.get("last_recommendation") or "").upper() == "SELL"),
        "hold_recommendation_count": sum(1 for row in open_rows if str(row.get("last_recommendation") or "").upper() == "HOLD"),
        "last_review_min": min(last_reviews) if last_reviews else None,
        "last_review_max": max(last_reviews) if last_reviews else None,
        "by_ticker": by_ticker_rows,
        "debit_buckets": debit_bucket_rows,
        "entry_basis_counts": dict(sorted(basis_counts.items())),
        "proof_reason_counts": dict(sorted(proof_counts.items())),
    }


def evaluate_current_paper_book(db_path: Path = DEFAULT_TRACKED_DB) -> dict[str, Any]:
    rows = load_tracked_positions(db_path)
    summary = summarize_positions(rows)
    blockers = []
    if not rows:
        blockers.append("no_tracked_positions")
    if summary.get("closed_count", 0) == 0:
        blockers.append("no_closed_paper_positions")
    if "spread_ask_bid" not in summary.get("entry_basis_counts", {}):
        blockers.append("no_spread_ask_bid_entry_fills_logged")
    if summary.get("proof_reason_counts"):
        non_eligible = {
            key: value
            for key, value in summary["proof_reason_counts"].items()
            if key != "eligible"
        }
        if non_eligible:
            blockers.append("current_book_is_comparable_or_manual_not_exact_proof")
    result = {
        "source": str(Path(db_path)),
        "status": "partial" if rows else "blocked",
        "summary": summary,
        "blockers": blockers,
        "interpretation": (
            "Current paper book is profitable as marked, but fill-discipline cannot pass until spread_ask_bid fills "
            "and timestamped fill attempts are logged."
        ),
    }
    result.update(
        {
            "open_position_count": summary.get("open_count", 0),
            "position_count": summary.get("open_count", 0),
            "winner_count": summary.get("winner_count", 0),
            "winning_position_count": summary.get("winner_count", 0),
            "loser_count": summary.get("loser_count", 0),
            "losing_position_count": summary.get("loser_count", 0),
            "paper_pnl_pct_points": summary.get("paper_pnl_pct_points", 0.0),
            "total_pnl_pct_points": summary.get("total_pnl_pct_points", 0.0),
        }
    )
    return result


def _trade_pnl(trade: dict[str, Any]) -> float:
    return safe_num(trade.get("net_pnl_pct", trade.get("pnl_pct")))


def summarize_trades(trades: Iterable[dict[str, Any]]) -> dict[str, Any]:
    return summarize_pnl_values(_trade_pnl(trade) for trade in trades)


def _resolution(trade: dict[str, Any]) -> str:
    return trade_contract_resolution(trade)


def _is_exact(trade: dict[str, Any]) -> bool:
    return is_exact_contract_resolution(_resolution(trade))


def _priced_trades(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [trade for trade in list(report.get("trades") or []) if trade.get("priced", True)]


def _group_trades_by_debit(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        groups[classify_debit_bucket(debit_pct(trade))].append(trade)
    output = []
    for bucket, rows in sorted(groups.items()):
        metrics = summarize_pnl_values(_trade_pnl(row) for row in rows)
        output.append({"bucket": bucket, **metrics})
    return output


def evaluate_historical_debit_controls(run_path: Path = DEFAULT_HISTORICAL_RUN) -> dict[str, Any]:
    path = Path(run_path)
    if not path.exists():
        return {"source": str(path), "status": "blocked", "blockers": ["missing_historical_run"]}
    report = _read_json(path)
    priced = _priced_trades(report)
    has_resolution = any(_resolution(trade) != "unknown" for trade in priced)
    exact = [trade for trade in priced if _is_exact(trade)] if has_resolution else priced
    all_groups = _group_trades_by_debit(priced)
    exact_groups = _group_trades_by_debit(exact)

    def lookup(rows: list[dict[str, Any]], bucket: str) -> dict[str, Any] | None:
        return next((row for row in rows if row.get("bucket") == bucket), None)

    cheap_exact = [
        trade
        for trade in exact
        if classify_debit_bucket(debit_pct(trade)) in {"cheap_lt40", "cheap_40_49"}
    ]
    high_exact = [
        trade
        for trade in exact
        if classify_debit_bucket(debit_pct(trade)) in {"high_55_74", "expensive_75_plus"}
    ]
    result_status = "scored"
    blockers: list[str] = []
    if len(exact) < 25:
        result_status = "thin_sample"
        blockers.append("exact_contract_sample_below_25")
    if not high_exact:
        blockers.append("no_exact_high_debit_control_trades")
    cheap_metrics = summarize_trades(cheap_exact)
    high_metrics = summarize_trades(high_exact)
    preferred_control = None
    if cheap_metrics["count"] and high_metrics["count"]:
        preferred_control = (
            "cheap_debit"
            if cheap_metrics["avg_pnl_pct"] >= high_metrics["avg_pnl_pct"]
            else "high_debit"
        )
    return {
        "source": str(path),
        "status": result_status,
        "run_at": report.get("run_at"),
        "playbook": report.get("playbook"),
        "pricing_lane": report.get("pricing_lane") or report.get("effective_pricing_lane"),
        "exact_trade_count": len(exact),
        "priced_trade_count": len(priced),
        "exact_by_debit_bucket": exact_groups,
        "all_priced_by_debit_bucket": all_groups,
        "cheap_exact_metrics": cheap_metrics,
        "high_exact_metrics": high_metrics,
        "cheap_debit": cheap_metrics,
        "cheap_debit_control": cheap_metrics,
        "high_debit": high_metrics,
        "high_debit_control": high_metrics,
        "preferred_control": preferred_control,
        "cheap_lt40_all_priced": lookup(all_groups, "cheap_lt40"),
        "high_55_74_all_priced": lookup(all_groups, "high_55_74"),
        "blockers": blockers,
        "interpretation": "Use exact buckets first; all-priced buckets are research-only because nearest contracts dominate the current artifact.",
    }


def evaluate_data_readiness(
    required_symbols: Iterable[str],
    readiness_path: Path = DEFAULT_PAID_DATA_READINESS,
    *,
    min_shared_quote_dates: int | None = None,
    readiness_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    symbols = sorted({str(symbol).upper() for symbol in required_symbols if str(symbol).strip()})
    path = Path(readiness_path)
    if not symbols:
        return {"status": "not_required", "required_symbols": []}
    if readiness_payload is None and not path.exists():
        return {"status": "blocked", "required_symbols": symbols, "blockers": ["missing_paid_data_readiness_artifact"]}
    readiness = dict(readiness_payload or _read_json(path))
    available = {str(symbol).upper() for symbol in readiness.get("available_underlyings") or []}
    missing = [symbol for symbol in symbols if symbol not in available]
    status = "ready" if not missing and readiness.get("status") == "ready_for_exact_replay" else "blocked"
    blockers = []
    if missing:
        blockers.append("missing_required_underlyings")
    if readiness.get("status") != "ready_for_exact_replay":
        blockers.append(str(readiness.get("blocker") or "paid_data_not_ready"))
    shared_quote_dates = readiness.get("shared_required_quote_dates") or {}
    shared_quote_date_count = int(shared_quote_dates.get("count") or 0) if isinstance(shared_quote_dates, dict) else 0
    if min_shared_quote_dates is not None and shared_quote_date_count < int(min_shared_quote_dates):
        blockers.append("insufficient_shared_quote_dates")
        status = "blocked"
    primary_blocker = "missing_required_symbols" if missing else (sorted(set(blockers))[0] if blockers else None)
    return {
        "source": "in_memory_paid_data_readiness" if readiness_payload is not None else str(path),
        "status": status,
        "required_symbols": symbols,
        "available_underlyings": sorted(available),
        "missing_symbols": missing,
        "missing_required_symbols": missing,
        "blocker": primary_blocker,
        "blockers": sorted(set(blockers)),
        "readiness_status": readiness.get("status"),
        "shared_quote_date_count": shared_quote_date_count,
        "min_shared_quote_dates": min_shared_quote_dates,
    }


def evaluate_ai_commodity_data_readiness(
    *,
    core_symbols: Iterable[str],
    expansion_symbols: Iterable[str],
    readiness_path: Path = DEFAULT_PAID_DATA_READINESS,
    readiness_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    proof_symbols = list(
        dict.fromkeys(
            str(symbol).strip().upper()
            for symbol in list(core_symbols or []) + list(expansion_symbols or [])
            if str(symbol).strip()
        )
    )
    proof_readiness = evaluate_data_readiness(
        proof_symbols,
        readiness_path,
        min_shared_quote_dates=AI_COMMODITY_MIN_SHARED_QUOTE_DATES,
        readiness_payload=readiness_payload,
    )
    proof_ready = proof_readiness.get("status") == "ready"
    status = "full_scan_ready" if proof_ready else "blocked"
    available = set(proof_readiness.get("available_underlyings") or [])
    return {
        "status": status,
        "proof": proof_readiness,
        "proof_symbols": list(proof_readiness.get("required_symbols") or []),
        "required_symbols": list(proof_readiness.get("required_symbols") or []),
        "core": proof_readiness,
        "expansion": {"status": "folded_into_full_scan_proof", "required_symbols": []},
        "core_symbols": list(proof_readiness.get("required_symbols") or []),
        "expansion_symbols": [],
        "data_ready_symbols": [
            symbol
            for symbol in list(proof_readiness.get("required_symbols") or [])
            if symbol in available
        ],
        "missing_required_symbols": list(proof_readiness.get("missing_required_symbols") or []),
        "missing_expansion_symbols": [],
        "blockers": [] if proof_ready else list(proof_readiness.get("blockers") or []),
        "readiness_status": proof_readiness.get("readiness_status"),
        "source": proof_readiness.get("source"),
    }


def _lane_result(
    lane: dict[str, Any],
    *,
    current_book: dict[str, Any],
    debit_control: dict[str, Any],
    readiness_path: Path,
    readiness_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evaluator = lane.get("evaluator")
    result: dict[str, Any] = {
        "id": lane["id"],
        "tier": lane["tier"],
        "priority": lane["priority"],
        "title": lane["title"],
        "hypothesis": lane["hypothesis"],
        "status": "pending",
        "score_source": None,
        "metrics": {},
        "blockers": [],
        "next_test": lane["test"],
        "pass_fail": lane["pass_fail"],
    }
    if evaluator == "current_paper_book_partial":
        result["status"] = "partial_current_paper_result"
        result["score_source"] = current_book.get("source")
        result["metrics"] = current_book.get("summary") or {}
        result["blockers"] = current_book.get("blockers") or []
        result["result"] = current_book.get("interpretation")
    elif evaluator == "historical_debit_control":
        result["status"] = debit_control.get("status", "blocked")
        result["score_source"] = debit_control.get("source")
        result["metrics"] = debit_control
        result["blockers"] = debit_control.get("blockers") or []
        result["result"] = (
            "Historical debit buckets were scored. Treat exact-contract rows as authority and all-priced rows as research."
        )
    elif evaluator == "symbol_data_readiness":
        readiness = evaluate_data_readiness(
            lane.get("required_symbols") or [],
            readiness_path,
            readiness_payload=readiness_payload,
        )
        result["status"] = "ready_for_paper_backtest" if readiness.get("status") == "ready" else "blocked_missing_data"
        result["score_source"] = readiness.get("source")
        result["metrics"] = readiness
        result["blockers"] = readiness.get("blockers") or []
        result["result"] = (
            "Required symbol option history is ready."
            if readiness.get("status") == "ready"
            else "Cannot honestly backtest this lane from current local trusted options history."
        )
    elif evaluator == "ai_commodity_data_readiness":
        readiness = evaluate_ai_commodity_data_readiness(
            core_symbols=lane.get("required_symbols") or [],
            expansion_symbols=lane.get("expansion_symbols") or [],
            readiness_path=readiness_path,
            readiness_payload=readiness_payload,
        )
        result["score_source"] = readiness.get("source")
        result["metrics"] = readiness
        if readiness.get("status") == "full_scan_ready":
            result["status"] = "ready_for_full_scan_paper_backtest"
            result["blockers"] = []
            result["result"] = "Full AI commodity scan universe has trusted Alpaca OPRA history ready for exact daily replay."
        else:
            result["status"] = "blocked_missing_data"
            result["blockers"] = readiness.get("blockers") or []
            result["result"] = "Full AI commodity scan-universe Alpaca OPRA history is not ready yet."
    elif evaluator in {"instrumentation_blocked", "event_data_blocked", "breadth_data_blocked", "intraday_data_blocked"}:
        result["status"] = "blocked_instrumentation"
        result["blockers"] = [evaluator]
        result["result"] = "Lane spec is complete, but the current app does not yet log the required inputs/outcomes."
    elif evaluator in {"paper_log_pending", "structure_instrumentation_pending", "portfolio_sim_pending", "exit_sim_pending"}:
        result["status"] = "pending_forward_paper_log"
        result["blockers"] = [evaluator]
        result["result"] = "Lane needs fresh tagged paper trades or structure-specific instrumentation before scoring."
    else:
        result["status"] = "pending"
        result["blockers"] = ["unknown_evaluator"]
    return result


def build_lane_lab_report(
    *,
    tracked_db: Path = DEFAULT_TRACKED_DB,
    historical_run: Path = DEFAULT_HISTORICAL_RUN,
    readiness_path: Path = DEFAULT_PAID_DATA_READINESS,
    readiness_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lanes = lane_definitions()
    current_book = evaluate_current_paper_book(tracked_db)
    debit_control = evaluate_historical_debit_controls(historical_run)
    evidence_policy = lane_lab_evidence_policy(
        tracked_db=tracked_db,
        historical_run=historical_run,
        readiness_path=readiness_path,
        readiness_payload=readiness_payload,
    )
    lane_results = [
        _lane_result(
            lane,
            current_book=current_book,
            debit_control=debit_control,
            readiness_path=readiness_path,
            readiness_payload=readiness_payload,
        )
        for lane in lanes
    ]
    status_counts: dict[str, int] = defaultdict(int)
    for item in lane_results:
        status_counts[str(item.get("status"))] += 1
    first_five = [item for item in lane_results if int(item["priority"]) <= 5]
    next_actions = [
        "Start logging spread_ask_bid fill attempts for fill_discipline.",
        "Persist top-3 contract alternatives per candidate for liquidity_first_spread.",
        "Keep high_debit_control as a shadow reject lane on every scan.",
        "Import trusted options history for GLD before scoring gld_macro_breakout.",
        "Create a tagged paper log for relative_strength_pullback before judging it.",
    ]
    ai_commodity = next(
        (item for item in lane_results if item.get("id") == "ai_commodity_infra_observation"),
        None,
    )
    if ai_commodity and "insufficient_shared_quote_dates" in set(ai_commodity.get("blockers") or []):
        proof_metrics = ((ai_commodity.get("metrics") or {}).get("proof") or {})
        next_actions.append(
            "Backfill AI commodity full scan-universe Alpaca OPRA history until the shared replay calendar reaches "
            f"{proof_metrics.get('min_shared_quote_dates')} dates; current shared dates: "
            f"{proof_metrics.get('shared_quote_date_count')}."
        )
    report = {
        "generated_at": _utc_now(),
        "lane_count": len(lanes),
        "first_five_ids": [item["id"] for item in first_five],
        "status_counts": dict(sorted(status_counts.items())),
        "sources": {
            "tracked_db": str(Path(tracked_db)),
            "historical_run": str(Path(historical_run)),
            "paid_data_readiness": str(Path(readiness_path)),
        },
        "source_quality": evidence_policy.get("source_quality"),
        "evidence_policy": evidence_policy,
        "current_paper_book": current_book,
        "historical_debit_control": debit_control,
        "lanes": lane_results,
        "next_actions": next_actions,
    }
    report["fingerprint"] = hashlib.sha256(
        json.dumps(
            {
                "first_five_ids": report["first_five_ids"],
                "status_counts": report["status_counts"],
                "sources": report["sources"],
                "lane_ids": [lane["id"] for lane in lane_results],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf8")
    ).hexdigest()
    return report


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Options Lane Lab",
        "",
        f"- Generated: {report.get('generated_at')}",
        f"- Lanes: {report.get('lane_count')}",
        f"- First five: {', '.join(report.get('first_five_ids') or [])}",
        f"- Status counts: `{json.dumps(report.get('status_counts') or {}, sort_keys=True)}`",
        f"- Source quality: `{(report.get('evidence_policy') or {}).get('source_quality')}`",
        f"- Row evidence group: `{(report.get('evidence_policy') or {}).get('evidence_group')}`",
        f"- Quote evidence class: `{((report.get('evidence_policy') or {}).get('quote_evidence') or {}).get('quote_evidence_class')}`",
        f"- Production proof eligible: `{(report.get('evidence_policy') or {}).get('production_proof_eligible')}`",
        "",
        "## Current Paper Book",
    ]
    current = report.get("current_paper_book", {}).get("summary", {})
    lines.extend(
        [
            f"- Open positions: `{current.get('open_count')}`",
            f"- Net P&L: `${current.get('net_pnl_usd')}`",
            f"- Net return on entry cost: `{current.get('net_return_on_entry_cost_pct')}%`",
            f"- Winners / losers: `{current.get('winner_count')}` / `{current.get('loser_count')}`",
            f"- SELL recommendations: `{current.get('sell_recommendation_count')}`",
            "",
            "## Lane Results",
            "",
            "| Priority | Lane | Tier | Status | Key Result |",
            "| ---: | --- | ---: | --- | --- |",
        ]
    )
    for lane in sorted(report.get("lanes") or [], key=lambda item: int(item.get("priority") or 999)):
        result = str(lane.get("result") or "").replace("|", "/")
        if len(result) > 110:
            result = result[:107] + "..."
        lines.append(
            f"| {lane.get('priority')} | `{lane.get('id')}` | {lane.get('tier')} | `{lane.get('status')}` | {result} |"
        )
    lines.extend(
        [
            "",
            "## Evidence Boundary",
            "",
            "- Lane Lab rows are research/planning readbacks, not live broker fills or production proof.",
            "- The quote evidence class labels the source quality of supporting readbacks; it does not promote legacy tracked DB or daily replay artifacts.",
        ]
    )
    lines.extend(["", "## Next Actions"])
    for action in report.get("next_actions") or []:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"lane_lab_{stamp}.json"
    md_path = output_dir / f"lane_lab_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    serialized = json.dumps(report, indent=2)
    markdown = render_markdown(report)
    json_path.write_text(serialized, encoding="utf8")
    latest_json.write_text(serialized, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
    }


def run_lane_lab(
    *,
    tracked_db: Path = DEFAULT_TRACKED_DB,
    historical_run: Path = DEFAULT_HISTORICAL_RUN,
    readiness_path: Path = DEFAULT_PAID_DATA_READINESS,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    write: bool = True,
    readiness_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = build_lane_lab_report(
        tracked_db=tracked_db,
        historical_run=historical_run,
        readiness_path=readiness_path,
        readiness_payload=readiness_payload,
    )
    if write:
        report["artifacts"] = write_report(report, output_dir)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the options lane lab across all paper-test lanes.")
    parser.add_argument("--tracked-db", default=str(DEFAULT_TRACKED_DB))
    parser.add_argument("--historical-run", default=str(DEFAULT_HISTORICAL_RUN))
    parser.add_argument("--paid-data-readiness", default=str(DEFAULT_PAID_DATA_READINESS))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_lane_lab(
        tracked_db=Path(args.tracked_db),
        historical_run=Path(args.historical_run),
        readiness_path=Path(args.paid_data_readiness),
        output_dir=Path(args.output_dir),
        write=not args.no_write,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            json.dumps(
                {
                    "lane_count": report["lane_count"],
                    "first_five_ids": report["first_five_ids"],
                    "status_counts": report["status_counts"],
                    "source_quality": report["source_quality"],
                    "evidence_policy": report["evidence_policy"],
                    "artifacts": report.get("artifacts"),
                    "next_actions": report["next_actions"],
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
