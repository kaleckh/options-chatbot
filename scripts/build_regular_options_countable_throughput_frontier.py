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
REPORT_ID = "regular_options_countable_throughput_frontier"

DEFAULT_ALL_PLANNED = (
    ROOT / "data" / "profitability-lab" / "regular-options-autoresearch" / "all-planned-sleeves" / "latest.json"
)
DEFAULT_MOMENTUM_EDGE = ROOT / "data" / "profitability-lab" / "regular-options-current-regime-momentum-edge" / "latest.json"
DEFAULT_ROBUST_EDGE = ROOT / "data" / "profitability-lab" / "regular-options-robust-edge-discovery" / "latest.json"
DEFAULT_HYPOTHESIS_TOURNAMENT = ROOT / "data" / "profitability-lab" / "regular-options-hypothesis-tournament" / "latest.json"
DEFAULT_WALK_FORWARD = ROOT / "data" / "profitability-lab" / "regular-options-historical-walk-forward" / "latest.json"
DEFAULT_EVIDENCE_BURNDOWN = ROOT / "data" / "profitability-lab" / "regular-options-evidence-blocker-burndown" / "latest.json"
DEFAULT_SOURCE_REPLAY = ROOT / "data" / "profitability-lab" / "regular-options-source-replay-pass" / "latest.json"
DEFAULT_MONTHLY_PROFITABILITY = ROOT / "data" / "forward-tracking" / "monthly_all_lanes_profitability_audit_latest.json"
DEFAULT_ROBUST_SEARCH = ROOT / "data" / "profitability-lab" / "regular-options-robust-search-evaluation" / "latest.json"

DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-countable-throughput-frontier"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-countable-throughput-frontier.md"
DEFAULT_ARTIFACT_JSON = ROOT / "artifacts" / "regular-options-countable-throughput-frontier.json"

BASE_CLEAN_STACK_EXACT_ROWS = 157
TARGET_EXACT_ROWS = 200
STRICT_NEW_GAP_REQUIRED = 43

READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
    "live_entry_allowed": False,
    "auto_track_allowed": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
}

PROHIBITED_ACTIONS = (
    "do_not_create_trades",
    "do_not_submit_broker_orders",
    "do_not_enable_auto_track",
    "do_not_enable_live_validation",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic_for_release",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_import_quotes",
    "do_not_mutate_evidence_databases",
    "do_not_consume_protected_holdout",
    "do_not_promote_any_lane",
    "do_not_count_raw_overlapping_rows",
    "do_not_treat_historical_rows_as_forward_proof",
    "do_not_treat_midpoint_stale_eod_display_manual_last_or_model_marks_as_executable_proof",
    "do_not_drop_zero_bid_untradable_or_unpriced_rows_as_missing_data",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "") or isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "") or isinstance(value, bool):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _round(value: Any, digits: int = 4) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, digits) if parsed is not None else None


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {"path": _rel(path), "required": required, "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return {}, meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    meta["report_id"] = payload.get("report_id")
    return payload, meta


def _load_run(path_value: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(str(path_value or ""))
    meta = {"path": _rel(path) if str(path_value or "") else "", "exists": bool(path_value) and path.exists(), "status": "missing"}
    if not path_value or not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (json.JSONDecodeError, OSError) as exc:
        meta["status"] = type(exc).__name__
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        return {}, meta
    meta["status"] = "loaded"
    return payload, meta


def _profit_factor(values: list[float]) -> float | None:
    gross_win = sum(v for v in values if v > 0)
    gross_loss = abs(sum(v for v in values if v < 0))
    if gross_loss == 0:
        return None if gross_win == 0 else 999.0
    return round(gross_win / gross_loss, 4)


def _concentration_from_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    positive = [_safe_float(row.get("net_pnl_pct")) or _safe_float(row.get("pnl_pct")) or 0.0 for row in trades]
    positive = [value for value in positive if value > 0]
    total_positive = sum(positive)
    by_month: dict[str, float] = defaultdict(float)
    by_underlying: dict[str, float] = defaultdict(float)
    by_expiration: dict[str, float] = defaultdict(float)
    for row in trades:
        pnl = _safe_float(row.get("net_pnl_pct")) or _safe_float(row.get("pnl_pct")) or 0.0
        if pnl <= 0:
            continue
        date = str(row.get("date") or "")
        by_month[date[:7] if len(date) >= 7 else "unknown"] += pnl
        by_underlying[str(row.get("ticker") or row.get("underlying") or "unknown")] += pnl
        expiry = str(row.get("long_entry_expiry") or row.get("expiration") or row.get("exit_date") or "unknown")
        by_expiration[expiry] += pnl

    def share(value: float) -> float:
        return round((value / total_positive) * 100.0, 2) if total_positive > 0 else 0.0

    top = sorted(positive, reverse=True)
    return {
        "max_single_trade_profit_share": share(top[0]) if top else 0.0,
        "top_5_trade_profit_share": share(sum(top[:5])) if top else 0.0,
        "max_month_profit_share": share(max(by_month.values(), default=0.0)),
        "max_underlying_profit_share": share(max(by_underlying.values(), default=0.0)),
        "max_expiration_profit_share": share(max(by_expiration.values(), default=0.0)),
    }


def _worst_remaining_pf(robustness: dict[str, Any]) -> float | None:
    values: list[float] = []
    for key in ("date_holdout_worst", "month_holdout_worst", "symbol_holdout_worst", "top_winner_removal"):
        for row in _as_list(robustness.get(key)):
            metrics = _as_dict(row.get("remaining_metrics"))
            pf = _safe_float(metrics.get("profit_factor"))
            if pf is not None:
                values.append(pf)
    stress_values = [_safe_float(row.get("metrics", {}).get("profit_factor")) for row in _as_list(robustness.get("slippage_stress"))]
    values.extend(value for value in stress_values if value is not None)
    return round(min(values), 4) if values else None


def _variant_to_frontier_candidate(variant: dict[str, Any]) -> dict[str, Any]:
    metrics = _as_dict(variant.get("standalone_metrics"))
    novelty = _as_dict(variant.get("novelty_vs_core_plus_clean_reference"))
    incremental = _as_dict(novelty.get("incremental_metrics"))
    robustness_summary = _as_dict(variant.get("robustness"))
    run, run_meta = _load_run(variant.get("run_path"))
    robustness, robustness_meta = _load_run(variant.get("robustness_path"))
    trades = [_as_dict(row) for row in _as_list(run.get("trades"))]
    unpriced_trades = [_as_dict(row) for row in _as_list(run.get("unpriced_trades"))]
    concentration = _concentration_from_trades(trades)
    lower_bound = _worst_remaining_pf(robustness)
    exact_rows = _safe_int(metrics.get("exact_trade_count") or run.get("priced_trade_count"))
    strict_new_rows = _safe_int(novelty.get("strict_new_trade_count"))
    with_rows = _safe_int(novelty.get("with_candidate_trade_count"), BASE_CLEAN_STACK_EXACT_ROWS + strict_new_rows)
    strict_new_pf = _round(incremental.get("profit_factor"))
    point_pf = _round(metrics.get("profit_factor") or run.get("profit_factor"))
    stress_pf = _round(robustness_summary.get("stress_5pct_per_side_profit_factor"))
    return {
        "candidate_id": str(variant.get("variant_id") or ""),
        "candidate_family": str(variant.get("lane_id") or "all_planned_variant"),
        "source_family": "all_planned_variant",
        "description": variant.get("description"),
        "run_path": _rel(Path(str(variant.get("run_path")))) if variant.get("run_path") else None,
        "run_ledger_status": run_meta.get("status"),
        "robustness_ledger_status": robustness_meta.get("status"),
        "exact_rows": exact_rows,
        "raw_rows": _safe_int(metrics.get("candidate_trade_count"), exact_rows + len(unpriced_trades)),
        "strict_new_rows": strict_new_rows,
        "strict_new_rows_after_opportunity_dedupe": strict_new_rows,
        "with_candidate_exact_rows": with_rows,
        "point_profit_factor": point_pf,
        "strict_new_profit_factor": strict_new_pf,
        "combined_profit_factor": point_pf,
        "profit_factor_lower_bound": lower_bound,
        "strict_new_profit_factor_lower_bound": None,
        "average_net_pnl_pct": _round(metrics.get("avg_pnl_pct")),
        "strict_new_average_net_pnl_pct": _round(incremental.get("avg_pnl_pct")),
        "stress_profit_factor": stress_pf,
        "strict_new_stress_profit_factor": stress_pf if strict_new_rows >= STRICT_NEW_GAP_REQUIRED else None,
        "final_holdout_exact_rows": 0,
        "final_holdout_profit_factor_lower_bound": None,
        "quote_coverage_pct": _round(metrics.get("quote_coverage_pct") or run.get("quote_coverage_pct")),
        "unpriced_rows": _safe_int(metrics.get("unpriced_trade_count"), len(unpriced_trades)),
        "zero_bid_rows": sum(1 for row in unpriced_trades if "zero" in str(row.get("unpriced_reason") or "").lower()),
        "untradable_rows": sum(1 for row in unpriced_trades if "tradable" in str(row.get("unpriced_reason") or "").lower()),
        "lookahead_only_rows": 0,
        "source_miss_rows": len(unpriced_trades),
        "rolling_status": robustness_summary.get("rolling_status"),
        "monthly_profitability_status": "unknown",
        "worth_status": variant.get("worth_status"),
        "opportunity_dedupe_source": "all_planned_summary_strict_new_count",
        "strict_new_row_ledger_available": False,
        **concentration,
    }


def _classify_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    row = dict(candidate)
    blockers: list[str] = []
    strict_new = _safe_int(row.get("strict_new_rows_after_opportunity_dedupe") or row.get("strict_new_rows"))
    with_rows = _safe_int(row.get("with_candidate_exact_rows"), BASE_CLEAN_STACK_EXACT_ROWS + strict_new)
    pf = _safe_float(row.get("point_profit_factor"))
    strict_pf = _safe_float(row.get("strict_new_profit_factor"))
    combined_pf = _safe_float(row.get("combined_profit_factor"))
    pf_lb = _safe_float(row.get("profit_factor_lower_bound"))
    strict_pf_lb = _safe_float(row.get("strict_new_profit_factor_lower_bound"))
    stress_pf = _safe_float(row.get("stress_profit_factor"))
    strict_stress_pf = _safe_float(row.get("strict_new_stress_profit_factor"))
    avg = _safe_float(row.get("average_net_pnl_pct"))
    strict_avg = _safe_float(row.get("strict_new_average_net_pnl_pct"))
    coverage = _safe_float(row.get("quote_coverage_pct"))
    unpriced = _safe_int(row.get("unpriced_rows"))
    zero_bid = _safe_int(row.get("zero_bid_rows"))
    untradable = _safe_int(row.get("untradable_rows"))
    lookahead = _safe_int(row.get("lookahead_only_rows"))
    final_holdout = _safe_int(row.get("final_holdout_exact_rows"))
    final_holdout_lb = _safe_float(row.get("final_holdout_profit_factor_lower_bound"))
    rolling = str(row.get("rolling_status") or "").lower()
    monthly = str(row.get("monthly_profitability_status") or "").lower()

    row["base_clean_stack_exact_rows"] = BASE_CLEAN_STACK_EXACT_ROWS
    row["target_exact_rows"] = TARGET_EXACT_ROWS
    row["strict_new_gap_required"] = STRICT_NEW_GAP_REQUIRED
    row["count_gap_closed"] = with_rows >= TARGET_EXACT_ROWS and strict_new >= STRICT_NEW_GAP_REQUIRED

    if lookahead > 0:
        blockers.append(f"lookahead_only_rows_{lookahead}")
        row["decision"] = "diagnostic_only_lookahead_or_unpriced"
    elif strict_new < STRICT_NEW_GAP_REQUIRED or with_rows < TARGET_EXACT_ROWS:
        blockers.append(f"strict_new_rows_{strict_new}_below_required_{STRICT_NEW_GAP_REQUIRED}")
        blockers.append(f"with_candidate_rows_{with_rows}_below_target_{TARGET_EXACT_ROWS}" if with_rows < TARGET_EXACT_ROWS else "strict_new_gap_not_closed")
        row["decision"] = "blocked_below_strict_new_count"
    elif pf is None or pf <= 1.0 or (avg is not None and avg <= 0):
        blockers.append("point_profitability_not_positive")
        row["decision"] = "rejected_negative_or_flat_edge"
    elif coverage is None or coverage < 90.0 or unpriced > 0 or zero_bid > 0 or untradable > 0:
        if coverage is None:
            blockers.append("quote_coverage_missing")
        elif coverage < 90.0:
            blockers.append(f"quote_coverage_{coverage}_below_90")
        if unpriced:
            blockers.append(f"unpriced_rows_{unpriced}")
        if zero_bid:
            blockers.append(f"zero_bid_rows_{zero_bid}")
        if untradable:
            blockers.append(f"untradable_rows_{untradable}")
        row["decision"] = "blocked_execution_quality"
    elif combined_pf is not None and combined_pf >= 1.25 and (strict_pf is None or strict_pf < 1.20):
        blockers.append(f"strict_new_profit_factor_{strict_pf}_below_1.20")
        row["decision"] = "rejected_base_subsidized_only"
    elif combined_pf is not None and combined_pf >= 1.25 and strict_avg is not None and strict_avg <= 0:
        blockers.append("strict_new_average_net_pnl_not_positive")
        row["decision"] = "rejected_base_subsidized_only"
    elif combined_pf is None or combined_pf < 1.25 or strict_pf is None or strict_pf < 1.20:
        blockers.append("profitability_gate_failed")
        row["decision"] = "rejected_negative_or_flat_edge"
    elif pf_lb is None or pf_lb <= 1.0 or strict_pf_lb is None or strict_pf_lb <= 1.0:
        blockers.append("profit_factor_lower_bound_missing_or_not_above_1")
        row["decision"] = "blocked_profitability_lower_bound"
    elif stress_pf is None or stress_pf < 1.05 or strict_stress_pf is None or strict_stress_pf < 1.0 or rolling in {"watch", "fail", "fragile"} or monthly in {"winner_concentrated", "single_month_dependent", "fragile"}:
        blockers.append("stress_or_rolling_gate_failed")
        row["decision"] = "blocked_stress_fragility"
    elif final_holdout < 30 or final_holdout_lb is None or final_holdout_lb <= 1.0:
        blockers.append("final_holdout_depth_or_lower_bound_failed")
        row["decision"] = "blocked_holdout_depth"
    elif (
        (_safe_float(row.get("max_single_trade_profit_share")) or 0.0) > 20.0
        or (_safe_float(row.get("top_5_trade_profit_share")) or 0.0) > 50.0
        or (_safe_float(row.get("max_month_profit_share")) or 0.0) > 35.0
        or (_safe_float(row.get("max_underlying_profit_share")) or 0.0) > 50.0
        or (_safe_float(row.get("max_expiration_profit_share")) or 0.0) > 40.0
    ):
        blockers.append("concentration_red_flag")
        row["decision"] = "blocked_concentration_dependency"
    else:
        row["decision"] = "countable_throughput_candidate_for_forward_freeze_review"

    if row.get("run_ledger_status") != "loaded":
        blockers.append("run_level_trade_ledger_missing")
    if not row.get("strict_new_row_ledger_available"):
        blockers.append("strict_new_row_level_identity_ledger_missing")
    row["blockers"] = sorted(set(blockers))
    return row


def _candidate_rows(all_planned: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [_classify_candidate(_variant_to_frontier_candidate(_as_dict(item))) for item in _as_list(all_planned.get("variants"))]
    order = {
        "countable_throughput_candidate_for_forward_freeze_review": 0,
        "blocked_execution_quality": 1,
        "blocked_profitability_lower_bound": 2,
        "blocked_stress_fragility": 3,
        "blocked_holdout_depth": 4,
        "blocked_below_strict_new_count": 5,
        "rejected_base_subsidized_only": 6,
        "rejected_negative_or_flat_edge": 7,
        "diagnostic_only_lookahead_or_unpriced": 8,
    }
    return sorted(
        rows,
        key=lambda row: (
            order.get(str(row.get("decision")), 99),
            -_safe_int(row.get("strict_new_rows_after_opportunity_dedupe")),
            -_safe_int(row.get("with_candidate_exact_rows")),
            str(row.get("candidate_id")),
        ),
    )


def _overall_status(candidates: list[dict[str, Any]], source_artifacts: dict[str, dict[str, Any]]) -> str:
    if any(meta.get("required") and meta.get("status") != "loaded" for meta in source_artifacts.values()):
        return "blocked_missing_source_artifact"
    if any(row.get("decision") == "countable_throughput_candidate_for_forward_freeze_review" for row in candidates):
        return "countable_throughput_candidate_found_research_only"
    return "current_historical_surface_exhausted_under_current_prohibitions"


def build_report(
    *,
    all_planned_path: Path = DEFAULT_ALL_PLANNED,
    momentum_edge_path: Path = DEFAULT_MOMENTUM_EDGE,
    robust_edge_path: Path = DEFAULT_ROBUST_EDGE,
    hypothesis_tournament_path: Path = DEFAULT_HYPOTHESIS_TOURNAMENT,
    walk_forward_path: Path = DEFAULT_WALK_FORWARD,
    evidence_burndown_path: Path = DEFAULT_EVIDENCE_BURNDOWN,
    source_replay_path: Path = DEFAULT_SOURCE_REPLAY,
    monthly_profitability_path: Path = DEFAULT_MONTHLY_PROFITABILITY,
    robust_search_path: Path = DEFAULT_ROBUST_SEARCH,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    all_planned, all_planned_meta = _load_json(all_planned_path, required=True)
    momentum_edge, momentum_meta = _load_json(momentum_edge_path, required=True)
    robust_edge, robust_edge_meta = _load_json(robust_edge_path, required=False)
    hypothesis, hypothesis_meta = _load_json(hypothesis_tournament_path, required=False)
    walk_forward, walk_forward_meta = _load_json(walk_forward_path, required=False)
    evidence, evidence_meta = _load_json(evidence_burndown_path, required=False)
    source_replay, source_replay_meta = _load_json(source_replay_path, required=False)
    monthly, monthly_meta = _load_json(monthly_profitability_path, required=False)
    robust_search, robust_search_meta = _load_json(robust_search_path, required=False)
    source_artifacts = {
        "all_planned_sleeves": all_planned_meta,
        "current_regime_momentum_edge": momentum_meta,
        "robust_edge": robust_edge_meta,
        "hypothesis_tournament": hypothesis_meta,
        "walk_forward": walk_forward_meta,
        "evidence_blocker_burndown": evidence_meta,
        "source_replay_pass": source_replay_meta,
        "monthly_profitability": monthly_meta,
        "robust_search": robust_search_meta,
    }
    candidates = _candidate_rows(all_planned)
    pass_rows = [row for row in candidates if row.get("decision") == "countable_throughput_candidate_for_forward_freeze_review"]
    raw_count_rows = [row for row in candidates if row.get("count_gap_closed")]
    counts = Counter(str(row.get("decision")) for row in candidates)
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": _overall_status(candidates, source_artifacts),
        **READ_ONLY_FLAGS,
        "scope": "read_only_countable_throughput_frontier_falsification",
        "is_trade_recommendation": False,
        "base_clean_stack_exact_rows": BASE_CLEAN_STACK_EXACT_ROWS,
        "target_exact_rows": TARGET_EXACT_ROWS,
        "strict_new_gap_required": STRICT_NEW_GAP_REQUIRED,
        "countable_throughput_candidate_found": bool(pass_rows),
        "current_historical_surface_exhausted_under_current_prohibitions": not bool(pass_rows),
        "forward_freeze_review_candidate": bool(pass_rows),
        "row_level_candidate_ledger_status": "run_trade_ledgers_loaded_where_available_strict_new_identity_summary_only",
        "source_artifacts": source_artifacts,
        "upstream_status": {
            "current_regime_momentum_edge": momentum_edge.get("status"),
            "robust_edge": robust_edge.get("overall_status"),
            "hypothesis_tournament": hypothesis.get("overall_status"),
            "walk_forward": walk_forward.get("status"),
            "evidence_blocker_burndown": evidence.get("status"),
            "source_replay_pass": source_replay.get("status"),
            "monthly_profitability": monthly.get("status"),
            "robust_search": robust_search.get("status"),
        },
        "candidate_count": len(candidates),
        "raw_count_candidate_count": len(raw_count_rows),
        "decision_counts": dict(sorted(counts.items())),
        "candidate_rankings": candidates,
        "strict_new_tranche_profitability": [
            {
                "candidate_id": row.get("candidate_id"),
                "candidate_family": row.get("candidate_family"),
                "strict_new_rows_after_opportunity_dedupe": row.get("strict_new_rows_after_opportunity_dedupe"),
                "strict_new_profit_factor": row.get("strict_new_profit_factor"),
                "strict_new_profit_factor_lower_bound": row.get("strict_new_profit_factor_lower_bound"),
                "strict_new_stress_profit_factor": row.get("strict_new_stress_profit_factor"),
                "strict_new_average_net_pnl_pct": row.get("strict_new_average_net_pnl_pct"),
                "decision": row.get("decision"),
            }
            for row in candidates
        ],
        "blocker_table": [
            {
                "candidate_id": row.get("candidate_id"),
                "decision": row.get("decision"),
                "with_candidate_exact_rows": row.get("with_candidate_exact_rows"),
                "strict_new_rows_after_opportunity_dedupe": row.get("strict_new_rows_after_opportunity_dedupe"),
                "point_profit_factor": row.get("point_profit_factor"),
                "strict_new_profit_factor": row.get("strict_new_profit_factor"),
                "stress_profit_factor": row.get("stress_profit_factor"),
                "quote_coverage_pct": row.get("quote_coverage_pct"),
                "unpriced_rows": row.get("unpriced_rows"),
                "blockers": row.get("blockers"),
            }
            for row in raw_count_rows
        ],
        "known_current_regime_reproductions": {
            "tracked_winner_chain_native_research_all_sleeves": "blocked despite 269 combined rows because coverage/unpriced/stress/rolling gates fail",
            "sleeve_next_index_refill_v1": "blocked despite PF 1.74, stress PF 1.33, and 100% coverage because it adds only 6 strict-new rows",
        },
        "required_next_approval_if_exhausted": [
            "operator_approval_for_fresh_forward_paper_shadow_collection",
            "operator_approval_for_scoped_source_repair_or_replay",
            "operator_approval_for_new_causal_playbook_generation",
            "operator_approval_for_new_historical_data_surface_or_longer_lookback",
        ],
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report.get("accepted_profitability") is not False:
        raise ValueError("frontier report cannot accept profitability")
    if report.get("promotion_ready") is not False:
        raise ValueError("frontier report cannot promote")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Countable Throughput Frontier",
        "",
        "This report is generated from `scripts/build_regular_options_countable_throughput_frontier.py`. It is a read-only falsification artifact over existing historical candidates. It does not create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/stops/sizing/proof bars, run live validation, enable auto-track, submit broker orders, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Countable throughput candidate found: `{_fmt_bool(report['countable_throughput_candidate_found'])}`.",
        f"- Current historical surface exhausted under current prohibitions: `{_fmt_bool(report['current_historical_surface_exhausted_under_current_prohibitions'])}`.",
        f"- Base clean stack exact rows: `{report['base_clean_stack_exact_rows']}`.",
        f"- Target exact rows: `{report['target_exact_rows']}`.",
        f"- Strict-new gap required: `{report['strict_new_gap_required']}`.",
        f"- Candidate count: `{report['candidate_count']}`.",
        f"- Raw count candidates: `{report['raw_count_candidate_count']}`.",
        f"- Decision counts: `{json.dumps(report['decision_counts'], sort_keys=True)}`.",
        f"- Row-level ledger status: `{report['row_level_candidate_ledger_status']}`.",
        "",
        "## Candidate Frontier",
        "",
        "| Candidate | Family | Decision | Exact | Strict New | With Base | PF | Strict PF | PF LB | Stress PF | Coverage | Unpriced | Blockers |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in _as_list(report.get("candidate_rankings")):
        row = _as_dict(row)
        blockers = ", ".join(str(item) for item in _as_list(row.get("blockers")))[:280]
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.get('candidate_id')}`",
                    f"`{row.get('candidate_family')}`",
                    f"`{row.get('decision')}`",
                    str(row.get("exact_rows")),
                    str(row.get("strict_new_rows_after_opportunity_dedupe")),
                    str(row.get("with_candidate_exact_rows")),
                    str(row.get("point_profit_factor")),
                    str(row.get("strict_new_profit_factor")),
                    str(row.get("profit_factor_lower_bound")),
                    str(row.get("stress_profit_factor")),
                    str(row.get("quote_coverage_pct")),
                    str(row.get("unpriced_rows")),
                    blockers,
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Strict-New Tranche Profitability",
            "",
            "| Candidate | Strict New | Strict PF | Strict PF LB | Strict Stress PF | Strict Avg P&L % | Decision |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in _as_list(report.get("strict_new_tranche_profitability")):
        row = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.get('candidate_id')}`",
                    str(row.get("strict_new_rows_after_opportunity_dedupe")),
                    str(row.get("strict_new_profit_factor")),
                    str(row.get("strict_new_profit_factor_lower_bound")),
                    str(row.get("strict_new_stress_profit_factor")),
                    str(row.get("strict_new_average_net_pnl_pct")),
                    f"`{row.get('decision')}`",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Raw Count Blockers", ""])
    if _as_list(report.get("blocker_table")):
        lines.extend(
            [
                "| Candidate | With Base | Strict New | PF | Stress PF | Coverage | Unpriced | Decision | Blockers |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for row in _as_list(report.get("blocker_table")):
            row = _as_dict(row)
            blockers = ", ".join(str(item) for item in _as_list(row.get("blockers")))[:320]
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{row.get('candidate_id')}`",
                        str(row.get("with_candidate_exact_rows")),
                        str(row.get("strict_new_rows_after_opportunity_dedupe")),
                        str(row.get("point_profit_factor")),
                        str(row.get("stress_profit_factor")),
                        str(row.get("quote_coverage_pct")),
                        str(row.get("unpriced_rows")),
                        f"`{row.get('decision')}`",
                        blockers,
                    ]
                )
                + " |"
            )
    else:
        lines.append("- No candidate closes the strict-new count gap.")
    lines.extend(
        [
            "",
            "## Stop Verdict",
            "",
            f"- `countable_throughput_candidate_found`: `{_fmt_bool(report['countable_throughput_candidate_found'])}`.",
            f"- `current_historical_surface_exhausted_under_current_prohibitions`: `{_fmt_bool(report['current_historical_surface_exhausted_under_current_prohibitions'])}`.",
            "- If the stop verdict is true, the next loop needs a separate operator approval gate for fresh forward paper-shadow collection, scoped source repair/replay, a new causal playbook, or a new historical data surface/longer lookback.",
            "",
            "## Prohibited Actions",
            "",
        ]
    )
    lines.extend(f"- `{action}`" for action in report["prohibited_actions"])
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
    artifact_json: Path = DEFAULT_ARTIFACT_JSON,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    artifact_json.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{stamp}.json"
    md_path = output_dir / f"{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
        "artifact_json": _rel(artifact_json),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    markdown = render_markdown(report_with_artifacts)
    for path in (json_path, latest_json, artifact_json):
        path.write_text(json.dumps(report_with_artifacts, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the read-only regular-options countable throughput frontier.")
    parser.add_argument("--all-planned", type=Path, default=DEFAULT_ALL_PLANNED)
    parser.add_argument("--momentum-edge", type=Path, default=DEFAULT_MOMENTUM_EDGE)
    parser.add_argument("--robust-edge", type=Path, default=DEFAULT_ROBUST_EDGE)
    parser.add_argument("--hypothesis-tournament", type=Path, default=DEFAULT_HYPOTHESIS_TOURNAMENT)
    parser.add_argument("--walk-forward", type=Path, default=DEFAULT_WALK_FORWARD)
    parser.add_argument("--evidence-burndown", type=Path, default=DEFAULT_EVIDENCE_BURNDOWN)
    parser.add_argument("--source-replay", type=Path, default=DEFAULT_SOURCE_REPLAY)
    parser.add_argument("--monthly-profitability", type=Path, default=DEFAULT_MONTHLY_PROFITABILITY)
    parser.add_argument("--robust-search", type=Path, default=DEFAULT_ROBUST_SEARCH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--artifact-json", type=Path, default=DEFAULT_ARTIFACT_JSON)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        all_planned_path=args.all_planned,
        momentum_edge_path=args.momentum_edge,
        robust_edge_path=args.robust_edge,
        hypothesis_tournament_path=args.hypothesis_tournament,
        walk_forward_path=args.walk_forward,
        evidence_burndown_path=args.evidence_burndown,
        source_replay_path=args.source_replay,
        monthly_profitability_path=args.monthly_profitability,
        robust_search_path=args.robust_search,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(
            report,
            output_dir=args.output_dir,
            docs_report=args.docs_report,
            artifact_json=args.artifact_json,
        )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
