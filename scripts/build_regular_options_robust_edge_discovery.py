from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_robust_edge_discovery"

DEFAULT_ROBUST_SEARCH = ROOT / "data" / "profitability-lab" / "regular-options-robust-search-evaluation" / "latest.json"
DEFAULT_WALK_FORWARD = ROOT / "data" / "profitability-lab" / "regular-options-historical-walk-forward" / "latest.json"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_MONTHLY_AUDIT = ROOT / "data" / "forward-tracking" / "monthly_all_lanes_profitability_audit_latest.json"
DEFAULT_TRADE_QUALIFICATION = ROOT / "data" / "forward-tracking" / "regular_options_trade_qualification_latest.json"
DEFAULT_PAPER_SHADOW_PLAN = ROOT / "data" / "forward-tracking" / "regular_options_paper_shadow_evidence_plan_latest.json"
DEFAULT_MARKET_WINDOW_CHECKLIST = ROOT / "data" / "forward-tracking" / "regular_options_market_window_evidence_checklist_latest.json"
DEFAULT_LANE_PROMOTION = ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.json"
DEFAULT_MISSED_FILTER_MATRIX = ROOT / "data" / "forward-tracking" / "missed_regular_picks_filter_matrix_latest.json"
DEFAULT_MISSED_OUTCOMES = ROOT / "data" / "forward-tracking" / "missed_regular_picks_outcome_latest.json"
DEFAULT_MISSED_FAILURES = ROOT / "data" / "forward-tracking" / "missed_regular_picks_failure_modes_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-robust-edge-discovery"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-robust-edge-discovery.md"

MAX_SOURCE_AGE_HOURS = 96
MIN_TOTAL_EXACT_ROWS = 200
MIN_FINAL_HOLDOUT_ROWS = 30
MAX_CONCENTRATION_PCT = 60.0
MIN_PF_LB = 1.0

TRUSTED_EXECUTION_CLASSES = {
    "trusted_intraday_opra_nbbo",
    "trusted_opra_nbbo",
    "executable_exact_options",
    "exact_bid_ask",
}

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_robust_edge_discovery",
    "do_not_submit_broker_orders_from_robust_edge_discovery",
    "do_not_enable_auto_track_from_robust_edge_discovery",
    "do_not_enable_live_validation_from_robust_edge_discovery",
    "do_not_change_scanner_policy_from_robust_edge_discovery",
    "do_not_change_stops_from_robust_edge_discovery",
    "do_not_change_sizing_from_robust_edge_discovery",
    "do_not_lower_proof_bars_from_robust_edge_discovery",
    "do_not_mutate_evidence_databases_from_robust_edge_discovery",
    "do_not_treat_historical_research_rows_as_live_proof",
    "do_not_count_midpoint_eod_stale_manual_display_last_or_model_marks_as_proof",
)

REQUIRED_EVIDENCE_BEFORE_LIVE_DISCUSSION = (
    "frozen candidate algorithm spec with no post-hoc rule edits",
    "at least 30 post-freeze exact realized paper-shadow rows",
    "fresh executable exact OPRA/NBBO entry evidence for each forward row",
    "policy-defined executable exact OPRA/NBBO exit evidence for each forward row",
    "positive forward net P&L after fees and executable pricing",
    "forward paper profit-factor lower bound above 1.0",
    "no open-risk governor blocker",
    "no source-quality, unpriced, midpoint, stale, EOD, display-only, manual, last-trade, or model proof contamination",
)

NON_GOALS = (
    "prove future profits with certainty",
    "create trades",
    "submit broker orders",
    "enable auto-track",
    "enable live validation",
    "change scanner policy",
    "change stops",
    "change sizing",
    "lower proof bars",
    "mutate evidence databases",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return path.name


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: Any, digits: int = 2) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, digits) if parsed is not None else None


def _unique(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _norm(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _load_json_artifact(
    path: Path,
    *,
    name: str,
    required: bool,
    generated_at_utc: str,
    max_age_hours: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source = {
        "path": _rel(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "age_hours": None,
        "reason_codes": ["missing_readback"],
        "error": None,
    }
    if not path.exists():
        return {}, source
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        source["status"] = "malformed"
        source["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        source["reason_codes"] = ["malformed_readback"]
        return {}, source
    except OSError as exc:
        source["status"] = "unreadable"
        source["error"] = type(exc).__name__
        source["reason_codes"] = ["unreadable_readback"]
        return {}, source
    if not isinstance(payload, dict):
        source["status"] = "invalid"
        source["reason_codes"] = ["json_root_not_object"]
        return {}, source

    source["generated_at_utc"] = payload.get("generated_at_utc")
    as_of = _parse_utc(generated_at_utc) or datetime.now(UTC)
    generated = _parse_utc(payload.get("generated_at_utc"))
    if generated is None:
        source["status"] = "stale"
        source["reason_codes"] = ["missing_or_malformed_generated_at_utc", "stale_readback"]
        return payload, source
    age_hours = (as_of - generated).total_seconds() / 3600
    source["age_hours"] = round(age_hours, 2)
    if age_hours < -1:
        source["status"] = "invalid"
        source["reason_codes"] = ["readback_generated_in_future"]
        return payload, source
    if age_hours > max_age_hours:
        source["status"] = "stale"
        source["reason_codes"] = ["stale_readback"]
        return payload, source

    source["status"] = "loaded"
    source["reason_codes"] = []
    source["report_id"] = payload.get("report_id") or name
    return payload, source


def _source_block_status(source_artifacts: dict[str, dict[str, Any]]) -> str | None:
    bad = [meta for meta in source_artifacts.values() if meta.get("required") and meta.get("status") != "loaded"]
    if not bad:
        return None
    if any(meta.get("status") == "stale" or "stale_readback" in _as_list(meta.get("reason_codes")) for meta in bad):
        return "blocked_stale_readbacks"
    return "blocked_missing_readbacks"


def _metric(metrics: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in metrics:
            return metrics.get(name)
    return None


def _empty_candidate(candidate_id: str, lane_id: str, strategy_family: str, rule_summary: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "lane_id": lane_id,
        "strategy_family": strategy_family,
        "rule_summary": rule_summary,
        "sample_window_start": None,
        "sample_window_end": None,
        "train_rows": 0,
        "validation_rows": 0,
        "holdout_rows": 0,
        "total_exact_rows": 0,
        "priced_rows": 0,
        "unpriced_rows": 0,
        "profit_factor": None,
        "profit_factor_lower_bound": None,
        "avg_net_pnl_pct": None,
        "median_net_pnl_pct": None,
        "net_pnl_usd": None,
        "win_rate_pct": None,
        "max_drawdown_pct": None,
        "deep_loss_counts": {},
        "ticker_concentration": {"status": "not_available"},
        "month_concentration": {"status": "not_available"},
        "regime_summary": {"status": "not_available"},
        "execution_evidence_class": "trusted_intraday_opra_nbbo",
        "source_quality_status": "unknown",
        "stress_results": {},
        "decision": "insufficient_data",
        "reason_codes": [],
        "next_step": "",
    }


def _concentration_status(concentration: dict[str, Any]) -> tuple[bool, str | None]:
    pct = _safe_float(
        concentration.get("top_profit_share_pct")
        or concentration.get("top_ticker_profit_share_pct")
        or concentration.get("top_month_profit_share_pct")
    )
    if pct is None:
        return False, None
    if pct > MAX_CONCENTRATION_PCT:
        return True, f"top_concentration_{round(pct, 2)}_above_{MAX_CONCENTRATION_PCT}"
    return False, None


def _stress_failed(stress_results: dict[str, Any]) -> bool:
    values = [
        stress_results.get("top_1_removed_profit_factor"),
        stress_results.get("top_3_removed_profit_factor"),
        stress_results.get("top_5_removed_profit_factor"),
        stress_results.get("wider_spread_profit_factor"),
        stress_results.get("stress_5pct_per_side_profit_factor"),
    ]
    return any((_safe_float(value) is not None and float(value) < 1.0) for value in values)


def _classify_candidate(candidate: dict[str, Any], *, source_status_blocked: bool) -> tuple[str, list[str], str]:
    reasons = list(_as_list(candidate.get("reason_codes")))
    blockers = [str(item) for item in _as_list(candidate.get("source_blockers")) + _as_list(candidate.get("blockers"))]
    reasons.extend(blockers)
    evidence_class = _norm(candidate.get("execution_evidence_class")).lower()
    if source_status_blocked:
        return "blocked_missing_readbacks", _unique([*reasons, "required_source_readback_not_loaded"]), "Refresh required readbacks before classifying this candidate."
    if evidence_class and evidence_class not in TRUSTED_EXECUTION_CLASSES:
        return "execution_fragile_reject", _unique([*reasons, f"non_executable_evidence_class:{evidence_class}"]), "Reject until executable exact OPRA/NBBO-style evidence replaces non-executable marks."
    if candidate.get("paper_shadow_source"):
        return "paper_shadow_candidate", _unique([*reasons, "paper_shadow_or_probation_only", "not_historical_robust_proof"]), "Freeze no live behavior; collect fresh exact paper entry and exact realized exit evidence."
    if candidate.get("quarantine_source"):
        return "quarantine_no_chase", _unique([*reasons, "quarantine_or_no_chase_active"]), "Keep parked; do not chase or refreeze without explicit earn-back evidence."
    if candidate.get("needs_replay_engine_source"):
        return "needs_replay_engine", _unique([*reasons, "replay_engine_or_source_repair_required"]), "Repair replay/source evidence before reading profitability."

    unpriced = _safe_int(candidate.get("unpriced_rows"))
    if unpriced > 0 or any("unpriced" in item for item in blockers):
        return "repair_needed", _unique([*reasons, f"unpriced_rows_{unpriced}" if unpriced else "unpriced_rows_present"]), "Repair source-quality or unpriced rows before any nomination."
    if any("quote_coverage" in item or "zero_bid" in item for item in blockers):
        return "execution_fragile_reject", _unique([*reasons, "execution_or_liquidity_fragility"]), "Reject or repair execution-quality failure before considering a forward freeze."

    total = _safe_int(candidate.get("total_exact_rows"))
    holdout = _safe_int(candidate.get("holdout_rows"))
    pf = _safe_float(candidate.get("profit_factor"))
    if total == 0:
        return "insufficient_data", _unique([*reasons, "no_exact_rows"]), "Wait for exact priced rows; do not infer an edge from missing evidence."
    if pf is not None and pf <= 1.0:
        return "overfit_reject", _unique([*reasons, "point_profit_factor_not_above_1"]), "Reject until point profitability is positive after costs."
    if total < MIN_TOTAL_EXACT_ROWS or holdout < MIN_FINAL_HOLDOUT_ROWS:
        return "thin_sample_watch", _unique([*reasons, f"total_exact_rows_{total}_or_holdout_rows_{holdout}_below_gate"]), "Collect more pre-holdout exact rows or future frozen-forward rows; do not promote."

    month_bad, month_reason = _concentration_status(_as_dict(candidate.get("month_concentration")))
    if month_bad:
        return "regime_fragile_reject", _unique([*reasons, month_reason or "month_concentration_above_gate"]), "Reject as month/regime-concentrated until a broader split proves durable."
    ticker_bad, ticker_reason = _concentration_status(_as_dict(candidate.get("ticker_concentration")))
    if ticker_bad:
        return "ticker_concentrated_reject", _unique([*reasons, ticker_reason or "ticker_concentration_above_gate"]), "Reject or split the candidate; profits are too concentrated."

    pf_lb = _safe_float(candidate.get("profit_factor_lower_bound"))
    if pf_lb is None or pf_lb <= MIN_PF_LB:
        return "overfit_reject", _unique([*reasons, "profit_factor_lower_bound_not_above_1"]), "Reject until downside bootstrap/stress lower bound clears 1.0."
    if _stress_failed(_as_dict(candidate.get("stress_results"))):
        return "overfit_reject", _unique([*reasons, "top_winner_or_slippage_stress_failed"]), "Reject until top-winner and execution stress tests remain profitable."
    if str(candidate.get("source_quality_status") or "").endswith("blocked"):
        return "blocked_source_quality", _unique([*reasons, "source_quality_gate_blocked"]), "Repair source quality before forward-freeze discussion."
    if not bool(candidate.get("historical_nomination_ready", False)) and candidate.get("source_family") == "robust_search":
        return "overfit_reject", _unique([*reasons, "existing_historical_nomination_ready_false"]), "Preserve existing promotion_ready=false; do not reinterpret blocked robust-search rows optimistically."
    return "robust_candidate_for_forward_freeze", _unique([*reasons, "all_strict_historical_gates_passed"]), "Freeze the exact algorithm spec for forward paper validation only."


def _robust_candidate_rows(robust: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _as_list(robust.get("candidates")):
        source = _as_dict(item)
        splits = _as_dict(source.get("split_metrics"))
        combined = _as_dict(splits.get("combined"))
        train = _as_dict(splits.get("train"))
        validation = _as_dict(splits.get("validation"))
        final = _as_dict(splits.get("final_holdout"))
        final_bootstrap = _as_dict(final.get("bootstrap"))
        combined_risk = _as_dict(combined.get("risk"))
        candidate_id = _norm(source.get("candidate_id"))
        lane_id = candidate_id.replace("lane:", "") if candidate_id.startswith("lane:") else candidate_id
        candidate = _empty_candidate(
            candidate_id=candidate_id,
            lane_id=lane_id,
            strategy_family=_norm(source.get("candidate_type")) or "historical_robust_search",
            rule_summary="Existing robust-search chronological split candidate; rules are owned by the upstream robust-search artifact.",
        )
        candidate.update(
            {
                "source_family": "robust_search",
                "sample_window_start": combined.get("first_entry_date"),
                "sample_window_end": combined.get("latest_entry_date"),
                "train_rows": _safe_int(train.get("exact_trade_count")),
                "validation_rows": _safe_int(validation.get("exact_trade_count")),
                "holdout_rows": _safe_int(final.get("exact_trade_count")),
                "total_exact_rows": _safe_int(combined.get("exact_trade_count")),
                "priced_rows": _safe_int(combined.get("exact_trade_count")),
                "unpriced_rows": _safe_int(source.get("unpriced_rows")),
                "profit_factor": _round(combined.get("profit_factor"), 4),
                "profit_factor_lower_bound": _round(final_bootstrap.get("pf_lb_5pct"), 4),
                "avg_net_pnl_pct": _round(combined.get("avg_pnl_pct")),
                "median_net_pnl_pct": _round(combined.get("median_pnl_pct")),
                "win_rate_pct": _round(combined.get("win_rate_pct")),
                "max_drawdown_pct": _round(combined_risk.get("max_drawdown_pct_points")),
                "deep_loss_counts": _as_dict(combined_risk.get("deep_loss_counts")),
                "execution_evidence_class": source.get("execution_evidence_class") or "trusted_intraday_opra_nbbo",
                "source_quality_status": _as_dict(source.get("source_quality_gate")).get("status"),
                "source_blockers": _as_list(source.get("blockers")),
                "historical_nomination_ready": bool(source.get("historical_nomination_ready")),
                "regime_summary": _as_dict(source.get("regime_check")),
                "stress_results": source.get("stress_results") or {
                    "final_holdout_pf_lb_5pct": final_bootstrap.get("pf_lb_5pct"),
                    "statistical_confidence": final_bootstrap.get("statistical_confidence"),
                },
                "ticker_concentration": _as_dict(source.get("ticker_concentration")) or {"status": "not_available"},
                "month_concentration": _as_dict(source.get("month_concentration")) or {"status": "not_available"},
            }
        )
        rows.append(candidate)
    return rows


def _variant_candidate_rows(walk: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _as_list(walk.get("variant_rows")):
        source = _as_dict(item)
        candidate_id = _norm(source.get("variant_id"))
        candidate = _empty_candidate(
            candidate_id=candidate_id,
            lane_id=_norm(source.get("lane_id")),
            strategy_family=_norm(source.get("runner")) or "all_planned_peer_sleeve",
            rule_summary="All-planned peer sleeve variant; exact rules are frozen in the upstream run artifact.",
        )
        worth = _norm(source.get("worth_status"))
        reasons = [f"worth_status:{worth}"] if worth else []
        if worth == "thin_sample":
            candidate["reason_codes"] = ["thin_sample_variant"]
        elif worth == "profitable_but_overlaps":
            candidate["reason_codes"] = ["profitable_but_overlaps_existing_stack"]
        elif worth == "repair_stress_before_counting":
            candidate["reason_codes"] = ["stress_or_risk_repair_required"]
        elif worth in {"not_worth_current_shape", "weak_positive_or_marginal"}:
            candidate["reason_codes"] = ["weak_or_negative_peer_variant"]
        elif worth == "no_current_candidates":
            candidate["reason_codes"] = ["no_current_candidates"]
        candidate["reason_codes"] = _unique([*candidate["reason_codes"], *reasons])
        candidate.update(
            {
                "source_family": "all_planned_variant",
                "total_exact_rows": _safe_int(source.get("standalone_exact_trade_count")),
                "priced_rows": _safe_int(source.get("standalone_exact_trade_count")),
                "unpriced_rows": _safe_int(source.get("standalone_unpriced_trade_count")),
                "profit_factor": _round(source.get("standalone_profit_factor"), 4),
                "avg_net_pnl_pct": _round(source.get("standalone_avg_pnl_pct")),
                "profit_factor_lower_bound": _round(source.get("stress_5pct_per_side_profit_factor"), 4),
                "execution_evidence_class": "trusted_intraday_opra_nbbo",
                "source_quality_status": "quote_coverage_ready" if _safe_float(source.get("quote_coverage_pct")) == 100 else "quote_coverage_partial",
                "stress_results": {
                    "stress_5pct_per_side_profit_factor": source.get("stress_5pct_per_side_profit_factor"),
                    "rolling_status": source.get("rolling_status"),
                    "strict_new_trade_count": source.get("strict_new_trade_count"),
                    "quote_coverage_pct": source.get("quote_coverage_pct"),
                },
                "source_blockers": [] if worth in {"candidate_to_close_200_gap"} else candidate["reason_codes"],
            }
        )
        if _safe_float(source.get("quote_coverage_pct")) is not None and float(source.get("quote_coverage_pct")) < 90:
            candidate["source_blockers"].append(f"quote_coverage_{source.get('quote_coverage_pct')}_below_90")
        rows.append(candidate)
    return rows


def _monthly_lane_map(monthly: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in _as_list(monthly.get("lane_leaderboard")):
        row = _as_dict(row)
        lane = _norm(row.get("lane"))
        if lane:
            result[lane] = row
    return result


def _ticker_concentration_from_monthly(row: dict[str, Any]) -> dict[str, Any]:
    guardrails = _as_dict(row.get("self_guardrails"))
    clusters = [_as_dict(item) for item in _as_list(guardrails.get("negative_ticker_clusters"))]
    if not clusters:
        return {"status": "not_available"}
    total_usd = abs(float(row.get("sum_net_pnl_usd") or 0.0))
    ranked = sorted(clusters, key=lambda item: abs(float(item.get("sum_net_pnl_usd") or 0.0)), reverse=True)
    top = ranked[0]
    top_usd = abs(float(top.get("sum_net_pnl_usd") or 0.0))
    pct = round((top_usd / total_usd) * 100, 2) if total_usd else None
    return {
        "status": "available",
        "top_ticker": top.get("key") or top.get("ticker"),
        "top_rows": top.get("rows"),
        "top_profit_share_pct": pct,
        "top_net_pnl_usd": top.get("sum_net_pnl_usd"),
    }


def _lane_candidate_rows(trade_qualification: dict[str, Any], monthly: dict[str, Any]) -> list[dict[str, Any]]:
    monthly_by_lane = _monthly_lane_map(monthly)
    rows: list[dict[str, Any]] = []
    for item in _as_list(trade_qualification.get("lane_decisions")):
        source = _as_dict(item)
        lane_id = _norm(source.get("lane_id"))
        monthly_row = monthly_by_lane.get(lane_id, {})
        candidate = _empty_candidate(
            candidate_id=f"lane:{lane_id}",
            lane_id=lane_id,
            strategy_family="monthly_lane_gate",
            rule_summary="Current monthly lane gate/read-only trade qualification lane decision.",
        )
        decision = _norm(source.get("decision"))
        if decision == "paper_shadow_collect":
            candidate["paper_shadow_source"] = True
        if decision == "quarantine_no_chase":
            candidate["quarantine_source"] = True
        if decision == "needs_replay_engine":
            candidate["needs_replay_engine_source"] = True
        candidate.update(
            {
                "source_family": "trade_qualification_lane",
                "sample_window_start": source.get("sample_window_start"),
                "sample_window_end": source.get("sample_window_end"),
                "total_exact_rows": _safe_int(source.get("priced_rows")),
                "priced_rows": _safe_int(source.get("priced_rows")),
                "profit_factor": _round(source.get("profit_factor"), 4),
                "avg_net_pnl_pct": _round(source.get("avg_net_pnl_pct")),
                "median_net_pnl_pct": _round(source.get("median_net_pnl_pct")),
                "win_rate_pct": _round(source.get("win_rate_pct")),
                "net_pnl_usd": _round(monthly_row.get("sum_net_pnl_usd")),
                "execution_evidence_class": "trusted_intraday_opra_nbbo",
                "source_quality_status": "fresh_forward_not_complete",
                "ticker_concentration": _ticker_concentration_from_monthly(monthly_row),
                "source_blockers": _as_list(source.get("reason_codes")),
                "reason_codes": [f"trade_qualification_decision:{decision}"],
            }
        )
        rows.append(candidate)
    return rows


def _classify_all(candidates: list[dict[str, Any]], *, source_status_blocked: bool) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        decision, reasons, next_step = _classify_candidate(candidate, source_status_blocked=source_status_blocked)
        row = dict(candidate)
        row["decision"] = decision
        row["reason_codes"] = reasons
        row["next_step"] = next_step
        row.pop("source_blockers", None)
        row.pop("paper_shadow_source", None)
        row.pop("quarantine_source", None)
        row.pop("needs_replay_engine_source", None)
        result.append(row)
    order = {
        "robust_candidate_for_forward_freeze": 0,
        "paper_shadow_candidate": 1,
        "thin_sample_watch": 2,
        "repair_needed": 3,
        "execution_fragile_reject": 4,
        "overfit_reject": 5,
        "regime_fragile_reject": 6,
        "ticker_concentrated_reject": 7,
        "quarantine_no_chase": 8,
        "needs_replay_engine": 9,
        "insufficient_data": 10,
        "blocked_missing_readbacks": 11,
    }
    result.sort(
        key=lambda row: (
            order.get(str(row.get("decision")), 99),
            -_safe_int(row.get("total_exact_rows")),
            str(row.get("candidate_id")),
        )
    )
    return result


def _overall_status(source_artifacts: dict[str, dict[str, Any]], candidates: list[dict[str, Any]], robust: dict[str, Any]) -> str:
    source_status = _source_block_status(source_artifacts)
    if source_status:
        return source_status
    if any(row.get("decision") == "robust_candidate_for_forward_freeze" for row in candidates):
        return "robust_candidate_found_for_forward_freeze"
    robust_summary = _as_dict(robust.get("summary"))
    if robust_summary.get("source_quality_gate_status") == "source_quality_gate_blocked" and not candidates:
        return "blocked_source_quality"
    if any(row.get("decision") == "paper_shadow_candidate" for row in candidates):
        return "paper_shadow_only"
    if all(row.get("total_exact_rows", 0) == 0 for row in candidates):
        return "blocked_insufficient_exact_data"
    return "no_robust_edge_found"


def _data_coverage_summary(feature: dict[str, Any], robust: dict[str, Any], walk: dict[str, Any], monthly: dict[str, Any]) -> dict[str, Any]:
    feature_summary = _as_dict(feature.get("summary"))
    robust_summary = _as_dict(robust.get("summary"))
    walk_summary = _as_dict(walk.get("summary"))
    monthly_summary = _as_dict(monthly.get("summary"))
    return {
        "feature_store_status": feature.get("status"),
        "quote_source": _as_dict(feature.get("inputs")).get("source_label"),
        "quote_snapshot_kind": _as_dict(feature.get("inputs")).get("snapshot_kind"),
        "quote_data_trust": _as_dict(feature.get("inputs")).get("data_trust"),
        "shared_quote_date_count": feature_summary.get("shared_quote_date_count"),
        "shared_quote_date_start": feature_summary.get("first_shared_quote_date_et")
        or feature_summary.get("shared_quote_date_start"),
        "shared_quote_date_end": feature_summary.get("latest_shared_quote_date_et")
        or feature_summary.get("shared_quote_date_end"),
        "quote_row_count": feature_summary.get("quote_row_count"),
        "robust_search_status": robust.get("status"),
        "accepted_exact_trade_count": robust_summary.get("accepted_exact_trade_count"),
        "ready_candidate_count": robust_summary.get("ready_candidate_count"),
        "source_quality_gate_status": robust_summary.get("source_quality_gate_status"),
        "walk_forward_status": walk.get("status"),
        "promotion_ready": walk_summary.get("promotion_ready"),
        "all_planned_tested_variant_count": walk_summary.get("all_planned_tested_variant_count"),
        "all_planned_variant_count": walk_summary.get("all_planned_variant_count"),
        "monthly_baseline_profit_factor": monthly_summary.get("baseline_profit_factor"),
        "monthly_baseline_avg_net_pnl_pct": monthly_summary.get("baseline_avg_net_pnl_pct"),
    }


def _proof_standard_summary(robust: dict[str, Any], walk: dict[str, Any]) -> dict[str, Any]:
    return {
        "standard": "executable exact options evidence only",
        "accepted_proof_sources": sorted(TRUSTED_EXECUTION_CLASSES),
        "historical_use": _as_dict(robust.get("proof_policy")).get("historical_use")
        or _as_dict(walk.get("proof_policy")).get("historical_use"),
        "fresh_forward_requirement": _as_dict(walk.get("proof_policy")).get("fresh_forward_requirement"),
        "not_counted_as_proof": [
            "midpoint",
            "EOD",
            "stale",
            "display-only",
            "manual",
            "last-trade",
            "model",
            "research/backfill rows without fresh exact bridge",
        ],
    }


def _split_summary(robust: dict[str, Any], walk: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(robust.get("summary"))
    walk_summary = _as_dict(walk.get("summary"))
    return {
        "split_policy": robust.get("split_policy"),
        "variants_searched": summary.get("variants_searched"),
        "selection_adjusted_bar": summary.get("selection_adjusted_bar"),
        "latest_candidate_entry_date": walk_summary.get("latest_candidate_entry_date"),
        "protected_forward_holdout_start_date": walk_summary.get("protected_forward_holdout_start_date"),
        "protected_forward_holdout_overlap": walk_summary.get("protected_forward_holdout_overlap"),
        "forward_holdout_guard_status": walk_summary.get("forward_holdout_guard_status"),
    }


def _stress_tests(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "candidate_id": row.get("candidate_id"),
            "decision": row.get("decision"),
            "stress_results": row.get("stress_results"),
            "reason_codes": row.get("reason_codes"),
        }
        for row in candidates
        if row.get("stress_results")
    ][:30]


def _concentration_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    ticker_flagged = [
        row
        for row in candidates
        if _concentration_status(_as_dict(row.get("ticker_concentration")))[0]
    ]
    month_flagged = [
        row
        for row in candidates
        if _concentration_status(_as_dict(row.get("month_concentration")))[0]
    ]
    return {
        "ticker_concentration_flagged_count": len(ticker_flagged),
        "month_concentration_flagged_count": len(month_flagged),
        "flagged_ticker_candidates": [
            {"candidate_id": row.get("candidate_id"), "ticker_concentration": row.get("ticker_concentration")}
            for row in ticker_flagged[:10]
        ],
        "flagged_month_candidates": [
            {"candidate_id": row.get("candidate_id"), "month_concentration": row.get("month_concentration")}
            for row in month_flagged[:10]
        ],
    }


def _forward_freeze_recommendation(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    robust = [row for row in candidates if row.get("decision") == "robust_candidate_for_forward_freeze"]
    if not robust:
        return {
            "status": "not_recommended",
            "candidate_id": None,
            "reason": "No candidate survives strict execution-realistic, split, stress, source-quality, and sample gates.",
            "frozen_rules": None,
        }
    best = robust[0]
    return {
        "status": "freeze_for_forward_paper_validation_only",
        "candidate_id": best.get("candidate_id"),
        "lane_id": best.get("lane_id"),
        "frozen_rules": best.get("rule_summary"),
        "required_forward_gate": list(REQUIRED_EVIDENCE_BEFORE_LIVE_DISCUSSION),
        "not_live_permission": True,
    }


def build_report(
    *,
    robust_search_path: Path = DEFAULT_ROBUST_SEARCH,
    walk_forward_path: Path = DEFAULT_WALK_FORWARD,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    monthly_audit_path: Path = DEFAULT_MONTHLY_AUDIT,
    trade_qualification_path: Path = DEFAULT_TRADE_QUALIFICATION,
    paper_shadow_plan_path: Path = DEFAULT_PAPER_SHADOW_PLAN,
    market_window_checklist_path: Path = DEFAULT_MARKET_WINDOW_CHECKLIST,
    lane_promotion_path: Path = DEFAULT_LANE_PROMOTION,
    missed_filter_matrix_path: Path = DEFAULT_MISSED_FILTER_MATRIX,
    missed_outcomes_path: Path = DEFAULT_MISSED_OUTCOMES,
    missed_failures_path: Path = DEFAULT_MISSED_FAILURES,
    generated_at_utc: str | None = None,
    max_source_age_hours: int = MAX_SOURCE_AGE_HOURS,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    specs = {
        "robust_search": (robust_search_path, True),
        "historical_walk_forward": (walk_forward_path, True),
        "feature_store": (feature_store_path, True),
        "monthly_profitability": (monthly_audit_path, True),
        "trade_qualification": (trade_qualification_path, True),
        "paper_shadow_evidence_plan": (paper_shadow_plan_path, True),
        "market_window_evidence_checklist": (market_window_checklist_path, True),
        "lane_promotion_state": (lane_promotion_path, True),
        "missed_filter_matrix": (missed_filter_matrix_path, True),
        "missed_outcomes": (missed_outcomes_path, True),
        "missed_failures": (missed_failures_path, True),
    }
    loaded: dict[str, dict[str, Any]] = {}
    source_artifacts: dict[str, dict[str, Any]] = {}
    for name, (path, required) in specs.items():
        payload, source = _load_json_artifact(
            path,
            name=name,
            required=required,
            generated_at_utc=generated_at,
            max_age_hours=max_source_age_hours,
        )
        loaded[name] = payload
        source_artifacts[name] = source

    source_status_blocked = _source_block_status(source_artifacts) is not None
    raw_candidates = [
        *_robust_candidate_rows(loaded["robust_search"]),
        *_variant_candidate_rows(loaded["historical_walk_forward"]),
        *_lane_candidate_rows(loaded["trade_qualification"], loaded["monthly_profitability"]),
    ]
    candidates = _classify_all(raw_candidates, source_status_blocked=source_status_blocked)
    counts = Counter(row.get("decision") for row in candidates)
    rejected_decisions = {
        "overfit_reject",
        "execution_fragile_reject",
        "regime_fragile_reject",
        "ticker_concentrated_reject",
        "quarantine_no_chase",
    }
    blocked_decisions = {"repair_needed", "needs_replay_engine", "insufficient_data", "blocked_missing_readbacks"}
    robust_candidates = [row for row in candidates if row.get("decision") == "robust_candidate_for_forward_freeze"]
    paper_candidates = [row for row in candidates if row.get("decision") == "paper_shadow_candidate"]
    best_candidate = robust_candidates[0] if robust_candidates else (paper_candidates[0] if paper_candidates else (candidates[0] if candidates else None))
    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": "regular_options_robust_edge_discovery_and_falsification",
        "read_only": True,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "is_trade_recommendation": False,
        "overall_status": _overall_status(source_artifacts, candidates, loaded["robust_search"]),
        "source_artifacts": source_artifacts,
        "data_coverage_summary": _data_coverage_summary(
            loaded["feature_store"],
            loaded["robust_search"],
            loaded["historical_walk_forward"],
            loaded["monthly_profitability"],
        ),
        "proof_standard_summary": _proof_standard_summary(loaded["robust_search"], loaded["historical_walk_forward"]),
        "candidate_count": len(candidates),
        "robust_candidate_count": counts.get("robust_candidate_for_forward_freeze", 0),
        "paper_shadow_candidate_count": counts.get("paper_shadow_candidate", 0),
        "rejected_candidate_count": sum(counts.get(item, 0) for item in rejected_decisions),
        "blocked_candidate_count": sum(counts.get(item, 0) for item in blocked_decisions),
        "best_candidate_if_any": best_candidate,
        "candidate_rankings": candidates,
        "rejected_candidates": [row for row in candidates if row.get("decision") in rejected_decisions],
        "stress_tests": _stress_tests(candidates),
        "split_summary": _split_summary(loaded["robust_search"], loaded["historical_walk_forward"]),
        "concentration_summary": _concentration_summary(candidates),
        "forward_freeze_recommendation": _forward_freeze_recommendation(candidates),
        "required_evidence_before_live_discussion": list(REQUIRED_EVIDENCE_BEFORE_LIVE_DISCUSSION),
        "operator_next_steps": [
            "Do not freeze any new algorithm from the current historical readbacks unless a candidate reaches robust_candidate_for_forward_freeze.",
            "Keep volatility_expansion_observation paper-shadow only and collect fresh exact entries plus policy-defined exact realized exits.",
            "Use the historical walk-forward repair queue for source-quality, unpriced, zero-bid, stress, and overlap repairs without mutating evidence stores unless separately approved.",
            "Rerun feature-store, robust-search, walk-forward, monthly profitability, trade qualification, paper-shadow plan, and market-window checklist after any approved repair.",
        ],
        "prohibited_actions": _unique(
            [
                *PROHIBITED_ACTIONS,
                *_as_list(loaded["robust_search"].get("prohibited_actions")),
                *_as_list(loaded["historical_walk_forward"].get("prohibited_actions")),
                *_as_list(loaded["monthly_profitability"].get("prohibited_actions")),
            ]
        ),
        "non_goals": list(NON_GOALS),
        "decision_counts": dict(sorted(counts.items())),
        "existing_promotion_ready": bool(_as_dict(loaded["historical_walk_forward"].get("summary")).get("promotion_ready")),
    }
    return report


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "/")


def _candidate_table(rows: list[dict[str, Any]], limit: int = 20) -> list[str]:
    if not rows:
        return ["No candidates."]
    lines = [
        "| Candidate | Decision | Exact | Holdout | PF | PF LB | Avg % | Evidence | Reasons |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in rows[:limit]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('candidate_id'))}`",
                    f"`{_cell(row.get('decision'))}`",
                    _cell(row.get("total_exact_rows")),
                    _cell(row.get("holdout_rows")),
                    _cell(row.get("profit_factor")),
                    _cell(row.get("profit_factor_lower_bound")),
                    _cell(row.get("avg_net_pnl_pct")),
                    f"`{_cell(row.get('execution_evidence_class'))}`",
                    _cell(", ".join(_as_list(row.get("reason_codes")))[:260]),
                ]
            )
            + " |"
        )
    if len(rows) > limit:
        lines.append(f"Showing `{limit}` of `{len(rows)}` candidates; see JSON for all rows.")
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    overall = report.get("overall_status")
    best = _as_dict(report.get("best_candidate_if_any"))
    if overall == "robust_candidate_found_for_forward_freeze":
        conclusion = f"Candidate `{best.get('candidate_id')}` survived local falsification for frozen forward paper validation only."
    elif overall == "paper_shadow_only":
        conclusion = "No robust historical edge is ready. Current state is paper-shadow only."
    else:
        conclusion = "No robust execution-realistic edge is supported by the current local data."
    candidates = [_as_dict(row) for row in _as_list(report.get("candidate_rankings"))]
    rejected = [_as_dict(row) for row in _as_list(report.get("rejected_candidates"))]
    data = _as_dict(report.get("data_coverage_summary"))
    freeze = _as_dict(report.get("forward_freeze_recommendation"))
    lines = [
        "# Regular Options Robust Edge Discovery and Falsification",
        "",
        conclusion,
        "",
        "## Best candidate, if any",
        "",
        f"- Candidate: `{best.get('candidate_id')}`.",
        f"- Decision: `{best.get('decision')}`.",
        f"- Lane: `{best.get('lane_id')}`.",
        f"- Exact rows: `{best.get('total_exact_rows')}`; holdout rows: `{best.get('holdout_rows')}`.",
        f"- Profit factor / lower bound: `{best.get('profit_factor')}` / `{best.get('profit_factor_lower_bound')}`.",
        f"- Next step: {best.get('next_step')}.",
        "",
        "## Why it is or is not trustworthy",
        "",
        f"- Overall status: `{overall}`.",
        f"- Robust candidates: `{report.get('robust_candidate_count')}`.",
        f"- Paper-shadow candidates: `{report.get('paper_shadow_candidate_count')}`.",
        f"- Rejected candidates: `{report.get('rejected_candidate_count')}`.",
        f"- Blocked candidates: `{report.get('blocked_candidate_count')}`.",
        f"- Existing promotion_ready preserved: `{str(report.get('existing_promotion_ready')).lower()}`.",
        "",
        "## Data coverage summary",
        "",
        f"- Feature store: `{data.get('feature_store_status')}`.",
        f"- Quote source: `{data.get('quote_source')}` / `{data.get('quote_snapshot_kind')}` / `{data.get('quote_data_trust')}`.",
        f"- Shared quote dates: `{data.get('shared_quote_date_count')}` from `{data.get('shared_quote_date_start')}` to `{data.get('shared_quote_date_end')}`.",
        f"- Robust-search status: `{data.get('robust_search_status')}`; accepted exact rows `{data.get('accepted_exact_trade_count')}`; ready candidates `{data.get('ready_candidate_count')}`.",
        f"- Source-quality gate: `{data.get('source_quality_gate_status')}`.",
        f"- Walk-forward status: `{data.get('walk_forward_status')}`; promotion ready `{data.get('promotion_ready')}`.",
        "",
        "## Proof standard used",
        "",
        f"- Standard: `{_as_dict(report.get('proof_standard_summary')).get('standard')}`.",
        "- Counted proof must be executable exact options evidence, not midpoint/EOD/stale/display/manual/last/model marks.",
        "- Historical rows can nominate or reject a future forward candidate only; they are not live proof.",
        "",
        "## Candidate leaderboard",
        "",
        *_candidate_table(candidates),
        "",
        "## Rejection table",
        "",
        *_candidate_table(rejected, limit=20),
        "",
        "## Stress-test results",
        "",
    ]
    for item in _as_list(report.get("stress_tests"))[:20]:
        item = _as_dict(item)
        lines.append(f"- `{item.get('candidate_id')}` `{item.get('decision')}`: `{_json_text(item.get('stress_results'))}`.")
    lines.extend(
        [
            "",
            "## Split / holdout summary",
            "",
            f"- `{_json_text(report.get('split_summary'))}`",
            "",
            "## Concentration analysis",
            "",
            f"- `{_json_text(report.get('concentration_summary'))}`",
            "",
            "## Forward-freeze candidate spec, if any",
            "",
            f"- Status: `{freeze.get('status')}`.",
            f"- Candidate: `{freeze.get('candidate_id')}`.",
            f"- Rules: {freeze.get('frozen_rules') or 'none'}",
            "",
            "## Requirements before live discussion",
            "",
        ]
    )
    lines.extend(f"- {item}." for item in _as_list(report.get("required_evidence_before_live_discussion")))
    lines.extend(["", "## What not to do", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("prohibited_actions")))
    lines.extend(
        [
            "",
            "## Source artifacts and staleness",
            "",
            "| Source | Status | Age hours | Generated at | Reasons |",
            "| --- | --- | ---: | --- | --- |",
        ]
    )
    for name, meta in sorted(_as_dict(report.get("source_artifacts")).items()):
        lines.append(
            f"| `{name}` | `{meta.get('status')}` | `{meta.get('age_hours')}` | `{meta.get('generated_at_utc')}` | `{_json_text(meta.get('reason_codes'))}` |"
        )
    lines.extend(["", "## Non-goals", "", "This report does not:", ""])
    lines.extend(f"- {item}" for item in _as_list(report.get("non_goals")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    docs_report.write_text(render_markdown(report), encoding="utf8")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build regular-options robust edge discovery/falsification report.")
    parser.add_argument("--robust-search", type=Path, default=DEFAULT_ROBUST_SEARCH)
    parser.add_argument("--walk-forward", type=Path, default=DEFAULT_WALK_FORWARD)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--monthly-audit", type=Path, default=DEFAULT_MONTHLY_AUDIT)
    parser.add_argument("--trade-qualification", type=Path, default=DEFAULT_TRADE_QUALIFICATION)
    parser.add_argument("--paper-shadow-plan", type=Path, default=DEFAULT_PAPER_SHADOW_PLAN)
    parser.add_argument("--market-window-checklist", type=Path, default=DEFAULT_MARKET_WINDOW_CHECKLIST)
    parser.add_argument("--lane-promotion", type=Path, default=DEFAULT_LANE_PROMOTION)
    parser.add_argument("--missed-filter-matrix", type=Path, default=DEFAULT_MISSED_FILTER_MATRIX)
    parser.add_argument("--missed-outcomes", type=Path, default=DEFAULT_MISSED_OUTCOMES)
    parser.add_argument("--missed-failures", type=Path, default=DEFAULT_MISSED_FAILURES)
    parser.add_argument("--max-source-age-hours", type=int, default=MAX_SOURCE_AGE_HOURS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", dest="json_output", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        robust_search_path=args.robust_search,
        walk_forward_path=args.walk_forward,
        feature_store_path=args.feature_store,
        monthly_audit_path=args.monthly_audit,
        trade_qualification_path=args.trade_qualification,
        paper_shadow_plan_path=args.paper_shadow_plan,
        market_window_checklist_path=args.market_window_checklist,
        lane_promotion_path=args.lane_promotion,
        missed_filter_matrix_path=args.missed_filter_matrix,
        missed_outcomes_path=args.missed_outcomes,
        missed_failures_path=args.missed_failures,
        max_source_age_hours=args.max_source_age_hours,
    )
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
