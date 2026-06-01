from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-operating-scorecard"
DEFAULT_DOC = ROOT / "docs" / "regular-options-operating-scorecard.md"
DEFAULT_AUTORESEARCH = ROOT / "data" / "profitability-lab" / "regular-options-autoresearch" / "experiments" / "latest.json"
DEFAULT_GUARDRAILS = ROOT / "data" / "forward-tracking" / "trading_desk_profitability_guardrails_latest.json"
DEFAULT_NEGATIVE_AUDIT = ROOT / "data" / "forward-tracking" / "trading_desk_negative_trade_decision_audit_latest.json"
DEFAULT_EXIT_REPLAY = ROOT / "data" / "forward-tracking" / "trading_desk_exit_policy_replay_latest.json"
DEFAULT_LEGACY_MISSED_CLOSE = ROOT / "data" / "forward-tracking" / "trading_desk_legacy_missed_close_audit_latest.json"
DEFAULT_GUARDRAIL_STARVATION = ROOT / "data" / "forward-tracking" / "regular_guardrail_starvation_latest.json"
DEFAULT_OPEN_POSITION_RISK = ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json"
DEFAULT_SUGGESTED_TRADE_CLOSE_RISK = ROOT / "data" / "forward-tracking" / "suggested_trade_close_risk_latest.json"
DEFAULT_API_PERFORMANCE = ROOT / "data" / "forward-tracking" / "trading_desk_api_performance_latest.json"
DEFAULT_AI_COMMODITY_PROGRESS = ROOT / "data" / "ai-commodity-infra" / "progress" / "latest.json"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "path": str(path), "missing": True}
    payload = json.loads(path.read_text(encoding="utf8"))
    if isinstance(payload, dict):
        payload.setdefault("available", True)
        payload.setdefault("path", str(path))
        return payload
    return {"available": False, "path": str(path), "error": "json_root_not_object"}


def _delta(after: Any, before: Any) -> float | None:
    before_value = safe_float(before)
    after_value = safe_float(after)
    if before_value is None or after_value is None:
        return None
    return round(after_value - before_value, 4)


def _summarize_autoresearch(payload: dict[str, Any]) -> dict[str, Any]:
    best = payload.get("best") if isinstance(payload.get("best"), dict) else {}
    metrics = best.get("autoresearch_metrics") if isinstance(best.get("autoresearch_metrics"), dict) else {}
    blockers = best.get("promotion_blockers") if isinstance(best.get("promotion_blockers"), list) else []
    score = safe_float(best.get("score"))
    clean_count = safe_float(metrics.get("promotable_clean_count"))
    lane_a_pf = safe_float(metrics.get("lane_a_conservative_profit_factor"))
    zero_bid_rate = safe_float(metrics.get("zero_bid_exit_rate_pct"))
    status = str(best.get("status") or "missing")
    return {
        "artifact_path": payload.get("path"),
        "experiment_batch": payload.get("experiment_batch"),
        "best_variant_id": best.get("variant_id"),
        "status": status,
        "score": score,
        "research_score": safe_float(best.get("research_score")),
        "clean_count": clean_count,
        "scout_count": safe_float(metrics.get("scout_count")),
        "effective_quote_coverage_pct": safe_float(metrics.get("effective_quote_coverage_pct")),
        "effective_unresolved_count": safe_float(metrics.get("effective_unresolved_count")),
        "zero_bid_exit_rate_pct": zero_bid_rate,
        "lane_a_conservative_profit_factor": lane_a_pf,
        "promotion_blockers": blockers,
        "visible_result": bool(
            status == "promotable_clean"
            or (lane_a_pf is not None and lane_a_pf >= 1.30 and clean_count is not None and clean_count >= 200)
        ),
        "still_blocked": bool(score is None or score <= 0 or blockers),
    }


def _summarize_guardrails(payload: dict[str, Any]) -> dict[str, Any]:
    baseline = payload.get("baseline") if isinstance(payload.get("baseline"), dict) else {}
    combined = payload.get("combined_promoted_guardrails") if isinstance(payload.get("combined_promoted_guardrails"), dict) else {}
    kept = combined.get("kept") if isinstance(combined.get("kept"), dict) else {}
    blocked = combined.get("blocked") if isinstance(combined.get("blocked"), dict) else {}
    avg_delta = _delta(kept.get("avg_pnl_pct"), baseline.get("avg_pnl_pct"))
    median_delta = _delta(kept.get("median_pnl_pct"), baseline.get("median_pnl_pct"))
    negative_rate_delta = _delta(kept.get("negative_rate_priced_pct"), baseline.get("negative_rate_priced_pct"))
    promoted = payload.get("promoted_guardrails") if isinstance(payload.get("promoted_guardrails"), list) else []
    return {
        "artifact_path": payload.get("path"),
        "baseline": {
            "rows": baseline.get("rows"),
            "priced": baseline.get("priced"),
            "avg_pnl_pct": safe_float(baseline.get("avg_pnl_pct")),
            "median_pnl_pct": safe_float(baseline.get("median_pnl_pct")),
            "negative_rate_priced_pct": safe_float(baseline.get("negative_rate_priced_pct")),
        },
        "promoted_kept_subset": {
            "rows": kept.get("rows"),
            "priced": kept.get("priced"),
            "avg_pnl_pct": safe_float(kept.get("avg_pnl_pct")),
            "median_pnl_pct": safe_float(kept.get("median_pnl_pct")),
            "negative_rate_priced_pct": safe_float(kept.get("negative_rate_priced_pct")),
        },
        "promoted_blocked_subset": {
            "rows": blocked.get("rows"),
            "priced": blocked.get("priced"),
            "avg_pnl_pct": safe_float(blocked.get("avg_pnl_pct")),
            "median_pnl_pct": safe_float(blocked.get("median_pnl_pct")),
            "negative_rate_priced_pct": safe_float(blocked.get("negative_rate_priced_pct")),
        },
        "deltas_vs_baseline": {
            "avg_pnl_pct": avg_delta,
            "median_pnl_pct": median_delta,
            "negative_rate_priced_pct": negative_rate_delta,
        },
        "promoted_guardrails": promoted,
        "visible_result": bool(
            avg_delta is not None
            and avg_delta > 0
            and median_delta is not None
            and median_delta > 0
            and negative_rate_delta is not None
            and negative_rate_delta < 0
        ),
    }


def _summarize_negative_audit(payload: dict[str, Any]) -> dict[str, Any]:
    targets = payload.get("legacy_missed_close_targets")
    if not isinstance(targets, list):
        targets = []
    negative_trades = payload.get("negative_trades")
    if not isinstance(negative_trades, list):
        negative_trades = []
    categories: dict[str, int] = {}
    for row in negative_trades:
        if not isinstance(row, dict):
            continue
        category = str(row.get("failure_category") or "unknown")
        categories[category] = categories.get(category, 0) + 1
    return {
        "artifact_path": payload.get("path"),
        "negative_trade_count": len(negative_trades),
        "legacy_missed_close_target_count": len(targets),
        "failure_category_counts": categories,
        "legacy_targets": [
            {
                "trade_id": row.get("trade_id"),
                "ticker": row.get("ticker"),
                "final_pnl_pct": safe_float(row.get("final_pnl_pct")),
                "first_negative_time": row.get("first_negative_time"),
                "best_executable_before_negative": row.get("best_executable_before_negative"),
                "positive_executable_sell_before_final_loss": row.get("positive_executable_sell_before_final_loss"),
                "failure_category": row.get("failure_category"),
            }
            for row in targets
            if isinstance(row, dict)
        ],
        "visible_result": bool(targets),
    }


def _summarize_exit_replay(payload: dict[str, Any]) -> dict[str, Any]:
    policies = payload.get("policies") if isinstance(payload.get("policies"), list) else []
    best = policies[0] if policies and isinstance(policies[0], dict) else {}
    promote = [
        policy
        for policy in policies
        if isinstance(policy, dict)
        and (policy.get("recommendation") or {}).get("status") == "promote_candidate"
    ]
    legacy_rows = []
    for policy in policies:
        if not isinstance(policy, dict):
            continue
        for row in policy.get("legacy_targets") or []:
            if isinstance(row, dict):
                legacy_rows.append(
                    {
                        "policy_id": policy.get("policy_id"),
                        "trade_id": row.get("trade_id"),
                        "ticker": row.get("ticker"),
                        "baseline_pnl_pct": safe_float(row.get("baseline_pnl_pct")),
                        "policy_pnl_pct": safe_float(row.get("policy_pnl_pct")),
                        "delta_vs_baseline_pct": safe_float(row.get("delta_vs_baseline_pct")),
                        "reason": row.get("reason"),
                        "reviewed_at": row.get("reviewed_at"),
                    }
                )
    return {
        "artifact_path": payload.get("path"),
        "baseline": payload.get("baseline") if isinstance(payload.get("baseline"), dict) else {},
        "best_policy_id": best.get("policy_id"),
        "best_policy_recommendation": (best.get("recommendation") or {}).get("status") if isinstance(best, dict) else None,
        "promote_candidate_count": len(promote),
        "legacy_target_replay_rows": legacy_rows,
        "legacy_target_positive_delta_count": sum(
            1 for row in legacy_rows if (safe_float(row.get("delta_vs_baseline_pct")) or 0.0) > 0
        ),
        "visible_result": bool(legacy_rows),
        "broad_exit_rule_ready": bool(promote),
    }


def _summarize_legacy_missed_close(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    return {
        "artifact_path": payload.get("path"),
        "available": not bool(payload.get("missing")),
        "recommendation": summary.get("recommendation"),
        "diagnosis_counts": summary.get("diagnosis_counts") or {},
        "current_action_required_count": int(summary.get("current_action_required_count") or 0),
        "historical_stale_path_count": int(summary.get("historical_stale_path_count") or 0),
        "target_count": int(summary.get("target_count") or len(rows) or 0),
    }


def _summarize_guardrail_starvation(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("missing"):
        return {
            "artifact_path": payload.get("path"),
            "available": False,
            "status": "missing",
            "playbooks_completed": 0,
            "candidate_count_total": None,
            "returned_count_total": None,
            "starvation_playbooks": [],
            "zero_candidate_playbook_count": 0,
            "top_drop_counts": [],
            "top_upstream_drop_details": [],
        }
    overall = payload.get("overall") if isinstance(payload.get("overall"), dict) else {}
    errors = payload.get("errors") if isinstance(payload.get("errors"), list) else []
    starvation_playbooks = list(overall.get("starvation_playbooks") or [])
    zero_candidate_playbooks = list(overall.get("zero_candidate_playbooks") or [])
    candidate_total = int(overall.get("candidate_count_total") or 0)
    completed = int(overall.get("playbooks_completed") or 0)
    status = overall.get("status")
    if not status:
        if errors:
            status = "audit_errors"
        elif starvation_playbooks:
            status = "guardrail_starvation_detected"
        elif completed and len(zero_candidate_playbooks) == completed and candidate_total == 0:
            status = "upstream_zero_candidate_scan_pressure"
        elif candidate_total > 0:
            status = "candidates_present_not_guardrail_starved"
        else:
            status = "no_guardrail_starvation_detected"
    return {
        "artifact_path": payload.get("path"),
        "available": True,
        "status": status,
        "generated_at_utc": payload.get("generated_at_utc"),
        "playbooks_completed": completed,
        "playbooks_requested": int(overall.get("playbooks_requested") or 0),
        "candidate_count_total": candidate_total,
        "returned_count_total": int(overall.get("returned_count_total") or 0),
        "candidate_decision_counts": overall.get("candidate_decision_counts") or {},
        "starvation_playbooks": starvation_playbooks,
        "zero_candidate_playbook_count": len(zero_candidate_playbooks),
        "top_drop_counts": list(overall.get("top_drop_counts") or []),
        "top_upstream_drop_details": list(overall.get("top_upstream_drop_details") or []),
        "error_count": len(errors),
    }


def _summarize_open_position_risk(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("missing"):
        return {
            "artifact_path": payload.get("path"),
            "available": False,
            "summary": {},
            "evidence_counts": {},
            "action_counts": {},
            "actionable_position_ids": [],
            "actionable_positions": [],
            "open_rows": None,
            "stored_executable_sell_count": 0,
            "stored_non_executable_sell_count": 0,
            "below_configured_stop_mark_count": 0,
            "executable_close_ready_count": 0,
            "review_required_count": 0,
            "current_action_required_count": 0,
        }
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    evidence_counts = payload.get("evidence_counts") if isinstance(payload.get("evidence_counts"), dict) else {}
    action_counts = payload.get("action_counts") if isinstance(payload.get("action_counts"), dict) else {}
    actionable_positions = [
        row for row in list(payload.get("actionable_positions") or []) if isinstance(row, dict)
    ]
    stored_executable = int(action_counts.get("stored_executable_sell") or 0)
    stored_non_executable = int(action_counts.get("stored_non_executable_sell") or 0)
    below_stop_mark = int(action_counts.get("below_configured_stop_mark") or 0)
    review_required = stored_non_executable + below_stop_mark
    return {
        "artifact_path": payload.get("path"),
        "available": True,
        "generated_at_utc": payload.get("generated_at_utc"),
        "summary": summary,
        "by_lane": payload.get("by_lane") if isinstance(payload.get("by_lane"), dict) else {},
        "by_record_class": payload.get("by_record_class") if isinstance(payload.get("by_record_class"), dict) else {},
        "evidence_counts": evidence_counts,
        "action_counts": action_counts,
        "actionable_position_ids": list(payload.get("actionable_position_ids") or []),
        "actionable_positions": actionable_positions,
        "open_rows": summary.get("rows"),
        "stored_executable_sell_count": stored_executable,
        "stored_non_executable_sell_count": stored_non_executable,
        "below_configured_stop_mark_count": below_stop_mark,
        "executable_close_ready_count": stored_executable,
        "review_required_count": review_required,
        "current_action_required_count": stored_executable + review_required,
    }


def _summarize_suggested_trade_close_risk(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("missing"):
        return {
            "artifact_path": payload.get("path"),
            "available": False,
            "storage_available": None,
            "summary": {},
            "evidence_counts": {},
            "action_counts": {},
            "close_risk_trade_ids": [],
            "stale_or_missing_review_trade_ids": [],
            "attention_trade_ids": [],
            "attention_trades": [],
            "open_rows": None,
            "stored_executable_sell_count": 0,
            "stored_non_executable_sell_count": 0,
            "mark_trigger_review_required_count": 0,
            "stale_or_missing_review_count": 0,
            "executable_close_ready_count": 0,
            "review_required_count": 0,
            "current_action_required_count": 0,
        }
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    evidence_counts = payload.get("evidence_counts") if isinstance(payload.get("evidence_counts"), dict) else {}
    action_counts = payload.get("action_counts") if isinstance(payload.get("action_counts"), dict) else {}
    attention_trades = [
        row for row in list(payload.get("attention_trades") or []) if isinstance(row, dict)
    ]
    stored_executable = int(action_counts.get("stored_executable_sell") or 0)
    stored_non_executable = int(action_counts.get("stored_non_executable_sell") or 0)
    mark_trigger_review_required = int(action_counts.get("below_configured_stop_mark") or 0) + int(
        action_counts.get("above_configured_target_mark") or 0
    )
    stale_or_missing = len(list(payload.get("stale_or_missing_review_trade_ids") or []))
    review_required_ids = {
        row.get("id")
        for row in attention_trades
        if row.get("id") is not None and row.get("action_bucket") != "stored_executable_sell"
    }
    review_required = (
        len(review_required_ids)
        if attention_trades
        else stored_non_executable + mark_trigger_review_required + stale_or_missing
    )
    return {
        "artifact_path": payload.get("path"),
        "available": True,
        "storage_available": payload.get("storage_available"),
        "load_error": payload.get("load_error"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "summary": summary,
        "closed_summary": payload.get("closed_summary") if isinstance(payload.get("closed_summary"), dict) else {},
        "by_lane": payload.get("by_lane") if isinstance(payload.get("by_lane"), dict) else {},
        "by_record_class": payload.get("by_record_class") if isinstance(payload.get("by_record_class"), dict) else {},
        "evidence_counts": evidence_counts,
        "action_counts": action_counts,
        "close_risk_trade_ids": list(payload.get("close_risk_trade_ids") or []),
        "stale_or_missing_review_trade_ids": list(payload.get("stale_or_missing_review_trade_ids") or []),
        "attention_trade_ids": list(payload.get("attention_trade_ids") or []),
        "attention_trades": attention_trades,
        "open_rows": summary.get("rows"),
        "stored_executable_sell_count": stored_executable,
        "stored_non_executable_sell_count": stored_non_executable,
        "mark_trigger_review_required_count": mark_trigger_review_required,
        "stale_or_missing_review_count": stale_or_missing,
        "executable_close_ready_count": stored_executable,
        "review_required_count": review_required,
        "current_action_required_count": stored_executable + review_required,
    }


def _endpoint_ref(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    return {
        "label": row.get("label"),
        "target": row.get("target"),
        "path": row.get("path"),
        "status_code": row.get("status_code"),
        "elapsed_ms": safe_float(row.get("elapsed_ms")),
        "backend_duration_ms": safe_float(row.get("backend_duration_ms")),
        "payload_bytes": row.get("payload_bytes"),
        "row_count": row.get("row_count"),
        "page": row.get("page") if isinstance(row.get("page"), dict) else None,
    }


def _summarize_api_performance(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("missing"):
        return {
            "artifact_path": payload.get("path"),
            "available": False,
            "status": "missing",
            "endpoint_count": 0,
            "ok_endpoint_count": 0,
            "error_endpoint_count": None,
            "frontend_max_elapsed_ms": None,
            "frontend_total_payload_bytes": None,
            "backend_max_duration_ms": None,
            "cache_stats": None,
            "slowest_frontend_endpoint": None,
            "largest_payload_endpoint": None,
            "routes": [],
        }
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    endpoints = [row for row in list(payload.get("endpoints") or []) if isinstance(row, dict)]
    return {
        "artifact_path": payload.get("path"),
        "available": True,
        "generated_at_utc": payload.get("generated_at_utc"),
        "status": summary.get("status") or "unknown",
        "endpoint_count": int(summary.get("endpoint_count") or len(endpoints)),
        "ok_endpoint_count": int(summary.get("ok_endpoint_count") or 0),
        "error_endpoint_count": int(summary.get("error_endpoint_count") or 0),
        "frontend_max_elapsed_ms": safe_float(summary.get("frontend_max_elapsed_ms")),
        "frontend_total_payload_bytes": summary.get("frontend_total_payload_bytes"),
        "backend_max_elapsed_ms": safe_float(summary.get("backend_max_elapsed_ms")),
        "backend_max_duration_ms": safe_float(summary.get("backend_max_duration_ms")),
        "slowest_frontend_endpoint": _endpoint_ref(summary.get("slowest_frontend_endpoint")),
        "slowest_backend_duration_endpoint": _endpoint_ref(summary.get("slowest_backend_duration_endpoint")),
        "largest_payload_endpoint": _endpoint_ref(summary.get("largest_payload_endpoint")),
        "cache_stats": summary.get("cache_stats") if isinstance(summary.get("cache_stats"), dict) else None,
        "routes": [_endpoint_ref(row) for row in endpoints],
    }


def _summarize_ai_commodity_progress(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("missing"):
        return {
            "artifact_path": payload.get("path"),
            "available": False,
            "status": "missing",
            "provider": None,
            "proof_source_label": None,
            "current_shared_quote_dates": None,
            "required_shared_quote_dates": None,
            "remaining_shared_quote_dates": None,
            "progress_pct": None,
            "verification_status": "missing",
            "verified": False,
            "live_scan_candidate_count": None,
            "proof_eligible_candidate_count": None,
            "scan_drop_reason_count": None,
            "capture_status": None,
            "capture_target_complete": None,
            "missing_target_symbol_count": None,
            "safe_to_tune_filters": False,
            "guarded_command_safe_to_execute_now": False,
            "guarded_command_next_when_allowed": None,
            "next_not_before_user_local": None,
            "blockers": [],
            "goal_completion_failed_requirements": [],
        }
    proof_window = payload.get("proof_window") if isinstance(payload.get("proof_window"), dict) else {}
    verification = payload.get("verification_gate") if isinstance(payload.get("verification_gate"), dict) else {}
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    scan = payload.get("scan") if isinstance(payload.get("scan"), dict) else {}
    capture = payload.get("capture") if isinstance(payload.get("capture"), dict) else {}
    lane_next = payload.get("lane_next_step") if isinstance(payload.get("lane_next_step"), dict) else {}
    lane_plan = payload.get("lane_next_step_plan") if isinstance(payload.get("lane_next_step_plan"), dict) else {}
    guard = payload.get("guarded_command_decision") if isinstance(payload.get("guarded_command_decision"), dict) else {}
    capture_outcome = (
        payload.get("exact_capture_progress_outcome")
        if isinstance(payload.get("exact_capture_progress_outcome"), dict)
        else {}
    )
    drop_diagnostics = [
        row
        for row in list(scan.get("drop_diagnostics") or [])
        if isinstance(row, dict)
    ]
    top_scan_drops = [
        {
            "drop_key": row.get("drop_key"),
            "count": row.get("count"),
            "example_symbols": list(row.get("example_symbols") or [])[:4],
            "next_diagnostic_action": row.get("next_diagnostic_action"),
        }
        for row in drop_diagnostics[:5]
    ]
    missing_after = list(capture.get("missing_target_date_symbols_after") or capture.get("missing_target_date_symbols") or [])
    verification_blockers = list(verification.get("blockers") or [])
    lane_blockers = list(lane_next.get("blocked_gates") or [])
    scorecard_blockers = list(payload.get("profitability_evidence_scorecard_blockers") or [])
    failed_requirements = list(payload.get("goal_completion_failed_requirements") or [])
    return {
        "artifact_path": payload.get("path"),
        "available": True,
        "generated_at_utc": payload.get("generated_at"),
        "provider": payload.get("provider"),
        "proof_source_label": payload.get("proof_source_label"),
        "status": payload.get("profitability_evidence_scorecard_status") or verification.get("status") or "unknown",
        "profitability_evidence_scorecard_passed_requirement_count": payload.get(
            "profitability_evidence_scorecard_passed_requirement_count"
        ),
        "profitability_evidence_scorecard_total_requirement_count": payload.get(
            "profitability_evidence_scorecard_total_requirement_count"
        ),
        "current_shared_quote_dates": _first_present(
            proof_window.get("current_shared_quote_dates"),
            verification.get("current_shared_quote_dates"),
        ),
        "required_shared_quote_dates": _first_present(
            proof_window.get("required_shared_quote_dates"),
            verification.get("required_shared_quote_dates"),
        ),
        "remaining_shared_quote_dates": proof_window.get("remaining_shared_quote_dates"),
        "progress_pct": safe_float(proof_window.get("progress_pct")),
        "diagnostic_ready": bool(proof_window.get("diagnostic_ready")),
        "full_replay_unlock_date": proof_window.get("approx_completion_date_if_one_capture_per_weekday"),
        "diagnostic_replay_unlock_date": proof_window.get("approx_diagnostic_ready_date_if_one_capture_per_weekday"),
        "verification_status": verification.get("status") or "unknown",
        "verified": bool(verification.get("verified")),
        "source_quality_status": verification.get("source_quality_status"),
        "replay_total_trades": verification.get("replay_total_trades"),
        "replay_profit_factor": safe_float(verification.get("replay_profit_factor")),
        "replay_total_return_pct": safe_float(verification.get("replay_total_return_pct")),
        "live_scan_candidate_count": _first_present(
            verification.get("live_scan_candidate_count"),
            scan.get("candidate_count"),
        ),
        "proof_eligible_candidate_count": _first_present(
            verification.get("proof_eligible_candidate_count"),
            scan.get("proof_eligible_candidate_count"),
        ),
        "scan_drop_reason_count": scan.get("scan_drop_reason_count"),
        "top_scan_drops": top_scan_drops,
        "readiness_status": readiness.get("status"),
        "readiness_blocker": readiness.get("blocker"),
        "thin_required_underlying_count": len(list(readiness.get("thin_required_underlyings") or [])),
        "missing_required_underlying_count": len(list(readiness.get("missing_required_underlyings") or [])),
        "capture_status": capture.get("status"),
        "capture_target_date": capture.get("target_date"),
        "capture_target_complete": capture.get("target_capture_complete"),
        "missing_target_symbol_count": len(missing_after),
        "missing_target_symbols_preview": missing_after[:10],
        "capture_progress_status": capture_outcome.get("status"),
        "capture_progress_material": bool(capture_outcome.get("material_progress")),
        "capture_progress_next_action": capture_outcome.get("next_action"),
        "capture_progress_blockers": list(capture_outcome.get("blockers") or []),
        "lane_phase": lane_next.get("phase"),
        "priority_action": lane_next.get("priority_action"),
        "primary_blocker": lane_next.get("primary_blocker"),
        "safe_to_tune_filters": bool(lane_next.get("safe_to_tune_filters")),
        "next_timed_event_kind": lane_next.get("next_timed_event_kind"),
        "next_timed_action": lane_next.get("next_timed_action"),
        "next_timed_event_user_local": lane_next.get("next_timed_event_user_local"),
        "lane_plan_status": lane_plan.get("status"),
        "lane_plan_command": lane_plan.get("command"),
        "lane_plan_run_next_execution_command": bool(lane_plan.get("run_next_execution_command")),
        "guarded_command_status": guard.get("status"),
        "guarded_command_safe_to_execute_now": bool(guard.get("safe_to_execute_now")),
        "guarded_command_command": guard.get("command") or guard.get("command_display"),
        "guarded_command_next_when_allowed": guard.get("next_command_when_allowed"),
        "guarded_command_reason": guard.get("reason"),
        "next_not_before_user_local": guard.get("next_not_before_user_local"),
        "blockers": verification_blockers or scorecard_blockers or lane_blockers,
        "goal_completion_failed_requirements": failed_requirements,
        "production_filters_locked": not bool(lane_next.get("safe_to_tune_filters")),
    }


def _next_actions(
    *,
    autoresearch: dict[str, Any],
    guardrails: dict[str, Any],
    negative_audit: dict[str, Any],
    exit_replay: dict[str, Any],
    legacy_missed_close: dict[str, Any],
    guardrail_starvation: dict[str, Any],
    open_position_risk: dict[str, Any],
    suggested_trade_close_risk: dict[str, Any],
    api_performance: dict[str, Any],
    ai_commodity_progress: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    if open_position_risk.get("executable_close_ready_count"):
        actions.append(
            "Resolve still-open rows with stored executable SELL evidence before strategy or UI performance work."
        )
    if open_position_risk.get("review_required_count"):
        actions.append(
            "Do not close open rows from display-only marks; rerun explicit review during a fresh executable quote window for non-executable SELL or below-stop mark rows."
        )
    if suggested_trade_close_risk.get("executable_close_ready_count"):
        actions.append(
            "Resolve suggested trades with stored executable SELL evidence through explicit review auto-close or manual close using executable quote evidence."
        )
    if suggested_trade_close_risk.get("stored_non_executable_sell_count") or suggested_trade_close_risk.get(
        "mark_trigger_review_required_count"
    ):
        actions.append(
            "Do not close suggested trades from stale/display-only marks; refresh explicit review and require executable close evidence."
        )
    if suggested_trade_close_risk.get("stale_or_missing_review_count"):
        actions.append(
            "Refresh stale or missing suggested-trade reviews before relying on suggested-trade P&L or close state."
        )
    if legacy_missed_close.get("current_action_required_count"):
        actions.append(
            "Fix current auto-close handling for still-open rows with executable SELL evidence."
        )
    elif negative_audit.get("legacy_missed_close_target_count") and not legacy_missed_close.get("available"):
        actions.append(
            "Run the legacy rows 26/39/44 missed-close audit before changing broad exit policy."
        )
    elif legacy_missed_close.get("historical_stale_path_count"):
        actions.append(
            "Treat legacy rows 26/39/44 as historical stale-policy diagnostics, not a broad current exit-policy change."
        )
    starvation_status = str(guardrail_starvation.get("status") or "missing")
    if guardrails.get("visible_result") and starvation_status == "missing":
        actions.append(
            "Run the regular guardrail-starvation audit before loosening promoted Trading Desk entry guardrails."
        )
    elif guardrails.get("visible_result") and starvation_status == "guardrail_starvation_detected":
        actions.append(
            "Inspect guardrail-blocked candidate rows before loosening promoted Trading Desk entry guardrails."
        )
    elif guardrails.get("visible_result") and starvation_status == "upstream_zero_candidate_scan_pressure":
        actions.append(
            "Do not loosen promoted Trading Desk entry guardrails for the current no-pick state; investigate upstream scan/data/liquidity drops."
        )
    elif guardrails.get("visible_result"):
        actions.append(
            "Keep promoted Trading Desk entry guardrails active; current starvation audit does not show guardrails filtering all viable rows."
        )
    if autoresearch.get("still_blocked"):
        actions.append(
            "Do not tune Lane A entry/memory again; test a non-overlapping sleeve or materially different exit/liquidity rule."
        )
    if not exit_replay.get("broad_exit_rule_ready"):
        actions.append(
            "Do not promote a broad exit-policy replay; current candidates improve some rows but fail broader negative-rate/winner-loss checks."
        )
    if not api_performance.get("available"):
        actions.append(
            "Run the Trading Desk API performance audit so route latency, backend duration headers, payload windows, and cache stats stay visible in the operating scorecard."
        )
    elif api_performance.get("error_endpoint_count"):
        actions.append(
            "Fix failing Trading Desk performance probes before treating the latency and payload scorecard as representative."
        )
    if not ai_commodity_progress.get("available"):
        actions.append(
            "Run the AI commodity OPRA progress readback so the active proof lane is visible beside regular options."
        )
    else:
        if ai_commodity_progress.get("guarded_command_safe_to_execute_now"):
            command = ai_commodity_progress.get("guarded_command_command") or ai_commodity_progress.get(
                "lane_plan_command"
            )
            actions.append(
                f"Run the allowed AI commodity guarded command and then rerun the next-execution readback: `{command}`."
            )
        elif ai_commodity_progress.get("guarded_command_next_when_allowed"):
            actions.append(
                "Keep AI commodity production filters locked; wait for the guarded OPRA event before running "
                f"`{ai_commodity_progress.get('guarded_command_next_when_allowed')}`."
            )
        if ai_commodity_progress.get("capture_progress_status") == "exact_capture_progress_failed_or_not_observed":
            actions.append(
                "Repair the AI commodity exact OPRA capture failure before strategy tuning; the latest target capture did not advance shared quote dates."
            )
        elif ai_commodity_progress.get("remaining_shared_quote_dates"):
            actions.append(
                "Continue AI commodity exact OPRA capture/readback until shared bid/ask history unlocks replay."
            )
    return actions


def build_scorecard(
    *,
    autoresearch_path: Path = DEFAULT_AUTORESEARCH,
    guardrails_path: Path = DEFAULT_GUARDRAILS,
    negative_audit_path: Path = DEFAULT_NEGATIVE_AUDIT,
    exit_replay_path: Path = DEFAULT_EXIT_REPLAY,
    legacy_missed_close_path: Path = DEFAULT_LEGACY_MISSED_CLOSE,
    guardrail_starvation_path: Path = DEFAULT_GUARDRAIL_STARVATION,
    open_position_risk_path: Path = DEFAULT_OPEN_POSITION_RISK,
    suggested_trade_close_risk_path: Path = DEFAULT_SUGGESTED_TRADE_CLOSE_RISK,
    api_performance_path: Path = DEFAULT_API_PERFORMANCE,
    ai_commodity_progress_path: Path = DEFAULT_AI_COMMODITY_PROGRESS,
) -> dict[str, Any]:
    autoresearch = _summarize_autoresearch(_load_json(autoresearch_path))
    guardrails = _summarize_guardrails(_load_json(guardrails_path))
    negative_audit = _summarize_negative_audit(_load_json(negative_audit_path))
    exit_replay = _summarize_exit_replay(_load_json(exit_replay_path))
    legacy_missed_close = _summarize_legacy_missed_close(_load_json(legacy_missed_close_path))
    guardrail_starvation = _summarize_guardrail_starvation(_load_json(guardrail_starvation_path))
    open_position_risk = _summarize_open_position_risk(_load_json(open_position_risk_path))
    suggested_trade_close_risk = _summarize_suggested_trade_close_risk(_load_json(suggested_trade_close_risk_path))
    api_performance = _summarize_api_performance(_load_json(api_performance_path))
    ai_commodity_progress = _summarize_ai_commodity_progress(_load_json(ai_commodity_progress_path))
    product_progress = bool(guardrails.get("visible_result") or negative_audit.get("visible_result"))
    proof_progress = bool(autoresearch.get("visible_result"))
    status = (
        "proof_grade_profitability_ready"
        if proof_progress
        else "visible_product_profitability_progress_but_proof_still_blocked"
        if product_progress
        else "no_material_profitability_progress_visible"
    )
    return {
        "generated_at_utc": _utc_now_iso(),
        "scope": "active_options_operating_scorecard",
        "status": status,
        "product_profitability_progress_visible": product_progress,
        "proof_grade_profitability_progress_visible": proof_progress,
        "autoresearch": autoresearch,
        "trading_desk_guardrails": guardrails,
        "negative_decision_audit": negative_audit,
        "exit_policy_replay": exit_replay,
        "legacy_missed_close_audit": legacy_missed_close,
        "guardrail_starvation_audit": guardrail_starvation,
        "open_position_risk": open_position_risk,
        "suggested_trade_close_risk": suggested_trade_close_risk,
        "api_performance": api_performance,
        "ai_commodity_progress": ai_commodity_progress,
        "next_actions": _next_actions(
            autoresearch=autoresearch,
            guardrails=guardrails,
            negative_audit=negative_audit,
            exit_replay=exit_replay,
            legacy_missed_close=legacy_missed_close,
            guardrail_starvation=guardrail_starvation,
            open_position_risk=open_position_risk,
            suggested_trade_close_risk=suggested_trade_close_risk,
            api_performance=api_performance,
            ai_commodity_progress=ai_commodity_progress,
        ),
    }


def markdown_report(scorecard: dict[str, Any]) -> str:
    guard = scorecard["trading_desk_guardrails"]
    auto = scorecard["autoresearch"]
    negative = scorecard["negative_decision_audit"]
    exit_replay = scorecard["exit_policy_replay"]
    legacy = scorecard["legacy_missed_close_audit"]
    starvation = scorecard["guardrail_starvation_audit"]
    open_risk = scorecard["open_position_risk"]
    suggested_risk = scorecard["suggested_trade_close_risk"]
    api_perf = scorecard["api_performance"]
    ai_commodity = scorecard["ai_commodity_progress"]
    lines = [
        "# Active Options Operating Scorecard",
        "",
        f"- Status: `{scorecard['status']}`",
        f"- Product profitability progress visible: `{scorecard['product_profitability_progress_visible']}`",
        f"- Proof-grade profitability progress visible: `{scorecard['proof_grade_profitability_progress_visible']}`",
        "",
        "## Trading Desk Guardrails",
        "",
        (
            f"- Baseline avg/median/negative-rate: `{guard['baseline']['avg_pnl_pct']}%` / "
            f"`{guard['baseline']['median_pnl_pct']}%` / `{guard['baseline']['negative_rate_priced_pct']}%`"
        ),
        (
            f"- Promoted kept avg/median/negative-rate: `{guard['promoted_kept_subset']['avg_pnl_pct']}%` / "
            f"`{guard['promoted_kept_subset']['median_pnl_pct']}%` / "
            f"`{guard['promoted_kept_subset']['negative_rate_priced_pct']}%`"
        ),
        f"- Deltas: `{guard['deltas_vs_baseline']}`",
        "",
        "## Frozen Proof Judge",
        "",
        f"- Best variant: `{auto.get('best_variant_id')}`",
        f"- Score/status: `{auto.get('score')}` / `{auto.get('status')}`",
        f"- Clean/scout count: `{auto.get('clean_count')}` / `{auto.get('scout_count')}`",
        f"- Lane A conservative PF / zero-bid rate: `{auto.get('lane_a_conservative_profit_factor')}` / `{auto.get('zero_bid_exit_rate_pct')}%`",
        f"- Blockers: `{auto.get('promotion_blockers')}`",
        "",
        "## Live Scan Starvation",
        "",
        f"- Status: `{starvation.get('status')}`",
        f"- Playbooks completed/requested: `{starvation.get('playbooks_completed')}` / `{starvation.get('playbooks_requested')}`",
        f"- Candidate/returned totals: `{starvation.get('candidate_count_total')}` / `{starvation.get('returned_count_total')}`",
        f"- Guardrail starvation playbooks: `{starvation.get('starvation_playbooks')}`",
        f"- Zero-candidate playbooks: `{starvation.get('zero_candidate_playbook_count')}`",
        f"- Leading drops: `{starvation.get('top_drop_counts')}`",
        "",
        "## Open Position Risk",
        "",
        f"- Open regular rows: `{open_risk.get('open_rows')}`",
        f"- Evidence counts: `{open_risk.get('evidence_counts')}`",
        f"- Action counts: `{open_risk.get('action_counts')}`",
        f"- Actionable open IDs: `{open_risk.get('actionable_position_ids')}`",
        f"- Executable close-ready rows: `{open_risk.get('executable_close_ready_count')}`",
        f"- Review-required non-executable rows: `{open_risk.get('review_required_count')}`",
        "",
        "## Suggested Trade Close Risk",
        "",
        f"- Open suggested rows: `{suggested_risk.get('open_rows')}`",
        f"- Evidence counts: `{suggested_risk.get('evidence_counts')}`",
        f"- Action counts: `{suggested_risk.get('action_counts')}`",
        f"- Close-risk suggested IDs: `{suggested_risk.get('close_risk_trade_ids')}`",
        f"- Stale/missing review IDs: `{suggested_risk.get('stale_or_missing_review_trade_ids')}`",
        f"- Executable close-ready suggested rows: `{suggested_risk.get('executable_close_ready_count')}`",
        f"- Review-required suggested rows: `{suggested_risk.get('review_required_count')}`",
        "",
        "## Trading Desk API Performance",
        "",
        f"- Status: `{api_perf.get('status')}`",
        f"- Endpoints ok/errors: `{api_perf.get('ok_endpoint_count')}` / `{api_perf.get('error_endpoint_count')}`",
        f"- Frontend max elapsed / total payload bytes: `{api_perf.get('frontend_max_elapsed_ms')} ms` / `{api_perf.get('frontend_total_payload_bytes')}`",
        f"- Backend max duration header: `{api_perf.get('backend_max_duration_ms')} ms`",
        f"- Slowest frontend route: `{api_perf.get('slowest_frontend_endpoint')}`",
        f"- Largest payload route: `{api_perf.get('largest_payload_endpoint')}`",
        f"- Cache stats: `{api_perf.get('cache_stats')}`",
        "",
        "## AI Commodity OPRA Proof Lane",
        "",
        f"- Status: `{ai_commodity.get('status')}`",
        f"- Provider/source: `{ai_commodity.get('provider')}` / `{ai_commodity.get('proof_source_label')}`",
        (
            f"- Exact shared quote dates: `{ai_commodity.get('current_shared_quote_dates')}` / "
            f"`{ai_commodity.get('required_shared_quote_dates')}` "
            f"(remaining `{ai_commodity.get('remaining_shared_quote_dates')}`)"
        ),
        (
            f"- Verification/replay: `{ai_commodity.get('verification_status')}` / "
            f"trades `{ai_commodity.get('replay_total_trades')}` / "
            f"PF `{ai_commodity.get('replay_profit_factor')}`"
        ),
        (
            f"- Live/proof candidates: `{ai_commodity.get('live_scan_candidate_count')}` / "
            f"`{ai_commodity.get('proof_eligible_candidate_count')}`"
        ),
        f"- Capture status: `{ai_commodity.get('capture_status')}` target `{ai_commodity.get('capture_target_date')}` complete `{ai_commodity.get('capture_target_complete')}` missing symbols `{ai_commodity.get('missing_target_symbol_count')}`",
        f"- Guarded command: status `{ai_commodity.get('guarded_command_status')}` safe-now `{ai_commodity.get('guarded_command_safe_to_execute_now')}` next `{ai_commodity.get('guarded_command_next_when_allowed')}` not-before `{ai_commodity.get('next_not_before_user_local')}`",
        f"- Safe to tune filters: `{ai_commodity.get('safe_to_tune_filters')}`",
        f"- Top scan drops: `{ai_commodity.get('top_scan_drops')}`",
        f"- Blockers: `{ai_commodity.get('blockers')}`",
        f"- Failed goal requirements: `{ai_commodity.get('goal_completion_failed_requirements')}`",
        "",
        "## Closed-Trade Follow-Up",
        "",
        f"- Negative trade rows audited: `{negative.get('negative_trade_count')}`",
        f"- Legacy missed-close targets: `{negative.get('legacy_missed_close_target_count')}`",
        f"- Legacy missed-close recommendation: `{legacy.get('recommendation')}`",
        f"- Legacy current action required: `{legacy.get('current_action_required_count')}`",
        f"- Broad exit promote candidates: `{exit_replay.get('promote_candidate_count')}`",
        f"- Legacy target positive replay rows: `{exit_replay.get('legacy_target_positive_delta_count')}`",
        "",
        "## Next Actions",
        "",
    ]
    for action in scorecard.get("next_actions") or []:
        lines.append(f"- {action}")
    return "\n".join(lines) + "\n"


def write_outputs(scorecard: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, doc_path: Path = DEFAULT_DOC) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"regular_options_operating_scorecard_{stamp}.json"
    latest_json = output_dir / "latest.json"
    payload = json.dumps(scorecard, indent=2, sort_keys=True)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    doc_path.write_text(markdown_report(scorecard), encoding="utf8")
    return {"json": str(json_path), "latest_json": str(latest_json), "markdown": str(doc_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the regular supervised options profitability operating scorecard.")
    parser.add_argument("--autoresearch", type=Path, default=DEFAULT_AUTORESEARCH)
    parser.add_argument("--guardrails", type=Path, default=DEFAULT_GUARDRAILS)
    parser.add_argument("--negative-audit", type=Path, default=DEFAULT_NEGATIVE_AUDIT)
    parser.add_argument("--exit-replay", type=Path, default=DEFAULT_EXIT_REPLAY)
    parser.add_argument("--legacy-missed-close", type=Path, default=DEFAULT_LEGACY_MISSED_CLOSE)
    parser.add_argument("--guardrail-starvation", type=Path, default=DEFAULT_GUARDRAIL_STARVATION)
    parser.add_argument("--open-position-risk", type=Path, default=DEFAULT_OPEN_POSITION_RISK)
    parser.add_argument("--suggested-trade-close-risk", type=Path, default=DEFAULT_SUGGESTED_TRADE_CLOSE_RISK)
    parser.add_argument("--api-performance", type=Path, default=DEFAULT_API_PERFORMANCE)
    parser.add_argument("--ai-commodity-progress", type=Path, default=DEFAULT_AI_COMMODITY_PROGRESS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    scorecard = build_scorecard(
        autoresearch_path=args.autoresearch,
        guardrails_path=args.guardrails,
        negative_audit_path=args.negative_audit,
        exit_replay_path=args.exit_replay,
        legacy_missed_close_path=args.legacy_missed_close,
        guardrail_starvation_path=args.guardrail_starvation,
        open_position_risk_path=args.open_position_risk,
        suggested_trade_close_risk_path=args.suggested_trade_close_risk,
        api_performance_path=args.api_performance,
        ai_commodity_progress_path=args.ai_commodity_progress,
    )
    payload: dict[str, Any] = {"scorecard": scorecard}
    if not args.no_write:
        payload["artifacts"] = write_outputs(scorecard, output_dir=args.output_dir, doc_path=args.doc_path)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps({"status": scorecard["status"], "next_actions": scorecard["next_actions"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
