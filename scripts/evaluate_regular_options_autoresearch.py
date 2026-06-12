from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


MULTILANE_LATEST = ROOT / "data" / "profitability-lab" / "regular-options-multilane" / "latest.json"
OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-autoresearch"
LEDGER_PATH = OUTPUT_DIR / "ledger.jsonl"

EVALUATOR_VERSION = "regular-options-autoresearch-v2"
TARGET_CLEAN_TRADES = 200
COUNT_CANDIDATE_STATUSES = {"count_candidate", "portfolio_candidate"}
BOOTSTRAP_DRAWS = 10_000
BOOTSTRAP_SEED = "regular-options-autoresearch-bootstrap-v1"

PROMOTION_GATES: dict[str, Any] = {
    "clean_trade_count_min": TARGET_CLEAN_TRADES,
    "profit_factor_min": 1.50,
    "avg_pnl_pct_min_exclusive": 0.0,
    "effective_quote_coverage_pct_min": 97.5,
    "effective_unresolved_count_max": 0,
    "stress_5pct_profit_factor_min": 1.25,
    "rolling_oos_required_status": "passed",
    "zero_bid_exit_rate_pct_max": 2.0,
    "lane_a_conservative_profit_factor_min": 1.30,
}

PRODUCTION_EXTRA_GATES: dict[str, Any] = {
    "paper_shadow_status_required": "passed",
}

EVALUATOR_CONFIG: dict[str, Any] = {
    "version": EVALUATOR_VERSION,
    "scope": "regular_stock_options_only",
    "promotion_gates": PROMOTION_GATES,
    "production_extra_gates": PRODUCTION_EXTRA_GATES,
    "score_policy": {
        "score_is_zero_until_promotable_clean": True,
        "progress_score_is_diagnostic_triage_only": True,
        "bootstrap_confidence_is_diagnostic_only": True,
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "progress_score_inputs": [
            "promotable_clean_count",
            "conservative_profit_factor",
            "stress_5pct_profit_factor",
            "zero_bid_exit_rate_pct",
        ],
        "research_score_is_diagnostic_only": True,
        "research_score_excludes_trade_count_and_quote_coverage": True,
        "side_aware_zero_bid_replay_is_required_when_lane_a_is_counted": True,
        "daily_eod_midpoint_or_unresolved_rows_do_not_count": True,
    },
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def _round_optional(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return round(parsed, digits)


def evaluator_config_hash() -> str:
    encoded = json.dumps(EVALUATOR_CONFIG, sort_keys=True).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def load_or_build_multilane_report(*, refresh: bool, write_refreshed: bool) -> dict[str, Any]:
    if refresh or not MULTILANE_LATEST.exists():
        from scripts.run_regular_options_multilane_portfolio import build_report, write_outputs

        report = build_report()
        if write_refreshed:
            report["artifacts"] = write_outputs(report)
        return report
    return _load_json(MULTILANE_LATEST)


def _included_lanes(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        lane
        for lane in report.get("lanes") or []
        if lane.get("include_in_proof_portfolio") and str(lane.get("status") or "") in COUNT_CANDIDATE_STATUSES
    ]


def _lane_a_is_counted(lanes: list[dict[str, Any]]) -> bool:
    return any(str(lane.get("lane_id") or "").startswith("lane_a_") for lane in lanes)


def _conservative_zero_bid_mode(report: dict[str, Any]) -> dict[str, Any]:
    side_aware = report.get("side_aware_zero_bid_replay")
    if not isinstance(side_aware, dict):
        return {}
    modes = side_aware.get("modes")
    if not isinstance(modes, dict):
        return {}
    conservative = modes.get("conservative")
    return conservative if isinstance(conservative, dict) else {}


def _lane_candidate_count(lane: dict[str, Any]) -> int:
    return _safe_int((lane.get("metrics") or {}).get("candidate_trade_count"))


def _lane_exact_count(lane: dict[str, Any]) -> int:
    return _safe_int((lane.get("metrics") or {}).get("exact_trade_count"))


def _lane_unpriced_count(lane: dict[str, Any]) -> int:
    return _safe_int((lane.get("metrics") or {}).get("unpriced_trade_count"))


def _reported_lane_coverage(lanes: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = sum(_lane_candidate_count(lane) for lane in lanes)
    exact = sum(_lane_exact_count(lane) for lane in lanes)
    unresolved = sum(_lane_unpriced_count(lane) for lane in lanes)
    return {
        "candidate_count": candidates,
        "priced_or_exact_count": exact,
        "unresolved_count": unresolved,
        "coverage_pct": round((100.0 * exact / candidates), 2) if candidates else 0.0,
    }


def _effective_lane_coverage(lanes: list[dict[str, Any]], conservative: dict[str, Any]) -> dict[str, Any]:
    if not conservative:
        return _reported_lane_coverage(lanes)

    candidates = 0
    priced = 0
    unresolved = 0
    for lane in lanes:
        lane_id = str(lane.get("lane_id") or "")
        if lane_id.startswith("lane_a_"):
            candidates += _safe_int(conservative.get("combined_lane_a_candidate_count"), _lane_candidate_count(lane))
            priced += _safe_int(conservative.get("combined_lane_a_priced_count"), _lane_exact_count(lane))
            unresolved += _safe_int(conservative.get("combined_lane_a_unpriced_count"), _lane_unpriced_count(lane))
        else:
            candidates += _lane_candidate_count(lane)
            priced += _lane_exact_count(lane)
            unresolved += _lane_unpriced_count(lane)
    return {
        "candidate_count": candidates,
        "priced_or_exact_count": priced,
        "unresolved_count": unresolved,
        "coverage_pct": round((100.0 * priced / candidates), 2) if candidates else 0.0,
    }


def _stress_floor(lanes: list[dict[str, Any]]) -> float:
    values = [
        _safe_float((lane.get("robustness") or {}).get("stress_5pct_per_side_profit_factor"))
        for lane in lanes
        if (lane.get("robustness") or {}).get("stress_5pct_per_side_profit_factor") is not None
    ]
    return round(min(values), 2) if values else 0.0


def _net_pnl_pct_value(trade: dict[str, Any]) -> float | None:
    value = trade.get("net_pnl_pct", trade.get("pnl_pct"))
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _profit_factor_point(values: list[float]) -> float | None:
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss <= 0.0:
        return None
    return gross_win / gross_loss


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    index = max(0, min(len(sorted_values) - 1, math.ceil(float(pct) * len(sorted_values)) - 1))
    return sorted_values[index]


def _bootstrap_seed(label: str, values: list[float]) -> int:
    payload = json.dumps(
        {"label": label, "seed": BOOTSTRAP_SEED, "values": [round(value, 6) for value in values]},
        sort_keys=True,
    ).encode("utf8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def bootstrap_confidence_for_values(
    values: list[float],
    *,
    branch_id: str,
    draws: int = BOOTSTRAP_DRAWS,
) -> dict[str, Any]:
    clean_values = [float(value) for value in values if math.isfinite(float(value))]
    n_trades = len(clean_values)
    pf_point = _profit_factor_point(clean_values)
    avg_point = sum(clean_values) / n_trades if n_trades else None
    pf_draws: list[float] = []
    avg_draws: list[float] = []

    if n_trades:
        rng = random.Random(_bootstrap_seed(branch_id, clean_values))
        for _ in range(int(draws)):
            sample = [clean_values[rng.randrange(n_trades)] for _ in range(n_trades)]
            sample_pf = _profit_factor_point(sample)
            if sample_pf is not None:
                pf_draws.append(sample_pf)
            avg_draws.append(sum(sample) / n_trades)

    pf_draws.sort()
    avg_draws.sort()
    pf_lb = _percentile(pf_draws, 0.05)
    pf_ub = _percentile(pf_draws, 0.95)
    avg_lb = _percentile(avg_draws, 0.05)

    if pf_lb is not None and pf_point is not None and pf_lb < 1.0 and pf_point >= 1.2:
        confidence = "underpowered"
    elif pf_lb is not None and pf_lb > 1.0:
        confidence = "confident_positive"
    else:
        confidence = "negative_or_flat"

    return {
        "branch_id": branch_id,
        "draws": int(draws),
        "n_trades": n_trades,
        "pf_point": _round_optional(pf_point),
        "pf_lb_5pct": _round_optional(pf_lb),
        "pf_ub_95pct": _round_optional(pf_ub),
        "avg_net_point": _round_optional(avg_point),
        "avg_net_lb_5pct": _round_optional(avg_lb),
        "statistical_confidence": confidence,
        "pf_defined_draws": len(pf_draws),
        "no_loss_sample": bool(n_trades and pf_point is None and any(value > 0.0 for value in clean_values)),
    }


def _bootstrap_confidence(report: dict[str, Any]) -> dict[str, Any]:
    selected = [
        dict(trade)
        for trade in report.get("selected_trades") or []
        if dict(trade).get("exact_priced", dict(trade).get("priced", True))
    ]
    combined_values = [value for trade in selected if (value := _net_pnl_pct_value(trade)) is not None]
    combined = bootstrap_confidence_for_values(combined_values, branch_id="combined_portfolio")

    grouped: dict[str, list[float]] = defaultdict(list)
    for trade in selected:
        value = _net_pnl_pct_value(trade)
        if value is None:
            continue
        branch_id = str(trade.get("lane_id") or "unknown")
        grouped[branch_id].append(value)

    branch_rows = [
        bootstrap_confidence_for_values(values, branch_id=branch_id)
        for branch_id, values in sorted(grouped.items())
    ]
    return {
        "combined": combined,
        "branches": branch_rows,
        "policy": {
            "level": "trade_level_with_replacement",
            "draws": BOOTSTRAP_DRAWS,
            "seed": BOOTSTRAP_SEED,
            "pnl_basis": "net_pnl_pct",
            "diagnostic_only": True,
        },
    }


def _rolling_blocked_lanes(lanes: list[dict[str, Any]]) -> list[str]:
    blocked: list[str] = []
    for lane in lanes:
        rolling = str((lane.get("robustness") or {}).get("rolling_status") or "").strip().lower()
        if rolling != PROMOTION_GATES["rolling_oos_required_status"]:
            blocked.append(str(lane.get("lane_id") or "unknown"))
    return blocked


def _zero_bid_metrics(conservative: dict[str, Any]) -> dict[str, Any]:
    if not conservative:
        return {
            "available": False,
            "zero_bid_priced_count": 0,
            "zero_bid_exit_rate_pct": None,
            "zero_bid_missing_exit_rate_pct": None,
            "lane_a_conservative_profit_factor": None,
            "lane_a_conservative_avg_pnl_pct": None,
        }

    zero_bid = _safe_int(conservative.get("zero_bid_priced_count"))
    priced = _safe_int(conservative.get("priced_count"))
    combined_priced = _safe_int(conservative.get("combined_lane_a_priced_count"))
    combined_metrics = conservative.get("combined_with_existing_lane_a_metrics") or {}
    return {
        "available": True,
        "zero_bid_priced_count": zero_bid,
        "zero_bid_exit_rate_pct": round(100.0 * zero_bid / combined_priced, 2) if combined_priced else None,
        "zero_bid_missing_exit_rate_pct": round(100.0 * zero_bid / priced, 2) if priced else None,
        "lane_a_conservative_profit_factor": _round(combined_metrics.get("profit_factor")),
        "lane_a_conservative_avg_pnl_pct": _round(combined_metrics.get("avg_pnl_pct")),
    }


def build_metric_snapshot(report: dict[str, Any]) -> dict[str, Any]:
    combined = report.get("combined_portfolio") or {}
    combined_metrics = combined.get("metrics") or {}
    quality_gate = report.get("quality_gate") or {}
    lanes = _included_lanes(report)
    conservative = _conservative_zero_bid_mode(report)
    reported_coverage = _reported_lane_coverage(lanes)
    effective_coverage = _effective_lane_coverage(lanes, conservative)
    zero_bid = _zero_bid_metrics(conservative)
    bootstrap = _bootstrap_confidence(report)
    bootstrap_combined = bootstrap["combined"]

    return {
        "scope": report.get("scope"),
        "scout_count": _safe_int(combined_metrics.get("exact_trade_count")),
        "promotable_clean_count": 0,
        "profit_factor": _round(combined_metrics.get("profit_factor")),
        "avg_pnl_pct": _round(combined_metrics.get("avg_pnl_pct")),
        "win_rate_pct": _round(combined_metrics.get("win_rate_pct")),
        "effective_quote_coverage_pct": effective_coverage["coverage_pct"],
        "reported_quote_coverage_pct": reported_coverage["coverage_pct"],
        "effective_candidate_count": effective_coverage["candidate_count"],
        "effective_priced_or_exact_count": effective_coverage["priced_or_exact_count"],
        "effective_unresolved_count": effective_coverage["unresolved_count"],
        "reported_unresolved_count": reported_coverage["unresolved_count"],
        "stress_5pct_profit_factor": _stress_floor(lanes),
        "rolling_blocked_lanes": _rolling_blocked_lanes(lanes),
        "duplicate_group_count": _safe_int(combined.get("duplicate_group_count")),
        "suppressed_duplicate_trade_count": _safe_int(combined.get("suppressed_duplicate_trade_count")),
        "quality_gate_overall": quality_gate.get("overall_status"),
        "paper_shadow_status": quality_gate.get("paper_shadow_status"),
        "included_lane_ids": [str(lane.get("lane_id") or "") for lane in lanes],
        "lane_a_is_counted": _lane_a_is_counted(lanes),
        "pf_point": bootstrap_combined.get("pf_point"),
        "pf_lb_5pct": bootstrap_combined.get("pf_lb_5pct"),
        "pf_ub_95pct": bootstrap_combined.get("pf_ub_95pct"),
        "avg_net_lb_5pct": bootstrap_combined.get("avg_net_lb_5pct"),
        "n_trades": bootstrap_combined.get("n_trades"),
        "statistical_confidence": bootstrap_combined.get("statistical_confidence"),
        "bootstrap_confidence": bootstrap,
        **zero_bid,
    }


def promotion_blockers(metrics: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if metrics.get("scope") != "regular_stock_options_only":
        blockers.append("scope_not_regular_stock_options_only")
    if _safe_int(metrics.get("scout_count")) < PROMOTION_GATES["clean_trade_count_min"]:
        blockers.append(f"clean_trade_count_below_{PROMOTION_GATES['clean_trade_count_min']}")
    if _safe_float(metrics.get("profit_factor")) < PROMOTION_GATES["profit_factor_min"]:
        blockers.append("profit_factor_below_1_50")
    if _safe_float(metrics.get("avg_pnl_pct")) <= PROMOTION_GATES["avg_pnl_pct_min_exclusive"]:
        blockers.append("avg_pnl_not_positive")
    if _safe_float(metrics.get("effective_quote_coverage_pct")) < PROMOTION_GATES["effective_quote_coverage_pct_min"]:
        blockers.append("effective_quote_coverage_below_97_5")
    if _safe_int(metrics.get("effective_unresolved_count")) > PROMOTION_GATES["effective_unresolved_count_max"]:
        blockers.append("effective_unresolved_candidates_remain")
    if _safe_float(metrics.get("stress_5pct_profit_factor")) < PROMOTION_GATES["stress_5pct_profit_factor_min"]:
        blockers.append("stress_5pct_profit_factor_below_1_25")
    rolling_blocked = list(metrics.get("rolling_blocked_lanes") or [])
    if rolling_blocked:
        blockers.append("rolling_oos_not_passed:" + ",".join(rolling_blocked))
    if metrics.get("lane_a_is_counted"):
        if not metrics.get("available"):
            blockers.append("side_aware_zero_bid_replay_missing_for_counted_lane_a")
        zero_bid_rate = metrics.get("zero_bid_exit_rate_pct")
        if zero_bid_rate is None or _safe_float(zero_bid_rate) > PROMOTION_GATES["zero_bid_exit_rate_pct_max"]:
            blockers.append("zero_bid_exit_rate_above_2pct")
        lane_a_pf = metrics.get("lane_a_conservative_profit_factor")
        if lane_a_pf is None or _safe_float(lane_a_pf) < PROMOTION_GATES["lane_a_conservative_profit_factor_min"]:
            blockers.append("lane_a_conservative_pf_below_1_30")
    return blockers


def production_blockers(metrics: dict[str, Any], historical_blockers: list[str]) -> list[str]:
    blockers = list(historical_blockers)
    required = PRODUCTION_EXTRA_GATES["paper_shadow_status_required"]
    if str(metrics.get("paper_shadow_status") or "").lower() != required:
        blockers.append(f"paper_shadow_status_not_{required}")
    return blockers


def _quality_multiplier(metrics: dict[str, Any]) -> float:
    pf_mult = min(_safe_float(metrics.get("profit_factor")) / PROMOTION_GATES["profit_factor_min"], 2.0)
    stress_mult = min(_safe_float(metrics.get("stress_5pct_profit_factor")) / PROMOTION_GATES["stress_5pct_profit_factor_min"], 1.5)
    coverage_mult = min(_safe_float(metrics.get("effective_quote_coverage_pct")) / 100.0, 1.0)
    avg_bonus = min(max(_safe_float(metrics.get("avg_pnl_pct")), 0.0) / 100.0, 0.5)
    zero_bid_rate = _safe_float(metrics.get("zero_bid_exit_rate_pct"), 0.0)
    zero_bid_mult = max(0.0, 1.0 - zero_bid_rate / 100.0)
    return round(max(0.0, pf_mult * stress_mult * coverage_mult * (1.0 + avg_bonus) * zero_bid_mult), 4)


def _research_score(metrics: dict[str, Any]) -> float:
    lane_a_pf = metrics.get("lane_a_conservative_profit_factor")
    lane_a_penalty = 100.0 if lane_a_pf is not None and _safe_float(lane_a_pf) < 1.0 else 0.0
    score = (
        max(0.0, _safe_float(metrics.get("profit_factor")) - 1.0) * 50.0
        + max(0.0, _safe_float(metrics.get("avg_pnl_pct")))
        + max(0.0, _safe_float(metrics.get("stress_5pct_profit_factor")) - 1.0) * 25.0
        - _safe_float(metrics.get("effective_unresolved_count")) * 3.0
        - _safe_float(metrics.get("zero_bid_exit_rate_pct"), 0.0) * 2.0
        - len(metrics.get("rolling_blocked_lanes") or []) * 25.0
        - lane_a_penalty
    )
    return round(score, 2)


def _progress_conservative_profit_factor(metrics: dict[str, Any]) -> float:
    lane_a_pf = metrics.get("lane_a_conservative_profit_factor")
    if lane_a_pf is not None:
        return _safe_float(lane_a_pf)
    return _safe_float(metrics.get("profit_factor"))


def _progress_score(metrics: dict[str, Any]) -> float:
    clean_count = _safe_float(metrics.get("promotable_clean_count"))
    conservative_pf = _progress_conservative_profit_factor(metrics)
    stress_pf = _safe_float(metrics.get("stress_5pct_profit_factor"))
    zero_bid_rate = metrics.get("zero_bid_exit_rate_pct")

    clean_component = min(clean_count / float(TARGET_CLEAN_TRADES), 1.0) * 40.0
    pf_component = min(max(conservative_pf - 1.0, 0.0) / 0.5, 1.0) * 30.0
    stress_component = min(max(stress_pf - 1.0, 0.0) / 0.25, 1.0) * 20.0
    if zero_bid_rate is None:
        zero_bid_component = 10.0 if not metrics.get("lane_a_is_counted") else 0.0
    else:
        parsed_zero_bid = _safe_float(zero_bid_rate, 50.0)
        zero_bid_component = 10.0 if parsed_zero_bid <= 2.0 else max(0.0, 10.0 * (1.0 - (parsed_zero_bid / 50.0)))
    return round(clean_component + pf_component + stress_component + zero_bid_component, 2)


def build_scoreboard(
    report: dict[str, Any],
    *,
    experiment_id: str,
    hypothesis: str,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    metrics = build_metric_snapshot(report)
    historical_blockers = promotion_blockers(metrics)
    production_gate_blockers = production_blockers(metrics, historical_blockers)
    historical_status = "promotable_clean" if not historical_blockers else "scout_or_blocked"
    production_status = "production_ready" if not production_gate_blockers else "not_production_ready"
    clean_count = _safe_int(metrics.get("scout_count")) if historical_status == "promotable_clean" else 0
    metrics["promotable_clean_count"] = clean_count
    multiplier = _quality_multiplier(metrics) if historical_status == "promotable_clean" else 0.0
    score = round(clean_count * multiplier, 2) if historical_status == "promotable_clean" else 0.0
    progress_score = _progress_score(metrics)

    scoreboard = {
        "generated_at_utc": generated_at_utc or _utc_now(),
        "evaluator_version": EVALUATOR_VERSION,
        "evaluator_config_hash": evaluator_config_hash(),
        "experiment_id": experiment_id,
        "hypothesis": hypothesis,
        "status": historical_status,
        "production_status": production_status,
        "score": score,
        "progress_score": progress_score,
        "research_score": _research_score(metrics),
        "quality_multiplier": multiplier,
        "metrics": metrics,
        "promotion_gates": PROMOTION_GATES,
        "production_extra_gates": PRODUCTION_EXTRA_GATES,
        "promotion_blockers": historical_blockers,
        "production_blockers": production_gate_blockers,
        "read": _read(score, historical_status, historical_blockers, metrics),
    }
    scoreboard["score_line"] = format_score_line(scoreboard)
    return scoreboard


def _read(score: float, status: str, blockers: list[str], metrics: dict[str, Any]) -> str:
    if status == "promotable_clean":
        if metrics.get("paper_shadow_status") == "passed":
            return "The stack clears the frozen historical and paper-shadow gates."
        return "The stack clears the frozen historical gates but still needs paper-shadow evidence."
    if "lane_a_conservative_pf_below_1_30" in blockers:
        return "Blocked primarily by Lane A zero-bid survivability; do not count the 234 stack as clean."
    if score <= 0:
        return "Blocked by frozen promotion gates; use progress_score and blockers only for experiment triage."
    return "Scout evidence exists, but it is not promotable clean evidence."


def format_score_line(scoreboard: dict[str, Any]) -> str:
    metrics = scoreboard.get("metrics") or {}
    blockers = ",".join(scoreboard.get("promotion_blockers") or []) or "none"
    lane_a_pf = metrics.get("lane_a_conservative_profit_factor")
    zero_bid = metrics.get("zero_bid_exit_rate_pct")
    pf_lb = metrics.get("pf_lb_5pct")
    avg_lb = metrics.get("avg_net_lb_5pct")
    pf_lb_text = "n/a" if pf_lb is None else f"{_round(pf_lb):.2f}"
    avg_lb_text = "n/a" if avg_lb is None else f"{_round(avg_lb):.2f}"
    return (
        f"score: {_round(scoreboard.get('score')):.2f} "
        f"progress_score: {_round(scoreboard.get('progress_score')):.2f} "
        f"research_score: {_round(scoreboard.get('research_score')):.2f} "
        f"status: {scoreboard.get('status')} "
        f"production_status: {scoreboard.get('production_status')} "
        f"clean_count: {_safe_int(metrics.get('promotable_clean_count'))} "
        f"scout_count: {_safe_int(metrics.get('scout_count'))} "
        f"pf: {_round(metrics.get('profit_factor')):.2f} "
        f"avg_return: {_round(metrics.get('avg_pnl_pct')):.2f} "
        f"coverage: {_round(metrics.get('effective_quote_coverage_pct')):.2f} "
        f"unresolved: {_safe_int(metrics.get('effective_unresolved_count'))} "
        f"stress_pf: {_round(metrics.get('stress_5pct_profit_factor')):.2f} "
        f"pf_lb_5pct: {pf_lb_text} "
        f"avg_net_lb_5pct: {avg_lb_text} "
        f"stat_conf: {metrics.get('statistical_confidence')} "
        f"zero_bid_exit_rate: {('n/a' if zero_bid is None else f'{_round(zero_bid):.2f}')} "
        f"lane_a_zero_bid_pf: {('n/a' if lane_a_pf is None else f'{_round(lane_a_pf):.2f}')} "
        f"blockers: {blockers}"
    )


def _ledger_entry(scoreboard: dict[str, Any]) -> dict[str, Any]:
    metrics = scoreboard.get("metrics") or {}
    return {
        "generated_at_utc": scoreboard.get("generated_at_utc"),
        "evaluator_version": scoreboard.get("evaluator_version"),
        "evaluator_config_hash": scoreboard.get("evaluator_config_hash"),
        "experiment_id": scoreboard.get("experiment_id"),
        "hypothesis": scoreboard.get("hypothesis"),
        "status": scoreboard.get("status"),
        "production_status": scoreboard.get("production_status"),
        "score": scoreboard.get("score"),
        "progress_score": scoreboard.get("progress_score"),
        "research_score": scoreboard.get("research_score"),
        "clean_count": metrics.get("promotable_clean_count"),
        "scout_count": metrics.get("scout_count"),
        "profit_factor": metrics.get("profit_factor"),
        "pf_point": metrics.get("pf_point"),
        "pf_lb_5pct": metrics.get("pf_lb_5pct"),
        "pf_ub_95pct": metrics.get("pf_ub_95pct"),
        "avg_net_lb_5pct": metrics.get("avg_net_lb_5pct"),
        "n_trades": metrics.get("n_trades"),
        "statistical_confidence": metrics.get("statistical_confidence"),
        "avg_pnl_pct": metrics.get("avg_pnl_pct"),
        "effective_quote_coverage_pct": metrics.get("effective_quote_coverage_pct"),
        "effective_unresolved_count": metrics.get("effective_unresolved_count"),
        "stress_5pct_profit_factor": metrics.get("stress_5pct_profit_factor"),
        "zero_bid_exit_rate_pct": metrics.get("zero_bid_exit_rate_pct"),
        "lane_a_conservative_profit_factor": metrics.get("lane_a_conservative_profit_factor"),
        "promotion_blockers": scoreboard.get("promotion_blockers"),
        "production_blockers": scoreboard.get("production_blockers"),
    }


def append_ledger(scoreboard: dict[str, Any], *, path: Path = LEDGER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf8") as handle:
        handle.write(json.dumps(_ledger_entry(scoreboard), sort_keys=True) + "\n")


def render_markdown(scoreboard: dict[str, Any]) -> str:
    metrics = scoreboard.get("metrics") or {}
    bootstrap = metrics.get("bootstrap_confidence") or {}
    branches = bootstrap.get("branches") or []
    lines = [
        "# Regular Options Autoresearch Scoreboard",
        "",
        f"- Generated: `{scoreboard.get('generated_at_utc')}`",
        f"- Experiment: `{scoreboard.get('experiment_id')}`",
        f"- Hypothesis: `{scoreboard.get('hypothesis')}`",
        f"- Evaluator: `{scoreboard.get('evaluator_version')}`",
        f"- Evaluator config hash: `{scoreboard.get('evaluator_config_hash')}`",
        "",
        "## Score Line",
        "",
        f"`{scoreboard.get('score_line')}`",
        "",
        "## Status",
        "",
        f"- Historical clean status: `{scoreboard.get('status')}`",
        f"- Production status: `{scoreboard.get('production_status')}`",
        f"- Score: `{scoreboard.get('score')}`",
        f"- Progress score: `{scoreboard.get('progress_score')}`",
        f"- Research score: `{scoreboard.get('research_score')}`",
        f"- Read: {scoreboard.get('read')}",
        "",
        "## Metrics",
        "",
        f"- Clean count: `{metrics.get('promotable_clean_count')}`",
        f"- Scout count: `{metrics.get('scout_count')}`",
        f"- PF: `{metrics.get('profit_factor')}`",
        f"- Bootstrap PF point: `{metrics.get('pf_point')}`",
        f"- Bootstrap PF 5% lower bound: `{metrics.get('pf_lb_5pct')}`",
        f"- Bootstrap PF 95% upper bound: `{metrics.get('pf_ub_95pct')}`",
        f"- Bootstrap avg net 5% lower bound: `{metrics.get('avg_net_lb_5pct')}%`",
        f"- Bootstrap trades: `{metrics.get('n_trades')}`",
        f"- Statistical confidence: `{metrics.get('statistical_confidence')}`",
        f"- Avg PnL: `{metrics.get('avg_pnl_pct')}%`",
        f"- Effective coverage: `{metrics.get('effective_quote_coverage_pct')}%`",
        f"- Effective unresolved candidates: `{metrics.get('effective_unresolved_count')}`",
        f"- Stress PF: `{metrics.get('stress_5pct_profit_factor')}`",
        f"- Zero-bid exit rate: `{metrics.get('zero_bid_exit_rate_pct')}`",
        f"- Lane A conservative PF: `{metrics.get('lane_a_conservative_profit_factor')}`",
        "",
        "## Promotion Blockers",
        "",
    ]
    blockers = list(scoreboard.get("promotion_blockers") or [])
    lines.extend(f"- `{item}`" for item in blockers) if blockers else lines.append("- None.")
    if branches:
        lines.extend(
            [
                "",
                "## Branch Bootstrap Diagnostics",
                "",
                "| Branch | N | PF point | PF LB 5% | PF UB 95% | Avg net LB 5% | Confidence |",
                "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for row in branches:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row.get("branch_id")),
                        str(row.get("n_trades")),
                        str(row.get("pf_point")),
                        str(row.get("pf_lb_5pct")),
                        str(row.get("pf_ub_95pct")),
                        str(row.get("avg_net_lb_5pct")),
                        str(row.get("statistical_confidence")),
                    ]
                )
                + " |"
            )
    lines.extend(["", "## Production Blockers", ""])
    production = list(scoreboard.get("production_blockers") or [])
    lines.extend(f"- `{item}`" for item in production) if production else lines.append("- None.")
    lines.extend(
        [
            "",
            "## Frozen Evaluator Rule",
            "",
            "During a `/goal` run, do not edit this evaluator, its gates, or the ledger schema. Strategy experiments may change strategy/replay code, but the judge stays fixed until a human explicitly updates it outside the run.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(scoreboard: dict[str, Any], *, output_dir: Path = OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"regular_options_autoresearch_{stamp}.json"
    md_path = output_dir / f"regular_options_autoresearch_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    payload = json.dumps(scoreboard, indent=2, sort_keys=True)
    markdown = render_markdown(scoreboard)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    return {
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the regular stock-options autoresearch scoreboard.")
    parser.add_argument("--refresh-multilane", action="store_true", help="Regenerate the multi-lane report before scoring.")
    parser.add_argument("--no-write", action="store_true", help="Do not write scoreboard artifacts.")
    parser.add_argument("--append-ledger", action="store_true", help="Append a compact row to the experiment ledger.")
    parser.add_argument("--experiment-id", default="baseline-current-stack", help="Stable experiment id for ledger rows.")
    parser.add_argument("--hypothesis", default="Current regular stock-options multi-lane stack.", help="One-line hypothesis under test.")
    parser.add_argument("--json", action="store_true", help="Print the full scoreboard JSON.")
    parser.add_argument("--score-line", action="store_true", help="Print only the compact score line.")
    args = parser.parse_args(argv)

    report = load_or_build_multilane_report(refresh=args.refresh_multilane, write_refreshed=not args.no_write)
    scoreboard = build_scoreboard(
        report,
        experiment_id=args.experiment_id,
        hypothesis=args.hypothesis,
    )
    if not args.no_write:
        scoreboard["artifacts"] = write_outputs(scoreboard)
    if args.append_ledger:
        append_ledger(scoreboard)

    if args.json:
        print(json.dumps(scoreboard, indent=2, sort_keys=True))
    else:
        print(scoreboard["score_line"])
        if not args.no_write and not args.score_line:
            print(f"wrote {scoreboard['artifacts']['latest_json']}")
            if args.append_ledger:
                print(f"appended {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
