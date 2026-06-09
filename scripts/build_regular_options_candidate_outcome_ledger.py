from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_candidate_outcome_ledger"

DEFAULT_FRESH_EVIDENCE_LOOP = ROOT / "data" / "forward-tracking" / "regular_options_fresh_evidence_loop_latest.json"
DEFAULT_PAPER_SHORTLIST = ROOT / "data" / "profitability-lab" / "regular-options-paper-shortlist" / "latest.json"
DEFAULT_PROFIT_CAPTURE_QUEUE = (
    ROOT / "data" / "profitability-lab" / "regular-options-profit-capture-queue" / "latest.json"
)
DEFAULT_OPEN_RISK = ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json"
DEFAULT_SUGGESTED_CLOSE_RISK = ROOT / "data" / "forward-tracking" / "suggested_trade_close_risk_latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-candidate-outcome-ledger.md"

PROHIBITED_ACTIONS = (
    "do_not_create_live_row_from_candidate_outcome_ledger",
    "do_not_submit_broker_order_from_candidate_outcome_ledger",
    "do_not_change_scanner_policy_from_candidate_outcome_ledger",
    "do_not_lower_exact_opra_nbbo_proof_bar_from_candidate_outcome_ledger",
    "do_not_treat_midpoint_stale_eod_or_manual_rows_as_production_proof",
)

ACTION_DETAILS: dict[str, dict[str, Any]] = {
    "resolve_open_risk_governor": {
        "priority": 0,
        "label": "Resolve open-risk governor",
        "operator_next_step": "Refresh explicit open-position reviews during a fresh executable quote window; do not open new live scanner-origin rows while blocked.",
    },
    "refresh_suggested_trade_review": {
        "priority": 1,
        "label": "Refresh suggested-trade review",
        "operator_next_step": "Refresh explicit suggested-trade review before relying on paper-idea close state or P&L.",
    },
    "refresh_open_position_executable_review": {
        "priority": 1,
        "label": "Refresh open-position executable review",
        "operator_next_step": "Rerun the read-only open-position risk audit during a fresh executable quote window before acting on display-only marks.",
    },
    "collect_exact_exit_evidence": {
        "priority": 2,
        "label": "Collect exact exit evidence",
        "operator_next_step": "Refresh exact OPRA/NBBO exit evidence for the linked paper/tracked row, then regenerate the fresh-evidence loop.",
    },
    "promotion_review_candidate": {
        "priority": 3,
        "label": "Promotion review candidate",
        "operator_next_step": "Review only after exact entry and exact realized exit evidence are present; this ledger is still read-only.",
    },
    "create_or_link_paper_review_row": {
        "priority": 4,
        "label": "Create/link paper review",
        "operator_next_step": "Create or link a paper-review row from fresh exact entry evidence; do not count it as live proof until exact exit readback exists.",
    },
    "capture_paper_only_exact_entry": {
        "priority": 5,
        "label": "Capture paper-only exact entry",
        "operator_next_step": "During market hours, capture a fresh executable exact OPRA/NBBO entry for this paper/probation lane.",
    },
    "diagnose_proof_ineligible_fill": {
        "priority": 6,
        "label": "Diagnose proof-ineligible fill",
        "operator_next_step": "Use the fill-attempt skip reason and quote snapshot to identify the proof gate that blocked the candidate.",
    },
    "capture_missing_fill_attempt_evidence": {
        "priority": 7,
        "label": "Capture missing fill attempt evidence",
        "operator_next_step": "Rerun the market-window validation path only if the candidate is still freshly selected; require durable fill-attempt logging.",
    },
    "wait_for_fresh_match_or_archive_candidate": {
        "priority": 8,
        "label": "Wait/archive stale candidate",
        "operator_next_step": "Do not chase old rows. Wait for a fresh scanner match or archive the stale candidate as no-longer-matched.",
    },
    "wait_for_fresh_executable_tier_a_bridge": {
        "priority": 9,
        "label": "Wait for Tier A fresh bridge",
        "operator_next_step": "Keep clean historical Tier A evidence in paper routing until a fresh executable lane-signature match appears.",
    },
    "repair_historical_evidence": {
        "priority": 10,
        "label": "Repair historical evidence",
        "operator_next_step": "Use the exact repair burn-down/source replay path before importing more data or treating the row as proof.",
    },
    "respect_guardrail_or_lane_mismatch": {
        "priority": 11,
        "label": "Respect guardrail/lane mismatch",
        "operator_next_step": "Keep blocked, symbol-only, or lane-mismatch rows out of paper shortlist and live promotion.",
    },
    "monitor_candidate": {
        "priority": 99,
        "label": "Monitor",
        "operator_next_step": "No immediate evidence action was inferred from the readbacks.",
    },
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _load_json_artifact(path: Path, *, required: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    source = {
        "path": str(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "generated_at_utc": None,
        "error": None,
    }
    if not path.exists():
        source["error"] = "missing_artifact"
        return {}, source
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        source["status"] = "unreadable"
        source["error"] = type(exc).__name__
        return {}, source
    if not isinstance(payload, dict):
        source["status"] = "invalid"
        source["error"] = "json_root_not_object"
        return {}, source
    source["status"] = "loaded"
    source["generated_at_utc"] = payload.get("generated_at_utc")
    return payload, source


def _action_priority(action: str) -> int:
    return int(ACTION_DETAILS.get(action, ACTION_DETAILS["monitor_candidate"])["priority"])


def _action_label(action: str) -> str:
    return str(ACTION_DETAILS.get(action, ACTION_DETAILS["monitor_candidate"])["label"])


def _operator_next_step(action: str) -> str:
    return str(ACTION_DETAILS.get(action, ACTION_DETAILS["monitor_candidate"])["operator_next_step"])


def _unique_text(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _norm(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _prohibited_actions(row: dict[str, Any] | None = None) -> list[str]:
    bridge = _as_dict((row or {}).get("evidence_bridge"))
    return _unique_text(_as_list(bridge.get("prohibited_actions")) + list(PROHIBITED_ACTIONS))


def _fresh_candidate_action(row: dict[str, Any]) -> tuple[str, str]:
    validation_outcome = _norm(row.get("validation_outcome"))
    entry_status = _norm(row.get("entry_evidence_status"))
    realized_status = _norm(row.get("realized_pnl_status"))
    position_status = _norm(row.get("position_link_status"))
    bridge_status = _norm(row.get("evidence_bridge_status"))
    has_position = row.get("auto_track_position_id") is not None

    if bool(row.get("promotion_discussion_ready")):
        return "promotion_review_candidate", "exact_entry_and_exact_realized_exit_readback_present"
    if has_position and realized_status in {"missing_realized_pnl", "missing_exact_exit_evidence"}:
        return "collect_exact_exit_evidence", f"linked_position_has_{realized_status}"
    if bridge_status == "paper_probation_exact_entry_required" or validation_outcome == "paper_only":
        return "capture_paper_only_exact_entry", "paper_or_probation_candidate_requires_fresh_exact_entry_evidence"
    if entry_status == "fresh_executable_exact_entry" and position_status == "no_tracked_or_suggested_link":
        return "create_or_link_paper_review_row", "fresh_exact_entry_exists_without_paper_or_tracked_link"
    if validation_outcome == "proof_ineligible":
        return "diagnose_proof_ineligible_fill", _norm(row.get("fill_outcome_reason")) or "proof_gate_blocked_candidate"
    if entry_status == "fill_attempt_missing" and validation_outcome != "no_longer_matched":
        return "capture_missing_fill_attempt_evidence", "candidate_missing_durable_fill_attempt_evidence"
    if validation_outcome == "no_longer_matched":
        return "wait_for_fresh_match_or_archive_candidate", _norm(row.get("validation_outcome_reason")) or "candidate_no_longer_matched"
    if bridge_status == "exact_exit_pnl_required":
        return "collect_exact_exit_evidence", "exact_exit_pnl_required"
    return "monitor_candidate", "no_immediate_evidence_action_inferred"


def _fresh_candidate_row(row: dict[str, Any]) -> dict[str, Any]:
    action, reason = _fresh_candidate_action(row)
    bridge = _as_dict(row.get("evidence_bridge"))
    blockers = _unique_text(
        _as_list(row.get("evidence_bridge_blockers"))
        + _as_list(bridge.get("blockers"))
        + _as_list(row.get("entry_evidence_reasons"))
        + [_norm(row.get("validation_outcome_reason")), _norm(row.get("fill_outcome_reason"))]
    )
    required_next_evidence = _unique_text(
        _as_list(row.get("required_next_evidence")) + _as_list(bridge.get("required_next_evidence"))
    )
    return {
        "ledger_key": f"fresh:{_norm(row.get('candidate_key'))}",
        "row_type": "candidate",
        "source_report": "fresh_evidence_loop",
        "scan_date": row.get("scan_date"),
        "playbook_id": row.get("playbook_id"),
        "lane_id": row.get("playbook_id"),
        "ticker": row.get("ticker"),
        "symbol": row.get("ticker"),
        "direction": row.get("direction"),
        "expiry": row.get("expiry"),
        "contract_symbol": row.get("contract_symbol"),
        "short_contract_symbol": row.get("short_contract_symbol"),
        "candidate_key": row.get("candidate_key"),
        "candidate_status": row.get("candidate_status"),
        "validation_outcome": row.get("validation_outcome"),
        "entry_evidence_status": row.get("entry_evidence_status"),
        "fill_attempt_status": row.get("fill_attempt_status"),
        "fill_status": row.get("fill_status"),
        "fill_outcome": row.get("fill_outcome"),
        "fill_outcome_reason": row.get("fill_outcome_reason"),
        "position_id": row.get("auto_track_position_id"),
        "position_link_status": row.get("position_link_status"),
        "realized_pnl_status": row.get("realized_pnl_status"),
        "evidence_bridge_status": row.get("evidence_bridge_status"),
        "promotion_gate_context": row.get("promotion_gate_context"),
        "promotion_discussion_ready": bool(row.get("promotion_discussion_ready")),
        "next_evidence_action": action,
        "action_label": _action_label(action),
        "action_priority": _action_priority(action),
        "action_reason": reason,
        "operator_next_step": _operator_next_step(action),
        "required_next_evidence": required_next_evidence,
        "blocking_reasons": blockers,
        "prohibited_actions": _prohibited_actions(row),
        "live_policy_change": bool(row.get("live_policy_change")),
    }


def _paper_shortlist_eligible_row(row: dict[str, Any]) -> dict[str, Any]:
    action = "create_or_link_paper_review_row"
    blockers = _unique_text(_as_list(row.get("blockers")) + _as_list(_as_dict(row.get("fresh_match_bridge")).get("blockers")))
    return {
        "ledger_key": "paper_shortlist:eligible:"
        + "|".join(
            [
                _norm(row.get("playbook_id") or row.get("lane_id")),
                _norm(row.get("symbol") or row.get("ticker")),
                _norm(row.get("expiry")),
            ]
        ),
        "row_type": "paper_shortlist_candidate",
        "source_report": "paper_shortlist",
        "playbook_id": row.get("playbook_id") or row.get("lane_id"),
        "lane_id": row.get("playbook_id") or row.get("lane_id"),
        "ticker": row.get("symbol") or row.get("ticker"),
        "symbol": row.get("symbol") or row.get("ticker"),
        "direction": row.get("direction"),
        "expiry": row.get("expiry"),
        "selection_readiness": row.get("selection_readiness") or "paper_shortlist_eligible",
        "bridge_status": row.get("bridge_status") or _as_dict(row.get("fresh_match_bridge")).get("status"),
        "next_evidence_action": action,
        "action_label": _action_label(action),
        "action_priority": _action_priority(action),
        "action_reason": "paper_shortlist_row_is_eligible_for_paper_review_creation_or_linking",
        "operator_next_step": _operator_next_step(action),
        "required_next_evidence": ["fresh_executable_exact_opra_nbbo_entry", "paper_review_link"],
        "blocking_reasons": blockers,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
        "live_policy_change": bool(row.get("live_policy_change")),
    }


def _paper_shortlist_bridge_action(blockers: list[str]) -> tuple[str, str]:
    blocker_set = set(blockers)
    if "guardrail_not_clear" in blocker_set or "lane_signature_not_matched" in blocker_set:
        return "respect_guardrail_or_lane_mismatch", "fresh_scan_row_failed_guardrail_or_lane_signature_bridge"
    return "wait_for_fresh_executable_tier_a_bridge", "fresh_scan_row_has_no_clean_tier_a_lane_match"


def _paper_shortlist_preview_row(row: dict[str, Any]) -> dict[str, Any]:
    blockers = _unique_text(_as_list(row.get("blockers")) + _as_list(_as_dict(row.get("fresh_match_bridge")).get("blockers")))
    action, reason = _paper_shortlist_bridge_action(blockers)
    return {
        "ledger_key": "paper_shortlist:bridge:"
        + "|".join(
            [
                _norm(row.get("playbook_id")),
                _norm(row.get("symbol") or row.get("ticker")),
                _norm(row.get("match_type")),
            ]
        ),
        "row_type": "paper_shortlist_bridge",
        "source_report": "paper_shortlist",
        "playbook_id": row.get("playbook_id"),
        "lane_id": row.get("playbook_id"),
        "ticker": row.get("symbol") or row.get("ticker"),
        "symbol": row.get("symbol") or row.get("ticker"),
        "direction": row.get("direction"),
        "expiry": row.get("expiry"),
        "guardrail_decision": row.get("guardrail_decision"),
        "match_type": row.get("match_type"),
        "matched_tier_a_lanes": _as_list(row.get("matched_tier_a_lanes")),
        "bridge_status": row.get("bridge_status"),
        "fresh_executable_quote_window": bool(row.get("fresh_executable_quote_window")),
        "next_evidence_action": action,
        "action_label": _action_label(action),
        "action_priority": _action_priority(action),
        "action_reason": reason,
        "operator_next_step": _operator_next_step(action),
        "required_next_evidence": ["fresh_executable_tier_a_lane_signature_match"],
        "blocking_reasons": blockers,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
        "live_policy_change": bool(row.get("live_policy_change")),
    }


def _profit_capture_action(row: dict[str, Any]) -> tuple[str, str]:
    readiness = _norm(row.get("selection_readiness"))
    repair_priority = _norm(row.get("evidence_repair_priority"))
    repair_actionability = _compact_repair_actionability(row.get("repair_actionability"))
    repair_status = _norm(repair_actionability.get("status"))
    if readiness == "paper_review_candidate":
        return "wait_for_fresh_executable_tier_a_bridge", "clean_historical_tier_a_row_requires_fresh_executable_bridge"
    if repair_priority in {"high", "medium"} or repair_status in {
        "needs_status_or_forward_validation_after_repair",
        "source_replay_required",
    }:
        return "repair_historical_evidence", "repair_queue_row_requires_exact_source_replay_or_status_readback"
    return "monitor_candidate", "profit_capture_row_not_in_active_evidence_queue"


def _compact_repair_actionability(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "status": value.get("status"),
            "next_action": value.get("next_action"),
            "attempt_count": value.get("attempt_count"),
            "target_count": value.get("target_count"),
            "current_source_exhausted_count": value.get("current_source_exhausted_count"),
            "blocking_gates": _as_list(value.get("blocking_gates")),
            "latest_proof_repair_statuses": _as_list(value.get("latest_proof_repair_statuses")),
        }
    text = _norm(value)
    return {"status": text} if text else {}


def _compact_repair_target_summary(value: Any) -> dict[str, Any]:
    summary = _as_dict(value)
    if not summary:
        return {}
    attempt_summary = _as_dict(summary.get("repair_attempt_summary"))
    return {
        "detail_status": summary.get("detail_status"),
        "targets_found": summary.get("targets_found"),
        "unresolved_rows": summary.get("unresolved_rows"),
        "shown_target_count": summary.get("shown_target_count"),
        "missing_leg_counts": _as_dict(summary.get("missing_leg_counts")),
        "contracts": _as_list(summary.get("contracts"))[:8],
        "missing_quote_dates": _as_list(summary.get("missing_quote_dates"))[:8],
        "source_artifacts": _as_list(summary.get("source_artifacts"))[:5],
        "next_repair_action": summary.get("next_repair_action"),
        "repair_attempt_summary": {
            "attempt_count": attempt_summary.get("attempt_count"),
            "current_source_exhausted_count": attempt_summary.get("current_source_exhausted_count"),
            "exact_date_row_count": attempt_summary.get("exact_date_row_count"),
            "lookahead_row_count": attempt_summary.get("lookahead_row_count"),
            "outcome_counts": _as_dict(attempt_summary.get("outcome_counts")),
            "proof_repair_status_counts": _as_dict(attempt_summary.get("proof_repair_status_counts")),
        },
    }


def _profit_capture_row(row: dict[str, Any]) -> dict[str, Any]:
    action, reason = _profit_capture_action(row)
    bridge = _as_dict(row.get("paper_shortlist_bridge")) or _as_dict(row.get("fresh_match_bridge"))
    repair_actionability = _compact_repair_actionability(row.get("repair_actionability"))
    repair_summary = _compact_repair_target_summary(row.get("repair_target_summary"))
    blockers = _unique_text(
        _as_list(row.get("reason_codes"))
        + _as_list(bridge.get("blockers"))
        + [
            _norm(row.get("selection_reason")),
            _norm(row.get("status_reason")),
            _norm(repair_actionability.get("status")),
            _norm(repair_actionability.get("next_action")),
        ]
    )
    return {
        "ledger_key": "profit_capture:"
        + "|".join(
            [
                _norm(row.get("lane_id") or row.get("playbook_id")),
                _norm(row.get("symbol") or row.get("ticker")),
                _norm(row.get("capture_tier")),
                _norm(row.get("selection_readiness")),
            ]
        ),
        "row_type": "profit_capture_candidate",
        "source_report": "profit_capture_queue",
        "lane_id": row.get("lane_id") or row.get("playbook_id"),
        "playbook_id": row.get("lane_id") or row.get("playbook_id"),
        "ticker": row.get("symbol") or row.get("ticker"),
        "symbol": row.get("symbol") or row.get("ticker"),
        "capture_tier": row.get("capture_tier"),
        "selection_readiness": row.get("selection_readiness"),
        "evidence_repair_priority": row.get("evidence_repair_priority"),
        "repair_actionability": repair_actionability,
        "sample_status": row.get("sample_status"),
        "metrics": row.get("metrics"),
        "bridge_status": bridge.get("status"),
        "repair_target_summary": repair_summary,
        "next_evidence_action": action,
        "action_label": _action_label(action),
        "action_priority": _action_priority(action),
        "action_reason": reason,
        "operator_next_step": _operator_next_step(action),
        "required_next_evidence": ["fresh_executable_tier_a_lane_signature_match"]
        if action == "wait_for_fresh_executable_tier_a_bridge"
        else ["exact_contract_quote_date_repair_or_source_replay"],
        "blocking_reasons": blockers,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
        "live_policy_change": bool(row.get("live_policy_change")),
    }


def _open_risk_governor_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    governor = _as_dict(report.get("open_risk_governor"))
    rows: list[dict[str, Any]] = []
    if governor.get("live_entry_allowed") is False:
        action = "resolve_open_risk_governor"
        details = _as_list(governor.get("governor_details")) or [
            {
                "id": None,
                "ticker": None,
                "lane": None,
                "next_safe_action": ";".join(_as_list(governor.get("next_safe_actions"))),
            }
        ]
        for detail in details:
            if not isinstance(detail, dict):
                continue
            blockers = _unique_text(_as_list(governor.get("blockers")) + [_norm(detail.get("reason"))])
            rows.append(
                {
                    "ledger_key": f"open_risk_governor:{_norm(detail.get('id')) or 'unkeyed'}",
                    "row_type": "operator_blocker",
                    "source_report": "open_position_risk",
                    "position_id": detail.get("id"),
                    "lane_id": detail.get("lane"),
                    "playbook_id": detail.get("lane"),
                    "ticker": detail.get("ticker"),
                    "symbol": detail.get("ticker"),
                    "record_class": detail.get("record_class"),
                    "evidence_bucket": detail.get("evidence_bucket"),
                    "pricing_state": detail.get("pricing_state"),
                    "recommendation": detail.get("recommendation"),
                    "current_pnl_pct": detail.get("current_pnl_pct"),
                    "next_safe_action": detail.get("next_safe_action"),
                    "next_evidence_action": action,
                    "action_label": _action_label(action),
                    "action_priority": _action_priority(action),
                    "action_reason": "open_risk_governor_blocks_live_entry",
                    "operator_next_step": _operator_next_step(action),
                    "required_next_evidence": ["fresh_executable_open_position_review"],
                    "blocking_reasons": blockers,
                    "prohibited_actions": list(PROHIBITED_ACTIONS),
                    "live_policy_change": bool(governor.get("live_policy_change")),
                }
            )
    for detail in _as_list(report.get("actionable_positions")):
        if not isinstance(detail, dict):
            continue
        action = "refresh_open_position_executable_review"
        rows.append(
            {
                "ledger_key": f"open_position_actionable:{_norm(detail.get('id')) or 'unkeyed'}",
                "row_type": "operator_blocker",
                "source_report": "open_position_risk",
                "position_id": detail.get("id"),
                "lane_id": detail.get("lane"),
                "playbook_id": detail.get("lane"),
                "ticker": detail.get("ticker"),
                "symbol": detail.get("ticker"),
                "record_class": detail.get("record_class"),
                "evidence_bucket": detail.get("evidence_bucket"),
                "pricing_state": detail.get("pricing_state"),
                "recommendation": detail.get("recommendation"),
                "current_pnl_pct": detail.get("current_pnl_pct"),
                "next_safe_action": detail.get("next_safe_action"),
                "next_evidence_action": action,
                "action_label": _action_label(action),
                "action_priority": _action_priority(action),
                "action_reason": "open_position_actionable_row_requires_fresh_executable_review",
                "operator_next_step": _operator_next_step(action),
                "required_next_evidence": ["fresh_executable_open_position_review"],
                "blocking_reasons": _unique_text([_norm(detail.get("reason")), _norm(detail.get("first_warning"))]),
                "prohibited_actions": list(PROHIBITED_ACTIONS),
                "live_policy_change": False,
            }
        )
    return rows


def _suggested_trade_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for detail in _as_list(report.get("attention_trades")):
        if not isinstance(detail, dict):
            continue
        action = "refresh_suggested_trade_review"
        rows.append(
            {
                "ledger_key": f"suggested_trade_attention:{_norm(detail.get('id')) or 'unkeyed'}",
                "row_type": "operator_blocker",
                "source_report": "suggested_trade_close_risk",
                "suggested_trade_id": detail.get("id"),
                "lane_id": detail.get("lane"),
                "playbook_id": detail.get("lane"),
                "ticker": detail.get("ticker"),
                "symbol": detail.get("ticker"),
                "record_class": detail.get("record_class"),
                "evidence_bucket": detail.get("evidence_bucket"),
                "pricing_state": detail.get("pricing_state"),
                "recommendation": detail.get("recommendation"),
                "current_pnl_pct": detail.get("current_pnl_pct"),
                "next_safe_action": detail.get("next_safe_action"),
                "next_evidence_action": action,
                "action_label": _action_label(action),
                "action_priority": _action_priority(action),
                "action_reason": "suggested_trade_attention_row_requires_explicit_review_refresh",
                "operator_next_step": _operator_next_step(action),
                "required_next_evidence": ["fresh_suggested_trade_review"],
                "blocking_reasons": _unique_text([_norm(detail.get("reason")), _norm(detail.get("first_warning"))]),
                "prohibited_actions": list(PROHIBITED_ACTIONS),
                "live_policy_change": False,
            }
        )
    return rows


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def priority(row: dict[str, Any]) -> int:
        value = row.get("action_priority")
        if value is None:
            return 99
        text = str(value).strip()
        if not text:
            return 99
        return int(text)

    return sorted(
        rows,
        key=lambda row: (
            priority(row),
            _norm(row.get("next_evidence_action")),
            _norm(row.get("source_report")),
            _norm(row.get("lane_id") or row.get("playbook_id")),
            _norm(row.get("ticker") or row.get("symbol")),
            _norm(row.get("ledger_key")),
        ),
    )


def _work_queue(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_norm(row.get("next_evidence_action")) or "monitor_candidate"].append(row)
    queue = []
    for action, items in grouped.items():
        sample_rows = [
            {
                "ledger_key": item.get("ledger_key"),
                "source_report": item.get("source_report"),
                "lane_id": item.get("lane_id"),
                "ticker": item.get("ticker"),
                "row_type": item.get("row_type"),
                "action_reason": item.get("action_reason"),
            }
            for item in _sort_rows(items)[:5]
        ]
        queue.append(
            {
                "next_evidence_action": action,
                "action_label": _action_label(action),
                "action_priority": _action_priority(action),
                "count": len(items),
                "operator_next_step": _operator_next_step(action),
                "sample_rows": sample_rows,
            }
        )
    return sorted(queue, key=lambda item: (int(item["action_priority"]), str(item["next_evidence_action"])))


def _input_status_counts(inputs: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(source.get("status") or "unknown") for source in inputs.values())
    return dict(sorted(counts.items()))


def _live_policy_change(inputs: dict[str, dict[str, Any]], loaded: list[dict[str, Any]], rows: list[dict[str, Any]]) -> bool:
    if any(bool(report.get("live_policy_change")) for report in loaded):
        return True
    if any(bool(_as_dict(report.get("summary")).get("live_policy_change")) for report in loaded):
        return True
    if any(bool(row.get("live_policy_change")) for row in rows):
        return True
    return any(bool(source.get("live_policy_change")) for source in inputs.values())


def _operating_status(
    *,
    inputs: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
    open_risk_report: dict[str, Any],
    paper_shortlist: dict[str, Any],
    fresh_evidence: dict[str, Any],
) -> str:
    missing_required = [name for name, source in inputs.items() if source.get("required") and source.get("status") != "loaded"]
    if missing_required:
        return "ledger_blocked_missing_inputs"
    governor = _as_dict(open_risk_report.get("open_risk_governor"))
    if governor.get("live_entry_allowed") is False:
        return "ledger_live_entry_blocked_collect_evidence"
    if any(row.get("next_evidence_action") == "promotion_review_candidate" for row in rows) or int(
        _as_dict(paper_shortlist.get("summary")).get("eligible_count") or 0
    ) > 0:
        return "ledger_has_review_candidates"
    if int(_as_dict(fresh_evidence.get("summary")).get("candidate_count") or 0) > 0:
        return "ledger_collect_exact_evidence"
    return "ledger_waiting_for_candidates"


def build_report(
    *,
    fresh_evidence_loop_path: Path = DEFAULT_FRESH_EVIDENCE_LOOP,
    paper_shortlist_path: Path = DEFAULT_PAPER_SHORTLIST,
    profit_capture_queue_path: Path = DEFAULT_PROFIT_CAPTURE_QUEUE,
    open_risk_path: Path = DEFAULT_OPEN_RISK,
    suggested_close_risk_path: Path = DEFAULT_SUGGESTED_CLOSE_RISK,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    fresh_evidence, fresh_source = _load_json_artifact(fresh_evidence_loop_path, required=True)
    paper_shortlist, shortlist_source = _load_json_artifact(paper_shortlist_path, required=False)
    profit_capture_queue, queue_source = _load_json_artifact(profit_capture_queue_path, required=False)
    open_risk, open_source = _load_json_artifact(open_risk_path, required=False)
    suggested_risk, suggested_source = _load_json_artifact(suggested_close_risk_path, required=False)
    inputs = {
        "fresh_evidence_loop": fresh_source,
        "paper_shortlist": shortlist_source,
        "profit_capture_queue": queue_source,
        "open_position_risk": open_source,
        "suggested_trade_close_risk": suggested_source,
    }

    rows: list[dict[str, Any]] = []
    rows.extend(_fresh_candidate_row(row) for row in _as_list(fresh_evidence.get("candidates")) if isinstance(row, dict))
    rows.extend(
        _paper_shortlist_eligible_row(row)
        for row in _as_list(paper_shortlist.get("eligible_paper_review_candidates"))
        if isinstance(row, dict)
    )
    rows.extend(
        _paper_shortlist_preview_row(row)
        for row in _as_list(paper_shortlist.get("fresh_scan_non_eligible_preview"))
        if isinstance(row, dict)
    )
    active_profit_rows = [
        row
        for row in _as_list(profit_capture_queue.get("capture_queue"))
        if isinstance(row, dict)
        and (
            _norm(row.get("selection_readiness")) == "paper_review_candidate"
            or _norm(row.get("evidence_repair_priority")) in {"high", "medium"}
            or _norm(row.get("repair_actionability")) == "needs_status_or_forward_validation_after_repair"
        )
    ]
    rows.extend(_profit_capture_row(row) for row in active_profit_rows)
    rows.extend(_open_risk_governor_rows(open_risk))
    rows.extend(_suggested_trade_rows(suggested_risk))
    rows = _sort_rows(rows)

    action_counts = Counter(_norm(row.get("next_evidence_action")) or "monitor_candidate" for row in rows)
    row_type_counts = Counter(_norm(row.get("row_type")) or "unknown" for row in rows)
    source_counts = Counter(_norm(row.get("source_report")) or "unknown" for row in rows)
    priority_counts = Counter(str(row.get("action_priority")) for row in rows)
    fresh_summary = _as_dict(fresh_evidence.get("summary"))
    shortlist_summary = _as_dict(paper_shortlist.get("summary"))
    queue_summary = _as_dict(profit_capture_queue.get("summary"))
    governor = _as_dict(open_risk.get("open_risk_governor"))
    loaded_reports = [fresh_evidence, paper_shortlist, profit_capture_queue, open_risk, suggested_risk]
    live_policy_change = _live_policy_change(inputs, loaded_reports, rows)

    summary = {
        "operating_status": _operating_status(
            inputs=inputs,
            rows=rows,
            open_risk_report=open_risk,
            paper_shortlist=paper_shortlist,
            fresh_evidence=fresh_evidence,
        ),
        "ledger_row_count": len(rows),
        "fresh_candidate_count": int(fresh_summary.get("candidate_count") or 0),
        "paper_shortlist_eligible_count": int(shortlist_summary.get("eligible_count") or 0),
        "paper_shortlist_invariant_violation_count": int(shortlist_summary.get("invariant_violation_count") or 0),
        "profit_capture_queue_rows": int(queue_summary.get("queue_rows") or 0),
        "profit_capture_paper_review_candidate_count": int(
            _as_dict(queue_summary.get("selection_readiness_counts")).get("paper_review_candidate") or 0
        ),
        "promotion_discussion_ready_count": int(fresh_summary.get("promotion_discussion_ready_count") or 0),
        "exact_realized_pnl_count": int(fresh_summary.get("exact_realized_pnl_count") or 0),
        "missing_realized_pnl_count": int(fresh_summary.get("missing_realized_pnl_count") or 0),
        "paper_probation_bridge_count": int(fresh_summary.get("paper_probation_bridge_count") or 0),
        "exact_exit_bridge_count": int(fresh_summary.get("exact_exit_bridge_count") or 0),
        "open_risk_live_entry_allowed": governor.get("live_entry_allowed"),
        "open_risk_status": governor.get("status"),
        "suggested_attention_count": len(_as_list(suggested_risk.get("attention_trades"))),
        "action_counts": dict(sorted(action_counts.items())),
        "row_type_counts": dict(sorted(row_type_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items(), key=lambda item: int(item[0]) if item[0].isdigit() else 99)),
        "input_status_counts": _input_status_counts(inputs),
        "live_policy_change": live_policy_change,
    }

    return {
        "report_id": REPORT_ID,
        "status": "candidate_outcome_ledger_readback",
        "generated_at_utc": generated_at,
        "scope": "regular_options_profitability_candidate_outcomes",
        "read_only": True,
        "schema_version": 1,
        "summary": summary,
        "inputs": inputs,
        "proof_policy": {
            "readback_is": "operator evidence queue for regular options profitability proof work",
            "readback_is_not": "scanner promotion, broker recommendation, stop-policy change, live-entry approval, proof-bar reduction, or DB mutation",
            "trusted_proof_standard": "fresh executable exact OPRA/NBBO contract evidence for entry plus exact executable exit readback for realized P&L",
            "prohibited_actions": list(PROHIBITED_ACTIONS),
        },
        "source_summaries": {
            "fresh_evidence_loop": fresh_summary,
            "paper_shortlist": shortlist_summary,
            "profit_capture_queue": queue_summary,
            "open_risk_governor": governor,
            "suggested_trade_close_risk": {
                "attention_trade_ids": _as_list(suggested_risk.get("attention_trade_ids")),
                "action_counts": _as_dict(suggested_risk.get("action_counts")),
                "evidence_counts": _as_dict(suggested_risk.get("evidence_counts")),
            },
        },
        "next_evidence_queue": _work_queue(rows),
        "ledger_rows": rows,
    }


def _json_inline(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    lines = [
        "# Regular Options Candidate Outcome Ledger",
        "",
        "This report is generated from `scripts/build_regular_options_candidate_outcome_ledger.py`. It turns the fresh-evidence loop, paper shortlist, profit-capture queue, open-risk governor, and suggested-trade close-risk readbacks into one read-only next-evidence queue without changing scanner, broker, auth, DB, stop, or proof behavior.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Operating status: `{summary.get('operating_status')}`.",
        f"- Ledger rows: `{summary.get('ledger_row_count')}`.",
        f"- Fresh candidates: `{summary.get('fresh_candidate_count')}`.",
        f"- Paper-shortlist eligible rows: `{summary.get('paper_shortlist_eligible_count')}`.",
        f"- Profit-capture paper-review candidates: `{summary.get('profit_capture_paper_review_candidate_count')}`.",
        f"- Promotion-ready rows: `{summary.get('promotion_discussion_ready_count')}`.",
        f"- Exact realized P&L rows: `{summary.get('exact_realized_pnl_count')}`.",
        f"- Missing realized P&L rows: `{summary.get('missing_realized_pnl_count')}`.",
        f"- Paper/probation exact-entry bridges: `{summary.get('paper_probation_bridge_count')}`.",
        f"- Exact-exit bridges: `{summary.get('exact_exit_bridge_count')}`.",
        f"- Open-risk live entry allowed: `{summary.get('open_risk_live_entry_allowed')}`.",
        f"- Suggested-trade attention rows: `{summary.get('suggested_attention_count')}`.",
        f"- Action counts: `{_json_inline(summary.get('action_counts') or {})}`.",
        f"- Live policy change: `{str(bool(summary.get('live_policy_change'))).lower()}`.",
        "",
        "## Next Evidence Queue",
        "",
        "| Priority | Action | Count | Operator next step |",
        "| --- | --- | ---: | --- |",
    ]
    for item in _as_list(report.get("next_evidence_queue")):
        if not isinstance(item, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{item.get('action_priority')}`",
                    f"`{item.get('next_evidence_action')}`",
                    f"`{item.get('count')}`",
                    _norm(item.get("operator_next_step")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Highest Priority Rows",
            "",
            "| Priority | Action | Source | Lane | Ticker | Reason |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in _as_list(report.get("ledger_rows"))[:20]:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.get('action_priority')}`",
                    f"`{row.get('next_evidence_action')}`",
                    f"`{row.get('source_report')}`",
                    f"`{_norm(row.get('lane_id') or row.get('playbook_id'))}`",
                    f"`{_norm(row.get('ticker') or row.get('symbol'))}`",
                    _norm(row.get("action_reason")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Source Readbacks",
            "",
            f"- Fresh evidence validation outcomes: `{_json_inline(_as_dict(report.get('source_summaries')).get('fresh_evidence_loop', {}).get('validation_outcome_counts') or {})}`.",
            f"- Fresh evidence bridge statuses: `{_json_inline(_as_dict(report.get('source_summaries')).get('fresh_evidence_loop', {}).get('evidence_bridge_status_counts') or {})}`.",
            f"- Paper shortlist release gate: `{_as_dict(_as_dict(report.get('source_summaries')).get('paper_shortlist')).get('release_gate_status')}`.",
            f"- Profit-capture selection readiness: `{_json_inline(_as_dict(_as_dict(report.get('source_summaries')).get('profit_capture_queue')).get('selection_readiness_counts') or {})}`.",
            f"- Open-risk governor status: `{_as_dict(_as_dict(report.get('source_summaries')).get('open_risk_governor')).get('status')}`.",
            "",
            "## Boundary",
            "",
            "This is an operator readback only. It does not create trades, submit broker orders, change scanner promotion, change stop policy, change auth/session behavior, change DB schema, lower proof bars, or turn paper/research/backfill evidence into production proof.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
    generated_at = _norm(report.get("generated_at_utc")).replace("-", "").replace(":", "").replace("+00:00", "Z")
    stamp = generated_at.replace("T", "T").replace("Z", "Z")
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / f"{REPORT_ID}_latest.json"
    latest_md = output_dir / f"{REPORT_ID}_latest.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
    }
    report["artifacts"] = artifacts
    payload_with_artifacts = json.dumps(report, indent=2, sort_keys=True) + "\n"
    json_path.write_text(payload_with_artifacts, encoding="utf8")
    latest_json.write_text(payload_with_artifacts, encoding="utf8")
    return artifacts


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the regular options candidate outcome ledger.")
    parser.add_argument("--fresh-evidence-loop", type=Path, default=DEFAULT_FRESH_EVIDENCE_LOOP)
    parser.add_argument("--paper-shortlist", type=Path, default=DEFAULT_PAPER_SHORTLIST)
    parser.add_argument("--profit-capture-queue", type=Path, default=DEFAULT_PROFIT_CAPTURE_QUEUE)
    parser.add_argument("--open-risk", type=Path, default=DEFAULT_OPEN_RISK)
    parser.add_argument("--suggested-close-risk", type=Path, default=DEFAULT_SUGGESTED_CLOSE_RISK)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    report = build_report(
        fresh_evidence_loop_path=args.fresh_evidence_loop,
        paper_shortlist_path=args.paper_shortlist,
        profit_capture_queue_path=args.profit_capture_queue,
        open_risk_path=args.open_risk,
        suggested_close_risk_path=args.suggested_close_risk,
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
