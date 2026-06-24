from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_bullish_pullback_layer4_forward_capture_protocol as layer4_protocol
from scripts import validate_bullish_pullback_layer4_forward_candidate_rows as layer4_validator


REPORT_ID = "regular_options_market_window_approval_preflight"
APPROVAL_TOKEN = "APPROVE_BULLISH_PULLBACK_LAYER4_FORWARD_CAPTURE_REVIEW"
MAX_SOURCE_AGE_HOURS = 96

DEFAULT_GATEBOARD = ROOT / "data" / "forward-tracking" / "project_operator_gateboard_latest.json"
DEFAULT_TRADE_QUALIFICATION = ROOT / "data" / "forward-tracking" / "regular_options_trade_qualification_latest.json"
DEFAULT_GOAL_LOOP = ROOT / "data" / "forward-tracking" / "options_goal_loop_latest.json"
DEFAULT_MARKET_WINDOW_CHECKLIST = ROOT / "data" / "forward-tracking" / "regular_options_market_window_evidence_checklist_latest.json"
DEFAULT_PAPER_SHADOW_PLAN = ROOT / "data" / "forward-tracking" / "regular_options_paper_shadow_evidence_plan_latest.json"
DEFAULT_LAYER4_PROTOCOL = ROOT / "data" / "forward-tracking" / "bullish_pullback_layer4_forward_capture_protocol_latest.json"
DEFAULT_EXECUTION_SAFETY = ROOT / "data" / "forward-tracking" / "bullish_pullback_layer_execution_safety_audit_latest.json"
DEFAULT_EXECUTABLE_ECONOMICS = ROOT / "data" / "forward-tracking" / "bullish_pullback_layer_executable_economics_latest.json"
DEFAULT_APPROVAL_PACKET = ROOT / "docs" / "bullish-pullback-layer4-forward-paper-shadow-approval-packet.md"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-market-window-approval-preflight.md"

PROHIBITED_ACTIONS = (
    "do_not_append_forward_cohort_rows_from_approval_preflight",
    "do_not_create_trades_from_approval_preflight",
    "do_not_submit_broker_orders_from_approval_preflight",
    "do_not_enable_live_validation_from_approval_preflight",
    "do_not_enable_auto_track_from_approval_preflight",
    "do_not_import_quotes_from_approval_preflight",
    "do_not_mutate_evidence_databases_from_approval_preflight",
    "do_not_change_scanner_policy_from_approval_preflight",
    "do_not_change_strategy_logic_from_approval_preflight",
    "do_not_change_stops_from_approval_preflight",
    "do_not_change_sizing_from_approval_preflight",
    "do_not_lower_exact_executable_proof_bars_from_approval_preflight",
    "do_not_consume_protected_holdout_from_approval_preflight",
    "do_not_promote_from_historical_layer4_economics",
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
        return str(path)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return str(value or "").strip()


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


def _load_text_artifact(path: Path, *, required: bool) -> tuple[str, dict[str, Any]]:
    source = {
        "path": _rel(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "reason_codes": ["missing_readback"],
        "error": None,
    }
    if not path.exists():
        return "", source
    try:
        text = path.read_text(encoding="utf8")
    except OSError as exc:
        source["status"] = "unreadable"
        source["error"] = type(exc).__name__
        source["reason_codes"] = ["unreadable_readback"]
        return "", source
    source["status"] = "loaded"
    source["reason_codes"] = []
    return text, source


def _require(blockers: list[dict[str, Any]], code: str, condition: bool, *, observed: Any = None, expected: Any = None) -> None:
    if condition:
        return
    row: dict[str, Any] = {"code": code}
    if observed is not None:
        row["observed"] = observed
    if expected is not None:
        row["expected"] = expected
    blockers.append(row)


def _close_enough(value: Any, expected: float) -> bool:
    try:
        return math.isclose(float(value), expected, rel_tol=0, abs_tol=0.0001)
    except (TypeError, ValueError):
        return False


def _bool_flag(payload: dict[str, Any], key: str) -> bool:
    return payload.get(key) is True


def _count_by_type(rows: list[Any], type_key: str, expected_type: str) -> int:
    return sum(1 for row in rows if isinstance(row, dict) and row.get(type_key) == expected_type)


def _candidate_validation(candidate_jsonl_path: Path | None, generated_at_utc: str) -> dict[str, Any]:
    if candidate_jsonl_path is None:
        return {
            "candidate_jsonl_supplied": False,
            "candidate_rows_valid_for_future_approval_no_append": False,
            "candidate_validator_read_only": True,
            "cohort_append_performed": False,
            "append_allowed": False,
            "reject_counts": {},
            "total_candidate_rows": 0,
            "valid_candidate_rows": 0,
            "rejected_candidate_rows": 0,
        }
    report = layer4_validator.validate_rows(candidate_jsonl_path, generated_at_utc=generated_at_utc)
    return {
        "candidate_jsonl_supplied": True,
        "candidate_rows_path": report.get("candidate_rows_path"),
        "candidate_source": report.get("candidate_source"),
        "candidate_rows_valid_for_future_approval_no_append": bool(
            report.get("candidate_rows_would_be_valid_for_future_approval")
        ),
        "candidate_validator_read_only": report.get("candidate_validator_read_only") is True,
        "cohort_append_performed": report.get("cohort_append_performed") is True,
        "append_allowed": report.get("append_allowed") is True,
        "reject_counts": report.get("reject_counts") or {},
        "total_candidate_rows": report.get("total_candidate_rows", 0),
        "valid_candidate_rows": report.get("valid_candidate_rows", 0),
        "rejected_candidate_rows": report.get("rejected_candidate_rows", 0),
        "validator_overall_status": report.get("overall_status"),
    }


def _check_invariants(
    *,
    gateboard: dict[str, Any],
    trade_qualification: dict[str, Any],
    goal_loop: dict[str, Any],
    market_window_checklist: dict[str, Any],
    paper_shadow_plan: dict[str, Any],
    layer4_capture_protocol: dict[str, Any],
    execution_safety: dict[str, Any],
    executable_economics: dict[str, Any],
    approval_packet_text: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    selected = _as_dict(layer4_capture_protocol.get("selected_harness"))
    historical = _as_dict(layer4_capture_protocol.get("historical_executable_economics"))
    historical_counts = _as_dict(historical.get("row_counts"))
    protocol_safety = _as_dict(layer4_capture_protocol.get("execution_safety_preflight"))
    protocol_safety_counts = _as_dict(protocol_safety.get("row_counts"))
    goal_accounting = _as_dict(goal_loop.get("forward_evidence_accounting"))
    goal_readiness = _as_dict(goal_loop.get("acceptance_readiness"))

    _require(blockers, "gateboard_no_chase_not_loaded", _as_dict(gateboard.get("no_chase_manifest")).get("status") == "no_chase_active", observed=_as_dict(gateboard.get("no_chase_manifest")).get("status"), expected="no_chase_active")
    for payload_name, payload in (
        ("gateboard", gateboard),
        ("trade_qualification", trade_qualification),
        ("goal_loop", goal_loop),
        ("paper_shadow_plan", paper_shadow_plan),
        ("layer4_capture_protocol", layer4_capture_protocol),
    ):
        for flag in ("live_entry_allowed", "auto_track_allowed", "broker_order_allowed", "promotion_ready"):
            _require(blockers, f"{payload_name}_{flag}_must_be_false_or_absent", not _bool_flag(payload, flag), observed=payload.get(flag), expected=False)

    _require(blockers, "goal_loop_state_drift", goal_accounting.get("state") == "log_missing_blocker", observed=goal_accounting.get("state"), expected="log_missing_blocker")
    _require(blockers, "goal_loop_cohort_log_must_remain_missing", goal_accounting.get("cohort_log_exists") is False, observed=goal_accounting.get("cohort_log_exists"), expected=False)
    _require(blockers, "goal_loop_strict_rows_not_zero", goal_accounting.get("post_freeze_strict_exact_completed_rows") == 0, observed=goal_accounting.get("post_freeze_strict_exact_completed_rows"), expected=0)
    _require(blockers, "goal_loop_minimum_required_drift", goal_accounting.get("minimum_required") == 30, observed=goal_accounting.get("minimum_required"), expected=30)
    _require(blockers, "goal_loop_strict_pf_lb_must_be_null", goal_accounting.get("strict_usd_pf_lower_bound_5pct") is None, observed=goal_accounting.get("strict_usd_pf_lower_bound_5pct"), expected=None)
    _require(blockers, "acceptance_strict_rows_not_zero", goal_readiness.get("post_freeze_strict_exact_completed_rows") in (0, None), observed=goal_readiness.get("post_freeze_strict_exact_completed_rows"), expected=0)
    _require(blockers, "acceptance_pf_lb_must_be_null", goal_readiness.get("bootstrap_pf_lower_bound_5pct_usd") is None, observed=goal_readiness.get("bootstrap_pf_lower_bound_5pct_usd"), expected=None)

    _require(blockers, "layer4_protocol_status_drift", layer4_capture_protocol.get("capture_protocol_status") == "protocol_ready_waiting_for_market_window_and_operator_approval", observed=layer4_capture_protocol.get("capture_protocol_status"), expected="protocol_ready_waiting_for_market_window_and_operator_approval")
    _require(blockers, "layer4_protocol_must_be_read_only", layer4_capture_protocol.get("read_only") is True, observed=layer4_capture_protocol.get("read_only"), expected=True)
    _require(blockers, "layer4_protocol_historical_rows_must_not_be_forward_proof", layer4_capture_protocol.get("historical_rows_are_forward_proof") is False, observed=layer4_capture_protocol.get("historical_rows_are_forward_proof"), expected=False)
    _require(blockers, "layer4_protocol_cohort_append_must_be_false", layer4_capture_protocol.get("cohort_append_performed") is False, observed=layer4_capture_protocol.get("cohort_append_performed"), expected=False)
    _require(blockers, "layer4_protocol_validator_read_only_drift", layer4_capture_protocol.get("candidate_validator_read_only") is True, observed=layer4_capture_protocol.get("candidate_validator_read_only"), expected=True)
    _require(blockers, "selected_lane_drift", selected.get("lane_id") == layer4_protocol.SELECTED_LANE_ID, observed=selected.get("lane_id"), expected=layer4_protocol.SELECTED_LANE_ID)
    _require(blockers, "selected_layer_drift", selected.get("layer_id") == layer4_protocol.SELECTED_LAYER_ID, observed=selected.get("layer_id"), expected=layer4_protocol.SELECTED_LAYER_ID)
    _require(blockers, "selected_variant_drift", selected.get("variant_id") == layer4_protocol.SELECTED_VARIANT_ID, observed=selected.get("variant_id"), expected=layer4_protocol.SELECTED_VARIANT_ID)
    _require(blockers, "selected_allowed_symbols_drift", selected.get("allowed_symbols") == list(layer4_protocol.ALLOWED_SYMBOLS), observed=selected.get("allowed_symbols"), expected=list(layer4_protocol.ALLOWED_SYMBOLS))

    _require(blockers, "historical_economics_status_drift", historical.get("status") == "executable_economics_recomputed_profitable_but_preflight_blocked", observed=historical.get("status"), expected="executable_economics_recomputed_profitable_but_preflight_blocked")
    _require(blockers, "historical_economics_decision_drift", historical.get("harness_decision") == "profitable_but_preflight_blocked", observed=historical.get("harness_decision"), expected="profitable_but_preflight_blocked")
    _require(blockers, "historical_selected_rows_drift", historical_counts.get("selected_rows") == 129, observed=historical_counts.get("selected_rows"), expected=129)
    _require(blockers, "historical_tradable_rows_drift", historical_counts.get("tradable_executable_rows") == 120, observed=historical_counts.get("tradable_executable_rows"), expected=120)
    _require(blockers, "historical_net_usd_drift", _close_enough(historical.get("historical_side_aware_net_usd_total"), 45610.0), observed=historical.get("historical_side_aware_net_usd_total"), expected=45610.0)
    _require(blockers, "historical_pf_drift", _close_enough(historical.get("historical_side_aware_pf"), 3.7414), observed=historical.get("historical_side_aware_pf"), expected=3.7414)
    _require(blockers, "historical_pf_lb_drift", _close_enough(historical.get("historical_side_aware_pf_lb_5pct"), 2.27), observed=historical.get("historical_side_aware_pf_lb_5pct"), expected=2.27)
    _require(blockers, "historical_missing_required_quote_rows_drift", historical_counts.get("missing_required_quote_rows") == 3, observed=historical_counts.get("missing_required_quote_rows"), expected=3)
    _require(blockers, "historical_zero_untradable_rows_drift", historical_counts.get("zero_or_untradable_rows") == 6, observed=historical_counts.get("zero_or_untradable_rows"), expected=6)
    _require(blockers, "historical_source_mark_mismatch_rows_drift", historical_counts.get("source_mark_mismatch_rows") == 129, observed=historical_counts.get("source_mark_mismatch_rows"), expected=129)

    _require(blockers, "execution_safety_status_drift", protocol_safety.get("status") == "blocked_execution_safety_preflight", observed=protocol_safety.get("status"), expected="blocked_execution_safety_preflight")
    _require(blockers, "execution_safety_total_rows_drift", protocol_safety_counts.get("total_selected_rows") == 129, observed=protocol_safety_counts.get("total_selected_rows"), expected=129)
    _require(blockers, "execution_safety_missing_quote_rows_drift", protocol_safety_counts.get("crossed_or_missing_quote_rows") == 3, observed=protocol_safety_counts.get("crossed_or_missing_quote_rows"), expected=3)
    _require(blockers, "execution_safety_zero_untradable_rows_drift", protocol_safety_counts.get("zero_bid_or_untradable_rows") == 6, observed=protocol_safety_counts.get("zero_bid_or_untradable_rows"), expected=6)
    _require(blockers, "execution_safety_side_aware_mismatch_rows_drift", protocol_safety_counts.get("rows_with_side_aware_price_mismatch") == 129, observed=protocol_safety_counts.get("rows_with_side_aware_price_mismatch"), expected=129)

    econ_counts = _as_dict(executable_economics.get("row_counts"))
    _require(blockers, "economics_artifact_status_drift", executable_economics.get("overall_status") == "executable_economics_recomputed_profitable_but_preflight_blocked", observed=executable_economics.get("overall_status"), expected="executable_economics_recomputed_profitable_but_preflight_blocked")
    _require(blockers, "economics_artifact_tradable_rows_drift", econ_counts.get("tradable_executable_rows") == 120, observed=econ_counts.get("tradable_executable_rows"), expected=120)
    safety_counts = _as_dict(execution_safety.get("row_counts"))
    _require(blockers, "execution_safety_artifact_total_rows_drift", safety_counts.get("total_selected_rows") == 129, observed=safety_counts.get("total_selected_rows"), expected=129)

    action_type = "bullish_pullback_layer4_capture_protocol_ready_waiting_for_market_window_and_operator_approval"
    actions = _as_list(paper_shadow_plan.get("operator_actions"))
    steps = _as_list(market_window_checklist.get("checklist_steps"))
    _require(blockers, "paper_shadow_plan_layer4_action_count_drift", _count_by_type(actions, "action_type", action_type) == 1, observed=_count_by_type(actions, "action_type", action_type), expected=1)
    _require(blockers, "market_window_checklist_layer4_step_count_drift", _count_by_type(steps, "step_type", action_type) == 1, observed=_count_by_type(steps, "step_type", action_type), expected=1)

    packet_lower = approval_packet_text.lower()
    for token in (
        "does not approve appending rows",
        "broker orders",
        "live validation",
        "auto-track",
        "quote import",
        "protected-holdout",
        "promotion",
    ):
        _require(blockers, f"approval_packet_missing_{token.replace(' ', '_')}", token in packet_lower, observed="missing" if token not in packet_lower else "present", expected="present")

    readback = {
        "goal_loop_state": goal_accounting.get("state"),
        "volatility_post_freeze_strict_exact_completed_rows": goal_accounting.get("post_freeze_strict_exact_completed_rows"),
        "volatility_minimum_required_rows": goal_accounting.get("minimum_required"),
        "volatility_strict_usd_pf_lower_bound_5pct": goal_accounting.get("strict_usd_pf_lower_bound_5pct"),
        "volatility_cohort_log_exists": goal_accounting.get("cohort_log_exists"),
        "bullish_pullback_layer4_protocol_status": layer4_capture_protocol.get("capture_protocol_status"),
        "historical_side_aware_net_usd_total": historical.get("historical_side_aware_net_usd_total"),
        "historical_side_aware_pf": historical.get("historical_side_aware_pf"),
        "historical_side_aware_pf_lb_5pct": historical.get("historical_side_aware_pf_lb_5pct"),
        "historical_rows_are_forward_proof": layer4_capture_protocol.get("historical_rows_are_forward_proof"),
        "historical_blockers": {
            "missing_required_quote_rows": historical_counts.get("missing_required_quote_rows"),
            "zero_or_untradable_rows": historical_counts.get("zero_or_untradable_rows"),
            "source_mark_mismatch_rows": historical_counts.get("source_mark_mismatch_rows"),
        },
        "no_chase_acknowledged": _as_dict(gateboard.get("no_chase_manifest")).get("status") == "no_chase_active",
    }
    return blockers, readback


def _status_for(
    *,
    source_artifacts: dict[str, dict[str, Any]],
    invariant_blockers: list[dict[str, Any]],
    candidate_validation: dict[str, Any],
    market_window_status: str,
    operator_approval_granted: bool,
) -> str:
    bad_sources = [meta for meta in source_artifacts.values() if meta.get("required") and meta.get("status") != "loaded"]
    if bad_sources:
        return "blocked_stale_or_missing_readbacks"
    if invariant_blockers:
        return "blocked_gateboard_or_no_chase"
    if candidate_validation.get("candidate_jsonl_supplied") and not candidate_validation.get("candidate_rows_valid_for_future_approval_no_append"):
        return "blocked_candidate_validation_failed"
    if market_window_status == "market_closed":
        return "blocked_market_closed"
    if market_window_status != "market_open":
        return "blocked_market_window_unknown"
    if not operator_approval_granted:
        return "blocked_operator_approval_missing"
    if candidate_validation.get("candidate_jsonl_supplied"):
        return "candidate_rows_valid_for_future_approval_no_append"
    return "ready_for_operator_approval_no_append"


def build_report(
    *,
    gateboard_path: Path = DEFAULT_GATEBOARD,
    trade_qualification_path: Path = DEFAULT_TRADE_QUALIFICATION,
    goal_loop_path: Path = DEFAULT_GOAL_LOOP,
    market_window_checklist_path: Path = DEFAULT_MARKET_WINDOW_CHECKLIST,
    paper_shadow_plan_path: Path = DEFAULT_PAPER_SHADOW_PLAN,
    layer4_capture_protocol_path: Path = DEFAULT_LAYER4_PROTOCOL,
    execution_safety_path: Path = DEFAULT_EXECUTION_SAFETY,
    executable_economics_path: Path = DEFAULT_EXECUTABLE_ECONOMICS,
    approval_packet_path: Path = DEFAULT_APPROVAL_PACKET,
    candidate_jsonl_path: Path | None = None,
    market_window_status: str = "unknown",
    operator_approval_token: str = "",
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    source_specs = {
        "gateboard": gateboard_path,
        "trade_qualification": trade_qualification_path,
        "goal_loop": goal_loop_path,
        "market_window_checklist": market_window_checklist_path,
        "paper_shadow_plan": paper_shadow_plan_path,
        "bullish_pullback_layer4_forward_capture_protocol": layer4_capture_protocol_path,
        "bullish_pullback_layer_execution_safety_audit": execution_safety_path,
        "bullish_pullback_layer_executable_economics": executable_economics_path,
    }
    loaded: dict[str, dict[str, Any]] = {}
    source_artifacts: dict[str, dict[str, Any]] = {}
    for name, path in source_specs.items():
        loaded[name], source_artifacts[name] = _load_json_artifact(
            path,
            name=name,
            required=True,
            generated_at_utc=generated_at,
            max_age_hours=MAX_SOURCE_AGE_HOURS,
        )
    approval_packet_text, source_artifacts["approval_packet"] = _load_text_artifact(approval_packet_path, required=True)
    invariant_blockers, readback_summary = _check_invariants(
        gateboard=loaded["gateboard"],
        trade_qualification=loaded["trade_qualification"],
        goal_loop=loaded["goal_loop"],
        market_window_checklist=loaded["market_window_checklist"],
        paper_shadow_plan=loaded["paper_shadow_plan"],
        layer4_capture_protocol=loaded["bullish_pullback_layer4_forward_capture_protocol"],
        execution_safety=loaded["bullish_pullback_layer_execution_safety_audit"],
        executable_economics=loaded["bullish_pullback_layer_executable_economics"],
        approval_packet_text=approval_packet_text,
    )
    candidate_report = _candidate_validation(candidate_jsonl_path, generated_at)
    operator_approval_granted = operator_approval_token == APPROVAL_TOKEN
    normalized_market_status = market_window_status if market_window_status in {"market_open", "market_closed"} else "unknown"
    overall_status = _status_for(
        source_artifacts=source_artifacts,
        invariant_blockers=invariant_blockers,
        candidate_validation=candidate_report,
        market_window_status=normalized_market_status,
        operator_approval_granted=operator_approval_granted,
    )
    next_operator_action = {
        "blocked_stale_or_missing_readbacks": "refresh the required readbacks, then rerun this preflight",
        "blocked_gateboard_or_no_chase": "resolve readback drift before considering layer4 forward evidence",
        "blocked_candidate_validation_failed": "repair or discard the candidate JSONL rows; do not append",
        "blocked_market_closed": "wait_for_valid_market_window_then_run_preflight_again",
        "blocked_market_window_unknown": "wait_for_valid_market_window_then_run_preflight_again",
        "blocked_operator_approval_missing": f"obtain explicit operator approval token `{APPROVAL_TOKEN}` after market-window checks",
        "ready_for_operator_approval_no_append": "stage candidate JSONL rows and rerun validation before any future approval decision",
        "candidate_rows_valid_for_future_approval_no_append": "candidate rows are valid for review only; no append path has been executed",
    }.get(overall_status, "stop and inspect the preflight report")

    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "overall_status": overall_status,
        "read_only": True,
        "append_allowed": False,
        "cohort_append_performed": False,
        "appended_forward_cohort_rows": False,
        "mutated_evidence_databases": False,
        "evidence_databases_mutated": False,
        "imported_quotes": False,
        "quotes_imported": False,
        "broker_order_allowed": False,
        "live_entry_allowed": False,
        "auto_track_allowed": False,
        "promotion_ready": False,
        "changed_scanner_policy": False,
        "changed_strategy_logic": False,
        "changed_stops": False,
        "changed_sizing": False,
        "lowered_proof_bars": False,
        "consumed_protected_holdout": False,
        "market_window_status": normalized_market_status,
        "market_window_valid": normalized_market_status == "market_open",
        "operator_approval_required": True,
        "operator_approval_granted": operator_approval_granted,
        "approval_token_required": APPROVAL_TOKEN,
        "approval_packet_path": _rel(approval_packet_path),
        "candidate_validation": candidate_report,
        "source_artifacts": source_artifacts,
        "invariant_blockers": invariant_blockers,
        "readback_summary": readback_summary,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
        "next_operator_action": next_operator_action,
        "artifacts": {},
    }


def render_markdown(report: dict[str, Any]) -> str:
    candidate = _as_dict(report.get("candidate_validation"))
    readback = _as_dict(report.get("readback_summary"))
    lines = [
        "# Regular Options Market-Window Approval Preflight",
        "",
        f"Generated: `{report.get('generated_at_utc')}`.",
        "",
        f"Status: `{report.get('overall_status')}`.",
        "",
        "## Safety Boundary",
        "",
        f"- Read-only: `{report.get('read_only')}`.",
        f"- Append allowed: `{report.get('append_allowed')}`.",
        f"- Cohort append performed: `{report.get('cohort_append_performed')}`.",
        f"- Broker/live/auto-track/promotion allowed: `{report.get('broker_order_allowed')}` / `{report.get('live_entry_allowed')}` / `{report.get('auto_track_allowed')}` / `{report.get('promotion_ready')}`.",
        f"- Quote import or evidence mutation: `{report.get('imported_quotes')}` / `{report.get('mutated_evidence_databases')}`.",
        "",
        "## Gate State",
        "",
        f"- Market-window status: `{report.get('market_window_status')}`.",
        f"- Operator approval granted: `{report.get('operator_approval_granted')}`.",
        f"- Candidate JSONL supplied: `{candidate.get('candidate_jsonl_supplied')}`.",
        f"- Candidate rows valid for future approval review: `{candidate.get('candidate_rows_valid_for_future_approval_no_append')}`.",
        f"- Candidate rejects: `{candidate.get('reject_counts')}`.",
        "",
        "## Current Proof Readback",
        "",
        f"- Volatility goal-loop state: `{readback.get('goal_loop_state')}`.",
        f"- Volatility strict rows: `{readback.get('volatility_post_freeze_strict_exact_completed_rows')}` / `{readback.get('volatility_minimum_required_rows')}`.",
        f"- Volatility strict USD PF lower bound: `{readback.get('volatility_strict_usd_pf_lower_bound_5pct')}`.",
        f"- Bullish-pullback layer4 protocol: `{readback.get('bullish_pullback_layer4_protocol_status')}`.",
        f"- Historical side-aware net/PF/PF-LB: `{readback.get('historical_side_aware_net_usd_total')}` / `{readback.get('historical_side_aware_pf')}` / `{readback.get('historical_side_aware_pf_lb_5pct')}`.",
        f"- Historical rows are forward proof: `{readback.get('historical_rows_are_forward_proof')}`.",
        f"- Historical blockers: `{readback.get('historical_blockers')}`.",
        "",
        "## Next Operator Action",
        "",
        report.get("next_operator_action") or "",
        "",
    ]
    blockers = _as_list(report.get("invariant_blockers"))
    if blockers:
        lines.extend(["## Invariant Blockers", ""])
        for blocker in blockers:
            if isinstance(blocker, dict):
                lines.append(f"- `{blocker.get('code')}` observed `{blocker.get('observed')}` expected `{blocker.get('expected')}`")
        lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = str(report["generated_at_utc"]).replace("-", "").replace(":", "").replace("Z", "Z")
    artifact_base = output_dir / f"{REPORT_ID}_{stamp}"
    json_path = artifact_base.with_suffix(".json")
    markdown_path = artifact_base.with_suffix(".md")
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_markdown = output_dir / f"{REPORT_ID}_latest.md"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(markdown_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_markdown),
        "docs_report": _rel(docs_report),
    }
    report = dict(report)
    report["artifacts"] = artifacts
    text = render_markdown(report)
    payload = json.dumps(report, indent=2, sort_keys=True)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    markdown_path.write_text(text, encoding="utf8")
    latest_markdown.write_text(text, encoding="utf8")
    docs_report.write_text(text, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail-closed market-window approval preflight for bullish-pullback layer4 paper-shadow rows.")
    parser.add_argument("--gateboard", type=Path, default=DEFAULT_GATEBOARD)
    parser.add_argument("--trade-qualification", type=Path, default=DEFAULT_TRADE_QUALIFICATION)
    parser.add_argument("--goal-loop", type=Path, default=DEFAULT_GOAL_LOOP)
    parser.add_argument("--market-window-checklist", type=Path, default=DEFAULT_MARKET_WINDOW_CHECKLIST)
    parser.add_argument("--paper-shadow-plan", type=Path, default=DEFAULT_PAPER_SHADOW_PLAN)
    parser.add_argument("--layer4-capture-protocol", type=Path, default=DEFAULT_LAYER4_PROTOCOL)
    parser.add_argument("--execution-safety", type=Path, default=DEFAULT_EXECUTION_SAFETY)
    parser.add_argument("--executable-economics", type=Path, default=DEFAULT_EXECUTABLE_ECONOMICS)
    parser.add_argument("--approval-packet", type=Path, default=DEFAULT_APPROVAL_PACKET)
    parser.add_argument("--candidate-jsonl", type=Path, default=None)
    parser.add_argument("--market-window-status", choices=["unknown", "market_open", "market_closed", "market_window_required", "not_required_for_readonly"], default="unknown")
    parser.add_argument("--operator-approval-token", default="")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        gateboard_path=args.gateboard,
        trade_qualification_path=args.trade_qualification,
        goal_loop_path=args.goal_loop,
        market_window_checklist_path=args.market_window_checklist,
        paper_shadow_plan_path=args.paper_shadow_plan,
        layer4_capture_protocol_path=args.layer4_capture_protocol,
        execution_safety_path=args.execution_safety,
        executable_economics_path=args.executable_economics,
        approval_packet_path=args.approval_packet,
        candidate_jsonl_path=args.candidate_jsonl,
        market_window_status=args.market_window_status,
        operator_approval_token=args.operator_approval_token,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"{REPORT_ID}: {report['overall_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
