from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_market_window_evidence_checklist"

DEFAULT_TRADE_QUALIFICATION = ROOT / "data" / "forward-tracking" / "regular_options_trade_qualification_latest.json"
DEFAULT_PAPER_SHADOW_PLAN = ROOT / "data" / "forward-tracking" / "regular_options_paper_shadow_evidence_plan_latest.json"
DEFAULT_GATEBOARD = ROOT / "data" / "forward-tracking" / "project_operator_gateboard_latest.json"
DEFAULT_MONTHLY_PROFITABILITY = ROOT / "data" / "forward-tracking" / "monthly_all_lanes_profitability_audit_latest.json"
DEFAULT_FILL_ATTEMPT_PLAN = ROOT / "data" / "forward-tracking" / "regular_options_fill_attempt_evidence_capture_plan_latest.json"
DEFAULT_SUGGESTED_REVIEW_PLAN = ROOT / "data" / "forward-tracking" / "regular_options_suggested_trade_review_plan_latest.json"
DEFAULT_OPEN_RISK = ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json"
DEFAULT_SUGGESTED_CLOSE_RISK = ROOT / "data" / "forward-tracking" / "suggested_trade_close_risk_latest.json"
DEFAULT_CANDIDATE_LEDGER = ROOT / "data" / "forward-tracking" / "regular_options_candidate_outcome_ledger_latest.json"
DEFAULT_FRESH_EVIDENCE = ROOT / "data" / "forward-tracking" / "regular_options_fresh_evidence_loop_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-market-window-evidence-checklist.md"

MAX_SOURCE_AGE_HOURS = 96

PROHIBITED_ACTIONS = (
    "do_not_create_trades_from_market_window_checklist",
    "do_not_submit_broker_orders_from_market_window_checklist",
    "do_not_change_stops_from_market_window_checklist",
    "do_not_change_scanner_policy_from_market_window_checklist",
    "do_not_change_sizing_from_market_window_checklist",
    "do_not_enable_live_validation_from_market_window_checklist",
    "do_not_enable_auto_track_from_market_window_checklist",
    "do_not_lower_exact_executable_proof_bars_from_market_window_checklist",
    "do_not_mutate_evidence_databases_from_market_window_checklist",
    "do_not_treat_suggested_trade_review_as_recommendation",
)

SAFE_COMMANDS = (
    ("npm run options:gateboard", "Refresh operator gateboard and no-live/no-chase readback."),
    ("npm run options:triage:trade-qualification", "Refresh read-only trade qualification."),
    ("npm run options:plan:bullish-pullback-layer-shadow", "Refresh read-only bullish-pullback layer-shadow harness selection."),
    (
        "npm run options:audit:bullish-pullback-layer-execution-safety",
        "Refresh read-only bullish-pullback layer execution-safety preflight.",
    ),
    (
        "npm run options:audit:bullish-pullback-layer-executable-economics",
        "Refresh read-only bullish-pullback layer executable-economics audit.",
    ),
    (
        "npm run options:plan:bullish-pullback-layer4-forward-capture",
        "Refresh read-only bullish-pullback layer4 forward capture protocol.",
    ),
    ("npm run options:plan:paper-shadow-evidence", "Refresh paper-shadow evidence plan."),
    ("npm run options:plan:fill-attempt-evidence-capture", "Refresh fill-attempt evidence capture plan."),
    ("npm run options:plan:suggested-trade-review", "Refresh suggested-trade review-only plan."),
    ("npm run options:audit:monthly-profitability", "Refresh monthly profitability audit readback."),
    (
        "npm run options:preflight:market-window-approval",
        "Run the final no-write market-window approval preflight before any future approval discussion.",
    ),
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


def _source_block_status(source_artifacts: dict[str, dict[str, Any]]) -> str | None:
    bad = [meta for meta in source_artifacts.values() if meta.get("required") and meta.get("status") != "loaded"]
    if not bad:
        return None
    if any(meta.get("status") == "stale" or "stale_readback" in _as_list(meta.get("reason_codes")) for meta in bad):
        return "blocked_stale_readbacks"
    return "blocked_missing_readbacks"


def _open_risk_blocked(open_risk: dict[str, Any], trade_qualification: dict[str, Any]) -> bool:
    governor = _as_dict(open_risk.get("open_risk_governor"))
    triage_open = _as_dict(trade_qualification.get("open_risk_status"))
    status_values = [_norm(governor.get("status")), _norm(triage_open.get("status"))]
    return any("blocked" in value for value in status_values) or governor.get("live_entry_allowed") is False


def _command_steps() -> list[dict[str, Any]]:
    return [
        {
            "priority": index,
            "command": command,
            "purpose": purpose,
            "read_only": True,
            "is_broker_order": False,
            "is_trade_recommendation": False,
        }
        for index, (command, purpose) in enumerate(SAFE_COMMANDS, start=1)
    ]


def _base_step(
    *,
    step_id: str,
    priority: int,
    step_type: str,
    title: str,
    status: str,
    source_artifact: str,
    lane_id: Any = None,
    ticker: Any = None,
    position_id: Any = None,
    candidate_id: Any = None,
    suggested_trade_id: Any = None,
    reason_codes: list[Any] | None = None,
    market_window_required: bool = False,
    requires_policy_exit_condition: bool = False,
    requires_exact_entry_evidence: bool = False,
    requires_exact_exit_evidence: bool = False,
    requires_fill_attempt_evidence: bool = False,
    requires_operator_review: bool = False,
    command_hint: str = "",
    next_operator_step: str = "",
) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "priority": priority,
        "step_type": step_type,
        "title": title,
        "lane_id": lane_id,
        "ticker": ticker,
        "position_id": position_id,
        "candidate_id": candidate_id,
        "suggested_trade_id": suggested_trade_id,
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
        "command_hint": command_hint,
        "next_operator_step": next_operator_step,
    }


def _refresh_steps() -> list[dict[str, Any]]:
    return [
        _base_step(
            step_id="refresh:gateboard",
            priority=1,
            step_type="refresh_gateboard",
            title="Refresh gateboard",
            status="ready",
            source_artifact="project_operator_gateboard",
            command_hint="npm run options:gateboard",
            next_operator_step="Refresh the gateboard before any market-window evidence work.",
        ),
        _base_step(
            step_id="refresh:trade_qualification",
            priority=2,
            step_type="refresh_trade_qualification",
            title="Refresh trade qualification",
            status="ready",
            source_artifact="regular_options_trade_qualification",
            command_hint="npm run options:triage:trade-qualification",
            next_operator_step="Confirm no-live, no-auto-track, broker-order blocked state remains intact.",
        ),
        _base_step(
            step_id="refresh:paper_shadow_plan",
            priority=6,
            step_type="refresh_paper_shadow_plan",
            title="Refresh paper-shadow evidence plan",
            status="ready",
            source_artifact="regular_options_paper_shadow_evidence_plan",
            command_hint="npm run options:plan:paper-shadow-evidence",
            next_operator_step="Refresh evidence rows before using this checklist during a valid market-data window.",
        ),
        _base_step(
            step_id="refresh:bullish_pullback_layer_shadow",
            priority=3,
            step_type="refresh_bullish_pullback_layer_shadow_selection",
            title="Refresh bullish-pullback layer-shadow selection",
            status="ready",
            source_artifact="bullish_pullback_layer_shadow_selection",
            command_hint="npm run options:plan:bullish-pullback-layer-shadow",
            next_operator_step="Refresh the selected bullish-pullback paper-shadow harness before using the market-window checklist.",
        ),
        _base_step(
            step_id="refresh:bullish_pullback_layer_execution_safety",
            priority=4,
            step_type="refresh_bullish_pullback_layer_execution_safety_audit",
            title="Refresh bullish-pullback execution-safety preflight",
            status="ready",
            source_artifact="bullish_pullback_layer_execution_safety_audit",
            command_hint="npm run options:audit:bullish-pullback-layer-execution-safety",
            next_operator_step="Refresh the leg-level bid/ask and assignment/expiration preflight before using the selected bullish-pullback harness.",
        ),
        _base_step(
            step_id="refresh:bullish_pullback_layer4_forward_capture_protocol",
            priority=6,
            step_type="refresh_bullish_pullback_layer4_forward_capture_protocol",
            title="Refresh bullish-pullback layer4 forward capture protocol",
            status="ready",
            source_artifact="bullish_pullback_layer4_forward_capture_protocol",
            command_hint="npm run options:plan:bullish-pullback-layer4-forward-capture",
            next_operator_step="Refresh the read-only protocol before any future market-window candidate validation or approval discussion.",
        ),
        _base_step(
            step_id="refresh:bullish_pullback_layer_executable_economics",
            priority=5,
            step_type="refresh_bullish_pullback_layer_executable_economics",
            title="Refresh bullish-pullback executable economics",
            status="ready",
            source_artifact="bullish_pullback_layer_executable_economics",
            command_hint="npm run options:audit:bullish-pullback-layer-executable-economics",
            next_operator_step="Refresh the read-only executable-economics audit before any future approval discussion.",
        ),
        _base_step(
            step_id="refresh:market_window_approval_preflight",
            priority=9,
            step_type="refresh_market_window_approval_preflight",
            title="Run market-window approval preflight",
            status="ready",
            source_artifact="regular_options_market_window_approval_preflight",
            command_hint="npm run options:preflight:market-window-approval",
            next_operator_step="Run the no-write approval preflight as the final command before any future operator approval question.",
        ),
    ]


def _market_wait_status(market_window_status: str) -> str:
    if market_window_status == "market_open":
        return "ready_for_market_window"
    return "waiting_for_market_window"


def _policy_exit_fired(action: dict[str, Any]) -> bool:
    reasons = set(_as_list(action.get("reason_codes")))
    return bool(
        action.get("policy_exit_condition_fired")
        or "policy_exit_condition_fired" in reasons
        or "executable_exit_evidence_available" in reasons
    )


def _step_from_action(
    action: dict[str, Any],
    *,
    sequence: int,
    market_window_status: str,
    open_risk_blocked: bool,
) -> dict[str, Any]:
    action_type = _norm(action.get("action_type"))
    lane_id = action.get("lane_id")
    ticker = action.get("ticker")
    position_id = action.get("position_id")
    candidate_id = action.get("candidate_id")
    suggested_trade_id = action.get("suggested_trade_id")
    reasons = _as_list(action.get("reason_codes"))
    source_artifact = _norm(action.get("source_artifact")) or "regular_options_paper_shadow_evidence_plan"
    base_id = _norm(action.get("action_id")) or f"{action_type}:{sequence}"
    next_step = _norm(action.get("next_operator_step"))

    if action_type == "collect_exact_exit_evidence":
        if _policy_exit_fired(action):
            return _base_step(
                step_id=f"exit:{base_id}",
                priority=20 + sequence,
                step_type="collect_exact_exit_evidence",
                title="Collect exact exit evidence",
                status=_market_wait_status(market_window_status),
                source_artifact=source_artifact,
                lane_id=lane_id,
                ticker=ticker,
                position_id=position_id,
                candidate_id=candidate_id,
                reason_codes=[*reasons, "policy_exit_condition_fired"],
                market_window_required=True,
                requires_exact_exit_evidence=True,
                command_hint="npm run options:plan:paper-shadow-evidence",
                next_operator_step=next_step or "Collect exact executable exit evidence only from local policy-defined exit evidence.",
            )
        return _base_step(
            step_id=f"wait_policy_exit:{base_id}",
            priority=20 + sequence,
            step_type="wait_for_policy_exit_condition",
            title="Wait for policy-defined exit condition",
            status="waiting_for_policy_exit",
            source_artifact=source_artifact,
            lane_id=lane_id,
            ticker=ticker,
            position_id=position_id,
            candidate_id=candidate_id,
            reason_codes=[*reasons, "policy_exit_condition_not_fired"],
            market_window_required=True,
            requires_policy_exit_condition=True,
            requires_exact_exit_evidence=True,
            command_hint="npm run options:plan:paper-shadow-evidence",
            next_operator_step=next_step or "Do not force a close; collect exact exit evidence only after a policy-defined exit condition fires.",
        )

    if action_type == "collect_exact_entry_evidence":
        status = "blocked_by_open_risk" if open_risk_blocked else _market_wait_status(market_window_status)
        return _base_step(
            step_id=f"entry:{base_id}",
            priority=30 + sequence,
            step_type="collect_exact_entry_evidence",
            title="Collect exact entry evidence",
            status=status,
            source_artifact=source_artifact,
            lane_id=lane_id,
            ticker=ticker,
            candidate_id=candidate_id,
            reason_codes=reasons,
            market_window_required=True,
            requires_exact_entry_evidence=True,
            command_hint="npm run options:plan:paper-shadow-evidence",
            next_operator_step=next_step or "During a valid market-data window, capture exact entry evidence only if the row is still freshly selected.",
        )

    if action_type == "capture_fill_attempt_evidence":
        status = "blocked_by_open_risk" if open_risk_blocked else _market_wait_status(market_window_status)
        return _base_step(
            step_id=f"fill_attempt:{base_id}",
            priority=40 + sequence,
            step_type="capture_fill_attempt_evidence",
            title="Capture fill-attempt evidence",
            status=status,
            source_artifact=source_artifact,
            lane_id=lane_id,
            ticker=ticker,
            candidate_id=candidate_id,
            reason_codes=reasons,
            market_window_required=True,
            requires_fill_attempt_evidence=True,
            command_hint="npm run options:plan:fill-attempt-evidence-capture",
            next_operator_step=next_step or "Capture durable fill-attempt evidence for a fresh selection; do not turn it into a trade action.",
        )

    if action_type == "bullish_pullback_layer_4_execution_safety_preflight":
        step = _base_step(
            step_id=f"execution_safety_preflight:{base_id}",
            priority=34 + sequence,
            step_type="bullish_pullback_layer_4_execution_safety_preflight",
            title="Resolve bullish-pullback execution-safety preflight",
            status=_norm(action.get("status")) or "blocked_execution_safety_preflight",
            source_artifact=source_artifact,
            lane_id=lane_id,
            ticker=ticker,
            candidate_id=candidate_id,
            reason_codes=reasons,
            market_window_required=False,
            requires_exact_entry_evidence=True,
            requires_exact_exit_evidence=True,
            requires_operator_review=True,
            command_hint="npm run options:audit:bullish-pullback-layer-execution-safety",
            next_operator_step=next_step
            or "Resolve leg-level bid/ask execution-safety blockers before market-window paper-shadow collection.",
        )
        step.update(
            {
                "selected_layer_id": action.get("selected_layer_id"),
                "selected_variant_id": action.get("selected_variant_id"),
                "source_result_path": action.get("source_result_path"),
                "execution_safety_audit_status": action.get("execution_safety_audit_status"),
                "execution_safety_row_counts": action.get("execution_safety_row_counts"),
                "fatal_reason_counts": action.get("fatal_reason_counts"),
                "preflight_requirements": action.get("preflight_requirements"),
                "leg_level_bid_ask_audit_required": bool(action.get("leg_level_bid_ask_audit_required")),
                "assignment_expiration_risk_review_required": bool(action.get("assignment_expiration_risk_review_required")),
                "denominator_failure_row_handling_required": bool(action.get("denominator_failure_row_handling_required")),
            }
        )
        return step

    if action_type == "prepare_bullish_pullback_layer_shadow_harness":
        status = "blocked_by_open_risk" if open_risk_blocked else _market_wait_status(market_window_status)
        step = _base_step(
            step_id=f"layer_shadow_harness:{base_id}",
            priority=35 + sequence,
            step_type="prepare_bullish_pullback_layer_shadow_harness",
            title="Prepare bullish-pullback layer-shadow harness",
            status=status,
            source_artifact=source_artifact,
            lane_id=lane_id,
            ticker=ticker,
            candidate_id=candidate_id,
            reason_codes=reasons,
            market_window_required=True,
            requires_exact_entry_evidence=True,
            requires_exact_exit_evidence=True,
            requires_operator_review=True,
            command_hint="npm run options:plan:bullish-pullback-layer-shadow",
            next_operator_step=next_step
            or "Use the selected bullish-pullback layer only for future natural paper-shadow evidence collection.",
        )
        step.update(
            {
                "selected_layer_id": action.get("selected_layer_id"),
                "selected_variant_id": action.get("selected_variant_id"),
                "source_result_path": action.get("source_result_path"),
                "allowed_symbols": _as_list(action.get("allowed_symbols")),
                "harness_requirements": action.get("harness_requirements"),
                "leg_level_bid_ask_audit_required": bool(action.get("leg_level_bid_ask_audit_required")),
                "assignment_expiration_risk_review_required": bool(action.get("assignment_expiration_risk_review_required")),
                "denominator_failure_row_handling_required": bool(action.get("denominator_failure_row_handling_required")),
            }
        )
        return step

    if action_type == "bullish_pullback_layer4_capture_protocol_ready_waiting_for_market_window_and_operator_approval":
        status = "blocked_by_open_risk" if open_risk_blocked else "waiting_for_market_window_and_operator_approval"
        step = _base_step(
            step_id=f"layer4_forward_capture_protocol:{base_id}",
            priority=36 + sequence,
            step_type="bullish_pullback_layer4_capture_protocol_ready_waiting_for_market_window_and_operator_approval",
            title="Use bullish-pullback layer4 forward capture protocol",
            status=status,
            source_artifact=source_artifact,
            lane_id=lane_id,
            ticker=ticker,
            candidate_id=candidate_id,
            reason_codes=reasons,
            market_window_required=True,
            requires_exact_entry_evidence=True,
            requires_exact_exit_evidence=True,
            requires_operator_review=True,
            command_hint="npm run options:plan:bullish-pullback-layer4-forward-capture",
            next_operator_step=next_step
            or "Validate future natural paper-shadow denominator rows only after a valid market-data window and separate operator approval.",
        )
        step.update(
            {
                "selected_layer_id": action.get("selected_layer_id"),
                "selected_variant_id": action.get("selected_variant_id"),
                "source_result_path": action.get("source_result_path"),
                "allowed_symbols": _as_list(action.get("allowed_symbols")),
                "capture_protocol_status": action.get("capture_protocol_status"),
                "historical_executable_economics": action.get("historical_executable_economics"),
                "protocol_requirements": action.get("protocol_requirements"),
                "candidate_validator_read_only": bool(action.get("candidate_validator_read_only")),
                "cohort_append_performed": bool(action.get("cohort_append_performed")),
            }
        )
        return step

    if action_type == "refresh_suggested_trade_review":
        return _base_step(
            step_id=f"suggested_review:{base_id}",
            priority=50 + sequence,
            step_type="refresh_suggested_trade_review",
            title="Refresh suggested-trade review",
            status="review_only",
            source_artifact=source_artifact,
            lane_id=lane_id,
            ticker=ticker,
            suggested_trade_id=suggested_trade_id,
            reason_codes=[*reasons, "review_only_not_trade_recommendation"],
            market_window_required=True,
            requires_operator_review=True,
            command_hint="npm run options:plan:suggested-trade-review",
            next_operator_step=next_step or "Refresh the suggested-trade review only; do not treat the row as a recommendation.",
        )

    if action_type == "repair_replay_evidence":
        return _base_step(
            step_id=f"repair:{base_id}",
            priority=60 + sequence,
            step_type="repair_replay_evidence",
            title="Repair replay/source evidence",
            status="repair_only",
            source_artifact=source_artifact,
            lane_id=lane_id,
            ticker=ticker,
            candidate_id=candidate_id,
            reason_codes=reasons,
            command_hint="npm run options:plan:paper-shadow-evidence",
            next_operator_step=next_step or "Repair replay/source evidence only for active unexhausted targets.",
        )

    if action_type == "no_chase_quarantine":
        return _base_step(
            step_id=f"no_chase:{base_id}",
            priority=70 + sequence,
            step_type="no_chase_quarantine",
            title="Keep quarantined lane parked",
            status="blocked_by_no_chase",
            source_artifact=source_artifact,
            lane_id=lane_id,
            ticker=ticker,
            candidate_id=candidate_id,
            reason_codes=[*reasons, "no_chase_quarantine"],
            next_operator_step=next_step or "Keep this lane parked; do not create fresh market-window actions from quarantined evidence.",
        )

    if action_type == "wait_for_fresh_candidate":
        return _base_step(
            step_id=f"fresh_candidate:{base_id}",
            priority=80 + sequence,
            step_type="wait_for_fresh_candidate",
            title="Wait for fresh candidate",
            status="waiting_for_fresh_candidate",
            source_artifact=source_artifact,
            lane_id=lane_id,
            ticker=ticker,
            candidate_id=candidate_id,
            reason_codes=reasons,
            next_operator_step=next_step or "Wait for a fresh local candidate instead of inventing an evidence row.",
        )

    return _base_step(
        step_id=f"fresh_candidate:{base_id}",
        priority=90 + sequence,
        step_type="wait_for_fresh_candidate",
        title="Wait for fresh candidate",
        status="waiting_for_fresh_candidate",
        source_artifact=source_artifact,
        lane_id=lane_id,
        ticker=ticker,
        candidate_id=candidate_id,
        reason_codes=[*reasons, "unsupported_source_action_type"],
        next_operator_step="No market-window action is created from this source action type.",
    )


def _evidence_steps(
    paper_shadow_plan: dict[str, Any],
    *,
    market_window_status: str,
    open_risk_blocked: bool,
) -> list[dict[str, Any]]:
    actions = [row for row in _as_list(paper_shadow_plan.get("operator_actions")) if isinstance(row, dict)]
    if not actions:
        return [
            _base_step(
                step_id="wait_for_fresh_candidate:no_operator_actions",
                priority=80,
                step_type="wait_for_fresh_candidate",
                title="Wait for fresh candidate",
                status="waiting_for_fresh_candidate",
                source_artifact="regular_options_paper_shadow_evidence_plan",
                reason_codes=["no_operator_actions_from_paper_shadow_plan"],
                next_operator_step="No actionable evidence rows exist in the current local paper-shadow plan.",
            )
        ]
    return [
        _step_from_action(
            action,
            sequence=index,
            market_window_status=market_window_status,
            open_risk_blocked=open_risk_blocked,
        )
        for index, action in enumerate(actions, start=1)
    ]


def _overall_status(source_artifacts: dict[str, dict[str, Any]], steps: list[dict[str, Any]]) -> str:
    source_status = _source_block_status(source_artifacts)
    if source_status:
        return source_status
    evidence_steps = [step for step in steps if not step["step_type"].startswith("refresh_")]
    if not evidence_steps:
        return "blocked_no_evidence_actions"
    statuses = {step.get("status") for step in evidence_steps}
    if statuses == {"waiting_for_fresh_candidate"}:
        return "blocked_no_evidence_actions"
    if "waiting_for_market_window" in statuses or "waiting_for_market_window_and_operator_approval" in statuses:
        return "waiting_for_market_window"
    if statuses <= {"waiting_for_policy_exit", "repair_only", "blocked_by_no_chase"}:
        return "waiting_for_policy_exit"
    if statuses <= {"review_only", "repair_only", "blocked_by_no_chase"}:
        return "review_only"
    return "market_window_checklist_ready"


def _prohibited_actions(*payloads: dict[str, Any]) -> list[str]:
    values: list[Any] = list(PROHIBITED_ACTIONS)
    for payload in payloads:
        values.extend(_as_list(payload.get("prohibited_actions")))
        manifest = _as_dict(payload.get("no_chase_manifest"))
        values.extend(_as_list(manifest.get("prohibited_actions")))
    return _unique(values)


def build_report(
    *,
    trade_qualification_path: Path = DEFAULT_TRADE_QUALIFICATION,
    paper_shadow_plan_path: Path = DEFAULT_PAPER_SHADOW_PLAN,
    gateboard_path: Path = DEFAULT_GATEBOARD,
    monthly_profitability_path: Path = DEFAULT_MONTHLY_PROFITABILITY,
    fill_attempt_plan_path: Path = DEFAULT_FILL_ATTEMPT_PLAN,
    suggested_review_plan_path: Path = DEFAULT_SUGGESTED_REVIEW_PLAN,
    open_risk_path: Path = DEFAULT_OPEN_RISK,
    suggested_close_risk_path: Path = DEFAULT_SUGGESTED_CLOSE_RISK,
    candidate_ledger_path: Path = DEFAULT_CANDIDATE_LEDGER,
    fresh_evidence_path: Path = DEFAULT_FRESH_EVIDENCE,
    generated_at_utc: str | None = None,
    max_source_age_hours: int = MAX_SOURCE_AGE_HOURS,
    market_window_status: str = "unknown",
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    specs = {
        "trade_qualification": (trade_qualification_path, True),
        "paper_shadow_evidence_plan": (paper_shadow_plan_path, True),
        "gateboard": (gateboard_path, True),
        "monthly_profitability": (monthly_profitability_path, True),
        "fill_attempt_evidence_capture_plan": (fill_attempt_plan_path, True),
        "suggested_trade_review_plan": (suggested_review_plan_path, True),
        "open_position_risk": (open_risk_path, True),
        "suggested_trade_close_risk": (suggested_close_risk_path, True),
        "candidate_outcome_ledger": (candidate_ledger_path, True),
        "fresh_evidence_loop": (fresh_evidence_path, True),
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
    paper_shadow_plan = loaded["paper_shadow_evidence_plan"]
    open_risk_blocked = _open_risk_blocked(loaded["open_position_risk"], trade_qualification)
    steps = _refresh_steps() + _evidence_steps(
        paper_shadow_plan,
        market_window_status=market_window_status,
        open_risk_blocked=open_risk_blocked,
    )
    steps = sorted(steps, key=lambda item: (int(item.get("priority") or 99), _norm(item.get("step_id"))))
    status_counts = Counter(step.get("status") for step in steps)
    type_counts = Counter(step.get("step_type") for step in steps)
    blocked_actions = [step for step in steps if _norm(step.get("status")).startswith("blocked")]
    waiting_actions = [
        step
        for step in steps
        if step.get("status") in {"waiting_for_market_window", "waiting_for_market_window_and_operator_approval", "waiting_for_policy_exit", "waiting_for_fresh_candidate"}
    ]
    review_only_actions = [step for step in steps if step.get("status") == "review_only"]

    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "scope": "regular_options_market_window_evidence_capture_checklist",
        "read_only": True,
        "source_artifacts": source_artifacts,
        "overall_status": _overall_status(source_artifacts, steps),
        "market_window_status": market_window_status,
        "live_entry_allowed": bool(trade_qualification.get("live_entry_allowed")) if trade_qualification else False,
        "auto_track_allowed": bool(trade_qualification.get("auto_track_allowed")) if trade_qualification else False,
        "broker_order_allowed": False,
        "is_trade_recommendation": False,
        "best_evidence_lane": paper_shadow_plan.get("best_evidence_lane") or trade_qualification.get("best_current_lane_if_any"),
        "exact_realized_pnl_count": int(trade_qualification.get("exact_realized_pnl_count") or 0),
        "promotion_ready_count": int(trade_qualification.get("promotion_ready_count") or 0),
        "open_risk_blocked": open_risk_blocked,
        "checklist_steps": steps,
        "blocked_actions": blocked_actions,
        "waiting_actions": waiting_actions,
        "review_only_actions": review_only_actions,
        "commands_to_run": _command_steps(),
        "prohibited_actions": _prohibited_actions(
            trade_qualification,
            paper_shadow_plan,
            loaded["gateboard"],
            loaded["monthly_profitability"],
            loaded["fill_attempt_evidence_capture_plan"],
            loaded["suggested_trade_review_plan"],
        ),
        "required_evidence_before_promotion": _unique(
            [
                *_as_list(trade_qualification.get("required_evidence_before_promotion")),
                *_as_list(paper_shadow_plan.get("required_evidence_before_promotion")),
            ]
        ),
        "counts": {
            "checklist_step_count": len(steps),
            "blocked_action_count": len(blocked_actions),
            "waiting_action_count": len(waiting_actions),
            "review_only_action_count": len(review_only_actions),
            "market_window_required_count": sum(1 for step in steps if step.get("market_window_required")),
            "step_type_counts": dict(sorted(type_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "source_status_counts": dict(sorted(Counter(meta.get("status") for meta in source_artifacts.values()).items())),
        },
    }


def _json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _row_id(step: dict[str, Any]) -> str:
    for key in ("position_id", "candidate_id", "suggested_trade_id"):
        value = step.get(key)
        if value not in (None, ""):
            return _norm(value)
    return ""


def _table_steps(steps: list[dict[str, Any]]) -> list[str]:
    if not steps:
        return ["No rows."]
    rows = ["| Priority | Type | Status | Lane | Ticker | Row | Next step |", "| ---: | --- | --- | --- | --- | --- | --- |"]
    for step in steps:
        rows.append(
            "| `{priority}` | `{step_type}` | `{status}` | `{lane}` | `{ticker}` | `{row}` | {next_step} |".format(
                priority=step.get("priority"),
                step_type=step.get("step_type"),
                status=step.get("status"),
                lane=_norm(step.get("lane_id")),
                ticker=_norm(step.get("ticker")),
                row=_row_id(step),
                next_step=_norm(step.get("next_operator_step")).replace("|", "/"),
            )
        )
    return rows


def render_markdown(report: dict[str, Any]) -> str:
    best = _as_dict(report.get("best_evidence_lane"))
    best_lane = _norm(best.get("lane_id")) or "none"
    first_line = "No live release. Market-window task: collect/review evidence only."
    if best_lane != "none":
        first_line = f"No live release. Market-window task: collect/review evidence only for `{best_lane}`."

    steps = _as_list(report.get("checklist_steps"))
    ready = [step for step in steps if step.get("status") in {"ready", "ready_for_market_window"}]
    waiting_market = [step for step in steps if step.get("status") in {"waiting_for_market_window", "waiting_for_market_window_and_operator_approval"}]
    waiting_exit = [step for step in steps if step.get("status") == "waiting_for_policy_exit"]
    review_only = [step for step in steps if step.get("status") == "review_only"]
    fill_attempt = [step for step in steps if step.get("step_type") == "capture_fill_attempt_evidence"]
    repair_only = [step for step in steps if step.get("status") == "repair_only"]
    no_chase = [step for step in steps if step.get("step_type") == "no_chase_quarantine"]

    lines = [
        "# Regular Options Market Window Evidence Checklist",
        "",
        first_line,
        "",
        "## At a glance",
        "",
        f"- Overall status: `{report.get('overall_status')}`.",
        f"- Market-window status: `{report.get('market_window_status')}`.",
        f"- Live entry allowed: `{str(report.get('live_entry_allowed')).lower()}`.",
        f"- Auto-track allowed: `{str(report.get('auto_track_allowed')).lower()}`.",
        f"- Broker order allowed: `{str(report.get('broker_order_allowed')).lower()}`.",
        f"- Trade recommendation: `{str(report.get('is_trade_recommendation')).lower()}`.",
        f"- Exact realized P&L rows: `{report.get('exact_realized_pnl_count')}`.",
        f"- Promotion-ready rows: `{report.get('promotion_ready_count')}`.",
        f"- Checklist steps: `{_as_dict(report.get('counts')).get('checklist_step_count')}`.",
        f"- Waiting actions: `{_as_dict(report.get('counts')).get('waiting_action_count')}`.",
        f"- Blocked actions: `{_as_dict(report.get('counts')).get('blocked_action_count')}`.",
        f"- Review-only actions: `{_as_dict(report.get('counts')).get('review_only_action_count')}`.",
        f"- Step counts: `{_json_text(_as_dict(report.get('counts')).get('step_type_counts'))}`.",
        "",
        "## Safe command order",
        "",
    ]
    for item in _as_list(report.get("commands_to_run")):
        lines.append(f"- `{item.get('priority')}` `{item.get('command')}`: {item.get('purpose')}")

    lines.extend(
        [
            "",
            "## Ready now",
            "",
            *_table_steps(ready),
            "",
            "## Waiting for market window",
            "",
            *_table_steps(waiting_market),
            "",
            "## Waiting for policy exit",
            "",
            *_table_steps(waiting_exit),
            "",
            "## Review-only suggested trades",
            "",
            *_table_steps(review_only),
            "",
            "## Fill-attempt evidence",
            "",
            *_table_steps(fill_attempt),
            "",
            "## Repair-only evidence",
            "",
            *_table_steps(repair_only),
            "",
            "## Quarantined/no-chase lanes",
            "",
            *_table_steps(no_chase),
            "",
            "## Prohibited actions",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in _as_list(report.get("prohibited_actions")))
    lines.extend(["", "## Promotion requirements still missing", ""])
    lines.extend(f"- {item}." for item in _as_list(report.get("required_evidence_before_promotion")))
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
    lines.extend(
        [
            "",
            f"Source status counts: `{_json_text(_as_dict(report.get('counts')).get('source_status_counts'))}`.",
            "",
            "## Non-goals",
            "",
            "This checklist does not:",
            "",
            "- create trades",
            "- submit broker orders",
            "- change stops",
            "- change scanner policy",
            "- change sizing",
            "- lower proof bars",
            "- promote lanes",
            "- mutate evidence databases",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{REPORT_ID}_latest.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    docs_report.write_text(render_markdown(report), encoding="utf8")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the regular options market-window evidence checklist.")
    parser.add_argument("--trade-qualification", type=Path, default=DEFAULT_TRADE_QUALIFICATION)
    parser.add_argument("--paper-shadow-plan", type=Path, default=DEFAULT_PAPER_SHADOW_PLAN)
    parser.add_argument("--gateboard", type=Path, default=DEFAULT_GATEBOARD)
    parser.add_argument("--monthly-profitability", type=Path, default=DEFAULT_MONTHLY_PROFITABILITY)
    parser.add_argument("--fill-attempt-plan", type=Path, default=DEFAULT_FILL_ATTEMPT_PLAN)
    parser.add_argument("--suggested-review-plan", type=Path, default=DEFAULT_SUGGESTED_REVIEW_PLAN)
    parser.add_argument("--open-risk", type=Path, default=DEFAULT_OPEN_RISK)
    parser.add_argument("--suggested-close-risk", type=Path, default=DEFAULT_SUGGESTED_CLOSE_RISK)
    parser.add_argument("--candidate-ledger", type=Path, default=DEFAULT_CANDIDATE_LEDGER)
    parser.add_argument("--fresh-evidence", type=Path, default=DEFAULT_FRESH_EVIDENCE)
    parser.add_argument("--market-window-status", choices=("unknown", "market_open", "market_closed", "market_window_required", "not_required_for_readonly"), default="unknown")
    parser.add_argument("--max-source-age-hours", type=int, default=MAX_SOURCE_AGE_HOURS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", dest="json_output", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        trade_qualification_path=args.trade_qualification,
        paper_shadow_plan_path=args.paper_shadow_plan,
        gateboard_path=args.gateboard,
        monthly_profitability_path=args.monthly_profitability,
        fill_attempt_plan_path=args.fill_attempt_plan,
        suggested_review_plan_path=args.suggested_review_plan,
        open_risk_path=args.open_risk,
        suggested_close_risk_path=args.suggested_close_risk,
        candidate_ledger_path=args.candidate_ledger,
        fresh_evidence_path=args.fresh_evidence,
        max_source_age_hours=args.max_source_age_hours,
        market_window_status=args.market_window_status,
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
