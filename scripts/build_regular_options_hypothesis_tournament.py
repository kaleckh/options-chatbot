from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_hypothesis_tournament"

DEFAULT_ROBUST_EDGE = ROOT / "data" / "profitability-lab" / "regular-options-robust-edge-discovery" / "latest.json"
DEFAULT_ROBUST_SEARCH = ROOT / "data" / "profitability-lab" / "regular-options-robust-search-evaluation" / "latest.json"
DEFAULT_WALK_FORWARD = ROOT / "data" / "profitability-lab" / "regular-options-historical-walk-forward" / "latest.json"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_MONTHLY_AUDIT = ROOT / "data" / "forward-tracking" / "monthly_all_lanes_profitability_audit_latest.json"
DEFAULT_MISSED_FILTER_MATRIX = ROOT / "data" / "forward-tracking" / "missed_regular_picks_filter_matrix_latest.json"
DEFAULT_MISSED_FAILURES = ROOT / "data" / "forward-tracking" / "missed_regular_picks_failure_modes_latest.json"
DEFAULT_LANE_PROMOTION = ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-hypothesis-tournament"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-hypothesis-tournament.md"

MAX_SOURCE_AGE_HOURS = 96
DEFAULT_MAX_VARIANTS = 100
DEFAULT_MIN_TRADES = 200
DEFAULT_MIN_HOLDOUT_TRADES = 30
DEFAULT_MIN_MONTHS = 4
MAX_TICKER_PROFIT_SHARE_PCT = 35.0
MAX_MONTH_PROFIT_SHARE_PCT = 50.0
MIN_PF_LB = 1.0

TRUSTED_EXECUTION_CLASSES = {
    "trusted_intraday_opra_nbbo",
    "trusted_opra_nbbo",
    "executable_exact_options",
    "exact_bid_ask",
}

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_hypothesis_tournament",
    "do_not_submit_broker_orders_from_hypothesis_tournament",
    "do_not_enable_auto_track_from_hypothesis_tournament",
    "do_not_enable_live_validation_from_hypothesis_tournament",
    "do_not_change_scanner_policy_from_hypothesis_tournament",
    "do_not_change_stops_from_hypothesis_tournament",
    "do_not_change_sizing_from_hypothesis_tournament",
    "do_not_lower_proof_bars_from_hypothesis_tournament",
    "do_not_mutate_evidence_databases_from_hypothesis_tournament",
    "do_not_count_midpoint_eod_stale_manual_display_last_or_model_marks_as_proof",
    "do_not_treat_historical_research_rows_as_live_proof",
)

NON_GOALS = (
    "create trades",
    "submit broker orders",
    "enable auto-track",
    "enable live validation",
    "change scanner policy",
    "change stops",
    "change sizing",
    "lower proof bars",
    "mutate evidence databases",
    "prove future profits with certainty",
)

REQUIRED_EVIDENCE_BEFORE_LIVE_DISCUSSION = (
    "a frozen forward-paper candidate spec with no post-hoc edits",
    "at least 30 post-freeze exact realized paper-shadow rows",
    "fresh executable exact OPRA/NBBO entry evidence for each row",
    "policy-defined executable exact OPRA/NBBO exit evidence for each row",
    "positive forward net P&L after fees and execution-realistic pricing",
    "forward paper profit-factor lower bound above 1.0",
    "no source-quality, unpriced, midpoint, stale, EOD, display-only, manual, last-trade, or model proof contamination",
    "no open-risk or no-chase blocker",
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
        return str(path).replace("\\", "/")


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
        if value in (None, "") or isinstance(value, bool):
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
    meta = {
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
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        meta["reason_codes"] = ["malformed_readback"]
        return {}, meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        meta["reason_codes"] = ["unreadable_readback"]
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["reason_codes"] = ["json_root_not_object"]
        return {}, meta

    meta["generated_at_utc"] = payload.get("generated_at_utc")
    as_of = _parse_utc(generated_at_utc) or datetime.now(UTC)
    generated = _parse_utc(payload.get("generated_at_utc"))
    if generated is None:
        meta["status"] = "stale"
        meta["reason_codes"] = ["missing_or_malformed_generated_at_utc", "stale_readback"]
        return payload, meta
    age_hours = (as_of - generated).total_seconds() / 3600
    meta["age_hours"] = round(age_hours, 2)
    if age_hours < -1:
        meta["status"] = "invalid"
        meta["reason_codes"] = ["readback_generated_in_future"]
        return payload, meta
    if age_hours > max_age_hours:
        meta["status"] = "stale"
        meta["reason_codes"] = ["stale_readback"]
        return payload, meta

    meta["status"] = "loaded"
    meta["reason_codes"] = []
    meta["report_id"] = payload.get("report_id") or name
    return payload, meta


def _source_block_status(source_artifacts: dict[str, dict[str, Any]]) -> str | None:
    bad = [meta for meta in source_artifacts.values() if meta.get("required") and meta.get("status") != "loaded"]
    if not bad:
        return None
    if any(meta.get("status") == "stale" or "stale_readback" in _as_list(meta.get("reason_codes")) for meta in bad):
        return "blocked_stale_readbacks"
    return "blocked_missing_readbacks"


def _new_candidate(candidate_id: str, lane_id: str, family: str, rule_summary: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "lane_id": lane_id,
        "strategy_family": family,
        "rule_summary": rule_summary,
        "complexity_score": 1,
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
        "top_winner_dependency": {"status": "not_available"},
        "regime_summary": {"status": "not_available"},
        "execution_evidence_class": "trusted_intraday_opra_nbbo",
        "source_quality_status": "unknown",
        "stress_results": {},
        "decision": "insufficient_data",
        "reason_codes": [],
        "next_step": "",
    }


def _candidate_from_robust_edge(row: dict[str, Any]) -> dict[str, Any]:
    candidate = _new_candidate(
        _norm(row.get("candidate_id")),
        _norm(row.get("lane_id")),
        _norm(row.get("strategy_family")) or "existing_research_candidate",
        _norm(row.get("rule_summary")) or "Existing candidate from robust edge discovery.",
    )
    for key in (
        "sample_window_start",
        "sample_window_end",
        "train_rows",
        "validation_rows",
        "holdout_rows",
        "total_exact_rows",
        "priced_rows",
        "unpriced_rows",
        "profit_factor",
        "profit_factor_lower_bound",
        "avg_net_pnl_pct",
        "median_net_pnl_pct",
        "net_pnl_usd",
        "win_rate_pct",
        "max_drawdown_pct",
        "deep_loss_counts",
        "ticker_concentration",
        "month_concentration",
        "regime_summary",
        "execution_evidence_class",
        "source_quality_status",
        "stress_results",
    ):
        if key in row:
            candidate[key] = row.get(key)
    source_family = _norm(row.get("source_family"))
    if source_family == "trade_qualification_lane":
        candidate["complexity_score"] = 1
    elif source_family == "all_planned_variant":
        candidate["complexity_score"] = 2
    elif "combined" in candidate["candidate_id"]:
        candidate["complexity_score"] = 3
    else:
        candidate["complexity_score"] = 2
    candidate["source_decision"] = row.get("decision") or row.get("source_decision")
    candidate["reason_codes"] = _as_list(row.get("reason_codes"))
    candidate["next_step"] = row.get("next_step") or ""
    candidate["top_winner_dependency"] = _top_winner_dependency(_as_dict(candidate.get("stress_results")))
    return candidate


def _candidate_from_filter_scenario(row: dict[str, Any]) -> dict[str, Any]:
    scenario_id = _norm(row.get("scenario_id"))
    candidate = _new_candidate(
        f"filter:{scenario_id}",
        "multi_lane_filter_matrix",
        "simple_counterfactual_filter",
        f"Counterfactual missed-pick filter matrix scenario `{scenario_id}`; diagnostic only until preregistered and replayed point-in-time.",
    )
    candidate.update(
        {
            "complexity_score": 2 if "plus" in scenario_id or "combo" in scenario_id else 1,
            "total_exact_rows": _safe_int(row.get("kept_count")),
            "priced_rows": _safe_int(row.get("kept_count")),
            "profit_factor": _round(row.get("profit_factor"), 4),
            "avg_net_pnl_pct": _round(row.get("avg_net_pnl_pct")),
            "execution_evidence_class": "trusted_intraday_opra_nbbo",
            "source_quality_status": "research_backfill_counterfactual",
            "source_decision": row.get("status"),
            "stress_results": {
                "survives_later_date_split": bool(row.get("survives_later_date_split")),
                "lost_winner_count": row.get("lost_winner_count"),
                "avoided_lte_minus_50": row.get("avoided_lte_minus_50"),
            },
            "top_winner_dependency": {
                "status": "winner_damage_available",
                "lost_winner_count": _safe_int(row.get("lost_winner_count")),
            },
            "reason_codes": [f"filter_matrix_status:{_norm(row.get('status'))}"],
        }
    )
    if row.get("survives_later_date_split") is False:
        candidate["reason_codes"].append("does_not_survive_later_date_split")
    if _safe_int(row.get("lost_winner_count")) > 0:
        candidate["reason_codes"].append(f"lost_winner_count_{_safe_int(row.get('lost_winner_count'))}")
    return candidate


def _candidate_pool(robust_edge: dict[str, Any], missed_filter_matrix: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [_candidate_from_robust_edge(_as_dict(row)) for row in _as_list(robust_edge.get("candidate_rankings"))]
    candidates.extend(
        _candidate_from_filter_scenario(_as_dict(row))
        for row in _as_list(missed_filter_matrix.get("ranked_scenarios_by_kept_profit_factor"))
    )
    return [row for row in candidates if row.get("candidate_id")]


def _top_winner_dependency(stress: dict[str, Any]) -> dict[str, Any]:
    values = {
        "top_1_removed_profit_factor": stress.get("top_1_removed_profit_factor"),
        "top_3_removed_profit_factor": stress.get("top_3_removed_profit_factor"),
        "top_5_removed_profit_factor": stress.get("top_5_removed_profit_factor"),
    }
    available = {key: value for key, value in values.items() if _safe_float(value) is not None}
    if not available:
        return {"status": "not_available"}
    failed = {key: value for key, value in available.items() if (_safe_float(value) or 0.0) < 1.0}
    return {"status": "failed" if failed else "passed", "metrics": available, "failed_metrics": failed}


def _stress_fails(stress: dict[str, Any]) -> bool:
    for key in (
        "top_1_removed_profit_factor",
        "top_3_removed_profit_factor",
        "top_5_removed_profit_factor",
        "wider_spread_profit_factor",
        "stress_5pct_per_side_profit_factor",
    ):
        value = _safe_float(stress.get(key))
        if value is not None and value < 1.0:
            return True
    if stress.get("survives_later_date_split") is False:
        return True
    return False


def _ticker_concentrated(candidate: dict[str, Any]) -> tuple[bool, str | None]:
    concentration = _as_dict(candidate.get("ticker_concentration"))
    pct = _safe_float(concentration.get("top_ticker_profit_share_pct") or concentration.get("top_profit_share_pct"))
    if pct is not None and pct > MAX_TICKER_PROFIT_SHARE_PCT:
        return True, f"ticker_profit_share_{round(pct, 2)}_above_{MAX_TICKER_PROFIT_SHARE_PCT}"
    return False, None


def _month_concentrated(candidate: dict[str, Any]) -> tuple[bool, str | None]:
    concentration = _as_dict(candidate.get("month_concentration"))
    pct = _safe_float(concentration.get("top_month_profit_share_pct") or concentration.get("top_profit_share_pct"))
    if pct is not None and pct > MAX_MONTH_PROFIT_SHARE_PCT:
        return True, f"month_profit_share_{round(pct, 2)}_above_{MAX_MONTH_PROFIT_SHARE_PCT}"
    return False, None


def _contains_non_executable_reason(candidate: dict[str, Any]) -> bool:
    text = " ".join(_as_list(candidate.get("reason_codes"))).lower()
    needles = ("midpoint", "eod", "stale", "manual", "display", "last", "model")
    return any(item in text for item in needles)


def classify_candidate(
    candidate: dict[str, Any],
    *,
    source_status_blocked: bool,
    min_trades: int,
    min_holdout_trades: int,
    min_months: int,
) -> tuple[str, list[str], str]:
    reasons = list(_as_list(candidate.get("reason_codes")))
    if source_status_blocked:
        return "blocked_missing_readbacks", _unique([*reasons, "required_source_readback_not_loaded"]), "Refresh required readbacks before testing hypotheses."

    source_decision = _norm(candidate.get("source_decision"))
    evidence = _norm(candidate.get("execution_evidence_class")).lower()
    if evidence and evidence not in TRUSTED_EXECUTION_CLASSES:
        return "execution_fragile_reject", _unique([*reasons, f"non_executable_evidence_class:{evidence}"]), "Reject until executable exact OPRA/NBBO-style evidence replaces this source."
    if _contains_non_executable_reason(candidate):
        return "execution_fragile_reject", _unique([*reasons, "non_executable_or_stale_proof_source"]), "Reject; the proof source is not execution-realistic."
    if source_decision in {"quarantine_no_chase"}:
        return "quarantine_no_chase", _unique([*reasons, "quarantine_or_no_chase_active"]), "Keep parked; do not resurrect without explicit earn-back evidence."
    if source_decision == "needs_replay_engine":
        return "needs_replay_engine", _unique([*reasons, "replay_engine_or_source_repair_required"]), "Repair replay/source infrastructure before tournament scoring."

    unpriced = _safe_int(candidate.get("unpriced_rows"))
    reason_text = " ".join(str(item) for item in reasons).lower()
    if unpriced > 0:
        return "repair_needed", _unique([*reasons, f"unpriced_rows_{unpriced}"]), "Repair unpriced rows before any forward-freeze discussion."
    if "unpriced" in reason_text or "source_quality" in reason_text:
        return "repair_needed", _unique([*reasons, "source_quality_or_unpriced_blocker"]), "Repair source-quality or unpriced rows before interpreting the edge."
    if "quote_coverage" in reason_text or "zero_bid" in reason_text:
        return "execution_fragile_reject", _unique([*reasons, "execution_or_liquidity_fragility"]), "Reject or repair execution-quality failure before considering a freeze."

    total = _safe_int(candidate.get("total_exact_rows"))
    holdout = _safe_int(candidate.get("holdout_rows"))
    pf = _safe_float(candidate.get("profit_factor"))
    pf_lb = _safe_float(candidate.get("profit_factor_lower_bound"))
    if total == 0:
        return "insufficient_data", _unique([*reasons, "no_exact_rows"]), "Wait for exact priced rows; do not infer an edge."
    if pf is not None and pf <= 1.0:
        return "overfit_reject", _unique([*reasons, "point_profit_factor_not_above_1"]), "Reject until point profitability is positive after costs."

    ticker_bad, ticker_reason = _ticker_concentrated(candidate)
    if ticker_bad:
        return "ticker_concentrated_reject", _unique([*reasons, ticker_reason or "ticker_concentration_above_gate"]), "Reject or split; profits are too ticker-concentrated."
    month_bad, month_reason = _month_concentrated(candidate)
    if month_bad:
        return "month_concentrated_reject", _unique([*reasons, month_reason or "month_concentration_above_gate"]), "Reject as month/regime-concentrated until broader split evidence exists."
    if _stress_fails(_as_dict(candidate.get("stress_results"))):
        return "overfit_reject", _unique([*reasons, "stress_or_later_date_split_failed"]), "Reject until top-winner, later-date, and execution stress remain profitable."

    if source_decision == "paper_shadow_candidate":
        return "paper_shadow_candidate", _unique([*reasons, "paper_shadow_or_probation_only", "not_historical_robust_proof"]), "Keep paper-shadow only; collect fresh exact entries and exact realized exits."

    if total < min_trades:
        return "thin_sample_watch", _unique([*reasons, f"total_exact_rows_{total}_below_{min_trades}"]), "Collect more exact rows before trusting this hypothesis."
    if holdout < min_holdout_trades:
        return "insufficient_holdout_reject", _unique([*reasons, f"holdout_rows_{holdout}_below_{min_holdout_trades}"]), "Reject for freeze until protected/chronological holdout depth is sufficient."
    if min_months > 0 and _as_dict(candidate.get("month_concentration")).get("month_count") is not None:
        month_count = _safe_int(_as_dict(candidate.get("month_concentration")).get("month_count"))
        if month_count < min_months:
            return "regime_fragile_reject", _unique([*reasons, f"month_count_{month_count}_below_{min_months}"]), "Reject until at least several months are represented."
    if pf_lb is None or pf_lb <= MIN_PF_LB:
        return "holdout_fail_reject", _unique([*reasons, "profit_factor_lower_bound_not_above_1"]), "Reject until holdout/bootstrap lower bound clears 1.0."
    if source_decision == "robust_candidate_for_forward_freeze":
        return "forward_freeze_candidate", _unique([*reasons, "all_tournament_gates_passed"]), "Draft a frozen forward paper spec only; this is not live permission."
    return "thin_sample_watch", _unique([*reasons, "not_previously_robust_nomination_ready"]), "Keep as watchlist; require preregistered split and forward-paper evidence."


def _classify_all(
    candidates: list[dict[str, Any]],
    *,
    source_status_blocked: bool,
    max_variants: int,
    min_trades: int,
    min_holdout_trades: int,
    min_months: int,
) -> list[dict[str, Any]]:
    order_source = {
        "robust_candidate_for_forward_freeze": 0,
        "paper_shadow_candidate": 1,
        "thin_sample_watch": 2,
        "repair_needed": 3,
        "execution_fragile_reject": 4,
        "overfit_reject": 5,
    }
    candidates = sorted(
        candidates,
        key=lambda row: (
            order_source.get(str(row.get("source_decision")), 20),
            -(_safe_float(row.get("profit_factor")) or -999.0),
            -_safe_int(row.get("total_exact_rows")),
            str(row.get("candidate_id")),
        ),
    )[: max(0, max_variants)]
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        decision, reasons, next_step = classify_candidate(
            candidate,
            source_status_blocked=source_status_blocked,
            min_trades=min_trades,
            min_holdout_trades=min_holdout_trades,
            min_months=min_months,
        )
        row = dict(candidate)
        row["decision"] = decision
        row["reason_codes"] = reasons
        row["next_step"] = next_step
        result.append(row)

    decision_order = {
        "forward_freeze_candidate": 0,
        "paper_shadow_candidate": 1,
        "thin_sample_watch": 2,
        "insufficient_holdout_reject": 3,
        "repair_needed": 4,
        "holdout_fail_reject": 5,
        "overfit_reject": 6,
        "execution_fragile_reject": 7,
        "ticker_concentrated_reject": 8,
        "month_concentrated_reject": 9,
        "regime_fragile_reject": 10,
        "quarantine_no_chase": 11,
        "needs_replay_engine": 12,
        "insufficient_data": 13,
        "blocked_missing_readbacks": 14,
    }
    result.sort(
        key=lambda row: (
            decision_order.get(str(row.get("decision")), 99),
            _safe_int(row.get("complexity_score")),
            -(_safe_float(row.get("profit_factor")) or -999.0),
            -_safe_int(row.get("total_exact_rows")),
            str(row.get("candidate_id")),
        )
    )
    return result


def _overall_status(source_artifacts: dict[str, dict[str, Any]], candidates: list[dict[str, Any]], robust_edge: dict[str, Any]) -> str:
    source_status = _source_block_status(source_artifacts)
    if source_status:
        return source_status
    if _as_dict(robust_edge.get("data_coverage_summary")).get("source_quality_gate_status") == "source_quality_gate_blocked":
        if not candidates:
            return "blocked_source_quality"
    if any(row.get("decision") == "forward_freeze_candidate" for row in candidates):
        return "forward_freeze_candidate_found"
    if any(row.get("decision") == "paper_shadow_candidate" for row in candidates):
        return "paper_shadow_only"
    if not candidates:
        return "blocked_insufficient_row_level_data"
    return "no_candidate_survived"


def _data_coverage_summary(feature: dict[str, Any], robust_search: dict[str, Any], walk: dict[str, Any], monthly: dict[str, Any]) -> dict[str, Any]:
    feature_summary = _as_dict(feature.get("summary"))
    robust_summary = _as_dict(robust_search.get("summary"))
    walk_summary = _as_dict(walk.get("summary"))
    monthly_summary = _as_dict(monthly.get("summary"))
    return {
        "feature_store_status": feature.get("status"),
        "quote_source": _as_dict(feature.get("inputs")).get("source_label"),
        "quote_snapshot_kind": _as_dict(feature.get("inputs")).get("snapshot_kind"),
        "quote_data_trust": _as_dict(feature.get("inputs")).get("data_trust"),
        "shared_quote_date_count": feature_summary.get("shared_quote_date_count"),
        "shared_quote_date_start": feature_summary.get("first_shared_quote_date_et") or feature_summary.get("shared_quote_date_start"),
        "shared_quote_date_end": feature_summary.get("latest_shared_quote_date_et") or feature_summary.get("shared_quote_date_end"),
        "robust_search_status": robust_search.get("status"),
        "accepted_exact_trade_count": robust_summary.get("accepted_exact_trade_count"),
        "ready_candidate_count": robust_summary.get("ready_candidate_count"),
        "source_quality_gate_status": robust_summary.get("source_quality_gate_status"),
        "walk_forward_status": walk.get("status"),
        "promotion_ready": walk_summary.get("promotion_ready"),
        "monthly_baseline_profit_factor": monthly_summary.get("baseline_profit_factor"),
        "monthly_baseline_avg_net_pnl_pct": monthly_summary.get("baseline_avg_net_pnl_pct"),
    }


def _split_summary(robust_search: dict[str, Any], walk: dict[str, Any]) -> dict[str, Any]:
    robust_summary = _as_dict(robust_search.get("summary"))
    walk_summary = _as_dict(walk.get("summary"))
    return {
        "split_policy": robust_search.get("split_policy"),
        "variants_searched_upstream": robust_summary.get("variants_searched"),
        "selection_adjusted_bar": robust_summary.get("selection_adjusted_bar"),
        "latest_candidate_entry_date": walk_summary.get("latest_candidate_entry_date"),
        "protected_forward_holdout_start_date": walk_summary.get("protected_forward_holdout_start_date"),
        "protected_forward_holdout_overlap": walk_summary.get("protected_forward_holdout_overlap"),
        "forward_holdout_guard_status": walk_summary.get("forward_holdout_guard_status"),
        "promotion_ready": walk_summary.get("promotion_ready"),
    }


def _concentration_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    ticker = [row for row in candidates if row.get("decision") == "ticker_concentrated_reject"]
    month = [row for row in candidates if row.get("decision") == "month_concentrated_reject"]
    return {
        "ticker_concentration_flagged_count": len(ticker),
        "month_concentration_flagged_count": len(month),
        "flagged_ticker_candidates": [
            {"candidate_id": row.get("candidate_id"), "ticker_concentration": row.get("ticker_concentration")}
            for row in ticker[:10]
        ],
        "flagged_month_candidates": [
            {"candidate_id": row.get("candidate_id"), "month_concentration": row.get("month_concentration")}
            for row in month[:10]
        ],
    }


def _stress_test_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        {
            "candidate_id": row.get("candidate_id"),
            "decision": row.get("decision"),
            "stress_results": row.get("stress_results"),
            "top_winner_dependency": row.get("top_winner_dependency"),
        }
        for row in candidates
        if row.get("stress_results") or row.get("top_winner_dependency")
    ]
    return {
        "stress_rows_reported": len(rows),
        "stress_failed_count": sum(1 for row in candidates if "stress" in " ".join(_as_list(row.get("reason_codes")))),
        "rows": rows[:30],
    }


def _forward_freeze_spec(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    forward = [row for row in candidates if row.get("decision") == "forward_freeze_candidate"]
    if not forward:
        return None
    best = forward[0]
    return {
        "candidate_id": best.get("candidate_id"),
        "frozen_lane_id": best.get("lane_id"),
        "proposed_lane_id": best.get("lane_id"),
        "exact_entry_rules": best.get("rule_summary"),
        "exact_exclusion_rules": "No midpoint/EOD/stale/manual/display-only/last/model proof; reject unpriced, zero-bid, source-quality blocked, or concentration-failed rows.",
        "evidence_requirements": list(REQUIRED_EVIDENCE_BEFORE_LIVE_DISCUSSION),
        "forward_paper_validation_start_condition": "Only after operator accepts this read-only spec as frozen for paper validation.",
        "minimum_post_freeze_sample": 30,
        "pass_fail_gates": [
            "positive post-freeze exact realized net P&L",
            "post-freeze PF lower bound above 1.0",
            "no open-risk governor blocker",
            "no proof-source contamination",
        ],
        "stop_conditions_for_invalidating_candidate": [
            "PF below 1.0 after at least 30 exact realized rows",
            "source-quality contamination",
            "open-risk blocker unresolved",
            "rule drift after freeze",
        ],
        "not_live_permission": True,
    }


def _next_hypothesis_queue(candidates: list[dict[str, Any]], missed_failures: dict[str, Any], missed_filter_matrix: dict[str, Any]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    paper = [row for row in candidates if row.get("decision") == "paper_shadow_candidate"]
    if paper:
        best = paper[0]
        queue.append(
            {
                "priority": 1,
                "hypothesis_id": "collect_forward_exact_paper_shadow_for_best_lane",
                "candidate_id": best.get("candidate_id"),
                "lane_id": best.get("lane_id"),
                "action": "freeze no live behavior; collect fresh exact paper entries and policy-defined exact realized exits",
                "why": "best current lane is positive but lacks forward exact realized P&L and holdout depth",
            }
        )
    for row in candidates:
        if row.get("decision") in {"repair_needed", "execution_fragile_reject"}:
            queue.append(
                {
                    "priority": 2,
                    "hypothesis_id": "repair_source_quality_or_execution_fragility",
                    "candidate_id": row.get("candidate_id"),
                    "lane_id": row.get("lane_id"),
                    "action": row.get("next_step"),
                    "why": ", ".join(_as_list(row.get("reason_codes"))[:4]),
                }
            )
            break
    for row in _as_list(missed_filter_matrix.get("ranked_scenarios_by_kept_profit_factor"))[:3]:
        row = _as_dict(row)
        queue.append(
            {
                "priority": 3,
                "hypothesis_id": f"diagnostic_filter_matrix_{row.get('scenario_id')}",
                "candidate_id": f"filter:{row.get('scenario_id')}",
                "lane_id": "multi_lane_filter_matrix",
                "action": "preregister as diagnostic point-in-time replay only; do not change scanner policy",
                "why": f"kept_count={row.get('kept_count')} pf={row.get('profit_factor')} status={row.get('status')} lost_winners={row.get('lost_winner_count')}",
            }
        )
    guardrails = _as_dict(missed_failures.get("guardrail_candidates"))
    for label in ("debit_pct_gte_45_diagnostic", "dte_gte_36_diagnostic"):
        metric = _as_dict(guardrails.get(label))
        if metric:
            queue.append(
                {
                    "priority": 4,
                    "hypothesis_id": label,
                    "candidate_id": label,
                    "lane_id": "multi_lane_guardrail_diagnostic",
                    "action": "keep as simple diagnostic exclusion candidate for future preregistered replay",
                    "why": f"rows={metric.get('rows')} pf={metric.get('profit_factor')} avg={metric.get('avg_net_pnl_pct')}",
                }
            )
    queue.append(
        {
            "priority": 9,
            "hypothesis_id": "keep_quarantined_lanes_parked",
            "candidate_id": None,
            "lane_id": "quarantined_lanes",
            "action": "do not resurrect no-chase lanes without fresh exact earn-back evidence",
            "why": "quarantined lanes remain negative or no-chase in current readbacks",
        }
    )
    return queue[:15]


def build_report(
    *,
    robust_edge_path: Path = DEFAULT_ROBUST_EDGE,
    robust_search_path: Path = DEFAULT_ROBUST_SEARCH,
    walk_forward_path: Path = DEFAULT_WALK_FORWARD,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    monthly_audit_path: Path = DEFAULT_MONTHLY_AUDIT,
    missed_filter_matrix_path: Path = DEFAULT_MISSED_FILTER_MATRIX,
    missed_failures_path: Path = DEFAULT_MISSED_FAILURES,
    lane_promotion_path: Path = DEFAULT_LANE_PROMOTION,
    generated_at_utc: str | None = None,
    max_source_age_hours: int = MAX_SOURCE_AGE_HOURS,
    max_variants: int = DEFAULT_MAX_VARIANTS,
    min_trades: int = DEFAULT_MIN_TRADES,
    min_holdout_trades: int = DEFAULT_MIN_HOLDOUT_TRADES,
    min_months: int = DEFAULT_MIN_MONTHS,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    specs = {
        "robust_edge_discovery": (robust_edge_path, True),
        "robust_search": (robust_search_path, True),
        "historical_walk_forward": (walk_forward_path, True),
        "feature_store": (feature_store_path, True),
        "monthly_profitability": (monthly_audit_path, True),
        "missed_filter_matrix": (missed_filter_matrix_path, True),
        "missed_failures": (missed_failures_path, True),
        "lane_promotion_state": (lane_promotion_path, True),
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
    raw_candidates = _candidate_pool(loaded["robust_edge_discovery"], loaded["missed_filter_matrix"])
    candidates = _classify_all(
        raw_candidates,
        source_status_blocked=source_status_blocked,
        max_variants=max_variants,
        min_trades=min_trades,
        min_holdout_trades=min_holdout_trades,
        min_months=min_months,
    )
    counts = Counter(row.get("decision") for row in candidates)
    rejected_decisions = {
        "overfit_reject",
        "execution_fragile_reject",
        "regime_fragile_reject",
        "ticker_concentrated_reject",
        "month_concentrated_reject",
        "holdout_fail_reject",
        "insufficient_holdout_reject",
        "quarantine_no_chase",
    }
    blocked_decisions = {"repair_needed", "needs_replay_engine", "insufficient_data", "blocked_missing_readbacks"}
    forward = [row for row in candidates if row.get("decision") == "forward_freeze_candidate"]
    paper = [row for row in candidates if row.get("decision") == "paper_shadow_candidate"]
    thin = [row for row in candidates if row.get("decision") == "thin_sample_watch"]
    best = forward[0] if forward else (paper[0] if paper else (thin[0] if thin else (candidates[0] if candidates else None)))
    forward_spec = _forward_freeze_spec(candidates)

    report = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": "regular_options_hypothesis_tournament_read_only",
        "read_only": True,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "broker_order_allowed": False,
        "is_trade_recommendation": False,
        "overall_status": _overall_status(source_artifacts, candidates, loaded["robust_edge_discovery"]),
        "source_artifacts": source_artifacts,
        "search_budget": {
            "max_variants": max_variants,
            "min_trades": min_trades,
            "min_holdout_trades": min_holdout_trades,
            "min_months": min_months,
            "selection_adjusted_bar_preserved": _as_dict(loaded["robust_search"].get("summary")).get("selection_adjusted_bar"),
            "budget_enforced": len(raw_candidates) > max_variants,
            "raw_candidate_count": len(raw_candidates),
        },
        "variants_tested": len(candidates),
        "candidate_count": len(candidates),
        "forward_freeze_candidate_count": counts.get("forward_freeze_candidate", 0),
        "paper_shadow_candidate_count": counts.get("paper_shadow_candidate", 0),
        "thin_sample_watch_count": counts.get("thin_sample_watch", 0),
        "rejected_candidate_count": sum(counts.get(item, 0) for item in rejected_decisions),
        "blocked_candidate_count": sum(counts.get(item, 0) for item in blocked_decisions),
        "best_candidate_if_any": best,
        "candidate_rankings": candidates,
        "forward_freeze_spec_if_any": forward_spec,
        "rejected_candidates": [row for row in candidates if row.get("decision") in rejected_decisions],
        "stress_test_summary": _stress_test_summary(candidates),
        "split_summary": _split_summary(loaded["robust_search"], loaded["historical_walk_forward"]),
        "concentration_summary": _concentration_summary(candidates),
        "data_coverage_summary": _data_coverage_summary(
            loaded["feature_store"],
            loaded["robust_search"],
            loaded["historical_walk_forward"],
            loaded["monthly_profitability"],
        ),
        "required_evidence_before_live_discussion": list(REQUIRED_EVIDENCE_BEFORE_LIVE_DISCUSSION),
        "operator_next_steps": [
            "Do not forward-freeze a new candidate unless this report emits forward_freeze_candidate.",
            "Keep volatility_expansion_observation paper-shadow only and collect fresh exact realized evidence.",
            "Use the next_hypothesis_queue for preregistered diagnostic experiments only.",
            "Repair source-quality, unpriced, zero-bid, and coverage blockers before rerunning candidate scoring.",
        ],
        "next_hypothesis_queue": _next_hypothesis_queue(candidates, loaded["missed_failures"], loaded["missed_filter_matrix"]),
        "prohibited_actions": _unique(
            [
                *PROHIBITED_ACTIONS,
                *_as_list(loaded["robust_edge_discovery"].get("prohibited_actions")),
                *_as_list(loaded["robust_search"].get("prohibited_actions")),
                *_as_list(loaded["historical_walk_forward"].get("prohibited_actions")),
                *_as_list(loaded["monthly_profitability"].get("prohibited_actions")),
            ]
        ),
        "non_goals": list(NON_GOALS),
        "decision_counts": dict(sorted(counts.items())),
        "existing_promotion_ready": bool(_as_dict(loaded["historical_walk_forward"].get("summary")).get("promotion_ready")),
        "robust_edge_overall_status": loaded["robust_edge_discovery"].get("overall_status"),
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
        "| Candidate | Decision | Complexity | Exact | Holdout | PF | PF LB | Avg % | Reasons |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows[:limit]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(row.get('candidate_id'))}`",
                    f"`{_cell(row.get('decision'))}`",
                    _cell(row.get("complexity_score")),
                    _cell(row.get("total_exact_rows")),
                    _cell(row.get("holdout_rows")),
                    _cell(row.get("profit_factor")),
                    _cell(row.get("profit_factor_lower_bound")),
                    _cell(row.get("avg_net_pnl_pct")),
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
    if overall == "forward_freeze_candidate_found":
        conclusion = f"Candidate `{best.get('candidate_id')}` is ready for frozen forward paper validation only."
    elif overall == "paper_shadow_only":
        conclusion = "No tournament candidate is ready for forward freeze. Current state remains paper-shadow only."
    else:
        conclusion = "No tournament candidate survived the current local evidence gates."
    data = _as_dict(report.get("data_coverage_summary"))
    budget = _as_dict(report.get("search_budget"))
    candidates = [_as_dict(row) for row in _as_list(report.get("candidate_rankings"))]
    rejected = [_as_dict(row) for row in _as_list(report.get("rejected_candidates"))]
    forward_spec = report.get("forward_freeze_spec_if_any")
    lines = [
        "# Regular Options Hypothesis Tournament",
        "",
        conclusion,
        "",
        "## Search budget and variants tested",
        "",
        f"- Max variants: `{budget.get('max_variants')}`.",
        f"- Raw candidate count: `{budget.get('raw_candidate_count')}`.",
        f"- Variants tested: `{report.get('variants_tested')}`.",
        f"- Budget enforced: `{budget.get('budget_enforced')}`.",
        f"- Min trades / holdout / months: `{budget.get('min_trades')}` / `{budget.get('min_holdout_trades')}` / `{budget.get('min_months')}`.",
        f"- Selection-adjusted bar preserved from robust search: `{budget.get('selection_adjusted_bar_preserved')}`.",
        "",
        "## Data/proof standard",
        "",
        f"- Feature store: `{data.get('feature_store_status')}` with `{data.get('shared_quote_date_count')}` shared dates from `{data.get('shared_quote_date_start')}` to `{data.get('shared_quote_date_end')}`.",
        f"- Quote source: `{data.get('quote_source')}` / `{data.get('quote_snapshot_kind')}` / `{data.get('quote_data_trust')}`.",
        f"- Robust search: `{data.get('robust_search_status')}`, accepted exact rows `{data.get('accepted_exact_trade_count')}`, ready candidates `{data.get('ready_candidate_count')}`.",
        f"- Walk-forward: `{data.get('walk_forward_status')}`, promotion ready `{data.get('promotion_ready')}`.",
        "- Counted proof must be executable exact options evidence, not midpoint/EOD/stale/manual/display-only/last/model marks.",
        "",
        "## Best candidate, if any",
        "",
        f"- Candidate: `{best.get('candidate_id')}`.",
        f"- Decision: `{best.get('decision')}`.",
        f"- Lane: `{best.get('lane_id')}`.",
        f"- Exact / holdout rows: `{best.get('total_exact_rows')}` / `{best.get('holdout_rows')}`.",
        f"- PF / PF lower bound / avg: `{best.get('profit_factor')}` / `{best.get('profit_factor_lower_bound')}` / `{best.get('avg_net_pnl_pct')}`.",
        f"- Next step: {_norm(best.get('next_step')).rstrip('.')}.",
        "",
        "## Candidate leaderboard",
        "",
        *_candidate_table(candidates),
        "",
        "## Rejection table with reason codes",
        "",
        *_candidate_table(rejected),
        "",
        "## Stress-test summary",
        "",
        f"- `{_json_text(report.get('stress_test_summary'))}`",
        "",
        "## Split/holdout summary",
        "",
        f"- `{_json_text(report.get('split_summary'))}`",
        "",
        "## Concentration analysis",
        "",
        f"- `{_json_text(report.get('concentration_summary'))}`",
        "",
        "## Forward-freeze spec if any",
        "",
    ]
    if forward_spec:
        lines.append(f"- `{_json_text(forward_spec)}`")
    else:
        lines.append("- None. No candidate passed the tournament gates.")
    lines.extend(["", "## If no candidate survived, next hypothesis queue", ""])
    for item in _as_list(report.get("next_hypothesis_queue")):
        item = _as_dict(item)
        lines.append(
            f"- Priority `{item.get('priority')}` `{item.get('hypothesis_id')}`: {item.get('action')} ({item.get('why')})."
        )
    lines.extend(["", "## Requirements before live discussion", ""])
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
    lines.extend(["", "## Non-goals", "", "This workflow does not:", ""])
    lines.extend(f"- {item}" for item in _as_list(report.get("non_goals")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "latest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    docs_report.write_text(render_markdown(report), encoding="utf8")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build regular-options hypothesis tournament report.")
    parser.add_argument("--robust-edge", type=Path, default=DEFAULT_ROBUST_EDGE)
    parser.add_argument("--robust-search", type=Path, default=DEFAULT_ROBUST_SEARCH)
    parser.add_argument("--walk-forward", type=Path, default=DEFAULT_WALK_FORWARD)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--monthly-audit", type=Path, default=DEFAULT_MONTHLY_AUDIT)
    parser.add_argument("--missed-filter-matrix", type=Path, default=DEFAULT_MISSED_FILTER_MATRIX)
    parser.add_argument("--missed-failures", type=Path, default=DEFAULT_MISSED_FAILURES)
    parser.add_argument("--lane-promotion", type=Path, default=DEFAULT_LANE_PROMOTION)
    parser.add_argument("--max-source-age-hours", type=int, default=MAX_SOURCE_AGE_HOURS)
    parser.add_argument("--max-variants", type=int, default=DEFAULT_MAX_VARIANTS)
    parser.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES)
    parser.add_argument("--min-holdout-trades", type=int, default=DEFAULT_MIN_HOLDOUT_TRADES)
    parser.add_argument("--min-months", type=int, default=DEFAULT_MIN_MONTHS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", dest="json_output", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        robust_edge_path=args.robust_edge,
        robust_search_path=args.robust_search,
        walk_forward_path=args.walk_forward,
        feature_store_path=args.feature_store,
        monthly_audit_path=args.monthly_audit,
        missed_filter_matrix_path=args.missed_filter_matrix,
        missed_failures_path=args.missed_failures,
        lane_promotion_path=args.lane_promotion,
        max_source_age_hours=args.max_source_age_hours,
        max_variants=args.max_variants,
        min_trades=args.min_trades,
        min_holdout_trades=args.min_holdout_trades,
        min_months=args.min_months,
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
