from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


RUNS_DIR = ROOT / "data" / "options-validation" / "runs"
ROBUSTNESS_DIR = ROOT / "data" / "profitability-lab" / "imported-intraday-robustness"
OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-multilane"
DOCS_REPORT = ROOT / "docs" / "regular-options-multilane-2026-05-30.md"
LANE_LAB_LATEST = ROOT / "data" / "lane-lab" / "latest.json"
SIDE_AWARE_ZERO_BID_LATEST = (
    ROOT
    / "data"
    / "profitability-lab"
    / "side-aware-zero-bid"
    / "latest_lane_a_side_aware_zero_bid.json"
)

TARGET_EXACT_TRADES = 200
COUNT_CANDIDATE_STATUS = "count_candidate"
LEGACY_COUNT_CANDIDATE_STATUS = "portfolio_candidate"
COUNT_CANDIDATE_STATUSES = {COUNT_CANDIDATE_STATUS, LEGACY_COUNT_CANDIDATE_STATUS}


LANE_SOURCES: list[dict[str, Any]] = [
    {
        "lane_id": "bullish_pullback_core",
        "family": "bullish_pullback_observation",
        "label": "Bullish pullback count-expanded core",
        "role": "core",
        "decision": "portfolio_core",
        "artifact": RUNS_DIR / "20260528_224313_sleeve_pf59_coverage_a_refill_v1_intraday.json",
        "robustness": ROBUSTNESS_DIR / "latest_sleeve_pf59_coverage_a_refill_v1.json",
        "priority": 10,
        "include_in_proof_portfolio": True,
        "notes": "Current count-expanded paper-shadow branch; still strict-proof blocked by three provider no-match candidates.",
    },
    {
        "lane_id": "lane_a_chain_native_ret20_4_stop200_time75",
        "family": "bullish_pullback_observation",
        "label": "Lane A chain-native ret20=4 extension",
        "role": "portfolio_extension",
        "decision": "portfolio_extension_with_coverage_debt",
        "artifact": RUNS_DIR / "20260530_191945_lane_a_chain_native_ret20_4_stop200_time75_rerun4_v1_intraday.json",
        "robustness": ROBUSTNESS_DIR / "latest_lane_a_chain_native_ret20_4_stop200_time75_rerun4_v1.json",
        "priority": 15,
        "include_in_proof_portfolio": True,
        "notes": "Refreshed exact intraday rerun of the older Lane A branch after bounded exact and lookahead fills. It pushes the strict-deduped proof stack above 200, but the side-aware zero-bid replay shows the remaining exit debt is economically adverse.",
    },
    {
        "lane_id": "bullish_pullback_clean_exact_reference",
        "family": "bullish_pullback_observation",
        "label": "Bullish pullback clean exact reference",
        "role": "alternate_reference",
        "decision": "reference_only",
        "artifact": RUNS_DIR / "20260528_013303_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1_intraday.json",
        "robustness": ROBUSTNESS_DIR / "latest_sleeve_winner_clean_plus_liquid_no_cat_pm_prior1_timecombo55_50_75_mixed_v1.json",
        "priority": 20,
        "include_in_proof_portfolio": False,
        "notes": "Clean 100%-covered sibling; not added to the portfolio count because it substantially overlaps the core branch.",
    },
    {
        "lane_id": "iwm_small_cap_risk",
        "family": "iwm_small_cap_risk",
        "label": "IWM small-cap component",
        "role": "component_scout",
        "decision": "dedupe_component_only",
        "artifact": RUNS_DIR / "20260527_204655_sleeve_ticker_iwm_intraday.json",
        "priority": 30,
        "include_in_proof_portfolio": True,
        "notes": "Executable exact intraday component, but most accepted rows are expected to overlap the bullish-pullback core.",
    },
    {
        "lane_id": "etf_index_pullback_control",
        "family": "etf_index_pullback_control",
        "label": "ETF/index move-bucket scout",
        "role": "scout",
        "decision": "scout_only",
        "artifact": RUNS_DIR / "20260528_230351_sleeve_next_index_move_bucket_baseline_v1_intraday.json",
        "priority": 40,
        "include_in_proof_portfolio": False,
        "notes": "Too few exact trades and below the preferred PF/avg bars; visible as a future lane seed only.",
    },
    {
        "lane_id": "high_beta_momentum_volatility",
        "family": "high_beta_momentum_volatility",
        "label": "High-beta momentum scout",
        "role": "scout_rejected",
        "decision": "do_not_promote",
        "artifact": RUNS_DIR / "20260528_230651_sleeve_next_high_beta_momentum_fast_v1_intraday.json",
        "priority": 50,
        "include_in_proof_portfolio": False,
        "notes": "Existing exact intraday replay is decisively unprofitable; needs a new causal hypothesis before more tuning.",
    },
    {
        "lane_id": "high_beta_put_riskoff",
        "family": "high_beta_momentum_volatility",
        "label": "High-beta put riskoff scout",
        "role": "scout_blocked",
        "decision": "no_candidates",
        "artifact": RUNS_DIR / "20260528_230705_sleeve_next_high_beta_put_riskoff_v1_intraday.json",
        "priority": 60,
        "include_in_proof_portfolio": False,
        "notes": "No exact candidates in the current artifact.",
    },
    {
        "lane_id": "regular_bearish_index_riskoff",
        "family": "regular_bearish_put_primary",
        "label": "Regular bearish index riskoff",
        "role": "scout_blocked",
        "decision": "no_candidates",
        "artifact": RUNS_DIR / "20260527_204221_sleeve_bearish_index_riskoff_intraday.json",
        "priority": 70,
        "include_in_proof_portfolio": False,
        "notes": "Intraday artifact exists but produced zero candidates.",
    },
    {
        "lane_id": "regular_bearish_put_primary_timeexit_probe",
        "family": "regular_bearish_put_primary",
        "label": "Regular bearish put primary time-exit probe",
        "role": "intraday_rejected_probe",
        "decision": "do_not_promote",
        "artifact": RUNS_DIR / "20260530_164435_regular_bearish_put_primary_chain_native_timeexit_v1_intraday.json",
        "priority": 75,
        "include_in_proof_portfolio": False,
        "notes": "Put-chain data was imported and the lane priced 73 exact trades, but PF/average PnL were decisively negative.",
    },
    {
        "lane_id": "range_breakout_call_timeexit_probe",
        "family": "range_breakout_observation",
        "label": "Range breakout call time-exit probe",
        "role": "intraday_rejected_probe",
        "decision": "do_not_promote",
        "artifact": RUNS_DIR / "20260530_164542_range_breakout_observation_chain_native_call_timeexit_v1_intraday.json",
        "priority": 76,
        "include_in_proof_portfolio": False,
        "notes": "Trusted intraday rerun exists, but the priced exact sample is negative.",
    },
    {
        "lane_id": "volatility_expansion_call_timeexit_probe",
        "family": "volatility_expansion_observation",
        "label": "Volatility expansion call time-exit probe",
        "role": "intraday_rejected_probe",
        "decision": "do_not_promote",
        "artifact": RUNS_DIR / "20260530_164739_volatility_expansion_observation_chain_native_call_timeexit_v1_intraday.json",
        "priority": 77,
        "include_in_proof_portfolio": False,
        "notes": "Closest non-core probe, but after exact exit import it remained below breakeven.",
    },
    {
        "lane_id": "tracked_winner_chain_native_qqq_time80_intraday",
        "family": "tracked_winner_primary",
        "label": "Tracked-winner chain-native QQQ time80 intraday rerun",
        "role": "intraday_rejected_probe",
        "decision": "do_not_promote",
        "artifact": RUNS_DIR / "20260530_202046_tracked_winner_chain_native_qqq_time80_research_intraday.json",
        "priority": 78,
        "include_in_proof_portfolio": False,
        "notes": "Contrarian count-expansion check: 102 exact trades are novel versus the current 234 stack, but the current trusted intraday rerun has PF below the promotion bar and severe provider no-match coverage debt.",
    },
    {
        "lane_id": "tracked_winner_chain_native_research",
        "family": "tracked_winner_primary",
        "label": "Tracked-winner legacy daily research",
        "role": "legacy_daily_reference",
        "decision": "daily_research_only",
        "artifact": RUNS_DIR / "latest_daily.json",
        "priority": 80,
        "include_in_proof_portfolio": False,
        "notes": "Exact-contract daily/EOD reference, not trusted intraday OPRA/NBBO proof for the current count target.",
    },
    {
        "lane_id": "bearish_index_put_observation",
        "family": "bearish_put_debit_spread",
        "label": "Bearish index put observation",
        "role": "legacy_daily_reference",
        "decision": "daily_research_only",
        "artifact": RUNS_DIR / "20260505_015407_bearish_index_put_observation_daily.json",
        "priority": 90,
        "include_in_proof_portfolio": False,
        "notes": "Older daily artifact; useful as a candidate lane but not counted as exact intraday proof.",
    },
    {
        "lane_id": "range_breakout_observation",
        "family": "range_breakout_observation",
        "label": "Range breakout observation",
        "role": "legacy_daily_reference",
        "decision": "daily_research_only",
        "artifact": RUNS_DIR / "20260505_015458_range_breakout_observation_daily.json",
        "priority": 100,
        "include_in_proof_portfolio": False,
        "notes": "Older daily artifact with very sparse exact rows; needs intraday rerun before proof use.",
    },
    {
        "lane_id": "volatility_expansion_observation",
        "family": "volatility_expansion_observation",
        "label": "Volatility expansion observation",
        "role": "legacy_daily_reference",
        "decision": "daily_research_only",
        "artifact": RUNS_DIR / "20260505_015615_volatility_expansion_observation_daily.json",
        "priority": 110,
        "include_in_proof_portfolio": False,
        "notes": "Older daily artifact is negative and not proof-grade for this portfolio stack.",
    },
    {
        "lane_id": "bullish_mean_reversion",
        "family": "bullish_mean_reversion",
        "label": "Bullish mean-reversion observation",
        "role": "legacy_daily_reference",
        "decision": "no_candidates",
        "artifact": RUNS_DIR / "20260414_110605_bullish_mean_reversion_daily.json",
        "priority": 120,
        "include_in_proof_portfolio": False,
        "notes": "Older daily artifact produced no candidates.",
    },
]


REGULAR_LANE_LAB_IDS = {
    "fill_discipline",
    "liquidity_first_spread",
    "high_debit_control",
    "gld_macro_breakout",
    "relative_strength_pullback",
    "tlt_duration_shock",
    "iwm_small_cap_risk",
    "volatility_compression_breakout",
    "bull_put_credit_spread",
    "bearish_put_debit_spread",
    "post_event_vol_crush",
    "iron_condor_range",
    "market_neutral_premium_control",
    "no_trade_opportunity_cost",
    "random_approved_control",
    "inverse_signal_bearish_control",
    "risk_budget_sizing",
    "mechanical_profit_harvest",
    "quote_deterioration_stop",
    "portfolio_throttle",
    "sector_rotation_confirmation",
    "earnings_premium_avoidance",
    "rsi_trend_reclaim",
    "breadth_gated_index",
    "monday_gap_fade",
    "opex_pin_risk",
    "calendar_volatility",
    "pmcc_diagonal",
    "xle_energy_inflation",
    "xlf_financials",
    "smh_semiconductor",
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _round(value: Any, digits: int = 2) -> float:
    return round(_safe_float(value), digits)


def _metric_value(metrics: dict[str, Any], run: dict[str, Any], key: str) -> Any:
    value = metrics.get(key) if metrics else None
    return run.get(key) if value is None else value


def _metrics_from_run(run: dict[str, Any]) -> dict[str, Any]:
    metrics = run.get("authoritative_profitability_metrics") or run.get("exact_contract_metrics") or {}
    return {
        "candidate_trade_count": _safe_int(run.get("candidate_trade_count")),
        "priced_trade_count": _safe_int(run.get("priced_trade_count") or run.get("total_trades")),
        "exact_trade_count": _safe_int(metrics.get("trade_count") or run.get("exact_contract_match_count")),
        "unpriced_trade_count": _safe_int(run.get("unpriced_trade_count")),
        "quote_coverage_pct": _round(run.get("quote_coverage_pct")),
        "profit_factor": _round(_metric_value(metrics, run, "profit_factor")),
        "avg_pnl_pct": _round(_metric_value(metrics, run, "avg_pnl_pct")),
        "win_rate_pct": _round(_metric_value(metrics, run, "win_rate_pct")),
        "gross_win": _round(_metric_value(metrics, run, "gross_win")),
        "gross_loss": _round(_metric_value(metrics, run, "gross_loss")),
    }


def _is_count_candidate_status(status: Any) -> bool:
    return str(status or "") in COUNT_CANDIDATE_STATUSES


def _robustness_summary(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    payload = _load_json(path)
    rolling = payload.get("rolling_oos") or {}
    first_window = (rolling.get("windows") or [{}])[0].get("test") if rolling.get("windows") else {}
    stress_rows = payload.get("slippage_stress") or []
    stress_5 = {}
    for row in stress_rows:
        if abs(_safe_float(row.get("slippage_pct_per_side")) - 5.0) < 0.001:
            stress_5 = row.get("metrics") or {}
            break
    return {
        "status": payload.get("status"),
        "rolling_status": rolling.get("status"),
        "rolling_first_test_profit_factor": _round((first_window or {}).get("profit_factor")),
        "rolling_first_test_trades": _safe_int((first_window or {}).get("trades")),
        "stress_5pct_per_side_profit_factor": _round(stress_5.get("profit_factor")) if stress_5 else None,
    }


def is_exact_imported_trade(trade: dict[str, Any]) -> bool:
    resolution = str(trade.get("entry_contract_resolution") or "").lower()
    fill_basis = str(trade.get("exit_fill_basis") or "").lower()
    return bool(trade.get("priced", True)) and resolution.startswith("exact") and fill_basis == "imported_spread_mark"


def proof_grade_for_run(run: dict[str, Any]) -> str:
    truth = str(run.get("truth_source") or "").lower()
    realism = str(run.get("execution_realism") or "").lower()
    if truth == "historical_imported" and realism == "quote_backed_intraday_replay":
        return "trusted_intraday_opra_nbbo"
    if truth == "historical_imported_daily":
        return "exact_daily_research"
    if truth == "historical_imported":
        return "imported_intraday_research"
    return "non_proof"


def _trade_direction(trade: dict[str, Any]) -> str:
    raw = str(trade.get("type") or trade.get("direction") or "").strip().lower()
    if raw in {"call", "put"}:
        return raw
    return "unknown"


def normalize_trade(trade: dict[str, Any], lane: dict[str, Any], run: dict[str, Any], *, unpriced: bool = False) -> dict[str, Any]:
    ticker = str(trade.get("ticker") or "").strip().upper()
    direction = _trade_direction(trade)
    entry_date = str(trade.get("date") or trade.get("entry_date") or "")
    exposure_bucket = str(
        trade.get("allocation_group")
        or trade.get("sleeve_group")
        or trade.get("sector")
        or lane.get("family")
        or "unknown"
    ).strip().lower()
    exact_priced = (not unpriced) and proof_grade_for_run(run) == "trusted_intraday_opra_nbbo" and is_exact_imported_trade(trade)
    return {
        "lane_id": lane["lane_id"],
        "lane_family": lane.get("family"),
        "source_playbook": run.get("playbook"),
        "source_result_path": str(Path(lane["artifact"]).relative_to(ROOT)) if Path(lane["artifact"]).is_absolute() else str(lane["artifact"]),
        "proof_grade": proof_grade_for_run(run),
        "portfolio_priority": lane.get("priority"),
        "portfolio_eligible": bool(lane.get("include_in_proof_portfolio")) and exact_priced,
        "ticker": ticker,
        "entry_date": entry_date,
        "exit_date": str(trade.get("exit_date") or ""),
        "direction": direction,
        "strategy_type": str(trade.get("strategy_type") or ""),
        "exposure_bucket": exposure_bucket,
        "long_contract_symbol": str(
            trade.get("contract_symbol")
            or trade.get("long_contract_symbol")
            or trade.get("missing_long_contract_symbol")
            or ""
        ),
        "short_contract_symbol": str(
            trade.get("short_contract_symbol")
            or trade.get("missing_short_contract_symbol")
            or ""
        ),
        "priced": bool(trade.get("priced", not unpriced)) and not unpriced,
        "exact_priced": exact_priced,
        "pnl_pct": _round(trade.get("net_pnl_pct", trade.get("pnl_pct"))),
        "fill_basis": str(trade.get("exit_fill_basis") or ""),
        "entry_contract_resolution": str(trade.get("entry_contract_resolution") or ""),
        "unpriced_reason": str(trade.get("unpriced_reason") or trade.get("non_promotable_reason") or ""),
        "dedupe_key": "|".join([entry_date, ticker, direction]),
    }


def normalize_trades(lane: dict[str, Any], run: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        normalize_trade(trade, lane, run, unpriced=False)
        for trade in run.get("trades") or []
    ]
    rows.extend(
        normalize_trade(trade, lane, run, unpriced=True)
        for trade in run.get("unpriced_trades") or []
    )
    return rows


def dedupe_portfolio_trades(rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in rows if row.get("portfolio_eligible")]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        grouped[str(row.get("dedupe_key"))].append(row)

    selected: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for group in grouped.values():
        ordered = sorted(group, key=lambda row: (_safe_int(row.get("portfolio_priority"), 999), str(row.get("lane_id"))))
        selected.append(ordered[0])
        suppressed.extend(ordered[1:])

    selected.sort(key=lambda row: (str(row.get("entry_date")), str(row.get("ticker")), str(row.get("direction"))))
    return {
        "selected_trades": selected,
        "suppressed_duplicates": suppressed,
        "duplicate_group_count": sum(1 for group in grouped.values() if len(group) > 1),
    }


def metrics_for_trades(rows: list[dict[str, Any]]) -> dict[str, Any]:
    priced = [row for row in rows if row.get("exact_priced")]
    wins = [row for row in priced if _safe_float(row.get("pnl_pct")) > 0]
    losses = [row for row in priced if _safe_float(row.get("pnl_pct")) < 0]
    gross_win = sum(_safe_float(row.get("pnl_pct")) for row in wins)
    gross_loss = abs(sum(_safe_float(row.get("pnl_pct")) for row in losses))
    trade_count = len(priced)
    return {
        "exact_trade_count": trade_count,
        "win_trade_count": len(wins),
        "loss_trade_count": len(losses),
        "win_rate_pct": round((len(wins) / trade_count) * 100.0, 1) if trade_count else 0.0,
        "avg_pnl_pct": round(sum(_safe_float(row.get("pnl_pct")) for row in priced) / trade_count, 2) if trade_count else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else (round(gross_win, 2) if gross_win > 0 else 0.0),
        "gross_win": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "gap_to_200": max(TARGET_EXACT_TRADES - trade_count, 0),
    }


def classify_lane(run_metrics: dict[str, Any], robustness: dict[str, Any], proof_grade: str, include_in_proof: bool) -> dict[str, Any]:
    blockers: list[str] = []
    exact = _safe_int(run_metrics.get("exact_trade_count"))
    unpriced = _safe_int(run_metrics.get("unpriced_trade_count"))
    coverage = _safe_float(run_metrics.get("quote_coverage_pct"))
    pf = _safe_float(run_metrics.get("profit_factor"))
    avg = _safe_float(run_metrics.get("avg_pnl_pct"))
    stress_pf = _safe_float(robustness.get("stress_5pct_per_side_profit_factor"), default=0.0)
    rolling_status = str(robustness.get("rolling_status") or "").lower()

    if proof_grade != "trusted_intraday_opra_nbbo":
        blockers.append("not_trusted_intraday_opra_nbbo")
    if exact <= 0:
        blockers.append("no_exact_priced_trades")
    if exact < 25:
        blockers.append("thin_exact_sample")
    if pf < 1.75:
        blockers.append("pf_below_1_75")
    if avg <= 0:
        blockers.append("avg_pnl_not_positive")
    if coverage < 97.5:
        blockers.append("quote_coverage_below_97_5")
    if unpriced > 0:
        blockers.append("unpriced_candidates_remain")
    if robustness and stress_pf < 1.5:
        blockers.append("stress_pf_below_1_5")
    if robustness and rolling_status and rolling_status != "passed":
        blockers.append("rolling_oos_not_clean")

    if include_in_proof and proof_grade == "trusted_intraday_opra_nbbo" and exact >= 100 and pf >= 1.75:
        status = COUNT_CANDIDATE_STATUS
    elif proof_grade == "trusted_intraday_opra_nbbo" and exact > 0:
        status = "intraday_scout"
    elif proof_grade == "exact_daily_research":
        status = "daily_research_only"
    else:
        status = "blocked_or_empty"

    return {"status": status, "blockers": blockers}


def build_quality_gate(lane_reports: list[dict[str, Any]], combined_metrics: dict[str, Any]) -> dict[str, Any]:
    count_blockers: list[str] = []
    coverage_blockers: list[str] = []
    robustness_blockers: list[str] = []

    exact_count = _safe_int(combined_metrics.get("exact_trade_count"))
    if exact_count < TARGET_EXACT_TRADES:
        count_blockers.append(f"combined_exact_trade_count_below_{TARGET_EXACT_TRADES}")

    included_lanes = [
        lane
        for lane in lane_reports
        if lane.get("include_in_proof_portfolio") and _is_count_candidate_status(lane.get("status"))
    ]
    for lane in included_lanes:
        lane_id = str(lane.get("lane_id"))
        metrics = lane.get("metrics") or {}
        coverage = _safe_float(metrics.get("quote_coverage_pct"))
        unpriced = _safe_int(metrics.get("unpriced_trade_count"))
        if coverage < 97.5:
            coverage_blockers.append(f"{lane_id}:quote_coverage_{coverage:.1f}_below_97_5")
        if unpriced > 0:
            coverage_blockers.append(f"{lane_id}:unpriced_candidates_{unpriced}")

        robustness = lane.get("robustness") or {}
        if not robustness:
            robustness_blockers.append(f"{lane_id}:robustness_report_missing")
            continue
        rolling_status = str(robustness.get("rolling_status") or "").lower()
        stress_pf = _safe_float(robustness.get("stress_5pct_per_side_profit_factor"), default=0.0)
        if rolling_status != "passed":
            robustness_blockers.append(f"{lane_id}:rolling_oos_{rolling_status or 'missing'}")
        if stress_pf < 1.2:
            robustness_blockers.append(f"{lane_id}:stress_5pct_pf_{stress_pf:.2f}_below_1_2")

    paper_shadow_blockers = ["paper_shadow_fill_evidence_pending"]
    all_blockers = count_blockers + coverage_blockers + robustness_blockers + paper_shadow_blockers
    return {
        "overall_status": "production_ready" if not all_blockers else "quality_pending",
        "count_status": "passed" if not count_blockers else "blocked",
        "coverage_status": "passed" if not coverage_blockers else "blocked",
        "robustness_status": "passed" if not robustness_blockers else "blocked",
        "paper_shadow_status": "pending",
        "blockers": all_blockers,
    }


def compact_side_aware_zero_bid_report(payload: dict[str, Any]) -> dict[str, Any]:
    modes = payload.get("modes") or {}
    compact_modes: dict[str, Any] = {}
    for mode_name in ("midpoint_zero_bid", "conservative"):
        mode = modes.get(mode_name) or {}
        compact_modes[mode_name] = {
            "candidate_count": _safe_int(mode.get("candidate_count")),
            "priced_count": _safe_int(mode.get("priced_count")),
            "unpriced_count": _safe_int(mode.get("unpriced_count")),
            "zero_bid_priced_count": _safe_int(mode.get("zero_bid_priced_count")),
            "side_aware_metrics": mode.get("side_aware_metrics") or {},
            "combined_with_existing_lane_a_metrics": mode.get("combined_with_existing_lane_a_metrics") or {},
            "combined_lane_a_priced_count": _safe_int(mode.get("combined_lane_a_priced_count")),
            "combined_lane_a_unpriced_count": _safe_int(mode.get("combined_lane_a_unpriced_count")),
            "combined_lane_a_quote_coverage_pct": _safe_float(mode.get("combined_lane_a_quote_coverage_pct")),
            "exit_reasons": mode.get("exit_reasons") or {},
            "unpriced_reasons": mode.get("unpriced_reasons") or {},
        }
    return {
        "generated_at_utc": payload.get("generated_at_utc"),
        "artifact": str(SIDE_AWARE_ZERO_BID_LATEST.relative_to(ROOT)),
        "assumptions": payload.get("assumptions") or {},
        "provider_stats": payload.get("provider_stats") or {},
        "modes": compact_modes,
    }


def _side_aware_zero_bid_report() -> dict[str, Any] | None:
    if not SIDE_AWARE_ZERO_BID_LATEST.exists():
        return None
    return compact_side_aware_zero_bid_report(_load_json(SIDE_AWARE_ZERO_BID_LATEST))


def _lane_lab_blockers() -> list[dict[str, Any]]:
    if not LANE_LAB_LATEST.exists():
        return []
    payload = _load_json(LANE_LAB_LATEST)
    known_sources = {source["lane_id"] for source in LANE_SOURCES}
    known_sources.update(source["family"] for source in LANE_SOURCES)
    rows = []
    for lane in payload.get("lanes") or []:
        lane_id = str(lane.get("id") or "")
        if lane_id not in REGULAR_LANE_LAB_IDS or lane_id in known_sources:
            continue
        rows.append(
            {
                "lane_id": lane_id,
                "status": lane.get("status"),
                "blockers": lane.get("blockers") or [],
                "next_test": lane.get("next_test"),
                "pass_fail": lane.get("pass_fail"),
            }
        )
    return rows


def build_report() -> dict[str, Any]:
    lane_reports: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []

    for lane in LANE_SOURCES:
        artifact = Path(lane["artifact"])
        if not artifact.exists():
            lane_reports.append(
                {
                    "lane_id": lane["lane_id"],
                    "family": lane.get("family"),
                    "label": lane.get("label"),
                    "decision": "missing_artifact",
                    "status": "blocked_or_empty",
                    "blockers": ["missing_artifact"],
                    "source_result_path": str(artifact.relative_to(ROOT)) if artifact.is_absolute() else str(artifact),
                    "metrics": {},
                }
            )
            continue
        run = _load_json(artifact)
        run_metrics = _metrics_from_run(run)
        robustness = _robustness_summary(lane.get("robustness"))
        proof_grade = proof_grade_for_run(run)
        classification = classify_lane(
            run_metrics,
            robustness,
            proof_grade,
            bool(lane.get("include_in_proof_portfolio")),
        )
        rows = normalize_trades(lane, run)
        lane_portfolio_eligible = (
            bool(lane.get("include_in_proof_portfolio"))
            and _is_count_candidate_status(classification["status"])
        )
        for row in rows:
            row["portfolio_eligible"] = bool(row.get("exact_priced")) and lane_portfolio_eligible
        all_rows.extend(rows)
        lane_reports.append(
            {
                "lane_id": lane["lane_id"],
                "family": lane.get("family"),
                "label": lane.get("label"),
                "role": lane.get("role"),
                "decision": lane.get("decision"),
                "include_in_proof_portfolio": bool(lane.get("include_in_proof_portfolio")),
                "source_result_path": str(artifact.relative_to(ROOT)) if artifact.is_absolute() else str(artifact),
                "proof_grade": proof_grade,
                "status": classification["status"],
                "blockers": classification["blockers"],
                "metrics": run_metrics,
                "robustness": robustness,
                "normalized_trade_count": len(rows),
                "portfolio_eligible_trade_count": sum(1 for row in rows if row.get("portfolio_eligible")),
                "notes": lane.get("notes"),
            }
        )

    deduped = dedupe_portfolio_trades(all_rows)
    selected = deduped["selected_trades"]
    combined_metrics = metrics_for_trades(selected)
    by_lane = Counter(str(row.get("lane_id")) for row in selected)
    by_family = Counter(str(row.get("lane_family")) for row in selected)
    quality_gate = build_quality_gate(lane_reports, combined_metrics)

    status_counts = Counter(str(row.get("status")) for row in lane_reports)
    blocker_counts = Counter(blocker for row in lane_reports for blocker in row.get("blockers") or [])

    return {
        "generated_at": _utc_now(),
        "scope": "regular_stock_options_only",
        "target_exact_trades": TARGET_EXACT_TRADES,
        "proof_policy": {
            "counted_proof_grade": "trusted_intraday_opra_nbbo",
            "disallowed_for_proof_count": [
                "daily/EOD-only artifacts",
                "midpoint-only fills",
                "nearest-listed substitutions",
                "underlying bars",
                "option OHLC bars",
                "unresolved candidates",
            ],
        },
        "combined_portfolio": {
            "metrics": combined_metrics,
            "selected_trade_count": len(selected),
            "suppressed_duplicate_trade_count": len(deduped["suppressed_duplicates"]),
            "duplicate_group_count": deduped["duplicate_group_count"],
            "by_lane": dict(sorted(by_lane.items())),
            "by_family": dict(sorted(by_family.items())),
        },
        "quality_gate": quality_gate,
        "side_aware_zero_bid_replay": _side_aware_zero_bid_report(),
        "lane_status_counts": dict(sorted(status_counts.items())),
        "lane_blocker_counts": dict(sorted(blocker_counts.items())),
        "lanes": lane_reports,
        "blocked_lane_specs": _lane_lab_blockers(),
        "selected_trades": selected,
        "suppressed_duplicates": deduped["suppressed_duplicates"],
        "next_actions": [
            "Treat the current combined proof count as the honest starting point, not a production-ready annual capacity estimate.",
            "Do not add daily/EOD research artifacts to the proof count until they are rerun on trusted intraday OPRA/NBBO.",
            "Do not chase 300 until the current 200+ stack clears the quality gate: coverage, robustness, and paper-shadow fills.",
            "Use the side-aware zero-bid replay to decide whether Lane A can be made clean or must be reframed; zero-bid short-leg exits are economic losses, not harmless import gaps.",
            "Keep the tracked-winner intraday rerun visible as a rejected count-expansion scout unless a new causal/contract-selection version clears PF and coverage gates.",
            "Implement or rerun truly separate regular stock lanes only after the current 200+ stack is quality-gated.",
            "Do not promote bearish put, range-breakout, or volatility-expansion probes until they show positive PF on exact intraday evidence.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    combined = report["combined_portfolio"]
    metrics = combined["metrics"]
    lines = [
        "# Regular Options Multi-Lane Portfolio - 2026-05-30",
        "",
        "This report stacks regular stock-options lane evidence without using the AI commodity, crypto, Polymarket, or day-trading lanes.",
        "Only trusted intraday OPRA/NBBO exact rows are counted in the proof portfolio. Count success is separated from clean promotion and production readiness.",
        "",
        "## Count Target Passed, Quality Pending",
        "",
        f"- Exact trades after dedupe: `{metrics['exact_trade_count']}`.",
        f"- Gap to `200`: `{metrics['gap_to_200']}`.",
        f"- Count gate: `{report['quality_gate']['count_status']}`.",
        f"- Overall quality gate: `{report['quality_gate']['overall_status']}`.",
        "- Read: this is not `200 good trades`; it is `200+` count-feasible trusted-intraday rows with unresolved quality blockers.",
        "",
        "## Combined Count Stack",
        "",
        f"- PF: `{metrics['profit_factor']}`.",
        f"- Avg PnL: `{metrics['avg_pnl_pct']}%`.",
        f"- Win rate: `{metrics['win_rate_pct']}%`.",
        f"- Suppressed duplicate exact trades: `{combined['suppressed_duplicate_trade_count']}` across `{combined['duplicate_group_count']}` duplicate groups.",
        f"- By lane: `{json.dumps(combined['by_lane'], sort_keys=True)}`.",
        "",
        "## 200 Quality Gate",
        "",
        f"- Overall: `{report['quality_gate']['overall_status']}`.",
        f"- Count: `{report['quality_gate']['count_status']}`.",
        f"- Coverage: `{report['quality_gate']['coverage_status']}`.",
        f"- Robustness: `{report['quality_gate']['robustness_status']}`.",
        f"- Paper shadow: `{report['quality_gate']['paper_shadow_status']}`.",
        f"- Blockers: `{json.dumps(report['quality_gate']['blockers'])}`.",
        "",
    ]
    side_aware = report.get("side_aware_zero_bid_replay")
    if side_aware:
        modes = side_aware.get("modes") or {}
        conservative = modes.get("conservative") or {}
        midpoint = modes.get("midpoint_zero_bid") or {}
        conservative_side = conservative.get("side_aware_metrics") or {}
        conservative_combined = conservative.get("combined_with_existing_lane_a_metrics") or {}
        midpoint_combined = midpoint.get("combined_with_existing_lane_a_metrics") or {}
        lines.extend(
            [
                "## Lane A Side-Aware Zero-Bid Replay",
                "",
                f"- Artifact: `{side_aware.get('artifact')}`.",
                (
                    f"- Conservative zero-bid mode priced `{conservative.get('priced_count')}` of "
                    f"`{conservative.get('candidate_count')}` missing-exit candidates; "
                    f"`{conservative.get('zero_bid_priced_count')}` priced rows used at least one zero-bid exit quote."
                ),
                (
                    f"- Conservative side-aware rows alone: PF `{conservative_side.get('profit_factor')}`, "
                    f"avg `{conservative_side.get('avg_pnl_pct')}%`, win rate `{conservative_side.get('win_rate_pct')}%`."
                ),
                (
                    f"- Conservative combined Lane A: `{conservative.get('combined_lane_a_priced_count')}` priced, "
                    f"`{conservative.get('combined_lane_a_unpriced_count')}` unpriced, "
                    f"coverage `{conservative.get('combined_lane_a_quote_coverage_pct')}%`, "
                    f"PF `{conservative_combined.get('profit_factor')}`, avg `{conservative_combined.get('avg_pnl_pct')}%`."
                ),
                (
                    f"- Midpoint zero-bid combined Lane A is still weak: PF "
                    f"`{midpoint_combined.get('profit_factor')}`, avg `{midpoint_combined.get('avg_pnl_pct')}%`."
                ),
                "- Read: the missing Lane A exits are mostly adverse zero-bid short-leg states, so the quality blocker is economic, not just a missing-import artifact.",
                "",
            ]
        )
    lines.extend(
        [
            "## Lane Read",
            "",
            "| Lane | Status | Proof grade | Exact | Candidates | Coverage | PF | Avg % | Portfolio exact | Main blockers |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for lane in report["lanes"]:
        metrics = lane.get("metrics") or {}
        blockers = ", ".join(lane.get("blockers") or [])
        lines.append(
            "| "
            + " | ".join(
                [
                    str(lane.get("lane_id")),
                    str(lane.get("status")),
                    str(lane.get("proof_grade") or ""),
                    str(metrics.get("exact_trade_count", "")),
                    str(metrics.get("candidate_trade_count", "")),
                    str(metrics.get("quote_coverage_pct", "")),
                    str(metrics.get("profit_factor", "")),
                    str(metrics.get("avg_pnl_pct", "")),
                    str(lane.get("portfolio_eligible_trade_count", 0)),
                    blockers or "",
                ]
            )
            + " |"
        )

    blocked_specs = report.get("blocked_lane_specs") or []
    if blocked_specs:
        lines.extend(["", "## Blocked Specs", ""])
        for lane in blocked_specs:
            blockers = ", ".join(lane.get("blockers") or [])
            lines.append(f"- `{lane.get('lane_id')}`: `{lane.get('status')}`; blockers: `{blockers or 'none'}`.")

    lines.extend(
        [
            "",
            "## Read",
            "",
            "The refreshed stock-lane stack clears the `200` exact-trade target on strict date+ticker+direction dedupe by combining the current bullish-pullback core with the older Lane A chain-native extension.",
            "",
            "The count is not permission to stop. Lane A improved after exact and lookahead fills, but the side-aware zero-bid replay shows the missing exits are mostly adverse short-leg liquidity states, not harmless missing imports. A contrarian tracked-winner intraday rerun adds a visible 102-exact-trade scout, but its current trusted-intraday economics are below gate at PF `1.36` with `51.8%` coverage, so it is not counted toward the proof portfolio. The bearish, range, and volatility probes have now been rerun on trusted intraday data and rejected on profitability.",
            "",
            "## Next Actions",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report.get("next_actions") or [])
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_dir: Path = OUTPUT_DIR, docs_report: Path = DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"regular_options_multilane_{stamp}.json"
    latest_json = output_dir / "latest.json"
    md_path = output_dir / f"regular_options_multilane_{stamp}.md"
    latest_md = output_dir / "latest.md"
    payload = json.dumps(report, indent=2, sort_keys=True)
    markdown = render_markdown(report)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the regular stock-options multi-lane portfolio report.")
    parser.add_argument("--json", action="store_true", help="Print the generated report as JSON.")
    parser.add_argument("--no-write", action="store_true", help="Build the report without writing artifacts.")
    args = parser.parse_args(argv)

    report = build_report()
    if not args.no_write:
        report["artifacts"] = write_outputs(report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif not args.no_write:
        print(f"wrote {report['artifacts']['latest_json']}")
        print(f"wrote {report['artifacts']['docs_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
