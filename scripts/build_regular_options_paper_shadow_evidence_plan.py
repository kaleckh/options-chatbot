from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_paper_shadow_evidence_plan"

DEFAULT_TRADE_QUALIFICATION = ROOT / "data" / "forward-tracking" / "regular_options_trade_qualification_latest.json"
DEFAULT_GATEBOARD = ROOT / "data" / "forward-tracking" / "project_operator_gateboard_latest.json"
DEFAULT_MONTHLY_PROFITABILITY = ROOT / "data" / "forward-tracking" / "monthly_all_lanes_profitability_audit_latest.json"
DEFAULT_LANE_PROMOTION = ROOT / "data" / "forward-tracking" / "lane_promotion_state_latest.json"
DEFAULT_CANDIDATE_LEDGER = ROOT / "data" / "forward-tracking" / "regular_options_candidate_outcome_ledger_latest.json"
DEFAULT_FRESH_EVIDENCE = ROOT / "data" / "forward-tracking" / "regular_options_fresh_evidence_loop_latest.json"
DEFAULT_FILL_ATTEMPT_PLAN = ROOT / "data" / "forward-tracking" / "regular_options_fill_attempt_evidence_capture_plan_latest.json"
DEFAULT_SUGGESTED_REVIEW_PLAN = ROOT / "data" / "forward-tracking" / "regular_options_suggested_trade_review_plan_latest.json"
DEFAULT_OPEN_RISK = ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json"
DEFAULT_SUGGESTED_CLOSE_RISK = ROOT / "data" / "forward-tracking" / "suggested_trade_close_risk_latest.json"
DEFAULT_PAPER_SHORTLIST = ROOT / "data" / "profitability-lab" / "regular-options-paper-shortlist" / "latest.json"
DEFAULT_PROFIT_CAPTURE_QUEUE = ROOT / "data" / "profitability-lab" / "regular-options-profit-capture-queue" / "latest.json"
DEFAULT_BULLISH_PULLBACK_LAYER_SHADOW_SELECTION = ROOT / "data" / "forward-tracking" / "bullish_pullback_layer_shadow_selection_latest.json"
DEFAULT_BULLISH_PULLBACK_LAYER_EXECUTION_SAFETY_AUDIT = (
    ROOT / "data" / "forward-tracking" / "bullish_pullback_layer_execution_safety_audit_latest.json"
)
DEFAULT_BULLISH_PULLBACK_LAYER4_FORWARD_CAPTURE_PROTOCOL = (
    ROOT / "data" / "forward-tracking" / "bullish_pullback_layer4_forward_capture_protocol_latest.json"
)
DEFAULT_MARKET_WINDOW_APPROVAL_PREFLIGHT = (
    ROOT / "data" / "forward-tracking" / "regular_options_market_window_approval_preflight_latest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-paper-shadow-evidence-plan.md"
MAX_SOURCE_AGE_HOURS = 96

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_paper_shadow_evidence_plan",
    "do_not_submit_broker_orders_from_paper_shadow_evidence_plan",
    "do_not_change_stops_from_paper_shadow_evidence_plan",
    "do_not_change_scanner_policy_from_paper_shadow_evidence_plan",
    "do_not_change_sizing_from_paper_shadow_evidence_plan",
    "do_not_enable_live_validation_from_paper_shadow_evidence_plan",
    "do_not_enable_auto_track_from_paper_shadow_evidence_plan",
    "do_not_lower_exact_executable_proof_bars_from_paper_shadow_evidence_plan",
    "do_not_mutate_evidence_databases_from_paper_shadow_evidence_plan",
)

REQUIRED_EVIDENCE_BEFORE_PROMOTION = (
    "fresh executable exact OPRA/NBBO entry evidence for the paper-shadow lane after freeze",
    "policy-defined exact executable OPRA/NBBO exit evidence for linked rows",
    "exact realized P&L rows built from executable entry plus executable exit evidence",
    "promotion_ready_count greater than zero from the fresh evidence loop",
    "sufficient fresh forward sample size under the frozen lane gate",
    "no active no-chase or quarantine blocker for the lane",
    "open-risk governor clear in fresh local readbacks",
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
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


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
    generated_dt = _parse_utc(payload.get("generated_at_utc"))
    if generated_dt is None:
        source["status"] = "stale"
        source["reason_codes"] = ["missing_or_malformed_generated_at_utc", "stale_readback"]
        return payload, source
    age_hours = (as_of - generated_dt).total_seconds() / 3600
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


def _source_blocked(source_artifacts: dict[str, dict[str, Any]]) -> bool:
    return any(meta.get("required") and meta.get("status") != "loaded" for meta in source_artifacts.values())


def _open_risk_blocked(open_risk: dict[str, Any], trade_qualification: dict[str, Any]) -> bool:
    governor = _as_dict(open_risk.get("open_risk_governor"))
    triage_open = _as_dict(trade_qualification.get("open_risk_status"))
    status_values = [_norm(governor.get("status")), _norm(triage_open.get("status"))]
    return any("blocked" in value for value in status_values) or governor.get("live_entry_allowed") is False


def _best_lane(trade_qualification: dict[str, Any]) -> dict[str, Any] | None:
    best = _as_dict(trade_qualification.get("best_current_lane_if_any"))
    lane_id = _norm(best.get("lane_id"))
    if not lane_id:
        return None
    for row in _as_list(trade_qualification.get("lane_decisions")):
        if isinstance(row, dict) and _norm(row.get("lane_id")) == lane_id:
            if row.get("decision") == "paper_shadow_collect" and _norm(row.get("disposition")) in {"paper_shadow", ""}:
                return {
                    **best,
                    "promotion_state": row.get("promotion_state"),
                    "disposition": row.get("disposition"),
                    "reason_codes": _as_list(row.get("reason_codes")),
                }
    return None


def _base_action(
    *,
    action_id: str,
    priority: int,
    action_type: str,
    status: str,
    source_artifact: str,
    lane_id: Any = None,
    ticker: Any = None,
    position_id: Any = None,
    candidate_id: Any = None,
    suggested_trade_id: Any = None,
    scan_date: Any = None,
    reason_codes: list[Any] | None = None,
    market_window_required: bool = False,
    requires_policy_exit_condition: bool = False,
    requires_exact_entry_evidence: bool = False,
    requires_exact_exit_evidence: bool = False,
    requires_fill_attempt_evidence: bool = False,
    requires_operator_review: bool = False,
    next_operator_step: str = "",
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "priority": priority,
        "action_type": action_type,
        "lane_id": lane_id,
        "ticker": ticker,
        "position_id": position_id,
        "candidate_id": candidate_id,
        "suggested_trade_id": suggested_trade_id,
        "scan_date": scan_date,
        "source_artifact": source_artifact,
        "status": status,
        "reason_codes": _unique(reason_codes or []),
        "market_window_required": bool(market_window_required),
        "requires_policy_exit_condition": bool(requires_policy_exit_condition),
        "requires_exact_entry_evidence": bool(requires_exact_entry_evidence),
        "requires_exact_exit_evidence": bool(requires_exact_exit_evidence),
        "requires_fill_attempt_evidence": bool(requires_fill_attempt_evidence),
        "requires_operator_review": bool(requires_operator_review),
        "is_trade_recommendation": False,
        "is_broker_order": False,
        "next_operator_step": next_operator_step,
    }


def _ledger_actions(candidate_ledger: dict[str, Any], *, open_risk_blocked: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for row in _as_list(candidate_ledger.get("ledger_rows")):
        if not isinstance(row, dict):
            continue
        action = _norm(row.get("next_evidence_action"))
        if action == "collect_exact_exit_evidence":
            actions.append(
                _base_action(
                    action_id="exact_exit:" + _norm(row.get("ledger_key") or row.get("candidate_key")),
                    priority=2,
                    action_type="collect_exact_exit_evidence",
                    lane_id=row.get("lane_id"),
                    ticker=row.get("ticker") or row.get("symbol"),
                    position_id=row.get("position_id"),
                    candidate_id=row.get("candidate_key"),
                    scan_date=row.get("scan_date"),
                    source_artifact="candidate_outcome_ledger",
                    status="waiting_for_policy_exit",
                    reason_codes=_as_list(row.get("blocking_reasons")) + [_norm(row.get("action_reason"))],
                    market_window_required=True,
                    requires_policy_exit_condition=True,
                    requires_exact_exit_evidence=True,
                    next_operator_step="Collect exact executable exit evidence only after a policy-defined exit condition fires; do not force a close to manufacture evidence.",
                )
            )
        elif action == "capture_paper_only_exact_entry":
            status = "blocked_by_open_risk" if open_risk_blocked else "ready_for_market_window"
            actions.append(
                _base_action(
                    action_id="exact_entry:" + _norm(row.get("ledger_key") or row.get("candidate_key")),
                    priority=3,
                    action_type="collect_exact_entry_evidence",
                    lane_id=row.get("lane_id"),
                    ticker=row.get("ticker") or row.get("symbol"),
                    position_id=row.get("position_id"),
                    candidate_id=row.get("candidate_key"),
                    scan_date=row.get("scan_date"),
                    source_artifact="candidate_outcome_ledger",
                    status=status,
                    reason_codes=_as_list(row.get("blocking_reasons")) + [_norm(row.get("action_reason"))],
                    market_window_required=True,
                    requires_exact_entry_evidence=True,
                    requires_operator_review=True,
                    next_operator_step="During a valid market-data window, capture fresh executable exact entry evidence for this paper/probation candidate only if it is still freshly selected.",
                )
            )
    return actions


def _fill_attempt_actions(fill_attempt_plan: dict[str, Any], *, open_risk_blocked: bool) -> list[dict[str, Any]]:
    actions = []
    for row in _as_list(fill_attempt_plan.get("plan_rows")):
        if not isinstance(row, dict):
            continue
        status = "blocked_by_open_risk" if open_risk_blocked else "blocked_missing_fill_attempt"
        actions.append(
            _base_action(
                action_id="fill_attempt:" + _norm(row.get("ledger_key") or row.get("candidate_key")),
                priority=4,
                action_type="capture_fill_attempt_evidence",
                lane_id=row.get("lane_id"),
                ticker=row.get("ticker"),
                candidate_id=row.get("candidate_key"),
                scan_date=row.get("scan_date"),
                source_artifact="fill_attempt_evidence_capture_plan",
                status=status,
                reason_codes=_as_list(row.get("blocking_reasons")),
                market_window_required=bool(row.get("market_window_required", True)),
                requires_fill_attempt_evidence=True,
                requires_operator_review=True,
                next_operator_step=_norm(row.get("operator_next_step"))
                or "Capture durable fill-attempt evidence only for fresh selections during a valid market-data window.",
            )
        )
    return actions


def _suggested_review_actions(suggested_review_plan: dict[str, Any]) -> list[dict[str, Any]]:
    actions = []
    for row in _as_list(suggested_review_plan.get("plan_rows")):
        if not isinstance(row, dict):
            continue
        actions.append(
            _base_action(
                action_id="suggested_review:" + _norm(row.get("suggested_trade_id")),
                priority=5,
                action_type="refresh_suggested_trade_review",
                lane_id=row.get("lane"),
                ticker=row.get("ticker"),
                suggested_trade_id=row.get("suggested_trade_id"),
                source_artifact="suggested_trade_review_plan",
                status="review_only",
                reason_codes=[row.get("action_bucket"), row.get("evidence_bucket"), row.get("resolution_status")],
                market_window_required=bool(row.get("market_window_required", True)),
                requires_operator_review=True,
                next_operator_step=_norm(row.get("operator_next_step"))
                or "Refresh suggested-trade review during a fresh executable quote window; this is not a recommendation.",
            )
        )
    return actions


def _repair_actions(profit_capture_queue: dict[str, Any]) -> list[dict[str, Any]]:
    actions = []
    for row in _as_list(profit_capture_queue.get("evidence_repair_queue")):
        if not isinstance(row, dict):
            continue
        repair = _as_dict(row.get("repair_actionability"))
        if _norm(repair.get("status")) != "needs_status_or_forward_validation_after_repair":
            continue
        actions.append(
            _base_action(
                action_id="repair:" + "|".join([_norm(row.get("lane_id")), _norm(row.get("symbol"))]),
                priority=6,
                action_type="repair_replay_evidence",
                lane_id=row.get("lane_id"),
                ticker=row.get("symbol"),
                source_artifact="profit_capture_queue",
                status="repair_only",
                reason_codes=_as_list(row.get("reason_codes")) + [repair.get("status")],
                next_operator_step=_norm(repair.get("next_action"))
                or "Repair replay/source evidence only for active, unexhausted targets; do not count repair rows as fresh proof.",
            )
        )
    return actions


def _quarantine_actions(trade_qualification: dict[str, Any]) -> list[dict[str, Any]]:
    actions = []
    for row in _as_list(trade_qualification.get("lane_decisions")):
        if not isinstance(row, dict) or row.get("decision") != "quarantine_no_chase":
            continue
        lane = _norm(row.get("lane_id"))
        actions.append(
            _base_action(
                action_id="no_chase:" + lane,
                priority=7,
                action_type="no_chase_quarantine",
                lane_id=lane,
                source_artifact="trade_qualification",
                status="no_action",
                reason_codes=_as_list(row.get("reason_codes")),
                next_operator_step="Keep this lane parked. Do not chase, promote, or create fresh paper actions from quarantined evidence.",
            )
        )
    return actions


def _best_lane_wait_action(best_lane: dict[str, Any] | None, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not best_lane:
        return []
    lane = _norm(best_lane.get("lane_id"))
    has_lane_entry = any(action.get("lane_id") == lane and action.get("action_type") == "collect_exact_entry_evidence" for action in actions)
    if has_lane_entry:
        return []
    return [
        _base_action(
            action_id="wait_fresh_candidate:" + lane,
            priority=3,
            action_type="wait_for_fresh_candidate",
            lane_id=lane,
            source_artifact="trade_qualification",
            status="waiting_for_fresh_candidate",
            reason_codes=["best_paper_shadow_lane_needs_fresh_exact_bridge"],
            next_operator_step="Wait for a fresh scanner selection in the paper-shadow lane, then capture exact executable entry evidence during the valid market-data window.",
            requires_exact_entry_evidence=True,
        )
    ]


def _layer_shadow_harness_actions(selection: dict[str, Any]) -> list[dict[str, Any]]:
    if not selection or selection.get("overall_status") != "layer_shadow_selection_ready":
        return []
    requirements = _as_dict(selection.get("harness_requirements"))
    primary = _as_dict(selection.get("primary_harness_layer"))
    layer_id = _norm(requirements.get("selected_layer_id") or primary.get("layer_id"))
    variant_id = _norm(requirements.get("selected_variant_id") or primary.get("variant_id"))
    if not layer_id or not variant_id:
        return []
    action = _base_action(
        action_id="layer_shadow_harness:" + layer_id,
        priority=3,
        action_type="prepare_bullish_pullback_layer_shadow_harness",
        lane_id="bullish_pullback_observation",
        source_artifact="bullish_pullback_layer_shadow_selection",
        status="waiting_for_market_window",
        reason_codes=[
            "bullish_pullback_layer_stack_selected",
            "future_natural_market_window_evidence_only",
            "not_trade_recommendation",
        ],
        market_window_required=True,
        requires_exact_entry_evidence=True,
        requires_exact_exit_evidence=True,
        requires_operator_review=True,
        next_operator_step=(
            "Use selected bullish-pullback layer "
            + layer_id
            + " / "
            + variant_id
            + " as the future paper-shadow harness target only when a fresh natural market-window selection appears."
        ),
    )
    action.update(
        {
            "selected_layer_id": layer_id,
            "selected_variant_id": variant_id,
            "source_result_path": requirements.get("source_result_path") or primary.get("source_result_path"),
            "allowed_symbols": _as_list(selection.get("allowed_symbols") or requirements.get("allowed_symbols")),
            "harness_requirements": requirements,
            "target_truth": selection.get("target_truth"),
            "count_expanded_reference": selection.get("count_expanded_reference"),
            "high_pf_core_reference": selection.get("high_pf_core_reference"),
            "leg_level_bid_ask_audit_required": True,
            "assignment_expiration_risk_review_required": True,
            "denominator_failure_row_handling_required": True,
        }
    )
    return [action]


def _layer_execution_safety_preflight_actions(audit: dict[str, Any]) -> list[dict[str, Any]]:
    if not audit or audit.get("report_id") != "bullish_pullback_layer_execution_safety_audit":
        return []
    selected = _as_dict(audit.get("selected_layer"))
    layer_id = _norm(selected.get("layer_id"))
    variant_id = _norm(selected.get("variant_id"))
    if not layer_id or not variant_id:
        return []
    ready = audit.get("overall_status") == "ready_for_future_market_window_paper_shadow_preflight"
    action = _base_action(
        action_id="execution_safety_preflight:" + layer_id,
        priority=3,
        action_type="bullish_pullback_layer_4_execution_safety_preflight",
        lane_id="bullish_pullback_observation",
        source_artifact="bullish_pullback_layer_execution_safety_audit",
        status="preflight_ready_waiting_for_market_window" if ready else "blocked_execution_safety_preflight",
        reason_codes=(
            ["execution_safety_preflight_ready", "future_natural_market_window_evidence_only"]
            if ready
            else _as_list(audit.get("blockers"))
        ),
        market_window_required=False,
        requires_exact_entry_evidence=True,
        requires_exact_exit_evidence=True,
        requires_operator_review=True,
        next_operator_step=(
            "Resolve blocked leg-level bid/ask execution-safety preflight before using the selected bullish-pullback layer as a market-window paper-shadow harness."
            if not ready
            else "Keep this preflight attached as a required check before future natural market-window paper-shadow evidence collection."
        ),
    )
    action.update(
        {
            "selected_layer_id": layer_id,
            "selected_variant_id": variant_id,
            "source_result_path": selected.get("source_result_path"),
            "execution_safety_audit_status": audit.get("overall_status"),
            "execution_safety_row_counts": audit.get("row_counts"),
            "fatal_reason_counts": audit.get("fatal_reason_counts"),
            "preflight_requirements": audit.get("preflight_requirements"),
            "leg_level_bid_ask_audit_required": True,
            "assignment_expiration_risk_review_required": True,
            "denominator_failure_row_handling_required": True,
            "is_trade_recommendation": False,
            "is_broker_order": False,
        }
    )
    return [action]


def _layer4_forward_capture_protocol_actions(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    if not protocol or protocol.get("report_id") != "bullish_pullback_layer4_forward_capture_protocol":
        return []
    selected = _as_dict(protocol.get("selected_harness"))
    layer_id = _norm(selected.get("layer_id"))
    variant_id = _norm(selected.get("variant_id"))
    if not layer_id or not variant_id:
        return []
    ready = protocol.get("capture_protocol_status") == "protocol_ready_waiting_for_market_window_and_operator_approval"
    action = _base_action(
        action_id="layer4_forward_capture_protocol:" + layer_id,
        priority=3,
        action_type="bullish_pullback_layer4_capture_protocol_ready_waiting_for_market_window_and_operator_approval",
        lane_id="bullish_pullback_observation",
        source_artifact="bullish_pullback_layer4_forward_capture_protocol",
        status="waiting_for_market_window_and_operator_approval" if ready else "blocked_capture_protocol",
        reason_codes=(
            ["capture_protocol_ready", "future_natural_market_window_evidence_only", "operator_approval_required"]
            if ready
            else _as_list(protocol.get("blockers"))
        ),
        market_window_required=True,
        requires_exact_entry_evidence=True,
        requires_exact_exit_evidence=True,
        requires_operator_review=True,
        next_operator_step=(
            "Use the bullish-pullback layer4 protocol only for future natural paper-shadow denominator rows after a valid market-data window and separate operator approval."
            if ready
            else "Resolve blocked bullish-pullback layer4 capture protocol inputs before any future market-window row collection."
        ),
    )
    action.update(
        {
            "selected_layer_id": layer_id,
            "selected_variant_id": variant_id,
            "source_result_path": selected.get("source_result_path"),
            "allowed_symbols": _as_list(selected.get("allowed_symbols")),
            "capture_protocol_status": protocol.get("capture_protocol_status"),
            "historical_executable_economics": protocol.get("historical_executable_economics"),
            "protocol_requirements": protocol.get("protocol_requirements"),
            "candidate_validator_read_only": bool(protocol.get("candidate_validator_read_only")),
            "cohort_append_performed": bool(protocol.get("cohort_append_performed")),
            "live_entry_allowed": False,
            "auto_track_allowed": False,
            "broker_order_allowed": False,
            "is_trade_recommendation": False,
            "is_broker_order": False,
        }
    )
    return [action]


def _open_risk_actions(open_risk: dict[str, Any], trade_qualification: dict[str, Any], *, open_risk_blocked: bool) -> list[dict[str, Any]]:
    if not open_risk_blocked:
        return []
    governor = _as_dict(open_risk.get("open_risk_governor"))
    triage_open = _as_dict(trade_qualification.get("open_risk_status"))
    return [
        _base_action(
            action_id="open_risk:governor",
            priority=1,
            action_type="review_open_risk",
            source_artifact="open_position_risk",
            status="blocked_by_open_risk",
            reason_codes=_as_list(governor.get("blockers")) + _as_list(triage_open.get("reason_codes")),
            market_window_required=True,
            requires_operator_review=True,
            next_operator_step="Review open-risk / linked live-exact rows only with fresh executable review evidence; do not open new scanner-origin entries while blocked.",
        )
    ]


def _counts(actions: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "paper_shadow_action_count": sum(
            1
            for action in actions
            if action.get("action_type")
            in {
                "collect_exact_exit_evidence",
                "collect_exact_entry_evidence",
                "capture_fill_attempt_evidence",
                "wait_for_fresh_candidate",
                "bullish_pullback_layer_4_execution_safety_preflight",
                "prepare_bullish_pullback_layer_shadow_harness",
                "bullish_pullback_layer4_capture_protocol_ready_waiting_for_market_window_and_operator_approval",
            }
        ),
        "market_window_action_count": sum(1 for action in actions if action.get("market_window_required")),
        "waiting_action_count": sum(1 for action in actions if _norm(action.get("status")).startswith("waiting")),
        "blocked_action_count": sum(1 for action in actions if _norm(action.get("status")).startswith("blocked")),
    }


def _blocked_reasons(
    *,
    source_artifacts: dict[str, dict[str, Any]],
    trade_qualification: dict[str, Any],
    best_lane: dict[str, Any] | None,
    open_risk_blocked: bool,
) -> list[str]:
    reasons: list[Any] = []
    for name, source in source_artifacts.items():
        if source.get("required") and source.get("status") != "loaded":
            reasons.append(f"{name}:{','.join(_as_list(source.get('reason_codes')))}")
    if not best_lane:
        reasons.append("no_current_paper_shadow_lane")
    if open_risk_blocked:
        reasons.append("open_risk_governor_blocked")
    if _safe_int(trade_qualification.get("exact_realized_pnl_count")) == 0:
        reasons.append("no_exact_realized_pnl_rows")
    if _safe_int(trade_qualification.get("promotion_ready_count")) == 0:
        reasons.append("no_promotion_ready_rows")
    if trade_qualification.get("live_entry_allowed") is False:
        reasons.append("live_entry_not_allowed")
    if trade_qualification.get("auto_track_allowed") is False:
        reasons.append("auto_track_not_allowed")
    return _unique(reasons)


def _overall_status(
    *,
    source_artifacts: dict[str, dict[str, Any]],
    best_lane: dict[str, Any] | None,
    open_risk_blocked: bool,
    actions: list[dict[str, Any]],
) -> str:
    if _source_blocked(source_artifacts):
        return "blocked_missing_readbacks"
    if open_risk_blocked:
        return "blocked_open_risk"
    if not best_lane:
        return "blocked_no_paper_shadow_lane"
    active_actions = [
        action
        for action in actions
        if action.get("action_type") not in {"repair_replay_evidence", "no_chase_quarantine"}
    ]
    if not active_actions:
        return "waiting_for_fresh_candidates"
    if all(action.get("action_type") == "wait_for_fresh_candidate" for action in active_actions):
        return "waiting_for_fresh_candidates"
    if active_actions and all(action.get("status") in {"repair_only", "no_action"} for action in active_actions):
        return "repair_only"
    return "paper_shadow_evidence_collecting"


def _prohibited_actions(*reports: dict[str, Any]) -> list[str]:
    values: list[Any] = list(PROHIBITED_ACTIONS)
    for report in reports:
        values.extend(_as_list(report.get("prohibited_actions")))
        values.extend(_as_list(_as_dict(report.get("no_chase_manifest")).get("prohibited_actions")))
    return _unique(values)


def build_report(
    *,
    trade_qualification_path: Path = DEFAULT_TRADE_QUALIFICATION,
    gateboard_path: Path = DEFAULT_GATEBOARD,
    monthly_profitability_path: Path = DEFAULT_MONTHLY_PROFITABILITY,
    lane_promotion_path: Path = DEFAULT_LANE_PROMOTION,
    candidate_ledger_path: Path = DEFAULT_CANDIDATE_LEDGER,
    fresh_evidence_path: Path = DEFAULT_FRESH_EVIDENCE,
    fill_attempt_plan_path: Path = DEFAULT_FILL_ATTEMPT_PLAN,
    suggested_review_plan_path: Path = DEFAULT_SUGGESTED_REVIEW_PLAN,
    open_risk_path: Path = DEFAULT_OPEN_RISK,
    suggested_close_risk_path: Path = DEFAULT_SUGGESTED_CLOSE_RISK,
    paper_shortlist_path: Path = DEFAULT_PAPER_SHORTLIST,
    profit_capture_queue_path: Path = DEFAULT_PROFIT_CAPTURE_QUEUE,
    bullish_pullback_layer_shadow_selection_path: Path = DEFAULT_BULLISH_PULLBACK_LAYER_SHADOW_SELECTION,
    bullish_pullback_layer_execution_safety_audit_path: Path = DEFAULT_BULLISH_PULLBACK_LAYER_EXECUTION_SAFETY_AUDIT,
    bullish_pullback_layer4_forward_capture_protocol_path: Path = DEFAULT_BULLISH_PULLBACK_LAYER4_FORWARD_CAPTURE_PROTOCOL,
    market_window_approval_preflight_path: Path = DEFAULT_MARKET_WINDOW_APPROVAL_PREFLIGHT,
    generated_at_utc: str | None = None,
    max_source_age_hours: int = MAX_SOURCE_AGE_HOURS,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    specs = {
        "trade_qualification": (trade_qualification_path, True),
        "gateboard": (gateboard_path, True),
        "monthly_profitability": (monthly_profitability_path, True),
        "lane_promotion_state": (lane_promotion_path, True),
        "candidate_outcome_ledger": (candidate_ledger_path, True),
        "fresh_evidence_loop": (fresh_evidence_path, True),
        "fill_attempt_evidence_capture_plan": (fill_attempt_plan_path, True),
        "suggested_trade_review_plan": (suggested_review_plan_path, True),
        "open_position_risk": (open_risk_path, True),
        "suggested_trade_close_risk": (suggested_close_risk_path, True),
        "paper_shortlist": (paper_shortlist_path, True),
        "profit_capture_queue": (profit_capture_queue_path, True),
        "bullish_pullback_layer_shadow_selection": (bullish_pullback_layer_shadow_selection_path, False),
        "bullish_pullback_layer_execution_safety_audit": (bullish_pullback_layer_execution_safety_audit_path, False),
        "bullish_pullback_layer4_forward_capture_protocol": (bullish_pullback_layer4_forward_capture_protocol_path, False),
        "regular_options_market_window_approval_preflight": (market_window_approval_preflight_path, False),
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

    trade_qualification = loaded["trade_qualification"]
    best_lane = _best_lane(trade_qualification)
    open_blocked = _open_risk_blocked(loaded["open_position_risk"], trade_qualification)

    actions: list[dict[str, Any]] = []
    actions.extend(_open_risk_actions(loaded["open_position_risk"], trade_qualification, open_risk_blocked=open_blocked))
    actions.extend(_ledger_actions(loaded["candidate_outcome_ledger"], open_risk_blocked=open_blocked))
    actions.extend(_best_lane_wait_action(best_lane, actions))
    actions.extend(_layer_execution_safety_preflight_actions(loaded["bullish_pullback_layer_execution_safety_audit"]))
    actions.extend(_layer4_forward_capture_protocol_actions(loaded["bullish_pullback_layer4_forward_capture_protocol"]))
    actions.extend(_layer_shadow_harness_actions(loaded["bullish_pullback_layer_shadow_selection"]))
    actions.extend(_fill_attempt_actions(loaded["fill_attempt_evidence_capture_plan"], open_risk_blocked=open_blocked))
    actions.extend(_suggested_review_actions(loaded["suggested_trade_review_plan"]))
    actions.extend(_repair_actions(loaded["profit_capture_queue"]))
    actions.extend(_quarantine_actions(trade_qualification))
    actions = sorted(actions, key=lambda item: (int(item.get("priority") or 99), _norm(item.get("action_type")), _norm(item.get("action_id"))))

    counts = _counts(actions)
    blocked_reasons = _blocked_reasons(
        source_artifacts=source_artifacts,
        trade_qualification=trade_qualification,
        best_lane=best_lane,
        open_risk_blocked=open_blocked,
    )
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": "regular_options_paper_shadow_evidence_collection_plan",
        "read_only": True,
        "source_artifacts": source_artifacts,
        "overall_status": _overall_status(
            source_artifacts=source_artifacts,
            best_lane=best_lane,
            open_risk_blocked=open_blocked,
            actions=actions,
        ),
        "best_evidence_lane": best_lane,
        "bullish_pullback_layer_shadow_selection": loaded["bullish_pullback_layer_shadow_selection"]
        if loaded["bullish_pullback_layer_shadow_selection"].get("overall_status") == "layer_shadow_selection_ready"
        else None,
        "bullish_pullback_layer_execution_safety_audit": loaded["bullish_pullback_layer_execution_safety_audit"]
        if loaded["bullish_pullback_layer_execution_safety_audit"].get("report_id")
        == "bullish_pullback_layer_execution_safety_audit"
        else None,
        "bullish_pullback_layer4_forward_capture_protocol": loaded["bullish_pullback_layer4_forward_capture_protocol"]
        if loaded["bullish_pullback_layer4_forward_capture_protocol"].get("report_id")
        == "bullish_pullback_layer4_forward_capture_protocol"
        else None,
        "regular_options_market_window_approval_preflight": loaded["regular_options_market_window_approval_preflight"]
        if loaded["regular_options_market_window_approval_preflight"].get("report_id")
        == "regular_options_market_window_approval_preflight"
        else None,
        "live_entry_allowed": bool(trade_qualification.get("live_entry_allowed")) if trade_qualification else False,
        "auto_track_allowed": bool(trade_qualification.get("auto_track_allowed")) if trade_qualification else False,
        "broker_order_allowed": False,
        "exact_realized_pnl_count": _safe_int(trade_qualification.get("exact_realized_pnl_count")),
        "promotion_ready_count": _safe_int(trade_qualification.get("promotion_ready_count")),
        "paper_shadow_action_count": counts["paper_shadow_action_count"],
        "market_window_action_count": counts["market_window_action_count"],
        "waiting_action_count": counts["waiting_action_count"],
        "blocked_action_count": counts["blocked_action_count"],
        "operator_actions": actions,
        "blocked_reasons": blocked_reasons,
        "prohibited_actions": _prohibited_actions(
            trade_qualification,
            loaded["gateboard"],
            loaded["monthly_profitability"],
            loaded["fill_attempt_evidence_capture_plan"],
            loaded["suggested_trade_review_plan"],
        ),
        "required_evidence_before_promotion": list(REQUIRED_EVIDENCE_BEFORE_PROMOTION),
    }


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _status_answer(report: dict[str, Any]) -> str:
    best = _as_dict(report.get("best_evidence_lane"))
    if report.get("overall_status") == "blocked_missing_readbacks":
        return "No live release. Next best action: refresh missing or stale local readbacks before evidence collection."
    if best:
        return f"No live release. Next best action: collect paper-shadow exact evidence for {best.get('lane_id')}."
    return "No live release. Next best action: wait for a fresh paper-shadow candidate."


def render_markdown(report: dict[str, Any]) -> str:
    actions = [row for row in _as_list(report.get("operator_actions")) if isinstance(row, dict)]
    best = _as_dict(report.get("best_evidence_lane"))
    action_counts = Counter(_norm(row.get("action_type")) for row in actions)
    status_counts = Counter(_norm(row.get("status")) for row in actions)
    source_counts = Counter(_norm(meta.get("status")) for meta in _as_dict(report.get("source_artifacts")).values())
    market_actions = [row for row in actions if row.get("market_window_required")]
    waiting_actions = [row for row in actions if _norm(row.get("status")).startswith("waiting")]
    blocked_actions = [row for row in actions if _norm(row.get("status")).startswith("blocked")]
    lines = [
        "# Regular Options Paper Shadow Evidence Plan",
        "",
        _status_answer(report),
        "",
        "## At a glance",
        "",
        f"- Overall status: `{report.get('overall_status')}`.",
        f"- Live entry allowed: `{str(bool(report.get('live_entry_allowed'))).lower()}`.",
        f"- Auto-track allowed: `{str(bool(report.get('auto_track_allowed'))).lower()}`.",
        f"- Broker order allowed: `{str(bool(report.get('broker_order_allowed'))).lower()}`.",
        f"- Exact realized P&L rows: `{report.get('exact_realized_pnl_count')}`.",
        f"- Promotion-ready rows: `{report.get('promotion_ready_count')}`.",
        f"- Paper-shadow actions: `{report.get('paper_shadow_action_count')}`.",
        f"- Market-window actions: `{report.get('market_window_action_count')}`.",
        f"- Waiting actions: `{report.get('waiting_action_count')}`.",
        f"- Blocked actions: `{report.get('blocked_action_count')}`.",
        f"- Action counts: `{_json_inline(dict(sorted(action_counts.items())))}`.",
        f"- Status counts: `{_json_inline(dict(sorted(status_counts.items())))}`.",
        "",
        "## Best evidence lane",
        "",
    ]
    if best:
        lines.extend(
            [
                f"- Lane: `{best.get('lane_id')}`.",
                f"- Decision: `{best.get('decision')}`.",
                f"- Disposition: `{best.get('disposition')}`.",
                f"- Promotion state: `{best.get('promotion_state')}`.",
                f"- Profit factor: `{best.get('profit_factor')}`.",
                f"- Average net P&L pct: `{best.get('avg_net_pnl_pct')}`.",
                f"- Fresh exact entry count: `{best.get('fresh_exact_entry_count')}`.",
                f"- Exact realized P&L count: `{best.get('exact_realized_pnl_count')}`.",
            ]
        )
    else:
        lines.append("- None. The report will not invent a paper-shadow action without a current paper/probation lane.")
    lines.extend(["", "## Next market-window actions", "", "| Priority | Type | Status | Lane | Ticker | Row | Next step |", "| ---: | --- | --- | --- | --- | --- | --- |"])
    for row in market_actions:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.get('priority')}`",
                    f"`{row.get('action_type')}`",
                    f"`{row.get('status')}`",
                    f"`{_norm(row.get('lane_id'))}`",
                    f"`{_norm(row.get('ticker'))}`",
                    f"`{_norm(row.get('position_id') or row.get('candidate_id') or row.get('suggested_trade_id'))}`",
                    _norm(row.get("next_operator_step")),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Waiting actions", ""])
    if waiting_actions:
        for row in waiting_actions:
            lines.append(f"- `{row.get('action_type')}` `{row.get('lane_id')}` `{row.get('ticker')}`: {row.get('next_operator_step')}")
    else:
        lines.append("- No waiting-only rows beyond the current market-window queue.")
    lines.extend(["", "## Blocked actions", ""])
    if blocked_actions:
        for row in blocked_actions:
            lines.append(f"- `{row.get('action_type')}` `{row.get('lane_id')}` `{row.get('ticker')}`: `{_json_inline(row.get('reason_codes') or [])}`.")
    else:
        lines.append("- No row-level action is currently blocked by open risk or missing readbacks.")
    lines.extend(["", "## Open-risk / exact-exit evidence", ""])
    for row in actions:
        if row.get("action_type") in {"review_open_risk", "collect_exact_exit_evidence", "wait_for_policy_exit_condition"}:
            lines.append(f"- `{row.get('status')}` `{row.get('lane_id')}` `{row.get('ticker')}` position `{row.get('position_id')}`: {row.get('next_operator_step')}")
    lines.extend(["", "## Fill-attempt evidence", ""])
    fill_rows = [row for row in actions if row.get("action_type") == "capture_fill_attempt_evidence"]
    if fill_rows:
        for row in fill_rows[:12]:
            lines.append(f"- `{row.get('status')}` `{row.get('lane_id')}` `{row.get('ticker')}` `{row.get('scan_date')}`: {row.get('next_operator_step')}")
    else:
        lines.append("- No missing fill-attempt rows are exposed by the current plan.")
    lines.extend(["", "## Suggested-trade review actions", ""])
    suggested_rows = [row for row in actions if row.get("action_type") == "refresh_suggested_trade_review"]
    if suggested_rows:
        for row in suggested_rows:
            lines.append(f"- Review only: suggested trade `{row.get('suggested_trade_id')}` `{row.get('ticker')}`. {row.get('next_operator_step')}")
    else:
        lines.append("- No suggested-trade review attention rows are exposed by the current plan.")
    lines.extend(["", "## Quarantined / no-chase lanes", ""])
    quarantine_rows = [row for row in actions if row.get("action_type") == "no_chase_quarantine"]
    if quarantine_rows:
        for row in quarantine_rows:
            lines.append(f"- `{row.get('lane_id')}`: {row.get('next_operator_step')}")
    else:
        lines.append("- No quarantine rows were exposed by the trade-qualification lane table.")
    lines.extend(["", "## Promotion requirements still missing", ""])
    for requirement in _as_list(report.get("required_evidence_before_promotion")):
        lines.append(f"- {requirement}.")
    lines.extend(["", "## Source artifacts and staleness", "", "| Source | Status | Age hours | Generated at | Reasons |", "| --- | --- | ---: | --- | --- |"])
    for name, meta in sorted(_as_dict(report.get("source_artifacts")).items()):
        if isinstance(meta, dict):
            lines.append(f"| `{name}` | `{meta.get('status')}` | `{meta.get('age_hours')}` | `{meta.get('generated_at_utc')}` | `{_json_inline(meta.get('reason_codes') or [])}` |")
    lines.extend(["", f"Source status counts: `{_json_inline(dict(sorted(source_counts.items())))}`.", "", "## Non-goals", "", "This report does not:", ""])
    lines.extend(
        [
            "- create trades",
            "- submit broker orders",
            "- change stops",
            "- change scanner policy",
            "- change sizing",
            "- lower proof bars",
            "- promote lanes",
            "- mutate evidence databases",
            "",
            "It also does not enable live validation or auto-track.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    stamp = _norm(report.get("generated_at_utc")).replace("-", "").replace(":", "").replace("+00:00", "Z")
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build read-only regular options paper-shadow evidence plan.")
    parser.add_argument("--trade-qualification", type=Path, default=DEFAULT_TRADE_QUALIFICATION)
    parser.add_argument("--gateboard", type=Path, default=DEFAULT_GATEBOARD)
    parser.add_argument("--monthly-profitability", type=Path, default=DEFAULT_MONTHLY_PROFITABILITY)
    parser.add_argument("--lane-promotion", type=Path, default=DEFAULT_LANE_PROMOTION)
    parser.add_argument("--candidate-ledger", type=Path, default=DEFAULT_CANDIDATE_LEDGER)
    parser.add_argument("--fresh-evidence", type=Path, default=DEFAULT_FRESH_EVIDENCE)
    parser.add_argument("--fill-attempt-plan", type=Path, default=DEFAULT_FILL_ATTEMPT_PLAN)
    parser.add_argument("--suggested-review-plan", type=Path, default=DEFAULT_SUGGESTED_REVIEW_PLAN)
    parser.add_argument("--open-risk", type=Path, default=DEFAULT_OPEN_RISK)
    parser.add_argument("--suggested-close-risk", type=Path, default=DEFAULT_SUGGESTED_CLOSE_RISK)
    parser.add_argument("--paper-shortlist", type=Path, default=DEFAULT_PAPER_SHORTLIST)
    parser.add_argument("--profit-capture-queue", type=Path, default=DEFAULT_PROFIT_CAPTURE_QUEUE)
    parser.add_argument("--bullish-pullback-layer-shadow-selection", type=Path, default=DEFAULT_BULLISH_PULLBACK_LAYER_SHADOW_SELECTION)
    parser.add_argument(
        "--bullish-pullback-layer-execution-safety-audit",
        type=Path,
        default=DEFAULT_BULLISH_PULLBACK_LAYER_EXECUTION_SAFETY_AUDIT,
    )
    parser.add_argument(
        "--bullish-pullback-layer4-forward-capture-protocol",
        type=Path,
        default=DEFAULT_BULLISH_PULLBACK_LAYER4_FORWARD_CAPTURE_PROTOCOL,
    )
    parser.add_argument(
        "--market-window-approval-preflight",
        type=Path,
        default=DEFAULT_MARKET_WINDOW_APPROVAL_PREFLIGHT,
    )
    parser.add_argument("--max-source-age-hours", type=int, default=MAX_SOURCE_AGE_HOURS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        trade_qualification_path=args.trade_qualification,
        gateboard_path=args.gateboard,
        monthly_profitability_path=args.monthly_profitability,
        lane_promotion_path=args.lane_promotion,
        candidate_ledger_path=args.candidate_ledger,
        fresh_evidence_path=args.fresh_evidence,
        fill_attempt_plan_path=args.fill_attempt_plan,
        suggested_review_plan_path=args.suggested_review_plan,
        open_risk_path=args.open_risk,
        suggested_close_risk_path=args.suggested_close_risk,
        paper_shortlist_path=args.paper_shortlist,
        profit_capture_queue_path=args.profit_capture_queue,
        bullish_pullback_layer_shadow_selection_path=args.bullish_pullback_layer_shadow_selection,
        bullish_pullback_layer_execution_safety_audit_path=args.bullish_pullback_layer_execution_safety_audit,
        bullish_pullback_layer4_forward_capture_protocol_path=args.bullish_pullback_layer4_forward_capture_protocol,
        market_window_approval_preflight_path=args.market_window_approval_preflight,
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
